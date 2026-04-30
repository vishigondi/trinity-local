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
    return f'do shell script "open \\"file://{launchpad}\\""\n'


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
        from .portal_page import write_portal_html
        launchpad_path = write_portal_html()
    destinations = destinations or _default_launchpad_link_dirs()
    written: list[Path] = []
    for destination in destinations:
        written.append(write_launchpad_app(destination, launchpad_path))
    return written
