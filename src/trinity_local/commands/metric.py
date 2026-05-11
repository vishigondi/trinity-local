"""`trinity-local metric rate-limit-saves` — the case-study number named in
`docs/launch-package.md`. Reads ~/.trinity/analytics/dispatch_outcomes.jsonl
and prints aggregate stats over a window.

Day-1 metric. Every public claim about Trinity's value over the first 90 days
of public use needs a number behind it. This is that number.
"""
from __future__ import annotations

import json


def register(subparsers):
    sp = subparsers.add_parser(
        "metric",
        help="Read Trinity's dispatch-outcomes metric (rate-limit-saves and friends)",
    )
    sp.add_argument(
        "name",
        nargs="?",
        default="rate-limit-saves",
        choices=["rate-limit-saves", "dispatch-summary"],
        help="Which metric to print (default: rate-limit-saves)",
    )
    sp.add_argument(
        "--days",
        type=int,
        default=30,
        help="Window in days (default: 30)",
    )
    sp.add_argument("--json", dest="as_json", action="store_true", help="Output as JSON")
    sp.set_defaults(handler=handle_metric)


def handle_metric(args):
    from datetime import datetime, timezone, timedelta

    from ..state_paths import dispatch_outcomes_path

    path = dispatch_outcomes_path()
    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)

    entries: list[dict] = []
    if path.exists():
        with path.open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                try:
                    ts = datetime.fromisoformat(entry["ts"].replace("Z", "+00:00"))
                except (KeyError, ValueError):
                    continue
                if ts >= cutoff:
                    entries.append(entry)

    if args.name == "rate-limit-saves":
        # Count entries where Trinity routed around a primary failure.
        saves = [e for e in entries if e.get("rate_limit_save")]
        by_kind: dict[str, int] = {}
        by_primary: dict[str, int] = {}
        for e in saves:
            kind = e.get("failure_kind") or "unknown"
            by_kind[kind] = by_kind.get(kind, 0) + 1
            by_primary[e.get("primary", "?")] = by_primary.get(e.get("primary", "?"), 0) + 1
        report = {
            "metric": "rate-limit-saves",
            "window_days": args.days,
            "total_saves": len(saves),
            "total_ask_calls": len(entries),
            "save_rate": round(len(saves) / max(1, len(entries)), 3),
            "by_failure_kind": by_kind,
            "by_primary_provider": by_primary,
        }
    elif args.name == "dispatch-summary":
        succeeded_first_try = sum(1 for e in entries if e.get("retries", 0) == 0 and e.get("succeeded_on"))
        succeeded_after_retry = sum(1 for e in entries if e.get("retries", 0) > 0 and e.get("succeeded_on"))
        all_failed = sum(1 for e in entries if not e.get("succeeded_on"))
        report = {
            "metric": "dispatch-summary",
            "window_days": args.days,
            "total_calls": len(entries),
            "succeeded_first_try": succeeded_first_try,
            "succeeded_after_retry": succeeded_after_retry,
            "all_failed": all_failed,
        }
    else:
        report = {"ok": False, "reason": f"unknown metric: {args.name}"}

    if args.as_json:
        print(json.dumps(report, indent=2))
    else:
        # Human-readable
        print(f"Trinity metric · {report.get('metric', 'unknown')} · last {args.days} days")
        for k, v in report.items():
            if k in {"metric", "window_days"}:
                continue
            print(f"  {k}: {v}")
    return 0
