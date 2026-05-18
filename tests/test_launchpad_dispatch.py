"""Tests for the Phase 4 three-tier dispatch path.

Phase 4 of the macOS-Shortcuts → Chrome-extension transition routes
launchpad button clicks through one of three tiers in priority order:

  1. Chrome extension (via chrome.runtime.sendMessage to a known
     extension ID + the extension's onMessageExternal handler).
  2. macOS Shortcut (the existing shortcuts:// URL path).
  3. Inline install prompt banner.

This file covers the Python side of the contract:

- `launchpad_data._browser_extension()` reads the persisted ID written
  by `commands.install.handle_install_extension`.
- The launchpad pageData carries `browserExtension` so the file:// JS
  can call chrome.runtime.sendMessage(<id>, …) without guessing.
- `launchpad_runtime_js()` emits the `window.__TRINITY_DISPATCH__`
  contract on which both `launchCouncil` and `ingestOnce` rely.

The JS-side contract (probe → cache → dispatch) lives in
browser-extension/background.js + launchpad_runtime_js() and is
covered by the manifest + node --check smoke + the existing
test_install_extension.py for the manifest writes.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
    return tmp_path


def test_browser_extension_empty_when_settings_file_missing(isolated_home):
    """Fresh install — no extension.json yet. dispatch should report
    `configured: False` so the JS skips the extension probe."""
    from trinity_local.launchpad_data import _browser_extension

    result = _browser_extension()
    assert result == {"extensionId": None, "configured": False}


def test_browser_extension_reads_persisted_id(isolated_home, monkeypatch):
    """When install-extension has persisted the ID, _browser_extension
    surfaces it for the launchpad. The 32-char `a-p` format is Chrome's
    canonical extension-ID encoding."""
    from trinity_local import state_paths
    from trinity_local.launchpad_data import _browser_extension

    settings_dir = state_paths.telemetry_settings_dir()
    payload = {
        "extension_id": "abcdefghijklmnopabcdefghijklmnop",
        "host_path": "/usr/local/bin/trinity-local-capture-host",
        "browsers": ["chrome: /tmp/local.trinity.capture.json"],
    }
    (settings_dir / "extension.json").write_text(json.dumps(payload))

    result = _browser_extension()
    assert result == {
        "extensionId": "abcdefghijklmnopabcdefghijklmnop",
        "configured": True,
    }


def test_browser_extension_treats_missing_id_field_as_not_configured(isolated_home):
    """A malformed settings file (no extension_id, or empty string) must
    NOT promote the launchpad to `configured: True` — that would point
    chrome.runtime.sendMessage at a falsy ID and silently fail every
    dispatch."""
    from trinity_local import state_paths
    from trinity_local.launchpad_data import _browser_extension

    settings_dir = state_paths.telemetry_settings_dir()
    (settings_dir / "extension.json").write_text(json.dumps({"host_path": "/x"}))

    result = _browser_extension()
    assert result["configured"] is False
    assert result["extensionId"] is None


def test_browser_extension_treats_malformed_json_as_not_configured(isolated_home):
    """Corrupt settings file must not raise — degrade gracefully."""
    from trinity_local import state_paths
    from trinity_local.launchpad_data import _browser_extension

    settings_dir = state_paths.telemetry_settings_dir()
    (settings_dir / "extension.json").write_text("not-json{")

    result = _browser_extension()
    assert result["configured"] is False


def test_install_extension_persists_id_for_launchpad(isolated_home, monkeypatch, capsys):
    """End-to-end: `trinity-local install-extension --extension-id <X>`
    must write the settings file that `_browser_extension` reads."""
    from trinity_local import state_paths
    from trinity_local.commands.install import handle_install_extension

    monkeypatch.setattr(
        "shutil.which", lambda name: f"/usr/local/bin/{name}"
    )
    # Avoid touching the real Native Messaging directories on macOS/Linux.
    monkeypatch.setattr(
        "trinity_local.commands.install._native_messaging_dirs",
        lambda browsers: [("chrome", isolated_home / "fake-chrome-nm")],
    )

    args = SimpleNamespace(
        extension_id="abcdefghijklmnopabcdefghijklmnop",
        host_path=None,
        browsers=["chrome"],
        firefox=False,
    )
    rc = handle_install_extension(args)
    assert rc == 0 or rc is None

    settings_file = state_paths.telemetry_settings_dir() / "extension.json"
    assert settings_file.exists()
    payload = json.loads(settings_file.read_text())
    assert payload["extension_id"] == "abcdefghijklmnopabcdefghijklmnop"
    assert "host_path" in payload


def test_launchpad_runtime_js_emits_dispatch_contract():
    """The runtime block must define window.__TRINITY_DISPATCH__ with the
    methods that launchpad_template.py callers depend on (`dispatch`,
    `probe`, `state`, `extensionId`). If this block is renamed or moved,
    the Vue methods break silently — every launch goes through the
    fallback path forever."""
    from trinity_local.launchpad_runtime import launchpad_runtime_js

    js = launchpad_runtime_js()
    assert "window.__TRINITY_DISPATCH__" in js
    assert "dispatch" in js
    assert "trinity-ping" in js
    assert "sessionStorage" in js
    # The two live tier names must appear so the result handler in Vue
    # can branch on them. (Tier-2 'shortcut' was retired 2026-05-18 with
    # the macOS Shortcut dispatcher kill — only extension + install-prompt
    # remain on the live dispatch path.)
    assert "'extension'" in js
    assert "'install-prompt'" in js
    assert "native-host-unavailable" in js
    # Tier-2 shortcut branch is GONE — Chrome extension is the only
    # live dispatch path. Regression guard against accidental re-add.
    # buildShortcutUrl() survives as a `return ''` no-op (callsites in
    # launchpad_template + council_review still reference the function
    # name; they pass '' into dispatch which ignores it).
    assert "'shortcut'" not in js
    assert "shortcuts://run-shortcut" not in js


def test_launchpad_runtime_js_uses_pageData_for_extension_id():
    """The dispatch script must read the extension ID from pageData
    (the only path the file:// page has) — not hard-code anything."""
    from trinity_local.launchpad_runtime import launchpad_runtime_js

    js = launchpad_runtime_js()
    assert "pageData.browserExtension" in js


def test_launchpad_runtime_js_includes_external_messaging_protocol():
    """sendMessage to a specific extension ID (not the default) is the
    only API that works for file:// → externally-connectable extension
    delivery. Regression-guard the signature."""
    from trinity_local.runtime_env import run_with_runtime_env  # noqa: F401 — keep import
    from trinity_local.launchpad_runtime import launchpad_runtime_js

    js = launchpad_runtime_js()
    # chrome.runtime.sendMessage(extensionId, message, callback) is the
    # contract; rejecting `chrome.runtime.sendMessage(message, callback)`.
    assert re.search(r"chrome\.runtime\.sendMessage\(\s*extensionId", js), (
        "dispatch must target a specific extensionId, not the default extension"
    )


def test_browser_extension_in_launchpad_pagedata(isolated_home):
    """The pageData payload the launchpad template consumes must carry
    `browserExtension` so the JS dispatch script can read it. Without
    this key, `pageData.browserExtension.extensionId` is undefined and
    the dispatcher defaults to `absent` forever."""
    from trinity_local.launchpad_data import build_page_data

    page_data = build_page_data(
        live_review_path=isolated_home / "stub-review.html",
        recent_councils=[],
    )
    assert "browserExtension" in page_data
    assert isinstance(page_data["browserExtension"], dict)
    assert "extensionId" in page_data["browserExtension"]
    assert "configured" in page_data["browserExtension"]
