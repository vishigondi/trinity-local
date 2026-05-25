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
        "by_rejection_type": {},
    }))
    return path


def _share_args(tmp_path: Path, *, eval_id: str | None = None) -> Namespace:
    return Namespace(
        target=None,
        eval_id=eval_id,
        out=str(tmp_path / "compare.png"),
        open_after=False,
        compare=True,
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
