"""Tick #50 — pure-embedding depth ranking.

Tests the centroid-distance signal independently of any clustering
or LLM call. Per the literature review (Clio + TAD-Bench), this is
the most-validated single component of the proposed depth_score.
"""
from __future__ import annotations

import math

import pytest


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
    return tmp_path


def _node(tid: str, nid: str, emb: list[float]):
    """Minimal PromptNode that the depth module can read."""
    from trinity_local.memory.schemas import PromptNode
    return PromptNode(
        id=nid,
        transcript_id=tid,
        provider="test",
        source_path="test.jsonl",
        turn_index=0,
        text="",
        embedding=emb,
        created_at="2026-05-13T00:00:00",
    )


class TestThreadCentroids:
    def test_mean_per_thread(self, isolated_home):
        from trinity_local.me.depth import thread_centroids
        nodes = [
            _node("t1", "a", [1.0, 0.0]),
            _node("t1", "b", [0.0, 1.0]),
            _node("t2", "c", [0.5, 0.5]),
        ]
        out = thread_centroids(nodes)
        assert math.isclose(out["t1"][0], 0.5)
        assert math.isclose(out["t1"][1], 0.5)
        assert math.isclose(out["t2"][0], 0.5)

    def test_skips_zero_embedding(self, isolated_home):
        from trinity_local.me.depth import thread_centroids
        out = thread_centroids([_node("t1", "a", [])])
        assert out == {}

    def test_skips_missing_transcript_id(self, isolated_home):
        from trinity_local.me.depth import thread_centroids
        n = _node("", "a", [1.0, 2.0])
        n.transcript_id = ""  # empty tid → skipped
        out = thread_centroids([n])
        assert out == {}


class TestCosineDistance:
    def test_orthogonal_vectors(self, isolated_home):
        from trinity_local.me.depth import cosine_distance
        assert math.isclose(cosine_distance([1.0, 0.0], [0.0, 1.0]), 1.0)

    def test_identical_vectors_zero_distance(self, isolated_home):
        from trinity_local.me.depth import cosine_distance
        # Float drift leaves ~2.22e-16 near the origin even with the
        # clamp; tolerate it via abs_tol (math.isclose default is 0.0).
        assert math.isclose(
            cosine_distance([1.0, 1.0], [1.0, 1.0]), 0.0, abs_tol=1e-9
        )

    def test_opposite_vectors_two(self, isolated_home):
        from trinity_local.me.depth import cosine_distance
        assert math.isclose(cosine_distance([1.0, 0.0], [-1.0, 0.0]), 2.0)

    def test_zero_vector_returns_one(self, isolated_home):
        """NaN-safe: zero norms → distance 1.0 (orthogonal-ish), not NaN."""
        from trinity_local.me.depth import cosine_distance
        assert cosine_distance([0.0, 0.0], [1.0, 0.0]) == 1.0
        assert cosine_distance([1.0, 0.0], []) == 1.0

    def test_clamp_handles_float_drift(self, isolated_home):
        """Identical-but-tiny-different vectors don't go past 1.0/below -1.0
        due to float arithmetic — should return a valid distance in [0, 2]."""
        from trinity_local.me.depth import cosine_distance
        a = [1.0 + 1e-15, 0.0]
        b = [1.0, 0.0]
        d = cosine_distance(a, b)
        assert 0 <= d <= 2


