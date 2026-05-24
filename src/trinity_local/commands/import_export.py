"""``trinity-local import-export PATH`` — bulk Takeout / web-export import (#148).

The existing ``seed-from-taste-terminal`` command requires a personal-rig
directory layout (``~/projects/taste-terminal/data/exports/...``). End
users with their own Takeout / ChatGPT-export downloads have arbitrary
paths, so they can't use it.

This command auto-detects the export type by probing structure:

- File ``conversations.json`` with array of dicts containing
  ``mapping`` → ChatGPT export
- File ``conversations.json`` with array of dicts containing
  ``chat_messages`` → Claude.ai export
- File ``MyActivity.html`` (or directory containing one under
  ``My Activity/Gemini Apps/``) → Gemini Takeout

If the path is a directory, walks it looking for any of the above
patterns. Each detected source is parsed and the SessionRecords are
indexed via the same Stage 0–1 pipeline that ``seed-from-taste-terminal``
uses (the actual indexer is shared — _flush_chunk + _stage_session
are imported from commands.seed).

This is the backend primitive the launchpad bulk-import UI will call.
Slice 1 of task #148 ships the CLI; the launchpad UI follows as
slice 2.
"""
from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any


def register(subparsers):
    parser = subparsers.add_parser(
        "import-export",
        help="Bulk-import a Takeout / web-export at any path. Auto-detects ChatGPT / Claude.ai / Gemini-Takeout (#148).",
    )
    # Positional preserved for CLI ergonomics; `--path` mirror added so
    # the capture-host action dispatcher (--flag VALUE shape) can fire
    # this from the launchpad without a positional-arg special case.
    parser.add_argument(
        "path",
        nargs="?",
        default=None,
        help="File OR directory containing the export. For a directory, recursively probes for known export files. Same as --path.",
    )
    parser.add_argument(
        "--path",
        dest="path_flag",
        default=None,
        help="Alias for the positional path arg. Used when invoked via capture-host action dispatch.",
    )
    parser.add_argument(
        "--source", default=None,
        choices=["claude_ai", "chatgpt", "gemini_takeout"],
        help="Force a specific parser instead of auto-detecting. Useful when probe heuristics get it wrong.",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Probe + print detection result without ingesting. Useful for debugging which parser would run.",
    )
    parser.add_argument(
        "--limit", type=int, default=None,
        help="Max sessions per detected source (default: all).",
    )
    parser.add_argument(
        "--batch-size", type=int, default=64,
        help="Embedding batch size (default 64).",
    )
    parser.add_argument(
        "--dim", type=int, default=768,
        help="Embedding dimension (default 768 — Nomic).",
    )
    parser.set_defaults(handler=handle_import_export)


def detect_exports(root: Path) -> list[dict[str, Any]]:
    """Probe ``root`` for known export shapes.

    Returns a list of ``{source, path, hint}`` dicts describing each
    detected export. Multiple may be returned when a directory contains
    several Takeout extracts (e.g., zip1 + zip2). Empty list when
    nothing matches — caller surfaces a "no exports found" hint.

    Detection precedence (when ambiguous, both are returned):
    1. Claude.ai: ``conversations.json`` whose first element has
       ``chat_messages`` key
    2. ChatGPT: ``conversations.json`` whose first element has
       ``mapping`` key
    3. Gemini: ``MyActivity.html`` under ``My Activity/Gemini Apps/``
       (full Takeout layout) or directly at root
    """
    detected: list[dict[str, Any]] = []

    if root.is_file():
        kind = _detect_single_file(root)
        if kind:
            detected.append({"source": kind, "path": str(root), "hint": "explicit file"})
        return detected

    # Directory walk — bounded depth so we don't traverse the user's
    # whole home dir if they pass /. Cap at 6 levels (enough for
    # nested Takeout zips: Takeout/My Activity/Gemini Apps/MyActivity.html)
    for path in _bounded_walk(root, max_depth=6):
        if path.is_file():
            kind = _detect_single_file(path)
            if kind:
                detected.append({"source": kind, "path": str(path), "hint": str(path.relative_to(root))})

    return detected


def _detect_single_file(path: Path) -> str | None:
    """Return the export kind for a single file, or None if unknown."""
    name = path.name.lower()
    if name == "conversations.json":
        return _detect_conversations_json(path)
    if name == "myactivity.html" or "myactivity" in name and name.endswith(".html"):
        return "gemini_takeout"
    return None


