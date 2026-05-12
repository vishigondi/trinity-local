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


def _consolidate_args(**overrides) -> SimpleNamespace:
    """argparse Namespace with consolidate's argument defaults."""
    base = {
        "min_basin_size": 3,
        "dry_run": False,
        "basin": None,
        "provider": "claude",
        "audit": False,
        "audit_provider": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _plant_outcomes(home: Path, basin: str, n: int) -> None:
    """Write N council_outcome JSON files all classified to `basin`."""
    out_dir = home / "council_outcomes"
    out_dir.mkdir(parents=True, exist_ok=True)
    for i in range(n):
        (out_dir / f"council_{basin}_{i:04d}.json").write_text(
            json.dumps({
                "council_run_id": f"{basin}_c{i}",
                "bundle_id": f"{basin}_b{i}",
                "winner_provider": "claude",
                "routing_label": {
                    "task_type": basin,
                    "winner": "claude",
                    "routing_lesson": "claude wins",
                    "agreed_claims": ["x"],
                    "disagreed_claims": [],
                },
            }),
            encoding="utf-8",
        )


class TestConsolidateCLI:
    """Coverage for the branches of `handle_consolidate` that don't require
    a real flagship call. The full extraction path is exercised by
    test_cortex.TestConsolidateAll with a stub dispatch; these tests pin
    the CLI's *gating* logic (dry-run, --audit-provider conflict, etc.)
    that lives in the command module, not in cortex.py."""

    def test_no_outcomes_returns_zero_with_reason(self, tmp_path, monkeypatch, capsys):
        from trinity_local.commands.cortex import handle_consolidate

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        rc = handle_consolidate(_consolidate_args())
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        # Empty state is exit 0 (it's a valid no-op), not exit 1.
        assert rc == 0
        assert payload["ok"] is False
        assert "no council outcomes" in payload["reason"]

    def test_dry_run_lists_eligible_and_skipped_without_dispatching(self, tmp_path, monkeypatch, capsys):
        from trinity_local.commands.cortex import handle_consolidate

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        # One basin with 5 outcomes (eligible), one with 1 (below min=3)
        _plant_outcomes(tmp_path, "system_design", 5)
        _plant_outcomes(tmp_path, "tiny_basin", 1)

        rc = handle_consolidate(_consolidate_args(dry_run=True))
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert rc == 0
        assert payload["mode"] == "dry-run"
        assert payload["eligible_basins"] == {"system_design": 5}
        assert payload["skipped_below_min"] == {"tiny_basin": 1}
        # Dry-run must NOT have called any provider — no audit chatter
        # on stderr is the proxy.
        assert "Chairman-audit-mode" not in captured.err

    def test_audit_provider_conflict_returns_one(self, tmp_path, monkeypatch, capsys):
        """--audit-provider == --provider is invalid (an audit by the same
        model that wrote the rule is worse than no audit at all). Should
        exit 1 with a clear reason before any dispatch happens."""
        from trinity_local.commands.cortex import handle_consolidate

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        _plant_outcomes(tmp_path, "b", 5)

        rc = handle_consolidate(_consolidate_args(
            audit=True, audit_provider="claude", provider="claude"
        ))
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert rc == 1
        assert payload["ok"] is False
        assert "must differ" in payload["reason"]
        assert "claude" in payload["reason"]

    def test_min_basin_size_filter_excludes_small_basins(self, tmp_path, monkeypatch, capsys):
        from trinity_local.commands.cortex import handle_consolidate

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        _plant_outcomes(tmp_path, "small", 2)
        _plant_outcomes(tmp_path, "big", 5)

        rc = handle_consolidate(_consolidate_args(min_basin_size=4, dry_run=True))
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert rc == 0
        # min_basin_size=4 excludes both "small" (n=2) and would have
        # been excluding "big" if n<4. Only "big" should be eligible.
        assert payload["eligible_basins"] == {"big": 5}
        assert payload["skipped_below_min"] == {"small": 2}

    def test_basin_filter_narrows_to_named_basins(self, tmp_path, monkeypatch, capsys):
        from trinity_local.commands.cortex import handle_consolidate

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        _plant_outcomes(tmp_path, "a", 5)
        _plant_outcomes(tmp_path, "b", 5)
        _plant_outcomes(tmp_path, "c", 5)

        rc = handle_consolidate(_consolidate_args(basin=["a", "c"], dry_run=True))
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert rc == 0
        # --basin filters BEFORE min-size — only the named basins should
        # be present in the dry-run report.
        assert set(payload["eligible_basins"].keys()) == {"a", "c"}

    def test_no_eligible_basins_returns_one(self, tmp_path, monkeypatch, capsys):
        """When every basin is below min-size, exit 1 with a reason that
        lists the basins-below-min so the operator can lower --min-basin-size."""
        from trinity_local.commands.cortex import handle_consolidate

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        _plant_outcomes(tmp_path, "a", 2)
        _plant_outcomes(tmp_path, "b", 1)

        rc = handle_consolidate(_consolidate_args(min_basin_size=3))
        captured = capsys.readouterr()
        payload = json.loads(captured.out)
        assert rc == 1
        assert payload["ok"] is False
        assert "no basins" in payload["reason"]
        # The basins-below-min listing helps the operator decide whether
        # to wait for more councils or lower the threshold.
        assert payload["basins_below_min"] == {"a": 2, "b": 1}
