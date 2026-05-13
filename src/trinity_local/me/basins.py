"""Stage 1 — topology via numpy k-means over PromptNode embeddings.

Produces ~20 basins per `me-build`. Each basin carries:
- id (b00..bNN)
- size (count of prompts in cluster)
- top_terms (top-3 TF-IDF residual phrases vs full corpus)
- centroid (768d numpy vector)
- prompt_ids (sample for stage 2 to walk)

Two consumers:
1. Stage 2 tags each extracted decision with its basin id.
2. Stage 4 post-filter drops accepted pairs whose tension evidence
   all sits in a single basin (topic-local virtue, not real lens).

NOT a chairman input — the council ratified that passing basin ids
through the prompt is dead-code-prone unless deterministic code uses
them. Per-decision tagging + post-filter together fix that.
"""

from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..memory.store import iter_prompt_nodes
from ..state_paths import state_dir


_DEFAULT_K = 20
_DEFAULT_SEED = 42
_TOP_TERMS_PER_BASIN = 3
# Stop words that crowd out distinctive vocabulary in tiny corpora.
_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "if", "is", "are", "was", "were",
    "be", "been", "being", "of", "to", "in", "on", "at", "for", "with",
    "by", "from", "as", "this", "that", "these", "those", "it", "its",
    "i", "you", "he", "she", "we", "they", "me", "us", "them", "my",
    "your", "his", "her", "our", "their", "do", "does", "did", "have",
    "has", "had", "will", "would", "should", "could", "can", "may",
    "might", "must", "shall", "not", "no", "yes", "so", "up", "out",
    "about", "over", "than", "then", "there", "what", "when", "where",
    "who", "how", "why", "all", "any", "some", "each", "every", "more",
    "most", "less", "least", "very", "just", "only", "also", "even",
    "still", "yet", "now", "here", "into", "onto", "upon", "off",
    "down", "back", "again", "before", "after", "during", "while",
    "because", "though", "although", "since", "until", "unless",
}


@dataclass
class Basin:
    id: str
    size: int   # total turn count across all threads in this basin
    top_terms: list[str]
    centroid: list[float]
    prompt_ids: list[str] = field(default_factory=list)
    # Top-K threads closest to the basin centroid — the most semantically
    # representative conversations. Per-thread shape:
    #   {transcript_id, turn_count, headline, turns: [{id, snippet, turn_index}]}
    # Stored under `representatives` for backward-compat with the older
    # per-turn shape; the viewer detects the new shape by the presence of
    # `transcript_id` + `turns`.
    representatives: list[dict[str, Any]] = field(default_factory=list)
    # NEW for thread-aware topology: how many distinct sessions (threads)
    # landed in this basin. `size` is the total turn count.
    thread_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        # No truncation on prompt_ids. Earlier code capped at 50 "for readable
        # JSON" — but `load_basins()` round-trips the file back into Basin
        # dataclasses, and `basin_for_prompt(basins, id)` checks membership
        # against the loaded list. With a 50-id cap, any prompt beyond the
        # first 50 in a basin was silently mis-tagged as "no basin" after
        # the round-trip, breaking Stage 2/4 of the lens pipeline. Keeping
        # the full list keeps topics.json a faithful serialization.
        return {
            "id": self.id,
            "size": self.size,
            "thread_count": self.thread_count,
            "top_terms": self.top_terms,
            "centroid": self.centroid,
            "prompt_ids": self.prompt_ids,
            "representatives": self.representatives,
        }


def me_dir() -> Path:
    """Output directory for lens-discovery artifacts."""
    path = state_dir() / "me"
    path.mkdir(parents=True, exist_ok=True)
    return path


def basins_path() -> Path:
    """The topology file. Renamed from `me/basins.json` → `memories/topics.json`
    per the brand axis (topics = semantic memory; basins was math-jargon).
    Migration handled by state_paths.memories_dir() on first access."""
    from ..state_paths import topics_path
    return topics_path()


