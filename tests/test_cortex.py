"""Tests for the v1.5 cortex layer.

Pure-Python pieces only — trust-score computation, schema round-trips,
consolidate_basin with an injected flagship extractor. The actual
flagship-call (production) is wired via providers.make_provider and is not
exercised here.
"""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from trinity_local.cortex import (
    FailureModes,
    RoutingPattern,
    RoutingRule,
    TrustScore,
    TRUST_USE_RULE,
    TRUST_KNN_FALLBACK,
    compute_trust_score,
    consolidate_basin,
    load_routing_patterns,
    save_routing_patterns,
)


# ──────────────────────────────────────────────────────────────────────────────
# trust_score computation — system, not flagship.
# ──────────────────────────────────────────────────────────────────────────────

class TestComputeTrustScore:
    def test_strong_basin_lands_in_use_rule_band(self):
        # 40 episodes, claude wins 80%, recent winners agree, high diversity.
        trust = compute_trust_score(
            n_episodes=40,
            winner_distribution={"claude": 0.8, "codex": 0.15, "gemini": 0.05},
            rule_primary="claude",
            recent_winners=["claude"] * 8 + ["codex"] * 2,
            diversity_metric=0.85,
        )
        assert trust.value >= TRUST_USE_RULE
        assert trust.interpretation == "use rule alone"

    def test_weak_basin_falls_below_knn_fallback(self):
        # Only 3 episodes, split distribution, recency disagrees.
        trust = compute_trust_score(
            n_episodes=3,
            winner_distribution={"claude": 0.34, "codex": 0.33, "gemini": 0.33},
            rule_primary="claude",
            recent_winners=["codex", "codex", "gemini"],
            diversity_metric=0.4,
        )
        assert trust.value < TRUST_KNN_FALLBACK
        assert trust.interpretation == "ignore rule, fall back to kNN"

    def test_recency_disagreement_drags_trust_down(self):
        """Same basin, same distribution — but recency_agreement collapses
        when the last 10 outcomes all picked someone else. Geometric mean
        means one weak component drags everything."""
        strong = compute_trust_score(
            n_episodes=30,
            winner_distribution={"claude": 0.7, "codex": 0.3},
            rule_primary="claude",
            recent_winners=["claude"] * 10,
            diversity_metric=0.7,
        )
        recency_disagreed = compute_trust_score(
            n_episodes=30,
            winner_distribution={"claude": 0.7, "codex": 0.3},
            rule_primary="claude",
            recent_winners=["codex"] * 10,
            diversity_metric=0.7,
        )
        assert recency_disagreed.value < strong.value
        # And recency_disagreed should fall below TRUST_USE_RULE.
        assert recency_disagreed.value < TRUST_USE_RULE

    def test_components_are_transparent_and_serializable(self):
        trust = compute_trust_score(
            n_episodes=25,
            winner_distribution={"claude": 0.6, "codex": 0.4},
            rule_primary="claude",
            recent_winners=["claude"] * 6 + ["codex"] * 4,
            diversity_metric=0.7,
        )
        payload = trust.to_dict()
        # All 4 components present, all named, all numeric.
        assert set(payload["components"].keys()) == {
            "n_episodes_norm", "consistency_score", "recency_agreement", "diversity"
        }
        for v in payload["components"].values():
            assert 0.0 <= v <= 1.0
        # System-computed badge.
        assert payload["computed_by"] == "system"
        # Interpretation is the human-readable band.
        assert payload["interpretation"] in {
            "use rule alone", "use rule with kNN fallback", "ignore rule, fall back to kNN"
        }


# ──────────────────────────────────────────────────────────────────────────────
# consolidate_basin — uses injectable extractor so no flagship calls in tests.
# ──────────────────────────────────────────────────────────────────────────────

def _stub_extractor(canned: dict):
    def _fn(outcomes: list[dict]) -> dict:
        return canned
    return _fn


def _outcome(*, council_id: str, winner: str) -> dict:
    return {
        "council_id": council_id,
        "bundle_id": council_id,
        "winner": winner,
        "winner_provider": winner,
    }


