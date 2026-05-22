"""Unit tests for the 3-stage lens-discovery pipeline.

Pipeline: basins.py + decisions.py + pair_mining.py + post-filter.
Tests cover the load-bearing pieces — k-means determinism with seed,
decision parser tolerance, and the basin post-filter that makes
topology evidence actually gate output (Option C, council_70eaf228d7753074).
"""

from __future__ import annotations




class TestBasins:
    def test_kmeans_pp_handles_all_zero_distances(self):
        """When all candidate points are duplicates of an existing centroid,
        the probability vector becomes all-zero and rng.choice would NaN.
        Fall back to uniform random."""
        import numpy as np
        from trinity_local.me.basins import _kmeans_pp_init

        # 10 identical rows — every candidate is at distance 0 from first centroid
        matrix = np.tile(np.array([[1.0, 0.0, 0.0]], dtype=np.float32), (10, 1))
        centroids = _kmeans_pp_init(matrix, k=3, seed=42)
        assert centroids.shape == (3, 3)
        # All centroids equal the duplicated row (no NaN, no crash)
        assert np.all(np.isfinite(centroids))

    def test_compute_basins_skips_nan_embeddings(self, monkeypatch, tmp_path):
        """A few NaN embeddings would otherwise poison every centroid via
        mean-update, collapsing all rows into one cluster."""
        import numpy as np
        from trinity_local.memory.schemas import PromptNode
        from trinity_local.me import basins as basins_mod

        # Build a synthetic corpus: 30 well-separated rows + 5 NaN.
        # Each node gets a unique transcript_id so thread-aware clustering
        # treats each turn as its own session and the test exercises the
        # NaN-skip path (not the thread-collapse path).
        def _node(node_id: str, text: str, embedding: list[float], tid: str) -> PromptNode:
            return PromptNode(
                id=node_id,
                transcript_id=tid,
                provider="test",
                source_path="/tmp/x",
                turn_index=0,
                text=text,
                embedding=embedding,
                created_at="2026-05-06T00:00:00",
            )

        good = [
            _node(
                f"p_{i:02d}",
                f"prompt {i}",
                np.eye(10)[i % 10].tolist() + [0.0] * 758,
                f"thread_{i:02d}",  # one thread per turn — exercise k-means
            )
            for i in range(30)
        ]
        bad = [_node(f"bad_{i}", f"poisoned {i}", [float("nan")] * 768, f"thread_bad_{i}") for i in range(5)]

        # Stage 1 basins reads `iter_prompt_nodes(limit=None)` — the
        # canonical uncapped walker (so populated installs aren't masked
        # by the 5000-node hot-path cap on the default call). Patch on
        # the basins module since the function is imported at the top.
        monkeypatch.setattr(basins_mod, "iter_prompt_nodes", lambda **kw: iter(good + bad))
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))

        result = basins_mod.compute_basins(k=5, seed=42)
        # NaN rows skipped, ≥2 healthy basins formed (would collapse to 1 if NaN
        # propagated through centroid means)
        assert len(result) >= 2, f"basins collapsed: {[(b.id, b.size) for b in result]}"
        total = sum(b.size for b in result)
        assert total == 30, "NaN rows should be skipped from clustering"

    def test_basin_for_prompt_lookup(self):
        from trinity_local.me.basins import Basin, basin_for_prompt
        b1 = Basin(id="b00", size=2, top_terms=[], centroid=[0.0], prompt_ids=["p1", "p2"])
        b2 = Basin(id="b01", size=1, top_terms=[], centroid=[1.0], prompt_ids=["p3"])
        assert basin_for_prompt([b1, b2], "p2") == "b00"
        assert basin_for_prompt([b1, b2], "p3") == "b01"
        assert basin_for_prompt([b1, b2], "missing") is None

    def test_basin_serialization_keeps_full_prompt_ids(self):
        """Regression: basins.py used to truncate prompt_ids to 50 entries
        in to_dict() "for readable JSON". After load_basins() round-trips
        through that JSON, basin_for_prompt() returned None for any prompt
        beyond the first 50 — silently breaking Stage 2/4 of the lens
        pipeline. Keep the full list so round-trips are lossless."""
        from trinity_local.me.basins import Basin
        ids = [f"p{i:04d}" for i in range(80)]  # > 50, the old cap
        basin = Basin(id="b00", size=80, top_terms=[], centroid=[0.0], prompt_ids=ids)
        payload = basin.to_dict()
        assert payload["prompt_ids"] == ids, (
            f"to_dict truncated prompt_ids ({len(payload['prompt_ids'])} of {len(ids)}); "
            "this breaks basin_for_prompt() lookup after load_basins() round-trip"
        )


