"""Tests for the cortex CLI handlers in commands/cortex.py.

The `consolidate` handler is exercised only via end-to-end tests in
test_cortex.TestConsolidateAll. This module covers the smaller, oft-
overlooked piece: `cortex-override`, which has real branching logic
(no-patterns / missing-basin / increment / reset) that was previously
only smoke-tested by hand.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


def _plant_pattern(basin: str, *, override: int = 0) -> None:
    """Write a single-basin routing_patterns.json. Replaces whatever's there."""
    from trinity_local import cortex
    pattern = cortex.RoutingPattern(
        basin_id=basin,
        consolidated_at="2026-05-12T07:00:00Z",
        n_episodes=20,
        task_kinds=[basin],
        winner_distribution={"claude": 0.8},
        routing_rule=cortex.RoutingRule(
            primary="claude", challenger=None, reason="x", subroutes=[]
        ),
        trust_score=cortex.TrustScore(
            value=0.8,
            components={
                "n_episodes_norm": 0.8, "consistency_score": 0.8,
                "recency_agreement": 0.8, "diversity": 0.7,
                "coherence_score": 0.8, "audit_score": 1.0,
            },
        ),
        override_count=override,
    )
    existing = cortex.load_routing_patterns()
    existing[basin] = pattern
    cortex.save_routing_patterns(existing)


def _run(args: SimpleNamespace, capsys) -> tuple[int, dict]:
    """Invoke handle_cortex_override and parse the JSON output it prints."""
    from trinity_local.commands.cortex import handle_cortex_override
    rc = handle_cortex_override(args)
    captured = capsys.readouterr()
    return rc, json.loads(captured.out)


class TestCortexOverrideCLI:
    def test_no_consolidation_yet_reports_clearly(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        rc, payload = _run(
            SimpleNamespace(basin="system_design", reason=None, reset=False),
            capsys,
        )
        assert rc == 1
        assert payload["ok"] is False
        assert "consolidat" in payload["reason"]

    def test_missing_basin_lists_known_basins(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        _plant_pattern("writing")
        _plant_pattern("system_design")

        rc, payload = _run(
            SimpleNamespace(basin="not_a_real_basin", reason=None, reset=False),
            capsys,
        )
        assert rc == 1
        assert payload["ok"] is False
        # The operator MUST see the known basins so they can correct the typo
        # without having to grep the json by hand.
        assert "not_a_real_basin" in payload["reason"]
        assert "system_design" in payload["reason"]
        assert "writing" in payload["reason"]

    def test_increment_returns_zero_and_persists(self, tmp_path, monkeypatch, capsys):
        from trinity_local import cortex

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        _plant_pattern("system_design", override=0)

        rc, payload = _run(
            SimpleNamespace(basin="system_design", reason="wrong primary", reset=False),
            capsys,
        )
        assert rc == 0
        assert payload["ok"] is True
        assert payload["action"] == "incremented"
        assert payload["override_count"] == 1
        # Effective trust ≈ raw * 0.5 = 0.4
        assert abs(payload["effective_trust"] - 0.4) < 0.01
        assert payload["raw_trust"] == 0.8
        assert payload["reason"] == "wrong primary"

        # Persisted — load again, count should still be 1.
        loaded = cortex.load_routing_patterns()
        assert loaded["system_design"].override_count == 1

    def test_repeated_increments_compound(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        _plant_pattern("b", override=0)

        _run(SimpleNamespace(basin="b", reason=None, reset=False), capsys)
        rc, payload = _run(
            SimpleNamespace(basin="b", reason=None, reset=False), capsys
        )
        assert rc == 0
        assert payload["override_count"] == 2
        # Effective trust = 0.8 * 0.25 = 0.2
        assert abs(payload["effective_trust"] - 0.2) < 0.01

    def test_reset_returns_count_to_zero(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        _plant_pattern("b", override=3)

        rc, payload = _run(
            SimpleNamespace(basin="b", reason=None, reset=True), capsys
        )
        assert rc == 0
        assert payload["action"] == "reset"
        assert payload["override_count"] == 0
        # Back to raw trust
        assert abs(payload["effective_trust"] - 0.8) < 0.01

    def test_reason_carried_through_to_output(self, tmp_path, monkeypatch, capsys):
        """The CLI doesn't persist the reason (yet) but it MUST echo it back
        in the JSON output so the calling agent (or shell pipeline) can log
        it. Without this the user has no programmatic confirmation that the
        reason landed."""
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        _plant_pattern("b")

        _, payload = _run(
            SimpleNamespace(basin="b", reason="claude over-engineers in this basin", reset=False),
            capsys,
        )
        assert payload["reason"] == "claude over-engineers in this basin"
