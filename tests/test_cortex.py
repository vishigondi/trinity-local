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


def _has_semantic_embeddings() -> bool:
    """True when the MLX/nomic embedding backend successfully INITIALIZED
    (not just importable — runtime-ready). Falls back to False on CI
    where only `[test]` is installed (no sentence_transformers /
    torch). TF-IDF embeddings work for shape but not for semantic-
    similarity assertions, so semantic-similarity tests skip when only
    TF-IDF is available.

    First version of this helper just checked `import MlxEmbedder`,
    which succeeded even when sentence_transformers was missing
    (MlxEmbedder is just a class def; the lazy `__init__` is what
    needs sentence_transformers). On CI, that gave a false positive
    and the test still ran on TF-IDF, failing on the semantic-
    similarity assertion. Using the canonical
    `embeddings.is_available()` which only returns True when MLX
    successfully initialized at module-import time.
    """
    try:
        from trinity_local.embeddings import is_available
        return is_available()
    except Exception:
        return False


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
        # All 6 components present (n_episodes_norm, consistency_score,
        # recency_agreement, diversity, coherence_score, audit_score),
        # all named, all numeric.
        assert set(payload["components"].keys()) == {
            "n_episodes_norm", "consistency_score", "recency_agreement",
            "diversity", "coherence_score", "audit_score",
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
            task_types=["system_design"],
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
                task_types=[],
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
            task_types=[],
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
            task_types=["x"],
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
            task_types=["x"],
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
                "task_types": [],
                "winner_distribution": {"claude": 1.0},
                "routing_rule": {"primary": "claude", "challenger": None, "reason": "", "subroutes": []},
                "trust_score": {"value": 0.5, "components": {}, "computed_by": "system"},
            }}),
            encoding="utf-8",
        )
        loaded = load_routing_patterns()
        assert loaded["legacy"].basin_centroid == []

    @pytest.mark.skipif(
        not _has_semantic_embeddings(),
        reason="needs MLX/nomic embedding backend for semantic similarity. TF-IDF fallback (CI default) can't match 'similar query → basin' assertions because TF-IDF embeds word-overlap not meaning.",
    )
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
            task_types=["system_design"],
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
                "task_types": [],
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


class TestFlagshipExtractorProviderRouting:
    """make_flagship_extractor must dispatch to the provider the caller
    asked for. The old version hard-coded "claude" regardless of CLI
    choice — that's the bug this test pins."""

    def test_default_provider_is_claude(self):
        from trinity_local.cortex import make_flagship_extractor

        seen = []
        def fake_dispatch(provider, prompt):
            seen.append(provider)
            return '{"primary": "claude"}'
        ext = make_flagship_extractor(fake_dispatch, basin_id="b")
        ext([{"routing_label": {"winner": "claude"}}])
        assert seen == ["claude"]

    def test_custom_provider_threads_through(self):
        from trinity_local.cortex import make_flagship_extractor

        seen = []
        def fake_dispatch(provider, prompt):
            seen.append(provider)
            return '{"primary": "gemini"}'
        ext = make_flagship_extractor(fake_dispatch, basin_id="b", provider="gemini")
        ext([{"routing_label": {"winner": "gemini"}}])
        # Previously this would have been ["claude"] — bug fixed.
        assert seen == ["gemini"]


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


# ──────────────────────────────────────────────────────────────────────────────
# Basin geometry — geometric median, manifold dim, bimodality flag.
# ──────────────────────────────────────────────────────────────────────────────


