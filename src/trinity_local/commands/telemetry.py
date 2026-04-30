"""Handlers for telemetry settings and inspection."""
from __future__ import annotations

import json

from ..daemon_manager import daemon_install, daemon_start, daemon_status, daemon_stop
from ..refresh import refresh_launchpad
from ..telemetry import (
    build_elo_snapshot,
    disable_telemetry,
    enable_telemetry,
    launchpad_telemetry_state,
    load_telemetry_settings,
    reset_share_install_id,
    save_telemetry_settings,
)


def register(subparsers):
    show = subparsers.add_parser("telemetry-show", help="Show telemetry settings and current local snapshot")
    show.set_defaults(handler=handle_telemetry_show)

    enable = subparsers.add_parser("telemetry-enable", help="Enable anonymous telemetry sharing")
    enable.add_argument("--endpoint", default=None)
    enable.add_argument("--without-usage-events", action="store_true")
    enable.add_argument("--without-elo", action="store_true")
    enable.set_defaults(handler=handle_telemetry_enable)

    disable = subparsers.add_parser("telemetry-disable", help="Disable anonymous telemetry sharing")
    disable.set_defaults(handler=handle_telemetry_disable)

    reset = subparsers.add_parser("telemetry-reset-id", help="Reset the anonymous share install id")
    reset.set_defaults(handler=handle_telemetry_reset_id)

    endpoint = subparsers.add_parser("telemetry-endpoint", help="Set or clear the telemetry endpoint")
    endpoint.add_argument("--url", default=None)
    endpoint.add_argument("--clear", action="store_true")
    endpoint.set_defaults(handler=handle_telemetry_endpoint)

    ingest_enable = subparsers.add_parser("auto-ingest-enable", help="Enable automatic transcript ingestion")
    ingest_enable.set_defaults(handler=handle_auto_ingest_enable)

    ingest_disable = subparsers.add_parser("auto-ingest-disable", help="Disable automatic transcript ingestion")
    ingest_disable.set_defaults(handler=handle_auto_ingest_disable)


def handle_telemetry_show(args):
    settings = load_telemetry_settings()
    payload = {
        "settings": settings.to_dict(),
        "snapshot": build_elo_snapshot(),
        "launchpad": launchpad_telemetry_state(),
    }
    print(json.dumps(payload, indent=2))


def handle_telemetry_enable(args):
    settings = enable_telemetry(
        endpoint=args.endpoint,
        share_usage_events=not args.without_usage_events,
        share_elo_summaries=not args.without_elo,
    )
    portal_path = refresh_launchpad()
    print(json.dumps({"settings": settings.to_dict(), "portal_path": str(portal_path)}, indent=2))


def handle_telemetry_disable(args):
    settings = disable_telemetry()
    portal_path = refresh_launchpad()
    print(json.dumps({"settings": settings.to_dict(), "portal_path": str(portal_path)}, indent=2))


def handle_telemetry_reset_id(args):
    settings = reset_share_install_id()
    portal_path = refresh_launchpad()
    print(json.dumps({"settings": settings.to_dict(), "portal_path": str(portal_path)}, indent=2))


def handle_telemetry_endpoint(args):
    settings = load_telemetry_settings()
    if args.clear:
        settings.endpoint = None
    elif args.url:
        settings.endpoint = args.url
    path = save_telemetry_settings(settings)
    portal_path = refresh_launchpad()
    print(json.dumps({"settings": settings.to_dict(), "path": str(path), "portal_path": str(portal_path)}, indent=2))


def handle_auto_ingest_enable(args):
    settings = load_telemetry_settings()
    settings.auto_ingest_transcript = True
    save_telemetry_settings(settings)
    install_success, install_message = daemon_install()
    start_success, start_message = (True, "")
    if install_success:
        start_success, start_message = daemon_start()
    status_success, status_message = daemon_status()
    portal_path = refresh_launchpad()
    print(
        json.dumps(
            {
                "settings": settings.to_dict(),
                "portal_path": str(portal_path),
                "daemon_install": {"success": install_success, "message": install_message},
                "daemon_start": {"success": start_success, "message": start_message} if start_message else None,
                "daemon_status": {"success": status_success, "message": status_message},
            },
            indent=2,
        )
    )


def handle_auto_ingest_disable(args):
    settings = load_telemetry_settings()
    settings.auto_ingest_transcript = False
    save_telemetry_settings(settings)
    stop_success, stop_message = daemon_stop()
    status_success, status_message = daemon_status()
    portal_path = refresh_launchpad()
    print(
        json.dumps(
            {
                "settings": settings.to_dict(),
                "portal_path": str(portal_path),
                "daemon_stop": {"success": stop_success, "message": stop_message},
                "daemon_status": {"success": status_success, "message": status_message},
            },
            indent=2,
        )
    )
