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


@dataclass
class CompareCardData:
    """Cross-provider leaderboard view. Each row is the most-recent eval
    run for one target_provider against the user's rejection signal.
    The card surfaces the ranked list (top 5 if more), the leader's
    margin over the runner-up, and the mixed-eval-set warning when
    rows aren't directly comparable.
    """
    rows: list[dict]  # [{target, model, aggregate_score, items_completed, judge, ...}]
    eval_id: str | None = None
    mixed_eval_sets: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "rows": list(self.rows),
            "eval_id": self.eval_id,
            "mixed_eval_sets": self.mixed_eval_sets,
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
    axis_hint = _load_font("regular", 14)  # one-liner per axis below the label
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
        row_height = 48  # bumped from 36 to make room for the axis-hint line

        # Lazy import — keeps eval_card.py importable without the runtime
        # scorer module on render-only paths.
        from .evals.scorer import AXIS_ONELINER

        for axis_name, mean_score, _count in data.by_axis:
            # Label (left-anchored) + small hint line below
            draw.text((margin, y), axis_name, font=axis_label, fill=COLOR_MUTED)
            hint = AXIS_ONELINER.get(axis_name, "")
            if hint:
                draw.text((margin, y + 22), hint, font=axis_hint, fill=COLOR_MUTED)

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


