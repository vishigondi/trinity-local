from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from .config import trinity_home


@dataclass
class ScoreEntry:
    provider: str
    task_kind: str
    score: float
    successes: int
    failures: int


def state_dir() -> Path:
    return trinity_home()


def scoreboard_path() -> Path:
    return state_dir() / "scoreboard.json"


def runs_path() -> Path:
    return state_dir() / "runs.jsonl"


def load_scoreboard() -> dict[str, dict[str, dict[str, float | int]]]:
    path = scoreboard_path()
    if not path.exists():
        return {}
    return json.loads(path.read_text())


def save_scoreboard(data: dict[str, dict[str, dict[str, float | int]]]) -> None:
    scoreboard_path().write_text(json.dumps(data, indent=2, sort_keys=True))


def append_run(record: dict) -> None:
    with runs_path().open("a") as handle:
        handle.write(json.dumps(record) + "\n")


def update_provider_score(provider: str, task_kind: str, success: bool) -> None:
    data = load_scoreboard()
    provider_entry = data.setdefault(provider, {})
    task_entry = provider_entry.setdefault(
        task_kind, {"score": 0.0, "successes": 0, "failures": 0}
    )

    if success:
        task_entry["successes"] += 1
        task_entry["score"] += 1.0
    else:
        task_entry["failures"] += 1
        task_entry["score"] -= 0.5

    save_scoreboard(data)


def best_provider_for_task(task_kind: str) -> tuple[str, float] | None:
    data = load_scoreboard()
    best_name: str | None = None
    best_score = float("-inf")
    for provider, provider_entry in data.items():
        task_entry = provider_entry.get(task_kind)
        if not task_entry:
            continue
        score = float(task_entry.get("score", 0.0))
        if score > best_score:
            best_name = provider
            best_score = score
    if best_name is None:
        return None
    return best_name, best_score
