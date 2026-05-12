from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .runtime_env import project_venv_root, runtime_path_prefix
from .shortcuts_integration import DEFAULT_SHORTCUT_NAME
from .state_paths import shortcut_bin_dir, shortcut_setup_dir


def render_shortcut_setup_markdown(shortcut_name: str = DEFAULT_SHORTCUT_NAME) -> str:
    return f"""# {shortcut_name}

Create a macOS Shortcut named `{shortcut_name}` with this structure:

1. `Receive` text input.
2. `Get Text from Shortcut Input`.
3. `Run Shell Script` with:

```bash
payload="$(cat)"
"$HOME/.trinity/bin/trinity-dispatch" "$payload"
```

4. Set:

   - `Input` → `Text`
   - `Pass Input` → `to stdin`

Example Trinity payload:

```json
{{"name":"open_review","args":{{"task_id":"task_123","path":"/Users/me/review.html"}},"task_id":"task_123","metadata":{{"kind":"review_ready"}}}}
```

Security note:

- This Shortcut passes raw JSON payloads to `~/.trinity/bin/trinity-dispatch`.
- The local wrapper resolves the action into a command and executes it.
- Keep it local to your Mac.
- Do not reuse it for untrusted URLs or arbitrary browser content.
"""


def write_shortcut_setup(shortcut_name: str = DEFAULT_SHORTCUT_NAME) -> Path:
    path = shortcut_setup_dir() / "TRINITY_DISPATCH_SETUP.md"
    path.write_text(render_shortcut_setup_markdown(shortcut_name), encoding="utf-8")
    return path


def _render_dispatch_wrapper(python_executable: str) -> str:
    venv_root = str(project_venv_root(python_executable))
    path_prefix = runtime_path_prefix(python_executable)
    return f"""#!/bin/sh
set -eu

TRINITY_VENV_ROOT="{venv_root}"
TRINITY_PATH_PREFIX="{path_prefix}"

choose_python() {{
  for candidate in \
    "$TRINITY_VENV_ROOT/bin/python3" \
    "$TRINITY_VENV_ROOT/bin/python" \
    "$(command -v python3 2>/dev/null || true)" \
    "$(command -v python 2>/dev/null || true)"
  do
    [ -n "$candidate" ] || continue
    [ -x "$candidate" ] || continue
    if "$candidate" -c 'import trinity_local.dispatch_runner' >/dev/null 2>&1; then
      printf '%s\\n' "$candidate"
      return 0
    fi
  done
  return 1
}}

PYTHON_BIN="$(choose_python)" || {{
  echo "trinity-dispatch: unable to locate a Python interpreter with trinity_local installed" >&2
  exit 1
}}

export PATH="$TRINITY_PATH_PREFIX:$PATH"
exec "$PYTHON_BIN" -m trinity_local.dispatch_runner "$@"
"""


def _validate_python_executable(python_executable: str) -> bool:
    """Verify that the Python executable still exists."""
    return Path(python_executable).exists()


def _validate_venv_bin(python_executable: str) -> bool:
    """Verify that the venv bin directory still exists."""
    venv_bin = project_venv_root(python_executable) / "bin"
    return venv_bin.exists() and venv_bin.is_dir()


def write_dispatch_wrapper(python_executable: str | None = None) -> Path:
    """Write the trinity-dispatch wrapper script to ~/.trinity/bin/.

    Validates that the Python executable and venv are still available.
    Returns the path to the wrapper, which is created even if validation fails.
    """
    exec_path = python_executable or sys.executable
    if not _validate_python_executable(exec_path):
        raise FileNotFoundError(f"Python executable not found: {exec_path}")
    if not _validate_venv_bin(exec_path):
        raise FileNotFoundError(f"Virtual environment directory not found for {exec_path}")

    path = shortcut_bin_dir() / "trinity-dispatch"
    script = _render_dispatch_wrapper(exec_path)
    path.write_text(script, encoding="utf-8")
    path.chmod(0o755)
    return path


