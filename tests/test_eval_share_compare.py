"""eval-share --compare: cross-provider leaderboard PNG.

Pins the wedge artifact for #116. Single-provider eval-share already
exists (tests/test_eval_share.py); this covers the comparison-card
shape — the actual tweet-object the user produces from their corpus.
"""
from __future__ import annotations

import json
from argparse import Namespace
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
    aggregate: float | None,
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


def _share_args(tmp_path: Path, *, eval_id: str | None = None, by_axis: bool = False) -> Namespace:
    return Namespace(
        target=None,
        eval_id=eval_id,
        out=str(tmp_path / "compare.png"),
        open_after=False,
        compare=True,
        by_axis=by_axis,
    )


class TestEvalShareCompareEmptyState:
    def test_no_runs_exits_nonzero(self, home, tmp_path, capsys):
        from trinity_local.commands.eval import handle_eval_share
        with pytest.raises(SystemExit) as exc:
            handle_eval_share(_share_args(tmp_path))
        assert exc.value.code == 1
        out = capsys.readouterr().out
        assert "No eval results found" in out

    def test_unknown_eval_id_filter_surfaces(self, home, tmp_path, capsys):
        from trinity_local.commands.eval import handle_eval_share
        _write_run(home, eval_id="set_a", target="claude", aggregate=0.8)
        with pytest.raises(SystemExit) as exc:
            handle_eval_share(_share_args(tmp_path, eval_id="set_DOES_NOT_EXIST"))
        assert exc.value.code == 1
        out = capsys.readouterr().out
        assert "set_DOES_NOT_EXIST" in out


class TestEvalShareCompareWritesPng:
    def test_three_provider_card_writes_valid_png(self, home, tmp_path, capsys):
        from trinity_local.commands.eval import handle_eval_share
        _write_run(home, eval_id="set_a", target="claude",      aggregate=0.78)
        _write_run(home, eval_id="set_a", target="codex",       aggregate=0.76)
        _write_run(home, eval_id="set_a", target="antigravity", aggregate=0.61)
        handle_eval_share(_share_args(tmp_path))
        out = capsys.readouterr().out
        summary = json.loads(out)
        assert summary["mode"] == "compare"
        assert summary["bytes"] > 0
        # PNG magic header
        png = Path(summary["path"]).read_bytes()
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        # Leaderboard rows preserved in summary in rank order
        targets = [r["target"] for r in summary["rows"]]
        assert targets == ["claude", "codex", "antigravity"]

    def test_summary_carries_judge_per_row(self, home, tmp_path, capsys):
        from trinity_local.commands.eval import handle_eval_share
        _write_run(home, eval_id="set_a", target="claude", aggregate=0.8, judge="codex")
        _write_run(home, eval_id="set_a", target="codex",  aggregate=0.7, judge="claude")
        handle_eval_share(_share_args(tmp_path))
        summary = json.loads(capsys.readouterr().out)
        judges = {r["target"]: r["judge"] for r in summary["rows"]}
        assert judges == {"claude": "codex", "codex": "claude"}

    def test_mixed_eval_sets_flag_set_when_unscoped(self, home, tmp_path, capsys):
        from trinity_local.commands.eval import handle_eval_share
        _write_run(home, eval_id="set_a", target="claude", aggregate=0.8)
        _write_run(home, eval_id="set_b", target="codex",  aggregate=0.7)
        handle_eval_share(_share_args(tmp_path))
        summary = json.loads(capsys.readouterr().out)
        assert summary["mixed_eval_sets"] is True
        # eval_id should be None on the summary (multi-set, no filter)
        assert summary["eval_id"] is None

    def test_eval_id_scope_filters_and_sets_eval_id_on_summary(self, home, tmp_path, capsys):
        from trinity_local.commands.eval import handle_eval_share
        _write_run(home, eval_id="set_a", target="claude", aggregate=0.8)
        _write_run(home, eval_id="set_b", target="codex",  aggregate=0.7)
        handle_eval_share(_share_args(tmp_path, eval_id="set_a"))
        summary = json.loads(capsys.readouterr().out)
        assert summary["mixed_eval_sets"] is False
        assert summary["eval_id"] == "set_a"
        assert [r["target"] for r in summary["rows"]] == ["claude"]


