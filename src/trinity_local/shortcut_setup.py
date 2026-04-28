from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from .scoreboard import state_dir
from .shortcuts_integration import DEFAULT_SHORTCUT_NAME


def shortcut_setup_dir() -> Path:
    path = state_dir() / "shortcut_setup"
    path.mkdir(parents=True, exist_ok=True)
    return path


def shortcut_bin_dir() -> Path:
    path = state_dir() / "bin"
    path.mkdir(parents=True, exist_ok=True)
    return path


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
    # Use .parent first (the venv's bin/ dir where entry points live),
    # then resolve. If we resolve() first, symlinks chase to the Homebrew
    # framework dir which doesn't contain trinity-local.
    venv_bin = str(Path(python_executable).parent.resolve())
    return f"""#!{python_executable}
from __future__ import annotations

import json
import os
import subprocess
import sys

from trinity_local.dispatch_registry import command_for_dispatch, make_dispatch_action

VENV_BIN = "{venv_bin}"


def main() -> int:
    os.environ["PATH"] = VENV_BIN + ":" + os.environ.get("PATH", "")

    if len(sys.argv) >= 2:
        payload_text = sys.argv[1]
    else:
        payload_text = sys.stdin.read()

    if not payload_text.strip():
        print("trinity-dispatch: empty payload", file=sys.stderr)
        return 1

    try:
        raw = json.loads(payload_text)
    except json.JSONDecodeError as exc:
        print(f"trinity-dispatch: invalid JSON: {{exc}}", file=sys.stderr)
        return 1

    try:
        action = make_dispatch_action(
            raw["name"],
            args=raw.get("args", {{}}),
            task_id=raw.get("task_id"),
            metadata=raw.get("metadata", {{}}),
        )
    except Exception as exc:
        print(f"trinity-dispatch: invalid action: {{exc}}", file=sys.stderr)
        return 1

    command = command_for_dispatch(action)
    if not command:
        print(f"trinity-dispatch: no command mapping for action {{action.name}}", file=sys.stderr)
        return 1

    # /bin/zsh -lc starts a login shell which reinitializes PATH from
    # shell profiles, losing os.environ changes.  Inject the venv bin
    # directly into the command so trinity-local is always resolvable.
    wrapped = f'export PATH="{{VENV_BIN}}:$PATH"; {{command}}'
    completed = subprocess.run(["/bin/zsh", "-lc", wrapped], check=False)
    return int(completed.returncode)


if __name__ == "__main__":
    raise SystemExit(main())
"""


def write_dispatch_wrapper(python_executable: str | None = None) -> Path:
    """Write the trinity-dispatch wrapper script to ~/.trinity/bin/."""
    path = shortcut_bin_dir() / "trinity-dispatch"
    script = _render_dispatch_wrapper(python_executable or sys.executable)
    path.write_text(script, encoding="utf-8")
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
    # Always write the setup guide and dispatch wrapper
    write_shortcut_setup(shortcut_name)
    wrapper_path = write_dispatch_wrapper()
    wrapper_msg = f"\n\n✅ Dispatch wrapper written to:\n   {wrapper_path}" if wrapper_path.exists() else ""

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

