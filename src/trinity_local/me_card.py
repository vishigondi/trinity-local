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
from typing import Any

from .me.pair_mining import load_lenses, load_orderings
from .share_card_base import (
    CARD_WIDTH,
    CARD_HEIGHT,
    COLOR_INK,
    COLOR_MUTED,
    COLOR_ACCENT,
    LANDING_URL as ME_CARD_LANDING_URL,
    FOOTER_TAGLINE as ME_CARD_FOOTER_TAGLINE,
    load_font as _load_font,
    wrap_text as _wrap,
    blank_canvas,
    save_png,
)

# Card-specific accent — the sage tint behind the paired-tension block.
COLOR_LENS_BG = (37, 88, 71, 12)


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


def render_me_card(data: CardLensData) -> bytes:
    """Render a 1200×630 PNG. Returns the bytes; caller writes to disk or
    pipes to stdout. Empty lens data still produces a card (fallback CTA
    "run `lens-build` to generate yours")."""
    img, draw = blank_canvas()
    # Re-init with RGBA mode to enable alpha-tinted sage block fill
    from PIL import ImageDraw
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
        draw.text((margin, y), "Run trinity-local lens",
                  font=headline, fill=COLOR_INK)
        y += 80
        draw.text((margin, y),
                  "to surface the tensions in how you think.",
                  font=body, fill=COLOR_MUTED)
        y += 60

    # Footer wordmark + install URL, bottom-right corner.
    # The URL is the SAME single-source-of-truth string used by eval_card
    # and council_card (keepwhatworks.com — single-sourced via
    # share_card_base.LANDING_URL since commit 8c30538). A recipient
    # who sees this me-card on Twitter follows the URL to the landing
    # page for the install one-liner.
    footer_text = f"{ME_CARD_FOOTER_TAGLINE}   ·   {ME_CARD_LANDING_URL}"
    bbox = draw.textbbox((0, 0), footer_text, font=footer)
    fw = bbox[2] - bbox[0]
    draw.text(
        (CARD_WIDTH - margin - fw, CARD_HEIGHT - margin - 18),
        footer_text,
        font=footer,
        fill=COLOR_MUTED,
    )

    # Bottom-left orderings preview. 100-persona audit P96 fix: prior
    # guard was `if data.orderings and y < CARD_HEIGHT - 200` (i.e. y < 430)
    # — on any real lens with 2 paired tensions + failure modes, y easily
    # crossed 430, so the orderings region (~460–542) silently dropped
    # despite JSON reporting orderings_count: 3. Left ~40% empty whitespace
    # below "hallucinated confidence".
    #
    # New rule: ALWAYS render orderings when present. Anchor to fixed
    # bottom region (CARD_HEIGHT - margin - 110 for label); if the upper
    # lens-render pushed y past the orderings label position, slide the
    # orderings block DOWN past y so it doesn't overlap. Footer stays at
    # absolute bottom; orderings live in the gap between lens-content and
    # footer.
    if data.orderings:
        # Default position: anchored bottom-left, with room for 2 rows + footer.
        orderings_label_y = CARD_HEIGHT - margin - 110
        # If lens content already runs past the orderings region, slide
        # down enough to clear (small 20px gap), accepting the orderings
        # may sit closer to the footer than ideal.
        if y > orderings_label_y - 20:
            orderings_label_y = min(y + 20, CARD_HEIGHT - margin - 80)
        draw.text((margin, orderings_label_y),
                  "ALSO PREFERRED",
                  font=fail_label, fill=COLOR_MUTED)
        oy = orderings_label_y + 30
        # Render up to 3 (was 2) — orderings_count up to 3 in real data.
        for pa, pb in data.orderings[:3]:
            if oy > CARD_HEIGHT - margin - 38:
                break  # would collide with footer line
            draw.text((margin, oy), f"{pa} > {pb}",
                      font=ordering, fill=COLOR_INK)
            oy += 32

    return save_png(img)


