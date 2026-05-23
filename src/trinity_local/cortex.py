"""v1.5 cortex layer — extracted routing patterns per basin.

Hippocampus stores episodes (individual council outcomes). Cortex stores
extracted patterns across them. The brain works in two tiers; Trinity does too.

This module owns the cortex schema, the system-computed `trust_score`, and the
consolidation orchestration. The actual pattern extraction is a flagship-model
call that's injected via a callable — keeping it testable without LLM access,
and (in production) routed through whatever the user's strongest sub is.

The 6-component trust_score is the most load-bearing piece: it's what gates
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
    "n_episodes_norm": 0.22,
    "consistency_score": 0.22,
    "recency_agreement": 0.18,
    "diversity": 0.10,
    "coherence_score": 0.18,
    "audit_score": 0.10,
}

# Chairman-audit-mode (task #47). After consolidation extracts a rule via
# a primary flagship, an *independent* chairman (different provider) is
# asked to read the same outcomes and rate the rule. Disagreement is a
# drift signal — either the primary chairman rubber-stamped a provider
# too aggressively or a model silently regressed. Both are actionable;
# the audit catches them per scale-plan §8.9.
#
# Mapping is multiplicative-via-geometric-mean: a "disagreed" audit at
# weight 0.10 drops a 0.80 trust to ~0.63 (one band lower); "agreed"
# nudges trust up slightly without making weak rules look strong; the
# default "unaudited" stays neutral so opt-out users don't pay a
# penalty for not running the audit pass.
# Geomean identity for "no signal" is 1.0, not 0.5. Audit is opt-in;
# rules that weren't audited shouldn't be penalized for the user not
# running --audit. So unaudited contributes neutrally. The audit only
# helps catch FAILED rules — agreed=1.0 (same as unaudited, just signals
# it was run), disagreed=0.1 (strong demotion), unclear=0.5 (small
# penalty since the auditor punted).
AUDIT_SCORE_MAP = {
    "unaudited": 1.0,
    "agreed": 1.0,
    "disagreed": 0.1,
    "unclear": 0.5,
}


def audit_score_for(status: str) -> float:
    return AUDIT_SCORE_MAP.get(status, 0.5)

# Geometric helpers live in ``cortex_geometry.py``. Re-exported here for
# the back-compat aliases that tests still consume (`from .cortex import
# _xxx`). Tick 54 trimmed 5 zero-caller re-exports
# (BIMODALITY_KURTOSIS_THRESHOLD, MANIFOLD_DIM_SATURATION, euclid,
# mean_cosine_to, project_onto_first_pc) — those constants/helpers stay
# in cortex_geometry.py, just not aliased through here. See
# cortex_geometry.py for docs.
from .cortex_geometry import (  # noqa: F401 — re-export for back-compat
    compute_basin_geometry as _compute_basin_geometry,
    excess_kurtosis as _excess_kurtosis,
    participation_ratio as _participation_ratio,
    weiszfeld_median as _weiszfeld_median,
)

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
    """Per-provider failure shape extracted from disagreed_claims.

    The three named slots are fast-path conveniences for the canonical
    council providers (claude / codex / antigravity). Any other provider
    name falls into `other` and round-trips through to_dict / from_dict
    unchanged. The `antigravity` slot was renamed from `gemini` in tick
    63 (2026-05-20) — old on-disk patterns with "gemini" keys still
    load via the `other` dict path; from_dict normalizes them into the
    `antigravity` slot when reading legacy data."""

    claude: str | None = None
    codex: str | None = None
    antigravity: str | None = None
    other: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        out: dict[str, str] = {}
        if self.claude:
            out["claude"] = self.claude
        if self.codex:
            out["codex"] = self.codex
        if self.antigravity:
            out["antigravity"] = self.antigravity
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
    task_types: list[str]
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
    # Chairman-audit-mode verdict on this rule (task #47). One of
    # "unaudited" (default — opt-in via consolidate --audit), "agreed",
    # "disagreed", "unclear". Feeds the `audit_score` trust component
    # via AUDIT_SCORE_MAP. Persisted so a later --audit re-run can replace
    # the verdict without re-extracting the rule.
    audit_status: str = "unaudited"
    # User-veto count. Incremented by `trinity-local cortex-override
    # --basin <id>`. Each click halves effective trust via
    # ``effective_trust(pattern)``; 3+ overrides on a high-trust rule
    # drops it below TRUST_KNN_FALLBACK so the rule stops driving
    # routing. Persists across consolidations — the user's "this is
    # wrong" signal must not be erased by a fresh extraction (the
    # whole point is to teach the consolidator the rule was wrong).
    # Spec-v1.5 Week 5 ship item.
    override_count: int = 0

    def to_dict(self) -> dict:
        return {
            "basin_id": self.basin_id,
            "consolidated_at": self.consolidated_at,
            "n_episodes": self.n_episodes,
            "task_types": self.task_types,
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
            "audit_status": self.audit_status,
            "override_count": self.override_count,
        }


def compute_trust_score(
    *,
    n_episodes: int,
    winner_distribution: dict[str, float],
    rule_primary: str,
    recent_winners: list[str],
    diversity_metric: float,
    coherence_score: float = 0.5,
    audit_status: str = "unaudited",
) -> TrustScore:
    """Compute the 6-component trust score. All inputs are derivable from
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

    # 6. Audit score derived from audit_status. "unaudited" maps to 0.5
    # (neutral) so opt-out users don't pay a penalty for not running the
    # second-chairman pass; "agreed" rewards 0.9, "disagreed" demotes 0.1.
    audit = audit_score_for(audit_status)

    components = {
        "n_episodes_norm": n_norm,
        "consistency_score": consistency,
        "recency_agreement": recency,
        "diversity": diversity,
        "coherence_score": coherence,
        "audit_score": audit,
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


# Per-override multiplicative penalty. 0.5 chosen so:
#   - 1 override: trust × 0.5 (drops one full band: use-rule → kNN-fallback)
#   - 2 overrides: trust × 0.25 (deep in ignore-rule band)
#   - 3+ overrides: rule is effectively dead
# Anyone clicking "wrong" twice is sending a strong veto; the rule should
# stop driving routing immediately.
_OVERRIDE_PENALTY = 0.5


def effective_trust(pattern: "RoutingPattern") -> float:
    """Trust score with the user-veto penalty applied.

    The components in `pattern.trust_score` stay clean (data-quality
    signals only); overrides are a hard user veto layered on top. Callers
    that gate on trust (the cortex hot-path in ask, the launchpad sort
    order) must use THIS function, not `pattern.trust_score.value`,
    otherwise an overridden rule still drives routing.
    """
    if pattern.override_count <= 0:
        return pattern.trust_score.value
    return pattern.trust_score.value * (_OVERRIDE_PENALTY ** pattern.override_count)


def load_routing_patterns() -> dict[str, RoutingPattern]:
    """Read the cortex routing patterns from `~/.trinity/scoreboard/picks.json`.
    Empty dict if file doesn't exist. (Resolves via the back-compat
    `cortex_routing_patterns_path()` alias — function name preserved for
    backward compatibility; on-disk file moved cortex/ → memories/ →
    scoreboard/ in pre-launch migrations.)"""
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
    """Write the cortex routing patterns to `~/.trinity/scoreboard/picks.json`
    atomically. (Function name preserved; file path moved during pre-launch
    migrations — see `load_routing_patterns()` for lineage.)"""
    from .utils import atomic_write_text
    path = cortex_routing_patterns_path()
    serialized = {basin_id: p.to_dict() for basin_id, p in patterns.items()}
    atomic_write_text(path, json.dumps(serialized, indent=2))


def _pattern_from_dict(raw: dict) -> RoutingPattern:
    """Inverse of RoutingPattern.to_dict()."""
    rule = RoutingRule(**raw["routing_rule"])
    trust = TrustScore(
        value=raw["trust_score"]["value"],
        components=raw["trust_score"]["components"],
        computed_by=raw["trust_score"].get("computed_by", "system"),
    )
    fm_raw = raw.get("failure_modes", {})
    # Back-compat: pre-2026-05-20 patterns wrote `gemini`; new ones write
    # `antigravity`. Both can be present in old corpora; prefer the new
    # key, fall through to the legacy one.
    _ag_or_gemini = fm_raw.get("antigravity") or fm_raw.get("gemini")
    fm = FailureModes(
        claude=fm_raw.get("claude"),
        codex=fm_raw.get("codex"),
        antigravity=_ag_or_gemini,
        other={k: v for k, v in fm_raw.items() if k not in {"claude", "codex", "antigravity", "gemini"}},
    )
    return RoutingPattern(
        basin_id=raw["basin_id"],
        consolidated_at=raw["consolidated_at"],
        n_episodes=raw["n_episodes"],
        task_types=raw.get("task_types", []),
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
        audit_status=str(raw.get("audit_status", "unaudited") or "unaudited"),
        override_count=int(raw.get("override_count", 0) or 0),
    )


# Type alias for the injectable flagship extractor. Takes a list of council
# outcome dicts (for one basin) and returns the extracted (rule, failure_modes,
# successful_prompts) — what the flagship looked at the data and concluded.
# Production wires this through providers.make_provider(claude_opus).run(prompt).
# Tests inject a stub that returns canned values.
FlagshipExtractor = Callable[[list[dict]], dict[str, Any]]

# Type alias for the chairman-audit extractor (task #47). Given an
# already-extracted rule + the outcomes it was extracted from, returns one
# of "agreed" | "disagreed" | "unclear". Production passes a *different*
# provider than the primary extractor so the audit is independent.
RuleAuditor = Callable[[RoutingRule, list[dict]], str]


def consolidate_basin(
    *,
    basin_id: str,
    outcomes: list[dict],
    task_types: list[str],
    diversity_metric: float,
    extractor: FlagshipExtractor,
    auditor: RuleAuditor | None = None,
    prior_override_count: int = 0,
) -> RoutingPattern:
    """Run the consolidation pass for one basin: extract rule via flagship,
    optionally audit it via an independent chairman, compute trust_score
    via system, return the assembled RoutingPattern.

    Args:
        extractor: injectable flagship extractor (primary). Production
            wires through `providers.make_provider(claude_opus).run`. Tests
            pass a stub.
        auditor: optional independent chairman that reads the extracted
            rule + the same outcomes and returns a verdict (agreed /
            disagreed / unclear). When provided, the verdict feeds the
            audit_score trust component — disagreement demotes trust.
            None ⇒ audit_status stays "unaudited" (neutral). Should use a
            different provider than `extractor` to keep the check honest.
        prior_override_count: user-veto count carried over from the prior
            consolidation pass. The CLI's consolidate-all loop reads the
            existing pattern's override_count and passes it here so a
            fresh extraction doesn't erase the user's "this rule is
            wrong" signal. Default 0 = new basin / no prior overrides.
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
    # Back-compat: same legacy-"gemini" → "antigravity" normalization as
    # `_pattern_from_dict()` above. Both paths must accept old corpora.
    _ag_or_gemini = fm_dict.get("antigravity") or fm_dict.get("gemini")
    fm = FailureModes(
        claude=fm_dict.get("claude"),
        codex=fm_dict.get("codex"),
        antigravity=_ag_or_gemini,
        other={k: v for k, v in fm_dict.items() if k not in {"claude", "codex", "antigravity", "gemini"}},
    )
    successful_prompts = extracted.get("successful_prompts", {})

    # Evidence: cite the outcome ids the flagship saw. Cap at 20 to keep the
    # JSON small; full set is in council_outcomes/ anyway.
    evidence = [
        (o.get("council_id") or o.get("bundle_id") or "").strip()
        for o in outcomes
        if (o.get("council_id") or o.get("bundle_id"))
    ][:20]

    # Run the independent-chairman audit when one's wired in. Catches drift:
    # if the primary chairman always picks `claude` regardless of merit,
    # an audit chairman (different provider) reading the same outcomes
    # will disagree, and the audit_score trust component demotes the rule.
    audit_status = "unaudited"
    if auditor is not None:
        try:
            verdict = auditor(rule, outcomes)
            if verdict in AUDIT_SCORE_MAP:
                audit_status = verdict
        except Exception as exc:
            # An audit failure must not break consolidation, but it MUST
            # surface — a user who ran `consolidate --audit` and silently
            # got everything "unaudited" would have no idea their audit
            # provider was broken. Print to stderr so the CLI's per-basin
            # progress line shows the cause; trust component still falls
            # back to the neutral identity (1.0 for unaudited).
            import sys as _sys
            print(
                f"  ! audit failed for basin {basin_id!r}: "
                f"{type(exc).__name__}: {exc}",
                file=_sys.stderr,
            )
            audit_status = "unaudited"

    trust = compute_trust_score(
        n_episodes=n_episodes,
        winner_distribution=winner_distribution,
        rule_primary=rule.primary,
        recent_winners=recent_winners,
        diversity_metric=diversity_metric,
        coherence_score=geometry["coherence_score"],
        audit_status=audit_status,
    )

    return RoutingPattern(
        basin_id=basin_id,
        consolidated_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        n_episodes=n_episodes,
        task_types=task_types,
        winner_distribution=winner_distribution,
        routing_rule=rule,
        trust_score=trust,
        failure_modes=fm,
        successful_prompts=successful_prompts,
        evidence=evidence,
        basin_centroid=geometry["centroid"],
        manifold_dim=geometry["manifold_dim"],
        bimodal_flag=geometry["bimodal_flag"],
        audit_status=audit_status,
        override_count=prior_override_count,
    )


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
            # user_verdict field removed 2026-05-23 (post-launch sweep).
            # metadata.user_verdict is wipe-on-read in
            # council_runtime.load_council_outcome since #134
            # (rating-surface retirement) — the value was always None
            # here, just adding noise to the chairman's extraction prompt.
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
    "antigravity": "<...>"
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


def make_flagship_extractor(
    dispatch_fn: Callable[[str, str], str],
    basin_id: str,
    provider: str = "claude",
) -> FlagshipExtractor:
    """Build the FlagshipExtractor production runs. dispatch_fn is injected so
    tests can mock it. Production wires through `providers.make_provider(...)`.

    `dispatch_fn(provider_name, prompt) -> response_text` is the same signature
    as the ask-dispatch shim. ``provider`` defaults to claude (most reliable
    structured JSON output per spec-v1.5.md) but callers (the CLI's
    `--provider` flag, in particular) pass through whatever the user picked.

    Previously this hard-coded ``"claude"`` regardless of CLI choice — the
    closed-over dispatch shim swallowed the disagreement. The bug was
    invisible because both ignored each other; making both honor the
    provider arg surfaces real CLI control over the extraction provider.
    """
    def _extract(outcomes: list[dict], geometry: dict | None = None) -> dict[str, Any]:
        prompt = build_extraction_prompt(basin_id, outcomes, geometry=geometry)
        response = dispatch_fn(provider, prompt)
        return parse_extraction_response(response)

    return _extract


_AUDIT_VERDICTS = {"agreed", "disagreed", "unclear"}


def build_audit_prompt(rule: "RoutingRule", outcomes: list[dict]) -> str:
    """Build the prompt an independent chairman reads to audit an extracted
    rule. Asks for a single-word verdict so parsing stays trivial.
    """
    compressed: list[dict] = []
    for o in outcomes[:20]:  # smaller sample than extraction — audit needs less
        label = o.get("routing_label") or {}
        compressed.append({
            "council_id": o.get("council_run_id") or o.get("council_id"),
            "winner": label.get("winner") or o.get("winner_provider"),
            "routing_lesson": label.get("routing_lesson", ""),
            # user_verdict field removed 2026-05-23 — same dead-read
            # pattern as the extraction prompt above (#134 wiped this
            # field on read; chairman audit never saw a real value).
        })
    return f"""You are auditing a routing rule another chairman extracted from real council outcomes. Reply with exactly ONE word: agreed, disagreed, or unclear.

RULE BEING AUDITED:
  primary: {rule.primary}
  challenger: {rule.challenger or "none"}
  reason: {rule.reason}

EVIDENCE (council outcomes the rule was extracted from):
{json.dumps(compressed, indent=2)}

Question: does the evidence actually support primary={rule.primary!r} as the model to route this kind of question to?

Reply with ONE word, no JSON, no markdown, no explanation:
  agreed     — the evidence clearly backs the rule's primary
  disagreed  — the evidence points at a different primary
  unclear    — the evidence is mixed or insufficient
"""


def parse_audit_response(text: str) -> str:
    """Parse the audit chairman's one-word reply. Tolerant of surrounding
    whitespace, punctuation, markdown — but ONLY accepts one of the three
    canonical verdicts. Anything else returns "unclear" (safe default)."""
    first_word = ""
    for tok in text.strip().lower().replace(".", " ").replace(",", " ").split():
        cleaned = "".join(ch for ch in tok if ch.isalpha())
        if cleaned in _AUDIT_VERDICTS:
            return cleaned
        if not first_word and cleaned:
            first_word = cleaned
    return "unclear"


def make_rule_auditor(
    dispatch_fn: Callable[[str, str], str],
    audit_provider: str = "antigravity",
) -> RuleAuditor:
    """Build a RuleAuditor backed by `dispatch_fn(audit_provider, prompt)`.

    The default audit provider is `antigravity` so it differs from the
    primary extractor's default (`claude`). When the user's pool doesn't
    include antigravity, the CLI flag --audit-provider lets them pick
    another. An audit by the SAME provider that wrote the rule is worse
    than no audit at all, so the CLI refuses --audit-provider ==
    default-extractor-provider.
    """
    def _audit(rule: "RoutingRule", outcomes: list[dict]) -> str:
        prompt = build_audit_prompt(rule, outcomes)
        response = dispatch_fn(audit_provider, prompt)
        return parse_audit_response(response)

    return _audit


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
        # task_types is just [basin_id] for v1.5 Week 2 since we use task_type
        # AS the basin. Week 3 the basin classifier maps multiple task_types
        # into one true basin and this list expands accordingly.
        # Diversity metric stub: use winner-distribution Shannon entropy as a
        # proxy until the basin classifier ships in Week 3.
        diversity = _entropy_diversity(basin_outcomes)
        patterns[basin_id] = consolidate_basin(
            basin_id=basin_id,
            outcomes=basin_outcomes,
            task_types=[basin_id],
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
