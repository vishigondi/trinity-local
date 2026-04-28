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


def notify(title: str, message: str) -> None:
    system = platform.system().lower()
    try:
        if system == "darwin" and shutil.which("osascript"):
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
