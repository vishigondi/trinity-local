"""Pure-embedding depth-ranking for threads.

The literature-validated component of the depth signal (per the TAD-Bench
text-anomaly work + scientific-doc novelty detection) is centroid
distance — threads whose embedding sits far from the corpus mean are
the unusual conversations, by definition not daily chatter. The other
proposed components (inter-turn distance, curvature) have individual
backing but no production analog combining them; ship those when we
have a way to validate the combination.

This module ships the centroid-distance signal alone first. No
chairman calls. No heuristics. Pure geometry on the existing
PromptNode embeddings.

Used as a SECONDARY rank — surface deep-thought threads within a
basin's representatives, not as a pre-clustering filter (Anthropic's
Clio approach: cluster everything, rank within clusters, drop noise
via cluster-size thresholds).
"""
from __future__ import annotations

import math
from typing import Iterable

from ..memory.schemas import PromptNode


def thread_centroids(nodes: Iterable[PromptNode]) -> dict[str, list[float]]:
    """Return {transcript_id: mean_embedding} across all turns in each thread.

    Skips threads whose embeddings are missing or zero-norm. Empty
    dict when no usable nodes — caller can short-circuit.
    """
    sums: dict[str, list[float]] = {}
    counts: dict[str, int] = {}
    for node in nodes:
        emb = getattr(node, "embedding", None) or []
        if not emb:
            continue
        tid = getattr(node, "transcript_id", None)
        if not tid:
            continue
        if tid not in sums:
            sums[tid] = [0.0] * len(emb)
            counts[tid] = 0
        # Skip if dim mismatch — shouldn't happen with a consistent
        # embedder, but a stale node could be from a prior model.
        if len(emb) != len(sums[tid]):
            continue
        for i, v in enumerate(emb):
            sums[tid][i] += v
        counts[tid] += 1
    return {
        tid: [v / counts[tid] for v in s]
        for tid, s in sums.items()
        if counts[tid] > 0
    }


def corpus_centroid(centroids: dict[str, list[float]]) -> list[float]:
    """Mean of per-thread centroids. Equal weight per thread so a
    chatty 200-turn thread doesn't dominate a focused 5-turn thread."""
    if not centroids:
        return []
    dim = len(next(iter(centroids.values())))
    accum = [0.0] * dim
    n = 0
    for c in centroids.values():
        if len(c) != dim:
            continue
        for i, v in enumerate(c):
            accum[i] += v
        n += 1
    if not n:
        return []
    return [v / n for v in accum]


def cosine_distance(a: list[float], b: list[float]) -> float:
    """1 - cosine_similarity. Range [0, 2]. NaN-safe → returns 1.0
    (orthogonal) when either vector is zero."""
    if not a or not b or len(a) != len(b):
        return 1.0
    dot = 0.0
    na = 0.0
    nb = 0.0
    for x, y in zip(a, b):
        dot += x * y
        na += x * x
        nb += y * y
    if na <= 0 or nb <= 0:
        return 1.0
    cos = dot / (math.sqrt(na) * math.sqrt(nb))
    # Clamp — float drift can push valid cosine slightly outside [-1, 1]
    cos = max(-1.0, min(1.0, cos))
    return 1.0 - cos


def thread_corpus_distance(
    nodes: Iterable[PromptNode],
) -> dict[str, float]:
    """Return {transcript_id: cosine_distance(thread_centroid, corpus_centroid)}.

    Higher = the thread sits further from the corpus center. The
    TAD-Bench-validated novelty signal. Empty dict when there's no
    usable embedding data.

    Note: equal weight per thread in the corpus mean — chatty threads
    don't dominate. The literature supports this for unsupervised
    novelty detection (avoids the "everything looks normal because
    most of the corpus is one topic" failure mode).
    """
    centroids = thread_centroids(nodes)
    if not centroids:
        return {}
    corpus_mean = corpus_centroid(centroids)
    if not corpus_mean:
        return {}
    return {
        tid: cosine_distance(c, corpus_mean)
        for tid, c in centroids.items()
    }


def thread_inter_turn_distance(
    nodes: Iterable[PromptNode],
) -> dict[str, float]:
    """Return {transcript_id: mean_cosine_distance_between_consecutive_turns}.

    Threads where the user moved through semantic space (high mean
    distance between turn N and turn N+1 embeddings) did real work.
    Threads that stayed put (low distance, "more / yes / and then?")
    are chatter. Pure geometry, no labels.

    Single-turn threads get distance 0 — they had no opportunity to
    move. Filtered downstream (won't out-rank multi-turn threads
    when multiplied into the composite score with log(1+x)).
    """
    # Group nodes by thread, preserving turn_index order.
    by_thread: dict[str, list[PromptNode]] = {}
    for node in nodes:
        tid = getattr(node, "transcript_id", None)
        if not tid:
            continue
        if not (getattr(node, "embedding", None) or []):
            continue
        by_thread.setdefault(tid, []).append(node)
    out: dict[str, float] = {}
    for tid, turns in by_thread.items():
        turns.sort(key=lambda n: getattr(n, "turn_index", 0))
        if len(turns) < 2:
            out[tid] = 0.0
            continue
        deltas = []
        for prev, curr in zip(turns, turns[1:]):
            d = cosine_distance(prev.embedding, curr.embedding)
            deltas.append(d)
        out[tid] = sum(deltas) / len(deltas) if deltas else 0.0
    return out


