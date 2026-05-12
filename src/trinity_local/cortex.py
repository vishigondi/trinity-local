"""v1.5 cortex layer — extracted routing patterns per basin.

Hippocampus stores episodes (individual council outcomes). Cortex stores
extracted patterns across them. The brain works in two tiers; Trinity does too.

This module owns the cortex schema, the system-computed `trust_score`, and the
consolidation orchestration. The actual pattern extraction is a flagship-model
call that's injected via a callable — keeping it testable without LLM access,
and (in production) routed through whatever the user's strongest sub is.

The 4-component trust_score is the most load-bearing piece: it's what gates
whether a cortex rule is trusted enough to drive routing decisions. Per
spec-v1.5.md:

  ≥0.75  → use rule alone
  0.50–0.75 → use rule, kNN as calibration
  <0.50  → ignore rule, fall back to kNN

The score combines:
  1. n_episodes_norm    — small basins are shaky (need ≥25 outcomes)
  2. consistency_score  — how much primary dominates the distribution
  3. recency_agreement  — last 10 outcomes agree with the rule?
  4. diversity          — embed-distance spread, catches niche-artifact basins
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field, asdict
from typing import Any, Callable

from .state_paths import cortex_routing_patterns_path, council_outcomes_dir


# Trust score thresholds — match docs/spec-v1.5.md.
TRUST_USE_RULE = 0.75
TRUST_KNN_FALLBACK = 0.50

# Component weights (geometric mean, then weighted). Tunable after the human-
# calibration gate at end of Week 2.
_TRUST_WEIGHTS = {
    "n_episodes_norm": 0.25,
    "consistency_score": 0.25,
    "recency_agreement": 0.20,
    "diversity": 0.10,
    "coherence_score": 0.20,
}

# Bimodality kurtosis threshold. Excess kurtosis below this on the first
# PC distribution flags a basin as plausibly bimodal — at which point the
# flagship is told "this basin has bimodal geometry" and may emit two
# rules. v1.5 only flags; v1.6 wires HDBSCAN to actually split.
#
# Calibration note: -1.3 is just below uniform (-1.2 excess kurtosis) so
# uniform-along-an-axis basins (which are coherent, not bimodal) don't
# trip the flag. Truly twin-peaked distributions hit -1.4 to -2.0+.
_BIMODALITY_KURTOSIS_THRESHOLD = -1.3

# Manifold dimensionality cap for the coherence signal. Effective dim
# computed via participation ratio of the singular values; saturates at
# this number of components. Beyond ~5 the basin is high-dim noise.
_MANIFOLD_DIM_SATURATION = 5.0

# n_episodes saturation point: a basin with this many outcomes is "fully
# informed" on that axis. Fewer outcomes dilute trust proportionally.
N_EPISODES_FULL = 25


@dataclass
class RoutingRule:
    """The flagship-extracted shape — what to do, why, and when."""

    primary: str
    challenger: str | None
    reason: str
    subroutes: list[dict] = field(default_factory=list)


@dataclass
class FailureModes:
    """Per-provider failure shape extracted from disagreed_claims."""

    claude: str | None = None
    codex: str | None = None
    gemini: str | None = None
    other: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        out: dict[str, str] = {}
        if self.claude:
            out["claude"] = self.claude
        if self.codex:
            out["codex"] = self.codex
        if self.gemini:
            out["gemini"] = self.gemini
        out.update(self.other)
        return out


@dataclass
class TrustScore:
    """System-computed (not flagship-declared) — flagship describes the rule,
    we decide whether to trust it. See spec-v1.5.md.
    """

    value: float
    components: dict[str, float]
    computed_by: str = "system"

    @property
    def interpretation(self) -> str:
        if self.value >= TRUST_USE_RULE:
            return "use rule alone"
        if self.value >= TRUST_KNN_FALLBACK:
            return "use rule with kNN fallback"
        return "ignore rule, fall back to kNN"

    def to_dict(self) -> dict:
        return {
            "value": round(self.value, 3),
            "components": {k: round(v, 3) for k, v in self.components.items()},
            "computed_by": self.computed_by,
            "interpretation": self.interpretation,
        }


@dataclass
class RoutingPattern:
    """One basin's worth of extracted routing knowledge."""

    basin_id: str
    consolidated_at: str
    n_episodes: int
    task_kinds: list[str]
    winner_distribution: dict[str, float]
    routing_rule: RoutingRule
    trust_score: TrustScore
    failure_modes: FailureModes = field(default_factory=FailureModes)
    successful_prompts: dict[str, list[str]] = field(default_factory=dict)
    decay: dict = field(default_factory=dict)
    evidence: list[str] = field(default_factory=list)
    # Geometric median of this basin's evidence-prompt embeddings (Weiszfeld
    # iteration). Replaces Euclidean mean (v1.5+) — robust to outliers via
    # L1 minimization. Used at query time by ask._best_centroid_match.
    basin_centroid: list[float] = field(default_factory=list)
    # Effective intrinsic dimensionality via participation ratio of the
    # centered embedding SVD. Low (≤2) = coherent cluster. High (≥5 with
    # small N) = noise. Feeds the coherence_score trust component.
    manifold_dim: float = 0.0
    # Excess kurtosis on the first-PC distribution. Negative values flag
    # plausibly bimodal basins — surfaced in the extraction prompt so the
    # flagship can emit two rules instead of averaging them. <_BIMODALITY_KURTOSIS_THRESHOLD
    # → bimodal_flag=true.
    bimodal_flag: bool = False

    def to_dict(self) -> dict:
        return {
            "basin_id": self.basin_id,
            "consolidated_at": self.consolidated_at,
            "n_episodes": self.n_episodes,
            "task_kinds": self.task_kinds,
            "winner_distribution": {k: round(v, 3) for k, v in self.winner_distribution.items()},
            "routing_rule": asdict(self.routing_rule),
            "trust_score": self.trust_score.to_dict(),
            "failure_modes": self.failure_modes.to_dict(),
            "successful_prompts": self.successful_prompts,
            "decay": self.decay,
            "evidence": self.evidence,
            "basin_centroid": self.basin_centroid,
            "manifold_dim": round(self.manifold_dim, 3),
            "bimodal_flag": self.bimodal_flag,
        }


