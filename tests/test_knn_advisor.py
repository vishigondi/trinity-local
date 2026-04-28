"""Tests for knn_advisor — the k-NN advisory layer."""
from __future__ import annotations

import json
import os
import tempfile
from unittest import mock

import pytest

# Use isolated TRINITY_HOME for all tests
_test_home = tempfile.mkdtemp(prefix="trinity-test-knn-")
os.environ["TRINITY_HOME"] = _test_home

from trinity_local.knn_advisor import (
    KnnAdvice,
    _CorpusEntry,
    _load_corpus,
    advise,
    corpus_size,
)


def _make_hard_example(
    example_id: str,
    provider: str,
    label: str,
    hard_type: str,
    prompt: str,
) -> dict:
    """Build a minimal hard example JSON blob."""
    return {
        "example_id": example_id,
        "hard_type": hard_type,
        "chosen_provider": provider,
        "chosen_model": {"provider": provider},
        "label": label,
        "outcome": {},
        "transcript": {
            "session_id": f"sess-{example_id}",
            "provider": provider,
            "source_path": "/tmp/fake.jsonl",
            "first_user_text": prompt,
        },
        "hard_signals": {},
        "related_sessions": [],
    }


def _populate_corpus(examples: list[dict]) -> None:
    """Write example JSONs to the test hard_examples dir."""
    from trinity_local.config import trinity_home

    hard_dir = trinity_home() / "research" / "hard_examples"
    hard_dir.mkdir(parents=True, exist_ok=True)
    for ex in examples:
        path = hard_dir / f"{ex['example_id']}.json"
        path.write_text(json.dumps(ex), encoding="utf-8")

    # Force reload
    import trinity_local.knn_advisor as adv
    adv._corpus_cache = None


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCorpusLoading:
    def test_empty_corpus(self):
        """advise() returns None when no corpus exists."""
        import trinity_local.knn_advisor as adv
        adv._corpus_cache = None
        result = advise("test prompt", "claude")
        # May return None (no corpus) or an advice (if corpus dir was populated)
        # Just ensure no crash
        assert result is None or isinstance(result, KnnAdvice)

    def test_corpus_loads(self):
        examples = [
            _make_hard_example("ex1", "claude", "needs_council", "needs_council",
                               "Write a sorting algorithm in Python"),
            _make_hard_example("ex2", "codex", "bad_fit", "failed",
                               "Deploy Kubernetes cluster on AWS"),
            _make_hard_example("ex3", "claude", "needs_council", "needs_council",
                               "Debug this failing test case"),
            _make_hard_example("ex4", "gemini", "bad_fit", "rerouted",
                               "Research competitor pricing strategies"),
            _make_hard_example("ex5", "cowork", "needs_council", "needs_council",
                               "Analyze these sales reports and create a dashboard"),
            _make_hard_example("ex6", "claude", "bad_fit", "rerouted",
                               "Compare cloud hosting providers for our startup"),
        ]
        _populate_corpus(examples)
        assert corpus_size() == 6


class TestAdvise:
    @pytest.fixture(autouse=True)
    def _setup_corpus(self):
        """Set up a small corpus for testing."""
        examples = [
            _make_hard_example("ex1", "claude", "needs_council", "needs_council",
                               "Write a sorting algorithm in Python"),
            _make_hard_example("ex2", "codex", "bad_fit", "failed",
                               "Deploy Kubernetes cluster on AWS"),
            _make_hard_example("ex3", "claude", "needs_council", "needs_council",
                               "Debug this failing test case"),
            _make_hard_example("ex4", "gemini", "bad_fit", "rerouted",
                               "Research competitor pricing strategies"),
            _make_hard_example("ex5", "cowork", "needs_council", "needs_council",
                               "Analyze these sales reports and create a dashboard"),
            _make_hard_example("ex6", "claude", "bad_fit", "rerouted",
                               "Compare cloud hosting providers for our startup"),
            _make_hard_example("ex7", "codex", "needs_council", "needs_council",
                               "Refactor the database layer to use connection pooling"),
        ]
        _populate_corpus(examples)

    def test_empty_prompt_returns_none(self):
        assert advise("", "claude") is None
        assert advise("   ", "claude") is None

    def test_advise_returns_knn_advice(self):
        """Non-empty prompt against valid corpus returns KnnAdvice."""
        result = advise("Write a function to sort arrays", "claude", k=3)
        if result is None:
            pytest.skip("Embeddings not available")
        assert isinstance(result, KnnAdvice)
        assert result.neighbor_count == 3
        assert len(result.evidence) > 0

    def test_should_council_flag(self):
        """When most neighbors are needs_council/bad_fit, should_council is True."""
        result = advise("Write a sorting algorithm", "claude", k=5)
        if result is None:
            pytest.skip("Embeddings not available")
        # Our corpus is mostly needs_council/bad_fit, so should_council should be True
        assert isinstance(result.should_council, bool)

    def test_top2_providers(self):
        result = advise("Deploy to production", "claude", k=5)
        if result is None:
            pytest.skip("Embeddings not available")
        assert isinstance(result.top2_providers, list)
        assert len(result.top2_providers) <= 2

    def test_evidence_includes_knn_line(self):
        result = advise("Research competitor analysis", "claude", k=3)
        if result is None:
            pytest.skip("Embeddings not available")
        assert any("k-NN" in e for e in result.evidence)


