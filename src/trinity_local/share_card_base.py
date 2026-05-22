"""Shared infrastructure for 1200×630 OG share cards.

Three card renderers (`me_card`, `eval_card`, `council_card`) used to
inline their own copies of the canvas dimensions, color palette, font
loader, wrap helper, and footer/CTA renderer. The doc-consistency tests
actively enforce that *"all three carry the same install CTA + same
landing URL"* — collapsing the shared contract here makes that
enforcement structural rather than fragile.

Each card module owns only its body (the unique data-dense middle) and
imports the canvas + footer from this base. Tufte direction: the body
is where every card gets data-dense — small multiples, inline labels,
no chartjunk — without re-rendering the brand contract surface.
"""
from __future__ import annotations


# OG card shape — 1200×630 renders cleanly on Twitter / LinkedIn / Discord
# / Slack / iMessage previews. Pinned per surface-shape convention.
CARD_WIDTH = 1200
CARD_HEIGHT = 630

# Trinity palette — cream BG + deep ink + sage accent. Matches the
# launchpad's earthy/sage palette. All three cards share these so a
# viewer sees a coherent product.
COLOR_BG = (252, 248, 239)        # cream
COLOR_INK = (26, 26, 26)          # deep ink for headlines
COLOR_MUTED = (95, 95, 95)        # muted ink for body
COLOR_ACCENT = (37, 88, 71)       # sage green for accents

# Single source of truth for the public landing URL and footer tagline
# on share artifacts. Mirrored across all three cards by importing here
# — any future brand pivot stays consistent.
LANDING_URL = "keepwhatworks.com"
# Logo char: ⠕ (U+2815, Braille pattern dots-135). Per user direction
# 2026-05-22 — the brand mark Trinity carries on every share artifact.
FOOTER_TAGLINE = "⠕ Trinity · keepwhatworks.com"


# Font path candidates — try macOS first, fall back to Linux DejaVu, then
# Pillow's bitmap default. The macOS path is the production path; the
# others keep the renderer functional in CI / on Linux contributors'
# machines.
_FONT_CANDIDATES = {
    "regular": [
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ],
    "bold": [
        "/System/Library/Fonts/HelveticaNeue.ttc",
        "/System/Library/Fonts/Helvetica.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ],
    "serif": [
        "/System/Library/Fonts/Times.ttc",
        "/System/Library/Fonts/Charter.ttc",
        "/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf",
    ],
    "mono": [
        "/System/Library/Fonts/Menlo.ttc",
        "/System/Library/Fonts/Monaco.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf",
    ],
}


def load_font(kind: str, size: int):
    """Best-effort font load with PIL bitmap default as a clean fallback.
    Pillow's default renders at any size but doesn't look great — the
    macOS path is the production path."""
    from PIL import ImageFont
    for path in _FONT_CANDIDATES.get(kind, []):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


def wrap_text(text: str, font, max_width: int, draw) -> list[str]:
    """Greedy word-wrap respecting the font's measured pixel width.
    Walks word-by-word using draw.textbbox; returns lines."""
    words = text.split()
    if not words:
        return []
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        candidate = f"{current} {word}"
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if (bbox[2] - bbox[0]) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def blank_canvas():
    """1200×630 cream canvas + ImageDraw handle. Every card starts here."""
    from PIL import Image, ImageDraw
    img = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), COLOR_BG)
    return img, ImageDraw.Draw(img)


def draw_footer(draw, *, cta_block_top: int, margin: int = 60) -> None:
    """Render the shared install CTA + landing URL + footer tagline.

    Layout (anchored to cta_block_top):
        cta_block_top:        "Install"
        cta_block_top + 28:   LANDING_URL  (sage)
        bottom-32:            FOOTER_TAGLINE  (right-aligned, muted)

    Each card's body owns where `cta_block_top` lands; everything below
    that is shared brand contract.
    """
    cta_label = load_font("regular", 14)
    cta_url = load_font("bold", 22)
    footer = load_font("regular", 12)

    draw.text((margin, cta_block_top), "Install", font=cta_label, fill=COLOR_MUTED)
    draw.text((margin, cta_block_top + 28), LANDING_URL,
              font=cta_url, fill=COLOR_ACCENT)

    bbox = draw.textbbox((0, 0), FOOTER_TAGLINE, font=footer)
    width = bbox[2] - bbox[0]
    draw.text(
        (CARD_WIDTH - margin - width, CARD_HEIGHT - 32),
        FOOTER_TAGLINE,
        font=footer,
        fill=COLOR_MUTED,
    )


def save_png(img) -> bytes:
    """Serialize the canvas to PNG bytes. Caller owns disk write."""
    import io
    buffer = io.BytesIO()
    img.save(buffer, format="PNG", optimize=True)
    return buffer.getvalue()
