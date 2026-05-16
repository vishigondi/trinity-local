"""Tests for Phase 5 dispatch readiness — the CLI-side mirror of the
launchpad's in-page dispatch banner.

`dispatch_readiness()` is the same data both surfaces consume; this file
locks the contract so the CLI hint and the launchpad banner can't drift
apart (drift principle #20: load-bearing facts in N≥3 surfaces decay in
the oldest one).
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


def test_dispatch_readiness_empty_install(isolated_home, monkeypatch):
    """Fresh install with no extension settings + no Shortcut. Should
    return `ready: False` plus a hint that points at install-extension —
    the future path, not the legacy path."""
    monkeypatch.setattr("shutil.which", lambda name: None)
    # Force shortcut to non-applicable so the test is independent of the
    # dev machine's actual Shortcut state (it's typically installed).
    monkeypatch.setattr(
        "trinity_local.launchpad_data._shortcut_status",
        lambda: {"ok": True, "applicable": False},
    )
    from trinity_local.launchpad_data import dispatch_readiness

    result = dispatch_readiness()
    assert result["ready"] is False
    assert result["extension_configured"] is False
    assert result["host_on_path"] is False
    assert result["recommended_action"] is not None
    assert "install-extension" in result["recommended_action"]


def test_dispatch_readiness_extension_configured_and_host_present(
    isolated_home, monkeypatch
):
    """Extension ID persisted + host on PATH → fully ready, no hint."""
    from trinity_local import state_paths
    settings_dir = state_paths.telemetry_settings_dir()
    (settings_dir / "extension.json").write_text(json.dumps({
        "extension_id": "abcdefghijklmnopabcdefghijklmnop",
        "host_path": "/usr/local/bin/trinity-local-capture-host",
    }))
    monkeypatch.setattr(
        "shutil.which",
        lambda name: "/usr/local/bin/trinity-local-capture-host"
        if name == "trinity-local-capture-host" else None,
    )
    # Force shortcut to look not-applicable so the test is independent
    # of platform AND of whether the dev machine has the Shortcut.
    monkeypatch.setattr(
        "trinity_local.launchpad_data._shortcut_status",
        lambda: {"ok": True, "applicable": False},
    )
    from trinity_local.launchpad_data import dispatch_readiness

    result = dispatch_readiness()
    assert result["ready"] is True
    assert result["recommended_action"] is None
    assert result["extension_configured"] is True
    assert result["host_on_path"] is True


def test_dispatch_readiness_extension_id_but_host_missing(
    isolated_home, monkeypatch
):
    """Extension ID is persisted but the console script isn't on PATH
    (e.g. user installed via wheel but `trinity-local-capture-host` is
    in a venv they activated elsewhere). The hint must be SPECIFIC —
    pointing at the broken half, not at install-extension generically."""
    from trinity_local import state_paths
    settings_dir = state_paths.telemetry_settings_dir()
    (settings_dir / "extension.json").write_text(json.dumps({
        "extension_id": "abcdefghijklmnopabcdefghijklmnop",
    }))
    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.setattr(
        "trinity_local.launchpad_data._shortcut_status",
        lambda: {"ok": True, "applicable": False},
    )
    from trinity_local.launchpad_data import dispatch_readiness

    result = dispatch_readiness()
    assert result["ready"] is False
    assert result["extension_configured"] is True
    assert result["host_on_path"] is False
    assert "trinity-local-capture-host" in result["recommended_action"]


def test_dispatch_readiness_shortcut_only(isolated_home, monkeypatch):
    """macOS user with the Shortcut registered but no extension — still
    ready (tier 2 works), no hint."""
    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.setattr(
        "trinity_local.launchpad_data._shortcut_status",
        lambda: {"ok": True, "applicable": True, "name": "Trinity Dispatch"},
    )
    from trinity_local.launchpad_data import dispatch_readiness

    result = dispatch_readiness()
    assert result["ready"] is True
    assert result["recommended_action"] is None
    assert result["shortcut_installed"] is True


def test_dispatch_readiness_mac_no_shortcut(isolated_home, monkeypatch):
    """macOS user, applicable Shortcut, but NOT installed AND no
    extension. Hint should mention both paths — extension is the
    forward path, shortcut-install is the legacy macOS-only fallback."""
    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.setattr(
        "trinity_local.launchpad_data._shortcut_status",
        lambda: {"ok": False, "applicable": True, "name": "Trinity Dispatch"},
    )
    from trinity_local.launchpad_data import dispatch_readiness

    result = dispatch_readiness()
    assert result["ready"] is False
    assert "install-extension" in result["recommended_action"]
    assert "shortcut-install" in result["recommended_action"]


def test_portal_html_includes_dispatch_readiness(
    isolated_home, monkeypatch, capsys
):
    """End-to-end: `trinity-local portal-html` (no --open-browser) prints
    a JSON object that includes the `dispatch` snapshot. Scripts that
    consume the output (CI, dev tooling) can read it without a separate
    CLI call."""
    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.setattr(
        "trinity_local.launchpad_data._shortcut_status",
        lambda: {"ok": True, "applicable": False},
    )
    from trinity_local.commands.portal import handle_portal_html

    args = SimpleNamespace(title="Trinity test", open_browser=False)
    handle_portal_html(args)
    out, err = capsys.readouterr()
    payload = json.loads(out)
    assert "dispatch" in payload
    assert "ready" in payload["dispatch"]
    # When --open-browser is false, the stderr hint should be silent.
    assert "hint:" not in err


def test_portal_html_emits_hint_on_open_when_not_ready(
    isolated_home, monkeypatch, capsys
):
    """`portal-html --open-browser` on an empty install MUST emit the
    install-extension hint to stderr — otherwise the user opens a
    launchpad whose buttons silently no-op. Phase 4 added the in-page
    banner; this is the CLI-side mirror so headless invocations aren't
    silent."""
    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.setattr(
        "trinity_local.launchpad_data._shortcut_status",
        lambda: {"ok": True, "applicable": False},
    )
    # No-op the actual file open — we don't want to launch a browser
    # from the test process. Also keep `opened: False` in the JSON.
    monkeypatch.setattr(
        "trinity_local.commands.portal.open_path", lambda path: False
    )
    from trinity_local.commands.portal import handle_portal_html

    args = SimpleNamespace(title="Trinity test", open_browser=True)
    handle_portal_html(args)
    out, err = capsys.readouterr()
    payload = json.loads(out)
    assert payload["dispatch"]["ready"] is False
    assert "hint:" in err
    assert "install-extension" in err


def test_portal_html_silent_on_open_when_ready(
    isolated_home, monkeypatch, capsys
):
    """When dispatch is wired (here: shortcut applicable + ok), the
    CLI must NOT print a noisy hint. Silence is the success signal."""
    monkeypatch.setattr("shutil.which", lambda name: None)
    monkeypatch.setattr(
        "trinity_local.launchpad_data._shortcut_status",
        lambda: {"ok": True, "applicable": True, "name": "Trinity Dispatch"},
    )
    monkeypatch.setattr(
        "trinity_local.commands.portal.open_path", lambda path: True
    )
    from trinity_local.commands.portal import handle_portal_html

    args = SimpleNamespace(title="Trinity test", open_browser=True)
    handle_portal_html(args)
    out, err = capsys.readouterr()
    payload = json.loads(out)
    assert payload["dispatch"]["ready"] is True
    assert "hint:" not in err
