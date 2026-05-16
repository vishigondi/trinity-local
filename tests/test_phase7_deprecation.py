"""Tests for Phase 7 — Shortcuts deprecation messaging + MIGRATION doc.

Phase 7 doesn't break the legacy Shortcut path; it adds:
  - a soft stderr note on `shortcut-install` pointing at the extension
  - docs/MIGRATION.md as the upgrade walkthrough
  - a new `dispatch_ready` doctor check that surfaces ANY-tier
    readiness (extension OR Shortcut) — broader than the existing
    shortcut-only check

This file pins all three.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
    return tmp_path


def test_shortcut_install_emits_deprecation_note(
    isolated_home, monkeypatch, capsys
):
    """`trinity-local shortcut-install --dry-run` must print the Phase 7
    deprecation note to stderr — pointing at the extension path. Stays
    on stderr so the JSON contract on stdout (consumed by scripts +
    tests) is unchanged."""
    from trinity_local.commands.shortcuts import handle_shortcut_install

    args = SimpleNamespace(
        shortcut_name="Trinity Dispatch",
        dry_run=True,
    )
    handle_shortcut_install(args)
    out, err = capsys.readouterr()
    # The JSON output must still be parseable — note goes to stderr.
    payload = json.loads(out)
    assert payload["dry_run"] is True
    # The note must mention MIGRATION.md and install-extension.
    assert "MIGRATION.md" in err
    assert "install-extension" in err
    assert "legacy" in err.lower()


def test_migration_doc_exists_and_covers_three_platforms():
    """The migration doc is the user-facing artifact for Phase 7. It
    must explain the upgrade path on each platform — without these
    sections, a Linux/Windows user has no recourse when their old
    `shortcut-install` no-op stops being the punt."""
    repo_root = Path(__file__).resolve().parents[1]
    migration_path = repo_root / "docs" / "MIGRATION.md"
    assert migration_path.exists(), "docs/MIGRATION.md missing"

    content = migration_path.read_text()
    # The three platform headings the doc must address.
    assert "macOS" in content
    assert "Linux" in content
    assert "Windows" in content
    # The two CLI verbs the user has to run (regression-guard against
    # silent rename: install-extension is the v1 command name).
    assert "install-extension" in content
    assert "install-launcher" in content
    # The retirement criteria (>=90% extension, >75% wired) must be in
    # the doc so users know the Shortcut path is not gone overnight.
    assert "90%" in content or "ninety" in content.lower()


def test_doctor_check_dispatch_ready_ok_when_extension_wired(
    isolated_home, monkeypatch
):
    """When the extension settings + host are both wired, the new doctor
    check reports OK with the tier ('extension')."""
    from trinity_local import state_paths
    settings_dir = state_paths.telemetry_settings_dir()
    (settings_dir / "extension.json").write_text(json.dumps({
        "extension_id": "abcdefghijklmnopabcdefghijklmnop",
    }))
    monkeypatch.setattr(
        "shutil.which",
        lambda name: "/usr/local/bin/trinity-local-capture-host"
        if name == "trinity-local-capture-host" else None,
    )
    monkeypatch.setattr(
        "trinity_local.launchpad_data._shortcut_status",
        lambda: {"ok": True, "applicable": False},
    )
    from trinity_local.doctor import _check_dispatch_ready

    result = _check_dispatch_ready()
    assert result.ok is True
    assert "extension" in result.detail.lower()


def test_doctor_check_dispatch_ready_fails_when_no_tier_wired(
    isolated_home, monkeypatch
):
    """When neither path is wired, doctor surfaces a `fix` command
    pointing at install-extension so the user has a one-line action."""
    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.setattr(
        "trinity_local.launchpad_data._shortcut_status",
        lambda: {"ok": True, "applicable": False},
    )
    from trinity_local.doctor import _check_dispatch_ready

    result = _check_dispatch_ready()
    assert result.ok is False
    assert result.fix and "install-extension" in result.fix


def test_doctor_run_includes_dispatch_ready_check(isolated_home, monkeypatch):
    """`run_doctor()` must include `dispatch_ready` so the global
    health summary surfaces it. Without this, the check exists but
    nothing calls it on the production code path."""
    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.setattr(
        "trinity_local.launchpad_data._shortcut_status",
        lambda: {"ok": True, "applicable": False},
    )
    from trinity_local.doctor import run_doctor

    report = run_doctor()
    names = [check.name for check in report.checks]
    assert "dispatch_ready" in names, (
        f"run_doctor() must include dispatch_ready; got {names!r}"
    )