class TestDecisionParser:
    def test_valence_enum_includes_correction_and_cost(self):
        # correction/cost are in the valence enum so real lenses don't
        # get rejected for lacking literal regret quotes. (The earlier
        # citation to a council ID that never landed was removed in
        # commit a6a8a11 — same phantom shape caught in claude.md.
        # The enum itself is load-bearing in me/decisions.py; that's
        # what this test pins.)
        from trinity_local.me.decisions import VALID_VALENCES
        assert "correction" in VALID_VALENCES
        assert "cost" in VALID_VALENCES
        assert "regret" in VALID_VALENCES

    def test_parse_decisions_tolerates_markdown_fences(self):
        from trinity_local.me.decisions import parse_decisions

        raw = """```json
{"id": "d_1", "privileged": "speed", "sacrificed": "quality", "valence": "regret", "basin": "b00", "verbatim": "shipped fast hated it", "prompt_id": "p1"}
{"id": "d_2", "privileged": "rigor", "sacrificed": "speed", "valence": "satisfaction", "basin": "b01", "verbatim": "took weeks worth it", "prompt_id": "p2"}
```"""
        decisions = parse_decisions(raw, basins=[])
        assert len(decisions) == 2
        assert decisions[0].privileged == "speed"
        assert decisions[1].valence == "satisfaction"

    def test_parse_decisions_skips_malformed_lines(self):
        from trinity_local.me.decisions import parse_decisions

        raw = '{"id":"d_1","privileged":"a","sacrificed":"b","valence":"regret","basin":"b00","verbatim":"x","prompt_id":"p1"}\n'
        raw += "this is not json\n"
        raw += '{"missing_required":"yes"}\n'
        raw += '{"id":"d_2","privileged":"c","sacrificed":"d","valence":"BOGUS","basin":"b00","verbatim":"y","prompt_id":"p1"}\n'
        raw += '{"id":"d_3","privileged":"e","sacrificed":"f","valence":"correction","basin":"b00","verbatim":"z","prompt_id":"p1"}\n'

        decisions = parse_decisions(raw, basins=[])
        # Only d_1 and d_3 should survive; d_2 has invalid valence, plus the noise lines
        assert {d.id for d in decisions} == {"d_1", "d_3"}

    def test_parse_decisions_re_tags_basin_from_prompt_id(self):
        # Chairman's `basin` field is NOT trusted — re-tag from
        # ground-truth basin lookup. This is what makes basin tags
        # load-bearing per council_70eaf228d7753074.
        from trinity_local.me.basins import Basin
        from trinity_local.me.decisions import parse_decisions

        basins = [
            Basin(id="b00", size=1, top_terms=[], centroid=[0.0], prompt_ids=["real_prompt_1"]),
            Basin(id="b01", size=1, top_terms=[], centroid=[1.0], prompt_ids=["real_prompt_2"]),
        ]
        # Chairman claims basin=b99 (made up) but prompt_id maps to b00
        raw = '{"id":"d_1","privileged":"a","sacrificed":"b","valence":"regret","basin":"b99","verbatim":"x","prompt_id":"real_prompt_1"}'
        decisions = parse_decisions(raw, basins)
        assert decisions[0].basin == "b00", "basin should be re-tagged from prompt_id, not chairman"


