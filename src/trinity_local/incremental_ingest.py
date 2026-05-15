"""Tool-triggered incremental ingest into the memory index.

Runs on the MCP hot path (or from CLI). Walks transcripts newer than a
per-source cursor at ``~/.trinity/memory/cursors.json`` and appends
``PromptNode`` records WITHOUT embeddings — embeddings are written by
``seed-from-taste-terminal`` (one-shot) or recomputed lazily by
``me-build`` / ``consolidate``. Per ``claude.md``: the read path stays
embedding-free, only seed and consolidation pay the embed cost.

Deadline-bounded: the caller passes ``deadline_s`` (default 2s) and we
persist the cursor at whichever path we got to so the next call resumes.
Designed to fire-and-forget at the start of MCP ``ask`` /
``search_prompts`` so newly-typed prompts become routable without a
manual ``seed-from-taste-terminal`` rerun.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from .ingest import iter_prompt_turns
from .memory import PromptNode, upsert_prompt_node
from .memory.store import iter_prompt_nodes
from .state_paths import ingest_cursors_path
from .task_types import guess_task_type
from .utils import now_iso, stable_id


DEFAULT_SOURCES = ("claude", "codex", "gemini", "cowork", "browser_claude", "browser_chatgpt")
DEFAULT_DEADLINE_S = 2.0


@dataclass
class IngestResult:
    scanned: int = 0
    added: int = 0
    skipped_existing: int = 0
    skipped_parse: int = 0
    sources: list[str] = field(default_factory=list)
    took_ms: int = 0
    deadline_hit: bool = False

    def to_dict(self) -> dict:
        return {
            "scanned": self.scanned,
            "added": self.added,
            "skipped_existing": self.skipped_existing,
            "skipped_parse": self.skipped_parse,
            "sources": list(self.sources),
            "took_ms": self.took_ms,
            "deadline_hit": self.deadline_hit,
        }


def _load_cursors() -> dict[str, float]:
    path = ingest_cursors_path()
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, float] = {}
    for source, entry in raw.items():
        if isinstance(entry, (int, float)):
            out[source] = float(entry)
        elif isinstance(entry, dict):
            mtime = entry.get("last_mtime", 0.0)
            try:
                out[source] = float(mtime or 0.0)
            except (TypeError, ValueError):
                out[source] = 0.0
    return out


def _save_cursors(cursors: dict[str, float]) -> None:
    path = ingest_cursors_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {source: {"last_mtime": mtime} for source, mtime in cursors.items()}
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    tmp.replace(path)


def _existing_prompt_node_ids() -> set[str]:
    # Uncapped: dedup needs every existing ID, not the 5000 most-recent.
    # Otherwise incremental_ingest reappends prompts whose IDs sit below
    # the cap (most of the user's corpus on a populated install).
    return {node.id for node in iter_prompt_nodes(limit=None)}


def ingest_recent(
    *,
    sources: list[str] | None = None,
    deadline_s: float = DEFAULT_DEADLINE_S,
) -> IngestResult:
    """Walk transcripts newer than the per-source cursor; append PromptNodes
    without embeddings. Bounded by ``deadline_s``; cursor is persisted at
    the latest-scanned path mtime so the next call resumes."""
    from .watch_runtime import _iter_recent_paths, _parse_source_path

    sources = list(sources or DEFAULT_SOURCES)
    cursors = _load_cursors()
    existing_ids = _existing_prompt_node_ids()

    started = time.monotonic()
    result = IngestResult(sources=sources)

    for source in sources:
        if time.monotonic() - started >= deadline_s:
            result.deadline_hit = True
            break
        last_mtime = cursors.get(source, 0.0)
        max_mtime = last_mtime

        try:
            paths = list(_iter_recent_paths(source, last_mtime))
        except (OSError, ValueError):
            continue

        for path in paths:
            if time.monotonic() - started >= deadline_s:
                result.deadline_hit = True
                break
            result.scanned += 1
            try:
                file_mtime = path.stat().st_mtime
            except OSError:
                continue
            max_mtime = max(max_mtime, file_mtime)

            try:
                session = _parse_source_path(source, path)
            except Exception:
                result.skipped_parse += 1
                continue
            if session is None:
                result.skipped_parse += 1
                continue

            try:
                turns = list(iter_prompt_turns(session))
            except Exception:
                result.skipped_parse += 1
                continue

            for turn in turns:
                node_id = stable_id(
                    "pnode", turn.transcript_id, str(turn.turn_index), turn.text[:200]
                )
                if node_id in existing_ids:
                    result.skipped_existing += 1
                    continue
                node = PromptNode(
                    id=node_id,
                    transcript_id=turn.transcript_id,
                    provider=turn.provider,
                    source_path=turn.source_path,
                    turn_index=turn.turn_index,
                    text=turn.text,
                    embedding=[],
                    created_at=now_iso(),
                    timestamp=turn.timestamp,
                    preceding_assistant_text=turn.preceding_assistant_text,
                    following_assistant_text=turn.following_assistant_text,
                    themes=[guess_task_type(turn.text)] if turn.text else [],
                )
                upsert_prompt_node(node)
                existing_ids.add(node_id)
                result.added += 1

        cursors[source] = max_mtime

    _save_cursors(cursors)
    result.took_ms = int((time.monotonic() - started) * 1000)
    return result
