"""Four-tier Bayesian gate for moves.

The promotion + demotion logic for moves. Each tier is a function that
returns a TierResult (pass/fail + score + reason). Tiers run in order:
T1 → T2 → T3 → T4. Earlier tiers act as priors that filter candidates
before the expensive likelihood (T3) runs.

Tier ownership map:
  T1 (lexical prior)           — shipped #168
  T2 (embedding prior)         — shipped #168
  T3 (chairman eval)           — task #169
  T4 (live Bayesian posterior) — shipped #170 (this file)

The full spec: docs/PREFERENCE_CORPUS_SPEC.md "Eval-gated promotion —
the Bayesian gate (the wedge)".
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass
from pathlib import Path
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


_T3_JUDGE_PROMPT = """You are scoring a candidate MOVE — a procedural pattern the user has shown a preference for — against one of the user's documented rejections.

The user's load-bearing tensions for this basin (from their personal lens — these ARE the rubric, not background context):
---
{tension_rubric}
---

REJECTION AXIS: {rejection_type}
{axis_rubric}

What the model previously gave the user that they REJECTED:
---
{rejected_response}
---

What the user's NEXT TURN looked like (their implicit correction):
---
{user_substitute}
---

Chairman's annotation of why this was a rejection:
{rubric_signal}

The candidate MOVE under evaluation — would applying this move have helped avoid the rejection?
---
NAME: {move_name}
DESCRIPTION:
{move_description}
BODY:
{move_body}
---

Output ONLY a JSON object on a single line. No prose, no markdown fences:
{{"score": <float in [0.0, 1.0]>, "reason": "<one-sentence rationale>"}}

Score 1.0 = applying this move would have prevented the rejection entirely.
Score 0.0 = the move is irrelevant or would have made the rejection worse.
0.5 = neutral / inconclusive / the move doesn't address this axis.
"""


@dataclass(frozen=True)
class LensTension:
    """One paired-tension from lens.md.

    The chairman should grade candidate moves against the tensions
    whose basin-span overlaps with the move's basin — this is the
    seed-kernel recursion edge: the chairman that judges T3 reads the
    same lens that's being trained by the chairman's own picks at T4.
    """
    pole_a: str
    pole_b: str
    pole_a_failure: str  # what pure-A looks like when it goes wrong
    pole_b_failure: str  # what pure-B looks like when it goes wrong
    basins: tuple[str, ...]  # basin IDs the tension spans


_LENS_HEADING_RE = re.compile(r"^### \d+\.\s+(.+?)\s+↔\s+(.+?)\s*$", re.MULTILINE)
_LENS_FAIL_A_RE = re.compile(r"^- Pure-(.+?) fails as: \*\*(.+?)\*\*", re.MULTILINE)
_LENS_BASINS_RE = re.compile(r"^- Tension evidence spans basins:\s*(.+?)\s*$", re.MULTILINE)


def parse_lens_tensions(lens_text: str) -> list[LensTension]:
    """Extract paired-tension records from a lens.md document.

    Lens format (from `lens-build` chairman synthesis):
        ### N. pole_a ↔ pole_b
        - Pure-pole_a fails as: **pole_a_failure**
        - Pure-pole_b fails as: **pole_b_failure**
        - Tension evidence spans basins: b00, b02

    Parser is tolerant: returns an empty list when the lens is missing
    or malformed, so T3 can fall back to the generic axis rubric.
    """
    if not lens_text:
        return []
    # Split on "### " section boundaries so per-tension parsing is bounded.
    # First section before the first heading is intro prose; skip.
    sections = re.split(r"\n(?=### \d+\.)", lens_text)
    out: list[LensTension] = []
    for sec in sections:
        sec = sec.strip()
        if not sec.startswith("### "):
            continue
        head = _LENS_HEADING_RE.search(sec)
        if not head:
            continue
        pole_a = head.group(1).strip()
        pole_b = head.group(2).strip()
        # Failure modes appear as two `- Pure-X fails as: **Y**` lines
        failures = {fail.group(1).strip(): fail.group(2).strip() for fail in _LENS_FAIL_A_RE.finditer(sec)}
        # Basins line is optional — some tensions are corpus-wide
        basins_match = _LENS_BASINS_RE.search(sec)
        basins: tuple[str, ...] = ()
        if basins_match:
            basins = tuple(
                b.strip() for b in basins_match.group(1).split(",") if b.strip()
            )
        out.append(LensTension(
            pole_a=pole_a,
            pole_b=pole_b,
            pole_a_failure=failures.get(pole_a, ""),
            pole_b_failure=failures.get(pole_b, ""),
            basins=basins,
        ))
    return out


def render_tension_rubric_for_basin(
    tensions: list[LensTension],
    basin_id: str | None,
    *,
    max_tensions: int = 3,
) -> str:
    """Render the tension rubric the chairman uses at T3.

    Selection logic:
      - If the candidate has a basin set, prefer tensions whose
        `basins` includes that basin (this is the recursion edge:
        the chairman grades against the user's documented tensions
        for the SAME basin the move targets).
      - Fall back to corpus-wide tensions (basins == ()) when no
        basin-specific tensions exist.
      - Last resort: include all tensions, capped at `max_tensions`.

    Returns a multiline string suitable for inlining into the T3
    prompt. Empty when no tensions are available (T3 falls back to
    the generic axis rubric in that case — vacuous pass remains
    correct cold-start behavior).
    """
    if not tensions:
        return ""

    if basin_id:
        scoped = [t for t in tensions if basin_id in t.basins]
        if scoped:
            tensions = scoped
        else:
            corpus_wide = [t for t in tensions if not t.basins]
            if corpus_wide:
                tensions = corpus_wide

    tensions = tensions[:max_tensions]

    lines: list[str] = []
    for t in tensions:
        lines.append(f"TENSION: {t.pole_a} ↔ {t.pole_b}")
        if t.pole_a_failure:
            lines.append(f"  Pure-{t.pole_a} fails as: {t.pole_a_failure}")
        if t.pole_b_failure:
            lines.append(f"  Pure-{t.pole_b} fails as: {t.pole_b_failure}")
        lines.append(
            "  Grade higher when the move helps the model find the "
            "load-bearing midpoint instead of collapsing to either pole."
        )
        lines.append("")
    return "\n".join(lines).strip()


def _tension_probe_text(tension: LensTension) -> str:
    """Concat a tension's poles + failure modes into one probe text.
    Used by gate-over-lens to give T1/T2 a single semantic surface
    representing the tension's full claim."""
    parts = [tension.pole_a, tension.pole_b]
    if tension.pole_a_failure:
        parts.append(tension.pole_a_failure)
    if tension.pole_b_failure:
        parts.append(tension.pole_b_failure)
    return " · ".join(p for p in parts if p)