def compute_trust_score(
    *,
    n_episodes: int,
    winner_distribution: dict[str, float],
    rule_primary: str,
    recent_winners: list[str],
    diversity_metric: float,
    coherence_score: float = 0.5,
) -> TrustScore:
    """Compute the 5-component trust score. All inputs are derivable from
    accumulated council outcomes; no flagship-declared values.

    Args:
        n_episodes: count of outcomes in this basin
        winner_distribution: {provider: fraction} from outcomes
        rule_primary: provider name the flagship chose as primary
        recent_winners: last 10 winner_providers in chronological order
        diversity_metric: 0..1, average embed-distance spread within basin
        coherence_score: 0..1, basin geometric coherence (1 - manifold_dim /
            saturation). Low when embeddings are high-dim noise; high when
            they collapse to a tight low-dim manifold. Without this signal,
            a confident rule on a noisy basin reads as high-trust — the
            most dangerous failure mode. Default 0.5 = neutral for callers
            that don't compute geometry.

    Returns:
        TrustScore with computed value + transparent component breakdown.
    """
    # 1. Sample-size: linear saturation up to N_EPISODES_FULL.
    n_norm = min(1.0, n_episodes / N_EPISODES_FULL)

    # 2. Consistency: winner's share of the distribution. 0.62 = primary won
    # 62% of the time → consistency_score=0.62. Tied (33/33/33) → 0.33.
    consistency = winner_distribution.get(rule_primary, 0.0)

    # 3. Recency agreement: of the last 10 outcomes, what fraction picked
    # the primary the rule names? Catches "rule used to be true but isn't."
    if recent_winners:
        agreed = sum(1 for w in recent_winners if w == rule_primary)
        recency = agreed / len(recent_winners)
    else:
        recency = 0.5  # neutral when no recent data

    # 4. Diversity already 0..1; passed through.
    diversity = max(0.0, min(1.0, diversity_metric))

    # 5. Coherence already 0..1; passed through.
    coherence = max(0.0, min(1.0, coherence_score))

    components = {
        "n_episodes_norm": n_norm,
        "consistency_score": consistency,
        "recency_agreement": recency,
        "diversity": diversity,
        "coherence_score": coherence,
    }
    # Weighted geometric mean — penalizes any single weak component more than
    # a weighted arithmetic mean would. A basin with 50 episodes (n_norm=1.0)
    # but recency_agreement=0.2 should not be high-trust. Geometric mean does
    # that by construction.
    # log(g) = Σ w_i · log(x_i) → g = exp(Σ w_i · log(x_i)).
    # Guard against log(0): tiny floor of 1e-6.
    log_val = sum(
        _TRUST_WEIGHTS[name] * math.log(max(1e-6, val)) for name, val in components.items()
    )
    value = math.exp(log_val)

    return TrustScore(value=value, components=components)


