"""Portal and review command handlers."""
from __future__ import annotations

import http.server
import json
import socketserver
import sys
import webbrowser
from pathlib import Path
from urllib.parse import quote

from ..council_review import write_unified_council_page
from ..council_runtime import load_council_outcome, load_prompt_bundle
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

    rlp = subparsers.add_parser(
        "review-link",
        help="Print mobile-safe links for a council review page",
    )
    rlp.add_argument("council_id", help="Council run id, e.g. council_abc123")
    rlp.add_argument("--json", dest="as_json", action="store_true")
    rlp.add_argument(
        "--web-base",
        default="https://trinity.openclaw.ai/app",
        help="Universal-link bootstrap base URL. Carries only the council id.",
    )
    rlp.add_argument(
        "--no-web",
        action="store_true",
        help="Omit the hosted universal-link bootstrap URL.",
    )
    rlp.set_defaults(handler=handle_review_link)

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


def _review_link_payload(council_id: str, review_path: Path, web_base: str | None) -> dict:
    safe_id = quote(council_id, safe="")
    resolved = review_path.expanduser().resolve()
    payload = {
        "council_id": council_id,
        "review_path": str(resolved),
        "file_url": resolved.as_uri(),
        "deep_link": f"trinity://review/{safe_id}",
        "content_source": "local_review_artifact_or_paired_desktop",
        "url_privacy": "URLs contain only the council id; review content stays local unless the user explicitly exports it.",
    }
    if web_base:
        payload["web_url"] = f"{web_base.rstrip('/')}/review/{safe_id}"
    return payload


def handle_review_link(args):
    outcome = load_council_outcome(args.council_id)
    bundle = load_prompt_bundle(outcome.bundle_id)
    review_path = write_unified_council_page(bundle, outcome)
    payload = _review_link_payload(
        outcome.council_run_id,
        review_path,
        None if args.no_web else args.web_base,
    )
    if args.as_json:
        print(json.dumps(payload, indent=2))
        return

    print(f"Review file: {payload['file_url']}")
    print(f"App link:    {payload['deep_link']}")
    if payload.get("web_url"):
        print(f"Web link:    {payload['web_url']}")
    print("Privacy:     URL carries only council_id; content loads from local review artifact or paired desktop.")


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
