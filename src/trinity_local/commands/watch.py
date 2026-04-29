"""Handlers for watch-once, watch-loop."""
from __future__ import annotations

import json

from ..council_status import write_council_status
from ..watch_runtime import watch_loop, watch_once


def register(subparsers):
    wp = subparsers.add_parser("watch-once", help="Scan recent transcript changes and emit tasks/actions")
    wp.add_argument("--source", action="append", dest="sources", choices=["claude", "codex", "gemini", "cowork"], default=[])
    wp.add_argument("--notify", action="store_true")
    wp.add_argument("--status-token", default=None, help="Launchpad status token for one-shot ingest progress")
    wp.set_defaults(handler=handle_watch_once)

    wlp = subparsers.add_parser("watch-loop", help="Poll transcript sources and keep emitting tasks/actions")
    wlp.add_argument("--source", action="append", dest="sources", choices=["claude", "codex", "gemini", "cowork"], default=[])
    wlp.add_argument("--notify", action="store_true")
    wlp.add_argument("--interval", type=int, default=30)
    wlp.set_defaults(handler=handle_watch_loop)


def handle_watch_once(args):
    sources = args.sources or ["cowork", "claude", "gemini", "codex"]
    status_token = getattr(args, "status_token", None)
    if status_token:
        write_council_status(
            status_token,
            status="running",
            task_text="Scan recent transcripts once",
            metadata={"kind": "ingest", "sources": sources},
        )
    try:
        result = watch_once(sources=sources, notify=args.notify)
    except Exception as exc:
        if status_token:
            write_council_status(
                status_token,
                status="failed",
                task_text="Scan recent transcripts once",
                error=str(exc),
                metadata={"kind": "ingest", "sources": sources},
            )
        raise
    if status_token:
        write_council_status(
            status_token,
            status="completed",
            task_text="Scan recent transcripts once",
            review_path=result.portal_path,
            metadata={
                "kind": "ingest",
                "sources": sources,
                "scanned": result.scanned,
                "tasks_written": result.tasks_written,
                "actions_written": result.actions_written,
                "portal_path": result.portal_path,
            },
        )
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