def load_routing_patterns() -> dict[str, RoutingPattern]:
    """Read the cortex routing_patterns.json. Empty dict if file doesn't exist."""
    path = cortex_routing_patterns_path()
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, RoutingPattern] = {}
    for basin_id, raw in data.items():
        try:
            out[basin_id] = _pattern_from_dict(raw)
        except (KeyError, TypeError):
            continue  # skip malformed entries; consolidator will rewrite
    return out


def save_routing_patterns(patterns: dict[str, RoutingPattern]) -> None:
    """Write the cortex routing_patterns.json atomically."""
    path = cortex_routing_patterns_path()
    serialized = {basin_id: p.to_dict() for basin_id, p in patterns.items()}
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(serialized, indent=2), encoding="utf-8")
    tmp.replace(path)


def _pattern_from_dict(raw: dict) -> RoutingPattern:
    """Inverse of RoutingPattern.to_dict()."""
    rule = RoutingRule(**raw["routing_rule"])
    trust = TrustScore(
        value=raw["trust_score"]["value"],
        components=raw["trust_score"]["components"],
        computed_by=raw["trust_score"].get("computed_by", "system"),
    )
    fm_raw = raw.get("failure_modes", {})
    fm = FailureModes(
        claude=fm_raw.get("claude"),
        codex=fm_raw.get("codex"),
        gemini=fm_raw.get("gemini"),
        other={k: v for k, v in fm_raw.items() if k not in {"claude", "codex", "gemini"}},
    )
    return RoutingPattern(
        basin_id=raw["basin_id"],
        consolidated_at=raw["consolidated_at"],
        n_episodes=raw["n_episodes"],
        task_kinds=raw.get("task_kinds", []),
        winner_distribution=raw.get("winner_distribution", {}),
        routing_rule=rule,
        trust_score=trust,
        failure_modes=fm,
        successful_prompts=raw.get("successful_prompts", {}),
        decay=raw.get("decay", {}),
        evidence=raw.get("evidence", []),
        basin_centroid=raw.get("basin_centroid", []),
        manifold_dim=float(raw.get("manifold_dim", 0.0) or 0.0),
        bimodal_flag=bool(raw.get("bimodal_flag", False)),
    )


# Type alias for the injectable flagship extractor. Takes a list of council
# outcome dicts (for one basin) and returns the extracted (rule, failure_modes,
# successful_prompts) — what the flagship looked at the data and concluded.
# Production wires this through providers.make_provider(claude_opus).run(prompt).
# Tests inject a stub that returns canned values.
FlagshipExtractor = Callable[[list[dict]], dict[str, Any]]


def consolidate_basin(
    *,
    basin_id: str,
    outcomes: list[dict],
    task_kinds: list[str],
    diversity_metric: float,
    extractor: FlagshipExtractor,
) -> RoutingPattern:
    """Run the consolidation pass for one basin: extract rule via flagship,
    compute trust_score via system, return the assembled RoutingPattern.

    The extractor is injectable — production passes a real flagship-call
    function; tests pass a stub. This keeps the orchestration testable.
    """
    from datetime import datetime, timezone

    if not outcomes:
        raise ValueError(f"consolidate_basin called with no outcomes for {basin_id}")

    # Compute winner distribution from outcomes.
    winners: list[str] = []
    for o in outcomes:
        winner = (o.get("winner") or o.get("winner_provider") or "").strip()
        if winner:
            winners.append(winner)
    n_episodes = len(outcomes)
    total_winners = len(winners) or 1
    winner_distribution = {
        w: round(winners.count(w) / total_winners, 3) for w in set(winners)
    }

    # Recent winners (last 10) for recency_agreement computation.
    recent_winners = winners[-10:] if len(winners) >= 1 else []

    # Compute the structured geometric prior FIRST so the flagship can
    # condition on it (rule-extraction on structure, not geometry-in-language).
    geometry = _compute_basin_geometry(outcomes)

    # Flagship extracts the rule + failure modes + successful prompt templates.
    # Pass geometry if the extractor accepts it (production), else fall back
    # to single-arg call (test stubs).
    try:
        extracted = extractor(outcomes, geometry)
    except TypeError:
        extracted = extractor(outcomes)
    rule = RoutingRule(
        primary=extracted["primary"],
        challenger=extracted.get("challenger"),
        reason=extracted.get("reason", ""),
        subroutes=extracted.get("subroutes", []),
    )
    fm_dict = extracted.get("failure_modes", {})
    fm = FailureModes(
        claude=fm_dict.get("claude"),
        codex=fm_dict.get("codex"),
        gemini=fm_dict.get("gemini"),
        other={k: v for k, v in fm_dict.items() if k not in {"claude", "codex", "gemini"}},
    )
    successful_prompts = extracted.get("successful_prompts", {})

    # Evidence: cite the outcome ids the flagship saw. Cap at 20 to keep the
    # JSON small; full set is in council_outcomes/ anyway.
    evidence = [
        (o.get("council_id") or o.get("bundle_id") or "").strip()
        for o in outcomes
        if (o.get("council_id") or o.get("bundle_id"))
    ][:20]

    trust = compute_trust_score(
        n_episodes=n_episodes,
        winner_distribution=winner_distribution,
        rule_primary=rule.primary,
        recent_winners=recent_winners,
        diversity_metric=diversity_metric,
        coherence_score=geometry["coherence_score"],
    )

    return RoutingPattern(
        basin_id=basin_id,
        consolidated_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        n_episodes=n_episodes,
        task_kinds=task_kinds,
        winner_distribution=winner_distribution,
        routing_rule=rule,
        trust_score=trust,
        failure_modes=fm,
        successful_prompts=successful_prompts,
        evidence=evidence,
        basin_centroid=geometry["centroid"],
        manifold_dim=geometry["manifold_dim"],
        bimodal_flag=geometry["bimodal_flag"],
    )


