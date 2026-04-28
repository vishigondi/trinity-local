"""Handlers for run, recommend, and scoreboard commands."""
from __future__ import annotations

import json
from pathlib import Path

from ..config import load_config
from ..coordinator import HeuristicCoordinator
from ..runner import run_task
from ..scoreboard import load_scoreboard


def register(subparsers):
    run_parser = subparsers.add_parser("run", help="Run the coordinator on a task")
    run_parser.add_argument("task", help="User task to solve")
    run_parser.add_argument("--task-kind", default=None, help="Task kind, e.g. coding")
    run_parser.add_argument("--cwd", default=".", help="Working directory for CLI providers")
    run_parser.set_defaults(handler=handle_run)

    recommend_parser = subparsers.add_parser("recommend", help="Show best model for a task kind")
    recommend_parser.add_argument("--task-kind", default="general", help="Task kind to inspect")
    recommend_parser.set_defaults(handler=handle_recommend)

    scoreboard_parser = subparsers.add_parser("scoreboard", help="Print aggregate provider scores")
    scoreboard_parser.set_defaults(handler=handle_scoreboard)


def handle_run(args):
    import sys
    print(
        "WARNING: The 'run' command is deprecated. Use your CLI directly "
        "(claude, gemini, codex) and let 'trinity-local watch-once' observe "
        "your sessions. See docs/product-spec.md for details.",
        file=sys.stderr,
    )
    config = load_config(args.config)
    task_kind = args.task_kind or config.default_task_kind
    outcome = run_task(
        config=config,
        task=args.task,
        task_kind=task_kind,
        cwd=Path(args.cwd).expanduser().resolve(),
    )
    payload = {
        "accepted": outcome.accepted,
        "final_provider": outcome.final_provider,
        "final_role": outcome.final_role,
        "final_text": outcome.final_text,
        "turns": outcome.turns,
    }
    print(json.dumps(payload, indent=2))


def handle_recommend(args):
    config = load_config(args.config)
    coordinator = HeuristicCoordinator(config)
    print(coordinator.recommendation(args.task_kind))


def handle_scoreboard(args):
    print(json.dumps(load_scoreboard(), indent=2, sort_keys=True))
