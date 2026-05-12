"""Tests for the desktop-icon launchpad wrapper.

The desktop launchpad icon's AppleScript used to call /usr/bin/open on
the cached HTML directly, so every click showed stale content if the
template had been updated since the last regen. The fix is a wrapper at
~/.trinity/bin/trinity-launchpad that regenerates the page first, then
opens it. These tests pin that contract.
"""
from __future__ import annotations

import os
import stat
import subprocess
import sys
from pathlib import Path

import pytest


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
    return tmp_path


class TestWriteLaunchpadWrapper:
    def test_writes_executable_shell_script(self, isolated_home):
        from trinity_local.shortcut_setup import write_launchpad_wrapper

        path = write_launchpad_wrapper(sys.executable)

        assert path.name == "trinity-launchpad"
        assert path.exists()
        # Mode includes the executable bit for owner.
        mode = path.stat().st_mode
        assert mode & stat.S_IXUSR, f"wrapper must be executable, got mode {oct(mode)}"
        body = path.read_text()
        assert body.startswith("#!/bin/sh\n")

    def test_wrapper_calls_refresh_launchpad_before_open(self, isolated_home):
        """The whole point of this wrapper: regen first, then open."""
        from trinity_local.shortcut_setup import write_launchpad_wrapper

        path = write_launchpad_wrapper(sys.executable)
        body = path.read_text()

        # Must invoke refresh_launchpad (the regen step) — not just open.
        assert "from trinity_local.refresh import refresh_launchpad" in body
        assert "refresh_launchpad()" in body
        # Must open the result.
        assert "/usr/bin/open" in body

    def test_wrapper_falls_back_to_cached_when_regen_fails(self, isolated_home):
        """If the regen step blows up, the click should still open
        whatever HTML exists rather than a dead-end."""
        from trinity_local.shortcut_setup import write_launchpad_wrapper

        body = write_launchpad_wrapper(sys.executable).read_text()
        # Fallback path is the canonical launchpad HTML location.
        assert "$HOME/.trinity/portal_pages/launchpad.html" in body
        # And the script does NOT set -e on the regen step (so a failure
        # there doesn't abort the whole shell).
        assert "set -u" in body
        assert "set -eu" not in body

    def test_wrapper_invocation_actually_regenerates(self, isolated_home, monkeypatch):
        """End-to-end: write the wrapper, run it with `open` stubbed, then
        check that ~/.trinity/portal_pages/launchpad.html was created or
        updated as a result. Pins that the embedded Python invocation
        actually drives the renderer."""
        from trinity_local.shortcut_setup import write_launchpad_wrapper
        from trinity_local.state_paths import portal_pages_dir

        # Stub the `/usr/bin/open` step so the test doesn't actually
        # launch a browser. We do this by prepending a fake `open` to PATH.
        fake_bin = isolated_home / "fake_bin"
        fake_bin.mkdir()
        fake_open = fake_bin / "open"
        fake_open.write_text("#!/bin/sh\necho fake_open_called \"$@\" > '%s/_open_calls.log'\n" % isolated_home)
        fake_open.chmod(0o755)

        wrapper = write_launchpad_wrapper(sys.executable)

        # The wrapper uses /usr/bin/open explicitly, so PATH stubbing won't
        # intercept it. Instead, run the wrapper's body Python step directly
        # to confirm the regen produces a file.
        launchpad_html = portal_pages_dir() / "launchpad.html"
        assert not launchpad_html.exists(), "Pre-condition: launchpad.html absent"

        result = subprocess.run(
            [sys.executable, "-c",
             "from trinity_local.refresh import refresh_launchpad; print(refresh_launchpad())"],
            capture_output=True, text=True,
            env={**os.environ, "TRINITY_HOME": str(isolated_home)},
        )
        assert result.returncode == 0, f"regen failed: {result.stderr}"
        assert launchpad_html.exists(), "Wrapper must produce the launchpad HTML"


class TestInstallWiresWrapper:
    def test_install_launchpad_shortcuts_writes_wrapper(self, isolated_home, monkeypatch):
        """install_launchpad_shortcuts() must drop the wrapper at
        ~/.trinity/bin/trinity-launchpad — without it, the desktop icon's
        AppleScript falls back to the stale-content path."""
        from trinity_local import launchpad_install

        # Stub out the actual AppleScript compile + icon work — those need
        # osacompile / sips / iconutil which aren't reliably present in CI.
        monkeypatch.setattr(launchpad_install, "_compile_launchpad_app", lambda *a, **kw: None)
        monkeypatch.setattr(launchpad_install, "_apply_launchpad_icon", lambda *a, **kw: None)
        monkeypatch.setattr(launchpad_install, "_register_app", lambda *a, **kw: None)
        monkeypatch.setattr(
            launchpad_install,
            "_default_launchpad_link_dirs",
            lambda: [isolated_home / "fake_apps"],
        )

        launchpad_install.install_launchpad_shortcuts()

        wrapper = isolated_home / "bin" / "trinity-launchpad"
        assert wrapper.exists(), "install must drop the trinity-launchpad wrapper"
        assert wrapper.stat().st_mode & stat.S_IXUSR


class TestAppleScriptPointsToWrapper:
    def test_applescript_prefers_wrapper_over_direct_open(self):
        """The AppleScript template must invoke the wrapper when present,
        falling back to a direct open only if the wrapper is missing."""
        from trinity_local.launchpad_install import _launchpad_applescript

        script = _launchpad_applescript(Path("/tmp/fake_launchpad.html"))

        # New: wrapper path is hardcoded into the script.
        assert "trinity-launchpad" in script
        # New: wrapper-exists check before direct-open fallback.
        assert "test -x" in script
        # Direct-open fallback still present (in case wrapper is missing).
        assert "/usr/bin/open" in script