def _compute_basin_geometry(outcomes: list[dict]) -> dict:
    """Return the structured geometric prior for one basin's evidence
    embeddings. Replaces the bare Euclidean mean (v1.4) — the consolidation
    pass now receives a tight numeric description of basin shape so the
    flagship can do rule-extraction-on-structure instead of
    geometry-in-language.

    Returns dict with:
      centroid:       geometric median (Weiszfeld iteration). Robust to
                      outliers via L1 minimization. ``[]`` if embedding fails.
      manifold_dim:   effective dim via participation ratio of the centered
                      SVD. Low (≤2) = coherent. High (≥5 small-N) = noise.
      coherence_score: ``1 - manifold_dim / _MANIFOLD_DIM_SATURATION``, clipped 0..1.
                      Direct trust component.
      bimodal_flag:   excess kurtosis on first PC distribution < threshold →
                      basin is plausibly bimodal. Surfaced to extraction
                      prompt so flagship can emit two rules.
      ordered_indices: outcomes sorted by L2 distance from the median —
                      typical first, outliers last. Used to put the most
                      representative episodes at the top of the prompt.

    Best-effort: any failure returns an empty geometry (centroid=[], dim=0,
    coherence=0.5 neutral, flag=False, ordered=[]). The caller falls through
    to label-only paths.
    """
    empty = {
        "centroid": [],
        "manifold_dim": 0.0,
        "coherence_score": 0.5,
        "bimodal_flag": False,
        "ordered_indices": [],
    }

    try:
        from .embeddings import embed
    except ImportError:
        return empty

    # Extract the prompt text from each outcome (the synthesis_prompt or
    # bundle task_text). Track original outcome index so the caller can
    # reorder by typicality.
    indexed_prompts: list[tuple[int, str]] = []
    for idx, o in enumerate(outcomes[:40]):  # cap mirrors build_extraction_prompt
        synth = o.get("synthesis_prompt") or ""
        text = ""
        if synth:
            text = synth.split("\n\n")[0][:500] if "\n\n" in synth else synth[:500]
        if not text:
            label = o.get("routing_label") or {}
            text = label.get("task_type", "") or ""
        if text.strip():
            indexed_prompts.append((idx, text.strip()))

    if not indexed_prompts:
        return empty

    try:
        vectors_raw = [(idx, embed(p)) for idx, p in indexed_prompts]
    except Exception:
        return empty
    vectors_with_idx = [(idx, v) for idx, v in vectors_raw if v]
    if not vectors_with_idx:
        return empty

    dim = len(vectors_with_idx[0][1])
    # Tolerate dim mismatch (backend swap mid-consolidation).
    vectors_with_idx = [(idx, v) for idx, v in vectors_with_idx if len(v) == dim]
    if not vectors_with_idx:
        return empty

    indices = [idx for idx, _ in vectors_with_idx]
    matrix = [list(v) for _, v in vectors_with_idx]
    n = len(matrix)

    median = _weiszfeld_median(matrix)

    # Order by L2 distance from median (typical → outlier).
    distances = [
        (idx, _euclid(matrix[i], median)) for i, idx in enumerate(indices)
    ]
    distances.sort(key=lambda t: t[1])
    ordered_indices = [idx for idx, _ in distances]

    # Manifold dim via participation ratio on centered matrix — purely a
    # descriptive signal surfaced to the LLM prompt (numeric flavor of
    # basin shape). Not used directly as a trust component; participation
    # ratio is too sensitive to ambient dimensionality with high-dim
    # embeddings to be a clean 0..1 measure.
    manifold_dim = _participation_ratio(matrix, median)

    # Trust-relevant coherence: mean cosine similarity from the median.
    # In the same units as the query-time matcher (cosine), saturates
    # naturally at 1.0 (every point coincides with the median) and falls
    # toward 0 as evidence spreads. This is what we actually care about:
    # "if I route a new query whose embedding sits near the median, how
    # representative is that of the basin?"
    coherence = max(0.0, min(1.0, _mean_cosine_to(median, matrix)))

    # Bimodality via excess kurtosis on first PC. Project each row onto
    # the leading singular direction (computed via power iteration to avoid
    # bringing in scipy/numpy.linalg as a hard dep). Floor N at 10 — the
    # kurtosis statistic is too noisy below that to call bimodality with
    # any confidence, and false positives here cost more than false
    # negatives (a wrongly-split basin produces two weak rules instead of
    # one decent rule).
    bimodal_flag = False
    if n >= 10:
        first_pc_scalars = _project_onto_first_pc(matrix, median)
        if first_pc_scalars:
            bimodal_flag = _excess_kurtosis(first_pc_scalars) < _BIMODALITY_KURTOSIS_THRESHOLD

    return {
        "centroid": median,
        "manifold_dim": manifold_dim,
        "coherence_score": coherence,
        "bimodal_flag": bimodal_flag,
        "ordered_indices": ordered_indices,
    }


