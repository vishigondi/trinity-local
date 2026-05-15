"""Phase 2.5 — vocabulary distillation.

Reads ~/.trinity/memory/prompt_nodes.jsonl and emits
~/.trinity/memories/vocabulary.md — the user's terminology overlay.

Three flavors of distinctive terminology surfaced (no LLM call):

1. **Anchors** (proper-noun recurrence): capitalized multi-word entities the
   user names across ≥3 distinct conversation threads. Pure regex + thread
   count; surfaces the projects/people/products that thread through the
   user's thinking but get stopword-stripped by the lowercase tokenizer.

2. **Homonyms** (one word → two meanings): tokens whose context-embedding
   distribution spreads across multiple regions of embedding space. Detected
   by the variance ratio between two clusters of the token's prompt
   embeddings — a high split-variance ratio signals the same token sitting in
   two semantic contexts.

3. **Synonyms** (two words → one meaning): pairs of distinct tokens whose
   mean context embeddings are cosine-similar above threshold. Each token's
   "mean context" is the centroid of every prompt embedding the token appears
   in. Near-identical centroids → the words are used in the same semantic
   territory.

The same machinery the cortex layer uses (bimodality flagging via geometric
prior) applied to the user's own terminology. Pure numpy; no chairman call;
runs ~1s on a 5k-prompt index.

Output schema is markdown, intentionally human-legible — chairman reads
vocabulary.md as one of the three thinking core memories before synthesizing.
"""
from __future__ import annotations

import re
from collections import defaultdict
from typing import Iterable

from .embeddings import is_finite_embedding


# Conservative defaults — surface only the most-overloaded terms; first run
# on a real corpus showed ~12 surfaces is the right ballpark before noise
# starts dominating signal.
DEFAULT_MIN_FREQ = 5
DEFAULT_TOP_HOMONYMS = 10
DEFAULT_TOP_SYNONYMS = 10
DEFAULT_TOP_ANCHORS = 15
DEFAULT_ANCHOR_MIN_THREADS = 3
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

# Anchors: capitalized words optionally chained with internal lowercase + hyphens
# (Trinity, GitHub, Sakana TRINITY, Claude Code). The runs of single capitalized
# tokens are merged at extraction time when adjacent in source text.
_PROPER_TOKEN_RX = re.compile(r"\b([A-Z][a-zA-Z][a-zA-Z0-9_-]*(?:\s+[A-Z][a-zA-Z][a-zA-Z0-9_-]*){0,3})\b")

# Words common at sentence start that aren't real anchors — filtered out
# because they always capitalize but rarely refer to entities.
_ANCHOR_BLACKLIST = frozenset({
    "the", "this", "that", "these", "those", "there", "here",
    "what", "when", "where", "which", "who", "why", "how",
    "i", "you", "we", "they", "he", "she", "it", "my", "your",
    "but", "and", "or", "so", "if", "yes", "no", "not",
    "can", "could", "would", "should", "will", "may", "might",
    "is", "are", "was", "were", "be", "been", "being",
    "do", "does", "did", "have", "has", "had",
    "ok", "okay", "well", "now", "then", "just", "let", "lets",
})


def _tokenize(text: str) -> list[str]:
    return [t.lower() for t in _TOKEN_RX.findall(text or "") if t.lower() not in _STOPWORDS]


def _extract_proper_phrases(text: str) -> list[str]:
    """Pull capitalized multi-word entity candidates from text.

    Lowercases the first word against the blacklist (catches "The …" /
    "When …" sentence starts that wear capital letters but aren't anchors).
    Returns the raw matched phrases — caller decides what counts.
    """
    out: list[str] = []
    if not text:
        return out
    for raw in _PROPER_TOKEN_RX.findall(text):
        phrase = raw.strip()
        if not phrase:
            continue
        first = phrase.split()[0].lower()
        if first in _ANCHOR_BLACKLIST:
            # Strip a sentence-start blacklisted word; keep rest only if it
            # still has ≥1 capitalized token left.
            rest = phrase.split(maxsplit=1)
            if len(rest) < 2:
                continue
            phrase = rest[1]
        out.append(phrase)
    return out


