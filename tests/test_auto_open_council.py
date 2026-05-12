"""Auto-open-council gate: ship Way 3 — after every council writes, if
the user has run `trinity-local auto-open-enable`, shell out `open
<review_path>` so the harness doesn't need to know. The hook lives in
council_runner._maybe_auto_open. These tests cover the gating logic
WITHOUT actually spawning `open` (we monkeypatch subprocess.Popen).
"""
from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
    return tmp_path


def test_default_off_no_open_call(isolated_home, monkeypatch):
    """Without `auto-open-enable`, the hook is a no-op — no subprocess
    spawned, no errors raised."""
    from trinity_local import council_runner

    popen_mock = MagicMock()
    monkeypatch.setattr("subprocess.Popen", popen_mock)

    council_runner._maybe_auto_open(Path("/tmp/anywhere.html"))
    popen_mock.assert_not_called()


def test_enabled_shells_out_on_darwin(isolated_home, monkeypatch):
    """With the setting on AND running on macOS, `open <path>` fires."""
    from trinity_local import council_runner
    from trinity_local.telemetry import load_telemetry_settings, save_telemetry_settings

    settings = load_telemetry_settings()
    settings.auto_open_council = True
    save_telemetry_settings(settings)

    monkeypatch.setattr(sys, "platform", "darwin")
    popen_mock = MagicMock()
    monkeypatch.setattr("subprocess.Popen", popen_mock)

    council_runner._maybe_auto_open(Path("/tmp/x.html"))
    popen_mock.assert_called_once()
    args = popen_mock.call_args[0][0]
    assert args[0] == "open"
    assert args[1] == "/tmp/x.html"


def test_enabled_but_linux_silently_skips(isolated_home, monkeypatch):
    """`open` is a macOS binary. Linux/Windows must not crash trying to
    spawn it — silently skip when sys.platform != 'darwin'."""
    from trinity_local import council_runner
    from trinity_local.telemetry import load_telemetry_settings, save_telemetry_settings

    settings = load_telemetry_settings()
    settings.auto_open_council = True
    save_telemetry_settings(settings)

    monkeypatch.setattr(sys, "platform", "linux")
    popen_mock = MagicMock()
    monkeypatch.setattr("subprocess.Popen", popen_mock)

    council_runner._maybe_auto_open(Path("/tmp/x.html"))
    popen_mock.assert_not_called()


def test_subprocess_exception_swallowed(isolated_home, monkeypatch):
    """If subprocess.Popen itself raises (e.g., PATH issue, sandbox
    block), the council write has already succeeded — the failure to
    open a browser must not propagate up and break the council return."""
    from trinity_local import council_runner
    from trinity_local.telemetry import load_telemetry_settings, save_telemetry_settings

    settings = load_telemetry_settings()
    settings.auto_open_council = True
    save_telemetry_settings(settings)

    monkeypatch.setattr(sys, "platform", "darwin")
    def boom(*args, **kwargs):
        raise OSError("PATH problem")
    monkeypatch.setattr("subprocess.Popen", boom)

    # Should NOT raise.
    council_runner._maybe_auto_open(Path("/tmp/x.html"))


def test_cli_enable_disable_toggles_setting(isolated_home, monkeypatch, capsys):
    """The two CLI handlers flip the persisted flag."""
    from types import SimpleNamespace
    from trinity_local.commands.telemetry import (
        handle_auto_open_enable,
        handle_auto_open_disable,
    )
    from trinity_local.telemetry import load_telemetry_settings

    # Default off
    assert load_telemetry_settings().auto_open_council is False

    handle_auto_open_enable(SimpleNamespace())
    capsys.readouterr()
    assert load_telemetry_settings().auto_open_council is True

    handle_auto_open_disable(SimpleNamespace())
    capsys.readouterr()
    assert load_telemetry_settings().auto_open_council is False
