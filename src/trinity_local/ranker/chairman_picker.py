"""Pick the chairman = the strongest predicted model for the task.

Aligns the chairman role with the generator-verifier asymmetry: the strongest
model recognizes good answers best.

**Personal/global sigmoid blend** (v1.5 task #52). The previous lookup was a
hard cut: if ANY rated council existed for a task_kind, the personal pick
won outright — even at n=1, where the signal is statistically meaningless.
That left global benchmarks orphaned the moment a user ran their first
council. The blended path:

  alpha   = sigmoid((n - PERSONAL_MIDPOINT) / PERSONAL_STEEPNESS)
  blended = alpha * personal_overall + (1 - alpha) * global_overall

n is the count of personal councils for this task_kind. At n=0 → alpha ≈ 0
→ ~100% global. At n=PERSONAL_MIDPOINT (5) → alpha = 0.5 → equal blend. At
n=10 → alpha ≈ 0.99 → personal dominates. Smooth transition replaces the
hard cut; cold-start works on day 1 and personalization compounds.

Manual override (--primary-provider on the CLI) bypasses this entirely.
"""
from __future__ import annotations

import math

from ..global_benchmarks import get_global_benchmarks
from ..personal_routing import compute_personal_routing_table
from ..task_kinds import guess_task_kind


# Map Trinity task_kind → benchmark category. Aligned with the arena
# leaderboard's category names so this stays portable when external benchmarks
# come back online; sourced from `categories.CATEGORY_REGISTRY`.
from ..categories import task_kind_to_category as _registry_task_kind_to_category

_TASK_KIND_TO_BENCHMARK_CATEGORY: dict[str, str] = _registry_task_kind_to_category()


# Sigmoid tuning. Midpoint at 5 councils = 50% personal weight (the point
# where the user has enough signal that their data is comparable to a noisy
# external benchmark). Steepness 2 = transition spans roughly n=2 (mostly
# global) to n=8 (mostly personal).
PERSONAL_MIDPOINT = 5
PERSONAL_STEEPNESS = 2.0
# Per-provider overall score is in [0, 10] (chairman's overall is reported
# on a 0..10 scale). Global benchmark scores from arena are in [0, 100]
# (Elo-derived); rescale by /10 to make them commensurate before blending.
_GLOBAL_RESCALE = 0.1


def sigmoid_alpha(n: int) -> float:
    """Confidence in personal data given n councils in this task_kind.

    The same sigmoid the blend uses, exposed so the launchpad can render
    "X% personalized" badges that line up with the chairman's actual
    weighting. Single source of truth — if the curve gets tuned, every
    surface that displays it tracks the change.
    """
    return 1.0 / (1.0 + math.exp(-(n - PERSONAL_MIDPOINT) / PERSONAL_STEEPNESS))


# Backward-compat alias for any in-tree caller still using the private name.
_sigmoid_alpha = sigmoid_alpha


def _personal_scores(task_kind: str, available: list[str]) -> tuple[dict[str, float], int]:
    """Return ({provider: overall}, n_councils) from the personal routing table
    for this task_kind. Empty dict + n=0 when no data."""
    try:
        data = compute_personal_routing_table()
    except Exception:
        return {}, 0
    bucket = (data.get("by_task_type") or {}).get(task_kind) or {}
    scores: dict[str, float] = {}
    max_n = 0
    for provider, sub in bucket.items():
        if provider not in available:
            continue
        overall = sub.get("overall") if isinstance(sub, dict) else None
        if overall is None:
            continue
        scores[provider] = float(overall)
        max_n = max(max_n, int(sub.get("n", 0) or 0))
    return scores, max_n


def _global_scores(task_kind: str, available: list[str]) -> dict[str, float]:
    """Return {provider: rescaled_overall} from global benchmarks for this
    task_kind. Rescaled to [0, 10] to be commensurate with personal."""
    category = _TASK_KIND_TO_BENCHMARK_CATEGORY.get(task_kind, "reasoning")
    benchmarks = get_global_benchmarks().get(category) or {}
    models = benchmarks.get("models") or {}
    return {
        provider: float(score) * _GLOBAL_RESCALE
        for provider, score in models.items()
        if provider in available
    }


def _blended_pick(
    task_kind: str, available: list[str]
) -> tuple[str | None, dict]:
    """Sigmoid-blend personal vs global per provider; return the argmax and a
    debug payload describing the alpha and the contributing scores."""
    personal, n = _personal_scores(task_kind, available)
    glb = _global_scores(task_kind, available)
    alpha = _sigmoid_alpha(n)

    # Build the candidate set: any provider with at least one signal source.
    providers = set(personal) | set(glb)
    if not providers:
        return None, {"alpha": alpha, "n_personal": n, "blended": {}}

    blended: dict[str, float] = {}
    for p in providers:
        p_score = personal.get(p)
        g_score = glb.get(p)
        # If only one signal exists for a provider, that one carries weight 1.
        # Without this, a provider absent from global benchmarks but strong in
        # personal data would have its score halved at low n.
        if p_score is None:
            blended[p] = g_score or 0.0
        elif g_score is None:
            blended[p] = p_score
        else:
            blended[p] = alpha * p_score + (1.0 - alpha) * g_score

    best = max(blended.items(), key=lambda kv: kv[1])
    return best[0], {
        "alpha": round(alpha, 3),
        "n_personal": n,
        "blended": {p: round(s, 3) for p, s in blended.items()},
    }


def predict_strongest_chairman(
    task_text: str,
    *,
    available_providers: list[str],
) -> str:
    """Return the provider name that should chair the council for this task.

    Caller is responsible for ensuring `available_providers` only contains
    providers the user has configured + enabled. This function always returns
    a provider from that list (or an empty string if the list is empty).
    """
    if not available_providers:
        return ""
    task_kind = guess_task_kind(task_text)
    pick, _ = _blended_pick(task_kind, available_providers)
    if pick:
        return pick
    return available_providers[0]


def chairman_pick_reason(
    task_text: str,
    *,
    available_providers: list[str],
) -> dict[str, object]:
    """Return both the pick and a debug payload describing why it was picked.

    Useful for logging and for the `route` MCP tool that surfaces the reason.
    """
    if not available_providers:
        return {"chairman": "", "source": "none", "task_kind": ""}
    task_kind = guess_task_kind(task_text)
    pick, debug = _blended_pick(task_kind, available_providers)
    if pick is None:
        return {
            "chairman": available_providers[0],
            "source": "default_order",
            "task_kind": task_kind,
        }
    # source describes WHERE the signal was pulled from. With sigmoid blend
    # we report alpha + n so a caller (or telemetry) can see how trustworthy
    # the personal data is at the time of the pick.
    if debug["alpha"] >= 0.8:
        source = "personal_routing_table"
    elif debug["alpha"] <= 0.2:
        source = "global_benchmarks"
    else:
        source = "blended"
    return {
        "chairman": pick,
        "source": source,
        "task_kind": task_kind,
        "alpha": debug["alpha"],
        "n_personal": debug["n_personal"],
    }
