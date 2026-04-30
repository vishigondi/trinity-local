from __future__ import annotations

import json
from pathlib import Path

from .state_paths import council_feedback_path as _state_council_feedback_path
from .utils import now_iso


def council_feedback_path() -> Path:
    return _state_council_feedback_path()


def append_council_feedback(*, council_id: str, provider: str, answer_label: str | None = None) -> dict:
    record = {
        "council_id": council_id,
        "provider": provider,
        "answer_label": answer_label,
        "rated_at": now_iso(),
    }
    with council_feedback_path().open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
    return record


def latest_feedback_by_council() -> dict[str, dict]:
    path = council_feedback_path()
    if not path.exists():
        return {}
    latest: dict[str, dict] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        council_id = raw.get("council_id")
        if council_id:
            latest[council_id] = raw
    return latest
