"""trinity-local doctor — pre-flight checks for cold-install / launch-readiness.

Per council_35b2ae198a65b349 eval seed: name a specific cold-install
failure mode AND the exact CLI command that detects it before the
user hits a live council.
"""
from __future__ import annotations

import json

from ..doctor import format_human, run_doctor


def register(subparsers):
    parser = subparsers.add_parser(
        "doctor",
        help="Pre-flight checks: providers installed, authenticated, Trinity dir writeable.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit a JSON report (for harness use). Default is human-readable.",
    )
    parser.set_defaults(handler=handle_doctor)


def handle_doctor(args):
    report = run_doctor()
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(format_human(report))
    if not report.ready_for_council:
        return 2
    if not report.all_ok:
        return 1
    return 0
