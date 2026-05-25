"""eval-show --compare: cross-provider leaderboard CLI parity.

Launchpad copy promises `trinity-local eval-show renders the same` as
the leaderboard. This pins the CLI behavior: --compare aggregates
across targets, sorts by aggregate_score desc, scopes by --eval-id,
warns when rows span multiple eval sets.
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
    items_completed: int = 10,
    judge: str = "claude",
    by_axis: dict | None = None,
) -> Path:
    """Drop a synthetic eval result JSON in the canonical location.

    Filename follows runner.result_path():
      eval_<eval_id>__model_<target>__<ts>.json
    """
    from trinity_local.evals.builder import results_dir
    results_dir().mkdir(parents=True, exist_ok=True)
    fname = f"eval_{eval_id}__model_{target}__20260101T000000.json"
    path = results_dir() / fname
    payload = {
        "eval_id": eval_id,
        "target_provider": target,
        "target_model": f"{target}-model",
        "started_at": "2026-01-01T00:00:00+00:00",
        "completed_at": "2026-01-01T00:10:00+00:00",
        "items_total": items_completed,
        "items_completed": items_completed,
        "items_failed": 0,
        "items": [
            {"judge_provider": judge, "score": 0.5, "rejection_type": "REFRAME"}
        ],
        "aggregate_score": aggregate,
        "by_rejection_type": {
            axis: {"mean_score": score, "count": 1, "min_score": score, "max_score": score}
            for axis, score in (by_axis or {}).items()
        },
    }
    path.write_text(json.dumps(payload))
    return path


def _compare_args(eval_id: str | None = None, by_axis: bool = False) -> Namespace:
    return Namespace(
        target=None,
        eval_id=eval_id,
        limit_samples=0,
        compare=True,
        by_axis=by_axis,
    )


class TestCompareEmptyState:
    def test_no_runs_exits_nonzero_with_hint(self, home, capsys):
        from trinity_local.commands.eval import handle_eval_show
        with pytest.raises(SystemExit) as exc:
            handle_eval_show(_compare_args())
        assert exc.value.code == 1
        out = capsys.readouterr().out
        assert "No eval results found" in out
        assert "eval-run --target" in out

    def test_filter_to_unknown_eval_id_surfaces_filter(self, home, capsys):
        from trinity_local.commands.eval import handle_eval_show
        _write_run(home, eval_id="set_a", target="claude", aggregate=0.8)
        with pytest.raises(SystemExit) as exc:
            handle_eval_show(_compare_args(eval_id="set_DOES_NOT_EXIST"))
        assert exc.value.code == 1
        out = capsys.readouterr().out
        assert "set_DOES_NOT_EXIST" in out


class TestCompareLeaderboard:
    def test_orders_by_aggregate_score_desc(self, home, capsys):
        from trinity_local.commands.eval import handle_eval_show
        _write_run(home, eval_id="set_a", target="claude", aggregate=0.78)
        _write_run(home, eval_id="set_a", target="codex", aggregate=0.76)
        _write_run(home, eval_id="set_a", target="antigravity", aggregate=0.61)
        handle_eval_show(_compare_args())
        out = capsys.readouterr().out
        # The ordering check: claude before codex before antigravity.
        i_claude = out.find("claude")
        i_codex = out.find("codex")
        i_antigravity = out.find("antigravity")
        assert 0 <= i_claude < i_codex < i_antigravity, (
            f"Leaderboard order wrong:\n{out}"
        )
        # The leader-margin summary surfaces below the table.
        assert "claude leads codex" in out
        assert "+0.020" in out  # 0.78 - 0.76

    def test_judge_provider_surfaces_in_table(self, home, capsys):
        from trinity_local.commands.eval import handle_eval_show
        _write_run(home, eval_id="set_a", target="claude", aggregate=0.8, judge="codex")
        _write_run(home, eval_id="set_a", target="codex", aggregate=0.7, judge="claude")
        handle_eval_show(_compare_args())
        out = capsys.readouterr().out
        # Both judges visible — a model never grading itself is the
        # core claim and worth surfacing.
        assert "codex" in out
        assert "claude" in out

    def test_mixed_eval_sets_warning_fires_when_unscoped(self, home, capsys):
        from trinity_local.commands.eval import handle_eval_show
        _write_run(home, eval_id="set_a", target="claude", aggregate=0.8)
        _write_run(home, eval_id="set_b", target="codex", aggregate=0.7)
        handle_eval_show(_compare_args())
        out = capsys.readouterr().out
        assert "rows span 2 different eval sets" in out
        assert "--eval-id" in out

    def test_eval_id_scope_suppresses_warning_and_filters(self, home, capsys):
        from trinity_local.commands.eval import handle_eval_show
        _write_run(home, eval_id="set_a", target="claude", aggregate=0.8)
        _write_run(home, eval_id="set_b", target="codex", aggregate=0.7)
        handle_eval_show(_compare_args(eval_id="set_a"))
        out = capsys.readouterr().out
        assert "rows span" not in out
        assert "eval set: set_a" in out
        # Filtered out: set_b's codex row shouldn't render.
        assert "codex" not in out

    def test_per_target_dedup_keeps_most_recent(self, home, capsys):
        """If a target has multiple runs against the same eval set,
        keep the newest (matches launchpad policy)."""
        from trinity_local.commands.eval import handle_eval_show
        from trinity_local.evals.builder import results_dir
        results_dir().mkdir(parents=True, exist_ok=True)
        older = results_dir() / "eval_set_a__model_claude__20260101T000000.json"
        older.write_text(json.dumps({
            "eval_id": "set_a", "target_provider": "claude",
            "items": [{"judge_provider": "codex"}],
            "items_completed": 10, "aggregate_score": 0.50,
        }))
        newer = results_dir() / "eval_set_a__model_claude__20260201T000000.json"
        newer.write_text(json.dumps({
            "eval_id": "set_a", "target_provider": "claude",
            "items": [{"judge_provider": "codex"}],
            "items_completed": 10, "aggregate_score": 0.95,
        }))
        # Touch newer to ensure mtime ordering.
        import os, time
        os.utime(newer, (time.time(), time.time()))
        handle_eval_show(_compare_args(eval_id="set_a"))
        out = capsys.readouterr().out
        assert "0.950" in out
        assert "0.500" not in out


class TestCompareFlagRegistered:
    def test_compare_arg_present(self):
        """Argparse smoke: the flag is registered on the eval-show
        subparser so doc invocations don't fail."""
        from trinity_local.commands.eval import register
        import argparse
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers()
        register(sub)
        args = parser.parse_args(["eval-show", "--compare"])
        assert getattr(args, "compare", False) is True

    def test_by_axis_arg_present(self):
        from trinity_local.commands.eval import register
        import argparse
        parser = argparse.ArgumentParser()
        sub = parser.add_subparsers()
        register(sub)
        args = parser.parse_args(["eval-show", "--compare", "--by-axis"])
        assert getattr(args, "by_axis", False) is True


