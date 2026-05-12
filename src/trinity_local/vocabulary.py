"""Phase 2.5 — vocabulary distillation.

Reads ~/.trinity/memory/prompt_nodes.jsonl and emits
~/.trinity/memories/vocabulary.md — the user's terminology overlay.

Two flavors of overload detected geometrically (no LLM call):

1. **Homonyms** (one word → two meanings): tokens whose context-embedding
   distribution spreads across multiple regions of embedding space. Detected
   by the variance ratio between two clusters of the token's prompt
   embeddings — a high split-variance ratio signals the same token sitting in
   two semantic contexts.

2. **Synonyms** (two words → one meaning): pairs of distinct tokens whose
   mean context embeddings are cosine-similar above threshold. Each token's
   "mean context" is the centroid of every prompt embedding the token appears
   in. Near-identical centroids → the words are used in the same semantic
   territory.

The same machinery the cortex layer uses (bimodality flagging via geometric
prior) applied to the user's own terminology. Pure numpy; no chairman call;
runs ~1s on a 5k-prompt index.

Output schema is markdown, intentionally human-legible — chairman reads
vocabulary.md as one of the five plural core memories before synthesizing.
"""
from __future__ import annotations

import math
import re
from collections import defaultdict
from pathlib import Path
from typing import Iterable


# Conservative defaults — surface only the most-overloaded terms; first run
# on a real corpus showed ~12 surfaces is the right ballpark before noise
# starts dominating signal.
DEFAULT_MIN_FREQ = 5
DEFAULT_TOP_HOMONYMS = 10
DEFAULT_TOP_SYNONYMS = 10
DEFAULT_SYNONYM_COSINE_THRESHOLD = 0.92

# Stopwords kept tight — only words a developer would reflexively skip,
# nothing that could plausibly be a load-bearing term. The whole point is
# to surface YOUR vocabulary, not strip it down to nouns.
_STOPWORDS = frozenset(
    """
    a an and are as at be but by for if in into is it no not of on or
    such that the their then there these they this to was were will with
    you your i me my we us our they them their it its he she his her
    so do does did just very also only really maybe just like get got
    have has had can could would should might must may
    """.split()
)

_TOKEN_RX = re.compile(r"[a-zA-Z][a-zA-Z_-]{2,}")  # 3+ chars, alpha/_/-, alpha start


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RX.findall(text or "") if t.lower() not in _STOPWORDS]


def _l2_normalize(vec):
    import numpy as np
    norm = np.linalg.norm(vec)
    return vec / norm if norm > 0 else vec


