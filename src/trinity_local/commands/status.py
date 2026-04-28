"""Handler for the status command — one-shot system summary."""
from __future__ import annotations

import json

from ..adapters import check_all_adapters
from ..action_runtime import list_actions
from ..cost_tracker import load_cost_log, summarize_costs
from ..drift import check_drift
from ..scoreboard import state_dir
from ..task_runtime import tasks_dir


def register(subparsers):
    parser = subparsers.add_parser("status", help="Show Trinity system status summary")
    parser.add_argument("--json", dest="as_json", action="store_true", help="Output as JSON")
    parser.set_defaults(handler=handle_status)


def _count_files(directory, pattern="*.json"):
    """Count files matching a glob in a directory."""
    try:
        return sum(1 for _ in directory.glob(pattern))
    except (OSError, FileNotFoundError):
        return 0


def handle_status(args):
    # Adapters
    adapters = check_all_adapters()
    ready_adapters = [a for a in adapters if a.installed]
    total_transcripts = sum(a.transcript_count for a in adapters)

    # Tasks
    task_count = _count_files(tasks_dir())

    # Actions
    pending_actions = list_actions(status="pending")
    completed_actions = list_actions(status="completed")

    # Costs
    cost_log = load_cost_log()
    cost_summary = summarize_costs(cost_log) if cost_log else {}

    # Drift
    drift_alerts = check_drift()

    # State dir
    home = state_dir()

    # Reviews
    reviews_dir = home / "reviews"
    review_count = _count_files(reviews_dir) if reviews_dir.exists() else 0

    # Council outcomes
    council_dir = home / "council_outcomes"
    council_count = _count_files(council_dir) if council_dir.exists() else 0

    if args.as_json:
        print(json.dumps({
            "trinity_home": str(home),
            "adapters": {
                "ready": len(ready_adapters),
                "total": len(adapters),
                "total_transcripts": total_transcripts,
                "details": [a.to_dict() for a in adapters],
            },
            "tasks": task_count,
            "actions": {
                "pending": len(pending_actions),
                "completed": len(completed_actions),
            },
            "reviews": review_count,
            "councils": council_count,
            "cost_sessions": len(cost_log),
            "cost_by_provider": {k: v.total_cost_usd for k, v in cost_summary.items()} if cost_summary else {},
            "drift_alerts": len(drift_alerts),
        }, indent=2))
        return

    # Human-readable output
    print("┌─────────────────────────────────────────┐")
    print("│         Trinity Local — Status           │")
    print("└─────────────────────────────────────────┘")
    print()

    # Adapters
    print(f"  Adapters:  {len(ready_adapters)}/{len(adapters)} ready, {total_transcripts:,} transcripts total")
    for a in adapters:
        icon = "✅" if a.installed else "❌"
        ver = f" ({a.version})" if a.version else ""
        count = f" · {a.transcript_count:,} files" if a.transcript_root else ""
        print(f"    {icon} {a.provider}{ver}{count}")
    print()

    # Tasks & Actions
    print(f"  Tasks:     {task_count}")
    print(f"  Actions:   {len(pending_actions)} pending, {len(completed_actions)} completed")
    print(f"  Reviews:   {review_count}")
    print(f"  Councils:  {council_count}")
    print()

    # Costs
    if cost_summary:
        print(f"  Cost log:  {len(cost_log)} sessions tracked")
        for provider, summary in sorted(cost_summary.items()):
            print(f"    {provider}: ${summary.total_cost_usd:.4f}")
    else:
        print("  Cost log:  no sessions tracked yet")
    print()

    # Drift
    if drift_alerts:
        print(f"  ⚠  {len(drift_alerts)} drift alert(s):")
        for alert in drift_alerts:
            print(f"    · {alert.message}")
    else:
        print("  Drift:     no alerts")
    print()

    # State location
    print(f"  State:     {home}")
    print()
