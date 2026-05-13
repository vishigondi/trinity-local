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