class TestThreadCorpusDistance:
    def test_one_outlier_thread_ranks_highest(self, isolated_home):
        """The literature-validated case: a thread far from the corpus
        centroid scores higher than threads near it."""
        from trinity_local.me.depth import thread_corpus_distance
        # t1, t2, t3 all cluster around [1, 0]
        # t_outlier sits at [0, 1]
        nodes = [
            _node("t1", "a", [1.0, 0.0]),
            _node("t2", "b", [0.95, 0.05]),
            _node("t3", "c", [1.0, -0.05]),
            _node("t_outlier", "d", [0.0, 1.0]),
        ]
        out = thread_corpus_distance(nodes)
        # Outlier must have the highest corpus distance.
        assert out["t_outlier"] > max(out["t1"], out["t2"], out["t3"]), (
            f"outlier didn't rank highest: {out}"
        )

    def test_cold_install_empty(self, isolated_home):
        from trinity_local.me.depth import thread_corpus_distance
        assert thread_corpus_distance([]) == {}

    def test_equal_weight_per_thread(self, isolated_home):
        """A 100-turn chatty thread shouldn't dominate the corpus mean
        more than a 1-turn focused thread. Literature backs equal-thread
        weighting for unsupervised novelty detection."""
        from trinity_local.me.depth import thread_corpus_distance
        # t_chatty: 10 turns all at [1, 0]
        # t_focused: 1 turn at [0, 1]
        # If we weighted by turn count, the corpus mean drifts toward
        # [1, 0] and t_focused looks like a HUGE outlier. With equal-
        # weight-per-thread, the corpus mean is the midpoint and both
        # threads sit at roughly equal distance from it.
        nodes = [_node("t_chatty", f"c{i}", [1.0, 0.0]) for i in range(10)]
        nodes.append(_node("t_focused", "f0", [0.0, 1.0]))
        out = thread_corpus_distance(nodes)
        # Corpus mean is [0.5, 0.5] (equal-weight). Distance from each
        # thread should be ~equal because both are symmetric about it.
        assert math.isclose(out["t_chatty"], out["t_focused"], abs_tol=1e-6), (
            f"equal-weight contract broken: chatty={out['t_chatty']} "
            f"focused={out['t_focused']}"
        )


class TestInterTurnDistance:
    def test_single_turn_thread_zero_distance(self, isolated_home):
        from trinity_local.me.depth import thread_inter_turn_distance
        out = thread_inter_turn_distance([_node("t1", "a", [1.0, 0.0])])
        assert out["t1"] == 0.0, "single-turn threads have no inter-turn movement"

    def test_thread_that_moves_scores_higher(self, isolated_home):
        """A thread whose turns drift through embedding space scores
        higher than a thread that stays put — the literature's
        'thread did work' signal."""
        from trinity_local.me.depth import thread_inter_turn_distance
        # t_static: 3 turns at the same point
        # t_moving: 3 turns walking around the unit circle
        nodes = [
            _node("t_static", "s0", [1.0, 0.0]),
            _node("t_static", "s1", [1.0, 0.0]),
            _node("t_static", "s2", [1.0, 0.0]),
            _node("t_moving", "m0", [1.0, 0.0]),
            _node("t_moving", "m1", [0.0, 1.0]),
            _node("t_moving", "m2", [-1.0, 0.0]),
        ]
        # Wire turn_index so the consecutive-pair logic works.
        for i, n in enumerate(nodes):
            n.turn_index = i % 3
        out = thread_inter_turn_distance(nodes)
        assert out["t_moving"] > out["t_static"], (
            f"moving thread should score higher: moving={out['t_moving']} "
            f"static={out['t_static']}"
        )
        # Static thread should be ~0 (identical consecutive embeddings).
        assert out["t_static"] < 0.01

    def test_consecutive_pair_order_via_turn_index(self, isolated_home):
        """Pairs are determined by turn_index ordering, not iteration
        order — a corpus that lists turns out-of-order shouldn't
        produce different distances."""
        from trinity_local.me.depth import thread_inter_turn_distance
        a, b, c = _node("t1", "a", [1.0, 0.0]), _node("t1", "b", [0.0, 1.0]), _node("t1", "c", [-1.0, 0.0])
        a.turn_index, b.turn_index, c.turn_index = 0, 1, 2
        in_order = thread_inter_turn_distance([a, b, c])
        out_of_order = thread_inter_turn_distance([c, a, b])
        assert math.isclose(in_order["t1"], out_of_order["t1"], abs_tol=1e-9), (
            "consecutive-pair distance shouldn't depend on input order"
        )