def _kmeans_pp_init(matrix, k: int, seed: int):
    """Pure-numpy k-means++ centroid init. Deterministic with seed."""
    import numpy as np

    rng = np.random.default_rng(seed)
    n, _ = matrix.shape
    first = int(rng.integers(0, n))
    centroids = [matrix[first]]
    for _ in range(1, k):
        diffs = matrix[:, None, :] - np.array(centroids)[None, :, :]
        sq_dists = np.sum(diffs * diffs, axis=2).min(axis=1)
        total = sq_dists.sum()
        if not np.isfinite(total) or total <= 0:
            # All remaining points are exactly on existing centroids
            # (duplicate embeddings). Fall back to uniform random.
            next_idx = int(rng.integers(0, n))
        else:
            probs = sq_dists / total
            # Replace any NaN that slipped through (extreme float edge cases)
            probs = np.nan_to_num(probs, nan=0.0)
            if probs.sum() <= 0:
                next_idx = int(rng.integers(0, n))
            else:
                probs = probs / probs.sum()
                next_idx = int(rng.choice(n, p=probs))
        centroids.append(matrix[next_idx])
    return np.array(centroids)


def _kmeans(matrix, k: int = _DEFAULT_K, *, seed: int = _DEFAULT_SEED, max_iter: int = 50):
    """Lightweight k-means. Returns (labels, centroids)."""
    import numpy as np

    n, _ = matrix.shape
    if n <= k:
        # Degenerate: each row is its own cluster.
        labels = np.arange(n)
        return labels, matrix.copy()
    centroids = _kmeans_pp_init(matrix, k, seed)
    labels = np.zeros(n, dtype=int)
    for _ in range(max_iter):
        diffs = matrix[:, None, :] - centroids[None, :, :]
        sq_dists = np.sum(diffs * diffs, axis=2)
        new_labels = np.argmin(sq_dists, axis=1)
        if (new_labels == labels).all():
            break
        labels = new_labels
        for c in range(k):
            members = matrix[labels == c]
            if len(members) > 0:
                centroids[c] = members.mean(axis=0)
    return labels, centroids


def _top_terms_for_cluster(texts: list[str], all_texts: list[str], top_n: int = _TOP_TERMS_PER_BASIN) -> list[str]:
    """TF-IDF residual: terms common in cluster but rare globally."""
    cluster_words = Counter()
    global_words = Counter()
    for text in texts:
        for w in re.findall(r"[a-zA-Z][a-zA-Z\-_]{2,}", text.lower()):
            if w in _STOPWORDS:
                continue
            cluster_words[w] += 1
    for text in all_texts:
        for w in re.findall(r"[a-zA-Z][a-zA-Z\-_]{2,}", text.lower()):
            if w in _STOPWORDS:
                continue
            global_words[w] += 1
    if not cluster_words:
        return []
    cluster_size = max(sum(cluster_words.values()), 1)
    global_size = max(sum(global_words.values()), 1)
    scored: list[tuple[str, float]] = []
    for word, count in cluster_words.most_common(50):
        cluster_freq = count / cluster_size
        global_freq = global_words.get(word, 0) / global_size
        # Residual: how much more frequent in cluster than globally.
        residual = cluster_freq - global_freq
        if residual > 0:
            scored.append((word, residual))
    scored.sort(key=lambda x: -x[1])
    return [w for w, _ in scored[:top_n]]