def _render_launchpad_wrapper(python_executable: str) -> str:
    """Trivially simple wrapper: just open the cached launchpad HTML.

    refresh_launchpad() is already wired into every state-mutation path
    that matters (council save, watch cycle, telemetry toggle, etc.), so
    the launchpad on disk is fresh by the time the user clicks. The
    wrapper exists to give the desktop icon ONE path to open — keeping
    the icon's AppleScript dumb. No Python boot, no regen wait, no
    background process; just a 50ms shell-out to `/usr/bin/open`.

    Dev iteration on the template itself: run `trinity-local portal-html`
    after editing — that's the explicit "rebuild the page" command. The
    wrapper deliberately doesn't second-guess your edits.
    """
    # python_executable kept in the signature for parity with
    # write_dispatch_wrapper (and future use), even though this wrapper
    # doesn't currently shell into Python.
    _ = python_executable
    return """#!/bin/sh
exec /usr/bin/open "file://$HOME/.trinity/portal_pages/launchpad.html"
"""


def write_launchpad_wrapper(python_executable: str | None = None) -> Path:
    """Write the trinity-launchpad wrapper script to ~/.trinity/bin/.

    The desktop icon calls this wrapper instead of opening the cached HTML
    directly, so every click refreshes content from the current template
    (~1s regen vs always-stale clicks).
    """
    exec_path = python_executable or sys.executable
    if not _validate_python_executable(exec_path):
        raise FileNotFoundError(f"Python executable not found: {exec_path}")
    if not _validate_venv_bin(exec_path):
        raise FileNotFoundError(f"Virtual environment directory not found for {exec_path}")

    path = shortcut_bin_dir() / "trinity-launchpad"
    path.write_text(_render_launchpad_wrapper(exec_path), encoding="utf-8")
    path.chmod(0o755)
    return path


