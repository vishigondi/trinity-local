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


def rank_threads_by_depth(
    nodes: Iterable[PromptNode],
    *,
    top_k: int | None = None,
) -> list[tuple[str, float]]:
    """Return [(transcript_id, depth_score)] sorted descending by score.

    Today's score = corpus_centroid_distance, the single literature-
    validated component. Multi-factor composite lands once we have
    a validation harness for it.

    `top_k=None` returns all threads; `top_k=N` truncates.
    """
    distances = thread_corpus_distance(nodes)
    ranked = sorted(distances.items(), key=lambda kv: kv[1], reverse=True)
    if top_k is not None:
        ranked = ranked[:top_k]
    return ranked
