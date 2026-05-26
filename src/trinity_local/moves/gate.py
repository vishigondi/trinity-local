"""Four-tier Bayesian gate for moves.

The promotion + demotion logic for moves. Each tier is a function that
returns a TierResult (pass/fail + score + reason). Tiers run in order:
T1 → T2 → T3 → T4. Earlier tiers act as priors that filter candidates
before the expensive likelihood (T3) runs.

Tier ownership map:
  T1 (lexical prior)           — shipped #168 commit pending
  T2 (embedding prior)         — shipped #168 commit pending
  T3 (chairman eval)           — task #169
  T4 (live Bayesian posterior) — task #170

The full spec: docs/PREFERENCE_CORPUS_SPEC.md "Eval-gated promotion —
the Bayesian gate (the wedge)".
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

from .schemas import Move


# ─── Lexical helpers — pure stdlib, no numpy/mlx ────────────────────


_WORD_PUNCT_RE = re.compile(r"[^a-z0-9]+")


def _tokenize(text: str) -> list[str]:
    """Lowercase + strip per-word punctuation, drop empties. Stable
    across platforms (no locale-sensitive regex flags)."""
    out: list[str] = []
    for w in text.lower().split():
        cleaned = _WORD_PUNCT_RE.sub("", w)
        if cleaned:
            out.append(cleaned)
    return out


def _word_ngrams(text: str, n: int = 3) -> set[str]:
    """Word n-grams as a set of space-joined strings. Sets (not lists)
    because Jaccard wants set semantics — duplicates don't matter."""
    words = _tokenize(text)
    if len(words) < n:
        return set(words)  # short texts: fall back to unigrams
    return {" ".join(words[i:i + n]) for i in range(len(words) - n + 1)}


def _jaccard(a: set[str], b: set[str]) -> float:
    """|A ∩ B| / |A ∪ B|. Returns 0.0 when both sets are empty
    (no overlap signal extractable)."""
    if not a and not b:
        return 0.0
    union = len(a | b)
    if union == 0:
        return 0.0
    return len(a & b) / union


def _cosine(a: list[float], b: list[float]) -> float:
    """Cosine similarity between two equal-length vectors. Returns 0.0
    on zero-norm vectors (preserves the "no signal" semantic — a zero
    vector matches nothing meaningfully)."""
    if len(a) != len(b):
        raise ValueError(
            f"cosine: vectors must be same length; got {len(a)} vs {len(b)}"
        )
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0.0 or nb == 0.0:
        return 0.0
    return dot / (na * nb)


def _candidate_text(move: Move) -> str:
    """Concat description + body for embedding/n-gram input. Description
    is the load-bearing summary; body adds detail. Empty body is fine —
    description alone gives the move's intent."""
    parts = [move.description.strip()]
    if move.body.strip():
        parts.append(move.body.strip())
    return "\n\n".join(parts)


@dataclass(frozen=True)
class TierResult:
    """Outcome of running a single tier against a candidate move.

    Fields:
        tier: "T1" / "T2" / "T3" / "T4" — for logging + demotion-reason
            attribution.
        passed: did the candidate clear this tier's threshold?
        score: the numeric tier score (Jaccard / cosine / chairman /
            posterior depending on tier).
        threshold: the threshold the score was compared against.
        reason: one-line human-readable explanation. Always set;
            populated even on pass for trace logs.
    """

    tier: str
    passed: bool
    score: float
    threshold: float
    reason: str


def T1_lexical(
    candidate: Move,
    accepted_patterns: list[str],
    *,
    threshold: float = 0.3,
    min_matches: int = 3,
    n: int = 3,
) -> TierResult:
    """Cheap structural prior: word n-gram Jaccard similarity vs accepted
    patterns in the candidate's claimed basin.

    Passes iff the candidate's body/description has Jaccard ≥ threshold
    against at least `min_matches` accepted patterns. Cost: ~1ms.

    Score field: the MAX Jaccard observed (most informative single
    number for debugging "how close was the candidate to the patterns
    it failed against"). Pass criterion uses the count of patterns
    that cleared threshold — a candidate that's structurally similar
    to several accepted patterns is stronger evidence than one that's
    eerily similar to a single outlier.

    Cold-install case: when `accepted_patterns` is empty (no rejection
    corpus in this basin yet), the tier passes with score=1.0 — no
    evidence FOR the candidate, but also no evidence AGAINST. T2/T3
    do the actual gating in that case.
    """
    if not accepted_patterns:
        return TierResult(
            tier="T1",
            passed=True,
            score=1.0,
            threshold=threshold,
            reason=(
                "T1 vacuously passes: no accepted patterns to compare "
                "against in this basin yet (cold-install / new-basin "
                "case). T2/T3 do the actual gating."
            ),
        )
    cand_ngrams = _word_ngrams(_candidate_text(candidate), n=n)
    similarities = [
        _jaccard(cand_ngrams, _word_ngrams(p, n=n)) for p in accepted_patterns
    ]
    matches_above = sum(1 for s in similarities if s >= threshold)
    max_sim = max(similarities) if similarities else 0.0
    passed = matches_above >= min_matches
    return TierResult(
        tier="T1",
        passed=passed,
        score=max_sim,
        threshold=threshold,
        reason=(
            f"max Jaccard {max_sim:.3f} (need ≥ {threshold:.2f}); "
            f"{matches_above}/{len(accepted_patterns)} patterns matched "
            f"(need ≥ {min_matches})"
        ),
    )


