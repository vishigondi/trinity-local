"""Handler for the digest command."""
from __future__ import annotations

import json
import subprocess
import sys

from ..digest import generate_digest, render_digest_html, render_digest_notification
from ..notifications import notify


def register(subparsers):
    parser = subparsers.add_parser("digest", help="Generate weekly activity digest")
    parser.add_argument("--days", type=int, default=7, help="Number of days to summarize")
    parser.add_argument("--notify", action="store_true", help="Send macOS notification")
    parser.add_argument("--open-browser", action="store_true", help="Open digest in browser")
    parser.add_argument("--json", dest="as_json", action="store_true", help="Output raw JSON")
    parser.set_defaults(handler=handle_digest)


def handle_digest(args):
    digest = generate_digest(period_days=args.days)

    if args.as_json:
        print(json.dumps(digest.to_dict(), indent=2))
        return

    html_path = render_digest_html(digest)
    summary = render_digest_notification(digest)
    print(summary)
    print(f"\nDigest saved to: {html_path}")

    if args.notify:
        notify(
            title="Trinity Weekly Digest",
            message=f"{digest.total_sessions} sessions, ~${digest.total_cost_usd:.2f}",
        )

    if args.open_browser:
        subprocess.run(["open", str(html_path)], check=False)
