"""Model drift detection.

Tracks (provider, normalized_model_id, task_kind) → rolling outcome scores.
Compares current-week scores against a 2-week baseline and emits alerts when
a provider's quality drops significantly.

Only detects drift when there's enough data — at least 3 sessions in the
current window and 5 in the baseline.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional, Tuple

from .config import trinity_home


@dataclass
class DriftAlert:
    """A detected quality change for a provider/model/task combination."""
    provider: str
    model_id: str | None
    task_kind: str
    baseline_score: float
    current_score: float
    delta_pct: float
    baseline_sessions: int
    current_sessions: int
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class OutcomeRecord:
    """One session outcome for drift tracking."""
    provider: str
    model_id: str | None
    task_kind: str
    completed: bool
    error_count: int
    session_seconds: float | None
    timestamp: str

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


def _outcomes_path() -> Path:
    path = trinity_home() / "outcomes.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def append_outcome(record: OutcomeRecord) -> None:
    """Append an outcome record to the drift tracking log."""
    with _outcomes_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(record.to_dict()) + "\n")


def _load_outcomes() -> list[OutcomeRecord]:
    """Load all outcome records."""
    path = _outcomes_path()
    if not path.exists():
        return []
    records: list[OutcomeRecord] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        records.append(OutcomeRecord(
            provider=raw.get("provider", ""),
            model_id=raw.get("model_id"),
            task_kind=raw.get("task_kind", "general"),
            completed=raw.get("completed", False),
            error_count=raw.get("error_count", 0),
            session_seconds=raw.get("session_seconds"),
            timestamp=raw.get("timestamp", ""),
        ))
    return records


def _score_outcome(record: OutcomeRecord) -> float:
    """Score a single outcome: 1.0 for clean completion, 0.0 for failure."""
    if not record.completed:
        return 0.0
    if record.error_count > 2:
        return 0.3
    if record.error_count > 0:
        return 0.7
    return 1.0


def _parse_ts(ts: str) -> float:
    """Parse an ISO timestamp to Unix epoch seconds."""
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
    except (ValueError, AttributeError):
        return 0.0


def check_drift(
    *,
    current_window_days: int = 7,
    baseline_window_days: int = 14,
    min_current: int = 3,
    min_baseline: int = 5,
    threshold_pct: float = 20.0,
) -> list[DriftAlert]:
    """Check for model drift by comparing recent outcomes to baseline.

    Returns a list of DriftAlert for any (provider, model, task_kind) combo
    where current-window quality has dropped by more than threshold_pct.
    """
    now = datetime.now(timezone.utc).timestamp()
    current_cutoff = now - (current_window_days * 86400)
    baseline_cutoff = now - (baseline_window_days * 86400)

    outcomes = _load_outcomes()

    # Group by (provider, model_id, task_kind).
    # Keep this as a plain type alias assignment so it works at runtime on 3.10+.
    Key = Tuple[str, Optional[str], str]
    current_scores: dict[Key, list[float]] = {}
    baseline_scores: dict[Key, list[float]] = {}

    for record in outcomes:
        ts = _parse_ts(record.timestamp)
        if ts <= 0:
            continue
        key: Key = (record.provider, record.model_id, record.task_kind)
        score = _score_outcome(record)

        if ts >= current_cutoff:
            current_scores.setdefault(key, []).append(score)
        elif ts >= baseline_cutoff:
            baseline_scores.setdefault(key, []).append(score)

    alerts: list[DriftAlert] = []
    for key, current in current_scores.items():
        baseline = baseline_scores.get(key, [])
        if len(current) < min_current or len(baseline) < min_baseline:
            continue

        current_avg = sum(current) / len(current)
        baseline_avg = sum(baseline) / len(baseline)

        if baseline_avg <= 0:
            continue

        delta_pct = ((current_avg - baseline_avg) / baseline_avg) * 100

        if delta_pct < -threshold_pct:
            provider, model_id, task_kind = key
            alerts.append(DriftAlert(
                provider=provider,
                model_id=model_id,
                task_kind=task_kind,
                baseline_score=round(baseline_avg, 3),
                current_score=round(current_avg, 3),
                delta_pct=round(delta_pct, 1),
                baseline_sessions=len(baseline),
                current_sessions=len(current),
                message=(
                    f"{provider}'s {task_kind} quality dropped {abs(delta_pct):.0f}% "
                    f"this week vs prior 2 weeks "
                    f"(model: {model_id or 'unknown'}, "
                    f"{len(current)} recent sessions vs {len(baseline)} baseline)"
                ),
            ))

    return alerts