def _find_bundled_shortcut(shortcut_name: str = DEFAULT_SHORTCUT_NAME) -> Path | None:
    """Look for a bundled .shortcut file in the project root."""
    from .config import project_root
    candidates = [
        project_root() / f"{shortcut_name}.shortcut",
        project_root() / f"{shortcut_name.replace(' ', '_')}.shortcut",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    # Fallback: any .shortcut file in the project root
    for candidate in project_root().glob("*.shortcut"):
        return candidate
    return None


def _shortcut_installed(shortcut_name: str = DEFAULT_SHORTCUT_NAME) -> bool:
    """Check if the named shortcut is already in the user's Shortcuts library."""
    try:
        result = subprocess.run(
            ["shortcuts", "list"],
            capture_output=True, text=True, timeout=10,
        )
        return shortcut_name in (result.stdout or "")
    except Exception:
        return False


def _render_installer_script(shortcut_name: str = DEFAULT_SHORTCUT_NAME) -> str:
    """Generate a shell script that creates the Trinity Dispatch shortcut.

    Uses the macOS `shortcuts` CLI to check if the shortcut exists.
    Since macOS doesn't support programmatic shortcut creation from shell,
    it opens the Shortcuts app for the user to create it manually.
    """
    return f'''#!/bin/zsh
# Trinity Dispatch Shortcut Installer
# Generated by trinity-local

set -e

SHORTCUT_NAME="{shortcut_name}"

echo "🔍 Checking for existing shortcut..."

if shortcuts list 2>/dev/null | grep -qF "$SHORTCUT_NAME"; then
    echo "✅ Shortcut '$SHORTCUT_NAME' already exists."
    echo "   Opening Shortcuts app for editing..."
    open "shortcuts://open-shortcut?name=$SHORTCUT_NAME"
    exit 0
fi

echo "📦 Creating shortcut '$SHORTCUT_NAME'..."
echo "   Note: macOS does not support programmatic shortcut creation."
echo "   Opening Shortcuts app — please create the shortcut manually."
echo ""
echo "   The setup guide has been written to:"
echo "   ~/.trinity/shortcut_setup/TRINITY_DISPATCH_SETUP.md"
echo ""

# Open Shortcuts app to the create screen
open "shortcuts://create-shortcut"

echo "✅ Shortcuts app opened. Follow the setup guide to configure."
echo ""
echo "   Quick steps:"
echo "   1. Name the shortcut: $SHORTCUT_NAME"
echo "   2. Add 'Get Text from Shortcut Input'"
echo "   3. Add 'Run Shell Script'"
echo "   4. Script:"
echo '      payload="$(cat)"'
echo '      "$HOME/.trinity/bin/trinity-dispatch" "$payload"'
echo "   5. Set Input = Text"
echo "   6. Set Pass Input = to stdin"
echo ""
echo "   For details, see the full guide:"
echo "   open ~/.trinity/shortcut_setup/TRINITY_DISPATCH_SETUP.md"
'''


def write_installer_script(shortcut_name: str = DEFAULT_SHORTCUT_NAME) -> Path:
    """Write the installer shell script to the setup directory."""
    script = _render_installer_script(shortcut_name)
    path = shortcut_setup_dir() / "install_shortcut.sh"
    path.write_text(script, encoding="utf-8")
    path.chmod(0o755)
    return path


def run_installer(shortcut_name: str = DEFAULT_SHORTCUT_NAME) -> tuple[bool, str]:
    """Install the Trinity Dispatch shortcut.

    Tries three strategies in order:
      1. If already installed → skip, open for editing
      2. If a bundled .shortcut file exists → sign & import via `open`
      3. Fall back to manual setup guide

    Returns (success, message).
    """
    # Always write the setup guide
    write_shortcut_setup(shortcut_name)

    # Write dispatch wrapper with validation
    wrapper_msg = ""
    try:
        wrapper_path = write_dispatch_wrapper()
        wrapper_msg = f"\n\n✅ Dispatch wrapper written to:\n   {wrapper_path}" if wrapper_path.exists() else ""
    except FileNotFoundError as exc:
        return False, (
            f"❌ Cannot create dispatch wrapper: {exc}\n\n"
            f"The virtual environment may have been moved or deleted.\n"
            f"Please run 'pip install -e .' again in your trinity-local directory."
        )

    # 1. Already installed?
    if _shortcut_installed(shortcut_name):
        return True, f"✅ Shortcut '{shortcut_name}' is already installed.{wrapper_msg}"

    # 2. Bundled .shortcut file?
    bundled = _find_bundled_shortcut(shortcut_name)
    if bundled:
        # Sign for sharing (so macOS accepts it without warnings)
        signed_path = shortcut_setup_dir() / f"{shortcut_name}-signed.shortcut"
        try:
            sign_result = subprocess.run(
                ["shortcuts", "sign", "--mode", "anyone",
                 "--input", str(bundled), "--output", str(signed_path)],
                capture_output=True, text=True, timeout=15,
            )
            import_file = signed_path if sign_result.returncode == 0 else bundled
        except Exception:
            import_file = bundled

        # Open the .shortcut file → triggers macOS "Add Shortcut?" dialog
        try:
            subprocess.run(
                ["open", str(import_file)],
                capture_output=True, text=True, timeout=10,
            )
            return True, (
                f"📦 Shortcut import dialog opened.\n"
                f"   Click 'Add Shortcut' in the dialog to finish.{wrapper_msg}"
            )
        except Exception as exc:
            return False, f"Failed to open shortcut file: {exc}"

    # 3. Fall back to manual installer script
    script_path = write_installer_script(shortcut_name)
    try:
        result = subprocess.run(
            ["/bin/zsh", str(script_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = (result.stdout or "").strip()
        if result.returncode == 0:
            return True, output + wrapper_msg
        return False, (result.stderr or output or "Unknown error")
    except subprocess.TimeoutExpired:
        return False, "Installer timed out."
    except OSError as exc:
        return False, str(exc)
