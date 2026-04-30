"""macOS launchd daemon management for persistent watch-loop."""
from __future__ import annotations

import subprocess
from pathlib import Path

from .state_paths import state_dir


DAEMON_LABEL = "com.trinity.local.watch"
DAEMON_NAME = "Trinity Local Watcher"


def _launchd_plist_path() -> Path:
    """Path to the launchd plist file."""
    return Path.home() / "Library" / "LaunchAgents" / f"{DAEMON_LABEL}.plist"


def _render_launchd_plist(python_executable: str, venv_bin: str) -> str:
    """Generate the launchd plist XML for watch-loop daemon."""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>Label</key>
	<string>{DAEMON_LABEL}</string>
	<key>ProgramArguments</key>
	<array>
		<string>{python_executable}</string>
		<string>-m</string>
		<string>trinity_local.main</string>
		<string>watch-loop</string>
		<string>--notify</string>
	</array>
	<key>RunAtLoad</key>
	<true/>
	<key>KeepAlive</key>
	<dict>
		<key>SuccessfulExit</key>
		<false/>
	</dict>
	<key>StandardOutPath</key>
	<string>{state_dir() / 'daemon.log'}</string>
	<key>StandardErrorPath</key>
	<string>{state_dir() / 'daemon.error.log'}</string>
	<key>EnvironmentVariables</key>
	<dict>
		<key>PATH</key>
		<string>{venv_bin}:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin</string>
	</dict>
</dict>
</plist>
"""


def daemon_install(python_executable: str | None = None) -> tuple[bool, str]:
    """Install the watch-loop daemon.

    Returns (success, message).
    """
    import sys
    exec_path = python_executable or sys.executable
    venv_bin = str(Path(exec_path).parent.resolve())
    plist_path = _launchd_plist_path()

    if plist_path.exists():
        return True, f"✓ {DAEMON_NAME} is already installed."

    plist_path.parent.mkdir(parents=True, exist_ok=True)
    plist_content = _render_launchd_plist(exec_path, venv_bin)
    plist_path.write_text(plist_content, encoding="utf-8")

    try:
        subprocess.run(
            ["launchctl", "load", str(plist_path)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return (
            True,
            f"✓ {DAEMON_NAME} installed and started.\n"
            f"  Logs: {state_dir() / 'daemon.log'}\n"
            f"  To stop: trinity-local daemon-stop\n"
            f"  To uninstall: trinity-local daemon-uninstall",
        )
    except Exception as exc:
        plist_path.unlink(missing_ok=True)
        return False, f"Failed to load daemon: {exc}"


def daemon_uninstall() -> tuple[bool, str]:
    """Uninstall and stop the watch-loop daemon.

    Returns (success, message).
    """
    plist_path = _launchd_plist_path()

    if not plist_path.exists():
        return True, f"✓ {DAEMON_NAME} is not installed."

    try:
        subprocess.run(
            ["launchctl", "unload", str(plist_path)],
            capture_output=True,
            text=True,
            timeout=10,
        )
    except Exception:
        pass

    plist_path.unlink(missing_ok=True)
    return True, f"✓ {DAEMON_NAME} uninstalled."


def daemon_start() -> tuple[bool, str]:
    """Start the watch-loop daemon."""
    plist_path = _launchd_plist_path()

    if not plist_path.exists():
        return False, f"✗ {DAEMON_NAME} is not installed. Run: trinity-local daemon-install"

    try:
        subprocess.run(
            ["launchctl", "start", DAEMON_LABEL],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return True, f"✓ {DAEMON_NAME} started."
    except Exception as exc:
        return False, f"Failed to start daemon: {exc}"


def daemon_stop() -> tuple[bool, str]:
    """Stop the watch-loop daemon."""
    plist_path = _launchd_plist_path()

    if not plist_path.exists():
        return False, f"✗ {DAEMON_NAME} is not installed."

    try:
        subprocess.run(
            ["launchctl", "stop", DAEMON_LABEL],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return True, f"✓ {DAEMON_NAME} stopped."
    except Exception as exc:
        return False, f"Failed to stop daemon: {exc}"


def daemon_status() -> tuple[bool, str]:
    """Check if the watch-loop daemon is running."""
    plist_path = _launchd_plist_path()

    if not plist_path.exists():
        return True, f"✗ {DAEMON_NAME} is not installed."

    try:
        result = subprocess.run(
            ["launchctl", "list"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        is_running = DAEMON_LABEL in (result.stdout or "")
        status = "running" if is_running else "installed but not running"
        return True, f"✓ {DAEMON_NAME} is {status}."
    except Exception as exc:
        return False, f"Failed to check daemon status: {exc}"