def _euclid(a: list[float], b: list[float]) -> float:
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def _mean_cosine_to(center: list[float], points: list[list[float]]) -> float:
    """Mean cosine similarity from ``center`` to each row in ``points``.

    Used as the trust-relevant coherence signal — directly answers "if a
    new query's embedding lands near the median, how similar is that to
    the typical evidence?" Returns 0.0 when the center has zero norm
    (degenerate); otherwise in [-1.0, 1.0] which the caller clips.
    """
    if not points or not center:
        return 0.0
    center_norm = math.sqrt(sum(x * x for x in center))
    if center_norm < 1e-12:
        return 0.0
    sims: list[float] = []
    for p in points:
        p_norm = math.sqrt(sum(x * x for x in p))
        if p_norm < 1e-12:
            continue
        dot = sum(a * b for a, b in zip(p, center))
        sims.append(dot / (p_norm * center_norm))
    if not sims:
        return 0.0
    return sum(sims) / len(sims)


def _weiszfeld_median(points: list[list[float]], max_iter: int = 50, eps: float = 1e-6) -> list[float]:
    """Geometric median via Weiszfeld iteration. Robust to outliers under
    L1 (a single far point can't drag the median the way it drags the mean).

    Single-pass O(I·N·D) where I ≤ 50. For typical basin sizes (≤50
    points × 768-dim embeddings) this completes in milliseconds.
    """
    if not points:
        return []
    dim = len(points[0])
    # Initialize at the arithmetic mean.
    median = [sum(p[i] for p in points) / len(points) for i in range(dim)]

    for _ in range(max_iter):
        weights: list[float] = []
        total_weight = 0.0
        coincident_index: int | None = None
        for i, p in enumerate(points):
            d = _euclid(median, p)
            if d < eps:
                coincident_index = i
                break
            w = 1.0 / d
            weights.append(w)
            total_weight += w

        if coincident_index is not None:
            # The current median sits exactly on point `coincident_index`.
            # Per Vardi–Zhang, the L1 minimizer is that point unless the
            # net pull from the rest exceeds 1. For our needs (≤50 points,
            # high-dim embeddings) collisions are vanishingly rare —
            # snapping to the colliding point is safe and stable.
            return list(points[coincident_index])

        if total_weight < eps:
            break

        new_median = [0.0] * dim
        for p, w in zip(points, weights):
            for j in range(dim):
                new_median[j] += p[j] * w
        for j in range(dim):
            new_median[j] /= total_weight

        # Convergence check on L2 step size.
        step = _euclid(new_median, median)
        median = new_median
        if step < eps:
            break

    return median