class TestPairMiningPostFilter:
    def _make_decisions(self):
        # Per spec ≥3 basins required for accepted lens. Build a corpus
        # where the topic-local pair sits in one basin and the structural
        # pair spans 3 distinct basins.
        from trinity_local.me.decisions import Decision
        return [
            # Topic-local tension: both directions in basin b00
            Decision(id="d1", privileged="speed", sacrificed="quality", valence="regret", basin="b00", verbatim="x"),
            Decision(id="d2", privileged="quality", sacrificed="speed", valence="regret", basin="b00", verbatim="y"),
            # Cross-basin tension: 3 distinct basins
            Decision(id="d3", privileged="long_view", sacrificed="last_day", valence="regret", basin="b00", verbatim="z"),
            Decision(id="d4", privileged="last_day", sacrificed="long_view", valence="regret", basin="b01", verbatim="w"),
            Decision(id="d5", privileged="long_view", sacrificed="last_day", valence="correction", basin="b02", verbatim="v"),
        ]

    def test_single_basin_pair_demoted_to_ordering(self):
        # All tension evidence in b00 → topic-local virtue, not real lens
        from trinity_local.me.pair_mining import LensPair, basin_post_filter
        decisions = self._make_decisions()
        pair = LensPair(
            pole_a="speed", pole_b="quality",
            failure_a="hack", failure_b="paralysis",
            tension_decisions=["d1", "d2"],
            verdict="accepted",
        )
        filtered = basin_post_filter([pair], decisions)
        assert filtered[0].verdict == "preserve_as_ordering"
        assert filtered[0].basins_spanned == ["b00"]

    def test_three_basin_pair_stays_accepted(self):
        # Per spec ≥3 basins required. Tension spans b00, b01, b02 → real lens.
        from trinity_local.me.pair_mining import LensPair, basin_post_filter
        decisions = self._make_decisions()
        pair = LensPair(
            pole_a="long_view", pole_b="last_day",
            failure_a="paralysis", failure_b="hedonism",
            tension_decisions=["d3", "d4", "d5"],
            verdict="accepted",
        )
        filtered = basin_post_filter([pair], decisions)
        assert filtered[0].verdict == "accepted"
        assert set(filtered[0].basins_spanned) == {"b00", "b01", "b02"}

    def test_two_basin_pair_demoted_to_ordering(self):
        # Two basins isn't enough — spec requires ≥3 domains. Demote.
        from trinity_local.me.pair_mining import LensPair, basin_post_filter
        decisions = self._make_decisions()
        pair = LensPair(
            pole_a="long_view", pole_b="last_day",
            failure_a="paralysis", failure_b="hedonism",
            tension_decisions=["d3", "d4"],
            verdict="accepted",
        )
        filtered = basin_post_filter([pair], decisions)
        assert filtered[0].verdict == "preserve_as_ordering"
        assert set(filtered[0].basins_spanned) == {"b00", "b01"}

    def test_sentinel_basin_ids_treated_as_missing(self):
        # Chairman sometimes emits "?" or "unknown" when uncertain. These
        # mustn't inflate basins_spanned past the spec threshold or every
        # ambiguous pair would falsely qualify as a real lens.
        from trinity_local.me.decisions import Decision
        from trinity_local.me.pair_mining import LensPair, basin_post_filter
        decisions = [
            Decision(id="d1", privileged="a", sacrificed="b", valence="regret", basin="?", verbatim="x"),
            Decision(id="d2", privileged="b", sacrificed="a", valence="regret", basin="unknown", verbatim="y"),
            Decision(id="d3", privileged="a", sacrificed="b", valence="regret", basin="b00", verbatim="z"),
        ]
        pair = LensPair(
            pole_a="a", pole_b="b", failure_a="x", failure_b="y",
            tension_decisions=["d1", "d2", "d3"],
            verdict="accepted",
        )
        filtered = basin_post_filter([pair], decisions)
        # Only b00 counts; sentinels stripped → 1 basin → demoted.
        assert filtered[0].basins_spanned == ["b00"]
        assert filtered[0].verdict == "preserve_as_ordering"

    def test_pair_with_no_basin_evidence_dropped(self):
        # Decisions referenced don't exist → no basin coverage
        from trinity_local.me.pair_mining import LensPair, basin_post_filter
        decisions = self._make_decisions()
        pair = LensPair(
            pole_a="x", pole_b="y",
            failure_a="a", failure_b="b",
            tension_decisions=["nonexistent_1", "nonexistent_2"],
            verdict="accepted",
        )
        filtered = basin_post_filter([pair], decisions)
        assert filtered[0].verdict == "dropped"

    def test_already_dropped_pair_passes_through(self):
        from trinity_local.me.pair_mining import LensPair, basin_post_filter
        pair = LensPair(
            pole_a="x", pole_b="y", failure_a="a", failure_b="b",
            verdict="dropped",
        )
        filtered = basin_post_filter([pair], [])
        assert filtered[0].verdict == "dropped"


class TestPairMiningParser:
    def test_parses_array_with_markdown_fences(self):
        from trinity_local.me.pair_mining import parse_pair_mining_output

        raw = """```json
[
  {"pole_a": "speed", "pole_b": "rigor", "failure_a": "hack", "failure_b": "paralysis", "tension_decisions": ["d1", "d2"], "dual_evidence": {"pole_a": ["d1"], "pole_b": ["d2"]}, "verdict": "accepted"},
  {"pole_a": "x", "pole_b": "y", "failure_a": "z", "failure_b": "w", "tension_decisions": ["d3"], "dual_evidence": {}, "verdict": "dropped"}
]
```"""
        pairs = parse_pair_mining_output(raw)
        assert len(pairs) == 2
        assert pairs[0].pole_a == "speed"
        assert pairs[1].verdict == "dropped"

    def test_skips_pairs_with_missing_poles(self):
        from trinity_local.me.pair_mining import parse_pair_mining_output

        raw = '[{"pole_a": "x", "pole_b": "x", "verdict": "accepted"}, {"pole_a": "a", "pole_b": "b", "verdict": "accepted"}]'
        pairs = parse_pair_mining_output(raw)
        # First skipped (poles equal), second kept
        assert len(pairs) == 1
        assert pairs[0].pole_a == "a"
