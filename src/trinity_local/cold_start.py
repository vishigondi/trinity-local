"""Cold-start auto-scan of local CLI transcripts on first MCP spawn.

The wow flow needs personalization on the first council, not a week
later. The four local-CLI parsers (Claude Code, Codex, Gemini CLI,
Cowork) all read from on-disk dirs the user already has — so the
moment Trinity's MCP child starts under a brand-new install, we can
auto-detect "no corpus + at least one CLI source present" and kick a
background scan. The server keeps serving tool calls immediately;
tool responses surface a `cold_start_scan` hint so the agent can tell
the user "I'm ingesting your CLI history…" while the scan runs.

Privacy invariant: same data path as `seed-from-taste-terminal`. Only
walks transcript dirs the user already owns on this machine. No
exports, no network, no opt-in dialog. Same `incremental_ingest`
pipeline so dedup / cursors / parser fallthrough behavior is shared.

Disable for tests + CI with ``TRINITY_AUTOSCAN_DISABLED=1``; the
conftest autouse fixture sets it so tests never scan the developer's
real ``~/.claude/``.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from .state_paths import state_dir
from .utils import now_iso


COLD_START_SOURCES = ("claude", "codex", "gemini", "cowork")
DEFAULT_SCAN_DEADLINE_S = 300.0
HINT_FRESH_WINDOW_S = 600.0  # surface "scan complete" for 10 min after finish


def cold_start_state_path() -> Path:
    return state_dir() / "cold_start_scan.json"


def _autoscan_disabled() -> bool:
    return os.environ.get("TRINITY_AUTOSCAN_DISABLED", "").strip() not in ("", "0", "false", "False")


def detect_available_sources() -> list[str]:
    """Return the subset of local-CLI sources whose dirs exist on this
    machine. Empty dir counts as absent — a user who installed Claude
    Code but never ran it shouldn't trigger an empty cold-start scan."""
    from .watch_runtime import _iter_recent_paths, _source_root

    available: list[str] = []
    for source in COLD_START_SOURCES:
        try:
            root = _source_root(source)
        except ValueError:
            continue
        if not root.exists():
            continue
        # At least one matching transcript file present.
        if any(True for _ in _iter_recent_paths(source, 0.0)):
            available.append(source)
    return available


def _corpus_is_empty() -> bool:
    """True when no PromptNodes are on disk. Read directly from the
    JSONL file path to avoid pulling the full module + cache layer on
    the cold-start hot path."""
    from .state_paths import memory_dir

    path = memory_dir() / "prompt_nodes.jsonl"
    if not path.exists():
        return True
    try:
        return path.stat().st_size == 0
    except OSError:
        return True


def is_cold_start() -> bool:
    """Cold-start trigger: empty corpus AND no prior scan state AND at
    least one local CLI source present AND not disabled by env."""
    if _autoscan_disabled():
        return False
    if cold_start_state_path().exists():
        return False
    if not _corpus_is_empty():
        return False
    return bool(detect_available_sources())


def read_state() -> dict | None:
    path = cold_start_state_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _write_state(state: dict) -> None:
    from .utils import atomic_write_text
    atomic_write_text(cold_start_state_path(), json.dumps(state, indent=2))


def _run_scan(sources: list[str], deadline_s: float, start_iso: str) -> None:
    """The thread body. Runs the scan, rewrites the state file with the
    result. Wrapped in broad try/except: a parser blow-up in any source
    cannot leave the state file at status=in_progress forever (would
    block future cold-start triggers).

    The initial in_progress state file is written synchronously by
    ``kick_cold_start_scan`` BEFORE this thread starts, so the
    cross-process race (two MCP servers calling is_cold_start()
    simultaneously) closes via the existence-check on the state file.
    """
    from .incremental_ingest import ingest_recent

    started = time.monotonic()
    error: str | None = None
    added = 0
    scanned = 0
    try:
        result = ingest_recent(sources=sources, deadline_s=deadline_s)
        added = result.added
        scanned = result.scanned
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

    _write_state({
        "status": "failed" if error else "complete",
        "started_at": start_iso,
        "finished_at": now_iso(),
        "sources_detected": list(sources),
        "added": added,
        "scanned": scanned,
        "deadline_s": deadline_s,
        "duration_s": round(time.monotonic() - started, 2),
        "error": error,
    })


