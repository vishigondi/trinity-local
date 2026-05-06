"""Tests for model drift detection."""
from __future__ import annotations

import json
from pathlib import Path

from trinity_local.drift import (
    DriftAlert,
    OutcomeRecord,
    _score_outcome,
    check_drift,
    _outcomes_path,
)


class TestScoreOutcome:
    def test_clean_completion(self):
        rec = OutcomeRecord("claude", "model-1", "coding", completed=True, error_count=0, session_seconds=60.0, timestamp="")
        assert _score_outcome(rec) == 1.0

    def test_completion_with_errors(self):
        rec = OutcomeRecord("claude", "model-1", "coding", completed=True, error_count=1, session_seconds=60.0, timestamp="")
        assert _score_outcome(rec) == 0.7

    def test_completion_with_many_errors(self):
        rec = OutcomeRecord("claude", "model-1", "coding", completed=True, error_count=5, session_seconds=60.0, timestamp="")
        assert _score_outcome(rec) == 0.3

    def test_not_completed(self):
        rec = OutcomeRecord("claude", "model-1", "coding", completed=False, error_count=0, session_seconds=60.0, timestamp="")
        assert _score_outcome(rec) == 0.0


class TestCheckDrift:
    def test_no_data_no_alerts(self, monkeypatch, tmp_path):
        """No outcomes → no drift alerts."""
        monkeypatch.setattr("trinity_local.state_paths.trinity_home", lambda: tmp_path)
        alerts = check_drift()
        assert alerts == []

    def test_drift_detected(self, monkeypatch, tmp_path):
        """When current quality drops below baseline, alert is emitted."""
        monkeypatch.setattr("trinity_local.state_paths.trinity_home", lambda: tmp_path)

        outcomes_path = tmp_path / "outcomes.jsonl"
        records: list[dict] = []

        # Baseline (8–14 days ago): all successful
        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)
        for i in range(6):
            ts = (now - timedelta(days=10) + timedelta(hours=i)).isoformat()
            records.append({
                "provider": "claude", "model_id": "claude-sonnet-4",
                "task_kind": "coding", "completed": True,
                "error_count": 0, "timestamp": ts,
            })

        # Current (last 7 days): all failing
        for i in range(4):
            ts = (now - timedelta(days=3) + timedelta(hours=i)).isoformat()
            records.append({
                "provider": "claude", "model_id": "claude-sonnet-4",
                "task_kind": "coding", "completed": False,
                "error_count": 0, "timestamp": ts,
            })

        with outcomes_path.open("w") as f:
            for rec in records:
                f.write(json.dumps(rec) + "\n")

        alerts = check_drift(min_current=3, min_baseline=5)
        assert len(alerts) == 1
        assert alerts[0].provider == "claude"
        assert alerts[0].delta_pct < -20

    def test_no_drift_when_stable(self, monkeypatch, tmp_path):
        """When quality is stable, no alerts."""
        monkeypatch.setattr("trinity_local.state_paths.trinity_home", lambda: tmp_path)

        outcomes_path = tmp_path / "outcomes.jsonl"
        records: list[dict] = []

        from datetime import datetime, timezone, timedelta
        now = datetime.now(timezone.utc)

        # Both windows: all successful
        for i in range(6):
            ts = (now - timedelta(days=10) + timedelta(hours=i)).isoformat()
            records.append({
                "provider": "gemini", "model_id": "gemini-2.5-pro",
                "task_kind": "research", "completed": True,
                "error_count": 0, "timestamp": ts,
            })
        for i in range(4):
            ts = (now - timedelta(days=3) + timedelta(hours=i)).isoformat()
            records.append({
                "provider": "gemini", "model_id": "gemini-2.5-pro",
                "task_kind": "research", "completed": True,
                "error_count": 0, "timestamp": ts,
            })

        with outcomes_path.open("w") as f:
            for rec in records:
                f.write(json.dumps(rec) + "\n")

        alerts = check_drift(min_current=3, min_baseline=5)
        assert alerts == []
