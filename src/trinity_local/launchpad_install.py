from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path

from .state_paths import portal_pages_dir

TRINITY_APP_NAME = "Trinity.app"
LAUNCHPAD_ICON_RELATIVE_PATH = Path("assets") / "binary_code.png"
LEGACY_LAUNCHPAD_LINK_NAMES = (
    "Trinity Launchpad.webloc",
    "Trinity.webloc",
    "Trinity Launchpad.app",
)


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _default_launchpad_link_dirs() -> list[Path]:
    home = Path.home()
    destinations = []

    system_apps = Path("/Applications")
    if system_apps.exists() and os.access(system_apps, os.W_OK):
        destinations.append(system_apps)

    destinations.append(home / "Desktop")
    return destinations


def _remove_launchpad_artifact(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
        return
    if path.is_dir():
        shutil.rmtree(path)


def _cleanup_legacy_launchpad_links(destination_dir: Path) -> None:
    for name in LEGACY_LAUNCHPAD_LINK_NAMES:
        legacy = destination_dir / name
        if legacy.exists() or legacy.is_symlink():
            _remove_launchpad_artifact(legacy)


def _launchpad_applescript(launchpad_path: Path) -> str:
    launchpad = str(launchpad_path.expanduser().resolve())
    # Plain `do shell script` to launch the launchpad. The AppleScriptObjC
    # bridge (NSWorkspace) was throwing -1700 on Apple Silicon Sequoia; the
    # shell-script TCC prompt only appears once and is then granted forever.
    #
    # The wrapper at ~/.trinity/bin/trinity-launchpad regenerates the page
    # before opening it, so every click sees fresh content from the current
    # template. If the wrapper is missing (e.g. user upgraded the package but
    # never re-ran install-mcp), fall back to opening the cached HTML.
    wrapper = Path.home() / ".trinity" / "bin" / "trinity-launchpad"
    return (
        'on run argv\n'
        '  try\n'
        '    if (count of argv) >= 1 then\n'
        '      set firstArg to item 1 of argv\n'
        '      if firstArg is "notify" then\n'
        '        set notifTitle to ""\n'
        '        set notifBody to ""\n'
        '        if (count of argv) >= 2 then set notifTitle to item 2 of argv\n'
        '        if (count of argv) >= 3 then set notifBody to item 3 of argv\n'
        '        display notification notifBody with title notifTitle\n'
        '        return\n'
        '      end if\n'
        '    end if\n'
        '  on error\n'
        '    -- fall through to launchpad open\n'
        '  end try\n'
        f'  set wrapperPath to "{wrapper}"\n'
        f'  set cachedPath to "{launchpad}"\n'
        '  try\n'
        '    set wrapperExists to (do shell script "test -x " & quoted form of wrapperPath & " && echo yes || echo no")\n'
        '    if wrapperExists is "yes" then\n'
        '      do shell script quoted form of wrapperPath\n'
        '    else\n'
        '      do shell script "/usr/bin/open " & quoted form of ("file://" & cachedPath)\n'
        '    end if\n'
        '  on error\n'
        '    do shell script "/usr/bin/open " & quoted form of ("file://" & cachedPath)\n'
        '  end try\n'
        '  return\n'
        'end run\n'
    )


def _compile_launchpad_app(target: Path, script: str) -> None:
    if target.exists() or target.is_symlink():
        _remove_launchpad_artifact(target)
    with tempfile.TemporaryDirectory() as tmpdir:
        source_path = Path(tmpdir) / "launchpad.applescript"
        source_path.write_text(script, encoding="utf-8")
        subprocess.run(
            ["osacompile", "-o", str(target), str(source_path)],
            check=True,
            capture_output=True,
            text=True,
        )
    _normalize_applet_plist(target)


def _normalize_applet_plist(app_path: Path) -> None:
    """osacompile bakes a legacy Info.plist with LSRequiresCarbon=true and a
    bundle identifier collision with other applets. On Apple Silicon Sequoia,
    LaunchServices can refuse to launch such bundles and fall back to Script
    Editor when the user double-clicks. Strip the legacy keys and stamp a
    stable Trinity-specific bundle identifier."""
    plist_path = app_path / "Contents" / "Info.plist"
    if not plist_path.exists():
        return
    plutil = shutil.which("plutil")
    if plutil is None:
        return
    subprocess.run(
        [plutil, "-remove", "LSRequiresCarbon", str(plist_path)],
        capture_output=True,
        check=False,
    )
    subprocess.run(
        [plutil, "-remove", "LSMinimumSystemVersionByArchitecture", str(plist_path)],
        capture_output=True,
        check=False,
    )
    # Insert (or replace) a stable bundle id so notifications/click-targets
    # are owned by Trinity rather than colliding with the generic AppleScript
    # applet identifier.
    subprocess.run(
        [plutil, "-replace", "CFBundleIdentifier", "-string", "com.trinity-local.launchpad", str(plist_path)],
        capture_output=True,
        check=False,
    )
    subprocess.run(
        [plutil, "-replace", "LSMinimumSystemVersion", "-string", "10.15", str(plist_path)],
        capture_output=True,
        check=False,
    )


def _find_launchpad_icon_source() -> Path | None:
    candidate = _project_root() / LAUNCHPAD_ICON_RELATIVE_PATH
    if candidate.exists():
        return candidate
    return None


def _apply_launchpad_icon(app_path: Path, image_path: Path | None) -> None:
    if image_path is None or not image_path.exists():
        return

    resources_dir = app_path / "Contents" / "Resources"
    resources_dir.mkdir(parents=True, exist_ok=True)
    target_icon = resources_dir / "applet.icns"

    # Remove Assets.car so our applet.icns takes precedence (osacompile bakes
    # the default AppleScript icon into Assets.car which overrides loose icns files)
    assets_car = resources_dir / "Assets.car"
    if assets_car.exists():
        assets_car.unlink()

    with tempfile.TemporaryDirectory() as tmpdir:
        iconset = Path(tmpdir) / "icon.iconset"
        iconset.mkdir()
        entries = [
            ("icon_16x16.png", 16),
            ("icon_16x16@2x.png", 32),
            ("icon_32x32.png", 32),
            ("icon_32x32@2x.png", 64),
            ("icon_128x128.png", 128),
            ("icon_128x128@2x.png", 256),
            ("icon_256x256.png", 256),
            ("icon_256x256@2x.png", 512),
            ("icon_512x512.png", 512),
            ("icon_512x512@2x.png", 1024),
        ]
        for filename, size in entries:
            subprocess.run(
                [
                    "sips", "-z", str(size), str(size),
                    "--setProperty", "format", "png",
                    str(image_path), "--out", str(iconset / filename),
                ],
                capture_output=True,
            )
        result = subprocess.run(
            ["iconutil", "-c", "icns", str(iconset), "-o", str(target_icon)],
            capture_output=True,
        )
        if result.returncode != 0:
            try:
                from PIL import Image
                with Image.open(image_path) as img:
                    img = img.convert("RGBA")
                    s = min(img.width, img.height)
                    img = img.crop(((img.width - s) // 2, (img.height - s) // 2, (img.width + s) // 2, (img.height + s) // 2))
                    img.save(target_icon, format="ICNS", sizes=[(sz, sz) for sz in (16, 32, 128, 256, 512)])
            except Exception:
                pass


def _register_app(app_path: Path) -> None:
    lsregister = Path(
        "/System/Library/Frameworks/CoreServices.framework"
        "/Frameworks/LaunchServices.framework/Support/lsregister"
    )
    if lsregister.exists():
        subprocess.run([str(lsregister), "-f", str(app_path)], capture_output=True)
    subprocess.run(["touch", str(app_path)], capture_output=True)


def write_launchpad_app(destination_dir: Path, launchpad_path: Path) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)
    _cleanup_legacy_launchpad_links(destination_dir)
    target = destination_dir / TRINITY_APP_NAME
    _compile_launchpad_app(target, _launchpad_applescript(launchpad_path))
    _apply_launchpad_icon(target, _find_launchpad_icon_source())
    _register_app(target)
    return target


def install_launchpad_shortcuts(
    *,
    launchpad_path: Path | None = None,
    destinations: list[Path] | None = None,
) -> list[Path]:
    if launchpad_path is None:
        from .refresh import refresh_launchpad
        launchpad_path = refresh_launchpad()
    # Drop the regen-then-open wrapper at ~/.trinity/bin/trinity-launchpad so
    # the desktop icon's AppleScript can call it. Best-effort: if writing the
    # wrapper fails (e.g. missing venv), the AppleScript falls back to opening
    # the cached HTML directly.
    try:
        from .shortcut_setup import write_launchpad_wrapper
        write_launchpad_wrapper()
    except (FileNotFoundError, OSError):
        pass
    destinations = destinations or _default_launchpad_link_dirs()
    written: list[Path] = []
    for destination in destinations:
        written.append(write_launchpad_app(destination, launchpad_path))
    return written
