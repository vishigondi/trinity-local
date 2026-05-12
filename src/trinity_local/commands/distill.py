"""`trinity-local distill` — Phase 5 stand-alone.

Reads the five core memories under `~/.trinity/memories/` and emits a
one-paragraph distillation to `~/.trinity/core.md`. The chairman reads
`core.md` first on every council; this command keeps that summary fresh.

Also runs as Phase 5 of `trinity-local dream`. Use standalone when you've
updated the lens or cortex manually and don't need a full dream pass.
"""
from __future__ import annotations

import json


def register(subparsers):
    sp = subparsers.add_parser(
        "distill",
        help="Distill the five core memories into ~/.trinity/core.md (one paragraph the chairman reads first on every council).",
    )
    sp.add_argument(
        "--provider",
        default="claude",
        help="Chairman provider for the distillation pass (default: claude).",
    )
    sp.set_defaults(handler=handle_distill)


def handle_distill(args):
    from ..distill import distill_via_chairman

    report = distill_via_chairman(provider=args.provider)
    print(json.dumps(report, indent=2))
    return 0 if report.get("ok") else 1