def kick_cold_start_scan(deadline_s: float = DEFAULT_SCAN_DEADLINE_S) -> dict | None:
    """Spawn the cold-start scan in a daemon thread. Returns the initial
    state dict (with status=in_progress), or None when no scan was kicked
    (autoscan disabled, corpus non-empty, prior scan present, or no
    available sources). Caller doesn't wait — the thread runs to deadline
    or completion and rewrites the state file.

    The initial in_progress state file is written SYNCHRONOUSLY before
    the daemon thread starts. This closes the cross-process race where
    two MCP servers (Claude Code + Codex CLI + Cursor + Gemini CLI all
    spawn on session start) call is_cold_start() simultaneously and
    both see an empty state — only the first to reach this function
    creates the state file; the rest hit the `is_cold_start()`
    state-file-exists short-circuit and return None.
    """
    if not is_cold_start():
        return None
    sources = detect_available_sources()
    if not sources:
        return None

    start_iso = now_iso()
    # Write the in_progress state BEFORE spawning the thread so the
    # second simultaneous caller's is_cold_start() check sees it and
    # bails. Within a single process, threading.Lock would be cheaper
    # but doesn't help across processes; the on-disk state file is
    # the cross-process serialization point.
    _write_state({
        "status": "in_progress",
        "started_at": start_iso,
        "finished_at": None,
        "sources_detected": list(sources),
        "added": 0,
        "scanned": 0,
        "deadline_s": deadline_s,
        "error": None,
    })

    thread = threading.Thread(
        target=_run_scan,
        args=(sources, deadline_s, start_iso),
        name="trinity-cold-start-scan",
        daemon=True,
    )
    thread.start()
    return read_state()


def cold_start_hint() -> dict | None:
    """For MCP tool responses. Returns a compact payload when the scan
    is running OR finished within ``HINT_FRESH_WINDOW_S``. The agent
    surfaces it inline so the user sees "I'm building your memory" without
    a launchpad detour. Returns None when no scan has ever fired (cold-
    start blocked or already-warm install) or when the scan is too old
    to be the agent's news."""
    state = read_state()
    if state is None:
        return None
    status = state.get("status")
    if status == "in_progress":
        return {
            "status": "in_progress",
            "message": (
                f"Trinity is ingesting your local CLI history "
                f"({', '.join(state.get('sources_detected', []))}). "
                f"Responses get more personal as it lands."
            ),
            "added_so_far": state.get("added", 0),
        }
    if status in ("complete", "failed"):
        # Only surface for a short window post-finish.
        finished_at = state.get("finished_at")
        if not finished_at:
            return None
        try:
            from datetime import datetime, timezone
            ts = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
            age_s = (datetime.now(timezone.utc) - ts).total_seconds()
        except (ValueError, TypeError):
            return None
        if age_s > HINT_FRESH_WINDOW_S:
            return None
        if status == "failed":
            return {
                "status": "failed",
                "message": (
                    "Cold-start ingest of your CLI history hit an error: "
                    f"{state.get('error') or 'unknown'}. "
                    "Run `trinity-local seed-from-taste-terminal` to retry."
                ),
                "added": state.get("added", 0),
            }
        return {
            "status": "complete",
            "message": (
                f"Trinity finished ingesting {state.get('added', 0)} prompts "
                f"from {', '.join(state.get('sources_detected', []))}. "
                f"Memories will warm up over the next few councils."
            ),
            "added": state.get("added", 0),
        }
    return None


def maybe_kick_cold_start() -> dict | None:
    """Idempotent entry point for the MCP server startup hook. Wraps
    ``kick_cold_start_scan`` so thread-spawn failures cannot crash the
    MCP server."""
    try:
        return kick_cold_start_scan()
    except Exception:
        return None
