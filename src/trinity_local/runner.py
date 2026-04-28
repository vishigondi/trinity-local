from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .config import AppConfig
from .coordinator import HeuristicCoordinator
from .notifications import notify
from .prompts import build_prompt
from .providers import ProviderError, make_provider
from .scoreboard import append_run, update_provider_score


@dataclass
class RunOutcome:
    accepted: bool
    final_provider: str
    final_role: str
    final_text: str
    turns: list[dict[str, str | int]]


def run_task(
    *,
    config: AppConfig,
    task: str,
    task_kind: str,
    cwd: Path,
) -> RunOutcome:
    coordinator = HeuristicCoordinator(config)
    transcript: list[dict[str, str | int]] = []
    final_text = ""
    final_provider = ""
    final_role = ""
    accepted = False

    for turn in range(1, config.max_turns + 1):
        selection = coordinator.select(turn, task_kind)
        prompt = build_prompt(
            role=selection.role,
            task=task,
            task_kind=task_kind,
            transcript=transcript,
        )
        provider = make_provider(selection.provider)
        try:
            result = provider.run(prompt, cwd)
            content = result.stdout if result.stdout else result.stderr
            success = result.returncode == 0 and bool(content.strip())
        except ProviderError as exc:
            content = str(exc)
            success = False

        transcript.append(
            {
                "turn": turn,
                "role": selection.role,
                "provider": selection.provider.name,
                "content": content.strip(),
            }
        )
        update_provider_score(selection.provider.name, task_kind, success)

        final_text = content.strip()
        final_provider = selection.provider.name
        final_role = selection.role

        if selection.role == "verifier":
            upper = content.upper()
            if "ACCEPT" in upper:
                accepted = True
                break

    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "task": task,
        "task_kind": task_kind,
        "accepted": accepted,
        "final_provider": final_provider,
        "final_role": final_role,
        "turns": transcript,
    }
    append_run(record)

    if config.notifications:
        from .coordinator import HeuristicCoordinator as _Coordinator

        summary = _Coordinator(config).recommendation(task_kind)
        notify(
            "trinity-local",
            f"{summary}. Final: {final_provider}/{final_role}.",
        )

    return RunOutcome(
        accepted=accepted,
        final_provider=final_provider,
        final_role=final_role,
        final_text=final_text,
        turns=transcript,
    )