def gate_lens_tension_in_basin(
    tension: LensTension,
    basin_id: str,
    *,
    accepted_patterns: list[str] | None = None,
    basin_centroid: list[float] | None = None,
    t1_threshold: float = 0.10,
    t2_threshold: float = 0.40,
) -> tuple[TierResult, TierResult]:
    """Apply the moves-gate T1+T2 primitives to a lens tension's claim
    that it spans `basin_id`. The kernel applying to its own substrate.

    Thresholds are looser than the moves gate (0.10 / 0.40 vs 0.30 /
    0.70) because tensions are short, abstract, and cross-domain by
    construction — their lexical/semantic overlap with concrete
    basin patterns is necessarily lower than a procedural move's.
    """
    probe = _tension_probe_text(tension)
    # T1 — lexical Jaccard
    if not accepted_patterns:
        t1 = TierResult(
            tier="T1",
            passed=True,
            score=1.0,
            threshold=t1_threshold,
            reason="T1 vacuous: basin has no accepted patterns yet",
        )
    else:
        probe_ngrams = _word_ngrams(probe, n=3)
        sims = [_jaccard(probe_ngrams, _word_ngrams(p, n=3)) for p in accepted_patterns]
        max_sim = max(sims) if sims else 0.0
        t1 = TierResult(
            tier="T1",
            passed=(max_sim >= t1_threshold),
            score=max_sim,
            threshold=t1_threshold,
            reason=f"max tension↔pattern Jaccard {max_sim:.3f}",
        )
    # T2 — centroid cosine
    if basin_centroid is None:
        t2 = TierResult(
            tier="T2",
            passed=False,
            score=0.0,
            threshold=t2_threshold,
            reason="T2 cannot run: no basin centroid",
        )
    else:
        from ..embeddings import embed
        emb = embed(probe)
        if len(emb) != len(basin_centroid):
            t2 = TierResult(
                tier="T2",
                passed=False,
                score=0.0,
                threshold=t2_threshold,
                reason=(
                    f"dim mismatch: tension emb {len(emb)} vs centroid "
                    f"{len(basin_centroid)}"
                ),
            )
        else:
            sim = _cosine(emb, basin_centroid)
            t2 = TierResult(
                tier="T2",
                passed=(sim >= t2_threshold),
                score=sim,
                threshold=t2_threshold,
                reason=f"tension cosine vs centroid {sim:.3f}",
            )
    return t1, t2


