"""Tests for `trinity-local moves-build / moves-show / moves-export` (#171).

The CLI surface is the user/agent's read+share interface to the moves
substrate. These tests pin the JSON shape (other tooling will parse it),
the disk side-effects (tarball + directory export), and the cold-install
behavior (empty substrate → friendly error, not crash).

Tests use an isolated TRINITY_HOME so writes don't pollute the real
install and parallel tests don't collide.
"""
from __future__ import annotations

import io
import json
import tarfile
from contextlib import redirect_stderr, redirect_stdout
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from trinity_local.commands import moves as moves_cmd
from trinity_local.moves import store
from trinity_local.moves.schemas import Move


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
    return tmp_path


def _make_move(
    name: str,
    *,
    basin: str = "basin-alpha",
    alpha: int = 4,
    beta: int = 2,
    promoted_at: str | None = None,
    body: str = "do the thing\n",
    t3_score: float | None = 0.82,
    baseline: float | None = 0.75,
) -> Move:
    return Move(
        name=name,
        description=f"description for {name}",
        trinity_basin_id=basin,
        trinity_promoted_at=promoted_at or datetime(2026, 5, 25, 12, 0, tzinfo=timezone.utc).isoformat(timespec="seconds"),
        trinity_alpha=alpha,
        trinity_beta=beta,
        trinity_execution_count=alpha + beta - 2,
        trinity_t3_chairman_score=t3_score,
        trinity_eval_baseline=baseline,
        trinity_promoted_from=["rej_001", "rej_002", "rej_003"],
        body=body,
    )


def _capture(handler, args) -> tuple[int, dict, str]:
    """Run a handler and capture (exit_code, parsed_stdout_json, stderr)."""
    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = handler(args)
    stdout = out.getvalue().strip()
    payload = json.loads(stdout) if stdout else {}
    return code, payload, err.getvalue()


# ─── moves-show ──────────────────────────────────────────────────────


class TestMovesShowList:
    def test_cold_install_returns_empty_list(self, isolated_home):
        args = SimpleNamespace(slug=None, archived=False, full=False)
        code, payload, _ = _capture(moves_cmd.handle_show, args)
        assert code == 0
        assert payload["ok"] is True
        assert payload["count"] == 0
        assert payload["moves"] == []
        assert payload["archived"] is False

    def test_lists_active_moves_with_posterior_and_tier_scores(self, isolated_home):
        store.write_move(_make_move("tighten verbose bullets"))
        store.write_move(_make_move(
            "expand-dense-paragraphs",
            basin="basin-beta",
            alpha=2,
            beta=6,
        ))
        args = SimpleNamespace(slug=None, archived=False, full=False)
        code, payload, _ = _capture(moves_cmd.handle_show, args)
        assert code == 0
        assert payload["count"] == 2
        names = {m["name"] for m in payload["moves"]}
        assert names == {"tighten verbose bullets", "expand-dense-paragraphs"}
        for entry in payload["moves"]:
            assert "posterior" in entry
            assert "alpha" in entry and "beta" in entry
            assert "basin" in entry
            # body excluded by default
            assert "body" not in entry
            # tier scores surfaced
            assert "t3_chairman_score" in entry
            assert "eval_baseline" in entry

    def test_full_flag_includes_body(self, isolated_home):
        store.write_move(_make_move("foo", body="step 1\nstep 2\n"))
        args = SimpleNamespace(slug=None, archived=False, full=True)
        code, payload, _ = _capture(moves_cmd.handle_show, args)
        assert code == 0
        assert payload["moves"][0]["body"] == "step 1\nstep 2\n"

    def test_archived_flag_lists_archived_not_active(self, isolated_home):
        store.write_move(_make_move("active-move"))
        # Archive directly via the store (simulating Phase 6c demotion).
        store.archive_move(
            store._slugify("active-move"),
            tier="T4",
            reason="posterior drifted below baseline",
        )
        # Active list is empty after demotion
        args_active = SimpleNamespace(slug=None, archived=False, full=False)
        _, active_payload, _ = _capture(moves_cmd.handle_show, args_active)
        assert active_payload["count"] == 0

        args_arch = SimpleNamespace(slug=None, archived=True, full=False)
        _, arch_payload, _ = _capture(moves_cmd.handle_show, args_arch)
        assert arch_payload["count"] == 1
        assert arch_payload["archived"] is True
        assert arch_payload["moves"][0]["demoted_by_tier"] == "T4"
        assert arch_payload["moves"][0]["demoted_at"] is not None


class TestMovesShowSingleSlug:
    def test_show_one_active_slug(self, isolated_home):
        store.write_move(_make_move("tighten verbose bullets"))
        args = SimpleNamespace(
            slug="tighten-verbose-bullets",
            archived=False,
            full=False,
        )
        code, payload, _ = _capture(moves_cmd.handle_show, args)
        assert code == 0
        assert payload["ok"] is True
        assert payload["slug"] == "tighten-verbose-bullets"
        assert payload["archived"] is False
        # single-slug always returns full=True so users can read the procedure
        assert "body" in payload["move"]

    def test_show_unknown_slug_returns_error(self, isolated_home):
        args = SimpleNamespace(slug="does-not-exist", archived=False, full=False)
        code, _, stderr = _capture(moves_cmd.handle_show, args)
        assert code == 1
        # Error payload goes to stderr; verify hint mentions the list verb
        err_payload = json.loads(stderr)
        assert err_payload["ok"] is False
        assert "Move not found" in err_payload["error"]
        assert "moves-show" in err_payload["hint"]

    def test_show_slug_falls_back_to_other_side(self, isolated_home):
        """If user asked for active but the move is archived (or vice versa),
        the command falls back to the other side rather than 404-ing."""
        store.write_move(_make_move("foo"))
        store.archive_move(store._slugify("foo"), tier="T4", reason="test")
        # User asks for it as if active — should find the archived copy.
        args = SimpleNamespace(slug="foo", archived=False, full=False)
        code, payload, _ = _capture(moves_cmd.handle_show, args)
        assert code == 0
        assert payload["archived"] is True


