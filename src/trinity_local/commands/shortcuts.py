"""Handlers for shortcut-url, shortcut-run, action-shortcut, shortcut-setup, shortcut-install."""
from __future__ import annotations

import json

from ..dispatch_registry import make_dispatch_action
from ..action_runtime import load_action
from ..shortcuts_integration import (
    DEFAULT_SHORTCUT_NAME, build_dispatch_payload,
    build_shortcut_url, make_shortcut_invocation, run_shortcut,
)
from ..shortcut_setup import run_installer, write_installer_script, write_shortcut_setup


def register(subparsers):
    sp = subparsers.add_parser("shortcut-url", help="Build a shortcuts:// dispatch URL")
    sp.add_argument("--action", required=True, help="Dispatch action name")
    sp.add_argument("--command", dest="shell_command", default=None)
    sp.add_argument("--task", default=None)
    sp.add_argument("--shortcut-name", default=DEFAULT_SHORTCUT_NAME)
    sp.set_defaults(handler=handle_shortcut_url)

    rp = subparsers.add_parser("shortcut-run", help="Run a macOS Shortcut dispatch payload")
    rp.add_argument("--action", required=True, help="Dispatch action name")
    rp.add_argument("--command", dest="shell_command", default=None)
    rp.add_argument("--task", default=None)
    rp.add_argument("--shortcut-name", default=DEFAULT_SHORTCUT_NAME)
    rp.set_defaults(handler=handle_shortcut_run)

    ap = subparsers.add_parser("action-shortcut", help="Build or run a Shortcut for a saved action")
    ap.add_argument("--action", required=True)
    ap.add_argument("--shortcut-name", default=DEFAULT_SHORTCUT_NAME)
    ap.add_argument("--run", action="store_true")
    ap.set_defaults(handler=handle_action_shortcut)

    ssp = subparsers.add_parser("shortcut-setup", help="Write a setup recipe for the macOS Trinity Dispatch shortcut")
    ssp.add_argument("--shortcut-name", default=DEFAULT_SHORTCUT_NAME)
    ssp.set_defaults(handler=handle_shortcut_setup)

    sip = subparsers.add_parser("shortcut-install", help="Create Trinity Dispatch shortcut (opens Shortcuts app)")
    sip.add_argument("--shortcut-name", default=DEFAULT_SHORTCUT_NAME)
    sip.add_argument("--dry-run", action="store_true", help="Write script only, don't run it")
    sip.set_defaults(handler=handle_shortcut_install)


def _resolve_action_name(raw: str) -> str:
    return "run_command" if raw == "run-command" else raw.replace("-", "_")


def handle_shortcut_url(args):
    dispatch = make_dispatch_action(
        _resolve_action_name(args.action),
        args={"command": args.shell_command} if args.shell_command else {},
        task_id=args.task,
    )
    payload = build_dispatch_payload(dispatch)
    url = build_shortcut_url(args.shortcut_name, payload)
    print(json.dumps({"shortcut_name": args.shortcut_name, "input_text": payload, "url": url}, indent=2))


def handle_shortcut_run(args):
    invocation = make_shortcut_invocation(
        dispatch=make_dispatch_action(
            _resolve_action_name(args.action),
            args={"command": args.shell_command} if args.shell_command else {},
            task_id=args.task,
        ),
        shortcut_name=args.shortcut_name,
    )
    ok = run_shortcut(invocation)
    print(json.dumps({"invocation": invocation.to_dict(), "ran": ok}, indent=2))


def handle_action_shortcut(args):
    action = load_action(args.action)
    dispatch = action.dispatch_action or {}
    if not dispatch:
        raise SystemExit("error: action-shortcut requires an action with a dispatch_action")
    invocation = make_shortcut_invocation(
        dispatch=make_dispatch_action(
            dispatch["name"],
            args=dispatch.get("args", {}),
            task_id=dispatch.get("task_id") or action.task_id,
            metadata=dispatch.get("metadata", {}),
        ),
        shortcut_name=args.shortcut_name,
    )
    payload = {"action": action.to_dict(), "shortcut": invocation.to_dict()}
    if args.run:
        payload["ran"] = run_shortcut(invocation)
    print(json.dumps(payload, indent=2))


def handle_shortcut_setup(args):
    path = write_shortcut_setup(args.shortcut_name)
    print(json.dumps({"path": str(path), "shortcut_name": args.shortcut_name}, indent=2))


def handle_shortcut_install(args):
    # Phase 7 deprecation soft-notice. The macOS Shortcut path is the
    # legacy tier-2 fallback; the cross-platform Chrome extension is the
    # forward path. We DON'T remove shortcut-install — existing users
    # need it. But every invocation surfaces a one-line note (stderr,
    # so the JSON contract on stdout stays parseable for scripts).
    # See docs/MIGRATION.md for the upgrade path.
    import sys as _sys
    print(
        "note: macOS Shortcut is now the legacy fallback (tier 2). The "
        "cross-platform Chrome extension is the recommended path — see "
        "docs/MIGRATION.md and `trinity-local install-extension --help`.",
        file=_sys.stderr,
    )
    setup_path = write_shortcut_setup(args.shortcut_name)
    script_path = write_installer_script(args.shortcut_name)
    if args.dry_run:
        print(json.dumps({
            "setup_path": str(setup_path),
            "script_path": str(script_path),
            "dry_run": True,
        }, indent=2))
        return
    ok, message = run_installer(args.shortcut_name)
    print(json.dumps({
        "success": ok,
        "message": message,
        "setup_path": str(setup_path),
        "script_path": str(script_path),
    }, indent=2))
