"""Track and persist council execution progress for live updates."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from threading import Lock

from .scoreboard import state_dir
from .utils import now_iso


_PROGRESS_LOCK = Lock()


def council_progress_dir() -> Path:
    """Directory for in-progress council files."""
    path = state_dir() / "council_progress"
    path.mkdir(parents=True, exist_ok=True)
    return path


def council_progress_json_path(council_id: str) -> Path:
    return council_progress_dir() / f"{council_id}.json"


def council_progress_js_path(council_id: str) -> Path:
    return council_progress_dir() / f"{council_id}.js"


def _extract_reasoning_summary(text: str, max_length: int = 120) -> str:
    """Extract first sentence or first max_length chars as reasoning summary."""
    if not text:
        return ""
    text = text.strip()
    # Try to find first sentence (period, newline, or question mark)
    for delimiter in (".", "\n", "?"):
        idx = text.find(delimiter)
        if idx > 0:
            summary = text[:idx].strip()
            if summary:
                return summary[:max_length]
    # Fallback: first max_length chars
    return text[:max_length]


def _write_progress(council_id: str, progress: dict) -> Path:
    progress_path = council_progress_json_path(council_id)
    progress_path.write_text(json.dumps(progress, indent=2), encoding="utf-8")
    js = (
        "window.__TRINITY_COUNCIL_PROGRESS__ = window.__TRINITY_COUNCIL_PROGRESS__ || {};\n"
        f"window.__TRINITY_COUNCIL_PROGRESS__[{json.dumps(council_id)}] = {json.dumps(progress, separators=(',', ':'), ensure_ascii=True)};\n"
    )
    council_progress_js_path(council_id).write_text(js, encoding="utf-8")
    return progress_path


def init_council_progress(
    council_id: str,
    member_providers: list[str],
) -> Path:
    """Initialize progress file with all members/reviewers in pending state."""
    with _PROGRESS_LOCK:
        progress = {
            "council_id": council_id,
            "started_at": now_iso(),
            "members": {
                provider: {"status": "pending"}
                for provider in member_providers
            },
            "active_provider": None,
            "active_providers": [],
            "peer_reviews": {},
            "synthesis": {"status": "pending"},
        }

        return _write_progress(council_id, progress)


def start_member_progress(council_id: str, provider: str) -> None:
    """Mark a member as currently running."""
    progress_path = council_progress_json_path(council_id)
    if not progress_path.exists():
        return

    with _PROGRESS_LOCK:
        try:
            progress = json.loads(progress_path.read_text(encoding="utf-8"))
            if "members" not in progress:
                progress["members"] = {}
            active = list(progress.get("active_providers") or [])
            if provider not in active:
                active.append(provider)
            progress["members"][provider] = {
                "status": "running",
                "started_at": now_iso(),
            }
            progress["active_provider"] = provider
            progress["active_providers"] = active
            _write_progress(council_id, progress)
        except (OSError, json.JSONDecodeError):
            pass


def update_member_progress(
    council_id: str,
    provider: str,
    response_text: str,
) -> None:
    """Mark a member as done and save their reasoning summary."""
    progress_path = council_progress_json_path(council_id)
    if not progress_path.exists():
        return

    with _PROGRESS_LOCK:
        try:
            progress = json.loads(progress_path.read_text(encoding="utf-8"))
            if "members" not in progress:
                progress["members"] = {}

            progress["members"][provider] = {
                "status": "done",
                "completed_at": now_iso(),
                "reasoning_summary": _extract_reasoning_summary(response_text),
            }
            active = [item for item in (progress.get("active_providers") or []) if item != provider]
            progress["active_providers"] = active
            progress["active_provider"] = active[0] if active else None
            _write_progress(council_id, progress)
        except (OSError, json.JSONDecodeError):
            pass


def update_member_failure(
    council_id: str,
    provider: str,
    error_text: str,
) -> None:
    """Mark a member as failed and save a compact failure summary."""
    progress_path = council_progress_json_path(council_id)
    if not progress_path.exists():
        return

    with _PROGRESS_LOCK:
        try:
            progress = json.loads(progress_path.read_text(encoding="utf-8"))
            if "members" not in progress:
                progress["members"] = {}

            progress["members"][provider] = {
                "status": "failed",
                "completed_at": now_iso(),
                "reasoning_summary": _extract_reasoning_summary(error_text),
            }
            active = [item for item in (progress.get("active_providers") or []) if item != provider]
            progress["active_providers"] = active
            progress["active_provider"] = active[0] if active else None
            _write_progress(council_id, progress)
        except (OSError, json.JSONDecodeError):
            pass


def update_synthesis_progress(council_id: str, status: str) -> None:
    """Update synthesis status (running or done)."""
    progress_path = council_progress_json_path(council_id)
    if not progress_path.exists():
        return

    with _PROGRESS_LOCK:
        try:
            progress = json.loads(progress_path.read_text(encoding="utf-8"))
            progress["synthesis"] = {
                "status": status,
                "updated_at": now_iso(),
            }
            if status == "running":
                progress["active_provider"] = None
                progress["active_providers"] = []
            _write_progress(council_id, progress)
        except (OSError, json.JSONDecodeError):
            pass


def finalize_council_progress(council_id: str) -> None:
    """Mark council as complete and ready for final review."""
    progress_path = council_progress_json_path(council_id)
    if not progress_path.exists():
        return

    with _PROGRESS_LOCK:
        try:
            progress = json.loads(progress_path.read_text(encoding="utf-8"))
            progress["completed_at"] = now_iso()
            progress["status"] = "complete"
            _write_progress(council_id, progress)
        except (OSError, json.JSONDecodeError):
            pass


def cleanup_progress(council_id: str) -> None:
    """Remove progress file once review page is ready."""
    for progress_path in (council_progress_json_path(council_id), council_progress_js_path(council_id)):
        if progress_path.exists():
            try:
                progress_path.unlink()
            except OSError:
                pass
