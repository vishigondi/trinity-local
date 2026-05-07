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
    size: int
    top_terms: list[str]
    centroid: list[float]
    prompt_ids: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "size": self.size,
            "top_terms": self.top_terms,
            "centroid": self.centroid,
            "prompt_ids": self.prompt_ids[:50],  # cap for readable JSON
        }


def me_dir() -> Path:
    """Output directory for lens-discovery artifacts."""
    path = state_dir() / "me"
    path.mkdir(parents=True, exist_ok=True)
    return path


def basins_path() -> Path:
    return me_dir() / "basins.json"


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
    """Cluster all PromptNode embeddings into k basins.

    Skips nodes without embeddings. Returns sorted by descending size so
    the most prevalent basin is b00.
    """
    try:
        import numpy as np
    except ImportError as exc:
        raise RuntimeError("numpy is required for basin clustering") from exc

    nodes = []
    embeddings = []
    texts = []
    skipped_nan = 0
    for node in iter_prompt_nodes():
        emb = getattr(node, "embedding", None)
        if not emb:
            continue
        # Skip embeddings with non-finite values — a small fraction of the
        # 18k corpus has NaN vectors (likely from a bad embed batch). They
        # poison k-means via NaN-propagating centroids, which collapses
        # every row into one cluster.
        if any(v != v or v == float("inf") or v == float("-inf") for v in emb):
            skipped_nan += 1
            continue
        nodes.append(node)
        embeddings.append(emb)
        texts.append(node.text or "")

    if not nodes:
        return []

    matrix = np.array(embeddings, dtype=np.float32)
    labels, centroids = _kmeans(matrix, k=min(k, len(nodes)), seed=seed)

    basins: list[Basin] = []
    for cluster_idx in range(len(centroids)):
        member_indices = [i for i, lbl in enumerate(labels) if lbl == cluster_idx]
        if not member_indices:
            continue
        cluster_texts = [texts[i] for i in member_indices]
        top_terms = _top_terms_for_cluster(cluster_texts, texts)
        basins.append(Basin(
            id=f"b{cluster_idx:02d}",
            size=len(member_indices),
            top_terms=top_terms,
            centroid=centroids[cluster_idx].tolist(),
            prompt_ids=[nodes[i].id for i in member_indices],
        ))
    basins.sort(key=lambda b: -b.size)
    # Rename ids in size order so b00 is always the largest.
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
