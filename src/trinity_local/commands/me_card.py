"""trinity-local me-card — render the strongest /me lens as a 1200×630 PNG.

Per council_35b2ae198a65b349: F3 (zero user screenshots in 14 days) fires
by default unless we ship a frictionless export-to-image artifact. This
command IS that artifact.

Default writes to ~/.trinity/share/me_card.png so the user can drag-drop
into a tweet without specifying a path.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from ..me_card import collect_card_data, render_me_card
from ..state_paths import state_dir


def register(subparsers):
    parser = subparsers.add_parser(
        "me-card",
        help="Render your strongest /me lens as a 1200×630 PNG (for socials).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output path. Defaults to ~/.trinity/share/me_card.png.",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Write PNG bytes to stdout instead of a file (for piping).",
    )
    parser.set_defaults(handler=handle_me_card)


def handle_me_card(args):
    data = collect_card_data()
    png = render_me_card(data)

    if args.stdout:
        sys.stdout.buffer.write(png)
        return 0

    out = args.out or (state_dir() / "share" / "me_card.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(png)
    print(json.dumps({
        "ok": True,
        "path": str(out),
        "bytes": len(png),
        "lens_present": data.lens_pole_a is not None,
        "orderings_count": len(data.orderings or []),
    }, indent=2))
    return 0
