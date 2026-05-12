"""Seed the memory index from external transcript exports.

v1: ingests claude_ai/, chatgpt*/, and gemini_takeout/ exports under
~/projects/taste-terminal/data/exports/ (or any compatible structure).

For each session yielded by the matching parser, writes:
  1. PromptNode per user-facing turn (via iter_prompt_turns)
  2. TurnWindow per PromptNode (skipped for single-turn sources like Gemini Takeout)

No LLM calls; pure embeddings + heuristics + metadata.
Resumable: skips PromptNode ids already on disk.
"""
from __future__ import annotations

import gc
import json
import os
import sys
import time
from pathlib import Path
from typing import Iterator

from ..ingest import (
    SessionRecord,
    iter_prompt_turns,
    parse_chatgpt_export,
    parse_claude_ai_export,
    parse_gemini_takeout_html,
)
from ..memory import (
    PromptNode,
    TurnWindow,
    iter_prompt_nodes,
    upsert_prompt_node,
    upsert_turn_window,
)
from ..task_types import guess_task_type
from ..utils import now_iso, stable_id


SOURCE_CHOICES = ("all", "claude_ai", "chatgpt", "gemini")


def register(subparsers):
    parser = subparsers.add_parser(
        "seed-from-taste-terminal",
        help="Seed memory index from ~/projects/taste-terminal/data/exports/ (claude_ai + chatgpt + gemini takeout)",
    )
    parser.add_argument("--path", required=True, help="Path to taste-terminal/data/exports/")
    parser.add_argument("--source", default="all", choices=SOURCE_CHOICES)
    parser.add_argument("--limit", type=int, default=None, help="Max sessions to ingest")
    parser.add_argument("--batch-size", type=int, default=64, help="Embedding batch size")
    parser.add_argument("--dim", type=int, default=768, help="Embedding dimension")
    parser.set_defaults(handler=handle_seed)


def _iter_sources(root: Path, source: str) -> Iterator[SessionRecord]:
    if source in ("all", "claude_ai"):
        path = root / "claude_ai" / "conversations.json"
        if path.exists():
            yield from parse_claude_ai_export(path)
    if source in ("all", "chatgpt"):
        for subdir in ("chatgpt", "chatgpt-2", "chatgpt-merged"):
            base = root / subdir
            if not base.is_dir():
                continue
            for path in sorted(base.glob("conversations*.json")):
                yield from parse_chatgpt_export(path)
    if source in ("all", "gemini"):
        for activity in sorted(root.glob("gemini_takeout/zip*/Takeout/My Activity/Gemini Apps/MyActivity.html")):
            yield from parse_gemini_takeout_html(activity)


def _existing_prompt_node_ids() -> set[str]:
    # Uncapped: dedup needs to see EVERY existing prompt ID, not just the
    # 5000 most-recent. Without this, re-running seed against an 18k-node
    # corpus would re-ingest the older 13k as if they were new (file
    # bloats; _iter_jsonl_latest_by_id collapses reads but the writes
    # waste disk + slow down subsequent loads).
    return {n.id for n in iter_prompt_nodes(limit=None)}


def _embed_in_batches(texts: list[str], *, dim: int, batch_size: int) -> list[list[float]]:
    from ..embeddings import embed_batch

    if not texts:
        return []
    return embed_batch(texts, dim=dim, batch_size=batch_size)


