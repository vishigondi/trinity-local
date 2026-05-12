"""Tests for research modules: replay, embeddings, ranking."""
from __future__ import annotations

import json
import math
from pathlib import Path

from trinity_local.research.replay import (
    ReplayStats,
    _guess_task_kind,
    _weak_label,
)
from trinity_local.research.embeddings import (
    EmbeddingRecord,
    _tokenize,
    build_tfidf_vectors,
    cosine_similarity,
)
from trinity_local.research.ranking import (
    _build_report,
    PredictionResult,
    run_heuristic_baseline,
)
from trinity_local.training_schema import (
    ModelDescriptor,
    OutcomeSignals,
    RoutingExample,
    TranscriptWindow,
)


def _make_example(
    example_id: str = "ex_test",
    provider: str = "claude",
    label: str = "good_fit",
    task_type: str = "coding",
    first_text: str = "Write a function to sort a list",
    completed: bool = True,
    tool_errors: int = 0,
    tool_calls: int = 5,
) -> RoutingExample:
    return RoutingExample(
        example_id=example_id,
        transcript=TranscriptWindow(
            session_id="sess_test",
            provider=provider,
            source_path="/tmp/test.jsonl",
            first_user_text=first_text,
            task_kind_hint=task_type,
            model=ModelDescriptor(provider=provider),
            outcome=OutcomeSignals(
                completed=completed,
                tool_errors_total=tool_errors,
                tool_calls_total=tool_calls,
            ),
        ),
        chosen_provider=provider,
        chosen_model=ModelDescriptor(provider=provider),
        label=label,
    )


class TestGuessTaskKind:
    def test_coding(self):
        assert _guess_task_kind("refactor this function") == "coding"

    def test_debugging(self):
        assert _guess_task_kind("debug this failing test") == "debugging"

    def test_research(self):
        assert _guess_task_kind("research stock market trends") == "research"

    def test_writing(self):
        assert _guess_task_kind("write a draft email") == "writing"

    def test_general(self):
        assert _guess_task_kind("help me please") == "general"


class TestWeakLabel:
    def test_good_fit(self):
        from trinity_local.training_schema import SessionFeatures, RawSessionRef
        features = SessionFeatures(
            raw=RawSessionRef(source="claude", native_id="s1", source_path="/t"),
            provider="claude",
            session_id="s1",
            model=ModelDescriptor(provider="claude"),
            outcome=OutcomeSignals(completed=True, tool_errors_total=0, tool_calls_total=10),
        )
        assert _weak_label(features) == "good_fit"

    def test_bad_fit_not_completed(self):
        from trinity_local.training_schema import SessionFeatures, RawSessionRef
        features = SessionFeatures(
            raw=RawSessionRef(source="codex", native_id="s2", source_path="/t"),
            provider="codex",
            session_id="s2",
            model=ModelDescriptor(provider="codex"),
            outcome=OutcomeSignals(completed=False, tool_errors_total=5, tool_calls_total=10),
        )
        assert _weak_label(features) == "bad_fit"

    def test_needs_council_high_error_rate(self):
        from trinity_local.training_schema import SessionFeatures, RawSessionRef
        features = SessionFeatures(
            raw=RawSessionRef(source="gemini", native_id="s3", source_path="/t"),
            provider="gemini",
            session_id="s3",
            model=ModelDescriptor(provider="gemini"),
            outcome=OutcomeSignals(completed=True, tool_errors_total=3, tool_calls_total=10),
        )
        assert _weak_label(features) == "needs_council"


class TestTokenize:
    def test_basic(self):
        assert _tokenize("Hello World 123") == ["hello", "world", "123"]

    def test_strips_punctuation(self):
        tokens = _tokenize("write a function(x, y) -> int:")
        assert "function" in tokens
        assert "int" in tokens


class TestTfidfVectors:
    def test_produces_vectors(self):
        examples = [
            _make_example("ex1", first_text="write a sorting function for a list"),
            _make_example("ex2", first_text="debug the failing test for sorting"),
            _make_example("ex3", first_text="research the best sorting algorithm"),
            _make_example("ex4", first_text="write documentation about sorting"),
        ]
        records = build_tfidf_vectors(examples)
        assert len(records) == 4
        assert all(isinstance(r, EmbeddingRecord) for r in records)
        assert all(len(r.vector) > 0 for r in records)

    def test_vectors_normalized(self):
        examples = [
            _make_example("ex1", first_text="write a sorting function for the list"),
            _make_example("ex2", first_text="debug the failing test for sorting"),
            _make_example("ex3", first_text="research best sorting algorithms available"),
        ]
        records = build_tfidf_vectors(examples)
        for r in records:
            norm = math.sqrt(sum(v * v for v in r.vector))
            if norm > 0:
                assert abs(norm - 1.0) < 0.01, f"Not normalized: {norm}"

    def test_single_example_returns_zero(self):
        examples = [_make_example("ex1")]
        records = build_tfidf_vectors(examples)
        assert len(records) == 1


class TestCosineSimilarity:
    def test_identical(self):
        assert cosine_similarity([1.0, 0.0], [1.0, 0.0]) == 1.0

    def test_orthogonal(self):
        assert cosine_similarity([1.0, 0.0], [0.0, 1.0]) == 0.0

    def test_empty(self):
        assert cosine_similarity([], []) == 0.0

    def test_different_lengths(self):
        assert cosine_similarity([1.0], [1.0, 2.0]) == 0.0


class TestHeuristicBaseline:
    def test_always_predicts_good_fit(self):
        examples = [
            _make_example("ex1", label="good_fit"),
            _make_example("ex2", label="bad_fit"),
            _make_example("ex3", label="needs_council"),
        ]
        report = run_heuristic_baseline(examples)
        assert report.total == 3
        assert report.correct == 1  # Only ex1 matches
        assert report.accuracy == 1 / 3


class TestBuildReport:
    def test_empty(self):
        report = _build_report("test", [])
        assert report.total == 0

    def test_perfect(self):
        predictions = [
            PredictionResult(
                example_id="ex1", true_label="good_fit", true_provider="claude",
                true_task_kind="coding", predicted_label="good_fit",
                correct=True, method="test",
            ),
        ]
        report = _build_report("test", predictions)
        assert report.accuracy == 1.0

    def test_confusion_matrix(self):
        predictions = [
            PredictionResult(
                example_id="ex1", true_label="good_fit", true_provider="claude",
                true_task_kind="coding", predicted_label="bad_fit",
                correct=False, method="test",
            ),
            PredictionResult(
                example_id="ex2", true_label="good_fit", true_provider="claude",
                true_task_kind="coding", predicted_label="good_fit",
                correct=True, method="test",
            ),
        ]
        report = _build_report("test", predictions)
        assert report.confusion["good_fit"]["bad_fit"] == 1
        assert report.confusion["good_fit"]["good_fit"] == 1