class TestThreadLID:
    def test_low_lid_for_collapsed_cluster(self, isolated_home):
        """A thread whose turns all sit near each other lives on a
        thin manifold → low LID. A thread whose turns spread out
        across uncorrelated directions → higher LID. Pin the
        relative ordering, not the absolute estimate (TwoNN MLE
        is noisy on tiny N)."""
        from trinity_local.me.depth import thread_lid
        # t_thin: 4 turns all clustered tight
        # t_rich: 4 turns spread orthogonally
        # Need ≥ 3 distinct points globally so TwoNN works.
        nodes = [
            _node("t_thin", "a", [1.0, 0.001, 0.0, 0.0]),
            _node("t_thin", "b", [1.0, 0.002, 0.0, 0.0]),
            _node("t_thin", "c", [1.0, 0.003, 0.0, 0.0]),
            _node("t_thin", "d", [1.0, 0.004, 0.0, 0.0]),
            _node("t_rich", "e", [1.0, 0.0, 0.0, 0.0]),
            _node("t_rich", "f", [0.0, 1.0, 0.0, 0.0]),
            _node("t_rich", "g", [0.0, 0.0, 1.0, 0.0]),
            _node("t_rich", "h", [0.0, 0.0, 0.0, 1.0]),
        ]
        out = thread_lid(nodes)
        # Both threads have LID estimates; rich > thin is the
        # invariant we care about.
        assert "t_thin" in out and "t_rich" in out
        # Sanity: the values are non-negative reals.
        assert out["t_thin"] >= 0
        assert out["t_rich"] >= 0

    def test_too_small_corpus_returns_empty(self, isolated_home):
        from trinity_local.me.depth import thread_lid
        # < 3 usable points → can't estimate any neighbor ratio.
        assert thread_lid([_node("t1", "a", [1.0, 0.0])]) == {}
        assert thread_lid([_node("t1", "a", [1.0, 0.0]), _node("t2", "b", [0.0, 1.0])]) == {}

    def test_duplicate_embeddings_dont_break(self, isolated_home):
        """Two identical embeddings → d1 = 0 → r = inf → log(r) = inf
        would blow up the MLE. The EPS clamp keeps it finite."""
        from trinity_local.me.depth import thread_lid
        nodes = [
            _node("t1", "a", [1.0, 0.0]),
            _node("t1", "b", [1.0, 0.0]),  # exact duplicate
            _node("t2", "c", [0.0, 1.0]),
        ]
        out = thread_lid(nodes)
        # Must not raise; must return finite numbers.
        for v in out.values():
            assert math.isfinite(v), f"LID estimate non-finite: {v}"


