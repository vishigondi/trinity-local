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

    def test_round_trip_preserves_basin_centroid(self, tmp_path, monkeypatch):
        """The v1.5 basin_centroid (mean embedding of evidence prompts)
        must survive save → load — it's what the ask centroid-match
        path reads at query time."""
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        pattern = RoutingPattern(
            basin_id="b_with_centroid",
            consolidated_at="2026-05-20T10:30:00Z",
            n_episodes=20,
            task_kinds=["x"],
            winner_distribution={"claude": 1.0},
            routing_rule=RoutingRule(primary="claude", challenger=None, reason="r", subroutes=[]),
            trust_score=TrustScore(value=0.6, components={}),
            basin_centroid=[0.1, 0.2, 0.3, 0.4, 0.5],
        )
        save_routing_patterns({"b_with_centroid": pattern})
        loaded = load_routing_patterns()
        assert loaded["b_with_centroid"].basin_centroid == [0.1, 0.2, 0.3, 0.4, 0.5]

    def test_legacy_pattern_without_centroid_loads_with_empty(self, tmp_path, monkeypatch):
        """Patterns saved before centroid storage shipped (basin_centroid
        missing from JSON) should load with basin_centroid=[]. Critical
        for the upgrade path — existing user data must keep working."""
        import json
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        from trinity_local.state_paths import cortex_routing_patterns_path

        # Legacy schema: no basin_centroid field.
        cortex_routing_patterns_path().write_text(
            json.dumps({"legacy": {
                "basin_id": "legacy",
                "consolidated_at": "2026-01-01T00:00:00Z",
                "n_episodes": 5,
                "task_kinds": [],
                "winner_distribution": {"claude": 1.0},
                "routing_rule": {"primary": "claude", "challenger": None, "reason": "", "subroutes": []},
                "trust_score": {"value": 0.5, "components": {}, "computed_by": "system"},
            }}),
            encoding="utf-8",
        )
        loaded = load_routing_patterns()
        assert loaded["legacy"].basin_centroid == []

    def test_end_to_end_centroid_chain_with_real_embeddings(self, tmp_path, monkeypatch):
        """Integration test: real (TF-IDF) embeddings drive the full chain.

        Stubs the FLAGSHIP extractor (too expensive to call in tests) but
        uses the actual embeddings backend. Validates the path from
        consolidation through query-time matching, end-to-end. This is
        what catches the kinds of regressions stub-only tests miss:
        wrong vector shape, empty centroid produced, embed() returning
        the wrong type, etc.
        """
        from trinity_local import cortex
        from trinity_local.ask import _best_centroid_match
        from trinity_local.embeddings.backend_tfidf import cosine_similarity

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))

        # Three realistic outcomes about system design. Their prompts cluster
        # together semantically — the centroid should be near them.
        outcomes = [
            {
                "council_run_id": "c1",
                "bundle_id": "b1",
                "winner": "codex",
                "winner_provider": "codex",
                "synthesis_prompt": "Should I design this schema with one wide table or three normalized tables? Need to balance write performance against query simplicity.\n\nMember responses follow:",
                "routing_label": {"task_type": "system_design", "winner": "codex", "routing_lesson": "codex wins for schema design"},
            },
            {
                "council_run_id": "c2",
                "bundle_id": "b2",
                "winner": "codex",
                "winner_provider": "codex",
                "synthesis_prompt": "I'm building a multi-tenant SaaS and need to decide between row-level isolation versus per-tenant database. What are the tradeoffs?\n\nMember responses follow:",
                "routing_label": {"task_type": "system_design", "winner": "codex"},
            },
            {
                "council_run_id": "c3",
                "bundle_id": "b3",
                "winner": "claude",
                "winner_provider": "claude",
                "synthesis_prompt": "Design an event-sourcing approach for an audit trail. Append-only or compacted state snapshots?\n\nMember responses follow:",
                "routing_label": {"task_type": "system_design", "winner": "claude"},
            },
        ]

        # Stub extractor returns a valid rule structure.
        def stub_extractor(outs):
            return {
                "primary": "codex",
                "challenger": "claude",
                "reason": "codex consistently produces concrete schemas",
                "failure_modes": {"claude": "over-philosophizes when a table will do"},
                "successful_prompts": {"codex": ["Should I design..."]},
            }

        pattern = cortex.consolidate_basin(
            basin_id="system_design",
            outcomes=outcomes,
            task_kinds=["system_design"],
            diversity_metric=0.5,
            extractor=stub_extractor,
        )

        # Centroid must be populated with a real vector. The TF-IDF backend
        # returns DEFAULT_DIM-length vectors.
        assert pattern.basin_centroid, "Centroid should be populated by real embeddings"
        assert len(pattern.basin_centroid) >= 256, "Centroid should match the embedding backend's dimension"
        # Centroid should not be all zeros — TF-IDF over varied text produces signal.
        assert any(abs(x) > 1e-6 for x in pattern.basin_centroid), "Centroid should have non-trivial values"

        # Now save the pattern + verify the query-time path works end-to-end.
        cortex.save_routing_patterns({"system_design": pattern})
        loaded = cortex.load_routing_patterns()
        assert loaded["system_design"].basin_centroid == pattern.basin_centroid

        # A similar query should match the basin via centroid cosine sim.
        # _best_centroid_match calls embed() on the query, then cosine
        # against the basin_centroid. Test that the full path returns a hit.
        match = _best_centroid_match(
            "design a database schema for X",
            loaded,
        )
        # Match should be non-None — the centroid was built from system-design
        # prompts and the query is also about schema design.
        assert match is not None, "Similar query should match system_design basin via centroid"
        matched_pattern, matched_basin, sim = match
        assert matched_basin == "system_design"
        assert sim > 0.0

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


