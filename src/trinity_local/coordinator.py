from __future__ import annotations

from dataclasses import dataclass

from .config import AppConfig, ProviderConfig
from .scoreboard import best_provider_for_task


ROLES = ("thinker", "worker", "verifier")


@dataclass
class Selection:
    role: str
    provider: ProviderConfig
    reason: str


class HeuristicCoordinator:
    def __init__(self, config: AppConfig) -> None:
        self.config = config

    def select(self, turn: int, task_kind: str) -> Selection:
        role = self._role_for_turn(turn)
        provider = self._provider_for(role, task_kind)
        reason = f"turn={turn} role={role} provider={provider.name}"
        return Selection(role=role, provider=provider, reason=reason)

    def recommendation(self, task_kind: str) -> str:
        best = best_provider_for_task(task_kind)
        if best:
            return f"{best[0]} is currently leading for {task_kind} with score {best[1]:.1f}"
        ordered = self.config.task_preferences.get(task_kind) or self.config.task_preferences.get(
            self.config.default_task_kind, []
        )
        if ordered:
            return f"{ordered[0]} is the default recommendation for {task_kind}"
        return "No recommendation yet"

    def _role_for_turn(self, turn: int) -> str:
        if turn == 1:
            return "thinker"
        if turn >= self.config.max_turns:
            return "verifier"
        if turn % 2 == 0:
            return "worker"
        return "verifier"

    def _provider_for(self, role: str, task_kind: str) -> ProviderConfig:
        scored = best_provider_for_task(task_kind)
        if scored:
            candidate = self.config.providers.get(scored[0])
            if candidate and self._supports(candidate, role, task_kind):
                return candidate

        for name in self.config.task_preferences.get(task_kind, []):
            provider = self.config.providers.get(name)
            if provider and self._supports(provider, role, task_kind):
                return provider

        for name in self.config.role_preferences.get(role, []):
            provider = self.config.providers.get(name)
            if provider and self._supports(provider, role, task_kind):
                return provider

        for provider in self.config.providers.values():
            if self._supports(provider, role, task_kind):
                return provider

        raise RuntimeError(f"No enabled provider supports role={role} task_kind={task_kind}")

    @staticmethod
    def _supports(provider: ProviderConfig, role: str, task_kind: str) -> bool:
        return (
            provider.enabled
            and role in provider.roles
            and (task_kind in provider.task_kinds or "general" in provider.task_kinds)
        )
