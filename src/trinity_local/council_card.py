"""council-share PNG export — render a council outcome as a 1200×630 OG card.

Companion to eval_card.py (eval results) and me_card.py (lens). All three
share the same visual language (cream BG, sage accent, serif headline,
mono CTA) so a viewer sees a coherent product, not three disconnected
artifacts.

Single function: ``render_council_card(card_data) -> bytes``. CLI writes
the bytes to disk; the recipient sees:

1. Headline — "[Winner] won" with the 3-model lineup
2. 1-2 agreed_claims (where models converged)
3. 1 disagreed_claim with its "why_matters" (where they fought + the stakes)
4. Install CTA → vishigondi.github.io/trinity-local

Privacy mode is the default. The user's verbatim prompt is NEVER inlined
on the card; the prompt may be present in the JSON outcome on disk but
never crosses to the share artifact. Members' full responses are also
omitted — only the chairman-extracted agreed_claims + disagreed_claims
land on the card.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .share_card_base import (
    CARD_WIDTH,
    CARD_HEIGHT,
    COLOR_BG,
    COLOR_INK,
    COLOR_MUTED,
    COLOR_ACCENT,
    LANDING_URL as CTA_LANDING_URL,
    FOOTER_TAGLINE,
    load_font as _load_font,
    blank_canvas,
    save_png,
)

# Card-specific accent — warm brown for the disagreement section that
# contrasts against the sage agreement accent.
COLOR_DISAGREE = (140, 60, 30)


@dataclass
class CouncilCardData:
    """Card-shaped projection of a CouncilOutcome. Members + claims
    are pre-flattened to plain strings so the renderer doesn't have to
    know about the CouncilRoutingLabel shape.
    """
    members: list[str] = field(default_factory=list)
    winner: str | None = None
    agreed_claims: list[str] = field(default_factory=list)
    disagreed_claim: str | None = None
    disagreed_why: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "members": list(self.members),
            "winner": self.winner,
            "agreed_claims": list(self.agreed_claims),
            "disagreed_claim": self.disagreed_claim,
            "disagreed_why": self.disagreed_why,
        }


def collect_card_data_from_outcome(outcome) -> CouncilCardData:
    """Build a CouncilCardData from a CouncilOutcome.

    Privacy-safe by construction: only fields from `routing_label`
    (chairman-extracted summary) cross to the card. The user's
    verbatim prompt + the members' full response text are NEVER read
    here, so they cannot leak through this path.
    """
    members = [m.provider for m in (outcome.member_results or [])]
    winner = outcome.winner_provider

    label = outcome.routing_label
    agreed: list[str] = []
    disagreed_claim: str | None = None
    disagreed_why: str | None = None
    if label is not None:
        agreed = [str(c) for c in (label.agreed_claims or [])]
        if label.disagreed_claims:
            # Pick the FIRST disagreed_claim — the chairman emits them
            # in priority order. Each item is a dict {provider, claim,
            # why_matters}; we render `claim` + `why_matters`.
            d0 = label.disagreed_claims[0] or {}
            disagreed_claim = str(d0.get("claim") or "") or None
            disagreed_why = str(d0.get("why_matters") or "") or None

    return CouncilCardData(
        members=members,
        winner=winner,
        agreed_claims=agreed,
        disagreed_claim=disagreed_claim,
        disagreed_why=disagreed_why,
    )


def _provider_display(name: str | None) -> str:
    if not name:
        return "?"
    friendly = {"claude": "Claude", "codex": "GPT", "gemini": "Gemini"}
    return friendly.get(name.lower(), name.capitalize())


def _wrap(text: str, font, max_width: int, draw) -> list[str]:
    """Greedy word-wrap that respects pixel width."""
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


CTA_HEADLINE = "Run your own council:"
# CTA_LANDING_URL / FOOTER_TAGLINE imported from share_card_base.


def render_council_card(data: CouncilCardData) -> bytes:
    """Render the 1200×630 PNG. Returns bytes; caller writes to disk."""
    img, draw = blank_canvas()
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img, "RGBA")

    eyebrow = _load_font("bold", 22)
    headline = _load_font("serif", 48)
    sub = _load_font("regular", 22)
    section_label = _load_font("bold", 18)
    claim_body = _load_font("regular", 20)
    cta_label = _load_font("bold", 20)
    cta_url = _load_font("mono", 22)
    footer = _load_font("regular", 18)

    margin = 60
    y = margin

    # ── Eyebrow ───────────────────────────────────────────────────
    draw.text((margin, y), "TRINITY · YOUR COUNCIL",
              font=eyebrow, fill=COLOR_ACCENT)
    y += 46

    # ── Headline ──────────────────────────────────────────────────
    if data.winner and data.members:
        members_text = " · ".join(_provider_display(m) for m in data.members[:3])
        headline_text = f"Trinity asked {members_text}."
        # Two-line headline — first line = roster, second line = winner.
        draw.text((margin, y), headline_text, font=headline, fill=COLOR_INK)
        y += 60
        winner_text = f"{_provider_display(data.winner)} won."
        draw.text((margin, y), winner_text, font=headline, fill=COLOR_ACCENT)
        y += 70
    elif data.members:
        # No winner recorded — still show the roster.
        members_text = " · ".join(_provider_display(m) for m in data.members[:3])
        draw.text((margin, y), f"Trinity asked {members_text}.",
                  font=headline, fill=COLOR_INK)
        y += 70
    else:
        # Empty-state fallback.
        draw.text((margin, y), "Trinity council",
                  font=headline, fill=COLOR_INK)
        y += 70

    # ── Body: agreed_claims + disagreed_claim ─────────────────────
    body_width = CARD_WIDTH - 2 * margin
    body_end = CARD_HEIGHT - margin - 100  # leave room for CTA + footer

    if data.agreed_claims:
        draw.text((margin, y), "AGREED",
                  font=section_label, fill=COLOR_ACCENT)
        y += 24
        # Up to 2 agreed claims, each wrapped to body_width
        for claim in data.agreed_claims[:2]:
            if y > body_end - 60:
                break
            lines = _wrap(f"• {claim}", claim_body, body_width, draw)
            for line in lines[:2]:  # cap each claim at 2 visual lines
                draw.text((margin, y), line, font=claim_body, fill=COLOR_INK)
                y += 28
            y += 6
        y += 8

    if data.disagreed_claim and y < body_end - 60:
        draw.text((margin, y), "DISAGREED — WHY IT MATTERS",
                  font=section_label, fill=COLOR_DISAGREE)
        y += 24
        # Render claim + why_matters as one wrapped block
        composite = data.disagreed_claim
        if data.disagreed_why:
            composite = f"{data.disagreed_claim} — {data.disagreed_why}"
        lines = _wrap(composite, claim_body, body_width, draw)
        for line in lines[:3]:  # cap at 3 visual lines
            if y > body_end - 28:
                break
            draw.text((margin, y), line, font=claim_body, fill=COLOR_INK)
            y += 28

    # ── CTA block ─────────────────────────────────────────────────
    cta_block_top = CARD_HEIGHT - margin - 90
    draw.text((margin, cta_block_top), CTA_HEADLINE,
              font=cta_label, fill=COLOR_ACCENT)
    draw.text((margin, cta_block_top + 28), CTA_LANDING_URL,
              font=cta_url, fill=COLOR_INK)

    # ── Footer tagline ────────────────────────────────────────────
    bbox = draw.textbbox((0, 0), FOOTER_TAGLINE, font=footer)
    fw = bbox[2] - bbox[0]
    draw.text(
        (CARD_WIDTH - margin - fw, CARD_HEIGHT - margin - 18),
        FOOTER_TAGLINE,
        font=footer,
        fill=COLOR_MUTED,
    )

    return save_png(img)
