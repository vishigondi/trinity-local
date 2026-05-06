"""Pick the chairman = the strongest predicted model for the task.

Aligns the chairman role with the generator-verifier asymmetry: the strongest
model recognizes good answers best. Lookup order:

1. compute_personal_routing_table().best_per_task_type[task_kind]
   — aggregated on demand from the user's own rated council outcomes. If
     present for this task_kind, always preferred.
2. global_benchmarks.py static priors mapped to task_kind. Cold-start.
3. First provider in available_providers (deterministic fallback).

Manual override (--primary-provider on the CLI) bypasses this entirely.
"""
from __future__ import annotations

from ..global_benchmarks import get_global_benchmarks
from ..personal_routing import compute_personal_routing_table
from ..task_kinds import guess_task_kind


# Map Trinity task_kind → benchmark category. Aligned with the arena
# leaderboard's category names so this stays portable when external benchmarks
# come back online; sourced from `categories.CATEGORY_REGISTRY`.
from ..categories import task_kind_to_category as _registry_task_kind_to_category

_TASK_KIND_TO_BENCHMARK_CATEGORY: dict[str, str] = _registry_task_kind_to_category()


def _personal_best(task_kind: str, available: list[str]) -> str | None:
    try:
        data = compute_personal_routing_table()
    except Exception:
        return None
    best_map = data.get("best_per_task_type") or {}
    candidate = best_map.get(task_kind)
    if isinstance(candidate, str) and candidate in available:
        return candidate
    return None


def _global_best(task_kind: str, available: list[str]) -> str | None:
    category = _TASK_KIND_TO_BENCHMARK_CATEGORY.get(task_kind, "reasoning")
    benchmarks = get_global_benchmarks().get(category) or {}
    models = benchmarks.get("models") or {}
    if not models:
        return None
    candidates = [(provider, score) for provider, score in models.items() if provider in available]
    if not candidates:
        return None
    candidates.sort(key=lambda pair: pair[1], reverse=True)
    return candidates[0][0]


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

    personal = _personal_best(task_kind, available_providers)
    if personal:
        return personal

    global_pick = _global_best(task_kind, available_providers)
    if global_pick:
        return global_pick

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
    personal = _personal_best(task_kind, available_providers)
    if personal:
        return {"chairman": personal, "source": "personal_routing_table", "task_kind": task_kind}
    global_pick = _global_best(task_kind, available_providers)
    if global_pick:
        return {"chairman": global_pick, "source": "global_benchmarks", "task_kind": task_kind}
    return {"chairman": available_providers[0], "source": "default_order", "task_kind": task_kind}
