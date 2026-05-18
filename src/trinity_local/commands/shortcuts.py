"""Handler for shortcut-install — legacy macOS Shortcut tier-2 fallback."""
from __future__ import annotations

import json

from ..shortcuts_integration import DEFAULT_SHORTCUT_NAME
from ..shortcut_setup import run_installer, write_installer_script, write_shortcut_setup


def register(subparsers):
    sip = subparsers.add_parser("shortcut-install", help="Create Trinity Dispatch shortcut (opens Shortcuts app)")
    sip.add_argument("--shortcut-name", default=DEFAULT_SHORTCUT_NAME)
    sip.add_argument("--dry-run", action="store_true", help="Write script only, don't run it")
    sip.set_defaults(handler=handle_shortcut_install)


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
