"""Disk-backed JSONL store for memory schemas (§8.4).

One JSONL file per type. Append-only for upserts (latest wins on read by id).
This is the bootstrap shape — switch to mmap'd vector blob + sqlite metadata
later if perf demands.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Iterator

from ..state_paths import (
    ingest_cursors_path,
    prompt_nodes_path,
    turn_windows_path,
)
from ..utils import now_iso
from .schemas import PromptNode, TurnWindow


_write_lock = threading.Lock()


def _append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with _write_lock:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, separators=(",", ":")) + "\n")


def upsert_prompt_node(node: PromptNode) -> None:
    _append_jsonl(prompt_nodes_path(), node.to_dict())


def upsert_turn_window(window: TurnWindow) -> None:
    _append_jsonl(turn_windows_path(), window.to_dict())


def _iter_jsonl_latest_by_id(path: Path) -> Iterator[dict]:
    """Yield the latest record per id from a JSONL file (append-only upsert)."""
    if not path.exists():
        return
    seen: dict[str, dict] = {}
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            rid = record.get("id")
            if rid:
                seen[rid] = record
    yield from seen.values()


# Cap the in-process search index at the most-recent N prompts. Beyond that,
# old prompts stay on disk but aren't loaded for search/autofill — recent
# history is what the user typically searches for. Override with the env var
# TRINITY_PROMPT_NODE_LIMIT for testing or larger working sets.
import os as _os
PROMPT_NODE_SEARCH_LIMIT = int(_os.environ.get("TRINITY_PROMPT_NODE_LIMIT", "5000"))

_PROMPT_NODE_CACHE: list[PromptNode] | None = None
_PROMPT_NODE_CACHE_KEY: tuple[float, int, int] | None = None


def _node_sort_key(node: PromptNode) -> str:
    """Stable sort key for newest-first ordering. Prefers `timestamp` (the
    original turn time) and falls back to `created_at` (the ingest time)."""
    return node.timestamp or node.created_at or ""


_UNSET = object()  # Sentinel so callers can distinguish "default cap" from "explicit None"


def iter_prompt_nodes(*, limit: object = _UNSET) -> Iterator[PromptNode]:
    """Yield PromptNodes (newest first), capped at the configured search limit
    by default.

    - omit `limit`        → cap at PROMPT_NODE_SEARCH_LIMIT (search/autofill default)
    - `limit=None`        → NO CAP — full corpus scan (for ID lookups)
    - `limit=<int>`       → cap at that many

    Cached in-process by file mtime + size + effective limit. Parsing 18k JSONL
    records costs ~2.7s; with the cache, subsequent reads in the same process
    are ~5ms.
    """
    global _PROMPT_NODE_CACHE, _PROMPT_NODE_CACHE_KEY
    path = prompt_nodes_path()
    try:
        stat = path.stat()
        mtime, size = stat.st_mtime, stat.st_size
    except OSError:
        mtime, size = 0.0, 0

    if limit is _UNSET:
        effective_limit: int | None = PROMPT_NODE_SEARCH_LIMIT
    else:
        # `limit=None` explicitly means "no cap"; an int means "cap to that".
        effective_limit = limit  # type: ignore[assignment]

    signature = (mtime, size, effective_limit if effective_limit is not None else -1)

    if _PROMPT_NODE_CACHE is not None and _PROMPT_NODE_CACHE_KEY == signature:
        yield from _PROMPT_NODE_CACHE
        return

    nodes: list[PromptNode] = []
    for record in _iter_jsonl_latest_by_id(path):
        try:
            nodes.append(PromptNode.from_dict(record))
        except Exception:
            continue

    if effective_limit is not None and len(nodes) > effective_limit:
        # Sort newest-first, then truncate. Keeps search/autofill bounded as
        # ingest grows; users with deep history can raise the env var or pass
        # `limit=None` for full-corpus operations.
        nodes.sort(key=_node_sort_key, reverse=True)
        nodes = nodes[:effective_limit]

    _PROMPT_NODE_CACHE = nodes
    _PROMPT_NODE_CACHE_KEY = signature
    yield from nodes


def invalidate_prompt_node_cache() -> None:
    """Clear the in-process cache (used after batch upserts complete)."""
    global _PROMPT_NODE_CACHE, _PROMPT_NODE_CACHE_KEY
    _PROMPT_NODE_CACHE = None
    _PROMPT_NODE_CACHE_KEY = None


def iter_turn_windows() -> Iterator[TurnWindow]:
    for record in _iter_jsonl_latest_by_id(turn_windows_path()):
        try:
            yield TurnWindow.from_dict(record)
        except Exception:
            continue


def load_prompt_node(node_id: str) -> PromptNode | None:
    """Look up a PromptNode by id with NO recency cap.

    `iter_prompt_nodes()` defaults to the recent-N working set (5000), which
    is right for search/autofill but wrong for ID lookup: `record_council_outcome`
    gets called with prompt IDs that may be older than the cap. Without
    `limit=None` this silently returned no-match for old prompts.
    """
    for node in iter_prompt_nodes(limit=None):
        if node.id == node_id:
            return node
    return None


def record_council_outcome(
    *,
    prompt_node_id: str,
    council_run_id: str,
    chairman_winner: str | None = None,
    user_winner: str | None = None,
) -> bool:
    """Attach a council outcome to a PromptNode by re-upserting the record.

    Returns True if the node was found and updated.
    """
    node = load_prompt_node(prompt_node_id)
    if node is None:
        return False
    if council_run_id not in node.council_run_ids:
        node.council_run_ids = [*node.council_run_ids, council_run_id]
    if chairman_winner is not None:
        node.chairman_winner = chairman_winner
    if user_winner is not None:
        node.user_winner = user_winner
    node.last_replayed_at = now_iso()
    upsert_prompt_node(node)
    return True


def load_cursor(source: str) -> dict:
    """Cursor for incremental ingest. Returns {} if no cursor for this source."""
    path = ingest_cursors_path()
    if not path.exists():
        return {}
    try:
        all_cursors = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    if not isinstance(all_cursors, dict):
        return {}
    cursor = all_cursors.get(source) or {}
    return cursor if isinstance(cursor, dict) else {}


def save_cursor(source: str, cursor: dict) -> None:
    """Persist cursor for a source. Cursor shape is source-specific."""
    path = ingest_cursors_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with _write_lock:
        if path.exists():
            try:
                all_cursors = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(all_cursors, dict):
                    all_cursors = {}
            except (json.JSONDecodeError, OSError):
                all_cursors = {}
        else:
            all_cursors = {}
        all_cursors[source] = cursor
        path.write_text(json.dumps(all_cursors, indent=2), encoding="utf-8")