def T2_embedding(
    candidate: Move,
    basin_centroid: list[float] | None,
    *,
    threshold: float = 0.7,
) -> TierResult:
    """Geometric basin membership: cosine similarity of the candidate's
    embedding vs the basin centroid.

    Passes iff cosine ≥ threshold. Cost: ~10ms (one embedding call
    via the existing embeddings backend — MLX when available, TF-IDF
    fallback when not).

    Cold-install case: when `basin_centroid` is None (candidate claims
    a basin that doesn't exist yet, or the topics.json hasn't been
    built), T2 fails — moves can't be promoted without a structural
    home. The dream-extension (#172) is responsible for ensuring
    every candidate's claimed basin EXISTS before invoking the gate.
    """
    if basin_centroid is None:
        return TierResult(
            tier="T2",
            passed=False,
            score=0.0,
            threshold=threshold,
            reason=(
                "T2 cannot run: no basin centroid available. The "
                "candidate's trinity_basin_id either doesn't exist in "
                "topics.json or topics.json hasn't been built yet. Run "
                "`trinity-local dream` to refresh basins, then re-run "
                "the gate."
            ),
        )
    # Embed candidate text. The embeddings backend handles MLX
    # availability + sanitization (NaN/Inf → TF-IDF fallback) at the
    # boundary, so we don't need to defend against bad vectors here.
    from ..embeddings import embed
    cand_emb = embed(_candidate_text(candidate))
    if len(cand_emb) != len(basin_centroid):
        # Defensive: dimension mismatch shouldn't happen in practice
        # (both come from the same backend) but a single bad config
        # would otherwise crash the gate. Fail loudly instead.
        return TierResult(
            tier="T2",
            passed=False,
            score=0.0,
            threshold=threshold,
            reason=(
                f"T2 dimension mismatch: candidate emb has "
                f"{len(cand_emb)} dims, basin centroid has "
                f"{len(basin_centroid)}. The embeddings backend changed "
                f"shape since topics.json was built — re-run dream."
            ),
        )
    sim = _cosine(cand_emb, basin_centroid)
    passed = sim >= threshold
    return TierResult(
        tier="T2",
        passed=passed,
        score=sim,
        threshold=threshold,
        reason=(
            f"cosine similarity {sim:.3f} vs basin centroid "
            f"(need ≥ {threshold:.2f})"
        ),
    )


def T3_chairman(
    candidate: Move,
    rejection_corpus: list[dict[str, Any]],
    *,
    baseline: float | None = None,
) -> TierResult:
    """Chairman scores the candidate against the personalized rejection
    corpus. Passes iff score ≥ baseline (or, on first promotion,
    iff score is non-empty and the baseline is set to the score).

    Cost: ~30s — the only expensive tier. Should run only on candidates
    that survived T1+T2.

    Implemented in task #169.
    """
    raise NotImplementedError("T3_chairman: implement in task #169")


def T4_posterior(move: Move) -> TierResult:
    """Live A/B posterior — Beta-Binomial via Move.posterior. Reads
    the alpha/beta on the move (updated by council_runtime when a
    council completes).

    No threshold here per se — the posterior IS the score. Caller
    decides "is the move still earning its keep" by comparing the
    posterior to the trinity_eval_baseline (or to a global floor).

    This tier is FREE because alpha/beta are updated as a side-effect
    of every council; this function just reads them.

    Implemented in task #170.
    """
    raise NotImplementedError("T4_posterior: implement in task #170")


def run_gate(
    candidate: Move,
    *,
    accepted_patterns: list[str] | None = None,
    basin_centroid: list[float] | None = None,
    rejection_corpus: list[dict[str, Any]] | None = None,
) -> list[TierResult]:
    """Run T1 → T2 → T3 sequentially, short-circuiting on first failure.

    T4 is excluded — it's only meaningful on already-promoted moves
    (alpha/beta start at the uninformative prior; the posterior is
    flat 0.5 before any council runs). Call T4_posterior() directly
    when re-evaluating active moves at dream time.

    Returns the list of TierResults in order. Each result's `passed`
    flag tells the caller whether the next tier ran.

    Wiring for #168-#170: this dispatcher stays unchanged; the tier
    functions get bodies. Tests against this signature today (with
    NotImplementedError responses) catch the wiring contract.
    """
    out: list[TierResult] = []
    # T1
    t1 = T1_lexical(candidate, accepted_patterns or [])
    out.append(t1)
    if not t1.passed:
        return out
    # T2
    t2 = T2_embedding(candidate, basin_centroid)
    out.append(t2)
    if not t2.passed:
        return out
    # T3
    t3 = T3_chairman(candidate, rejection_corpus or [])
    out.append(t3)
    return out
