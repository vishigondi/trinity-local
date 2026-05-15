"""Tests for the two shell wrappers shortcut_setup writes to ~/.trinity/bin/.

- **trinity-launchpad** is the desktop-icon shortcut: deliberately simple
  (`exec /usr/bin/open` on the cached HTML), no Python boot. The page on
  disk is kept fresh by `refresh_launchpad()` calls baked into every
  state-mutation path (council save, watch cycle, telemetry toggle).
- **trinity-dispatch** is the macOS Shortcut callback target — it's what
  fires when the user picks a model from the launchpad. It MUST survive
  venv relocation (per principle #13 / scale-plan item 13: shebang-baked
  paths break silently when the venv moves), so it walks a candidate
  list at runtime instead of hard-coding `#!/path/to/python`.

Both wrappers are launch-critical. The launchpad wrapper has had tests
since tick #15; trinity-dispatch was untested until tick #100 audit
flagged it as an untested public surface.
"""
from __future__ import annotations

import json
import stat
import sys
from pathlib import Path
from types import SimpleNamespace

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


class TestWriteDispatchWrapper:
    """trinity-dispatch is what the macOS Shortcut shells out to. It must:

    1. Live at ~/.trinity/bin/trinity-dispatch with mode 0755.
    2. NOT bake an absolute Python path into the shebang — that breaks
       when the venv is relocated (the bug that motivated principle #13).
    3. Walk a candidate list at runtime, preferring the project venv
       first so a global python doesn't accidentally win.
    4. Refuse to write the wrapper when the supplied Python or venv
       directory is missing — silent fallthrough would mask a broken
       install until the user clicks dispatch.
    """

    def test_writes_executable_shell_script(self, isolated_home):
        from trinity_local.shortcut_setup import write_dispatch_wrapper

        path = write_dispatch_wrapper(sys.executable)
        assert path.name == "trinity-dispatch"
        assert path.exists()
        mode = path.stat().st_mode
        assert mode & stat.S_IXUSR, f"wrapper must be executable, got mode {oct(mode)}"

    def test_shebang_is_generic_sh_not_baked_python(self, isolated_home):
        """The shebang must be `#!/bin/sh`, not `#!/path/to/venv/python`.
        Baking an absolute Python path is the original scale-plan item 13
        bug: the wrapper silently breaks when the venv moves or is
        recreated. The runtime `choose_python` body is the fix."""
        from trinity_local.shortcut_setup import write_dispatch_wrapper

        body = write_dispatch_wrapper(sys.executable).read_text()
        first_line = body.splitlines()[0]
        assert first_line == "#!/bin/sh", (
            f"dispatch shebang must be POSIX sh (so we can do venv detection "
            f"in shell at runtime, not bake a Python path); got: {first_line}"
        )
        assert "set -eu" in body, "fail-fast on missing vars or errors"

    def test_walks_venv_candidates_in_priority_order(self, isolated_home):
        """`choose_python` tries the venv-rooted Python first, then falls
        back to system python3/python. This ordering is load-bearing —
        a global python3 that doesn't have trinity_local installed must
        not win the race against a venv python that does."""
        from trinity_local.shortcut_setup import write_dispatch_wrapper

        body = write_dispatch_wrapper(sys.executable).read_text()
        # Find positions of each candidate; the venv ones must come first.
        venv_python3_idx = body.find('"$TRINITY_VENV_ROOT/bin/python3"')
        venv_python_idx = body.find('"$TRINITY_VENV_ROOT/bin/python"')
        sys_python3_idx = body.find('command -v python3')
        sys_python_idx = body.find('command -v python ')
        assert -1 < venv_python3_idx < venv_python_idx < sys_python3_idx < sys_python_idx, (
            "candidate order must be venv-python3, venv-python, system-python3, "
            f"system-python; got positions {venv_python3_idx}, {venv_python_idx}, "
            f"{sys_python3_idx}, {sys_python_idx}"
        )

    def test_validates_trinity_local_importable_before_choosing(self, isolated_home):
        """Each candidate is only accepted if `import trinity_local.dispatch_runner`
        succeeds against it. Otherwise a system python without Trinity
        installed could win the race after a venv move and fail at dispatch
        time with a stack trace instead of the clean error message."""
        from trinity_local.shortcut_setup import write_dispatch_wrapper

        body = write_dispatch_wrapper(sys.executable).read_text()
        assert "import trinity_local.dispatch_runner" in body
        # The fail-loud message must be present so a user with a broken
        # install sees something actionable instead of silent exit-1.
        assert "unable to locate a Python interpreter" in body

    def test_exec_runs_dispatch_runner_module(self, isolated_home):
        """The wrapper ends in `exec "$PYTHON_BIN" -m trinity_local.dispatch_runner "$@"`
        — running a module so the package's __main__-equivalent is used,
        not a script path that would change across installs."""
        from trinity_local.shortcut_setup import write_dispatch_wrapper

        body = write_dispatch_wrapper(sys.executable).read_text()
        assert 'exec "$PYTHON_BIN" -m trinity_local.dispatch_runner' in body

    def test_raises_when_python_missing(self, tmp_path, isolated_home):
        """Validation guard: a nonexistent Python path raises rather than
        writing a wrapper that silently dispatches to a broken interpreter."""
        from trinity_local.shortcut_setup import write_dispatch_wrapper

        bogus = str(tmp_path / "does-not-exist" / "python3")
        with pytest.raises(FileNotFoundError, match="Python executable not found"):
            write_dispatch_wrapper(bogus)

    def test_raises_when_venv_bin_missing(self, tmp_path, isolated_home):
        """Even if the Python binary exists, a missing venv bin/ directory
        is a broken setup — refuse to write the wrapper. project_venv_root
        infers the venv from the Python path; if there's no sibling bin/
        directory, fail loudly."""
        from trinity_local.shortcut_setup import write_dispatch_wrapper

        # Create a lone python binary with no surrounding venv structure.
        fake_python = tmp_path / "lonely-python"
        fake_python.write_text("#!/bin/sh\nexit 0\n")
        fake_python.chmod(0o755)
        with pytest.raises(FileNotFoundError, match="Virtual environment directory not found"):
            write_dispatch_wrapper(str(fake_python))


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


class TestInstallAppCommand:
    def test_install_app_command_prints_installed_paths(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ):
        from trinity_local.commands import install as install_cmd

        expected_launchpad_path = tmp_path / "launchpad.html"
        app_dir = tmp_path / "Apps"
        app_path = app_dir / "Trinity.app"

        monkeypatch.setattr(install_cmd, "refresh_launchpad", lambda: expected_launchpad_path)

        def fake_install_launchpad_shortcuts(*, launchpad_path: Path, destinations: list[Path] | None = None):
            assert launchpad_path == expected_launchpad_path
            assert destinations == [app_dir]
            return [app_path]

        monkeypatch.setattr(install_cmd, "install_launchpad_shortcuts", fake_install_launchpad_shortcuts)

        install_cmd.handle_install_app(SimpleNamespace(destination=[str(app_dir)]))

        payload = json.loads(capsys.readouterr().out)
        assert payload == {
            "launchpad_path": str(expected_launchpad_path),
            "app_paths": [str(app_path)],
        }
