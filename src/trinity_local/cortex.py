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
    "n_episodes_norm": 0.30,
    "consistency_score": 0.30,
    "recency_agreement": 0.25,
    "diversity": 0.15,
}

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
        }


def compute_trust_score(
    *,
    n_episodes: int,
    winner_distribution: dict[str, float],
    rule_primary: str,
    recent_winners: list[str],
    diversity_metric: float,
) -> TrustScore:
    """Compute the 4-component trust score. All inputs are derivable from
    accumulated council outcomes; no flagship-declared values.

    Args:
        n_episodes: count of outcomes in this basin
        winner_distribution: {provider: fraction} from outcomes
        rule_primary: provider name the flagship chose as primary
        recent_winners: last 10 winner_providers in chronological order
        diversity_metric: 0..1, average embed-distance spread within basin

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

    components = {
        "n_episodes_norm": n_norm,
        "consistency_score": consistency,
        "recency_agreement": recency,
        "diversity": diversity,
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

    # Flagship extracts the rule + failure modes + successful prompt templates.
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

    trust = compute_trust_score(
        n_episodes=n_episodes,
        winner_distribution=winner_distribution,
        rule_primary=rule.primary,
        recent_winners=recent_winners,
        diversity_metric=diversity_metric,
    )

    # Evidence: cite the outcome ids the flagship saw. Cap at 20 to keep the
    # JSON small; full set is in council_outcomes/ anyway.
    evidence = [
        (o.get("council_id") or o.get("bundle_id") or "").strip()
        for o in outcomes
        if (o.get("council_id") or o.get("bundle_id"))
    ][:20]

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