class TestEvalShareCompareByAxis:
    """--by-axis mode: the per-axis matrix PNG (the wedge artifact for
    'X is best at this kind of question')."""

    def test_writes_valid_matrix_png_and_per_axis_leader_summary(self, home, tmp_path, capsys):
        from trinity_local.commands.eval import handle_eval_share
        _write_run(home, eval_id="set_a", target="claude", aggregate=0.79,
                   by_axis={"REFRAME": 0.81, "COMPRESSION": 0.48})
        _write_run(home, eval_id="set_a", target="codex", aggregate=0.76,
                   by_axis={"REFRAME": 0.74, "COMPRESSION": 0.77})
        handle_eval_share(_share_args(tmp_path, by_axis=True))
        summary = json.loads(capsys.readouterr().out)
        # Mode flag carries the variant so scripted callers can branch.
        assert summary["mode"] == "compare-by-axis"
        # PNG written + valid magic header
        png = Path(summary["path"]).read_bytes()
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        # Per-axis leader names the right winner per axis
        assert "per_axis_leader" in summary
        assert summary["per_axis_leader"]["REFRAME"]["target"] == "claude"
        assert summary["per_axis_leader"]["COMPRESSION"]["target"] == "codex"

    def test_default_filename_distinguishes_aggregate_vs_matrix(self, home, tmp_path, capsys):
        """When --out is omitted, the default path picks a distinct
        filename so the two card variants don't overwrite each other."""
        from trinity_local.commands.eval import handle_eval_share
        _write_run(home, eval_id="set_a", target="claude", aggregate=0.79,
                   by_axis={"REFRAME": 0.81})
        # Bypass _share_args' tmp out so the default kicks in
        args = Namespace(
            target=None, eval_id=None, out=None,
            open_after=False, compare=True, by_axis=True,
        )
        from trinity_local.commands.eval import handle_eval_share
        handle_eval_share(args)
        summary = json.loads(capsys.readouterr().out)
        assert summary["path"].endswith("eval_compare_matrix_card.png")

    def test_summary_carries_by_axis_per_row_in_matrix_mode(self, home, tmp_path, capsys):
        """JSON summary in --by-axis mode should expose the per-axis
        scores per row so scripted callers can render a tweet-string."""
        from trinity_local.commands.eval import handle_eval_share
        _write_run(home, eval_id="set_a", target="claude", aggregate=0.79,
                   by_axis={"REFRAME": 0.81, "COMPRESSION": 0.48})
        handle_eval_share(_share_args(tmp_path, by_axis=True))
        summary = json.loads(capsys.readouterr().out)
        assert "by_axis" in summary["rows"][0]
        assert summary["rows"][0]["by_axis"]["REFRAME"] == 0.81

    def test_by_axis_without_compare_exits_2(self, home, tmp_path, capsys):
        """Mirrors eval-show: --by-axis only makes sense inside
        --compare. Lone --by-axis exits with hint, not crash."""
        from trinity_local.commands.eval import handle_eval_share
        _write_run(home, eval_id="set_a", target="claude", aggregate=0.8)
        args = Namespace(
            target=None, eval_id=None, out=str(tmp_path / "x.png"),
            open_after=False, compare=False, by_axis=True,
        )
        with pytest.raises(SystemExit) as exc:
            handle_eval_share(args)
        assert exc.value.code == 2
        out = capsys.readouterr().out
        assert "--by-axis only applies to --compare" in out


class TestRenderCompareCardPure:
    """Direct renderer tests — no I/O, no filesystem."""

    def test_renders_with_two_providers(self):
        from trinity_local.eval_card import CompareCardData, render_compare_card
        data = CompareCardData(
            rows=[
                {"target": "claude", "model": None, "aggregate_score": 0.85,
                 "items_completed": 20, "judge": "codex"},
                {"target": "codex", "model": None, "aggregate_score": 0.72,
                 "items_completed": 20, "judge": "claude"},
            ],
            eval_id="set_a",
            mixed_eval_sets=False,
        )
        png = render_compare_card(data)
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        # 1200x630 canvas — at least a few KB even with sparse content
        assert len(png) > 5000

    def test_empty_rows_falls_back_to_cta_card(self):
        """Defensive branch — CLI exits before this, but the renderer
        shouldn't crash on an empty leaderboard."""
        from trinity_local.eval_card import CompareCardData, render_compare_card
        png = render_compare_card(CompareCardData(rows=[]))
        assert png[:8] == b"\x89PNG\r\n\x1a\n"

    def test_matrix_renderer_handles_three_providers_with_axes(self):
        """Smoke the matrix renderer directly so a future change to the
        layout that breaks it surfaces here rather than only inside
        the share-handler tests."""
        from trinity_local.eval_card import CompareCardData, render_compare_matrix_card
        data = CompareCardData(
            rows=[
                {"target": "claude", "model": None, "aggregate_score": 0.79,
                 "items_completed": 45, "judge": "codex",
                 "by_axis": {"REFRAME": 0.81, "COMPRESSION": 0.48}},
                {"target": "codex", "model": None, "aggregate_score": 0.76,
                 "items_completed": 45, "judge": "claude",
                 "by_axis": {"REFRAME": 0.74, "COMPRESSION": 0.77}},
                {"target": "antigravity", "model": None, "aggregate_score": 0.61,
                 "items_completed": 42, "judge": "claude",
                 "by_axis": {"REFRAME": 0.61, "COMPRESSION": 0.08}},
            ],
            eval_id="set_a",
            mixed_eval_sets=False,
        )
        png = render_compare_matrix_card(data)
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        # The matrix card has chips + bars + scores, should be more
        # substantial than the empty-state fallback.
        assert len(png) > 8000

    def test_matrix_renderer_empty_state_falls_through(self):
        """Defensive: rows present but no by_axis breakdown → empty-state
        hint card, no crash."""
        from trinity_local.eval_card import CompareCardData, render_compare_matrix_card
        png = render_compare_matrix_card(CompareCardData(
            rows=[{"target": "claude", "model": None, "aggregate_score": 0.79,
                   "items_completed": 45, "judge": "codex", "by_axis": {}}],
        ))
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