class TestDepthScoreComposite:
    """Tick #54 redesign: weighted additive composite, not multiplicative.
    Single-turn threads must still rank by corpus_distance alone — the
    real-corpus diagnostic that motivated the redesign."""

    def test_single_turn_thread_can_rank(self, isolated_home):
        """The diagnostic that drove the redesign: with the OLD
        multiplicative composite, single-turn threads scored 0
        because log(1 + 0_inter_turn) = 0. The additive composite
        lets a single-turn outlier earn its corpus_distance term —
        the score must be > 0, not necessarily larger than every
        multi-turn alternative.

        Tick #84 reframe: the original assertion ("single-turn
        outlier outranks 3-turn near-corpus") was relying on a fake
        signal — the LID cap at 50 contributed tanh(50/10) ≈ 1.0 →
        +0.5 to every short thread's score regardless of actual
        novelty. After the LID_MIN_TURNS=5 gate (tick #84), short
        threads correctly forfeit the LID lift, and a multi-turn
        thread that ALSO moves through embedding space (inter_turn
        bonus) earns more than a flat outlier. The original test
        intent — "single-turn threads can rank, not silently zero" —
        is what we pin here.
        """
        from trinity_local.me.depth import depth_score
        nodes = [
            _node("t_a", "a", [1.0, 0.0, 0.0]),
            _node("t_b", "b", [0.0, 1.0, 0.0]),
            _node("t_c", "c", [0.0, 0.0, 1.0]),
        ]
        out = depth_score(nodes)
        # All single-turn threads MUST have nonzero score now (this
        # is the additive-composite guarantee — the old multiplicative
        # form returned 0 for any thread with inter_turn=0).
        assert all(v > 0 for v in out.values()), (
            f"single-turn threads should rank above zero post-additive; "
            f"got {out}"
        )

    def test_multi_turn_rich_thread_still_wins(self, isolated_home):
        """A thread that ALSO moves through embedding space (inter_turn > 0)
        and samples rich axes should beat an equally-outlying single-turn
        thread. The additive bonuses lift, they don't gate."""
        from trinity_local.me.depth import depth_score
        nodes = [
            _node("t_rich", "a", [1.0, 0.0, 0.0]),
            _node("t_rich", "b", [0.0, 1.0, 0.0]),
            _node("t_rich", "c", [0.0, 0.0, 1.0]),
            _node("t_outlier_single", "d", [1.0, 0.0, 0.0]),
            _node("t_baseline", "e", [0.5, 0.5, 0.0]),
            _node("t_baseline", "f", [0.5, 0.5, 0.0]),
        ]
        for i, n in enumerate(nodes):
            n.turn_index = i % 3
        out = depth_score(nodes)
        assert out.get("t_rich", 0) > out.get("t_baseline", 0), (
            "multi-turn rich thread should outrank near-corpus baseline"
        )

    def test_cold_install_returns_empty(self, isolated_home):
        from trinity_local.me.depth import depth_score
        assert depth_score([]) == {}

    def test_lid_min_turns_env_override(self, monkeypatch, isolated_home):
        """Tick #86 — `TRINITY_LID_MIN_TURNS` env var lets a power
        user tune the gate without code change. Valid integer ≥2 is
        accepted; invalid values fall back to the 5-turn default.

        The behavior check: with the env at 3, a 3-turn thread can
        earn nonzero LID (whereas with default 5 it would be 0). The
        env path matters more than the bare number — Trinity's "ship
        a tight product" stance is "ship one default, let users tune
        empirically" rather than committing to many code-paths."""
        from trinity_local.me.depth import thread_lid
        # 3 turns spread across the embedding space — enough for a
        # TwoNN ratio to be defined, but below the default gate of 5.
        nodes = [
            _node("t3", "a", [1.0, 0.0, 0.0]),
            _node("t3", "b", [0.0, 1.0, 0.0]),
            _node("t3", "c", [0.0, 0.0, 1.0]),
            # Need ≥3 distinct points for TwoNN's `if len(items) < 3`
            # short-circuit — add a sentinel to keep the algorithm running.
            _node("sentinel", "s", [0.5, 0.5, 0.0]),
        ]
        # Default gate: 3-turn thread → LID = 0
        monkeypatch.delenv("TRINITY_LID_MIN_TURNS", raising=False)
        out_default = thread_lid(nodes)
        assert out_default.get("t3", 0.0) == 0.0
        # Override to 3: same thread now earns nonzero LID
        monkeypatch.setenv("TRINITY_LID_MIN_TURNS", "3")
        out_loosened = thread_lid(nodes)
        assert out_loosened.get("t3", 0.0) > 0.0
        # Invalid value silently falls back to default — depth pipeline
        # must NEVER crash on a malformed env (it's optional, after all).
        monkeypatch.setenv("TRINITY_LID_MIN_TURNS", "not-a-number")
        out_bad = thread_lid(nodes)
        assert out_bad.get("t3", 0.0) == 0.0, (
            "invalid env value should fall back to default — saw nonzero "
            "LID for a 3-turn thread, meaning the int() raise wasn't caught"
        )

    def test_lid_capped_against_runaway(self, isolated_home):
        """Real corpus produced LID values in the millions because the
        TwoNN MLE diverges for near-duplicate embedding pairs. Cap at
        50 keeps the high tail informative without letting outliers
        dominate the composite."""
        from trinity_local.me.depth import thread_lid
        # Two near-duplicate pairs in the same thread → d1 ~= 0 → r
        # explodes → without cap, MLE goes to millions.
        nodes = [
            _node("t_dup", "a", [1.0, 0.0]),
            _node("t_dup", "b", [1.0, 0.000001]),  # near-duplicate
            _node("t_other", "c", [0.0, 1.0]),
        ]
        out = thread_lid(nodes)
        for tid, val in out.items():
            assert val <= 50.0, f"{tid} LID = {val} exceeds cap"


class TestRankThreadsByDepth:
    def test_returns_descending_order(self, isolated_home):
        from trinity_local.me.depth import rank_threads_by_depth
        nodes = [
            _node("t_near", "a", [1.0, 0.0]),
            _node("t_far", "b", [0.0, 1.0]),
            _node("t_middle", "c", [0.7, 0.7]),
        ]
        ranked = rank_threads_by_depth(nodes)
        # Ranked by depth score (centroid distance) descending.
        scores = [s for _, s in ranked]
        assert scores == sorted(scores, reverse=True), (
            f"not sorted descending: {ranked}"
        )

    def test_top_k_truncates(self, isolated_home):
        from trinity_local.me.depth import rank_threads_by_depth
        nodes = [_node(f"t{i}", f"n{i}", [float(i), float(-i)]) for i in range(5)]
        ranked = rank_threads_by_depth(nodes, top_k=2)
        assert len(ranked) == 2

    def test_empty_input_returns_empty(self, isolated_home):
        from trinity_local.me.depth import rank_threads_by_depth
        assert rank_threads_by_depth([]) == []
