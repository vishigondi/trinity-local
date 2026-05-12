"""Handler for the status command — one-shot system summary."""
from __future__ import annotations

import json

from ..adapters import check_all_adapters
from ..action_runtime import list_actions
from ..drift import check_drift
from ..scoreboard import load_scoreboard
from ..state_paths import state_dir, tasks_dir, analytics_dir


def register(subparsers):
    parser = subparsers.add_parser("status", help="Show Trinity system status summary")
    parser.add_argument("--json", dest="as_json", action="store_true", help="Output as JSON")
    parser.set_defaults(handler=handle_status)

    scoreboard_parser = subparsers.add_parser("scoreboard", help="Print aggregate provider scores")
    scoreboard_parser.set_defaults(handler=handle_scoreboard)


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

    # Watch errors
    watch_error_count, last_watch_error = _watch_error_summary()

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
            "drift_alerts": len(drift_alerts),
            "watch_errors": {
                "count": watch_error_count,
                "last_error_at": last_watch_error,
            },
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

    # Core memories — the five plural memories dream creates + the
    # singular core.md distillation. Reading paths from state_paths so
    # auto-migration kicks in transparently.
    from ..state_paths import (
        core_path, lens_path, picks_path, routing_path,
        topics_path, vocabulary_path,
    )
    print("  Memories:")
    for label, path in [
        ("lens.md       ", lens_path()),
        ("picks.json    ", picks_path()),
        ("routing.json  ", routing_path()),
        ("topics.json   ", topics_path()),
        ("vocabulary.md ", vocabulary_path()),
    ]:
        if path.exists():
            size = path.stat().st_size
            print(f"    ✅ {label} {size:>8,} bytes")
        else:
            print(f"    · {label} not built")
    core = core_path()
    if core.exists():
        # Show whether core is fresh vs stale relative to its source memories.
        from ..distill import is_core_stale
        stale = is_core_stale()
        marker = "⚠️ stale" if stale else "✅ fresh"
        print(f"    {marker} core.md       {core.stat().st_size:>8,} bytes — chairman reads this first")
    else:
        print(f"    · core.md       not distilled — run `trinity-local distill`")
    print()

    # Drift
    if drift_alerts:
        print(f"  ⚠  {len(drift_alerts)} drift alert(s):")
        for alert in drift_alerts:
            print(f"    · {alert.message}")
    else:
        print("  Drift:     no alerts")
    print()

    # Watch errors
    if watch_error_count > 0:
        print(f"  ⚠  {watch_error_count} watch-loop error(s)")
        if last_watch_error:
            print(f"    Last error: {last_watch_error}")
    else:
        print("  Watch:     no errors")
    print()

    # State location
    print(f"  State:     {home}")
    print()


def _watch_error_summary() -> tuple[int, str | None]:
    """Return (error_count, last_error_timestamp) from watch_errors.jsonl."""
    error_log = analytics_dir() / "watch_errors.jsonl"
    if not error_log.exists():
        return 0, None
    count = 0
    last_ts: str | None = None
    try:
        for line in error_log.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            count += 1
            try:
                record = json.loads(line)
                last_ts = record.get("timestamp", last_ts)
            except json.JSONDecodeError:
                continue
    except OSError:
        pass
    return count, last_ts


def handle_scoreboard(args):
    print(json.dumps(load_scoreboard(), indent=2, sort_keys=True))
