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
    assert "numpy>=1.26" in content, (
        "install.sh must install numpy — without it the embedding "
        "matmul fast-path + k-means clustering + vocabulary stats all "
        "fail at import time. CI launch-eve catch: fresh ubuntu-latest "
        "+ python3.12 environment can't find numpy because it wasn't "
        "in pyproject.toml main deps."
    )


def test_install_sh_handles_venv_active_state():
    """pip refuses `--user` when run inside an active virtualenv. The
    installer must detect this case (e.g. a contributor smoking install
    from inside their venv-active shell) and install into the venv
    instead. Sandboxed smoke (May 17) caught this: the warning fired
    silently, doctor only went green because mcp happened to be in the
    dev's system Python — on a truly fresh box that path doesn't exist
    and the install would surface a real failure downstream."""
    content = INSTALL_SH.read_text()
    # The venv detector must check sys.prefix vs sys.base_prefix — that's
    # the canonical Python idiom for "am I inside a venv right now."
    assert "sys.prefix" in content and "sys.base_prefix" in content, (
        "install.sh must detect virtualenv state via sys.prefix vs "
        "sys.base_prefix and drop the --user flag inside a venv."
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
    tmp_path, capsys, monkeypatch
):
    """Pointing update at a directory that exists but isn't a git
    checkout must error cleanly — that means the skill was installed
    via something other than scripts/install.sh (manual copy?) and
    update can't apply."""
    from trinity_local.commands.update import handle_update

    # Create the dir but no .git/
    (tmp_path / "fake_skill").mkdir()

    # Force the "not a Chrome extension install" branch so the error
    # message references the curl|bash install path, not the Chrome
    # auto-update one.
    monkeypatch.setattr(
        "trinity_local.launchpad_data.dispatch_readiness",
        lambda: {"ready": False, "extension_configured": False},
    )

    args = SimpleNamespace(
        skill_dir=str(tmp_path / "fake_skill"),
        check=False, json=False,
    )
    rc = handle_update(args)
    assert rc == 1
    err = capsys.readouterr().err
    assert "not a git checkout" in err


def test_update_skill_dir_prefers_canonical_when_present(tmp_path, monkeypatch):
    """Post-2026-05-19 pivot: ~/.trinity/code/ is the canonical install
    location. _skill_dir() must prefer it over the legacy
    ~/.claude/skills/trinity/ when both could exist."""
    from trinity_local.commands.update import _skill_dir

    # Patch Path.home to point at tmp_path.
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    # Seed both the canonical location and the legacy location,
    # with .git/ markers so the canonical-preferred check fires.
    canonical = tmp_path / ".trinity" / "code"
    canonical.mkdir(parents=True)
    (canonical / ".git").mkdir()
    legacy = tmp_path / ".claude" / "skills" / "trinity"
    legacy.mkdir(parents=True)
    (legacy / ".git").mkdir()

    resolved = _skill_dir(None)
    assert resolved == canonical, (
        f"_skill_dir() must prefer ~/.trinity/code/ over legacy when "
        f"both have .git/; got {resolved}"
    )


def test_update_skill_dir_falls_back_to_legacy(tmp_path, monkeypatch):
    """When ~/.trinity/code/ doesn't exist (or isn't a git checkout),
    _skill_dir falls back to the legacy ~/.claude/skills/trinity/
    path — for pre-pivot users mid-migration."""
    from trinity_local.commands.update import _skill_dir

    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    # NO ~/.trinity/code/.git — only legacy.
    legacy = tmp_path / ".claude" / "skills" / "trinity"
    legacy.mkdir(parents=True)
    (legacy / ".git").mkdir()

    resolved = _skill_dir(None)
    assert resolved == legacy


def test_update_explains_chrome_auto_update_when_not_git(
    tmp_path, capsys, monkeypatch
):
    """If the user's source dir isn't a git checkout AND the Chrome
    extension is wired, the error should explain that Chrome auto-
    updates the extension and no manual update is needed for the
    Python side — NOT scold them to re-install."""
    from trinity_local.commands.update import handle_update

    (tmp_path / "fake_source").mkdir()
    monkeypatch.setattr(
        "trinity_local.launchpad_data.dispatch_readiness",
        lambda: {"ready": True, "extension_configured": True},
    )

    args = SimpleNamespace(
        skill_dir=str(tmp_path / "fake_source"),
        check=False, json=False,
    )
    rc = handle_update(args)
    assert rc == 1
    err = capsys.readouterr().err
    assert "Chrome" in err or "auto-update" in err, (
        f"Update must explain Chrome auto-update for extension users; got: {err}"
    )


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
