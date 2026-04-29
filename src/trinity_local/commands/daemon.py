"""Commands for managing the watch-loop daemon."""
from __future__ import annotations

import argparse
import sys

from ..daemon_manager import (
    daemon_install,
    daemon_start,
    daemon_stop,
    daemon_status,
    daemon_uninstall,
)


def handle_daemon_install(args: argparse.Namespace) -> None:
    success, message = daemon_install()
    print(message)
    sys.exit(0 if success else 1)


def handle_daemon_uninstall(args: argparse.Namespace) -> None:
    success, message = daemon_uninstall()
    print(message)
    sys.exit(0 if success else 1)


def handle_daemon_start(args: argparse.Namespace) -> None:
    success, message = daemon_start()
    print(message)
    sys.exit(0 if success else 1)


def handle_daemon_stop(args: argparse.Namespace) -> None:
    success, message = daemon_stop()
    print(message)
    sys.exit(0 if success else 1)


def handle_daemon_status(args: argparse.Namespace) -> None:
    success, message = daemon_status()
    print(message)
    sys.exit(0 if success else 1)


def register(subparsers: argparse._SubParsersAction) -> None:
    daemon_parser = subparsers.add_parser(
        "daemon",
        help="Manage background watch-loop daemon",
    )
    daemon_subparsers = daemon_parser.add_subparsers(dest="daemon_action", required=True)

    install_parser = daemon_subparsers.add_parser("install", help="Install and start daemon")
    install_parser.set_defaults(handler=handle_daemon_install)

    uninstall_parser = daemon_subparsers.add_parser("uninstall", help="Stop and uninstall daemon")
    uninstall_parser.set_defaults(handler=handle_daemon_uninstall)

    start_parser = daemon_subparsers.add_parser("start", help="Start daemon")
    start_parser.set_defaults(handler=handle_daemon_start)

    stop_parser = daemon_subparsers.add_parser("stop", help="Stop daemon")
    stop_parser.set_defaults(handler=handle_daemon_stop)

    status_parser = daemon_subparsers.add_parser("status", help="Check daemon status")
    status_parser.set_defaults(handler=handle_daemon_status)
