"""launchpad per_axis_leader: surface the wedge chips inline.

When ≥2 providers have eval-run results AND the per-axis breakdown is
populated, the launchpad's eval-summary card should render leader
chips above the leaderboard table — "COMPRESSION: codex 0.77 |
REFRAME: claude 0.81". The CLI surfaces this via `eval-show
--compare --by-axis`; the launchpad mirrors so the wedge claim ("X is
best at this kind of question") is visible without leaving the page.

Pins both the data computation (launchpad_data._compute_eval_summary
returns per_axis_leader) and the template rendering (chips appear
in HTML when the data is present).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def home(patch_trinity_home: Path) -> Path:
    return patch_trinity_home


def _write_run(
    home: Path,
    *,
    eval_id: str,
    target: str,
    aggregate: float,
    items_completed: int = 45,
    judge: str = "claude",
    ts: str = "20260101T000000",
    by_axis: dict | None = None,
) -> Path:
    from trinity_local.evals.builder import results_dir
    results_dir().mkdir(parents=True, exist_ok=True)
    path = results_dir() / f"eval_{eval_id}__model_{target}__{ts}.json"
    path.write_text(json.dumps({
        "eval_id": eval_id,
        "target_provider": target,
        "target_model": f"{target}-model",
        "started_at": "2026-01-01T00:00:00+00:00",
        "completed_at": "2026-01-01T00:10:00+00:00",
        "items_total": items_completed,
        "items_completed": items_completed,
        "items_failed": 0,
        "items": [{"judge_provider": judge, "score": 0.5, "rejection_type": "REFRAME"}],
        "aggregate_score": aggregate,
        "by_rejection_type": {
            axis: {"mean_score": score, "count": 1, "min_score": score, "max_score": score}
            for axis, score in (by_axis or {}).items()
        },
    }))
    return path


class TestPerAxisLeaderData:
    def test_compute_eval_summary_emits_per_axis_leader(self, home):
        from trinity_local.launchpad_data import _eval_summary
        _write_run(home, eval_id="set_a", target="claude", aggregate=0.79,
                   by_axis={"REFRAME": 0.81, "COMPRESSION": 0.48})
        _write_run(home, eval_id="set_a", target="codex", aggregate=0.76,
                   by_axis={"REFRAME": 0.74, "COMPRESSION": 0.77})
        summary = _eval_summary()
        assert "per_axis_leader" in summary
        chips = {c["axis"]: c for c in summary["per_axis_leader"]}
        assert chips["REFRAME"]["target"] == "claude"
        assert chips["COMPRESSION"]["target"] == "codex"
        assert chips["COMPRESSION"]["score"] == 0.77

    def test_per_axis_leader_empty_when_no_by_rejection_type(self, home):
        """Older eval runs lacking by_rejection_type → empty chip list,
        not a crash. Template's v-if hides the chip row entirely."""
        from trinity_local.launchpad_data import _eval_summary
        _write_run(home, eval_id="set_a", target="claude", aggregate=0.79)
        summary = _eval_summary()
        assert summary["per_axis_leader"] == []

    def test_comparison_rows_carry_by_axis_dict(self, home):
        """The matrix-card path on the launchpad needs per-row by_axis
        scores; pin them so a future refactor doesn't drop them."""
        from trinity_local.launchpad_data import _eval_summary
        _write_run(home, eval_id="set_a", target="claude", aggregate=0.79,
                   by_axis={"REFRAME": 0.81})
        summary = _eval_summary()
        # Single-row comparison still emits the by_axis field
        assert "by_axis" in summary["comparison"][0]
        assert summary["comparison"][0]["by_axis"]["REFRAME"] == 0.81


class TestLaunchpadChipsRender:
    def test_chips_render_when_per_axis_leader_populated(self, home):
        from trinity_local.launchpad_template import render_launchpad_html
        from trinity_local.launchpad_data import _eval_summary
        _write_run(home, eval_id="set_a", target="claude", aggregate=0.79,
                   by_axis={"REFRAME": 0.81, "COMPRESSION": 0.48})
        _write_run(home, eval_id="set_a", target="codex", aggregate=0.76,
                   by_axis={"REFRAME": 0.74, "COMPRESSION": 0.77})
        summary = _eval_summary()
        html = render_launchpad_html(
            page_data={"evalSummary": summary},
            recent_cards="",
        )
        # Vue v-for over per_axis_leader; template binding visible in
        # rendered HTML even before runtime.
        assert "per_axis_leader" in html
        # Format string for chip text — matches "<axis>: <target> <score>"
        assert "chip.axis" in html
        assert "chip.target" in html

    def test_meta_line_advertises_by_axis_variants(self):
        from trinity_local.launchpad_template import render_launchpad_html
        html = render_launchpad_html(
            page_data={"evalSummary": {"has_results": True}},
            recent_cards="",
        )
        # CLI mirror + PNG export both discoverable from launchpad copy
        assert "--compare --by-axis" in html
        assert "eval-share --compare --by-axis" in html