def gate_lens_tensions(
    tensions: list[LensTension],
    *,
    basin_patterns: dict[str, list[str]] | None = None,
    basin_centroids: dict[str, list[float]] | None = None,
    require_both_tiers: bool = False,
) -> dict[str, Any]:
    """Run gate-over-lens: T1+T2 vs every tension/basin claim.

    For each tension and each claimed basin: either the basin survives
    (T1 or T2 passes — `require_both_tiers=True` to demand both) or
    the basin is dropped. A tension with NO surviving basins is
    archived; one with a reduced set is narrowed. Tensions with no
    basin claim (corpus-wide) pass through unchanged.

    Returns:
      {
        "kept":     [LensTension],                   # all basins survived
        "narrowed": [(orig, new)],                   # some basins dropped
        "archived": [(LensTension, reason)],         # no basins survived
        "by_basin": {basin_id: {pass: int, fail: int}},
      }

    The kernel applying to its own substrate: same T1/T2 primitives that
    gate moves now gate the lens that gates the moves. Tensions that
    claim a basin but can't resonate with the basin's content are
    architectural noise — surface them for archive, don't grade moves
    against them.
    """
    basin_patterns = basin_patterns or {}
    basin_centroids = basin_centroids or {}

    kept: list[LensTension] = []
    narrowed: list[tuple[LensTension, LensTension]] = []
    archived: list[tuple[LensTension, str]] = []
    by_basin: dict[str, dict[str, int]] = {}

    for tension in tensions:
        if not tension.basins:
            kept.append(tension)
            continue
        surviving: list[str] = []
        fail_reasons: list[str] = []
        for basin in tension.basins:
            t1, t2 = gate_lens_tension_in_basin(
                tension,
                basin,
                accepted_patterns=basin_patterns.get(basin),
                basin_centroid=basin_centroids.get(basin),
            )
            survives = (
                (t1.passed and t2.passed) if require_both_tiers
                else (t1.passed or t2.passed)
            )
            counters = by_basin.setdefault(basin, {"pass": 0, "fail": 0})
            counters["pass" if survives else "fail"] += 1
            if survives:
                surviving.append(basin)
            else:
                fail_reasons.append(
                    f"{basin}: T1 {t1.score:.2f}<{t1.threshold:.2f}, "
                    f"T2 {t2.score:.2f}<{t2.threshold:.2f}"
                )

        if not surviving:
            archived.append((
                tension,
                "; ".join(fail_reasons) if fail_reasons else "no surviving basins",
            ))
        elif tuple(surviving) == tension.basins:
            kept.append(tension)
        else:
            narrowed.append((
                tension,
                LensTension(
                    pole_a=tension.pole_a,
                    pole_b=tension.pole_b,
                    pole_a_failure=tension.pole_a_failure,
                    pole_b_failure=tension.pole_b_failure,
                    basins=tuple(surviving),
                ),
            ))

    return {
        "kept": kept,
        "narrowed": narrowed,
        "archived": archived,
        "by_basin": by_basin,
    }


def _filter_rejection_corpus(
    rejection_corpus: list[dict[str, Any]],
    move: Move,
) -> list[dict[str, Any]]:
    """Pick rejection records relevant to the candidate move.

    Strategy: when the move declares a basin, restrict to rejections
    in that basin (the most relevant signal — same-basin rejections are
    what the move would have addressed). When the move has no basin set
    yet (cold-install / pre-promotion), use the whole corpus.

    Returns the input list unchanged when basin filtering would yield
    zero items — better to score against the whole corpus than to
    score against zero items and return a meaningless score.
    """
    if not move.trinity_basin_id:
        return rejection_corpus
    same_basin = [r for r in rejection_corpus if r.get("basin") == move.trinity_basin_id]
    return same_basin if same_basin else rejection_corpus


