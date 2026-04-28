"""Ranking — compare heuristic baseline vs embedding-based prediction.

The heuristic baseline is the current _guess_task_kind() in watch_runtime.py.
The embedding ranker uses k-NN over TF-IDF vectors.

This module produces a comparison report showing accuracy, confusion matrix,
and per-provider/per-task-kind breakdowns. Written to
~/.trinity/research/ranking_report.json.
"""
from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from ..config import trinity_home
from ..training_schema import RoutingExample
from .embeddings import EmbeddingRecord, cosine_similarity


def _research_dir() -> Path:
    path = trinity_home() / "research"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass
class PredictionResult:
    """One example's prediction from a ranker."""
    example_id: str
    true_label: str
    true_provider: str
    true_task_kind: str
    predicted_label: str
    predicted_provider: str | None = None
    correct: bool = False
    method: str = ""


@dataclass
class RankingReport:
    """Aggregate comparison between methods."""
    method: str
    total: int = 0
    correct: int = 0
    accuracy: float = 0.0
    label_accuracy: dict[str, float] = field(default_factory=dict)
    provider_accuracy: dict[str, float] = field(default_factory=dict)
    task_kind_accuracy: dict[str, float] = field(default_factory=dict)
    confusion: dict[str, dict[str, int]] = field(default_factory=dict)
    predictions: list[PredictionResult] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "method": self.method,
            "total": self.total,
            "correct": self.correct,
            "accuracy": round(self.accuracy, 4),
            "label_accuracy": {k: round(v, 4) for k, v in self.label_accuracy.items()},
            "provider_accuracy": {k: round(v, 4) for k, v in self.provider_accuracy.items()},
            "task_kind_accuracy": {k: round(v, 4) for k, v in self.task_kind_accuracy.items()},
            "confusion": self.confusion,
        }


# ---------------------------------------------------------------------------
# Heuristic baseline
# ---------------------------------------------------------------------------

def _heuristic_label(example: RoutingExample) -> str:
    """The current heuristic: provider is always "good_fit" unless the
    task kind suggests council."""
    task_kind = example.transcript.task_kind_hint or "general"
    provider = example.chosen_provider

    # The heuristic always says the chosen provider is fine
    # This is the simplest baseline — "stay with what you have"
    return "good_fit"


def run_heuristic_baseline(examples: list[RoutingExample]) -> RankingReport:
    """Score the heuristic baseline against weak labels."""
    predictions: list[PredictionResult] = []
    for ex in examples:
        predicted = _heuristic_label(ex)
        predictions.append(PredictionResult(
            example_id=ex.example_id,
            true_label=ex.label,
            true_provider=ex.chosen_provider,
            true_task_kind=ex.transcript.task_kind_hint or "general",
            predicted_label=predicted,
            predicted_provider=ex.chosen_provider,
            correct=predicted == ex.label,
            method="heuristic",
        ))
    return _build_report("heuristic", predictions)


# ---------------------------------------------------------------------------
# Embedding k-NN ranker
# ---------------------------------------------------------------------------