def _two_means_split_variance(vectors, *, max_samples: int = 200) -> float:
    """K=2 split silhouette — bimodality score on [0, 1].

    Single-pass two-means seeded by the two farthest-apart points, then
    silhouette: mean per-point (b - a) / max(a, b) where a = mean distance
    to own cluster, b = mean distance to other cluster.

    - Unimodal (tight homogeneous cluster, forced split): silhouette ≈ 0.
    - Bimodal (real two-cluster structure): silhouette ≈ 0.7+.

    Pure numpy, no scipy/sklearn. Caps inputs at `max_samples` because
    the pairwise distance matrices are O(n²·d) memory — a token appearing
    in 5000 prompts with 768-d embeddings would otherwise allocate
    ~19GB. 200 samples is comfortably above the statistical floor for
    "is this bimodal or not."
    """
    import numpy as np
    n = len(vectors)
    if n < 4:
        return 0.0
    # Subsample large context sets — distance-matrix memory is O(n²·d).
    # Deterministic by stride so repeated runs return the same score.
    if n > max_samples:
        idx = np.linspace(0, n - 1, max_samples, dtype=int)
        vectors = [vectors[i] for i in idx]
        n = len(vectors)
    arr = np.asarray(vectors, dtype=float)
    # Seed centroids: two farthest-apart points.
    if n <= 50:
        diffs = arr[:, None, :] - arr[None, :, :]
        dists = np.linalg.norm(diffs, axis=-1)
        i, j = divmod(int(dists.argmax()), n)
    else:
        idx = np.linspace(0, n - 1, 50, dtype=int)
        sub = arr[idx]
        diffs = sub[:, None, :] - sub[None, :, :]
        dists = np.linalg.norm(diffs, axis=-1)
        ii, jj = divmod(int(dists.argmax()), 50)
        i, j = int(idx[ii]), int(idx[jj])
    c1, c2 = arr[i], arr[j]
    d1 = np.linalg.norm(arr - c1, axis=1)
    d2 = np.linalg.norm(arr - c2, axis=1)
    a1_mask = d1 <= d2
    if a1_mask.sum() < 2 or (~a1_mask).sum() < 2:
        return 0.0
    g1 = arr[a1_mask]
    g2 = arr[~a1_mask]

    # Silhouette: for each point, compute a (avg dist to own cluster) and
    # b (avg dist to other cluster). Vectorize via pairwise-distance matrices.
    def _pairwise(a, b):
        return np.linalg.norm(a[:, None, :] - b[None, :, :], axis=-1)
    d11 = _pairwise(g1, g1)
    d22 = _pairwise(g2, g2)
    d12 = _pairwise(g1, g2)
    # Own-cluster mean excludes self → divide by (n-1).
    a_g1 = (d11.sum(axis=1) / max(len(g1) - 1, 1))
    a_g2 = (d22.sum(axis=1) / max(len(g2) - 1, 1))
    b_g1 = d12.mean(axis=1)
    b_g2 = d12.mean(axis=0)
    s_g1 = (b_g1 - a_g1) / np.maximum(a_g1, b_g1).clip(min=1e-12)
    s_g2 = (b_g2 - a_g2) / np.maximum(a_g2, b_g2).clip(min=1e-12)
    silhouette = float(np.concatenate([s_g1, s_g2]).mean())  # in [-1, 1]
    # Unimodal (tight cluster, forced k=2 split): silhouette ≈ 0.
    # Bimodal (genuine 2-cluster structure): silhouette ≈ 0.7–1.0.
    # Clip negatives to 0 (means clusters are worse than no clustering — not
    # bimodal). Threshold heuristic for callers: ≥0.5 = bimodal candidate.
    return max(0.0, min(1.0, silhouette))


def _gather_token_contexts(nodes: Iterable, *, min_freq: int) -> dict[str, list]:
    """Map token → list of embeddings from prompts where the token appears.

    Only tokens appearing in ≥ min_freq distinct prompts are kept (cheap
    filter against the long tail of one-off typos).
    """
    contexts: dict[str, list] = defaultdict(list)
    for node in nodes:
        emb = getattr(node, "embedding", None)
        if not emb:
            continue
        text = getattr(node, "text", "") or ""
        for tok in set(_tokenize(text)):
            contexts[tok].append(emb)
    return {tok: vecs for tok, vecs in contexts.items() if len(vecs) >= min_freq}


def find_homonyms(token_contexts: dict[str, list], *, top_n: int) -> list[tuple[str, float, int]]:
    """Rank tokens by k=2 bimodality score over their context embeddings.

    Returns [(token, score, n_contexts), ...] descending by score, top_n only.
    """
    scored: list[tuple[str, float, int]] = []
    for tok, vecs in token_contexts.items():
        score = _two_means_split_variance(vecs)
        scored.append((tok, score, len(vecs)))
    scored.sort(key=lambda r: r[1], reverse=True)
    return scored[:top_n]


def find_synonyms(
    token_contexts: dict[str, list], *, top_n: int, threshold: float
) -> list[tuple[str, str, float, int, int]]:
    """Rank token pairs by cosine similarity of their mean context embedding.

    Returns [(token_a, token_b, cos_sim, n_a, n_b), ...] descending by sim,
    top_n only. Only pairs above `threshold` are returned.
    """
    import numpy as np
    tokens = sorted(token_contexts.keys())
    if len(tokens) < 2:
        return []
    means = np.stack([
        _l2_normalize(np.asarray(token_contexts[t]).mean(axis=0)) for t in tokens
    ])
    sims = means @ means.T  # cosine since each row is L2-normalized
    pairs: list[tuple[str, str, float, int, int]] = []
    for i in range(len(tokens)):
        for j in range(i + 1, len(tokens)):
            sim = float(sims[i, j])
            # Guard NaN/inf: a zero-norm mean vector slips through
            # _l2_normalize (returns unnormalized), and `nan < threshold`
            # is False — without this check, NaN pairs would leak into
            # the output.
            if not np.isfinite(sim):
                continue
            if sim < threshold:
                continue
            pairs.append((
                tokens[i], tokens[j], sim,
                len(token_contexts[tokens[i]]), len(token_contexts[tokens[j]]),
            ))
    pairs.sort(key=lambda r: r[2], reverse=True)
    return pairs[:top_n]