def render_compare_matrix_card(data: CompareCardData) -> bytes:
    """Per-axis × provider matrix card. The wedge artifact for the
    'best at this kind of question' claim — each provider gets a row
    with one short bar per axis, and the leader chip surfaces per axis.

    Same 1200×630 canvas as the aggregate card. Different shape: the
    aggregate card has bars-per-row sized by aggregate; this card has
    bars-per-axis sized by per-axis mean. When the per-axis spread
    between providers is large (live data: COMPRESSION codex 0.77 vs
    antigravity 0.08, a 0.7-spread), the matrix bars make it visible
    in a way the aggregate flattens.
    """
    img, _ = blank_canvas()
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img, "RGBA")

    eyebrow = _load_font("bold", 22)
    headline = _load_font("serif", 38)
    sub = _load_font("regular", 18)
    leader_chip_font = _load_font("bold", 16)
    target_font = _load_font("bold", 20)
    axis_label_font = _load_font("regular", 11)
    score_font = _load_font("mono", 14)
    warn_font = _load_font("regular", 14)
    cta_label = _load_font("bold", 20)
    cta_cmd = _load_font("mono", 22)
    footer = _load_font("regular", 18)

    margin = 60
    y = margin

    draw.text((margin, y), "TRINITY · PER-AXIS LEADERBOARD",
              font=eyebrow, fill=COLOR_ACCENT)
    y += 46

    # Collect axis set + per-axis leaders (sorted for stable order)
    axes_seen: set[str] = set()
    for row in data.rows:
        axes_seen.update((row.get("by_axis") or {}).keys())
    axes_ordered = sorted(axes_seen)

    if not data.rows or not axes_ordered:
        draw.text((margin, y), "Per-axis matrix needs ≥1 provider",
                  font=headline, fill=COLOR_INK)
        draw.text((margin, y + 60),
                  "with by_rejection_type breakdown. Re-run `trinity-local eval-run`.",
                  font=sub, fill=COLOR_MUTED)
    else:
        # Headline: the wedge. "Different models for different questions."
        draw.text((margin, y), "Different models for different questions.",
                  font=headline, fill=COLOR_INK)
        y += 50

        if data.mixed_eval_sets:
            draw.text(
                (margin, y),
                "⚠ rows span multiple eval sets — pass --eval-id to scope",
                font=warn_font, fill=COLOR_MUTED,
            )
            y += 22

        # Per-axis leader chips above the matrix. The tweet-line of
        # the card: "COMPRESSION → codex (0.77)  REFRAME → claude (0.81) ..."
        #
        # SUPPRESSED when mixed_eval_sets is True — same fix as the
        # launchpad's per_axis_leader (commit 83b9e99). Computing a
        # leader-per-axis across DIFFERENT eval sets is exactly the
        # claim the warning at the top of the card forbids. The
        # matrix bars stay (the per-row data is still meaningful as
        # each-provider's-own-score), but the leader chips that
        # synthesize a head-to-head are suppressed.
        if not data.mixed_eval_sets:
            chip_x = margin
            chip_y = y
            for axis in axes_ordered:
                scored = [(r["target"], r["by_axis"][axis]) for r in data.rows if axis in (r.get("by_axis") or {})]
                if not scored:
                    continue
                leader_target, leader_score = max(scored, key=lambda kv: kv[1])
                leader_name = _provider_display_name(leader_target, None)
                # No `→` — the bundled fonts lack the glyph and render
                # missing-glyph boxes in the chip. ASCII separator is safer.
                chip_text = f"{axis}: {leader_name} {leader_score:.2f}"
                bbox = draw.textbbox((0, 0), chip_text, font=leader_chip_font)
                chip_w = bbox[2] - bbox[0] + 16
                chip_h = bbox[3] - bbox[1] + 8
                if chip_x + chip_w > CARD_WIDTH - margin:
                    chip_x = margin
                    chip_y += chip_h + 8
                draw.rounded_rectangle(
                    [chip_x, chip_y, chip_x + chip_w, chip_y + chip_h],
                    radius=4,
                    fill=(45, 138, 62, 18),
                )
                draw.text((chip_x + 8, chip_y + 4), chip_text,
                          font=leader_chip_font, fill=COLOR_ACCENT)
                chip_x += chip_w + 6
            y = chip_y + 40
        else:
            # No chips → leave a smaller gap above the matrix, matching
            # the visual rhythm of the agreed-sets variant.
            y += 18

        # Matrix: target-name column + N axis-bar columns. Card width
        # gives ~280px for target column + remainder split N ways.
        target_col_width = 130
        axes_area_x = margin + target_col_width
        axes_area_w = CARD_WIDTH - margin - axes_area_x
        axis_col_w = axes_area_w // len(axes_ordered)
        bar_height = 8
        row_height = 50

        # Axis label header row
        for i, axis in enumerate(axes_ordered):
            col_center = axes_area_x + axis_col_w * i + axis_col_w // 2
            label = axis[:11]
            bbox = draw.textbbox((0, 0), label, font=axis_label_font)
            lw = bbox[2] - bbox[0]
            draw.text((col_center - lw // 2, y), label,
                      font=axis_label_font, fill=COLOR_MUTED)
        y += 18

        # Rows: one per provider
        max_rows = 4
        rows_to_render = data.rows[:max_rows]
        for row in rows_to_render:
            # Target name
            target_name = _provider_display_name(row["target"], row.get("model"))
            draw.text((margin, y + 4), target_name,
                      font=target_font, fill=COLOR_INK)
            # Per-axis bars + scores
            row_axes = row.get("by_axis") or {}
            bar_pad = 10  # horizontal padding inside each axis column
            for i, axis in enumerate(axes_ordered):
                col_x = axes_area_x + axis_col_w * i + bar_pad
                col_bar_w = axis_col_w - bar_pad * 2
                track_top = y + 8
                track_bot = track_top + bar_height
                draw.rounded_rectangle(
                    [col_x, track_top, col_x + col_bar_w, track_bot],
                    radius=bar_height // 2,
                    fill=COLOR_BAR_TRACK,
                )
                if axis in row_axes:
                    val = row_axes[axis]
                    fill_pct = max(0.0, min(1.0, val))
                    fill_w = int(col_bar_w * fill_pct)
                    if fill_w > bar_height:
                        draw.rounded_rectangle(
                            [col_x, track_top, col_x + fill_w, track_bot],
                            radius=bar_height // 2,
                            fill=COLOR_BAR_FILL,
                        )
                    # Score below the bar (small mono, center-aligned in column)
                    score_text = f"{val:.2f}"
                    bbox = draw.textbbox((0, 0), score_text, font=score_font)
                    sw = bbox[2] - bbox[0]
                    draw.text(
                        (col_x + (col_bar_w - sw) // 2, track_bot + 4),
                        score_text,
                        font=score_font,
                        fill=COLOR_INK,
                    )
                else:
                    # Missing-axis cell — small dash, center-aligned
                    bbox = draw.textbbox((0, 0), "—", font=score_font)
                    sw = bbox[2] - bbox[0]
                    draw.text(
                        (col_x + (col_bar_w - sw) // 2, track_bot + 4),
                        "—",
                        font=score_font,
                        fill=COLOR_MUTED,
                    )
            y += row_height

        if len(data.rows) > max_rows:
            draw.text(
                (margin, y + 4),
                f"+ {len(data.rows) - max_rows} more — see `eval-show --compare --by-axis`",
                font=axis_label_font, fill=COLOR_MUTED,
            )

    # CTA + footer (same as render_compare_card)
    cta_block_top = CARD_HEIGHT - margin - 90
    draw.text((margin, cta_block_top),
              "Run this benchmark against your own taste:",
              font=cta_label, fill=COLOR_ACCENT)
    draw.text((margin, cta_block_top + 28), CTA_LANDING_URL,
              font=cta_cmd, fill=COLOR_INK)

    bbox = draw.textbbox((0, 0), FOOTER_TAGLINE, font=footer)
    fw = bbox[2] - bbox[0]
    draw.text(
        (CARD_WIDTH - margin - fw, CARD_HEIGHT - margin - 18),
        FOOTER_TAGLINE,
        font=footer,
        fill=COLOR_MUTED,
    )

    return save_png(img)


def render_compare_card(data: CompareCardData) -> bytes:
    """Render the cross-provider leaderboard as a 1200×630 PNG.

    Each row = one target_provider's most-recent eval run against the
    user's rejection signal. The card's wedge is the COMPARISON —
    "I scored Claude, Codex, and Gemini on my taste; Claude won."

    Empty-state fallback mirrors render_eval_card so the file always
    contains something coherent; callers exit nonzero before reaching
    here when rows is empty, so this branch is defensive only.
    """
    img, _ = blank_canvas()
    from PIL import ImageDraw
    draw = ImageDraw.Draw(img, "RGBA")

    eyebrow = _load_font("bold", 22)
    headline = _load_font("serif", 48)
    sub = _load_font("regular", 22)
    rank_font = _load_font("mono", 22)
    target_font = _load_font("bold", 24)
    score_font = _load_font("mono", 26)
    judge_font = _load_font("regular", 14)
    warn_font = _load_font("regular", 16)
    cta_label = _load_font("bold", 20)
    cta_cmd = _load_font("mono", 22)
    footer = _load_font("regular", 18)

    margin = 60
    y = margin

    draw.text((margin, y), "TRINITY · CROSS-PROVIDER LEADERBOARD",
              font=eyebrow, fill=COLOR_ACCENT)
    y += 50

    if not data.rows:
        draw.text((margin, y), "Run trinity-local eval-run",
                  font=headline, fill=COLOR_INK)
        draw.text((margin, y + 70),
                  "against ≥2 providers to populate this card.",
                  font=sub, fill=COLOR_MUTED)
    else:
        # Headline: name the leader. "Claude leads on YOUR taste"
        leader = data.rows[0]
        leader_name = _provider_display_name(leader["target"], leader.get("model"))
        leader_agg = leader.get("aggregate_score")
        if leader_agg is not None:
            headline_text = f"{leader_name} leads at {leader_agg:.2f}"
        else:
            headline_text = f"{leader_name} ranked first"
        draw.text((margin, y), headline_text, font=headline, fill=COLOR_INK)
        y += 64

        if len(data.rows) >= 2:
            runner = data.rows[1]
            runner_agg = runner.get("aggregate_score")
            if leader_agg is not None and runner_agg is not None:
                margin_text = (
                    f"on YOUR kind of question · "
                    f"{leader_agg - runner_agg:+.3f} ahead of "
                    f"{_provider_display_name(runner['target'], runner.get('model'))}"
                )
            else:
                margin_text = "on YOUR kind of question"
        else:
            margin_text = "on YOUR kind of question"
        draw.text((margin, y), margin_text, font=sub, fill=COLOR_MUTED)
        y += 42

        if data.mixed_eval_sets:
            draw.text(
                (margin, y),
                "⚠ rows span multiple eval sets — pass --eval-id to scope",
                font=warn_font, fill=COLOR_MUTED,
            )
            y += 24

        # Leaderboard rows: rank · target · bar · score · (judge)
        # Card fits ~5 rows comfortably; truncate beyond that.
        max_rows = 5
        rows_to_render = data.rows[:max_rows]
        bar_x = margin + 290
        bar_width = CARD_WIDTH - bar_x - margin - 120  # leave room for score column
        bar_height = 16
        row_height = 44

        for i, row in enumerate(rows_to_render, 1):
            # Rank
            draw.text((margin, y + 8), f"{i}.", font=rank_font, fill=COLOR_MUTED)
            # Target name (display-friendly)
            target_name = _provider_display_name(row["target"], row.get("model"))
            draw.text((margin + 36, y + 4), target_name,
                      font=target_font, fill=COLOR_INK)

            # Judge attribution under the target name — small + muted
            judge = row.get("judge")
            if judge:
                draw.text((margin + 36, y + 28),
                          f"judge: {_provider_display_name(judge, None)}",
                          font=judge_font, fill=COLOR_MUTED)

            # Bar
            agg = row.get("aggregate_score")
            track_top = y + 12
            track_bot = track_top + bar_height
            draw.rounded_rectangle(
                [bar_x, track_top, bar_x + bar_width, track_bot],
                radius=bar_height // 2,
                fill=COLOR_BAR_TRACK,
            )
            if agg is not None:
                fill_pct = max(0.0, min(1.0, agg))
                fill_width = int(bar_width * fill_pct)
                if fill_width > bar_height:
                    draw.rounded_rectangle(
                        [bar_x, track_top, bar_x + fill_width, track_bot],
                        radius=bar_height // 2,
                        fill=COLOR_BAR_FILL,
                    )

            # Score (right-anchored)
            score_str = f"{agg:.3f}" if agg is not None else "—"
            draw.text(
                (bar_x + bar_width + 18, y + 6),
                score_str,
                font=score_font,
                fill=COLOR_INK,
            )

            y += row_height

        # If we truncated, surface that the leaderboard has more.
        if len(data.rows) > max_rows:
            draw.text(
                (margin, y + 4),
                f"+ {len(data.rows) - max_rows} more — see `eval-show --compare`",
                font=judge_font, fill=COLOR_MUTED,
            )

    # CTA + footer (same convention as render_eval_card)
    cta_block_top = CARD_HEIGHT - margin - 90
    draw.text((margin, cta_block_top),
              "Run this benchmark against your own taste:",
              font=cta_label, fill=COLOR_ACCENT)
    draw.text((margin, cta_block_top + 28), CTA_LANDING_URL,
              font=cta_cmd, fill=COLOR_INK)

    bbox = draw.textbbox((0, 0), FOOTER_TAGLINE, font=footer)
    fw = bbox[2] - bbox[0]
    draw.text(
        (CARD_WIDTH - margin - fw, CARD_HEIGHT - margin - 18),
        FOOTER_TAGLINE,
        font=footer,
        fill=COLOR_MUTED,
    )

    return save_png(img)