class TestByAxisMatrix:
    """--by-axis: per-rejection-type cross-provider matrix view."""

    def test_matrix_renders_axes_as_columns(self, home, capsys):
        from trinity_local.commands.eval import handle_eval_show
        _write_run(home, eval_id="set_a", target="claude", aggregate=0.79,
                   by_axis={"REFRAME": 0.81, "COMPRESSION": 0.48})
        _write_run(home, eval_id="set_a", target="codex", aggregate=0.76,
                   by_axis={"REFRAME": 0.74, "COMPRESSION": 0.77})
        handle_eval_show(_compare_args(by_axis=True))
        out = capsys.readouterr().out
        # Header carries both axes
        assert "REFRAME" in out
        assert "COMPRESSION" in out
        # Both providers' axis scores render
        assert "0.810" in out  # claude REFRAME
        assert "0.480" in out  # claude COMPRESSION
        assert "0.770" in out  # codex COMPRESSION

    def test_per_axis_leader_callout(self, home, capsys):
        from trinity_local.commands.eval import handle_eval_show
        _write_run(home, eval_id="set_a", target="claude", aggregate=0.79,
                   by_axis={"REFRAME": 0.81, "COMPRESSION": 0.48})
        _write_run(home, eval_id="set_a", target="codex", aggregate=0.76,
                   by_axis={"REFRAME": 0.74, "COMPRESSION": 0.77})
        handle_eval_show(_compare_args(by_axis=True))
        out = capsys.readouterr().out
        # The wedge claim: name the right leader per axis
        assert "REFRAME → claude" in out
        assert "COMPRESSION → codex" in out

    def test_missing_axis_for_a_provider_renders_dash(self, home, capsys):
        """If a provider's run didn't cover an axis (older run, partial
        eval), the matrix cell should show '—', not crash."""
        from trinity_local.commands.eval import handle_eval_show
        _write_run(home, eval_id="set_a", target="claude", aggregate=0.79,
                   by_axis={"REFRAME": 0.81, "COMPRESSION": 0.48})
        _write_run(home, eval_id="set_a", target="codex", aggregate=0.76,
                   by_axis={"REFRAME": 0.74})  # no COMPRESSION axis
        handle_eval_show(_compare_args(by_axis=True))
        out = capsys.readouterr().out
        # codex row should have a — for COMPRESSION
        codex_line = next(l for l in out.splitlines() if "codex" in l and "leader" not in l)
        # Two possible positions depending on header ordering — just
        # check there's a — somewhere in the codex row.
        assert "—" in codex_line

    def test_no_runs_have_per_axis_falls_back_gracefully(self, home, capsys):
        """Pre-by_rejection_type runs (no axis breakdown) should print a
        helpful hint instead of an empty matrix."""
        from trinity_local.commands.eval import handle_eval_show
        _write_run(home, eval_id="set_a", target="claude", aggregate=0.8)  # no by_axis
        handle_eval_show(_compare_args(by_axis=True))
        out = capsys.readouterr().out
        assert "no per-axis breakdown" in out
        assert "eval-run" in out

    def test_per_axis_leader_callout_suppressed_when_mixed_eval_sets(self, home, capsys):
        """Same fix shipped to launchpad chips + PNG matrix card —
        the per-axis leader callout synthesizes a head-to-head across
        providers. When those providers scored on DIFFERENT eval sets,
        the comparison is exactly what the mixed-set warning forbids."""
        from trinity_local.commands.eval import handle_eval_show
        _write_run(home, eval_id="set_a", target="claude", aggregate=0.79,
                   by_axis={"REFRAME": 0.81, "COMPRESSION": 0.48})
        _write_run(home, eval_id="set_b", target="codex", aggregate=0.76,
                   by_axis={"REFRAME": 0.74, "COMPRESSION": 0.77})
        # Unscoped so mixed-set warning fires
        handle_eval_show(_compare_args(by_axis=True))
        out = capsys.readouterr().out
        # Warning fires
        assert "rows span 2 different eval sets" in out
        # But the leader callout is suppressed (would name a misleading
        # winner-per-axis across mismatched sets)
        assert "Per-axis leader:" not in out

    def test_per_axis_leader_callout_renders_when_sets_agree(self, home, capsys):
        from trinity_local.commands.eval import handle_eval_show
        _write_run(home, eval_id="set_a", target="claude", aggregate=0.79,
                   by_axis={"REFRAME": 0.81, "COMPRESSION": 0.48})
        _write_run(home, eval_id="set_a", target="codex", aggregate=0.76,
                   by_axis={"REFRAME": 0.74, "COMPRESSION": 0.77})
        handle_eval_show(_compare_args(by_axis=True))
        out = capsys.readouterr().out
        # No mixed warning, leader callout IS present
        assert "rows span" not in out
        assert "Per-axis leader:" in out
        assert "REFRAME → claude" in out
        assert "COMPRESSION → codex" in out

    def test_by_axis_without_compare_exits_2(self, home, capsys):
        """--by-axis is only valid inside --compare; lone --by-axis exits
        with a hint not a crash."""
        from trinity_local.commands.eval import handle_eval_show
        _write_run(home, eval_id="set_a", target="claude", aggregate=0.8)
        args = Namespace(
            target=None, eval_id=None, limit_samples=0,
            compare=False, by_axis=True,
        )
        with pytest.raises(SystemExit) as exc:
            handle_eval_show(args)
        assert exc.value.code == 2
        out = capsys.readouterr().out
        assert "--by-axis only applies to the leaderboard view" in out