# ─── moves-export ────────────────────────────────────────────────────


class TestMovesExport:
    def test_cold_install_returns_error_not_crash(self, isolated_home):
        out_path = isolated_home / "exports" / "bundle.tar.gz"
        args = SimpleNamespace(
            out=out_path,
            format="tar.gz",
            include_archived=False,
        )
        code, _, stderr = _capture(moves_cmd.handle_export, args)
        assert code == 1
        err_payload = json.loads(stderr)
        assert "Nothing to export" in err_payload["error"]
        assert "moves-build" in err_payload["hint"]
        # Should not have created the output file
        assert not out_path.exists()

    def test_export_with_archive_dir_only_returns_error(self, isolated_home):
        """If active is empty but archive has entries and include-archived
        is off, we still report nothing to export (with a helpful hint)."""
        store.write_move(_make_move("foo"))
        store.archive_move(store._slugify("foo"), tier="T4", reason="drift")
        out_path = isolated_home / "bundle.tar.gz"
        args = SimpleNamespace(
            out=out_path,
            format="tar.gz",
            include_archived=False,
        )
        code, _, stderr = _capture(moves_cmd.handle_export, args)
        assert code == 1
        err_payload = json.loads(stderr)
        assert "Nothing to export" in err_payload["error"]
        assert "include-archived" in err_payload["hint"]

    def test_tarball_contains_active_skill_md(self, isolated_home):
        store.write_move(_make_move("tighten bullets"))
        store.write_move(_make_move("expand dense paragraphs", basin="basin-beta"))
        out_path = isolated_home / "bundle.tar.gz"
        args = SimpleNamespace(
            out=out_path,
            format="tar.gz",
            include_archived=False,
        )
        code, payload, _ = _capture(moves_cmd.handle_export, args)
        assert code == 0
        assert payload["ok"] is True
        assert payload["count"] == 2
        assert out_path.exists()
        with tarfile.open(out_path, "r:gz") as tar:
            names = sorted(tar.getnames())
        assert names == [
            "moves/expand-dense-paragraphs/SKILL.md",
            "moves/tighten-bullets/SKILL.md",
        ]

    def test_include_archived_adds_archive_path(self, isolated_home):
        store.write_move(_make_move("active-1"))
        store.write_move(_make_move("active-2"))
        store.archive_move(store._slugify("active-2"), tier="T4", reason="drift")
        out_path = isolated_home / "bundle.tar.gz"
        args = SimpleNamespace(
            out=out_path,
            format="tar.gz",
            include_archived=True,
        )
        code, payload, _ = _capture(moves_cmd.handle_export, args)
        assert code == 0
        assert payload["count"] == 2
        with tarfile.open(out_path, "r:gz") as tar:
            names = sorted(tar.getnames())
        assert names == [
            "moves/active-1/SKILL.md",
            "moves/archive/active-2/SKILL.md",
        ]

    def test_dir_format_copies_files_under_arcname(self, isolated_home):
        store.write_move(_make_move("tighten bullets"))
        out_path = isolated_home / "exported"
        args = SimpleNamespace(
            out=out_path,
            format="dir",
            include_archived=False,
        )
        code, payload, _ = _capture(moves_cmd.handle_export, args)
        assert code == 0
        assert payload["format"] == "dir"
        skill_md = out_path / "moves" / "tighten-bullets" / "SKILL.md"
        assert skill_md.exists()
        content = skill_md.read_text(encoding="utf-8")
        assert content.startswith("---\n")
        assert "name: tighten bullets" in content


# ─── moves-build ─────────────────────────────────────────────────────


class TestMovesBuild:
    def test_cold_install_returns_clean_report(self, isolated_home, monkeypatch):
        """No outcomes, no moves, no corpus → phase_6_moves_pass returns
        the zero report and the CLI passes it through."""
        args = SimpleNamespace(
            primary_provider=None,
            skip_promotion=False,
            skip_demotion=False,
        )
        code, payload, _ = _capture(moves_cmd.handle_build, args)
        assert code == 0
        assert payload["ok"] is True
        report = payload["phase_6_report"]
        assert "t4_update" in report
        assert "promotion" in report
        assert "demotion" in report

    def test_skip_flags_short_circuit_phases(self, isolated_home):
        args = SimpleNamespace(
            primary_provider=None,
            skip_promotion=True,
            skip_demotion=True,
        )
        code, payload, _ = _capture(moves_cmd.handle_build, args)
        assert code == 0
        assert payload["phase_6_report"]["promotion"] == {"skipped": True}
        assert payload["phase_6_report"]["demotion"] == {"skipped": True}


# ─── Registration ───────────────────────────────────────────────────


class TestRegistration:
    """The three verbs are registered in the dispatcher and resolve via
    `trinity-local --help`. Cheap structural check — guards against
    forgetting to add the new module to CORE_COMMAND_MODULES."""

    def test_moves_in_core_command_modules(self):
        from trinity_local.main import CORE_COMMAND_MODULES
        assert "moves" in CORE_COMMAND_MODULES

    def test_register_adds_three_subparsers(self):
        """Calling register(subparsers) adds exactly moves-build,
        moves-show, moves-export."""
        import argparse
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers()
        moves_cmd.register(subparsers)
        # argparse stashes parser objects in subparsers.choices
        assert set(subparsers.choices.keys()) == {
            "moves-build",
            "moves-show",
            "moves-export",
        }
