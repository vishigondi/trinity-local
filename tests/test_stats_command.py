"""Tests for `trinity-local stats` — the marketing-voice summary command.

Distinct from `status` (system health). stats is the "what has Trinity
done for me" surface used in onboarding screenshots and tester DMs.
The launch-package's T-1 sequence depends on this being a single
verifiable command.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
    return tmp_path


def _make_args(**kwargs):
    """Build a SimpleNamespace mimicking argparse output."""
    from types import SimpleNamespace
    defaults = {"days": 30, "as_json": False}
    defaults.update(kwargs)
    return SimpleNamespace(**defaults)


def _seed_council(home: Path, council_id: str, *, rated: bool):
    council_dir = home / "council_outcomes"
    council_dir.mkdir(parents=True, exist_ok=True)
    metadata: dict = {}
    if rated:
        metadata["user_verdict"] = {"user_winner": "claude"}
    (council_dir / f"{council_id}.json").write_text(
        json.dumps({"council_run_id": council_id, "metadata": metadata}),
        encoding="utf-8",
    )


def _seed_dispatch(home: Path, entries: list[dict]):
    analytics = home / "analytics"
    analytics.mkdir(parents=True, exist_ok=True)
    path = analytics / "dispatch_outcomes.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e) + "\n")


def _seed_eval_set(home: Path, n_items: int):
    evals = home / "evals"
    evals.mkdir(parents=True, exist_ok=True)
    (evals / "eval_abc.json").write_text(
        json.dumps({"eval_id": "eval_abc",
                    "items": [{"item_id": f"i{i}"} for i in range(n_items)]}),
        encoding="utf-8",
    )


def _seed_eval_result(home: Path, *, target="gemini", score=0.75):
    results = home / "evals" / "results"
    results.mkdir(parents=True, exist_ok=True)
    (results / f"eval_abc__model_{target}__20260514.json").write_text(
        json.dumps({
            "target_provider": target,
            "target_model": f"{target}-mock",
            "aggregate_score": score,
            "items_completed": 5,
        }),
        encoding="utf-8",
    )


def _seed_prompts(home: Path, n: int):
    prompts = home / "prompts"
    prompts.mkdir(parents=True, exist_ok=True)
    path = prompts / "prompt_nodes.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for i in range(n):
            f.write(json.dumps({"id": f"p{i}"}) + "\n")


class TestStatsCommand:
    """The marketing-voice summary surface — every shipped metric in one view."""

    def test_empty_install_returns_zeros(self, isolated_home, capsys):
        """A fresh install with nothing accumulated still runs cleanly
        and reports zeros across the board. The command must NEVER crash
        on missing state — onboarding screenshots happen before
        seed-from-taste-terminal runs."""
        from trinity_local.commands.stats import handle_stats
        rc = handle_stats(_make_args(as_json=True))
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["prompts_indexed"] == 0
        assert out["councils"] == {"total": 0, "rated": 0, "verdict_rate": 0.0}
        assert out["rate_limit_saves"] == {"total": 0, "of_calls": 0, "save_rate": 0.0}
        assert out["evals"]["items_mined"] == 0
        assert out["evals"]["latest_run"] is None

    def test_full_corpus_numbers_match_sources(self, isolated_home, capsys):
        """The whole point: stats produces the same numbers as the
        per-source CLIs (`metric`, council_outcomes count, eval-show).
        If stats and the source CLIs disagree, marketing claims based
        on stats won't survive a journalist running the source CLI to
        verify."""
        from datetime import datetime, timezone
        from trinity_local.commands.stats import handle_stats

        # Set up: 5 councils, 2 rated; 10 dispatches, 3 saves;
        # 8 eval items; 1 eval run target=gemini score=0.72.
        for i in range(5):
            _seed_council(isolated_home, f"council_{i}", rated=(i < 2))
        now = datetime.now(timezone.utc).isoformat()
        _seed_dispatch(isolated_home, [
            {"ts": now, "primary": "claude", "rate_limit_save": i < 3}
            for i in range(10)
        ])
        _seed_eval_set(isolated_home, n_items=8)
        _seed_eval_result(isolated_home, target="gemini", score=0.72)
        _seed_prompts(isolated_home, n=1000)

        rc = handle_stats(_make_args(as_json=True))
        assert rc == 0
        out = json.loads(capsys.readouterr().out)

        assert out["prompts_indexed"] == 1000
        assert out["councils"]["total"] == 5
        assert out["councils"]["rated"] == 2
        assert out["councils"]["verdict_rate"] == 0.4
        assert out["rate_limit_saves"]["total"] == 3
        assert out["rate_limit_saves"]["of_calls"] == 10
        assert out["rate_limit_saves"]["save_rate"] == 0.3
        assert out["evals"]["items_mined"] == 8
        assert out["evals"]["latest_run"]["target"] == "gemini"
        assert out["evals"]["latest_run"]["aggregate_score"] == 0.72

    def test_uses_ts_field_not_at(self, isolated_home, capsys):
        """The field-name regression that bit the launchpad helper at
        T-1. ask.py writes `ts` for the timestamp; if stats reads `at`,
        the window filter is silent dead code and EVERY entry passes.
        Verify by seeding ONLY with `ts` and a far-past timestamp —
        the entry MUST be excluded."""
        from datetime import datetime, timedelta, timezone
        from trinity_local.commands.stats import handle_stats

        far_past = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()
        _seed_dispatch(isolated_home, [
            {"ts": far_past, "primary": "claude", "rate_limit_save": True},
        ])
        rc = handle_stats(_make_args(as_json=True))
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        # 400 days old, 30-day window — should be excluded entirely.
        assert out["rate_limit_saves"]["of_calls"] == 0, (
            "Far-past entry slipped through the window filter — stats "
            "must read the same timestamp field ask.py writes (`ts`)."
        )

    def test_human_output_is_marketing_shaped(self, isolated_home, capsys):
        """The human-readable output is what users screenshot for
        marketing. Pin the shape: emoji-prefixed lines, each one a
        complete sentence with its number, ordered prompts→councils→
        rate-limit→evals→result. If the layout drifts, the launch
        screenshots and the tester-DM examples diverge from reality."""
        from trinity_local.commands.stats import handle_stats
        _seed_prompts(isolated_home, n=100)
        _seed_council(isolated_home, "council_a", rated=True)
        _seed_eval_set(isolated_home, n_items=20)
        rc = handle_stats(_make_args(as_json=False))
        assert rc == 0
        out = capsys.readouterr().out
        # Headline marketing voice
        assert "what's accumulated in your corpus" in out
        # Each marketing-critical number labeled clearly
        assert "100" in out and "Prompts indexed" in out
        assert "Councils run" in out
        assert "Rate-limit saves" in out
        assert "Eval items mined" in out
        # The state-dir footer (verifiable: user can `cat` the files)
        assert "State:" in out

    def test_stats_subcommand_registered(self):
        import argparse
        from trinity_local import main as main_module
        parser = main_module.build_parser()
        sub_actions = [a for a in parser._actions
                       if isinstance(a, argparse._SubParsersAction)]
        assert "stats" in sub_actions[0].choices

    def test_handles_corrupt_eval_set_without_crashing(self, isolated_home, capsys):
        """Analytics-never-crash invariant. A malformed eval set on
        disk shouldn't take down the marketing surface."""
        from trinity_local.commands.stats import handle_stats
        evals = isolated_home / "evals"
        evals.mkdir(parents=True, exist_ok=True)
        (evals / "eval_corrupt.json").write_text("{not json}", encoding="utf-8")
        # Should not raise.
        rc = handle_stats(_make_args(as_json=True))
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        assert out["evals"]["items_mined"] == 0
