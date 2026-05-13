"""Handler for the adapters command — provider adapter discovery and status."""
from __future__ import annotations

import json

from ..adapters import check_all_adapters


def register(subparsers):
    parser = subparsers.add_parser("adapters", help="Show provider adapter status")
    parser.add_argument("--json", dest="as_json", action="store_true", help="Output as JSON")
    parser.set_defaults(handler=handle_adapters)


def handle_adapters(args):
    statuses = check_all_adapters()

    if args.as_json:
        print(json.dumps([s.to_dict() for s in statuses], indent=2))
        return

    # Human-readable table
    print(f"{'Provider':<12} {'CLI':<18} {'Status':<12} {'Version':<30} {'Transcripts':>12}")
    print("-" * 90)
    for s in statuses:
        status = "✅ ready" if s.installed else "❌ missing"
        version = s.version or "(n/a)"
        count = str(s.transcript_count) if s.transcript_root else "-"
        print(f"{s.provider:<12} {s.cli_name:<18} {status:<12} {version:<30} {count:>12}")
        if s.error:
            print(f"  ⚠  {s.error}")
    print()
    ready = sum(1 for s in statuses if s.installed)
    total = len(statuses)
    print(f"{ready}/{total} adapters ready. Trinity needs at least 2 for cross-provider insights.")