def run_knn_ranker(
    examples: list[RoutingExample],
    embeddings: list[EmbeddingRecord],
    k: int = 5,
) -> RankingReport:
    """Score a k-NN ranker using leave-one-out cross-validation.

    For each example, find the k nearest neighbors (excluding itself),
    take the majority label, and compare against the true label.
    """
    # Build index: example_id -> embedding
    emb_index: dict[str, EmbeddingRecord] = {e.example_id: e for e in embeddings}
    example_index: dict[str, RoutingExample] = {e.example_id: e for e in examples}

    # Only evaluate examples that have embeddings
    valid_ids = [eid for eid in emb_index if eid in example_index]
    if len(valid_ids) < k + 1:
        return RankingReport(method="knn", total=0)

    predictions: list[PredictionResult] = []
    for query_id in valid_ids:
        query_emb = emb_index[query_id]
        query_ex = example_index[query_id]

        # Find k nearest neighbors
        similarities: list[tuple[float, str]] = []
        for candidate_id in valid_ids:
            if candidate_id == query_id:
                continue
            sim = cosine_similarity(query_emb.vector, emb_index[candidate_id].vector)
            similarities.append((sim, candidate_id))

        similarities.sort(key=lambda x: -x[0])
        top_k = similarities[:k]

        # Majority vote on label
        label_votes: Counter[str] = Counter()
        provider_votes: Counter[str] = Counter()
        for sim, neighbor_id in top_k:
            neighbor = example_index[neighbor_id]
            label_votes[neighbor.label] += 1
            provider_votes[neighbor.chosen_provider] += 1

        predicted_label = label_votes.most_common(1)[0][0] if label_votes else "good_fit"
        predicted_provider = provider_votes.most_common(1)[0][0] if provider_votes else None

        predictions.append(PredictionResult(
            example_id=query_id,
            true_label=query_ex.label,
            true_provider=query_ex.chosen_provider,
            true_task_kind=query_ex.transcript.task_kind_hint or "general",
            predicted_label=predicted_label,
            predicted_provider=predicted_provider,
            correct=predicted_label == query_ex.label,
            method="knn",
        ))

    return _build_report("knn", predictions)


# ---------------------------------------------------------------------------
# Report builder
# ---------------------------------------------------------------------------

def _build_report(method: str, predictions: list[PredictionResult]) -> RankingReport:
    """Build aggregate metrics from predictions."""
    total = len(predictions)
    if total == 0:
        return RankingReport(method=method)

    correct = sum(1 for p in predictions if p.correct)

    # Per-label accuracy
    label_total: Counter[str] = Counter()
    label_correct: Counter[str] = Counter()
    for p in predictions:
        label_total[p.true_label] += 1
        if p.correct:
            label_correct[p.true_label] += 1
    label_accuracy = {
        label: label_correct[label] / count
        for label, count in label_total.items()
        if count > 0
    }

    # Per-provider accuracy
    prov_total: Counter[str] = Counter()
    prov_correct: Counter[str] = Counter()
    for p in predictions:
        prov_total[p.true_provider] += 1
        if p.correct:
            prov_correct[p.true_provider] += 1
    provider_accuracy = {
        prov: prov_correct[prov] / count
        for prov, count in prov_total.items()
        if count > 0
    }

    # Per-task-kind accuracy
    kind_total: Counter[str] = Counter()
    kind_correct: Counter[str] = Counter()
    for p in predictions:
        kind_total[p.true_task_kind] += 1
        if p.correct:
            kind_correct[p.true_task_kind] += 1
    task_kind_accuracy = {
        kind: kind_correct[kind] / count
        for kind, count in kind_total.items()
        if count > 0
    }

    # Confusion matrix
    confusion: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for p in predictions:
        confusion[p.true_label][p.predicted_label] += 1

    return RankingReport(
        method=method,
        total=total,
        correct=correct,
        accuracy=correct / total,
        label_accuracy=label_accuracy,
        provider_accuracy=provider_accuracy,
        task_kind_accuracy=task_kind_accuracy,
        confusion={k: dict(v) for k, v in confusion.items()},
        predictions=predictions,
    )


# ---------------------------------------------------------------------------
# Full evaluation pipeline
# ---------------------------------------------------------------------------

def run_evaluation(
    examples: list[RoutingExample],
    embeddings: list[EmbeddingRecord],
    k: int = 5,
) -> dict[str, RankingReport]:
    """Run all rankers and return comparison reports."""
    results: dict[str, RankingReport] = {}
    results["heuristic"] = run_heuristic_baseline(examples)
    results["knn"] = run_knn_ranker(examples, embeddings, k=k)
    return results


def save_evaluation(reports: dict[str, RankingReport]) -> Path:
    """Save evaluation reports to disk."""
    path = _research_dir() / "ranking_report.json"
    payload = {name: report.to_dict() for name, report in reports.items()}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
