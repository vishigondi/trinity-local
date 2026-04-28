"""Handlers for watch-once, watch-loop."""
from __future__ import annotations

import json

from ..watch_runtime import watch_loop, watch_once


def register(subparsers):
    wp = subparsers.add_parser("watch-once", help="Scan recent transcript changes and emit tasks/actions")
    wp.add_argument("--source", action="append", dest="sources", choices=["claude", "codex", "gemini", "cowork"], default=[])
    wp.add_argument("--notify", action="store_true")
    wp.set_defaults(handler=handle_watch_once)

    wlp = subparsers.add_parser("watch-loop", help="Poll transcript sources and keep emitting tasks/actions")
    wlp.add_argument("--source", action="append", dest="sources", choices=["claude", "codex", "gemini", "cowork"], default=[])
    wlp.add_argument("--notify", action="store_true")
    wlp.add_argument("--interval", type=int, default=30)
    wlp.set_defaults(handler=handle_watch_loop)


def handle_watch_once(args):
    sources = args.sources or ["cowork", "claude", "gemini", "codex"]
    result = watch_once(sources=sources, notify=args.notify)
    print(json.dumps({
        "sources": sources,
        "scanned": result.scanned,
        "tasks_written": result.tasks_written,
        "actions_written": result.actions_written,
        "portal_path": result.portal_path,
    }, indent=2))


def handle_watch_loop(args):
    sources = args.sources or ["cowork", "claude", "gemini", "codex"]
    watch_loop(sources=sources, notify=args.notify, interval_seconds=args.interval)