def find_anchors(
    nodes: Iterable, *, min_threads: int, top_n: int,
) -> list[tuple[str, int, int]]:
    """Rank proper-noun phrases by distinct-thread count.

    Returns [(phrase, n_threads, n_mentions), ...] descending by thread
    recurrence then mention count. Filters to phrases appearing in
    ≥ min_threads distinct transcripts — the recurrence signal is what
    makes a token an anchor instead of a one-off proper noun.
    """
    # phrase → {transcript_ids}, mention count
    threads: dict[str, set] = defaultdict(set)
    mentions: dict[str, int] = defaultdict(int)
    for node in nodes:
        text = getattr(node, "text", "") or ""
        tid = getattr(node, "transcript_id", None) or getattr(node, "id", None)
        for phrase in _extract_proper_phrases(text):
            threads[phrase].add(tid)
            mentions[phrase] += 1
    ranked = [
        (phrase, len(tids), mentions[phrase])
        for phrase, tids in threads.items()
        if len(tids) >= min_threads
    ]
    # Sort by (thread recurrence DESC, mention count DESC). Recurrence first
    # because "appeared in 8 different conversations" is the load-bearing
    # signal — anchors are projects/people, not single-thread mentions.
    ranked.sort(key=lambda r: (-r[1], -r[2]))
    return ranked[:top_n]


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
        # NaN-or-Inf embeddings poison the k=2 silhouette downstream
        # (numpy distance computations propagate NaN). Same shape as
        # the filter in me/depth.py and me/basins.py.
        if not is_finite_embedding(emb):
            continue
        text = getattr(node, "text", "") or ""
        for tok in set(_tokenize(text)):
            contexts[tok].append(emb)
    return {tok: vecs for tok, vecs in contexts.items() if len(vecs) >= min_freq}


def find_homonyms(token_contexts: dict[str, list], *, top_n: int) -> list[tuple[str, float, int]]:
    """Rank tokens by k=2 bimodality score over their context embeddings.

    Returns [(token, score, n_contexts), ...] descending by score, top_n only.

    Ranking detail — silhouette saturates at 1.0 for genuinely bimodal
    tokens, so on a real corpus the top is `code`, `find`, `which` —
    common verbs that legitimately span many contexts but are too
    generic to surface as actionable overloads. We secondary-sort by
    INVERSE frequency: among tokens with equally-high bimodality,
    prefer the rarer one. Domain-specific overloads ("react", "lens",
    "thread") rank above generic English ("which", "find") even when
    their raw scores are identical.
    """
    scored: list[tuple[str, float, int]] = []
    for tok, vecs in token_contexts.items():
        score = _two_means_split_variance(vecs)
        scored.append((tok, score, len(vecs)))
    # Sort by (bimodality DESC, frequency ASC) — high score + rare = most
    # actionable. `-len(vecs)` would put high-frequency on top; we want the
    # OPPOSITE so the secondary key is len(vecs) ascending.
    scored.sort(key=lambda r: (-r[1], r[2]))
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
    anchors: list[tuple[str, int, int]],
    corpus_size: int,
) -> str:
    """Compose the markdown output. Chairman reads it as one of the three
    thinking core memories — keep it human-legible, no JSON dump."""
    lines = [
        "# Your vocabulary",
        "",
        "*Pure-geometric scan of your prompt corpus. Three views of distinctive",
        "terminology — anchors, homonyms, synonyms — surfaced as one of your",
        "three thinking core memories.*",
        "",
        f"_Scanned {corpus_size} prompts. Tokens require ≥5 occurrences; anchors require ≥3 distinct threads._",
        "",
        "## Anchors — proper nouns you return to across threads",
        "",
    ]
    if anchors:
        lines.append("Projects, people, products, and named ideas that recur across distinct conversations. Each row: anchor, distinct threads, total mentions.")
        lines.append("")
        lines.append("| anchor | threads | mentions |")
        lines.append("|---|---|---|")
        for phrase, n_threads, n_mentions in anchors:
            lines.append(f"| {phrase} | {n_threads} | {n_mentions} |")
    else:
        lines.append("_(none yet — no capitalized phrase recurs across enough distinct threads)_")
    lines.append("")
    lines.append("## Homonyms — one word, multiple meanings")
    lines.append("")
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
    top_anchors: int = DEFAULT_TOP_ANCHORS,
    anchor_min_threads: int = DEFAULT_ANCHOR_MIN_THREADS,
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
    # Anchors run on the FULL node set (not just embedded ones) — proper-noun
    # recurrence is pure-text and benefits from every transcript we have.
    # Doesn't share the embedding/min_freq gate; can surface signal even when
    # the corpus is too sparse for k=2 silhouette to be meaningful.
    anchors = find_anchors(nodes, min_threads=anchor_min_threads, top_n=top_anchors)
    if not contexts and not anchors:
        return {
            "ok": False, "skipped": True,
            "reason": f"no tokens meet min_freq={min_freq} and no anchors meet min_threads={anchor_min_threads}; corpus too small or too sparse",
        }

    homonyms = find_homonyms(contexts, top_n=top_homonyms) if contexts else []
    synonyms = find_synonyms(contexts, top_n=top_synonyms, threshold=synonym_threshold) if contexts else []
    md = render_vocabulary_md(
        homonyms=homonyms, synonyms=synonyms, anchors=anchors,
        corpus_size=len(nodes_with_emb),
    )
    path = vocabulary_path()
    path.write_text(md, encoding="utf-8")
    return {
        "ok": True,
        "path": str(path),
        "corpus_size": len(nodes_with_emb),
        "tokens_scanned": len(contexts),
        "anchors_emitted": len(anchors),
        "homonyms_emitted": len(homonyms),
        "synonyms_emitted": len(synonyms),
    }
