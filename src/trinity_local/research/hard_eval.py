"""Extended evaluation — hard-example-only metrics.

Evaluates against the 5 metrics the user requested:
  1. Reroute recall
  2. needs_council precision/recall
  3. Switch prediction accuracy
  4. Top-2 provider accuracy on hard examples
  5. Nearest-neighbor evidence quality for recommendations
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
class HardEvalReport:
    """Extended evaluation report for hard examples."""
    total_hard: int = 0
    by_hard_type: dict[str, int] = field(default_factory=dict)

    # 1. Reroute recall: of sessions that actually switched, how many
    #    did the ranker predict as bad_fit?
    reroute_recall: float | None = None
    reroute_total: int = 0
    reroute_detected: int = 0

    # 2. needs_council precision/recall
    needs_council_precision: float | None = None
    needs_council_recall: float | None = None
    needs_council_true_positive: int = 0
    needs_council_false_positive: int = 0
    needs_council_false_negative: int = 0
    needs_council_true_negative: int = 0

    # 3. Switch prediction accuracy: binary classification
    switch_accuracy: float | None = None
    switch_total: int = 0
    switch_correct: int = 0

    # 4. Top-2 provider accuracy: for sessions with known providers,
    #    does the top-2 k-NN vote include the correct provider?
    top2_provider_accuracy: float | None = None
    top2_total: int = 0
    top2_correct: int = 0

    # 5. NN evidence quality: average similarity of top-k neighbors
    nn_avg_similarity: float | None = None
    nn_min_similarity: float | None = None
    nn_avg_label_agreement: float | None = None

    # Label-level breakdown
    label_accuracy: dict[str, float] = field(default_factory=dict)
    confusion: dict[str, dict[str, int]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        # Round floats
        for key in d:
            if isinstance(d[key], float):
                d[key] = round(d[key], 4) if d[key] is not None else None
        if d.get("label_accuracy"):
            d["label_accuracy"] = {k: round(v, 4) for k, v in d["label_accuracy"].items()}
        return d


def run_hard_eval(
    hard_examples: list[RoutingExample],
    embeddings: list[EmbeddingRecord],
    *,
    k: int = 5,
    hard_types: dict[str, str] | None = None,
) -> dict[str, HardEvalReport]:
    """Run extended evaluation on hard examples only.

    Args:
        hard_examples: routing examples (only hard ones)
        embeddings: embedding records for these examples
        hard_types: mapping of example_id -> hard_type (from hard_mining)
        k: number of neighbors for k-NN

    Returns dict with "heuristic" and "knn" reports.
    """
    hard_types = hard_types or {}
    emb_index = {e.example_id: e for e in embeddings}
    ex_index = {e.example_id: e for e in hard_examples}

    results = {}
    results["heuristic"] = _eval_heuristic(hard_examples, hard_types)
    results["knn"] = _eval_knn(hard_examples, emb_index, ex_index, hard_types, k=k)
    return results


def _eval_heuristic(
    examples: list[RoutingExample],
    hard_types: dict[str, str],
) -> HardEvalReport:
    """Evaluate the heuristic baseline (always predicts good_fit)."""
    report = HardEvalReport(total_hard=len(examples))

    # Count by hard type
    type_counts: Counter[str] = Counter()
    for ex in examples:
        ht = hard_types.get(ex.example_id, "unknown")
        type_counts[ht] += 1
    report.by_hard_type = dict(type_counts)

    # Heuristic always predicts "good_fit"
    predicted = "good_fit"
    confusion: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))

    for ex in examples:
        true_label = ex.label
        confusion[true_label][predicted] += 1

    report.confusion = {k: dict(v) for k, v in confusion.items()}

    # 1. Reroute recall: switched/rerouted examples labeled bad_fit
    reroute_types = {"switched", "rerouted"}
    reroute_examples = [e for e in examples if hard_types.get(e.example_id) in reroute_types]
    report.reroute_total = len(reroute_examples)
    report.reroute_detected = 0  # Heuristic never predicts bad_fit
    report.reroute_recall = 0.0 if report.reroute_total > 0 else None

    # 2. needs_council precision/recall
    nc_true = [e for e in examples if e.label == "needs_council"]
    report.needs_council_false_negative = len(nc_true)
    report.needs_council_true_positive = 0
    report.needs_council_false_positive = 0
    report.needs_council_true_negative = len(examples) - len(nc_true)
    report.needs_council_recall = 0.0 if nc_true else None
    report.needs_council_precision = None  # No predictions made

    # 3. Switch accuracy: binary (is this a switch or not?)
    switch_examples = [e for e in examples if hard_types.get(e.example_id) == "switched"]
    report.switch_total = len(examples)
    report.switch_correct = len(examples) - len(switch_examples)  # Heuristic says "not switch" for all
    report.switch_accuracy = report.switch_correct / report.switch_total if report.switch_total > 0 else None

    # 4/5: Not applicable for heuristic
    report.top2_provider_accuracy = None
    report.nn_avg_similarity = None
    report.nn_min_similarity = None
    report.nn_avg_label_agreement = None

    # Label accuracy
    label_total: Counter[str] = Counter()
    label_correct: Counter[str] = Counter()
    for ex in examples:
        label_total[ex.label] += 1
        if ex.label == predicted:
            label_correct[ex.label] += 1
    report.label_accuracy = {
        label: label_correct[label] / count
        for label, count in label_total.items()
        if count > 0
    }

    return report


def _eval_knn(
    examples: list[RoutingExample],
    emb_index: dict[str, EmbeddingRecord],
    ex_index: dict[str, RoutingExample],
    hard_types: dict[str, str],
    *,
    k: int = 5,
) -> HardEvalReport:
    """Evaluate k-NN ranker on hard examples with extended metrics."""
    report = HardEvalReport(total_hard=len(examples))

    # Count by type
    type_counts: Counter[str] = Counter()
    for ex in examples:
        type_counts[hard_types.get(ex.example_id, "unknown")] += 1
    report.by_hard_type = dict(type_counts)

    valid_ids = [eid for eid in emb_index if eid in ex_index]
    if len(valid_ids) < k + 1:
        return report

    confusion: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    all_sims: list[float] = []
    all_label_agree: list[float] = []

    reroute_types = {"switched", "rerouted"}
    reroute_detected = 0
    reroute_total = 0
    nc_tp = 0
    nc_fp = 0
    nc_fn = 0
    nc_tn = 0
    switch_correct = 0
    switch_total = 0
    top2_correct = 0
    top2_total = 0

    for query_id in valid_ids:
        query_emb = emb_index[query_id]
        query_ex = ex_index[query_id]
        true_label = query_ex.label
        ht = hard_types.get(query_id, "unknown")

        # Find k nearest
        sims: list[tuple[float, str]] = []
        for cand_id in valid_ids:
            if cand_id == query_id:
                continue
            sim = cosine_similarity(query_emb.vector, emb_index[cand_id].vector)
            sims.append((sim, cand_id))
        sims.sort(key=lambda x: -x[0])
        top_k = sims[:k]

        # Collect votes
        label_votes: Counter[str] = Counter()
        provider_votes: Counter[str] = Counter()
        neighbor_sims: list[float] = []
        label_agreements = 0

        for sim, nid in top_k:
            neighbor = ex_index[nid]
            label_votes[neighbor.label] += 1
            provider_votes[neighbor.chosen_provider] += 1
            neighbor_sims.append(sim)
            if neighbor.label == true_label:
                label_agreements += 1

        predicted_label = label_votes.most_common(1)[0][0] if label_votes else "good_fit"
        top2_providers = [p for p, _ in provider_votes.most_common(2)]

        confusion[true_label][predicted_label] += 1

        # 1. Reroute recall
        if ht in reroute_types:
            reroute_total += 1
            if predicted_label == "bad_fit":
                reroute_detected += 1

        # 2. needs_council P/R
        true_nc = true_label == "needs_council"
        pred_nc = predicted_label == "needs_council"
        if true_nc and pred_nc:
            nc_tp += 1
        elif not true_nc and pred_nc:
            nc_fp += 1
        elif true_nc and not pred_nc:
            nc_fn += 1
        else:
            nc_tn += 1

        # 3. Switch prediction
        true_switch = ht == "switched"
        pred_switch = predicted_label == "bad_fit"
        switch_total += 1
        if true_switch == pred_switch:
            switch_correct += 1

        # 4. Top-2 provider accuracy
        top2_total += 1
        if query_ex.chosen_provider in top2_providers:
            top2_correct += 1

        # 5. NN evidence quality
        if neighbor_sims:
            all_sims.extend(neighbor_sims)
            all_label_agree.append(label_agreements / len(top_k))

    report.confusion = {k: dict(v) for k, v in confusion.items()}

    # 1. Reroute recall
    report.reroute_total = reroute_total
    report.reroute_detected = reroute_detected
    report.reroute_recall = reroute_detected / reroute_total if reroute_total > 0 else None

    # 2. needs_council P/R
    report.needs_council_true_positive = nc_tp
    report.needs_council_false_positive = nc_fp
    report.needs_council_false_negative = nc_fn
    report.needs_council_true_negative = nc_tn
    report.needs_council_precision = nc_tp / (nc_tp + nc_fp) if (nc_tp + nc_fp) > 0 else None
    report.needs_council_recall = nc_tp / (nc_tp + nc_fn) if (nc_tp + nc_fn) > 0 else None

    # 3. Switch prediction
    report.switch_total = switch_total
    report.switch_correct = switch_correct
    report.switch_accuracy = switch_correct / switch_total if switch_total > 0 else None

    # 4. Top-2 provider
    report.top2_total = top2_total
    report.top2_correct = top2_correct
    report.top2_provider_accuracy = top2_correct / top2_total if top2_total > 0 else None

    # 5. NN evidence quality
    if all_sims:
        report.nn_avg_similarity = sum(all_sims) / len(all_sims)
        report.nn_min_similarity = min(all_sims)
    if all_label_agree:
        report.nn_avg_label_agreement = sum(all_label_agree) / len(all_label_agree)

    # Label accuracy
    label_total: Counter[str] = Counter()
    label_correct: Counter[str] = Counter()
    for true_l, preds in confusion.items():
        for pred_l, count in preds.items():
            label_total[true_l] += count
            if true_l == pred_l:
                label_correct[true_l] += count
    report.label_accuracy = {
        label: label_correct[label] / count
        for label, count in label_total.items()
        if count > 0
    }

    return report


def save_hard_eval(reports: dict[str, HardEvalReport]) -> Path:
    """Save hard evaluation report."""
    path = _research_dir() / "hard_eval_report.json"
    payload = {name: report.to_dict() for name, report in reports.items()}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path