def _detect_conversations_json(path: Path) -> str | None:
    """conversations.json is used by both ChatGPT and Claude.ai exports
    — distinguish by inspecting first element's keys."""
    try:
        with path.open("r", encoding="utf-8") as fh:
            head = fh.read(8192)  # enough to see first conversation's keys
    except OSError:
        return None
    # Cheap structural check: look for distinguishing keys in the
    # first ~8KB. Both exports start with `[{...`; we just need to see
    # which key shows up first.
    chatgpt_pos = head.find('"mapping"')
    claude_pos = head.find('"chat_messages"')
    if chatgpt_pos >= 0 and (claude_pos < 0 or chatgpt_pos < claude_pos):
        return "chatgpt"
    if claude_pos >= 0:
        return "claude_ai"
    return None


def _bounded_walk(root: Path, *, max_depth: int) -> Iterator[Path]:
    """rglob with depth cap. Skips common noise dirs."""
    skip_names = {".git", "node_modules", "__pycache__", ".venv", "dist", "build"}
    base_depth = len(root.parts)
    try:
        for item in root.rglob("*"):
            try:
                depth = len(item.parts) - base_depth
            except ValueError:
                continue
            if depth > max_depth:
                continue
            if any(part in skip_names for part in item.parts):
                continue
            yield item
    except (OSError, PermissionError):
        return


def _parse_for_source(source: str, path: Path):
    """Dispatch to the right parser from ingest.py based on detected source."""
    from ..ingest import parse_chatgpt_export, parse_claude_ai_export, parse_gemini_takeout_html

    if source == "claude_ai":
        return parse_claude_ai_export(path)
    if source == "chatgpt":
        return parse_chatgpt_export(path)
    if source == "gemini_takeout":
        return parse_gemini_takeout_html(path)
    raise ValueError(f"unknown source: {source}")


def handle_import_export(args):
    # Accept either the positional path OR --path (capture-host
    # action-dispatch path uses --path because the host's allowlist
    # entry format is --flag VALUE pairs only).
    path_arg = args.path or getattr(args, "path_flag", None)
    if not path_arg:
        print(json.dumps({"ok": False, "error": "path is required (pass as positional or --path)"}, indent=2))
        raise SystemExit(2)
    root = Path(path_arg).expanduser().resolve()
    if not root.exists():
        print(json.dumps({"ok": False, "error": f"path not found: {root}"}, indent=2))
        raise SystemExit(1)

    # Detection phase
    if args.source:
        # User forced a parser — skip auto-detect, treat path as
        # explicit input to that parser
        detected = [{"source": args.source, "path": str(root), "hint": "forced via --source"}]
    else:
        detected = detect_exports(root)

    if not detected:
        print(json.dumps({
            "ok": False,
            "error": "no exports detected",
            "hint": (
                "Expected: a file conversations.json (ChatGPT or Claude.ai), "
                "or a Gemini Takeout extract containing My Activity/Gemini "
                "Apps/MyActivity.html. Pass --source to force a parser if "
                "auto-detect gets it wrong."
            ),
            "path": str(root),
        }, indent=2))
        raise SystemExit(1)

    if args.dry_run:
        print(json.dumps({
            "ok": True,
            "mode": "dry-run",
            "detected": detected,
        }, indent=2))
        return

    # Ingest phase — reuse seed.py's chunked indexer
    from .seed import _existing_prompt_node_ids, _flush_chunk, _stage_session

    existing_ids = _existing_prompt_node_ids()
    chunk: list[dict] = []
    prompts_indexed = 0
    windows_indexed = 0
    transcripts_indexed = 0
    sessions_indexed = 0
    sessions_seen = 0

    def _flush():
        nonlocal prompts_indexed, windows_indexed, transcripts_indexed, sessions_indexed
        if not chunk:
            return
        p, w, t = _flush_chunk(chunk, existing_ids, dim=args.dim, batch_size=args.batch_size)
        prompts_indexed += p
        windows_indexed += w
        transcripts_indexed += t
        sessions_indexed += sum(
            1 for s in chunk
            if not s["already_indexed"] and s["keepers"]
        )
        chunk.clear()

    chunk_size_target = 32
    per_source_counts: dict[str, int] = {}
    for entry in detected:
        source = entry["source"]
        path = Path(entry["path"])
        n_for_source = 0
        for session in _parse_for_source(source, path):
            if args.limit is not None and n_for_source >= args.limit:
                break
            sessions_seen += 1
            n_for_source += 1
            staged = _stage_session(session, existing_ids)
            if staged is None:
                continue
            chunk.append(staged)
            if len(chunk) >= chunk_size_target:
                _flush()
        per_source_counts[source] = per_source_counts.get(source, 0) + n_for_source

    _flush()  # tail

    print(json.dumps({
        "ok": True,
        "detected": detected,
        "per_source_sessions_seen": per_source_counts,
        "totals": {
            "sessions_seen": sessions_seen,
            "sessions_indexed": sessions_indexed,
            "prompts_indexed": prompts_indexed,
            "windows_indexed": windows_indexed,
            "transcripts_indexed": transcripts_indexed,
        },
    }, indent=2))
