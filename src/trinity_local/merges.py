"""Append-only log of tacit-record acts.

Trinity already mines one merge corpus (council winner selection via
`council_feedback.jsonl` + `council_outcomes/*.json`). The strategic
direction is to grow that into a unified log of every "user expressed
a preference by acting" moment, then compute downstream views (lens,
picks, routing, direction-of-preference vectors) over the same flat
substrate. Same pattern as the existing `council_outcomes/` canonical
store + `compute_personal_routing_table` computed view.

This module is the writer side. Consumers (lens-build,
personal_routing, future v1.5 direction-of-preference vectors) read
the log later via `iter_merge_records()`.

Schema is open — each record carries `type` + arbitrary additional
fields. v1.0 ships with the council-winner row only; other merge
shapes (in-thread overwrite, override → re-consolidation delta,
agent-diff accept/reject) get added as the corresponding callers
are wired up.

Cold-install path: the directory + file are created lazily on first
write. Reading from a non-existent log returns an empty iterator.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Iterator

from .me.basins import me_dir
from .utils import now_iso


def merges_path() -> Path:
    """`~/.trinity/me/merges.jsonl` — append-only log of merge acts."""
    return me_dir() / "merges.jsonl"


def record_merge(record: dict) -> dict:
    """Append one merge record to the log. Returns the record with
    `ts` filled in if absent.

    Callers pass a partial dict; this helper stamps the timestamp
    via the same `now_iso()` the rest of the codebase uses, then
    JSON-appends one line. Open-append in text mode so multiple
    concurrent writers (e.g. parallel councils) interleave at line
    boundaries — no file lock needed for the v1.0 scale.
    """
    if "ts" not in record:
        record = {**record, "ts": now_iso()}
    path = merges_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
    return record


def iter_merge_records() -> Iterator[dict]:
    """Read the merge log line-by-line. Skip malformed rows silently
    so a single corrupt line can't break a downstream consumer."""
    path = merges_path()
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue
