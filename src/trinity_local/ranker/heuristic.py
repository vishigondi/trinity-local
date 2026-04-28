"""Heuristic ranker: task-kind-based routing with outcome/cost evidence."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from .base import Ranker
from .types import RoutingContext, RoutingDecision


class HeuristicRanker(Ranker):
    """Routes based on task_kind (research/coding/debugging/general).

    Evidence comes from recent session outcomes and cost comparisons.
    Recommendations: research→gemini, coding→codex, default→claude.
    Confidence is fixed by task_kind (0.72/0.68/0.55).
    """

    def advise(self, context: RoutingContext) -> RoutingDecision:
        """Advise based on task_kind with outcome/cost evidence."""
        task_kind = context.task_kind
        evidence = self._gather_evidence(context)

        if task_kind in {"research", "cowork_general"}:
            return RoutingDecision(
                recommended_provider="gemini",
                top_k=["gemini", "codex"],
                needs_council=True,
                confidence=0.72,
                evidence=evidence + [
                    "Gemini is likely stronger for broad research and comparison."
                ],
                backend="heuristic",
            )
        if task_kind in {"coding", "debugging"}:
            return RoutingDecision(
                recommended_provider="codex",
                top_k=["codex", "claude"],
                needs_council=True,
                confidence=0.68,
                evidence=evidence + [
                    "Codex is likely stronger for execution-heavy coding work."
                ],
                backend="heuristic",
            )
        return RoutingDecision(
            recommended_provider="claude",
            top_k=[],
            needs_council=False,
            confidence=0.55,
            evidence=evidence + [
                "Claude is still the best default for this task shape."
            ],
            backend="heuristic",
        )

    def _gather_evidence(self, context: RoutingContext) -> list[str]:
        """Query outcome and cost logs to build evidence."""
        from ..cost_tracker import load_cost_log
        from ..drift import _load_outcomes

        evidence: list[str] = []

        # Check recent outcomes for this provider + task kind
        try:
            outcomes = _load_outcomes()
            provider_outcomes = [
                o for o in outcomes
                if o.provider == context.current_provider and o.task_kind == context.task_kind
            ]
            if len(provider_outcomes) >= 3:
                completed = sum(1 for o in provider_outcomes[-10:] if o.completed)
                total = min(len(provider_outcomes), 10)
                rate = completed / total
                evidence.append(
                    f"{context.current_provider} completed {completed}/{total} recent {context.task_kind} tasks "
                    f"({rate:.0%} completion rate)."
                )
                errored = sum(1 for o in provider_outcomes[-10:] if o.error_count > 0)
                if errored > 0:
                    evidence.append(
                        f"{errored}/{total} of those sessions had tool errors."
                    )
        except Exception:
            pass  # Gracefully degrade if outcome logs unavailable

        # Compare providers by cost for this task kind
        try:
            costs = load_cost_log(since_days=14)
            task_costs = [c for c in costs if c.task_kind == context.task_kind]
            if task_costs:
                by_provider: dict[str, list[float]] = {}
                for c in task_costs:
                    by_provider.setdefault(c.provider, []).append(c.total_cost_usd)
                for p, p_costs in sorted(by_provider.items()):
                    if p != context.current_provider and len(p_costs) >= 2:
                        avg = sum(p_costs) / len(p_costs)
                        evidence.append(
                            f"{p} averaged ${avg:.2f}/session for {context.task_kind} ({len(p_costs)} sessions)."
                        )
        except Exception:
            pass  # Gracefully degrade if cost logs unavailable

        return evidence
