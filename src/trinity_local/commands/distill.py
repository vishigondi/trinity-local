"""`trinity-local distill` — Phase 5 stand-alone.

Reads the three thinking core memories (lens, topics, vocabulary) under `~/.trinity/memories/` and emits a
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
        help="Distill the three thinking core memories (lens, topics, vocabulary) into ~/.trinity/core.md (one paragraph the chairman reads first on every council).",
    )
    sp.add_argument(
        "--provider",
        default="claude",
        help="Chairman provider for the distillation pass (default: claude).",
    )
    sp.add_argument(
        "--force",
        action="store_true",
        help="Re-distill even if core.md is already newer than every source memory.",
    )
    sp.set_defaults(handler=handle_distill)

    show = subparsers.add_parser(
        "core-show",
        help="Print the current ~/.trinity/core.md content (the singular distilled identity the chairman reads first).",
    )
    show.set_defaults(handler=handle_core_show)


def handle_distill(args):
    from ..distill import distill_via_chairman

    report = distill_via_chairman(provider=args.provider, force=getattr(args, "force", False))
    print(json.dumps(report, indent=2))
    return 0 if report.get("ok") else 1


def handle_core_show(args):
    """Print core.md verbatim. Symmetric with `lens-show` for the lens.

    Cold-install path: print a hint pointing at `distill` rather than an
    empty file.
    """
    import sys
    from ..state_paths import core_path
    path = core_path()
    if not path.exists():
        print(
            "# core.md not distilled yet — run `trinity-local distill`",
            file=sys.stderr,
        )
        print(f"# expected at: {path}", file=sys.stderr)
        return 1
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        print(
            "# core.md is empty — run `trinity-local distill --force`",
            file=sys.stderr,
        )
        return 1
    print(text)
    return 0
