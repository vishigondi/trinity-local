"""Handler for the status command — one-shot system summary + health check.

`status` absorbed the role of the (former) `doctor` command pre-launch: it
runs the same provider / MCP-dep / dir-writable pre-flight checks via
`trinity_local.doctor.run_doctor()` and prints a one-line health verdict
at the top of the human-readable output. JSON callers get the full report
under `"health"`. The standalone `doctor` CLI was retired in favor of this
single "tell me about Trinity" surface.
"""
from __future__ import annotations

import json

from ..adapters import check_all_adapters
from ..action_runtime import list_actions
from ..doctor import format_one_line, run_doctor
from ..drift import check_drift
from ..state_paths import state_dir, tasks_dir, analytics_dir


def register(subparsers):
    parser = subparsers.add_parser("status", help="Show Trinity system status summary + health check")
    parser.add_argument("--json", dest="as_json", action="store_true", help="Output as JSON")
    parser.set_defaults(handler=handle_status)


def _count_files(directory, pattern="*.json"):
    """Count files matching a glob in a directory."""
    try:
        return sum(1 for _ in directory.glob(pattern))
    except (OSError, FileNotFoundError):
        return 0


def _topics_summary(path) -> str:
    """Compact summary appended to the topics.json status row:
    "  · 20 basins · 18,184 turns across 12,041 threads".

    Returns empty on any failure — status output never crashes because
    of a malformed memory file (per claude.md "Analytics never crash").
    """
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        basins = payload.get("basins") or []
        if not basins:
            return ""
        total_turns = sum(int(b.get("size") or 0) for b in basins)
        thread_counts = [int(b.get("thread_count") or 0) for b in basins]
        if not any(thread_counts):
            # Legacy per-turn topics.json — emit a hint to refresh.
            return f"  · {len(basins)} basins · pre-thread-aware (run `trinity-local lens-build`)"
        total_threads = sum(thread_counts)
        return (
            f"  · {len(basins)} basins · {total_turns:,} turns"
            f" across {total_threads:,} threads"
        )
    except (OSError, ValueError, KeyError, TypeError):
        return ""


def handle_status(args):
    # Health (absorbed from former `doctor` command).
    health = run_doctor()

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
            "health": health.to_dict(),
            "adapters": {
                "ready": len(ready_adapters),
                "total": len(adapters),
                "total_transcripts": total_transcripts,
                "details": [a.to_dict() for a in adapters],
            },
            # Key matches the on-disk directory (~/.trinity/todos/) AND
            # the human "Todos:" display below. Internal Python name
            # `tasks_dir()` retained for back-compat with the v1.7
            # rename; external surfaces use the post-rename "todos".
            "todos": task_count,
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

    # Health (one-line verdict from doctor checks). Full per-check
    # detail surfaces on health failure via `--json` or by calling
    # run_doctor() / format_human() directly.
    print(f"  Health:    {format_one_line(health)}")
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
    # Display label matches the on-disk directory (~/.trinity/todos/);
    # internal Python name `tasks_dir()` retained for back-compat.
    print(f"  Todos:     {task_count}")
    print(f"  Actions:   {len(pending_actions)} pending, {len(completed_actions)} completed")
    print(f"  Reviews:   {review_count}")
    print(f"  Councils:  {council_count}")
    print()

    # Lens hierarchy + scoreboards. Per v1.7 architectural collapse,
    # the three thinking memories (lens / topics / vocabulary) + core.md
    # are what chairman reads as identity context; picks + routing are
    # operational scoreboards, surfaced separately. Reading paths from
    # state_paths so auto-migration kicks in transparently.
    from ..state_paths import (
        core_path, lens_path, picks_path, routing_path,
        topics_path, vocabulary_path,
    )
    print("  Memories:  (lens hierarchy — chairman identity context)")
    for label, path in [
        ("lens.md       ", lens_path()),
        ("topics.json   ", topics_path()),
        ("vocabulary.md ", vocabulary_path()),
    ]:
        if path.exists():
            size = path.stat().st_size
            extra = _topics_summary(path) if label.strip() == "topics.json" else ""
            print(f"    ✅ {label} {size:>8,} bytes{extra}")
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
        print("    · core.md       not distilled — run `trinity-local dream` (Phase 5 distills core.md)")
    print()
    print("  Scoreboards:  (operational model-selection bookkeeping)")
    for label, path in [
        ("picks.json    ", picks_path()),
        ("routing.json  ", routing_path()),
    ]:
        if path.exists():
            print(f"    ✅ {label} {path.stat().st_size:>8,} bytes")
        else:
            print(f"    · {label} not built")
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


