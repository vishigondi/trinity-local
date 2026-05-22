"""Tests for the Area 5 CLI consolidation (21 → 5 user-facing).

`trinity-local --help` shows exactly five verbs:
  - install   (umbrella: install-mcp, install-extension, ...)
  - status
  - update
  - dream
  - debug     (umbrella: replay-history, consolidate, ...)

Everything else stays registered (launchpad dispatch + Chrome ext
action allowlist call subparsers by name; dropping the registrations
breaks those flows) but disappears from `--help`'s discoverable
surface.
"""
from __future__ import annotations

import argparse


from trinity_local.main import (
    USER_FACING_COMMANDS,
    build_parser,
)


class TestUserFacingSurface:
    def test_user_facing_set_is_exactly_five(self):
        """The cron spec calls out 5 user-facing verbs. Drift here
        (someone adds a sixth or drops one) silently changes the
        marketing claim 'trinity-local has just 5 verbs you need to
        know.'"""
        assert USER_FACING_COMMANDS == frozenset(
            {"install", "status", "update", "dream", "debug"}
        ), (
            f"USER_FACING_COMMANDS must be exactly the 5 verbs from the "
            f"Area 5 spec; got {sorted(USER_FACING_COMMANDS)!r}."
        )

    def test_help_lists_only_five_subparsers_in_descriptive_table(self):
        """The descriptive table (the part below the usage line) must
        show exactly the five user-facing verbs. Non-canonical
        subparsers stay registered but should NOT appear here."""
        parser = build_parser()
        # Find the subparsers action.
        sub_action = next(
            a for a in parser._actions
            if isinstance(a, argparse._SubParsersAction)
        )
        # The descriptive table is generated from `_choices_actions`.
        listed = {a.dest for a in sub_action._choices_actions}
        assert listed == USER_FACING_COMMANDS, (
            f"--help descriptive table must list exactly the 5 user-"
            f"facing verbs; got {sorted(listed)!r}."
        )

    def test_metavar_overrides_noisy_usage_line(self):
        """Without an explicit metavar, argparse prints all 40+
        registered choices in the usage line. The metavar collapses
        it to {install,status,update,dream,debug}."""
        parser = build_parser()
        sub_action = next(
            a for a in parser._actions
            if isinstance(a, argparse._SubParsersAction)
        )
        assert sub_action.metavar == "{install,status,update,dream,debug}", (
            f"Subparsers metavar must be the user-facing 5; got "
            f"{sub_action.metavar!r}."
        )


class TestHiddenCommandsStillCallable:
    """The legacy commands (council-*, install-mcp, ingest-recent,
    etc.) stay reachable — the Chrome extension dispatches by name
    and dropping the registrations would silently break the
    launchpad. Confirm a sample of them parse without error."""

    def _can_parse(self, *argv):
        parser = build_parser()
        # Catch SystemExit (argparse's default for parser errors) so
        # we can assert success/failure cleanly.
        try:
            parser.parse_args(list(argv))
            return True
        except SystemExit:
            return False

    def test_install_mcp_still_callable(self):
        # `--help` returns rc=0 via SystemExit; parse with concrete args
        # instead so the call returns normally.
        assert self._can_parse("install-mcp"), (
            "install-mcp must remain callable — install.sh and the README's "
            "install brief both invoke it by name."
        )

    def test_council_launch_still_callable(self):
        assert self._can_parse("council-launch", "--task", "x"), (
            "council-launch must remain callable — Chrome extension's "
            "Native Messaging dispatcher fires it by name."
        )

    def test_ingest_recent_still_callable(self):
        assert self._can_parse("ingest-recent"), (
            "ingest-recent must remain callable — Chrome extension "
            "popup's ingest button dispatches to it."
        )

    def test_download_embedder_still_callable(self):
        assert self._can_parse("download-embedder"), (
            "download-embedder must remain callable — the embedder "
            "gate's error message points users at it."
        )

    def test_replay_history_still_callable(self):
        assert self._can_parse("replay-history", "--limit", "5"), (
            "replay-history must remain callable — power users rely on "
            "the bare name; the `debug` umbrella is discovery-only."
        )


class TestDebugUmbrella:
    def test_debug_no_args_lists_verbs(self, capsys):
        """`trinity-local debug` with no subcommand prints the
        power-user verb directory."""
        from trinity_local.commands.debug import handle_debug
        from types import SimpleNamespace

        rc = handle_debug(SimpleNamespace(subcommand=None))
        assert rc == 0
        out = capsys.readouterr().out
        # All four debug verbs must be listed.
        for verb in (
            "replay-history",
            "consolidate",
            "vocabulary",
            "seed-from-taste-terminal",
        ):
            assert verb in out, (
                f"debug umbrella must list {verb!r}; got: {out!r}"
            )

    def test_debug_with_subcommand_points_user_at_bare_name(self, capsys):
        """`trinity-local debug replay-history` doesn't (yet) execute
        the verb itself — it tells the user to run the bare name.
        This satisfies the discovery requirement without re-nesting
        every parser."""
        from trinity_local.commands.debug import handle_debug
        from types import SimpleNamespace

        rc = handle_debug(SimpleNamespace(subcommand="replay-history"))
        assert rc == 0
        err = capsys.readouterr().err
        assert "trinity-local replay-history" in err


class TestInstallUmbrella:
    def test_install_no_args_lists_verbs(self, capsys):
        """`trinity-local install` lists the install verbs so users
        find install-mcp (most common) and the optional ones."""
        from trinity_local.commands.install_umbrella import handle_install_umbrella
        from types import SimpleNamespace

        rc = handle_install_umbrella(SimpleNamespace())
        assert rc == 0
        out = capsys.readouterr().out
        for verb in (
            "install-mcp",
            "install-extension",
            "install-hooks",
            "install-launcher",
            "uninstall",
        ):
            assert verb in out, (
                f"install umbrella must list {verb!r}; got: {out!r}"
            )
        # The "most common" callout for install-mcp helps new users
        # know which one to run first.
        assert "install-mcp" in out
        assert "most" in out.lower() or "common" in out.lower()