def compute_basins(*, k: int = _DEFAULT_K, seed: int = _DEFAULT_SEED) -> list[Basin]:
    """Cluster threads (sessions) into k basins.

    Each thread's centroid is the mean embedding of its turns. We cluster
    threads, not turns — a multi-turn conversation about tweet-drafting
    becomes ONE point in basin-space, not N points scattered across
    "drafting" / "shortening" / "polishing" basins.

    Single-turn sources (Gemini Takeout) naturally become threads of
    size 1 — same code path, no special casing.

    Skips nodes without embeddings. Returns basins sorted by total turn
    count descending so b00 is the most prevalent.
    """
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("numpy is required for basin clustering") from exc

    # Use `iter_prompt_nodes(limit=None)` to lift the 5000-node hot-path
    # cap. Recent ingest skips embedding to keep the launchpad/search
    # path fast, so embeddings sit on the older seeded prompts BELOW
    # the cap.
    nodes: list = []
    skipped_nan = 0
    for node in iter_prompt_nodes(limit=None):
        emb = getattr(node, "embedding", None)
        if not emb:
            continue
        # Skip embeddings with non-finite values — bad embed batches
        # poison k-means via NaN-propagating centroids.
        if any(v != v or v == float("inf") or v == float("-inf") for v in emb):
            skipped_nan += 1
            continue
        nodes.append(node)

    if not nodes:
        return []

    # Group turns by transcript_id. A missing transcript_id falls back to
    # a synthetic per-turn thread (the node's own id) so single-turn
    # sources still cluster.
    threads: dict[str, list[int]] = {}
    for idx, node in enumerate(nodes):
        tid = getattr(node, "transcript_id", None) or node.id
        threads.setdefault(tid, []).append(idx)

    thread_ids = list(threads.keys())
    thread_centroids = np.zeros((len(thread_ids), len(nodes[0].embedding)), dtype=np.float32)
    for ti, tid in enumerate(thread_ids):
        thread_centroids[ti] = np.mean(
            [nodes[i].embedding for i in threads[tid]], axis=0, dtype=np.float32,
        )

    # Cluster THREADS, not turns. `labels[ti]` is the basin id for thread `tid`.
    labels, basin_centroids = _kmeans(thread_centroids, k=min(k, len(thread_ids)), seed=seed)

    REPRESENTATIVE_K = 5
    REPRESENTATIVE_MAX_CHARS = 280
    TURNS_PER_REP = 10  # cap turns rendered per representative thread

    basins: list[Basin] = []
    for cluster_idx in range(len(basin_centroids)):
        thread_indices = [ti for ti, lbl in enumerate(labels) if lbl == cluster_idx]
        if not thread_indices:
            continue

        # All turns across all threads in this basin (for top_terms,
        # prompt_ids, total-size).
        member_turn_indices: list[int] = []
        for ti in thread_indices:
            member_turn_indices.extend(threads[thread_ids[ti]])

        cluster_texts = [(nodes[i].text or "") for i in member_turn_indices]
        all_texts = [(n.text or "") for n in nodes]
        top_terms = _top_terms_for_cluster(cluster_texts, all_texts)

        # Pick representative THREADS: closest to basin centroid in
        # thread-centroid space.
        basin_centroid = basin_centroids[cluster_idx]
        thread_distances = [
            (ti, float(np.linalg.norm(thread_centroids[ti] - basin_centroid)))
            for ti in thread_indices
        ]
        thread_distances.sort(key=lambda pair: pair[1])

        reps: list[dict[str, Any]] = []
        for ti, dist in thread_distances[:REPRESENTATIVE_K]:
            tid = thread_ids[ti]
            turn_idx_in_nodes = threads[tid]
            # Sort the thread's turns by their original turn_index so
            # the viewer renders them in conversational order.
            turn_idx_in_nodes = sorted(
                turn_idx_in_nodes,
                key=lambda i: getattr(nodes[i], "turn_index", 0),
            )
            # Headline = the single turn closest to the BASIN centroid
            # within this thread (= the turn most central to "why this
            # thread is here").
            headline_idx = min(
                turn_idx_in_nodes,
                key=lambda i: float(np.linalg.norm(
                    np.array(nodes[i].embedding, dtype=np.float32) - basin_centroid
                )),
            )

            def _snippet(text: str) -> str:
                s = (text or "").strip()
                if len(s) > REPRESENTATIVE_MAX_CHARS:
                    return s[:REPRESENTATIVE_MAX_CHARS].rstrip() + "…"
                return s

            turns_payload = [
                {
                    "id": nodes[i].id,
                    "snippet": _snippet(nodes[i].text or ""),
                    "turn_index": getattr(nodes[i], "turn_index", 0),
                }
                for i in turn_idx_in_nodes[:TURNS_PER_REP]
            ]
            reps.append({
                "transcript_id": tid,
                "turn_count": len(turn_idx_in_nodes),
                "headline": _snippet(nodes[headline_idx].text or ""),
                "turns": turns_payload,
            })

        basins.append(Basin(
            id=f"b{cluster_idx:02d}",
            size=len(member_turn_indices),  # total turn count
            thread_count=len(thread_indices),
            top_terms=top_terms,
            centroid=basin_centroids[cluster_idx].tolist(),
            prompt_ids=[nodes[i].id for i in member_turn_indices],
            representatives=reps,
        ))

    basins.sort(key=lambda b: -b.size)
    for i, basin in enumerate(basins):
        basin.id = f"b{i:02d}"
    return basins


def save_basins(basins: list[Basin]) -> Path:
    path = basins_path()
    payload = {"basins": [b.to_dict() for b in basins]}
    path.write_text(json.dumps(payload, indent=2))
    return path


def load_basins() -> list[Basin]:
    path = basins_path()
    if not path.exists():
        return []
    payload = json.loads(path.read_text())
    return [Basin(**b) for b in payload.get("basins", [])]


def basin_for_prompt(basins: list[Basin], prompt_id: str) -> str | None:
    """Lookup which basin a prompt belongs to. Used during stage 2 to
    tag each decision with its basin_id for the stage 4 post-filter."""
    for basin in basins:
        if prompt_id in basin.prompt_ids:
            return basin.id
    return None