def T3_chairman(
    candidate: Move,
    rejection_corpus: list[dict[str, Any]],
    *,
    chairman_provider_config: Any | None = None,
    lens_text: str = "",
    baseline: float | None = None,
    sample_size: int = 10,
    cwd: Any | None = None,
) -> TierResult:
    """Chairman scores the candidate against the personalized rejection
    corpus. Each rejection gets a per-item chairman call asking "would
    applying this move have helped avoid this rejection?" — aggregate
    is the mean across sampled items.

    Pass criterion:
      - First evaluation (baseline=None): always passes; the aggregate
        score BECOMES the new baseline. This is the move's first
        T3-recorded personal best.
      - Subsequent re-evals (baseline set): passes iff score ≥ baseline.

    Cost: ~30s per ~10-item sample (one chairman call per item). The
    most expensive tier — should run only on candidates that survived
    T1 + T2 priors.

    Cold-install cases (handled gracefully):
      - Empty rejection corpus → vacuous pass (no signal AGAINST the
        candidate; the lens hasn't accumulated rejections in this basin
        yet). T1/T2/T4 do the actual gating.
      - No chairman_provider_config → fail with actionable reason
        (caller is responsible for resolving the chairman provider).

    Sample-size design: 10 items is large enough that one outlier
    judge call doesn't flip the verdict, small enough that a dream
    cycle on a real corpus stays well under a minute. Caller can
    override for unit tests (1-3 items) or for high-stakes re-evals.
    """
    if not rejection_corpus:
        return TierResult(
            tier="T3",
            passed=True,
            score=1.0,
            threshold=baseline if baseline is not None else 0.0,
            reason=(
                "T3 vacuously passes: empty rejection corpus (no signal "
                "against this candidate in the basin yet). T1/T2/T4 are "
                "doing the gating for now; T3 will gain teeth as the "
                "rejection corpus grows."
            ),
        )
    if chairman_provider_config is None:
        return TierResult(
            tier="T3",
            passed=False,
            score=0.0,
            threshold=baseline if baseline is not None else 0.0,
            reason=(
                "T3 cannot run: no chairman_provider_config supplied. "
                "Caller must resolve the chairman provider before "
                "invoking T3 (typically config.providers['claude'] or "
                "whatever provides the user's chairman synthesis)."
            ),
        )
    # Lazy imports — keep gate.py import-clean for tests that don't
    # exercise T3
    from ..providers import make_provider, ProviderResult

    # Filter to relevant rejections + sample
    relevant = _filter_rejection_corpus(rejection_corpus, candidate)
    sample = relevant[:sample_size]  # deterministic; caller can pre-shuffle if randomization is wanted

    # Parse lens tensions ONCE; the per-rejection loop renders the
    # basin-relevant subset into the prompt. This is the seed-kernel
    # recursion edge: T3's rubric IS the user's lens tensions, not
    # generic axis-of-rejection language. The chairman that judges
    # candidates here is reading the same lens that T4 trains via
    # the chairman's own real-council picks.
    tensions = parse_lens_tensions(lens_text or "")
    tension_rubric = render_tension_rubric_for_basin(
        tensions, candidate.trinity_basin_id
    )
    if not tension_rubric:
        # Cold-start: lens hasn't built yet (or has but no tensions
        # span this basin). Fall through to a minimal rubric pointer
        # — the per-rejection axis_rubric below still drives scoring.
        tension_rubric = (
            "(lens has no documented tensions for this basin yet; "
            "fall through to the per-rejection axis rubric)"
        )

    judge = make_provider(chairman_provider_config)
    cwd = cwd or Path.cwd()

    scores: list[float] = []
    for item in sample:
        rejection_type = item.get("type", "REFRAME")
        axis_rubric = _AXIS_RUBRIC_FOR_T3.get(
            rejection_type,
            "Grade on overall alignment between the move and the user's preferred response shape.",
        )
        prompt = _T3_JUDGE_PROMPT.format(
            tension_rubric=tension_rubric,
            rejection_type=rejection_type,
            axis_rubric=axis_rubric,
            rejected_response=(item.get("model_quote") or "")[:2000],
            user_substitute=(item.get("user_substitute") or "")[:1000],
            rubric_signal=(item.get("why_signal") or "(none)")[:500],
            move_name=candidate.name,
            move_description=candidate.description,
            move_body=(candidate.body or "(no body)")[:2000],
        )
        try:
            result: ProviderResult = judge.run(prompt, cwd=cwd)
            score = _parse_t3_judge_response(result.stdout)
        except Exception:
            # Judge failure → contribute neutral 0.5, don't crash the
            # whole T3 evaluation on one bad call
            score = 0.5
        scores.append(score)

    if not scores:
        # Sample resolved empty after filtering — shouldn't happen
        # given the empty-corpus guard above, but defensive
        return TierResult(
            tier="T3",
            passed=False,
            score=0.0,
            threshold=baseline if baseline is not None else 0.0,
            reason="T3 resolved no scorable rejection items after sampling",
        )
    aggregate = sum(scores) / len(scores)
    # First evaluation: pass + set baseline. Re-eval: compare to baseline.
    if baseline is None:
        return TierResult(
            tier="T3",
            passed=True,
            score=aggregate,
            threshold=aggregate,  # this score becomes the new baseline
            reason=(
                f"T3 first evaluation: aggregate {aggregate:.3f} across "
                f"{len(scores)} sampled rejections. Setting baseline = "
                f"{aggregate:.3f}."
            ),
        )
    passed = aggregate >= baseline
    return TierResult(
        tier="T3",
        passed=passed,
        score=aggregate,
        threshold=baseline,
        reason=(
            f"T3 re-eval: aggregate {aggregate:.3f} "
            f"{'≥' if passed else '<'} baseline {baseline:.3f} "
            f"({len(scores)} sampled rejections)"
        ),
    )


