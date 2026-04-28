"""Shared helpers used by multiple command modules."""
from __future__ import annotations

import json
from pathlib import Path

from ..council_schema import CouncilMemberResult, CouncilPeerReview


def read_text_file(path: str | None) -> str:
    if not path:
        return ""
    return Path(path).expanduser().read_text(encoding="utf-8")


def load_member_results(path: str) -> list[CouncilMemberResult]:
    raw = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("member results file must be a JSON list")
    return [CouncilMemberResult(**item) for item in raw if isinstance(item, dict)]


def load_peer_reviews(path: str) -> list[CouncilPeerReview]:
    raw = json.loads(Path(path).expanduser().read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("peer reviews file must be a JSON list")
    return [CouncilPeerReview(**item) for item in raw if isinstance(item, dict)]