class TestBasinGeometry:
    """Pure-numerical tests on _weiszfeld_median / _participation_ratio /
    _excess_kurtosis — no embeddings needed. These are the building blocks
    the structured geometric prior rides on.
    """

    def test_weiszfeld_median_matches_mean_for_symmetric_points(self):
        from trinity_local.cortex import _weiszfeld_median

        # Four points symmetric around (0, 0) → median should be near (0, 0).
        points = [[1.0, 0.0], [-1.0, 0.0], [0.0, 1.0], [0.0, -1.0]]
        median = _weiszfeld_median(points)
        assert abs(median[0]) < 0.05
        assert abs(median[1]) < 0.05

    def test_weiszfeld_robust_to_outlier(self):
        """The whole point: one extreme outlier should NOT drag the median
        the way it drags the arithmetic mean. The mean of these five points
        is dominated by the outlier; the median sits on the cluster.
        """
        from trinity_local.cortex import _weiszfeld_median

        points = [
            [0.0, 0.0], [0.1, 0.0], [-0.1, 0.0], [0.0, 0.1],
            [100.0, 100.0],  # one extreme outlier
        ]
        median = _weiszfeld_median(points)
        # Mean of these five points has each coord ≈ 20. Median should stay
        # near the cluster (within 10 of origin).
        assert abs(median[0]) < 10.0
        assert abs(median[1]) < 10.0

    def test_weiszfeld_handles_single_point(self):
        from trinity_local.cortex import _weiszfeld_median

        median = _weiszfeld_median([[3.0, 4.0, 5.0]])
        assert median == [3.0, 4.0, 5.0]

    def test_weiszfeld_handles_empty(self):
        from trinity_local.cortex import _weiszfeld_median

        assert _weiszfeld_median([]) == []

    def test_participation_ratio_low_for_collinear_points(self):
        """All points on a single line → 1 effective dim."""
        from trinity_local.cortex import _participation_ratio, _weiszfeld_median

        points = [[float(i), float(i * 2), float(i * 3)] for i in range(-3, 4)]
        center = _weiszfeld_median(points)
        pr = _participation_ratio(points, center)
        # On a perfect 1D line, PR ≈ 1.
        assert pr < 1.5

    def test_participation_ratio_higher_for_noise(self):
        """Spread points isotropically → PR climbs."""
        from trinity_local.cortex import _participation_ratio, _weiszfeld_median

        # Eight points roughly at corners of a 3D cube — covers all three axes.
        points = [
            [1.0, 1.0, 1.0], [-1.0, 1.0, 1.0], [1.0, -1.0, 1.0],
            [-1.0, -1.0, 1.0], [1.0, 1.0, -1.0], [-1.0, 1.0, -1.0],
            [1.0, -1.0, -1.0], [-1.0, -1.0, -1.0],
        ]
        center = _weiszfeld_median(points)
        pr = _participation_ratio(points, center)
        # Cube spans all three dimensions equally → PR ≈ 3.
        assert pr > 2.5

    def test_excess_kurtosis_bimodal_distribution(self):
        """Bimodal data has flat-topped or twin-peaked shape → kurtosis < 3
        (excess < 0)."""
        from trinity_local.cortex import _excess_kurtosis

        # Two clusters around -1 and +1, evenly populated.
        bimodal = [-1.0, -1.0, -1.0, -1.0, -1.0, 1.0, 1.0, 1.0, 1.0, 1.0]
        assert _excess_kurtosis(bimodal) < -0.5

    def test_excess_kurtosis_normal_like(self):
        from trinity_local.cortex import _excess_kurtosis

        # 30 samples roughly normal-shaped (concentrated around 0).
        vals = [0.0] * 20 + [-1.0] * 4 + [1.0] * 4 + [-2.0] * 1 + [2.0] * 1
        # Should be NOT bimodal (positive or near-zero excess kurtosis).
        assert _excess_kurtosis(vals) > -1.0


class TestComputeBasinGeometry:
    """End-to-end geometry computation on real (TF-IDF) embeddings —
    catches regressions in how the geometry dict gets assembled from raw
    outcomes."""

    def test_returns_empty_when_no_prompts(self, tmp_path, monkeypatch):
        from trinity_local.cortex import _compute_basin_geometry

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        # Outcomes with no synthesis_prompt and no routing_label.task_type
        outcomes = [{"council_run_id": "c1"}, {"council_run_id": "c2"}]
        geo = _compute_basin_geometry(outcomes)
        # Empty geometry shape — caller falls through.
        assert geo["centroid"] == []
        assert geo["coherence_score"] == 0.5  # neutral
        assert geo["bimodal_flag"] is False

    def test_coherent_basin_high_coherence_score(self, tmp_path, monkeypatch):
        """A basin where every outcome is about the same topic should
        produce a tight cluster → low manifold_dim → high coherence."""
        from trinity_local.cortex import _compute_basin_geometry

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        outcomes = []
        for i in range(8):
            outcomes.append({
                "council_run_id": f"c{i}",
                "synthesis_prompt": f"How do I configure pytest fixtures for case {i}? Need parametrize + tmp_path.\n\nMember responses follow:",
            })
        geo = _compute_basin_geometry(outcomes)
        assert geo["centroid"], "Should have real centroid for non-empty basin"
        # Coherent basin → coherence > 0.5 (neutral)
        assert geo["coherence_score"] > 0.4

    def test_geometry_orders_outcomes_by_distance_from_median(self, tmp_path, monkeypatch):
        """ordered_indices must put typical (close to median) outcomes first."""
        from trinity_local.cortex import _compute_basin_geometry

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        # Five similar prompts + one outlier — outlier should land last.
        outcomes = [
            {"council_run_id": "c0", "synthesis_prompt": "How do I configure pytest fixtures?"},
            {"council_run_id": "c1", "synthesis_prompt": "How do I configure pytest parametrize?"},
            {"council_run_id": "c2", "synthesis_prompt": "How do I configure pytest markers?"},
            {"council_run_id": "c3", "synthesis_prompt": "How do I configure pytest plugins?"},
            {"council_run_id": "c4", "synthesis_prompt": "How do I configure pytest hooks?"},
            {"council_run_id": "c5", "synthesis_prompt": "What's the best macaroni and cheese recipe with bechamel sauce?"},
        ]
        geo = _compute_basin_geometry(outcomes)
        assert geo["ordered_indices"], "Should return ordering"
        # The macaroni prompt should be at or near the end (index 5).
        assert geo["ordered_indices"][-1] == 5


