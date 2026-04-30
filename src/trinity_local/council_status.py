from __future__ import annotations

import json
from threading import Lock
from typing import Any

from .state_paths import council_status_dir, council_status_js_path, council_status_json_path
from .utils import now_iso


_STATUS_LOCK = Lock()


def _extract_reasoning_summary(text: str, max_length: int = 120) -> str:
    if not text:
        return ""
    text = text.strip()
    for delimiter in (".", "\n", "?"):
        idx = text.find(delimiter)
        if idx > 0:
            summary = text[:idx].strip()
            if summary:
                return summary[:max_length]
    return text[:max_length]


def load_council_status(status_token: str) -> dict[str, Any] | None:
    path = council_status_json_path(status_token)
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _write_status(status_token: str, payload: dict[str, Any]) -> dict[str, Any]:
    payload["status_token"] = status_token
    payload["updated_at"] = now_iso()
    council_status_json_path(status_token).write_text(
        json.dumps(payload, indent=2),
        encoding="utf-8",
    )
    js = (
        "window.__TRINITY_COUNCIL_STATUS__ = window.__TRINITY_COUNCIL_STATUS__ || {};\n"
        f"window.__TRINITY_COUNCIL_STATUS__[{json.dumps(status_token)}] = {json.dumps(payload, separators=(',', ':'), ensure_ascii=True)};\n"
    )
    council_status_js_path(status_token).write_text(js, encoding="utf-8")
    return payload


def write_council_status(
    status_token: str,
    *,
    status: str,
    task_text: str | None = None,
    bundle_id: str | None = None,
    council_id: str | None = None,
    review_path: str | None = None,
    error: str | None = None,
    metadata: dict[str, Any] | None = None,
    members: dict[str, dict[str, Any]] | None = None,
    synthesis: dict[str, Any] | None = None,
    active_provider: str | None = None,
    active_providers: list[str] | None = None,
) -> dict[str, Any]:
    with _STATUS_LOCK:
        payload = load_council_status(status_token) or {}
        payload["status"] = status
        if task_text is not None:
            payload["task_text"] = task_text
        if bundle_id is not None:
            payload["bundle_id"] = bundle_id
        if council_id is not None:
            payload["council_id"] = council_id
        if review_path is not None:
            payload["review_path"] = review_path
        if error is not None:
            payload["error"] = error
        elif "error" in payload and status in {"running", "completed"}:
            payload["error"] = None
        if metadata:
            existing = dict(payload.get("metadata") or {})
            existing.update(metadata)
            payload["metadata"] = existing
        if members is not None:
            payload["members"] = members
        if synthesis is not None:
            payload["synthesis"] = synthesis
        if active_provider is not None or "active_provider" in payload:
            payload["active_provider"] = active_provider
        if active_providers is not None:
            payload["active_providers"] = active_providers
        return _write_status(status_token, payload)


def init_council_run_state(
    status_token: str,
    *,
    task_text: str,
    bundle_id: str,
    members: list[str],
    metadata: dict[str, Any] | None = None,
    council_id: str | None = None,
    runner_pid: int | None = None,
    runner_pgid: int | None = None,
) -> dict[str, Any]:
    payload = {
        "status": "running",
        "task_text": task_text,
        "bundle_id": bundle_id,
        "council_id": council_id or bundle_id,
        "started_at": now_iso(),
        "members": {provider: {"status": "pending"} for provider in members},
        "active_provider": None,
        "active_providers": [],
        "synthesis": {"status": "pending"},
        "review_path": None,
        "error": None,
        "runner_pid": runner_pid,
        "runner_pgid": runner_pgid,
        "metadata": metadata or {},
    }
    with _STATUS_LOCK:
        return _write_status(status_token, payload)


def start_member_progress(status_token: str, provider: str) -> None:
    with _STATUS_LOCK:
        payload = load_council_status(status_token)
        if not payload:
            return
        members = dict(payload.get("members") or {})
        active = list(payload.get("active_providers") or [])
        if provider not in active:
            active.append(provider)
        members[provider] = {
            "status": "running",
            "started_at": now_iso(),
        }
        payload["members"] = members
        payload["active_provider"] = provider
        payload["active_providers"] = active
        _write_status(status_token, payload)


def update_member_progress(status_token: str, provider: str, response_text: str) -> None:
    with _STATUS_LOCK:
        payload = load_council_status(status_token)
        if not payload:
            return
        members = dict(payload.get("members") or {})
        members[provider] = {
            "status": "done",
            "completed_at": now_iso(),
            "reasoning_summary": _extract_reasoning_summary(response_text),
        }
        active = [item for item in (payload.get("active_providers") or []) if item != provider]
        payload["members"] = members
        payload["active_providers"] = active
        payload["active_provider"] = active[0] if active else None
        _write_status(status_token, payload)


def update_member_failure(status_token: str, provider: str, error_text: str) -> None:
    with _STATUS_LOCK:
        payload = load_council_status(status_token)
        if not payload:
            return
        members = dict(payload.get("members") or {})
        members[provider] = {
            "status": "failed",
            "completed_at": now_iso(),
            "reasoning_summary": _extract_reasoning_summary(error_text),
        }
        active = [item for item in (payload.get("active_providers") or []) if item != provider]
        payload["members"] = members
        payload["active_providers"] = active
        payload["active_provider"] = active[0] if active else None
        _write_status(status_token, payload)


def update_synthesis_progress(status_token: str, status: str) -> None:
    with _STATUS_LOCK:
        payload = load_council_status(status_token)
        if not payload:
            return
        payload["synthesis"] = {
            "status": status,
            "updated_at": now_iso(),
        }
        if status == "running":
            payload["active_provider"] = None
            payload["active_providers"] = []
        _write_status(status_token, payload)


def finalize_council_run_state(
    status_token: str,
    *,
    status: str,
    review_path: str | None = None,
    error: str | None = None,
    council_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    with _STATUS_LOCK:
        payload = load_council_status(status_token)
        if not payload:
            return None
        payload["status"] = status
        payload["completed_at"] = now_iso()
        if review_path is not None:
            payload["review_path"] = review_path
        if error is not None:
            payload["error"] = error
        if council_id is not None:
            payload["council_id"] = council_id
        if metadata:
            existing = dict(payload.get("metadata") or {})
            existing.update(metadata)
            payload["metadata"] = existing
        return _write_status(status_token, payload)

