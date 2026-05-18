"""Handlers for telemetry settings and inspection."""
from __future__ import annotations

import json

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

    auto_chain_enable = subparsers.add_parser(
        "auto-chain-enable",
        help="Auto-continue councils into consensus rounds until convergence (max 3 rounds by default)",
    )
    auto_chain_enable.add_argument("--max-rounds", type=int, default=3)
    auto_chain_enable.set_defaults(handler=handle_auto_chain_enable)

    auto_chain_disable = subparsers.add_parser(
        "auto-chain-disable",
        help="Disable auto-continuation; first round only unless user clicks Continue",
    )
    auto_chain_disable.set_defaults(handler=handle_auto_chain_disable)

    auto_open_enable = subparsers.add_parser(
        "auto-open-enable",
        help="Open the council review page in the default browser as soon as it's written (macOS only)",
    )
    auto_open_enable.set_defaults(handler=handle_auto_open_enable)

    auto_open_disable = subparsers.add_parser(
        "auto-open-disable",
        help="Disable auto-open; councils write the page but don't pop a browser tab",
    )
    auto_open_disable.set_defaults(handler=handle_auto_open_disable)

    polish_enable = subparsers.add_parser(
        "polish-auto-enable",
        help="Auto-iterate (consensus_round x N) when a council's task looks like polish ('make this better', 'tighten this'). Targeted version of auto-chain-enable.",
    )
    polish_enable.set_defaults(handler=handle_polish_auto_enable)

    polish_disable = subparsers.add_parser(
        "polish-auto-disable",
        help="Disable targeted polish auto-iterate (default — polish tasks run a single council unless --auto-chain-enable is on)",
    )
    polish_disable.set_defaults(handler=handle_polish_auto_disable)


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




def handle_auto_chain_enable(args):
    settings = load_telemetry_settings()
    settings.auto_chain_enabled = True
    if getattr(args, "max_rounds", None):
        settings.max_chain_rounds = int(args.max_rounds)
    save_telemetry_settings(settings)
    portal_path = refresh_launchpad()
    print(json.dumps({"settings": settings.to_dict(), "portal_path": str(portal_path)}, indent=2))


def handle_auto_chain_disable(args):
    settings = load_telemetry_settings()
    settings.auto_chain_enabled = False
    save_telemetry_settings(settings)
    portal_path = refresh_launchpad()
    print(json.dumps({"settings": settings.to_dict(), "portal_path": str(portal_path)}, indent=2))


def handle_auto_open_enable(args):
    settings = load_telemetry_settings()
    settings.auto_open_council = True
    save_telemetry_settings(settings)
    portal_path = refresh_launchpad()
    print(json.dumps({"settings": settings.to_dict(), "portal_path": str(portal_path)}, indent=2))


def handle_auto_open_disable(args):
    settings = load_telemetry_settings()
    settings.auto_open_council = False
    save_telemetry_settings(settings)
    portal_path = refresh_launchpad()
    print(json.dumps({"settings": settings.to_dict(), "portal_path": str(portal_path)}, indent=2))


def handle_polish_auto_enable(args):
    settings = load_telemetry_settings()
    settings.polish_auto_iterate = True
    save_telemetry_settings(settings)
    portal_path = refresh_launchpad()
    print(json.dumps({"settings": settings.to_dict(), "portal_path": str(portal_path)}, indent=2))


def handle_polish_auto_disable(args):
    settings = load_telemetry_settings()
    settings.polish_auto_iterate = False
    save_telemetry_settings(settings)
    portal_path = refresh_launchpad()
    print(json.dumps({"settings": settings.to_dict(), "portal_path": str(portal_path)}, indent=2))