class TestExtractionPromptIncludesGeometry:
    def test_geometry_block_only_when_provided(self):
        from trinity_local.cortex import build_extraction_prompt

        outcomes = [{
            "council_run_id": "c1",
            "routing_label": {"winner": "claude", "routing_lesson": "x"},
        }]

        without = build_extraction_prompt("system_design", outcomes, geometry=None)
        assert "BASIN GEOMETRY" not in without

        with_geo = build_extraction_prompt(
            "system_design",
            outcomes,
            geometry={
                "centroid": [0.1, 0.2, 0.3],
                "manifold_dim": 1.2,
                "coherence_score": 0.85,
                "bimodal_flag": False,
                "ordered_indices": [0],
            },
        )
        assert "BASIN GEOMETRY: COHERENT" in with_geo
        assert "manifold_dim=1.20" in with_geo

    def test_bimodal_shape_telegraphed(self):
        from trinity_local.cortex import build_extraction_prompt

        prompt = build_extraction_prompt(
            "system_design",
            [{"routing_label": {"winner": "claude"}}],
            geometry={
                "centroid": [0.1],
                "manifold_dim": 2.5,
                "coherence_score": 0.5,
                "bimodal_flag": True,
                "ordered_indices": [0],
            },
        )
        assert "BIMODAL" in prompt
        assert "TWO subroutes" in prompt

    def test_noisy_shape_encourages_no_rule(self):
        from trinity_local.cortex import build_extraction_prompt

        prompt = build_extraction_prompt(
            "system_design",
            [{"routing_label": {"winner": "claude"}}],
            geometry={
                "centroid": [0.1],
                "manifold_dim": 4.5,
                "coherence_score": 0.1,
                "bimodal_flag": False,
                "ordered_indices": [0],
            },
        )
        assert "NOISY" in prompt


# ──────────────────────────────────────────────────────────────────────────────
# Chairman-audit-mode (task #47).
# ──────────────────────────────────────────────────────────────────────────────


class TestAuditScoreMap:
    """The audit_score component derives from audit_status. Constants
    deliberately pin: unaudited contributes the geomean identity (1.0)
    so opt-in users aren't penalized, agreed and unaudited tie so the
    audit doesn't double-reward correct rules, disagreed drops trust
    by ~21% (one band lower), unclear is a small penalty."""

    def test_known_statuses(self):
        from trinity_local.cortex import AUDIT_SCORE_MAP, audit_score_for

        assert audit_score_for("unaudited") == 1.0
        assert audit_score_for("agreed") == 1.0
        assert audit_score_for("disagreed") == 0.1
        assert audit_score_for("unclear") == 0.5
        assert set(AUDIT_SCORE_MAP.keys()) == {"unaudited", "agreed", "disagreed", "unclear"}

    def test_unknown_status_treated_as_neutral(self):
        from trinity_local.cortex import audit_score_for

        # A foreign verdict (e.g., from a model that reinterpreted the prompt)
        # must not silently demote trust. Fall back to neutral 0.5.
        assert audit_score_for("inconclusive") == 0.5
        assert audit_score_for("") == 0.5