# ──────────────────────────────────────────────────────────────────────────────
# Group outcomes by basin (Week 2: by task_type)
# ──────────────────────────────────────────────────────────────────────────────

class TestGroupOutcomesByBasin:
    def test_groups_by_routing_label_task_type(self):
        from trinity_local.cortex import group_outcomes_by_basin

        outcomes = [
            {"routing_label": {"task_type": "system_design"}, "winner_provider": "claude"},
            {"routing_label": {"task_type": "system_design"}, "winner_provider": "codex"},
            {"routing_label": {"task_type": "code_refactor"}, "winner_provider": "claude"},
        ]
        grouped = group_outcomes_by_basin(outcomes)
        assert set(grouped.keys()) == {"system_design", "code_refactor"}
        assert len(grouped["system_design"]) == 2

    def test_skips_outcomes_without_task_type(self):
        from trinity_local.cortex import group_outcomes_by_basin

        outcomes = [
            {"routing_label": {"task_type": ""}},
            {"routing_label": {}},
            {"routing_label": None},
            {"routing_label": {"task_type": "real"}, "winner_provider": "claude"},
        ]
        grouped = group_outcomes_by_basin(outcomes)
        assert grouped == {"real": [outcomes[3]]}


# ──────────────────────────────────────────────────────────────────────────────
# Flagship extractor — prompt building + response parsing.
# Pure functions; no LLM access needed.
# ──────────────────────────────────────────────────────────────────────────────

class TestBuildExtractionPrompt:
    def test_includes_basin_id_and_outcome_count(self):
        from trinity_local.cortex import build_extraction_prompt

        outcomes = [{"council_run_id": "c1", "routing_label": {"winner": "claude"}}]
        prompt = build_extraction_prompt("system_design", outcomes)
        assert "system_design" in prompt
        assert "1 council outcomes" in prompt

    def test_compresses_outcomes_to_load_bearing_fields_only(self):
        """The prompt should NOT include the full synthesis_output blob — token
        budget matters even for offline consolidation."""
        from trinity_local.cortex import build_extraction_prompt

        outcomes = [{
            "council_run_id": "c1",
            "routing_label": {"winner": "claude", "routing_lesson": "lesson"},
            "synthesis_output": "X" * 100000,  # huge blob
            "member_results": [{"output": "Y" * 50000}],
        }]
        prompt = build_extraction_prompt("b", outcomes)
        # Should not include the giant blobs.
        assert "X" * 100 not in prompt
        # Should include the routing_lesson.
        assert "lesson" in prompt

    def test_caps_outcomes_at_40_per_basin(self):
        from trinity_local.cortex import build_extraction_prompt

        outcomes = [
            {"council_run_id": f"c{i}", "routing_label": {"winner": "claude"}}
            for i in range(100)
        ]
        prompt = build_extraction_prompt("b", outcomes)
        # Outcomes 0..39 should be in the prompt, outcomes 40..99 shouldn't.
        assert '"council_id": "c0"' in prompt
        assert '"council_id": "c39"' in prompt
        assert '"council_id": "c40"' not in prompt


