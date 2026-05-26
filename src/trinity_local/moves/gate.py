"""Four-tier Bayesian gate for moves — scaffolding.

The promotion + demotion logic for moves. Each tier is a function that
returns a TierResult (pass/fail + score + reason). Tiers run in order:
T1 → T2 → T3 → T4. Earlier tiers act as priors that filter candidates
before the expensive likelihood (T3) runs.

Tier ownership map (task #s):
  T1 (lexical prior)         — task #168
  T2 (embedding prior)       — task #168
  T3 (chairman eval)         — task #169
  T4 (live Bayesian posterior) — task #170

This module ships the SCAFFOLDING — function signatures + dispatcher
shape + the TierResult dataclass — so the moves substrate (#167) is
complete enough that #168-#170 are pure-implementation deltas. The
gate functions here raise NotImplementedError; downstream tasks fill
them in without changing the surface.

The full spec: docs/PREFERENCE_CORPUS_SPEC.md "Eval-gated promotion —
the Bayesian gate (the wedge)".
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .schemas import Move


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
) -> TierResult:
    """Cheap structural prior: n-gram Jaccard similarity vs accepted
    patterns in the candidate's claimed basin.

    Passes iff the candidate's body/description has Jaccard ≥ threshold
    against at least `min_matches` accepted patterns. Cost: ~1ms.

    Implemented in task #168.
    """
    raise NotImplementedError("T1_lexical: implement in task #168")


def T2_embedding(
    candidate: Move,
    basin_centroid: list[float] | None,
    *,
    threshold: float = 0.7,
) -> TierResult:
    """Geometric basin membership: cosine similarity of the candidate's
    embedding vs the basin centroid.

    Passes iff cosine ≥ threshold. Cost: ~10ms (one embedding call
    via the existing embeddings backend).

    Implemented in task #168.
    """
    raise NotImplementedError("T2_embedding: implement in task #168")


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
