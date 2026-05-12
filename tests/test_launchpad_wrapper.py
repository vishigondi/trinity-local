"""Tests for the desktop-icon launchpad wrapper.

The wrapper at ~/.trinity/bin/trinity-launchpad is deliberately simple:
just `exec /usr/bin/open` on the cached HTML. The page on disk is kept
fresh by `refresh_launchpad()` calls baked into every state-mutation
path (council save, watch cycle, telemetry toggle, etc.), so the
wrapper doesn't need to second-guess freshness — that would just slow
the click.
"""
from __future__ import annotations

import stat
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
        mode = path.stat().st_mode
        assert mode & stat.S_IXUSR, f"wrapper must be executable, got mode {oct(mode)}"
        body = path.read_text()
        assert body.startswith("#!/bin/sh\n")

    def test_wrapper_is_minimal(self, isolated_home):
        """The wrapper does ONE thing — open the cached launchpad. No Python
        boot, no regen, no background processes. Anything more makes the
        click slow without paying off — refresh_launchpad runs from
        state-mutation paths already."""
        from trinity_local.shortcut_setup import write_launchpad_wrapper

        body = write_launchpad_wrapper(sys.executable).read_text()
        # The body is two lines: shebang + exec open.
        non_empty_lines = [ln for ln in body.strip().splitlines() if ln.strip()]
        assert len(non_empty_lines) <= 2, (
            f"Wrapper must stay minimal; got {len(non_empty_lines)} lines:\n{body}"
        )
        assert "/usr/bin/open" in body
        assert "$HOME/.trinity/portal_pages/launchpad.html" in body

    def test_wrapper_does_not_invoke_python(self, isolated_home):
        """Regen is somebody else's job (council save, watch cycle, etc.).
        The wrapper must not shell into Python — that's what made clicks
        feel sluggish before."""
        from trinity_local.shortcut_setup import write_launchpad_wrapper

        body = write_launchpad_wrapper(sys.executable).read_text()
        assert "refresh_launchpad" not in body
        assert "import trinity_local" not in body
        assert "python" not in body.lower()


class TestInstallWiresWrapper:
    def test_install_launchpad_shortcuts_writes_wrapper(self, isolated_home, monkeypatch):
        """install_launchpad_shortcuts() drops the wrapper at
        ~/.trinity/bin/trinity-launchpad as part of the install flow."""
        from trinity_local import launchpad_install

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