# Per-rejection-type rubric copy lifted from evals/scorer.py
# (REJECTION_AXIS_RUBRIC). Duplicated to avoid the cross-module
# coupling — these strings are spec-stable and the duplication keeps
# moves/ self-contained.
_AXIS_RUBRIC_FOR_T3 = {
    "REFRAME": (
        "The user substituted a different FRAME. Score higher if the "
        "move helps the model notice when the user's literal question "
        "isn't the question they actually want answered."
    ),
    "COMPRESSION": (
        "The user wanted SHORTER. Score higher if the move would have "
        "led the model to produce a concise, direct response."
    ),
    "REDIRECT": (
        "The user wanted a structurally DIFFERENT output (spec vs "
        "narrative, etc.). Score higher if the move would have steered "
        "toward the correct shape."
    ),
    "SHARPENING": (
        "The user wanted more PRECISION (numbers, identifiers, "
        "concrete examples). Score higher if the move would have led "
        "to a sharper, more specific response."
    ),
}


def _parse_t3_judge_response(raw: str) -> float:
    """Extract score in [0.0, 1.0] from the chairman's stdout. Falls
    back to 0.5 on parse failure — better than crashing the whole T3
    sample on one bad judge call.

    Cribbed from evals/scorer._parse_judge_response but stripped down
    (we don't need the `reason` field here; the TierResult's `reason`
    is the aggregate-level explanation, not per-item).
    """
    import json
    import re as _re
    if not raw:
        return 0.5
    cleaned = raw.strip()
    cleaned = _re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = _re.sub(r"\s*```$", "", cleaned)
    try:
        parsed = json.loads(cleaned)
        score = float(parsed.get("score", 0.5))
        return max(0.0, min(1.0, score))
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    m = _re.search(r"\"score\"\s*:\s*([0-9.]+)", cleaned)
    if m:
        try:
            return max(0.0, min(1.0, float(m.group(1))))
        except ValueError:
            pass
    return 0.5


def T4_posterior(
    move: Move,
    *,
    threshold: float | None = None,
    min_executions: int = 5,
) -> TierResult:
    """Live A/B posterior — Beta-Binomial via Move.posterior. Reads
    the alpha/beta on the move; alpha/beta are updated incrementally by
    `update_posterior_from_council()` as councils complete.

    The threshold defaults to `move.trinity_eval_baseline` (the personal
    best from T3) — a move drifts below baseline → demote. If no
    baseline is set yet (move only has T1+T2 promotion), threshold
    falls back to 0.5 (the uninformative-prior break-even point).

    `min_executions` (default 5) prevents trigger-happy demotion on
    sparse evidence — with execution_count < 5, T4 vacuously passes
    regardless of posterior. Without this, a move that gets ONE failure
    in its first 3 executions (alpha=2, beta=2, posterior=0.5) would
    demote against a 0.7 baseline despite essentially no signal.

    This tier is FREE — no I/O, no model calls. The alpha/beta
    accumulation is the cost paid once per council via
    update_posterior_from_council().
    """
    actual_threshold = threshold if threshold is not None else (
        move.trinity_eval_baseline if move.trinity_eval_baseline is not None else 0.5
    )
    posterior = move.posterior
    # Under-execution case: too little signal to demote on
    if move.trinity_execution_count < min_executions:
        return TierResult(
            tier="T4",
            passed=True,
            score=posterior,
            threshold=actual_threshold,
            reason=(
                f"posterior {posterior:.3f} (need ≥ {actual_threshold:.2f}); "
                f"execution_count={move.trinity_execution_count} below "
                f"min_executions={min_executions} — vacuous pass (need "
                f"more council evidence before demotion is meaningful)"
            ),
        )
    passed = posterior >= actual_threshold
    return TierResult(
        tier="T4",
        passed=passed,
        score=posterior,
        threshold=actual_threshold,
        reason=(
            f"posterior {posterior:.3f} (α={move.trinity_alpha}, "
            f"β={move.trinity_beta}, n={move.trinity_execution_count}) "
            f"{'≥' if passed else '<'} baseline {actual_threshold:.2f}"
        ),
    )