def _truncate_to_chars(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    half = max_chars // 2
    return text[:half] + "\n[...]\n" + text[-half:]


def _build_window_text(turn) -> str:
    """Compact context window for TurnWindow embedding.

    Capped at 1500 chars. Longer windows blow up MPS memory during batched
    encode without improving retrieval quality — Nomic gets diminishing
    returns past ~1.5k chars and the 8192-token ceiling is a *capacity*,
    not a target.
    """
    chunks: list[str] = []
    if turn.preceding_assistant_text:
        chunks.append(f"Previous assistant: {turn.preceding_assistant_text}")
    chunks.append(f"User: {turn.text}")
    if turn.following_assistant_text:
        chunks.append(f"Assistant: {turn.following_assistant_text}")
    return _truncate_to_chars("\n\n".join(chunks), 1500)


def _stage_session(session, existing_ids: set[str]) -> dict | None:
    """Phase 1: walk a session, decide what needs embedding.

    Returns a 'staged session' dict the chunk processor will consume, or None
    if the session has nothing to do (no turns, all already indexed).
    """
    turns = list(iter_prompt_turns(session))
    if not turns:
        return None

    node_ids = [
        stable_id("pnode", t.transcript_id, str(t.turn_index), t.text[:200])
        for t in turns
    ]
    if all(node_id in existing_ids for node_id in node_ids):
        return {"already_indexed": True, "session": session}

    keepers: list[tuple] = []  # list of (turn, node_id, theme)
    prompt_texts: list[str] = []
    for turn, node_id in zip(turns, node_ids):
        if node_id in existing_ids:
            continue
        prompt_texts.append(f"search_document: {turn.text}")
        keepers.append((turn, node_id, guess_task_type(turn.text)))

    is_multi_turn = len(turns) > 1
    window_texts: list[str] = []
    if is_multi_turn:
        for turn, _, _ in keepers:
            window_texts.append(f"search_document: {_build_window_text(turn)}")

    return {
        "already_indexed": False,
        "session": session,
        "keepers": keepers,
        "prompt_texts": prompt_texts,
        "window_texts": window_texts,
        "is_multi_turn": is_multi_turn,
    }


def _flush_chunk(staged: list[dict], existing_ids: set[str], dim: int, batch_size: int) -> tuple[int, int, int]:
    """Phase 2 + 3: embed all texts in the chunk in ONE batched call,
    then write all PromptNodes / TurnWindows.

    Returns (prompts, windows, _) written. The TranscriptNode tier
    was retired; the third element is always 0 for backwards-compat with the
    progress reporter.
    """
    # Build a single mega-batch of all texts (prompts + windows, mixed prefixes)
    texts: list[str] = []
    for s in staged:
        if s["already_indexed"]:
            continue
        texts.extend(s["prompt_texts"])
        texts.extend(s["window_texts"])

    if not texts:
        return (0, 0, 0)

    # ONE batched embed call across all sessions in the chunk
    vectors = _embed_in_batches(texts, dim=dim, batch_size=batch_size)

    prompts_written = 0
    windows_written = 0
    cursor = 0

    for s in staged:
        if s["already_indexed"]:
            continue
        session = s["session"]
        keepers = s["keepers"]
        is_multi_turn = s["is_multi_turn"]

        # Slice prompt vectors out
        n_prompts = len(s["prompt_texts"])
        prompt_vectors = vectors[cursor:cursor + n_prompts]
        cursor += n_prompts

        session_node_records: list[tuple[PromptNode, list[float]]] = []
        for (turn, node_id, theme), embedding in zip(keepers, prompt_vectors):
            node = PromptNode(
                id=node_id,
                transcript_id=turn.transcript_id,
                provider=turn.provider,
                source_path=turn.source_path,
                turn_index=turn.turn_index,
                text=turn.text,
                embedding=embedding,
                created_at=now_iso(),
                timestamp=turn.timestamp,
                preceding_assistant_text=turn.preceding_assistant_text,
                following_assistant_text=turn.following_assistant_text,
                themes=[theme] if theme else [],
            )
            upsert_prompt_node(node)
            existing_ids.add(node_id)
            prompts_written += 1
            session_node_records.append((node, embedding))

        # Slice window vectors out (one per kept prompt for multi-turn sessions)
        if is_multi_turn and session_node_records:
            n_windows = len(s["window_texts"])
            window_vectors = vectors[cursor:cursor + n_windows]
            cursor += n_windows
            for (node, _), window_text, vec in zip(
                session_node_records,
                [w.split("search_document: ", 1)[-1] for w in s["window_texts"]],
                window_vectors,
            ):
                window = TurnWindow(
                    id=stable_id("twin", node.transcript_id, str(node.turn_index)),
                    transcript_id=node.transcript_id,
                    center_prompt_id=node.id,
                    text=window_text,
                    embedding=vec,
                    turn_start=max(0, node.turn_index - 1),
                    turn_end=node.turn_index + 1,
                )
                upsert_turn_window(window)
                windows_written += 1

    return (prompts_written, windows_written, 0)


# Tunables: process N sessions per chunk. Larger chunks = bigger embed batches
# = better MLX throughput, at the cost of memory. Smaller chunks = more frequent
# heartbeat, easier to spot a stall.
SESSIONS_PER_CHUNK = 6

# Force a `gc.collect()` after this many chunks. MLX/PyTorch hold onto activations
# longer than CPython would; a periodic collect keeps RSS bounded over long runs.
GC_EVERY_N_CHUNKS = 4

# If a single _flush_chunk call takes longer than this, log a STALL warning.
# A healthy chunk on M-series finishes in ~5–30s. >2min means MPS is contending
# (or another seed is running concurrently — yes, that already happened once).
STALL_WARN_SECONDS = 120.0


def handle_seed(args):
    root = Path(args.path).expanduser().resolve()
    if not root.exists():
        print(json.dumps({"ok": False, "error": f"path not found: {root}"}, indent=2))
        sys.exit(1)

    existing_ids = _existing_prompt_node_ids()
    sessions_seen = 0
    sessions_indexed = 0
    prompts_indexed = 0
    windows_indexed = 0
    transcripts_indexed = 0
    skipped_existing = 0
    started = time.time()

    chunk: list[dict] = []
    chunk_index = 0
    pid = os.getpid()

    def _flush():
        nonlocal prompts_indexed, windows_indexed, transcripts_indexed, sessions_indexed, chunk_index
        if not chunk:
            return
        chunk_index += 1
        chunk_started = time.time()
        p, w, t = _flush_chunk(chunk, existing_ids, dim=args.dim, batch_size=args.batch_size)
        chunk_elapsed = time.time() - chunk_started
        prompts_indexed += p
        windows_indexed += w
        transcripts_indexed += t
        sessions_indexed += sum(
            1 for s in chunk
            if not s["already_indexed"] and s["keepers"]
        )
        chunk.clear()

        elapsed = time.time() - started
        rate = prompts_indexed / elapsed if elapsed > 0 else 0
        stall_marker = " STALL" if chunk_elapsed > STALL_WARN_SECONDS else ""
        print(
            f"  [pid={pid} chunk#{chunk_index}] took={chunk_elapsed:.1f}s "
            f"sessions={sessions_seen} prompts={prompts_indexed} windows={windows_indexed} "
            f"trans={transcripts_indexed} rate={rate:.1f}/s elapsed={elapsed:.0f}s{stall_marker}",
            file=sys.stderr,
            flush=True,
        )

        # Periodic GC keeps RSS bounded over long runs. MLX/torch caches are
        # non-trivial; without this RSS creeps up over the course of hours.
        if chunk_index % GC_EVERY_N_CHUNKS == 0:
            gc.collect()

    for session in _iter_sources(root, args.source):
        if args.limit is not None and sessions_seen >= args.limit:
            break
        sessions_seen += 1

        staged = _stage_session(session, existing_ids)
        if staged is None:
            continue
        if staged["already_indexed"]:
            skipped_existing += 1
            continue

        chunk.append(staged)

        if len(chunk) >= SESSIONS_PER_CHUNK:
            _flush()

    _flush()  # final partial chunk

    elapsed = time.time() - started
    print(json.dumps({
        "ok": True,
        "path": str(root),
        "source": args.source,
        "sessions_seen": sessions_seen,
        "sessions_indexed": sessions_indexed,
        "prompts_indexed": prompts_indexed,
        "windows_indexed": windows_indexed,
        "transcripts_indexed": transcripts_indexed,
        "skipped_existing": skipped_existing,
        "elapsed_seconds": round(elapsed, 2),
        "throughput_prompts_per_second": round(prompts_indexed / elapsed, 2) if elapsed > 0 else 0,
        "dim": args.dim,
    }, indent=2))
