"""Handlers for portal-html, open-review."""
from __future__ import annotations

import json
from pathlib import Path

from ..council_review import review_pages_dir
from ..council_runtime import load_council_outcome
from ..notifications import open_path
from ..refresh import refresh_launchpad
from ..task_runtime import load_task_record


def register(subparsers):
    pp = subparsers.add_parser("portal-html", help="Generate a bookmarkable static launchpad page")
    pp.add_argument("--title", default="Trinity Launchpad")
    pp.add_argument("--video-url", default=None)
    pp.add_argument("--open-browser", action="store_true")
    pp.set_defaults(handler=handle_portal_html)

    orp = subparsers.add_parser("open-review", help="Open an existing review page for a task or outcome")
    orp.add_argument("--task", default=None)
    orp.add_argument("--outcome", default=None)
    orp.add_argument("--path", default=None)
    orp.set_defaults(handler=handle_open_review)


def handle_portal_html(args):
    path = refresh_launchpad(title=args.title, video_url=args.video_url)
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
