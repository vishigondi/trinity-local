from __future__ import annotations

import platform
import shutil
import subprocess
import webbrowser
from pathlib import Path


def _escape_applescript(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')


def _windows_escape(value: str) -> str:
    return value.replace("'", "''")


_TRINITY_APP_CANDIDATES = (
    Path("/Applications/Trinity.app"),
    Path.home() / "Desktop" / "Trinity.app",
    Path.home() / "Applications" / "Trinity.app",
)


def _find_trinity_app() -> Path | None:
    for candidate in _TRINITY_APP_CANDIDATES:
        if candidate.exists():
            return candidate
    return None


def notifications_enabled() -> bool:
    """Read ~/.trinity/settings/notifications.json — defaults to OFF.

    macOS Notification Center popups for every "ready to start council",
    "council ready", "drift alert", etc. turn into a steady wall of
    interruption once Trinity is running councils + watching transcripts.
    Off by default; flip on with `trinity-local notifications-enable`.
    """
    try:
        from .state_paths import state_dir
        settings = state_dir() / "settings" / "notifications.json"
        if not settings.exists():
            return False
        import json
        data = json.loads(settings.read_text(encoding="utf-8"))
        return bool(data.get("enabled", False))
    except Exception:
        return False


def notify(title: str, message: str) -> None:
    if not notifications_enabled():
        return
    system = platform.system().lower()
    try:
        if system == "darwin":
            # Use osascript directly. We previously routed through
            # Trinity.app for icon polish, but that side-effect-launched
            # the launchpad in a new tab on every council start /
            # completion / rate event — Trinity.app's default action is
            # "open launchpad" and the --args notify hint didn't suppress
            # it. Generic Script Editor icon is the smaller bug.
            if shutil.which("osascript"):
                script = (
                    f'display notification "{_escape_applescript(message)}" '
                    f'with title "{_escape_applescript(title)}"'
                )
                subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=False)
                return
        if system == "linux" and shutil.which("notify-send"):
            subprocess.run(["notify-send", title, message], capture_output=True, text=True, check=False)
            return
        if system == "windows" and shutil.which("powershell"):
            command = (
                "[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null; "
                "[Windows.Data.Xml.Dom.XmlDocument, Windows.Data.Xml.Dom.XmlDocument, ContentType = WindowsRuntime] > $null; "
                f"$xml = New-Object Windows.Data.Xml.Dom.XmlDocument; $xml.LoadXml('<toast><visual><binding template=\"ToastGeneric\"><text>{_windows_escape(title)}</text><text>{_windows_escape(message)}</text></binding></visual></toast>'); "
                "$toast = [Windows.UI.Notifications.ToastNotification]::new($xml); "
                "[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('trinity-local').Show($toast)"
            )
            subprocess.run(
                ["powershell", "-NoProfile", "-Command", command],
                capture_output=True,
                text=True,
                check=False,
            )
            return
    except Exception:
        return


def open_path(path: str | Path) -> bool:
    target = Path(path).expanduser().resolve()
    try:
        if platform.system().lower() == "darwin" and shutil.which("open"):
            subprocess.run(["open", str(target)], capture_output=True, text=True, check=False)
            return True
        if platform.system().lower() == "windows" and shutil.which("cmd"):
            subprocess.run(
                ["cmd", "/c", "start", "", str(target)],
                capture_output=True,
                text=True,
                check=False,
            )
            return True
        if platform.system().lower() == "linux" and shutil.which("xdg-open"):
            subprocess.run(["xdg-open", str(target)], capture_output=True, text=True, check=False)
            return True
        return webbrowser.open(target.as_uri())
    except Exception:
        return False
