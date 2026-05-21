"""eval-share PNG export — render an eval run result as a 1200×630 OG card.

Matches the visual language of `me_card.py` (same palette, fonts, margin
system, footer convention). The hero is the aggregate score against the
user's lens; per-axis bars show where the target model wins and loses on
the user's specific rejection signal.

Single function: ``render_eval_card(card_data) -> bytes``. CLI writes the
bytes to disk; future launchpad share button would download them.

The card is the artifact the user's pitch produces — *"I ran my evals on
Antigravity; here's where it landed; here's how you can do it too."* The
recipient gets:

1. The headline ("Claude scored 0.661 on YOUR kind of question")
2. Per-axis breakdown (REFRAME / COMPRESSION / REDIRECT / SHARPENING)
3. A clear install CTA below the chart
4. A github.com URL footer for the repo-public surface
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .share_card_base import (
    CARD_WIDTH,
    CARD_HEIGHT,
    COLOR_INK,
    COLOR_MUTED,
    COLOR_ACCENT,
    LANDING_URL as CTA_LANDING_URL,
    FOOTER_TAGLINE,
    load_font as _load_font,
    blank_canvas,
    save_png,
)

# Card-specific accents — solid sage for the score bar, transparent
# sage for the empty track behind it.
COLOR_BAR_FILL = (37, 88, 71)
COLOR_BAR_TRACK = (37, 88, 71, 36)


@dataclass
class EvalCardData:
    """Card-shaped view of an eval run result. The card shows the
    aggregate + up to 4 per-axis bars + the install CTA."""
    target_provider: str
    target_model: str | None = None
    aggregate_score: float | None = None
    items_total: int = 0
    items_completed: int = 0
    by_axis: list[tuple[str, float, int]] = field(default_factory=list)
    # (axis_name, mean_score, item_count) — sorted display order is
    # alphabetical (REFRAME / COMPRESSION / REDIRECT / SHARPENING) for
    # stability across runs.

    def to_dict(self) -> dict[str, Any]:
        return {
            "target_provider": self.target_provider,
            "target_model": self.target_model,
            "aggregate_score": self.aggregate_score,
            "items_total": self.items_total,
            "items_completed": self.items_completed,
            "by_axis": list(self.by_axis),
        }


def collect_card_data_from_result(result) -> EvalCardData:
    """Build EvalCardData from a RunResult (the dataclass loaded from
    ~/.trinity/evals/results/*.json by evals.runner.load_run_result).

    Pure-data transformation — no disk I/O, no scoring. The caller passes
    the loaded result; this just shapes it for the card renderer.
    """
    by_axis: list[tuple[str, float, int]] = []
    if result.by_rejection_type:
        for axis_name in sorted(result.by_rejection_type.keys()):
            stats = result.by_rejection_type[axis_name]
            by_axis.append((axis_name, float(stats["mean_score"]), int(stats["count"])))

    return EvalCardData(
        target_provider=result.target_provider,
        target_model=result.target_model,
        aggregate_score=result.aggregate_score,
        items_total=result.items_total,
        items_completed=result.items_completed,
        by_axis=by_axis,
    )


def _provider_display_name(provider: str, model: str | None) -> str:
    """Friendly display name for the headline.

    `provider` is the slug Trinity uses internally (claude / codex /
    antigravity); `model` is the specific version (claude-opus-4-7,
    gpt-5-5, gemini-3-1-pro-preview). The headline uses the friendly
    provider capitalization; the subhead carries the exact model id.
    """
    friendly = {"claude": "Claude", "codex": "GPT", "antigravity": "Antigravity"}
    return friendly.get(provider, provider.capitalize())


# Public landing URL — single source of truth here. Points at the
# GitHub Pages site (matches docs/REPO_PUBLIC_RUNBOOK + docs/CNAME),
# which has the full curl|sh install one-liner on its hero page. Doing
# it this way (Pages URL on the card, install one-liner on the Pages
# landing) keeps the PNG legible at 1200×630 — the full raw.github URL
# is too long for the card without wrapping.
#
# When the Pages URL moves, sweep this string AND update the same
# reference in launch.md / REPO_PUBLIC_RUNBOOK.md / docs/CNAME.
CTA_HEADLINE = "Run this eval against your own taste:"
# CTA_LANDING_URL / FOOTER_TAGLINE imported from share_card_base.


def render_eval_card(data: EvalCardData) -> bytes:
    """Render the 1200×630 PNG. Returns bytes; caller writes to disk.

    Empty / missing-score states are handled by falling through to a
    minimal "run trinity-local eval-run to produce yours" message so the
    card always renders something coherent.
    """
    img, draw = blank_canvas()
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img, "RGBA")

    eyebrow = _load_font("bold", 22)
    headline = _load_font("serif", 56)
    sub = _load_font("regular", 26)
    axis_label = _load_font("bold", 20)
    axis_score = _load_font("mono", 22)
    cta_label = _load_font("bold", 20)
    cta_cmd = _load_font("mono", 22)
    footer = _load_font("regular", 18)

    margin = 60
    y = margin

    # Eyebrow: "TRINITY · YOUR PERSONAL BENCHMARK"
    draw.text((margin, y), "TRINITY · YOUR PERSONAL BENCHMARK",
              font=eyebrow, fill=COLOR_ACCENT)
    y += 50

    # Empty-state fallback — no aggregate means no card-worthy data.
    if data.aggregate_score is None or not data.by_axis:
        draw.text((margin, y), "Run trinity-local eval-run",
                  font=headline, fill=COLOR_INK)
        y += 80
        draw.text((margin, y),
                  "to score any model against your kind of question.",
                  font=sub, fill=COLOR_MUTED)
    else:
        # Headline: "Claude scored 0.661"
        provider_name = _provider_display_name(data.target_provider, data.target_model)
        score_str = f"{data.aggregate_score:.2f}"  # 2 dp is the tweet-shape
        draw.text((margin, y),
                  f"{provider_name} scored {score_str}",
                  font=headline, fill=COLOR_INK)
        y += 76

        # Subhead: "on YOUR kind of question · 20 prompts, 4 axes"
        axis_count = len(data.by_axis)
        subhead = (
            f"on YOUR kind of question · "
            f"{data.items_completed} prompts, {axis_count} axes"
        )
        draw.text((margin, y), subhead, font=sub, fill=COLOR_MUTED)
        y += 50

        # Per-axis bars — left-anchored label, right-anchored score.
        # Bar track + fill use the sage palette; bar width scales with
        # the mean_score (0..1). 4 axes is the canonical case but we
        # render whatever the result has.
        bar_track_x = margin + 240
        bar_track_width = CARD_WIDTH - bar_track_x - margin - 80
        bar_height = 14
        row_height = 36

        for axis_name, mean_score, _count in data.by_axis:
            # Label (left-anchored)
            draw.text((margin, y), axis_name, font=axis_label, fill=COLOR_MUTED)

            # Bar track
            track_y_top = y + 4
            track_y_bot = track_y_top + bar_height
            draw.rounded_rectangle(
                [bar_track_x, track_y_top,
                 bar_track_x + bar_track_width, track_y_bot],
                radius=bar_height // 2,
                fill=COLOR_BAR_TRACK,
            )

            # Bar fill — width clamped to [0, 1] of the track
            fill_pct = max(0.0, min(1.0, mean_score))
            fill_width = int(bar_track_width * fill_pct)
            if fill_width > bar_height:
                draw.rounded_rectangle(
                    [bar_track_x, track_y_top,
                     bar_track_x + fill_width, track_y_bot],
                    radius=bar_height // 2,
                    fill=COLOR_BAR_FILL,
                )

            # Score (right-anchored at fixed column for alignment)
            score_text = f"{mean_score:.2f}"
            draw.text(
                (bar_track_x + bar_track_width + 16, y - 2),
                score_text,
                font=axis_score,
                fill=COLOR_INK,
            )

            y += row_height

        y += 8

    # ── CTA block, anchored above the footer ──────────────────────
    #
    # "Run this eval against your own taste:" on top, the GH Pages
    # landing URL below it. Two lines, sitting in the gap between the
    # bars and the bottom-right footer. The Pages page hosts the full
    # install one-liner so we don't have to fit it on the card.
    cta_block_top = CARD_HEIGHT - margin - 90
    draw.text((margin, cta_block_top), CTA_HEADLINE,
              font=cta_label, fill=COLOR_ACCENT)
    draw.text((margin, cta_block_top + 28), CTA_LANDING_URL,
              font=cta_cmd, fill=COLOR_INK)

    # ── Footer tagline, bottom-right corner ───────────────────────
    bbox = draw.textbbox((0, 0), FOOTER_TAGLINE, font=footer)
    fw = bbox[2] - bbox[0]
    draw.text(
        (CARD_WIDTH - margin - fw, CARD_HEIGHT - margin - 18),
        FOOTER_TAGLINE,
        font=footer,
        fill=COLOR_MUTED,
    )

    return save_png(img)
