"""Render Chrome extension icons at the four required sizes.

The browser-extension/manifest.json had no `icons` block, so Chrome
rendered the gray puzzle-piece placeholder in the toolbar and the
extensions list. This script generates the canonical ⠕ Trinity mark
(U+2815 — Braille pattern dots-135) at 16/32/48/128 px.

**Variant: "04 Filled badge"** — sage fill + cream dots (inverse of
the original 01 Canonical Ring). Picked 2026-05-23 because the
filled-disk treatment survives best at 16 px (the actual toolbar
size) and pops against Chrome's light browser-chrome bar. The
inverse-contrast treatment is also more distinctive at a glance
than the thin-ring variants when scrolling the chrome://extensions
list past other gray-puzzle-piece extensions.

⠕ is the brand mark Trinity carries on every share artifact (see
`share_card_base.FOOTER_TAGLINE`) and the launchpad eyebrow
(`launchpad_template.py`). Same character end-to-end — README badge,
share cards (still using 01 Canonical Ring framing for editorial
context), launchpad eyebrow, and the toolbar icon (now 04 Filled
badge for legibility).

Re-run if `design_system.COLORS` palette changes or the mark needs
updating. Output lands under `browser-extension/icons/` (4 PNGs)
plus a sibling `docs/favicon.png` rendered at 64 px for the site.

Font fallback chain: Apple Braille → Apple Symbols → DejaVu Sans →
Pillow default bitmap. Most system sans fonts render ⠕ as the
tofu-box "missing glyph"; the chain ensures real Braille rendering
on macOS dev machines AND Linux CI / contributor machines.
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
FAVICON_PATH = REPO_ROOT / "docs" / "favicon.png"
FAVICON_SIZE = 64

# ⠕ — U+2815, Braille pattern dots-135. The Trinity brand mark.
MARK = "⠕"

# Font candidates that actually carry Braille glyphs. Order: macOS
# Braille-specific, macOS symbol, Linux DejaVu, then ultimate fallback.
_FONT_CANDIDATES = [
    "/System/Library/Fonts/Apple Braille.ttf",
    "/System/Library/Fonts/Apple Symbols.ttf",
    "/Library/Fonts/Apple Braille.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


def _hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return tuple(int(value[i:i + 2], 16) for i in (0, 2, 4))


def _scaled(size: int) -> tuple[int, int]:
    """Supersample dimensions so tiny icons stay crisp after downsize."""
    scale = 4 if size <= 48 else 2
    return size * scale, scale


def _font_with_braille(pixel_size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        if not Path(path).exists():
            continue
        try:
            font = ImageFont.truetype(path, pixel_size)
            # Verify the font actually renders ⠕ — Pillow will return
            # zero width for missing glyphs, so we check the bbox.
            bbox = font.getbbox(MARK)
            if bbox and (bbox[2] - bbox[0]) > 0:
                return font
        except OSError:
            continue
    # Last-resort fallback. Will likely render a tofu box; ship a
    # placeholder so the script doesn't crash in CI.
    return ImageFont.load_default()


def render_icon(canvas_size: int) -> Image.Image:
    """Render the "04 Filled badge" variant: sage disk + cream ⠕ dots.

    Sage fill instead of cream → maximum legibility at toolbar size
    (16 px) where thin strokes vanish into the browser chrome. Cream
    dots provide high-contrast brand mark legibility.
    """
    work_size, scale = _scaled(canvas_size)
    img = Image.new("RGBA", (work_size, work_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    fill = _hex_to_rgb(COLORS["action_primary"])  # sage — #255847 — disk
    glyph = _hex_to_rgb(COLORS["bg_base"])        # cream — #f5efe3 — ⠕ dots

    # Solid sage disk. No outer ring — the filled treatment IS the
    # silhouette (mass beats stroke at 16 px). 1 px inset prevents
    # the LANCZOS downsize from clipping anti-aliased edges.
    inset = 1
    draw.ellipse(
        (inset, inset, work_size - inset, work_size - inset),
        fill=fill,
    )

    # Center the ⠕ glyph in cream. Braille glyphs sit high in the
    # em-box, so we measure the actual ink bbox (not the font bbox)
    # and translate accordingly — keeps the mark visually centered,
    # not just baseline-aligned.
    glyph_size = int(work_size * 0.58)
    font = _font_with_braille(glyph_size)
    bbox = draw.textbbox((0, 0), MARK, font=font)
    glyph_w = bbox[2] - bbox[0]
    glyph_h = bbox[3] - bbox[1]
    cx = (work_size - glyph_w) // 2 - bbox[0]
    cy = (work_size - glyph_h) // 2 - bbox[1]
    draw.text((cx, cy), MARK, fill=glyph, font=font)

    if scale != 1:
        img = img.resize((canvas_size, canvas_size), Image.LANCZOS)
    return img


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for size in SIZES:
        path = OUT_DIR / f"icon-{size}.png"
        img = render_icon(size)
        img.save(path, format="PNG")
        print(f"  → {path.relative_to(REPO_ROOT)}  ({size}×{size})")

    FAVICON_PATH.parent.mkdir(parents=True, exist_ok=True)
    favicon = render_icon(FAVICON_SIZE)
    favicon.save(FAVICON_PATH, format="PNG")
    print(f"  → {FAVICON_PATH.relative_to(REPO_ROOT)}  ({FAVICON_SIZE}×{FAVICON_SIZE})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