class TestConsolidateBasin:
    def test_assembles_pattern_from_outcomes(self):
        outcomes = [
            _outcome(council_id="c1", winner="claude"),
            _outcome(council_id="c2", winner="claude"),
            _outcome(council_id="c3", winner="codex"),
        ]
        extracted = {
            "primary": "claude",
            "challenger": "codex",
            "reason": "claude surfaces second-order failure modes",
            "subroutes": [{"if_keywords": ["ship"], "prefer": "codex"}],
            "failure_modes": {"claude": "over-engineers", "codex": "misses edge cases"},
            "successful_prompts": {"claude": ["Audit this against..."]},
        }
        pattern = consolidate_basin(
            basin_id="concrete_vs_comprehensive",
            outcomes=outcomes,
            task_kinds=["system_design"],
            diversity_metric=0.7,
            extractor=_stub_extractor(extracted),
        )
        assert pattern.basin_id == "concrete_vs_comprehensive"
        assert pattern.n_episodes == 3
        assert pattern.routing_rule.primary == "claude"
        assert pattern.routing_rule.challenger == "codex"
        # Winner distribution computed by the system, not the flagship.
        assert pattern.winner_distribution["claude"] == round(2/3, 3)
        assert pattern.winner_distribution["codex"] == round(1/3, 3)
        # Evidence cites council IDs (verifiable against drift).
        assert "c1" in pattern.evidence
        assert pattern.failure_modes.claude == "over-engineers"

    def test_raises_on_empty_outcomes(self):
        with pytest.raises(ValueError):
            consolidate_basin(
                basin_id="empty",
                outcomes=[],
                task_kinds=[],
                diversity_metric=0.5,
                extractor=_stub_extractor({"primary": "claude"}),
            )

    def test_trust_score_is_system_computed_not_extractor_declared(self):
        # The extractor could try to claim trust=0.99; we ignore it. Only the
        # system-computed value lands in the pattern.
        outcomes = [_outcome(council_id=f"c{i}", winner="claude") for i in range(2)]
        extracted = {
            "primary": "claude",
            "trust_score": 0.99,  # the flagship tries to declare trust
        }
        pattern = consolidate_basin(
            basin_id="b",
            outcomes=outcomes,
            task_kinds=[],
            diversity_metric=0.5,
            extractor=_stub_extractor(extracted),
        )
        # System computed something based on n_episodes=2, which is below
        # N_EPISODES_FULL=25 — should be much lower than 0.99.
        assert pattern.trust_score.value < 0.9
        assert pattern.trust_score.computed_by == "system"


# ──────────────────────────────────────────────────────────────────────────────
# load/save round-trip — schema stability.
# ──────────────────────────────────────────────────────────────────────────────

class TestLoadSaveRoundtrip:
    def test_round_trip_preserves_pattern(self, tmp_path, monkeypatch):
        # Redirect cortex_dir to tmp.
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        # Have to reload modules that cache trinity_home at import.
        from trinity_local import state_paths

        # state_paths uses functions; safe to call after env change.
        pattern = RoutingPattern(
            basin_id="b1",
            consolidated_at="2026-05-20T10:30:00Z",
            n_episodes=20,
            task_kinds=["x"],
            winner_distribution={"claude": 0.7, "codex": 0.3},
            routing_rule=RoutingRule(
                primary="claude",
                challenger="codex",
                reason="r",
                subroutes=[{"k": "v"}],
            ),
            trust_score=TrustScore(
                value=0.65,
                components={"n_episodes_norm": 0.8, "consistency_score": 0.7, "recency_agreement": 0.6, "diversity": 0.5},
            ),
            failure_modes=FailureModes(claude="overengineers", codex="bare"),
            evidence=["c1", "c2"],
        )
        save_routing_patterns({"b1": pattern})
        loaded = load_routing_patterns()
        assert "b1" in loaded
        assert loaded["b1"].routing_rule.primary == "claude"
        assert loaded["b1"].trust_score.value == 0.65
        assert loaded["b1"].failure_modes.claude == "overengineers"

    def test_load_missing_file_returns_empty_dict(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        result = load_routing_patterns()
        assert result == {}

    def test_load_malformed_entries_skipped(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        from trinity_local.state_paths import cortex_routing_patterns_path

        cortex_routing_patterns_path().write_text(
            json.dumps({"good": {
                "basin_id": "good",
                "consolidated_at": "2026-01-01T00:00:00Z",
                "n_episodes": 5,
                "task_kinds": [],
                "winner_distribution": {"claude": 1.0},
                "routing_rule": {"primary": "claude", "challenger": None, "reason": "", "subroutes": []},
                "trust_score": {"value": 0.5, "components": {}, "computed_by": "system"},
            }, "bad": {"not_a_pattern": True}}),
            encoding="utf-8",
        )
        loaded = load_routing_patterns()
        # bad entry skipped, good entry kept.
        assert "good" in loaded
        assert "bad" not in loaded
