"""Handlers for `merges-show` — peek at the merge corpus.

Same shape as cache-stats: a small inspector for what's accumulated
in `~/.trinity/me/merges.jsonl`. Useful for verifying the side-channel
writers (council_winner / cortex_override / in_thread_overwrite) are
landing rows + sizing the corpus before plugging in a downstream
consumer (direction-of-preference vectors, view-over-merges lens).
"""
from __future__ import annotations

import json


def register(subparsers):
    sp = subparsers.add_parser(
        "merges-show",
        help="Show counts of merge-log rows by type (and signal_type for in_thread_overwrite)",
    )
    sp.add_argument("--json", dest="as_json", action="store_true", help="Output as JSON")
    sp.set_defaults(handler=handle_merges_show)


def handle_merges_show(args):
    from ..merges import summarize_merges, merges_path

    summary = summarize_merges()
    payload = {**summary, "path": str(merges_path())}

    if args.as_json:
        print(json.dumps(payload, indent=2))
        return

    print("  Merge log")
    print(f"    Total rows:  {summary['total']:,}")
    if summary["first_ts"]:
        print(f"    First:       {summary['first_ts']}")
    if summary["last_ts"]:
        print(f"    Last:        {summary['last_ts']}")
    print(f"    Path:        {merges_path()}")
    if summary["by_type"]:
        print()
        print("  By type")
        for rtype, count in sorted(summary["by_type"].items(), key=lambda x: -x[1]):
            print(f"    {rtype:30s} {count:>5,}")
    if summary["by_signal_type"]:
        print()
        print("  in_thread_overwrite signals")
        for sig, count in sorted(summary["by_signal_type"].items(), key=lambda x: -x[1]):
            print(f"    {sig:30s} {count:>5,}")
    print()
