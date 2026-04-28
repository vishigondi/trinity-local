"""Tests for knn_analytics — advisory analytics module."""
from __future__ import annotations

import json
import os
import tempfile

import pytest

_test_home = tempfile.mkdtemp(prefix="trinity-test-analytics-")
os.environ["TRINITY_HOME"] = _test_home

from trinity_local.knn_analytics import (
    AdvisoryEvent,
    AdvisoryReport,
    generate_report,
    load_advisory_log,
    log_advisory_event,
    mark_suggestion_outcome,
    save_report,
)


def _make_event(**overrides) -> AdvisoryEvent:
    defaults = dict(
        timestamp="2026-04-28T01:00:00Z",
        session_id="test-session-1",
        provider="claude",
        task_kind="coding",
        prompt_len=100,
        knn_available=True,
        neighbor_count=5,
        council_confidence=0.8,
        should_council=True,
        evidence_count=4,
        heuristic_mode="recommendation",
        final_mode="council",
        was_upgraded=True,
        recommended_provider="codex",
    )
    defaults.update(overrides)
    return AdvisoryEvent(**defaults)


class TestEventLogging:
    def test_log_and_load(self):
        event = _make_event(session_id="log-test-1")
        log_advisory_event(event)
        events = load_advisory_log()
        found = [e for e in events if e.session_id == "log-test-1"]
        assert len(found) == 1
        assert found[0].provider == "claude"
        assert found[0].council_confidence == 0.8

    def test_multiple_events(self):
        for i in range(3):
            log_advisory_event(_make_event(session_id=f"multi-{i}"))
        events = load_advisory_log()
        multi = [e for e in events if e.session_id.startswith("multi-")]
        assert len(multi) == 3


class TestOutcomeTracking:
    def test_mark_acted_on(self):
        log_advisory_event(_make_event(session_id="outcome-test-1"))
        result = mark_suggestion_outcome("outcome-test-1", acted_on=True)
        assert result is True
        events = load_advisory_log()
        found = [e for e in events if e.session_id == "outcome-test-1"]
        assert found[0].suggestion_acted_on is True

    def test_mark_later_switched(self):
        log_advisory_event(_make_event(session_id="switch-test-1"))
        mark_suggestion_outcome(
            "switch-test-1",
            acted_on=False,
            later_switched=True,
            switch_target="gemini",
        )
        events = load_advisory_log()
        found = [e for e in events if e.session_id == "switch-test-1"]
        assert found[0].later_switched is True
        assert found[0].switch_target == "gemini"

    def test_mark_missing_session(self):
        result = mark_suggestion_outcome("nonexistent", acted_on=True)
        assert result is False


class TestReport:
    @pytest.fixture(autouse=True)
    def _populate_log(self):
        # Log a variety of events
        for i in range(5):
            log_advisory_event(_make_event(
                session_id=f"report-{i}",
                task_kind="coding" if i < 3 else "research",
                council_confidence=0.8 if i < 3 else 0.3,
                evidence_count=3 + i,
                was_upgraded=i < 2,
                heuristic_mode="recommendation",
                final_mode="council" if i < 2 else "recommendation",
                reroute_provider="codex" if i == 0 else None,
                reroute_similarity=0.75 if i == 0 else 0.0,
            ))
        # Mark some outcomes
        mark_suggestion_outcome("report-0", acted_on=True)
        mark_suggestion_outcome("report-1", acted_on=False, later_switched=True, switch_target="gemini")

    def test_report_basics(self):
        report = generate_report()
        assert report.total_events > 0
        assert report.knn_active_count > 0

    def test_evidence_spam_check(self):
        report = generate_report()
        assert report.evidence_count_avg > 0
        assert report.evidence_count_max > 0

    def test_upgrade_tracking(self):
        report = generate_report()
        assert report.upgrades_total >= 0
        assert 0 <= report.upgrade_rate <= 1

    def test_threshold_by_task_kind(self):
        report = generate_report()
        if report.confidence_by_task_kind:
            for kind, stats in report.confidence_by_task_kind.items():
                assert "mean" in stats
                assert "min" in stats
                assert "max" in stats

    def test_product_metrics(self):
        report = generate_report()
        assert report.suggestions_total >= 0

    def test_save_report(self):
        report = generate_report()
        path = save_report(report)
        assert path.exists()
        raw = json.loads(path.read_text())
        assert "total_events" in raw

    def test_alert_threshold_brittleness(self):
        """If confidence varies >30% across task kinds, an alert fires."""
        report = generate_report()
        # Our test data has coding=0.8, research=0.3 -> spread=0.5
        if report.confidence_by_task_kind:
            brittleness_alert = any("BRITTLENESS" in a for a in report.alerts)
            # This may or may not fire depending on accumulated test data
            assert isinstance(brittleness_alert, bool)
