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

from ..embeddings import is_finite_embedding
from ..memory.schemas import PromptNode


def thread_centroids(nodes: Iterable[PromptNode]) -> dict[str, list[float]]:
    """Return {transcript_id: mean_embedding} across all turns in each thread.

    Skips threads whose embeddings are missing, zero-norm, or contain
    NaN/Inf. Empty dict when no usable nodes.

    NaN filter is load-bearing: real corpora include gemini_takeout
    threads whose embeddings have non-finite components (cause: stale
    embed batches from an earlier embedder generation). Without the
    filter, those poison the corpus centroid and every distance
    downstream comes back as NaN.
    """
    sums: dict[str, list[float]] = {}
    counts: dict[str, int] = {}
    for node in nodes:
        emb = getattr(node, "embedding", None)
        # is_finite_embedding returns False for None, [], and any
        # non-finite component — one check covers all three rejection
        # reasons (was two checks before tick #59 simplification).
        if not is_finite_embedding(emb):
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
    # Group nodes by thread, preserving turn_index order. Filter
    # NaN/Inf embeddings to keep cosine_distance from emitting NaN.
    by_thread: dict[str, list[PromptNode]] = {}
    for node in nodes:
        tid = getattr(node, "transcript_id", None)
        if not tid:
            continue
        emb = getattr(node, "embedding", None)
        if not is_finite_embedding(emb):
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

    Vectorized via numpy: 5000 turns × 768-d normalizes + matmul is
    sub-second; the original Python double-loop was O(N²) at
    Python-call cost and timed out on real corpora.
    """
    # Build a flat list of usable (transcript_id, embedding) tuples.
    # NaN/Inf filter is load-bearing: a single non-finite row poisons
    # the whole cosine similarity matrix via the matmul, propagating
    # NaN across every other thread's LID estimate downstream.
    items: list[tuple[str, list[float]]] = []
    for node in nodes:
        tid = getattr(node, "transcript_id", None)
        emb = getattr(node, "embedding", None)
        if not (tid and is_finite_embedding(emb)):
            continue
        items.append((tid, emb))
    if len(items) < 3:
        return {}
    try:
        import numpy as np
    except ImportError:
        # Tests / minimal installs can fall back to the slow path
        # only if numpy is missing — production always has it.
        return {}
    # Stack into matrix; drop any rows whose dim doesn't match the
    # first usable row (mixed embedder generations).
    dim = len(items[0][1])
    keep_idx = [i for i, (_, emb) in enumerate(items) if len(emb) == dim]
    if len(keep_idx) < 3:
        return {}
    tids = [items[i][0] for i in keep_idx]
    X = np.array([items[i][1] for i in keep_idx], dtype=np.float32)
    # Normalize so dot products give cosine similarity.
    norms = np.linalg.norm(X, axis=1, keepdims=True)
    norms = np.where(norms <= 0, 1.0, norms)
    Xn = X / norms
    # Cosine distance matrix = 1 - similarity. Mask self-distance
    # to +inf so it's never picked as a nearest neighbor.
    sim = Xn @ Xn.T
    sim = np.clip(sim, -1.0, 1.0)
    dist = 1.0 - sim
    np.fill_diagonal(dist, np.inf)
    # Partial-sort each row for the 2 smallest distances.
    # np.partition is O(N) per row vs O(N log N) for full sort.
    if dist.shape[1] < 3:
        return {}
    nearest_two = np.partition(dist, 2, axis=1)[:, :2]
    nearest_two.sort(axis=1)  # ensure ascending within the two columns
    d1 = nearest_two[:, 0]
    d2 = nearest_two[:, 1]
    # EPS large enough to survive float32 precision near 1.0
    # (1.0 + 1e-9 is exactly 1.0 in float32 — invisible to log).
    EPS = 1e-6
    # Clamp d1 ≥ EPS so duplicate-embedding pairs don't produce inf r.
    d1 = np.where(d1 <= 0, EPS, d1)
    r = d2 / d1
    r = np.where(r <= 1.0, 1.0 + EPS, r).astype(np.float64)
    log_r = np.log(r)
    # Per-thread MLE: d_hat = N_thread / sum(log_r over thread's turns).
    sums: dict[str, float] = {}
    counts: dict[str, int] = {}
    for i, tid in enumerate(tids):
        sums[tid] = sums.get(tid, 0.0) + float(log_r[i])
        counts[tid] = counts.get(tid, 0) + 1
    # Cap LID at 50.0 (tick #54). The TwoNN MLE diverges when d1
    # approaches d2 — near-duplicate-embedding pairs produce LID
    # estimates in the millions (observed on real corpus: 1,048,576).
    # Those values are noise, not signal. The literature's typical
    # range for fluent human prose is ~9 (NeurIPS 2023); 50 keeps the
    # high tail loosely informative without letting outliers dominate.
    LID_CAP = 50.0
    # Minimum turn count for TwoNN to be statistically meaningful
    # (tick #84). Below this the MLE is dominated by one or two
    # ratios — usually saturates at LID_CAP for any pair where
    # d2/d1 is moderately large. Tick #84 ran depth_score on the
    # real 18k-prompt corpus and found 6 of the top-10 "surprising"
    # threads were 2-turn threads with capped LID — pure artifact,
    # not signal. Excluding short threads from LID forces the
    # composite to rank by corpus_distance + inter_turn, which IS
    # signal even on short threads. The literature's TwoNN papers
    # all use n≥5 as the minimum for stable estimates.
    LID_MIN_TURNS = 5
    out: dict[str, float] = {}
    for tid in set(tids):
        s = sums.get(tid, 0.0)
        n = counts.get(tid, 0)
        if n < LID_MIN_TURNS or s <= 0:
            # Under the minimum, return 0 — the composite drops the
            # LID term entirely for short threads. Better than
            # returning LID_CAP, which silently injects a fake +0.5
            # via tanh(50/10) into every short thread's depth_score.
            out[tid] = 0.0
        else:
            out[tid] = min(n / s, LID_CAP)
    return out


# Weights for the depth_score composite. corpus_distance is the
# literature's strongest single signal (TAD-Bench, scientific-doc
# novelty), so it gets the dominant weight. inter_turn and LID are
# bonuses that lift multi-turn / high-LID threads above ties on
# corpus_distance alone. Tunable, but defaults are well-grounded:
# corpus ∈ [0, 2], log(1+inter) ∈ [0, ~1.1], tanh(LID/10) ∈ [0, ~1]
# — so the weighted sum sits in roughly [0, 3.5].
_DEPTH_WEIGHT_CORPUS = 1.0
_DEPTH_WEIGHT_INTER_TURN = 0.5
_DEPTH_WEIGHT_LID = 0.5


def depth_score(
    nodes: Iterable[PromptNode],
) -> dict[str, float]:
    """Weighted-additive per-thread depth signal.

    score = 1.0 * corpus_distance
          + 0.5 * log(1 + inter_turn_distance)
          + 0.5 * tanh(LID / 10)

    Each component is individually peer-reviewed for the role it plays:
      - corpus_distance: novelty (TAD-Bench)
      - inter_turn_distance: thread moved through semantic space
        (Dialogue Telemetry's Stalling Index, inverted)
      - LID: thread sampled independent axes (TwoNN; NeurIPS 2023)

    **Why additive, not multiplicative (changed tick #54):** the
    multiplicative shape collapsed to 0 for single-turn threads
    because log(1 + 0) = 0. On a real 4380-thread install most
    threads were single-turn (claude.ai exports / gemini takeout
    flatten to 1 turn each), so the depth ranking was useless. The
    additive shape lets a single-turn outlier rank by corpus_distance
    alone; the bonus terms lift multi-turn rich threads above ties
    rather than gating the score.

    tanh(LID/10) replaces log(1 + LID) so noise from near-duplicate
    embeddings (which the LID_CAP also bounds) can't dominate; tanh
    saturates around 1.0 for LID ≥ 20.

    Caller pulls components via the dedicated functions above if
    they need a single signal in isolation.
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
        out[tid] = (
            _DEPTH_WEIGHT_CORPUS * c
            + _DEPTH_WEIGHT_INTER_TURN * math.log(1.0 + i)
            + _DEPTH_WEIGHT_LID * math.tanh(l / 10.0)
        )
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