def _participation_ratio(points: list[list[float]], center: list[float]) -> float:
    """Effective dimensionality via participation ratio of singular values.

    Define x_i = p_i - center. Build the covariance matrix
    C = (1/N) X^T X (in feature space — D×D). For an D-dim embedding
    that's expensive, but PR(C) = (tr C)² / tr(C²) only needs the trace
    and Frobenius norm of C, both computable from X X^T (the N×N gram
    matrix) since tr(X X^T) = tr(X^T X) and ‖X X^T‖_F = ‖X^T X‖_F.

    So PR = (Σᵢ d_i)² / Σᵢ,ⱼ (⟨x_i, x_j⟩)² where d_i = ⟨x_i, x_i⟩. This
    is O(N²·D) — fine for basins capped at 40 points.

    Result: 1.0 when all points coincide, → N as points spread isotropically.
    """
    n = len(points)
    if n < 2:
        return 0.0

    # Center.
    centered = [[p[i] - center[i] for i in range(len(p))] for p in points]

    # Gram matrix entries.
    gram_diag: list[float] = []
    gram_off_squared_sum = 0.0
    for i in range(n):
        d_ii = sum(x * x for x in centered[i])
        gram_diag.append(d_ii)
    trace = sum(gram_diag)
    if trace < 1e-12:
        return 0.0

    frobenius_sq = 0.0
    for i in range(n):
        for j in range(n):
            inner = sum(centered[i][k] * centered[j][k] for k in range(len(centered[i])))
            frobenius_sq += inner * inner

    if frobenius_sq < 1e-12:
        return 0.0
    return (trace * trace) / frobenius_sq


def _project_onto_first_pc(points: list[list[float]], center: list[float]) -> list[float]:
    """Project rows onto the leading singular direction via power iteration
    on the centered N×D matrix. Returns N scalars — the 1D distribution
    along the basin's primary axis of variation.

    Why not numpy.linalg.svd: this module currently has no hard numpy
    dependency in production paths; a 50-iteration power iteration on a
    small (≤40)×768 matrix runs in ms with no import cost.
    """
    n = len(points)
    if n < 2:
        return []
    dim = len(points[0])
    centered = [[p[i] - center[i] for i in range(dim)] for p in points]

    # Initialize a random-ish unit vector deterministically.
    v = [1.0 / math.sqrt(dim)] * dim

    for _ in range(50):
        # Apply X^T X · v (covariance-vector product, computed implicitly).
        Xv = [sum(centered[i][j] * v[j] for j in range(dim)) for i in range(n)]
        new_v = [0.0] * dim
        for j in range(dim):
            new_v[j] = sum(centered[i][j] * Xv[i] for i in range(n))
        norm = math.sqrt(sum(x * x for x in new_v))
        if norm < 1e-12:
            return []
        new_v = [x / norm for x in new_v]
        # Check convergence
        delta = sum((new_v[j] - v[j]) ** 2 for j in range(dim))
        v = new_v
        if delta < 1e-8:
            break

    # Project each centered row onto v.
    return [sum(centered[i][j] * v[j] for j in range(dim)) for i in range(n)]


def _excess_kurtosis(values: list[float]) -> float:
    """Excess kurtosis = E[(x-μ)⁴] / σ⁴ - 3. Negative values flag distributions
    flatter than normal (uniform → -1.2, bimodal → more negative still).
    Positive values are peakier than normal (Cauchy, Laplace).
    """
    n = len(values)
    if n < 4:
        return 0.0
    mean = sum(values) / n
    var = sum((v - mean) ** 2 for v in values) / n
    if var < 1e-12:
        return 0.0
    fourth = sum((v - mean) ** 4 for v in values) / n
    return fourth / (var * var) - 3.0


def iter_outcomes() -> list[dict]:
    """Walk all council_outcomes/*.json. Used by `consolidate` CLI."""
    out_dir = council_outcomes_dir()
    items: list[dict] = []
    if not out_dir.is_dir():
        return items
    for path in sorted(out_dir.glob("council_*.json")):
        try:
            items.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return items


def group_outcomes_by_basin(outcomes: list[dict]) -> dict[str, list[dict]]:
    """Group council outcomes by basin. For v1.5 Week 2 we use the chairman-
    classified `task_type` as the basin key — it's already in every outcome's
    routing_label and gives us a coherent cluster of similar questions. A
    proper centroid-based basin classifier (matching the lens pipeline's
    me/basins.json) lands in Week 3.

    Skips outcomes with no task_type. Returns {basin_id: [outcomes...]}.
    """
    grouped: dict[str, list[dict]] = {}
    for o in outcomes:
        label = o.get("routing_label") or {}
        task_type = (label.get("task_type") or "").strip()
        if not task_type:
            continue
        grouped.setdefault(task_type, []).append(o)
    return grouped


# ──────────────────────────────────────────────────────────────────────────────
# Flagship extractor — the actual LLM-driven step.
#
# The flagship reads N outcomes from one basin and emits a structured
# extraction: rule + failure modes + successful prompt templates. The prompt
# template lives in build_extraction_prompt; the JSON response gets parsed by
# parse_extraction_response. Both are pure functions — testable without LLM
# access. The runner that ties them together (build → dispatch → parse) lives
# in `make_flagship_extractor` and takes a dispatch_fn that production wires
# through `providers.make_provider(claude_opus_config).run(prompt, cwd).stdout`.
# ──────────────────────────────────────────────────────────────────────────────


