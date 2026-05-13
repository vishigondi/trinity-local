"""me-card PNG export — turn /me lens output into a 1200×630 OG-shaped image.

Per council_35b2ae198a65b349: F3 (zero user screenshots in 14 days) fires by
default unless we ship a frictionless export-to-image artifact. The lens
text is the hero; the card is what gets posted to Twitter/LinkedIn.

Single function: `render_me_card(lens_data) -> bytes`. Caller owns where
the bytes land (CLI writes to disk; future launchpad button writes via
download). No HTTP, no headless browser — pure Pillow.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .me.pair_mining import load_lenses, load_orderings


# OG card shape — 1200×630 is the Open Graph spec; renders cleanly on
# Twitter, LinkedIn, Discord, Slack, iMessage previews.
CARD_WIDTH = 1200
CARD_HEIGHT = 630

# Trinity colors — match the launchpad's earthy/sage palette.
COLOR_BG = (252, 248, 239)        # cream
COLOR_INK = (26, 26, 26)          # deep ink for headlines
COLOR_MUTED = (95, 95, 95)        # muted ink for body
COLOR_ACCENT = (37, 88, 71)       # sage green for accents
COLOR_LENS_BG = (37, 88, 71, 12)  # subtle sage tint behind lens block

# Font path candidates — try macOS first, fall back to PIL default.
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
}


def _load_font(kind: str, size: int):
    """Best-effort font load with PIL default as a clean fallback. Pillow's
    default is a bitmap font so it'll render at any size but doesn't look
    great — the macOS path is the production path."""
    from PIL import ImageFont
    for path in _FONT_CANDIDATES.get(kind, []):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


@dataclass
class CardLensData:
    """Trimmed-down view of /me lenses for card rendering. The card shows
    at most one lens (the strongest) + up to 3 orderings; full /me has more
    detail than fits on a 1200×630 image."""
    lens_pole_a: str | None = None
    lens_pole_b: str | None = None
    failure_a: str | None = None
    failure_b: str | None = None
    orderings: list[tuple[str, str]] = None  # [(pole_a, pole_b), ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "lens_pole_a": self.lens_pole_a,
            "lens_pole_b": self.lens_pole_b,
            "failure_a": self.failure_a,
            "failure_b": self.failure_b,
            "orderings": self.orderings or [],
        }


def collect_card_data() -> CardLensData:
    """Read the latest lenses + orderings from disk, pick the strongest lens
    (most basins spanned) and the top 3 orderings. Returns empty fields when
    nothing has been built yet — callers should guard or surface an empty
    state."""
    lenses = load_lenses()
    orderings = load_orderings()

    # Strongest lens = most basins spanned (proxy for cross-domain reach)
    best = None
    if lenses:
        best = max(lenses, key=lambda p: len(p.basins_spanned or []))

    return CardLensData(
        lens_pole_a=best.pole_a if best else None,
        lens_pole_b=best.pole_b if best else None,
        failure_a=best.failure_a if best else None,
        failure_b=best.failure_b if best else None,
        orderings=[(o.pole_a, o.pole_b) for o in orderings[:3]],
    )


def _wrap(text: str, font, max_width: int, draw) -> list[str]:
    """Greedy word-wrap that respects the font's measured width. Pillow's
    textbbox gives pixel widths; we walk word-by-word."""
    if not text:
        return []
    words = text.split()
    lines: list[str] = []
    current = ""
    for word in words:
        candidate = (current + " " + word).strip()
        bbox = draw.textbbox((0, 0), candidate, font=font)
        if bbox[2] - bbox[0] <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    return lines


def render_me_card(data: CardLensData) -> bytes:
    """Render a 1200×630 PNG. Returns the bytes; caller writes to disk or
    pipes to stdout. Empty lens data still produces a card (fallback CTA
    "run `lens-build` to generate yours")."""
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (CARD_WIDTH, CARD_HEIGHT), COLOR_BG)
    draw = ImageDraw.Draw(img, "RGBA")

    eyebrow = _load_font("bold", 22)
    headline = _load_font("serif", 56)
    body = _load_font("regular", 32)
    fail_label = _load_font("bold", 20)
    ordering = _load_font("regular", 24)
    footer = _load_font("regular", 18)

    margin = 60
    y = margin

    # Eyebrow: "TRINITY · YOUR TASTE, DISTILLED"
    draw.text((margin, y), "TRINITY · YOUR TASTE, DISTILLED",
              font=eyebrow, fill=COLOR_ACCENT)
    y += 50

    if data.lens_pole_a and data.lens_pole_b:
        # Stacked-poles layout: two poles separated by a sage-tinted
        # horizontal divider with a small "vs." label. Avoids the
        # unicode-arrow tofu issue (Helvetica doesn't have ↔), gives the
        # tension visual weight, and stays font-independent (the divider
        # is a drawn shape, not a glyph).
        # Use slightly smaller headline so 2 poles + labels + orderings
        # fit comfortably on a 630px tall card.
        pole_font = _load_font("serif", 44)
        lines_a = _wrap(data.lens_pole_a, pole_font, CARD_WIDTH - 2 * margin, draw)
        lines_b = _wrap(data.lens_pole_b, pole_font, CARD_WIDTH - 2 * margin, draw)
        line_h = 56
        divider_h = 40
        block_top = y - 12
        block_height = (len(lines_a) + len(lines_b)) * line_h + divider_h + 24
        draw.rounded_rectangle(
            [margin - 16, block_top, CARD_WIDTH - margin + 16, block_top + block_height],
            radius=12,
            fill=(37, 88, 71, 18),
        )
        # Pole A on top
        for line in lines_a:
            draw.text((margin, y), line, font=pole_font, fill=COLOR_INK)
            y += line_h
        # Divider — horizontal sage line + centered "vs." label
        y += 8
        divider_y = y + 8
        line_left = margin + 60
        line_right = CARD_WIDTH - margin - 60
        # Two short rules with "vs." between them
        rule_color = (37, 88, 71, 80)
        label_text = "vs."
        label_font = _load_font("regular", 18)
        bbox = draw.textbbox((0, 0), label_text, font=label_font)
        lw = bbox[2] - bbox[0]
        center_x = (line_left + line_right) // 2
        draw.line(
            [(line_left, divider_y), (center_x - lw // 2 - 12, divider_y)],
            fill=rule_color, width=2,
        )
        draw.line(
            [(center_x + lw // 2 + 12, divider_y), (line_right, divider_y)],
            fill=rule_color, width=2,
        )
        draw.text((center_x - lw // 2, divider_y - 12), label_text,
                  font=label_font, fill=COLOR_ACCENT)
        y += divider_h
        # Pole B below
        for line in lines_b:
            draw.text((margin, y), line, font=pole_font, fill=COLOR_INK)
            y += line_h
        y += 24

        # Failure modes — only render if there's room. With two-pole stacked
        # headline, vertical space is tighter on long-pole lenses; clip
        # gracefully rather than overlapping the footer.
        if data.failure_a and y < CARD_HEIGHT - 200:
            draw.text((margin, y), "PURE-A FAILS AS",
                      font=fail_label, fill=COLOR_MUTED)
            y += 24
            draw.text((margin, y), data.failure_a,
                      font=body, fill=COLOR_INK)
            y += 44
        if data.failure_b and y < CARD_HEIGHT - 150:
            draw.text((margin, y), "PURE-B FAILS AS",
                      font=fail_label, fill=COLOR_MUTED)
            y += 24
            draw.text((margin, y), data.failure_b,
                      font=body, fill=COLOR_INK)
            y += 44
    else:
        # Empty state — invite the user to build their own /me
        draw.text((margin, y), "Run trinity-local lens-build",
                  font=headline, fill=COLOR_INK)
        y += 80
        draw.text((margin, y),
                  "to surface the tensions in how you think.",
                  font=body, fill=COLOR_MUTED)
        y += 60

    # Footer wordmark, bottom-right corner
    footer_text = "trinity-local · local-first AI council on your machine"
    bbox = draw.textbbox((0, 0), footer_text, font=footer)
    fw = bbox[2] - bbox[0]
    draw.text(
        (CARD_WIDTH - margin - fw, CARD_HEIGHT - margin - 18),
        footer_text,
        font=footer,
        fill=COLOR_MUTED,
    )

    # Optional: bottom-left orderings preview if room remains and we have
    # them. Trims to 2 to keep the card breathable.
    if data.orderings and y < CARD_HEIGHT - 200:
        draw.text((margin, CARD_HEIGHT - margin - 110),
                  "ALSO PREFERRED",
                  font=fail_label, fill=COLOR_MUTED)
        oy = CARD_HEIGHT - margin - 80
        for pa, pb in data.orderings[:2]:
            draw.text((margin, oy), f"{pa} > {pb}",
                      font=ordering, fill=COLOR_INK)
            oy += 32

    import io
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def write_me_card(out_path: Path) -> Path:
    """Convenience wrapper: collect data + render + write PNG to disk."""
    data = collect_card_data()
    png_bytes = render_me_card(data)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_bytes(png_bytes)
    return out_path