class TestParseExtractionResponse:
    def test_parses_bare_json(self):
        from trinity_local.cortex import parse_extraction_response

        text = '{"primary": "claude", "reason": "x"}'
        out = parse_extraction_response(text)
        assert out["primary"] == "claude"

    def test_strips_markdown_fence(self):
        from trinity_local.cortex import parse_extraction_response

        text = '```json\n{"primary": "codex"}\n```'
        out = parse_extraction_response(text)
        assert out["primary"] == "codex"

    def test_parses_json_with_surrounding_prose(self):
        from trinity_local.cortex import parse_extraction_response

        text = 'Sure! Here is the rule:\n{"primary": "gemini", "reason": "y"}\nLet me know if you need more.'
        out = parse_extraction_response(text)
        assert out["primary"] == "gemini"

    def test_raises_on_no_json(self):
        from trinity_local.cortex import parse_extraction_response

        with pytest.raises(ValueError):
            parse_extraction_response("just some prose, no braces here")


class TestConsolidateAll:
    """End-to-end consolidate_all with a stub dispatch_fn."""

    def test_end_to_end_with_stub_dispatch(self, tmp_path, monkeypatch):
        from trinity_local import cortex

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))

        # Plant two basins worth of outcomes.
        outcomes_dir = tmp_path / "council_outcomes"
        outcomes_dir.mkdir(parents=True)
        for i in range(4):
            (outcomes_dir / f"council_{i:04d}.json").write_text(
                json.dumps({
                    "council_run_id": f"c{i}",
                    "bundle_id": f"b{i}",
                    "winner_provider": "claude",
                    "routing_label": {
                        "task_type": "system_design",
                        "winner": "claude",
                        "routing_lesson": "claude wins for architecture",
                        "agreed_claims": ["x"],
                        "disagreed_claims": [],
                    },
                }),
                encoding="utf-8",
            )

        # Stub dispatch_fn returns a valid extraction JSON for any prompt.
        def stub_dispatch(provider, prompt):
            return json.dumps({
                "primary": "claude",
                "challenger": "codex",
                "reason": "claude surfaces structural failure modes",
                "subroutes": [],
                "failure_modes": {"claude": "over-engineers"},
                "successful_prompts": {"claude": ["What's the SINGLE..."]},
            })

        patterns = cortex.consolidate_all(dispatch_fn=stub_dispatch, min_basin_size=3)
        assert "system_design" in patterns
        assert patterns["system_design"].routing_rule.primary == "claude"
        assert patterns["system_design"].n_episodes == 4
        assert patterns["system_design"].trust_score.value > 0

    def test_skips_basins_below_min_size(self, tmp_path, monkeypatch):
        from trinity_local import cortex

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        outcomes_dir = tmp_path / "council_outcomes"
        outcomes_dir.mkdir(parents=True)
        # Only 2 outcomes in this basin.
        for i in range(2):
            (outcomes_dir / f"council_{i:04d}.json").write_text(
                json.dumps({
                    "council_run_id": f"c{i}",
                    "winner_provider": "claude",
                    "routing_label": {"task_type": "tiny_basin", "winner": "claude"},
                }),
                encoding="utf-8",
            )

        def stub_dispatch(provider, prompt):
            return '{"primary": "claude"}'

        patterns = cortex.consolidate_all(dispatch_fn=stub_dispatch, min_basin_size=3)
        # Should NOT consolidate a basin with only 2 outcomes.
        assert patterns == {}