def render_vocabulary_md(
    *, homonyms: list[tuple[str, float, int]],
    synonyms: list[tuple[str, str, float, int, int]],
    corpus_size: int,
) -> str:
    """Compose the markdown output. Chairman reads it as one of the five
    plural core memories — keep it human-legible, no JSON dump."""
    lines = [
        "# Your vocabulary",
        "",
        "*Pure-geometric scan of your prompt corpus. Two flavors of terminology",
        "overload, surfaced as one of your five core memories.*",
        "",
        f"_Scanned {corpus_size} prompts. Tokens require ≥5 occurrences to qualify._",
        "",
        "## Homonyms — one word, multiple meanings",
        "",
    ]
    if homonyms:
        lines.append("Words you use across distinct semantic contexts. Each row: token, bimodality score (0–1), times used.")
        lines.append("")
        lines.append("| token | bimodality | uses |")
        lines.append("|---|---|---|")
        for tok, score, n in homonyms:
            lines.append(f"| `{tok}` | {score:.2f} | {n} |")
    else:
        lines.append("_(none yet — your terms are sitting in coherent contexts)_")
    lines.append("")
    lines.append("## Synonyms — multiple words, one meaning")
    lines.append("")
    if synonyms:
        lines.append("Pairs of distinct tokens whose context vectors are near-identical — candidates for unification.")
        lines.append("")
        lines.append("| token A | token B | cosine | uses A | uses B |")
        lines.append("|---|---|---|---|---|")
        for a, b, sim, na, nb in synonyms:
            lines.append(f"| `{a}` | `{b}` | {sim:.3f} | {na} | {nb} |")
    else:
        lines.append("_(none yet — your tokens occupy distinct semantic regions)_")
    lines.append("")
    return "\n".join(lines)


def distill_vocabulary(
    *,
    min_freq: int = DEFAULT_MIN_FREQ,
    top_homonyms: int = DEFAULT_TOP_HOMONYMS,
    top_synonyms: int = DEFAULT_TOP_SYNONYMS,
    synonym_threshold: float = DEFAULT_SYNONYM_COSINE_THRESHOLD,
) -> dict:
    """End-to-end Phase 2.5: scan corpus → emit vocabulary.md.

    Returns a report dict (`{ok, path, homonyms, synonyms, corpus_size}`).
    Returns `skipped: True` cleanly when no embedded prompts exist yet.

    Uses `iter_prompt_nodes(limit=None)` to walk the full corpus. The
    default `iter_prompt_nodes()` caps at 5000 most-recent nodes (hot
    path for launchpad/search), but recent ingest skips embedding to keep
    that path fast — so embeddings sit on the older seeded prompts BELOW
    the cap. `limit=None` lifts the cap and is cached in-process by file
    mtime, so dream/vocabulary/basins all share the parse cost.
    """
    from .memory.store import iter_prompt_nodes
    from .state_paths import vocabulary_path

    nodes = list(iter_prompt_nodes(limit=None))
    nodes_with_emb = [n for n in nodes if getattr(n, "embedding", None)]
    if not nodes_with_emb:
        return {
            "ok": False, "skipped": True,
            "reason": "no embedded prompts yet — run `seed-from-taste-terminal` first",
        }

    contexts = _gather_token_contexts(nodes_with_emb, min_freq=min_freq)
    if not contexts:
        return {
            "ok": False, "skipped": True,
            "reason": f"no tokens meet min_freq={min_freq}; corpus too small or too sparse",
        }

    homonyms = find_homonyms(contexts, top_n=top_homonyms)
    synonyms = find_synonyms(contexts, top_n=top_synonyms, threshold=synonym_threshold)
    md = render_vocabulary_md(
        homonyms=homonyms, synonyms=synonyms, corpus_size=len(nodes_with_emb),
    )
    path = vocabulary_path()
    path.write_text(md, encoding="utf-8")
    return {
        "ok": True,
        "path": str(path),
        "corpus_size": len(nodes_with_emb),
        "tokens_scanned": len(contexts),
        "homonyms_emitted": len(homonyms),
        "synonyms_emitted": len(synonyms),
    }