def thread_lid(nodes: Iterable[PromptNode]) -> dict[str, float]:
    """Return {transcript_id: LID estimate} via TwoNN (Facco et al. 2017).

    For each turn embedding, find its two nearest neighbors in the
    WHOLE corpus, compute the ratio r = d2/d1. Per-thread LID is the
    MLE over its turns' ratios: d_hat = N / sum(log(r_i)).

    Higher LID = the thread's turns sample more independent semantic
    axes = richer thinking. NeurIPS 2023 used this same estimator to
    separate fluent human prose (LID ≈ 9) from AI-generated text
    (LID ≈ 7.5). We're using it as a signal for "this thread covered
    ground" rather than truth-vs-fake.

    Returns 0.0 per thread when the corpus is too small to estimate
    (< 3 distinct usable embeddings) — caller can detect via the
    log(1 + lid) collapsing to 0.
    """
    # Build a flat list of usable (transcript_id, embedding) tuples.
    items: list[tuple[str, list[float]]] = []
    for node in nodes:
        tid = getattr(node, "transcript_id", None)
        emb = getattr(node, "embedding", None) or []
        if tid and emb:
            items.append((tid, emb))
    if len(items) < 3:
        return {}
    # Group by thread for the aggregation step. The kNN search is
    # against the whole-corpus pool, not per-thread.
    by_thread: dict[str, list[int]] = {}
    for idx, (tid, _) in enumerate(items):
        by_thread.setdefault(tid, []).append(idx)
    embeddings = [emb for _, emb in items]
    # Per-turn r = d2/d1. We need the 2nd-nearest distinct neighbor
    # in cosine distance; clamp r ≥ 1 + epsilon so log(r) stays finite
    # for duplicate-embedding pairs.
    EPS = 1e-9
    per_turn_log_r: list[tuple[str, float]] = []
    for src_idx, src_emb in enumerate(embeddings):
        # All distances from this turn to every other turn.
        ds: list[float] = []
        for tgt_idx, tgt_emb in enumerate(embeddings):
            if tgt_idx == src_idx:
                continue
            d = cosine_distance(src_emb, tgt_emb)
            ds.append(d)
        if len(ds) < 2:
            continue
        ds.sort()
        d1, d2 = ds[0], ds[1]
        if d1 <= 0:
            d1 = EPS  # duplicate-embedding pairs collapse — bound r to keep log finite
        r = d2 / d1
        if r <= 1.0:
            r = 1.0 + EPS
        per_turn_log_r.append((items[src_idx][0], math.log(r)))
    # Per-thread MLE: d_hat = N_thread / sum(log_r over thread's turns)
    sums: dict[str, float] = {}
    counts: dict[str, int] = {}
    for tid, lr in per_turn_log_r:
        sums[tid] = sums.get(tid, 0.0) + lr
        counts[tid] = counts.get(tid, 0) + 1
    out: dict[str, float] = {}
    for tid in by_thread.keys():
        s = sums.get(tid, 0.0)
        n = counts.get(tid, 0)
        if n == 0 or s <= 0:
            out[tid] = 0.0
        else:
            out[tid] = n / s
    return out


def depth_score(
    nodes: Iterable[PromptNode],
) -> dict[str, float]:
    """Composite per-thread depth signal: centroid × log(1 + inter_turn) × log(1 + LID).

    Each component is individually peer-reviewed for the role it plays:
      - corpus_distance: novelty (TAD-Bench)
      - inter_turn_distance: thread moved through semantic space
      - LID: thread sampled independent axes (TwoNN; NeurIPS 2023)

    Multiplicative composition: noise in any one component drags the
    score toward 0. A thread is only "deep" when all three signals
    agree. log(1 + ...) on the two ratio-scale signals so a thread
    with massive LID but middling centroid distance doesn't blow past
    a more-balanced thread.

    Materializes all three component maps once; caller can pull each
    via the dedicated function above when they need a single signal.
    """
    nodes_list = list(nodes)  # We iterate three times
    corpus = thread_corpus_distance(nodes_list)
    inter = thread_inter_turn_distance(nodes_list)
    lid = thread_lid(nodes_list)
    out: dict[str, float] = {}
    for tid in corpus.keys():
        c = corpus.get(tid, 0.0)
        i = inter.get(tid, 0.0)
        l = lid.get(tid, 0.0)
        out[tid] = c * math.log(1.0 + i) * math.log(1.0 + l)
    return out


def rank_threads_by_depth(
    nodes: Iterable[PromptNode],
    *,
    top_k: int | None = None,
) -> list[tuple[str, float]]:
    """Return [(transcript_id, depth_score)] sorted descending by score.

    Score is the composite from `depth_score()`. `top_k=None` returns
    all threads; `top_k=N` truncates to the top-N most-depth.
    """
    scores = depth_score(nodes)
    ranked = sorted(scores.items(), key=lambda kv: kv[1], reverse=True)
    if top_k is not None:
        ranked = ranked[:top_k]
    return ranked