def update_posterior_from_council(
    move: Move,
    *,
    winning_response_text: str,
    council_basin_id: str | None,
    applicability_threshold: float = 0.2,
    n: int = 3,
) -> tuple[Move, str]:
    """Apply one council's outcome to a move's alpha/beta tracker.

    Caller invokes once per (active move, completed council) pair.
    Returns (updated_move, action) where action is one of:
      - "alpha_incremented" — chairman picked a response that follows
        this move's prescription (move was applied + won)
      - "beta_incremented"  — chairman picked a response that does NOT
        follow this move, but the move's basin matched the task (move
        was applicable but not followed)
      - "skipped_wrong_basin" — move's basin doesn't match the council
        task's basin; this move doesn't apply, no update
      - "skipped_no_basin"   — move has no trinity_basin_id set (cold-
        install / mid-flight state); no update

    Note: the input move is MUTATED in place via record_success() /
    record_failure() — the returned reference is the same object, for
    callers that want to chain. Persistence is the caller's job
    (store.write_move).

    The applicability check uses word n-gram Jaccard: a move "was
    followed" iff Jaccard(move_body_ngrams, winning_response_ngrams)
    ≥ applicability_threshold. Default 0.2 — looser than T1's promotion
    threshold because we're measuring "the move's pattern appeared",
    not "the move's pattern dominated".
    """
    # Skip when basins don't match — no applicability signal
    if not move.trinity_basin_id:
        return move, "skipped_no_basin"
    if council_basin_id != move.trinity_basin_id:
        return move, "skipped_wrong_basin"
    # Applicability check via Jaccard on body n-grams
    move_ngrams = _word_ngrams(_candidate_text(move), n=n)
    winner_ngrams = _word_ngrams(winning_response_text or "", n=n)
    similarity = _jaccard(move_ngrams, winner_ngrams)
    if similarity >= applicability_threshold:
        move.record_success()
        return move, "alpha_incremented"
    move.record_failure()
    return move, "beta_incremented"


def run_gate(
    candidate: Move,
    *,
    accepted_patterns: list[str] | None = None,
    basin_centroid: list[float] | None = None,
    rejection_corpus: list[dict[str, Any]] | None = None,
    chairman_provider_config: Any | None = None,
    lens_text: str = "",
    baseline: float | None = None,
) -> list[TierResult]:
    """Run T1 → T2 → T3 sequentially, short-circuiting on first failure.

    T4 is excluded — it's only meaningful on already-promoted moves
    (alpha/beta start at the uninformative prior; the posterior is
    flat 0.5 before any council runs). Call T4_posterior() directly
    when re-evaluating active moves at dream time.

    Returns the list of TierResults in order. Each result's `passed`
    flag tells the caller whether the next tier ran.

    T3-specific kwargs (forwarded only when T1+T2 pass):
      - chairman_provider_config: required for T3 to actually run a
        chairman call. Caller resolves from config.providers.
      - lens_text: the user's lens.md content; cropped to ~2000 chars
        for chairman context. Empty string is acceptable (T3 prompts
        the chairman with "(lens not yet built)").
      - baseline: T3's threshold. None = first promotion (T3 will set
        the baseline from its score); a float = re-eval against
        existing personal best.
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
    t3 = T3_chairman(
        candidate,
        rejection_corpus or [],
        chairman_provider_config=chairman_provider_config,
        lens_text=lens_text,
        baseline=baseline,
    )
    out.append(t3)
    return out