class TestParseAuditResponse:
    """The audit chairman is asked for a one-word reply. Tolerate whitespace,
    punctuation, markdown wrappers — but only accept the three canonical
    verdicts; everything else returns 'unclear' (safe default)."""

    def test_clean_one_word(self):
        from trinity_local.cortex import parse_audit_response

        assert parse_audit_response("agreed") == "agreed"
        assert parse_audit_response("disagreed") == "disagreed"
        assert parse_audit_response("unclear") == "unclear"

    def test_uppercase_normalized(self):
        from trinity_local.cortex import parse_audit_response

        assert parse_audit_response("AGREED") == "agreed"
        assert parse_audit_response("Disagreed.") == "disagreed"

    def test_surrounding_whitespace_and_punctuation(self):
        from trinity_local.cortex import parse_audit_response

        assert parse_audit_response("  agreed.\n") == "agreed"
        assert parse_audit_response("verdict: disagreed,") == "disagreed"

    def test_garbage_falls_back_to_unclear(self):
        from trinity_local.cortex import parse_audit_response

        # Model didn't comply with the one-word constraint — safest is to
        # treat as unclear (small trust penalty), not as a false "agreed".
        assert parse_audit_response("the rule looks fine to me") == "unclear"
        assert parse_audit_response("") == "unclear"
        assert parse_audit_response("{\"verdict\": \"agreed\"}") == "agreed"  # token salvaged


class TestConsolidateBasinWithAuditor:
    def _outcomes(self):
        return [
            {
                "council_run_id": f"c{i}",
                "winner_provider": "claude",
                "routing_label": {
                    "task_type": "system_design",
                    "winner": "claude",
                    "routing_lesson": "claude wins for architecture",
                    "agreed_claims": ["x"],
                    "disagreed_claims": [],
                },
            }
            for i in range(5)
        ]

    def test_disagreed_audit_demotes_trust(self, tmp_path, monkeypatch):
        """The point of the audit: when an independent chairman disagrees
        with the extracted rule, trust drops by ~21% so the rule stops
        driving routing on its own (the cortex hot-path gates on
        TRUST_KNN_FALLBACK)."""
        from trinity_local import cortex

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))

        def extractor(outs, geometry=None):
            return {"primary": "claude", "challenger": "codex", "reason": "x"}

        def audit_agreed(rule, outs):
            return "agreed"

        def audit_disagreed(rule, outs):
            return "disagreed"

        pattern_clean = cortex.consolidate_basin(
            basin_id="system_design",
            outcomes=self._outcomes(),
            task_types=["system_design"],
            diversity_metric=0.6,
            extractor=extractor,
            auditor=audit_agreed,
        )
        pattern_demoted = cortex.consolidate_basin(
            basin_id="system_design",
            outcomes=self._outcomes(),
            task_types=["system_design"],
            diversity_metric=0.6,
            extractor=extractor,
            auditor=audit_disagreed,
        )

        assert pattern_clean.audit_status == "agreed"
        assert pattern_demoted.audit_status == "disagreed"
        # Disagreed must drop trust below the cleared baseline.
        assert pattern_demoted.trust_score.value < pattern_clean.trust_score.value
        # Specifically, disagreed should land at least 15% below agreed —
        # that's the demotion the AUDIT_SCORE_MAP encodes.
        assert (
            pattern_demoted.trust_score.value
            < pattern_clean.trust_score.value * 0.85
        )

    def test_no_auditor_leaves_status_unaudited(self, tmp_path, monkeypatch):
        """Audit is opt-in; default consolidate must not pay the second
        flagship call."""
        from trinity_local import cortex

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))

        def extractor(outs, geometry=None):
            return {"primary": "claude", "reason": "x"}

        pattern = cortex.consolidate_basin(
            basin_id="system_design",
            outcomes=self._outcomes(),
            task_types=["system_design"],
            diversity_metric=0.6,
            extractor=extractor,
        )
        assert pattern.audit_status == "unaudited"

    def test_auditor_exception_falls_back_to_unaudited(self, tmp_path, monkeypatch, capsys):
        """A flaky auditor (e.g., the audit provider hit a rate limit) must
        not break consolidation. The pattern is still saved; its audit
        status stays neutral; AND the failure surfaces on stderr so the
        operator knows their audit provider is broken (the silent-failure
        mode this test pins)."""
        from trinity_local import cortex

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))

        def extractor(outs, geometry=None):
            return {"primary": "claude", "reason": "x"}

        def auditor(rule, outs):
            raise RuntimeError("audit provider hit rate limit")

        pattern = cortex.consolidate_basin(
            basin_id="system_design",
            outcomes=self._outcomes(),
            task_types=["system_design"],
            diversity_metric=0.6,
            extractor=extractor,
            auditor=auditor,
        )
        assert pattern.audit_status == "unaudited"
        # The error must show up on stderr — without this, an operator who
        # ran `--audit` against a broken provider would see every rule as
        # "unaudited" with zero clue why. Loud failure beats silent fallback.
        captured = capsys.readouterr()
        assert "audit failed" in captured.err
        assert "system_design" in captured.err
        assert "rate limit" in captured.err

    def test_audit_status_persists_round_trip(self, tmp_path, monkeypatch):
        """The audit verdict must survive save → load so a later --audit
        re-run can compare against the prior verdict without re-running
        extraction."""
        from trinity_local import cortex

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))

        def extractor(outs, geometry=None):
            return {"primary": "claude", "reason": "x"}

        def auditor(rule, outs):
            return "agreed"

        pattern = cortex.consolidate_basin(
            basin_id="system_design",
            outcomes=self._outcomes(),
            task_types=["system_design"],
            diversity_metric=0.6,
            extractor=extractor,
            auditor=auditor,
        )
        cortex.save_routing_patterns({"system_design": pattern})
        loaded = cortex.load_routing_patterns()
        assert loaded["system_design"].audit_status == "agreed"


