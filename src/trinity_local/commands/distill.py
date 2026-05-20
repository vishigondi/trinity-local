"""Importable utility — Phase 5 distillation handlers.

The standalone `trinity-local distill` and `core-show` CLIs were retired
in the pre-launch simplification (2026-05-18, retirement registry).
`dream` Phase 5 calls `distill_via_chairman` directly; tests still import
`handle_distill` / `handle_core_show` for handler-level coverage. No
`register(subparsers)` here — main.py doesn't import this module into
the CLI surface.
"""
from __future__ import annotations

import json


def handle_distill(args):
    from ..distill import distill_via_chairman

    report = distill_via_chairman(provider=args.provider, force=getattr(args, "force", False))
    print(json.dumps(report, indent=2))
    return 0 if report.get("ok") else 1


def handle_core_show(args):
    """Print core.md verbatim. Symmetric with `lens-show` for the lens.

    Cold-install path: print a hint pointing at `dream` rather than an
    empty file. The standalone `distill` CLI was retired pre-launch; the
    rebuild path is now `trinity-local dream` (Phase 5 of dream runs
    distill_via_chairman over the three thinking memories).
    """
    import sys
    from ..state_paths import core_path
    path = core_path()
    if not path.exists():
        print(
            "# core.md not distilled yet — run `trinity-local dream`",
            file=sys.stderr,
        )
        print(f"# expected at: {path}", file=sys.stderr)
        return 1
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        print(
            "# core.md is empty — run `trinity-local dream`",
            file=sys.stderr,
        )
        return 1
    print(text)
    return 0
