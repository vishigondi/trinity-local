"""Tests for scripts/install.sh + trinity-local update.

The git-clone-led distribution (no PyPI, no npm) hinges on:
  - scripts/install.sh being valid bash + idempotent
  - bin/trinity-local wrapper resolving to the cloned repo
  - trinity-local update implementing --check / --json / ff-only pull
  - doctor surfacing staleness when behind origin
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_SH = REPO_ROOT / "scripts" / "install.sh"


# ─── scripts/install.sh ────────────────────────────────────────────


def test_install_sh_exists_and_is_executable():
    assert INSTALL_SH.exists()
    mode = INSTALL_SH.stat().st_mode & 0o777
    assert mode & 0o100, (
        f"scripts/install.sh must be user-executable (got {oct(mode)})"
    )


def test_install_sh_passes_bash_syntax_check():
    """`bash -n` parses without executing — catches typos that would
    break the curl|sh install before the user notices."""
    result = subprocess.run(
        ["bash", "-n", str(INSTALL_SH)],
        capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0, (
        f"bash syntax check failed:\n{result.stderr}"
    )


def test_install_sh_references_canonical_paths():
    """The installer must point at the canonical skill directory and
    bin directory. Drift here means the docs and the script diverge —
    user gets one path from README, installer puts files elsewhere.

    Distribution invariant: Trinity itself is NOT installed via pip/npm
    (the script clones the repo and writes shell wrappers). Runtime
    Python deps (Pillow, mcp) ARE installed via pip — they're third-
    party and we don't vendor them. The forbidden form is specifically
    `pip install trinity-local` / `pipx install trinity-local`."""
    content = INSTALL_SH.read_text()
    assert ".claude/skills/trinity" in content
    assert ".local/bin" in content
    assert "pip install trinity-local" not in content
    assert "pipx install trinity-local" not in content
    assert "npm install trinity-local" not in content
    assert "npm install -g trinity-local" not in content


def test_install_sh_writes_two_wrappers():
    """The installer should drop trinity-local + trinity-local-capture-host
    wrappers into ~/.local/bin/ — the only two CLI surfaces the user
    invokes by name."""
    content = INSTALL_SH.read_text()
    assert "TRINITY_BIN_DIR/trinity-local" in content
    assert "TRINITY_BIN_DIR/trinity-local-capture-host" in content


def test_install_sh_installs_runtime_python_deps():
    """Trinity's runtime deps (Pillow, mcp) are pyproject-declared but
    NOT auto-installed by the git clone. The installer must pip-install
    them or doctor's first run flags two failures the user has to fix
    manually — a "vibes-coded" first-impression smell."""
    content = INSTALL_SH.read_text()
    assert "Pillow>=10" in content, (
        "install.sh must install Pillow — without it me-card PNG "
        "rendering fails and doctor flags it on first run."
    )
    assert "mcp>=1.0" in content, (
        "install.sh must install the mcp package — without it the MCP "
        "server can't start and Claude Code can't see Trinity's tools."
    )


def test_install_sh_wrapper_uses_resolved_python():
    """The wrapper that ~/.local/bin/trinity-local writes must use the
    Python binary the install script validated, not a raw `python3`.
    On systems where `python3` is older than the candidate the script
    picked (e.g. `python3.13` passes, `python3` is 3.9), the wrapper
    would silently break."""
    content = INSTALL_SH.read_text()
    # Heredoc body must reference $PYTHON_BIN (unescaped — expanded at
    # script time) for the wrapper, NOT literal `python3 -m`.
    assert 'exec "$PYTHON_BIN" -m trinity_local.main' in content, (
        "wrapper should embed the resolved Python binary so it can't "
        "drift if the user later installs a stale python3 ahead of it."
    )


# ─── trinity-local update ──────────────────────────────────────────


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
    return tmp_path


def test_update_check_command_registered():
    """`trinity-local update --check` must be a registered subcommand."""
    import argparse
    from trinity_local.commands.update import register

    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="cmd")
    register(subparsers)

    args = parser.parse_args(["update", "--check"])
    assert getattr(args, "handler", None) is not None
    assert args.check is True


def test_update_emits_error_when_skill_dir_missing(tmp_path, capsys):
    """Pointing update at a non-existent skill dir must error cleanly,
    not crash."""
    from trinity_local.commands.update import handle_update

    args = SimpleNamespace(
        skill_dir=str(tmp_path / "nonexistent"),
        check=False, json=False,
    )
    rc = handle_update(args)
    assert rc == 1
    err = capsys.readouterr().err
    assert "not found" in err


def test_update_emits_error_when_skill_dir_not_a_git_checkout(
    tmp_path, capsys
):
    """Pointing update at a directory that exists but isn't a git
    checkout must error cleanly — that means the skill was installed
    via something other than scripts/install.sh (manual copy?) and
    update can't apply."""
    from trinity_local.commands.update import handle_update

    # Create the dir but no .git/
    (tmp_path / "fake_skill").mkdir()

    args = SimpleNamespace(
        skill_dir=str(tmp_path / "fake_skill"),
        check=False, json=False,
    )
    rc = handle_update(args)
    assert rc == 1
    err = capsys.readouterr().err
    assert "not a git checkout" in err


def test_update_check_on_real_repo_returns_up_to_date_or_lag(capsys):
    """Run update --check against the actual repo (the test environment's
    own checkout). Should either report "up to date" or a specific lag
    count — never crash."""
    from trinity_local.commands.update import handle_update

    args = SimpleNamespace(
        skill_dir=str(REPO_ROOT),
        check=True, json=True,
    )
    rc = handle_update(args)
    # rc==0 on success OR soft-fail (network issue). The point is no crash.
    assert rc == 0
    out = capsys.readouterr().out
    # Either we got JSON with the expected shape, or we got the soft-fail
    # path (which writes to stderr, not stdout — stdout is empty).
    if out.strip():
        data = json.loads(out)
        assert "behind" in data or "error" in data


def test_update_json_mode_format(capsys):
    """`--json` mode emits machine-readable output, not human prose."""
    from trinity_local.commands.update import handle_update

    args = SimpleNamespace(
        skill_dir=str(REPO_ROOT),
        check=True, json=True,
    )
    handle_update(args)
    out = capsys.readouterr().out.strip()
    if out:  # might be empty if soft-fail to stderr
        # JSON parses without error.
        parsed = json.loads(out)
        assert isinstance(parsed, dict)
