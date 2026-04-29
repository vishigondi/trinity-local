"""Track and persist council execution progress for live updates."""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .scoreboard import state_dir
from .utils import now_iso


def council_progress_dir() -> Path:
    """Directory for in-progress council files."""
    path = state_dir() / "council_progress"
    path.mkdir(parents=True, exist_ok=True)
    return path


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


def init_council_progress(
    council_id: str,
    member_providers: list[str],
) -> Path:
    """Initialize progress file with all members/reviewers in pending state."""
    progress_path = council_progress_dir() / f"{council_id}.json"

    progress = {
        "council_id": council_id,
        "started_at": now_iso(),
        "members": {
            provider: {"status": "pending"}
            for provider in member_providers
        },
        "peer_reviews": {},
        "synthesis": {"status": "pending"},
    }

    progress_path.write_text(json.dumps(progress, indent=2), encoding="utf-8")
    return progress_path


def update_member_progress(
    council_id: str,
    provider: str,
    response_text: str,
) -> None:
    """Mark a member as done and save their reasoning summary."""
    progress_path = council_progress_dir() / f"{council_id}.json"
    if not progress_path.exists():
        return

    try:
        progress = json.loads(progress_path.read_text(encoding="utf-8"))
        if "members" not in progress:
            progress["members"] = {}

        progress["members"][provider] = {
            "status": "done",
            "completed_at": now_iso(),
            "reasoning_summary": _extract_reasoning_summary(response_text),
        }

        progress_path.write_text(json.dumps(progress, indent=2), encoding="utf-8")
    except (OSError, json.JSONDecodeError):
        pass


def update_synthesis_progress(council_id: str, status: str) -> None:
    """Update synthesis status (running or done)."""
    progress_path = council_progress_dir() / f"{council_id}.json"
    if not progress_path.exists():
        return

    try:
        progress = json.loads(progress_path.read_text(encoding="utf-8"))
        progress["synthesis"] = {
            "status": status,
            "updated_at": now_iso(),
        }
        progress_path.write_text(json.dumps(progress, indent=2), encoding="utf-8")
    except (OSError, json.JSONDecodeError):
        pass


def finalize_council_progress(council_id: str) -> None:
    """Mark council as complete and ready for final review."""
    progress_path = council_progress_dir() / f"{council_id}.json"
    if not progress_path.exists():
        return

    try:
        progress = json.loads(progress_path.read_text(encoding="utf-8"))
        progress["completed_at"] = now_iso()
        progress["status"] = "complete"
        progress_path.write_text(json.dumps(progress, indent=2), encoding="utf-8")
    except (OSError, json.JSONDecodeError):
        pass


def cleanup_progress(council_id: str) -> None:
    """Remove progress file once review page is ready."""
    progress_path = council_progress_dir() / f"{council_id}.json"
    if progress_path.exists():
        try:
            progress_path.unlink()
        except OSError:
            pass