# ──────────────────────────────────────────────────────────────────────────────
# Override mechanism — user veto (#) spec-v1.5 Week 5.
# ──────────────────────────────────────────────────────────────────────────────


class TestEffectiveTrust:
    """Override count multiplicatively demotes trust. 1 override halves it,
    2 quarters it, etc. The components (data-quality signals) stay clean —
    overrides are a hard user veto layered on top."""

    def _pattern(self, *, trust_value: float = 0.85, override_count: int = 0):
        from trinity_local.cortex import RoutingPattern, RoutingRule, TrustScore

        return RoutingPattern(
            basin_id="b",
            consolidated_at="2026-05-12T00:00:00Z",
            n_episodes=20,
            task_types=["b"],
            winner_distribution={"claude": 0.8},
            routing_rule=RoutingRule(primary="claude", challenger=None, reason="x", subroutes=[]),
            trust_score=TrustScore(
                value=trust_value,
                components={
                    "n_episodes_norm": 0.8, "consistency_score": 0.8,
                    "recency_agreement": 0.8, "diversity": 0.8,
                    "coherence_score": 0.85, "audit_score": 1.0,
                },
            ),
            override_count=override_count,
        )

    def test_no_override_returns_raw_trust(self):
        from trinity_local.cortex import effective_trust

        assert effective_trust(self._pattern(trust_value=0.85)) == 0.85

    def test_one_override_halves_trust(self):
        from trinity_local.cortex import effective_trust

        assert effective_trust(self._pattern(trust_value=0.85, override_count=1)) == 0.85 * 0.5

    def test_two_overrides_quarters_trust(self):
        from trinity_local.cortex import effective_trust

        result = effective_trust(self._pattern(trust_value=0.85, override_count=2))
        assert abs(result - 0.85 * 0.25) < 1e-9

    def test_override_persists_through_save_load(self, tmp_path, monkeypatch):
        from trinity_local import cortex

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        pattern = self._pattern(trust_value=0.7, override_count=2)
        cortex.save_routing_patterns({"b": pattern})
        loaded = cortex.load_routing_patterns()
        assert loaded["b"].override_count == 2
        assert abs(cortex.effective_trust(loaded["b"]) - 0.7 * 0.25) < 1e-9


class TestConsolidatePreservesOverrideCount:
    """The user marked a rule wrong; a later `consolidate` re-extracts the
    rule. The override_count MUST carry over — otherwise the user's veto
    is silently erased and the demoted rule comes back at full trust."""

    def test_prior_override_count_propagates(self, tmp_path, monkeypatch):
        from trinity_local import cortex

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))

        outcomes = [
            {
                "council_run_id": f"c{i}",
                "winner_provider": "claude",
                "routing_label": {"task_type": "b", "winner": "claude"},
            }
            for i in range(5)
        ]

        def extractor(outs, geometry=None):
            return {"primary": "claude", "reason": "x"}

        pattern = cortex.consolidate_basin(
            basin_id="b",
            outcomes=outcomes,
            task_types=["b"],
            diversity_metric=0.5,
            extractor=extractor,
            prior_override_count=2,
        )
        assert pattern.override_count == 2

    def test_default_prior_is_zero(self, tmp_path, monkeypatch):
        from trinity_local import cortex

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))

        outcomes = [
            {"council_run_id": "c1", "winner_provider": "claude",
             "routing_label": {"task_type": "b", "winner": "claude"}},
        ]

        def extractor(outs, geometry=None):
            return {"primary": "claude", "reason": "x"}

        pattern = cortex.consolidate_basin(
            basin_id="b",
            outcomes=outcomes,
            task_types=["b"],
            diversity_metric=0.5,
            extractor=extractor,
        )
        assert pattern.override_count == 0