def build_extraction_prompt(
    basin_id: str,
    outcomes: list[dict],
    geometry: dict | None = None,
) -> str:
    """Build the prompt that asks a flagship model to extract a routing rule
    from N council outcomes in one basin. The schema of the expected response
    matches RoutingRule + FailureModes + successful_prompts.

    When ``geometry`` is provided (the structured geometric prior from
    ``_compute_basin_geometry``), outcomes are re-ordered typical-first
    and the prompt prefixes a one-paragraph description of basin shape —
    coherence, bimodality, manifold dim. This is the "rule-extraction on
    structure" move: the flagship stops doing geometry-in-language and
    starts conditioning on numerically-extracted basin properties.
    """
    # Reorder outcomes typical-first when geometry tells us how.
    ordered = list(outcomes)
    if geometry and geometry.get("ordered_indices"):
        ordered_idx = geometry["ordered_indices"]
        seen = set(ordered_idx)
        reordered = [outcomes[i] for i in ordered_idx if i < len(outcomes)]
        # Append any outcomes the geometry pass skipped (e.g. empty prompts).
        for i, o in enumerate(outcomes):
            if i not in seen:
                reordered.append(o)
        ordered = reordered

    # Compress each outcome to its load-bearing fields. The full council
    # outcome JSON has synthesis_prompt + synthesis_output blobs that aren't
    # needed for extraction. We send just routing_label.
    compressed: list[dict] = []
    for o in ordered[:40]:  # cap to 40 outcomes per basin — keeps token budget reasonable
        label = o.get("routing_label") or {}
        entry = {
            "council_id": o.get("council_run_id") or o.get("council_id"),
            "winner": label.get("winner") or o.get("winner_provider"),
            "runner_up": label.get("runner_up"),
            "routing_lesson": label.get("routing_lesson", ""),
            "agreed_claims": label.get("agreed_claims", []),
            "disagreed_claims": label.get("disagreed_claims", []),
            "user_verdict": (o.get("metadata") or {}).get("user_verdict", {}).get("user_winner"),
        }
        compressed.append(entry)

    geometry_block = ""
    if geometry and geometry.get("centroid"):
        coherence = geometry["coherence_score"]
        manifold_dim = geometry["manifold_dim"]
        bimodal = geometry["bimodal_flag"]
        if bimodal:
            shape = "BIMODAL"
            shape_note = (
                "The embeddings split into two distinguishable modes. If the "
                "two modes route to different providers, return TWO subroutes "
                "instead of forcing a single primary."
            )
        elif coherence < 0.4:
            shape = "NOISY"
            shape_note = (
                "The embeddings are spread across many dimensions — this basin "
                "may not be a real cluster. Be conservative: prefer no rule "
                "over a confident wrong rule. Setting subroutes=[] is acceptable."
            )
        elif coherence > 0.7:
            shape = "COHERENT"
            shape_note = (
                "The embeddings cluster tightly. Outcomes near the top of the "
                "list are the typical ones — weight them more heavily than "
                "outliers near the bottom."
            )
        else:
            shape = "MIXED"
            shape_note = (
                "Outcomes are ordered typical-first. Trust the head of the list."
            )
        geometry_block = (
            f"BASIN GEOMETRY: {shape} (manifold_dim={manifold_dim:.2f}, "
            f"coherence={coherence:.2f}, bimodal={bimodal}). {shape_note}\n\n"
        )

    return f"""You are extracting a ROUTING RULE for a personal AI router. You have {len(outcomes)} council outcomes from one user, all in basin "{basin_id}". For each outcome: which model won, the chairman's routing lesson, what models agreed/disagreed on, the user's verdict if they overrode.

{geometry_block}Your job: read these outcomes and extract a structured routing rule the system will use to route NEW questions in this basin. Be specific. Cite outcome IDs when relevant.

Return a single JSON object (no prose around it) matching this exact shape:

{{
  "primary": "<provider name>",
  "challenger": "<provider name or null>",
  "reason": "<one-sentence why the primary wins, with the actual structural difference between providers>",
  "subroutes": [
    {{"if_keywords": ["..."], "prefer": "<provider>", "why": "<one sentence>"}}
  ],
  "failure_modes": {{
    "claude": "<one-phrase failure mode when claude loses in this basin, or null>",
    "codex": "<...>",
    "gemini": "<...>"
  }},
  "successful_prompts": {{
    "claude": ["<first-words pattern of a prompt that worked>", "<another>"],
    "codex": ["..."]
  }}
}}

Rules:
- Use ONLY evidence from the outcomes below. Don't invent.
- If user verdicts contradict the chairman winner, weight USER VERDICTS more heavily — they are the ground truth of taste.
- If a provider never appears in the outcomes, omit it from failure_modes/successful_prompts.
- "reason" must name the actual structural difference (not "claude is smarter"; instead "claude consistently surfaces second-order failure modes that codex glosses over").
- subroutes only when keywords clearly flip the winner.
- DO NOT include a trust_score field. The system computes that.

OUTCOMES:
{json.dumps(compressed, indent=2)}"""