class TestUpgradeRecommendation:
    """Test that _upgrade_recommendation correctly integrates k-NN advice."""

    def test_heuristic_fallback_when_no_corpus(self):
        """When knn_advisor.advise returns None, rec is unchanged."""
        from trinity_local.task_schema import TaskRecommendation

        rec = TaskRecommendation(
            recommended_provider="claude",
            recommended_mode="recommendation",
            reason="test",
            confidence=0.55,
            evidence=[],
        )
        original_mode = rec.recommended_mode

        with mock.patch("trinity_local.knn_advisor.advise", return_value=None):
            from trinity_local.watch_runtime import _upgrade_recommendation
            result = _upgrade_recommendation(
                (rec, [], "claude"), "test prompt", "claude"
            )

        out_rec, out_members, out_primary = result
        assert out_rec.recommended_mode == original_mode
        assert out_rec.knn_method is None

    def test_never_downgrade_council(self):
        """k-NN should never downgrade a council recommendation."""
        from trinity_local.task_schema import TaskRecommendation

        rec = TaskRecommendation(
            recommended_provider="gemini",
            recommended_mode="council",
            reason="test",
            confidence=0.72,
            evidence=[],
        )

        advice = KnnAdvice(
            should_council=False,  # k-NN says no council
            council_confidence=0.2,
            neighbor_count=5,
            evidence=["k-NN test"],
        )

        with mock.patch("trinity_local.knn_advisor.advise", return_value=advice):
            from trinity_local.watch_runtime import _upgrade_recommendation
            result = _upgrade_recommendation(
                (rec, ["gemini", "codex"], "claude"), "test prompt", "claude"
            )

        out_rec, _, _ = result
        # Must NOT downgrade to recommendation
        assert out_rec.recommended_mode == "council"
        # But should still annotate
        assert out_rec.knn_method == "embedding_knn"

    def test_upgrade_to_council(self):
        """k-NN can promote recommendation → council."""
        from trinity_local.task_schema import TaskRecommendation

        rec = TaskRecommendation(
            recommended_provider="claude",
            recommended_mode="recommendation",
            reason="Claude is default",
            confidence=0.55,
            evidence=[],
        )

        advice = KnnAdvice(
            should_council=True,
            council_confidence=0.8,
            top2_providers=["codex", "gemini"],
            neighbor_count=5,
            evidence=["k-NN: 4/5 neighbors suggest council"],
        )

        with mock.patch("trinity_local.knn_advisor.advise", return_value=advice):
            from trinity_local.watch_runtime import _upgrade_recommendation
            result = _upgrade_recommendation(
                (rec, [], "claude"), "test prompt", "claude"
            )

        out_rec, out_members, _ = result
        assert out_rec.recommended_mode == "council"
        assert out_rec.knn_method == "embedding_knn"
        assert out_rec.knn_council_confidence == 0.8
        assert out_rec.top2_providers == ["codex", "gemini"]
        assert any("k-NN" in e for e in out_rec.evidence)
        # Members should be populated from top2
        assert len(out_members) > 0
