"""Portal and review command handlers."""
from __future__ import annotations

import http.server
import json
import socketserver
import sys
import webbrowser
from pathlib import Path

from ..council_runtime import load_council_outcome
from ..notifications import open_path
from ..refresh import refresh_launchpad
from ..state_paths import review_pages_dir, trinity_home
from ..task_runtime import load_task_record


def register(subparsers):
    pp = subparsers.add_parser("portal-html", help="Generate a bookmarkable static launchpad page")
    pp.add_argument("--title", default="Trinity · Own your memories")
    pp.add_argument("--open-browser", action="store_true")
    pp.set_defaults(handler=handle_portal_html)

    orp = subparsers.add_parser("open-review", help="Open an existing review page for a task or outcome")
    orp.add_argument("--task", default=None)
    orp.add_argument("--outcome", default=None)
    orp.add_argument("--path", default=None)
    orp.set_defaults(handler=handle_open_review)

    sp = subparsers.add_parser(
        "serve",
        help="Serve ~/.trinity over HTTP so the launchpad works at http://localhost:PORT (alternative to file://)",
    )
    sp.add_argument("--port", type=int, default=8765)
    sp.add_argument("--open-browser", action="store_true", help="Open the launchpad in a browser tab")
    sp.set_defaults(handler=handle_serve)


def handle_portal_html(args):
    path = refresh_launchpad(title=args.title)
    opened = open_path(path) if args.open_browser else False
    print(json.dumps({"path": str(path), "opened": opened}, indent=2))


def handle_open_review(args):
    target = None
    if args.path:
        target = Path(args.path).expanduser().resolve()
    elif args.task:
        task = load_task_record(args.task)
        if task.review_page_path:
            target = Path(task.review_page_path).expanduser().resolve()
    elif args.outcome:
        outcome = load_council_outcome(args.outcome)
        target = review_pages_dir() / f"{outcome.council_run_id}.html"
    if target is None:
        raise SystemExit("error: open-review requires --path, --task, or --outcome with a recorded review page")
    opened = open_path(target)
    print(json.dumps({"path": str(target), "opened": opened}, indent=2))


def handle_serve(args):
    """Serve ~/.trinity over HTTP. Same launchpad/review pages render under
    file:// (double-click) AND http://localhost:PORT — page-data URLs are
    relative so both contexts resolve correctly. Useful when the user wants
    a stable URL to share with screen recorders, devtools, or playwright."""
    home = trinity_home()
    refresh_launchpad()  # ensure pages are fresh before serving

    handler = lambda *a, **kw: http.server.SimpleHTTPRequestHandler(*a, directory=str(home), **kw)
    try:
        httpd = socketserver.TCPServer(("127.0.0.1", args.port), handler)
    except OSError as exc:
        print(f"error: could not bind 127.0.0.1:{args.port} — {exc}", file=sys.stderr)
        raise SystemExit(1)

    url = f"http://127.0.0.1:{args.port}/portal_pages/launchpad.html"
    print(f"Trinity is serving {home} at http://127.0.0.1:{args.port}")
    print(f"Launchpad: {url}")
    print("Press Ctrl-C to stop.")
    if args.open_browser:
        webbrowser.open(url)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nstopped.")
        httpd.shutdown()