def parse_extraction_response(text: str) -> dict[str, Any]:
    """Parse the flagship's JSON response into the dict consolidate_basin
    expects. Tolerates surrounding markdown fences and prose. Raises if no
    JSON object can be extracted at all.
    """
    text = text.strip()
    # Strip markdown fences.
    if text.startswith("```"):
        # Remove opening fence (with optional `json` tag).
        lines = text.split("\n")
        if len(lines) >= 2:
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        text = "\n".join(lines)
    # Find the first { ... balanced } and parse it.
    start = text.find("{")
    if start < 0:
        raise ValueError("no JSON object in extractor response")
    depth = 0
    end = -1
    for i, ch in enumerate(text[start:], start=start):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end < 0:
        raise ValueError("unbalanced JSON in extractor response")
    return json.loads(text[start:end])


def make_flagship_extractor(dispatch_fn: Callable[[str, str], str], basin_id: str) -> FlagshipExtractor:
    """Build the FlagshipExtractor production runs. dispatch_fn is injected so
    tests can mock it. Production wires through `providers.make_provider(...)`.

    `dispatch_fn(provider_name, prompt) -> response_text` is the same signature
    as the ask-dispatch shim. Default provider for cortex consolidation is
    claude (most reliable structured JSON output per spec-v1.5.md), but
    callers can vary it per basin to amortize cost across subs.
    """
    def _extract(outcomes: list[dict], geometry: dict | None = None) -> dict[str, Any]:
        prompt = build_extraction_prompt(basin_id, outcomes, geometry=geometry)
        response = dispatch_fn("claude", prompt)
        return parse_extraction_response(response)

    return _extract


def consolidate_all(
    *,
    dispatch_fn: Callable[[str, str], str],
    min_basin_size: int = 3,
) -> dict[str, RoutingPattern]:
    """Run the full consolidation pass: walk outcomes, group by basin, call
    the flagship extractor per basin, compute trust scores, return the
    patterns dict. Caller writes via save_routing_patterns.

    `min_basin_size` skips basins with too few outcomes — extraction quality
    is noise for n<3. Tuned in Week 2 calibration.
    """
    outcomes = iter_outcomes()
    grouped = group_outcomes_by_basin(outcomes)

    patterns: dict[str, RoutingPattern] = {}
    for basin_id, basin_outcomes in grouped.items():
        if len(basin_outcomes) < min_basin_size:
            continue
        extractor = make_flagship_extractor(dispatch_fn, basin_id)
        # task_kinds is just [basin_id] for v1.5 Week 2 since we use task_type
        # AS the basin. Week 3 the basin classifier maps multiple task_types
        # into one true basin and this list expands accordingly.
        # Diversity metric stub: use winner-distribution Shannon entropy as a
        # proxy until the basin classifier ships in Week 3.
        diversity = _entropy_diversity(basin_outcomes)
        patterns[basin_id] = consolidate_basin(
            basin_id=basin_id,
            outcomes=basin_outcomes,
            task_kinds=[basin_id],
            diversity_metric=diversity,
            extractor=extractor,
        )
    return patterns


def _entropy_diversity(outcomes: list[dict]) -> float:
    """Cheap diversity proxy: normalized Shannon entropy of the winner
    distribution. Real centroid-spread metric lands in Week 3 with the basin
    classifier. A basin where every outcome picked the same winner has
    entropy=0 → diversity=0 (the "basin" is a niche-artifact echo chamber).
    A basin where wins spread across 3 providers evenly has entropy≈1.
    """
    winners = [
        (o.get("routing_label") or {}).get("winner") or o.get("winner_provider")
        for o in outcomes
    ]
    winners = [w for w in winners if w]
    if not winners:
        return 0.5  # neutral when no data
    counts: dict[str, int] = {}
    for w in winners:
        counts[w] = counts.get(w, 0) + 1
    n = len(winners)
    entropy = -sum((c / n) * math.log(c / n) for c in counts.values())
    # Normalize against max entropy for 3 providers (log 3).
    max_entropy = math.log(3) if len(counts) >= 3 else math.log(max(2, len(counts)))
    return min(1.0, entropy / max_entropy) if max_entropy > 0 else 0.0
