"""Render Chrome extension icons at the four required sizes.

The browser-extension/manifest.json had no `icons` block, so Chrome
rendered the gray puzzle-piece placeholder in the toolbar and the
extensions list. This script generates a brand-coherent set —
cream background, sage accent, serif "T" — at 16/32/48/128 px.

Re-run if `design_system.COLORS` palette changes or the mark needs
updating. Output lands under `browser-extension/icons/`.

The same brand cues are used across the launchpad CSS, share cards,
and (now) the toolbar icon — one visual language across surfaces.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "src"))

from PIL import Image, ImageDraw, ImageFont

from trinity_local.design_system import COLORS


SIZES = [16, 32, 48, 128]
OUT_DIR = REPO_ROOT / "browser-extension" / "icons"


def _font_for_size(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Find a serif font that exists on this machine; fallback to default."""
    candidates = [
        "/System/Library/Fonts/Supplemental/Times New Roman Bold.ttf",
        "/System/Library/Fonts/Times.ttc",
        "/System/Library/Fonts/Supplemental/Georgia Bold.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf",
    ]
    glyph_size = int(size * 0.72)
    for path in candidates:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, glyph_size)
            except OSError:
                continue
    return ImageFont.load_default()


def render_icon(size: int) -> Image.Image:
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    bg = COLORS["bg_base"]
    fg = COLORS["action_primary"]

    pad = max(1, size // 16)
    draw.ellipse(
        (pad, pad, size - pad - 1, size - pad - 1),
        fill=bg,
        outline=fg,
        width=max(1, size // 24),
    )

    font = _font_for_size(size)
    text = "T"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    x = (size - text_w) // 2 - bbox[0]
    y = (size - text_h) // 2 - bbox[1]
    draw.text((x, y), text, fill=fg, font=font)

    return img


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for size in SIZES:
        img = render_icon(size)
        path = OUT_DIR / f"icon-{size}.png"
        img.save(path, "PNG")
        print(f"  wrote {path} ({size}x{size})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
