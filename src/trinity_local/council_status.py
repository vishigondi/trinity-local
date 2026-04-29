from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .scoreboard import state_dir
from .utils import now_iso


def council_status_dir() -> Path:
    path = state_dir() / "portal_pages" / "status"
    path.mkdir(parents=True, exist_ok=True)
    return path


def council_status_json_path(status_token: str) -> Path:
    return council_status_dir() / f"council_status_{status_token}.json"


def council_status_js_path(status_token: str) -> Path:
    return council_status_dir() / f"council_status_{status_token}.js"


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
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status_token": status_token,
        "status": status,
        "updated_at": now_iso(),
    }
    if task_text:
        payload["task_text"] = task_text
    if bundle_id:
        payload["bundle_id"] = bundle_id
    if council_id:
        payload["council_id"] = council_id
    if review_path:
        payload["review_path"] = review_path
    if error:
        payload["error"] = error
    if metadata:
        payload["metadata"] = metadata

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
