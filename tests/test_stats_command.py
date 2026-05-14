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


class TestStatsShareTemplate:
    """The --share flag prints copy-pasteable Twitter/HN templates.
    This is the launch-package T-1 'thread drafted' surface — when
    the user's about to write a launch post, they type one command
    and get pre-populated text with their actual numbers. The
    friction-removal that turns 'I have numbers' into 'I have a
    tweet ready to post.'"""

    def test_share_renders_all_three_anchors_when_data_present(
        self, isolated_home, capsys
    ):
        from datetime import datetime, timezone
        from trinity_local.commands.stats import handle_stats

        # Seed all three anchors: rate-limit saves, eval result,
        # councils + prompts.
        now = datetime.now(timezone.utc).isoformat()
        _seed_dispatch(isolated_home, [
            {"ts": now, "primary": "claude", "rate_limit_save": True}
            for _ in range(50)
        ])
        _seed_council(isolated_home, "council_a", rated=True)
        _seed_eval_set(isolated_home, n_items=10)
        _seed_eval_result(isolated_home, target="gemini", score=0.81)
        _seed_prompts(isolated_home, n=2500)

        rc = handle_stats(_make_args(share=True))
        assert rc == 0
        out = capsys.readouterr().out

        # All three anchors named
        assert "Rate-limit-saves anchor" in out
        assert "Personal-benchmark anchor" in out
        assert "Corpus-size anchor" in out

        # Each anchor carries the right number from the actual report
        # (so the share-text and the source CLI can't disagree — that
        # would be a credibility hit when someone runs `stats` to
        # verify a posted claim).
        assert "50" in out  # rate-limit saves count
        assert "0.81" in out  # eval aggregate score
        assert "2,500" in out  # corpus size

        # Wedge phrases that must stay one-voice across surfaces.
        # Normalize whitespace because the templates wrap at column
        # boundaries — a multi-word phrase can cross a newline.
        flat = " ".join(out.split())
        assert "commercially prevented from building" in flat
        assert "the layer above the labs" in flat

    def test_share_omits_benchmark_anchor_when_no_eval_result(
        self, isolated_home, capsys
    ):
        """Don't print a benchmark anchor with a missing/null score —
        users would tweet '? scored None/1.00 on my question' and
        that's worse than skipping the variant entirely."""
        from datetime import datetime, timezone
        from trinity_local.commands.stats import handle_stats

        _seed_dispatch(isolated_home, [
            {"ts": datetime.now(timezone.utc).isoformat(),
             "primary": "claude", "rate_limit_save": True},
        ])
        _seed_prompts(isolated_home, n=100)

        rc = handle_stats(_make_args(share=True))
        assert rc == 0
        out = capsys.readouterr().out

        # Rate-limit + corpus anchors present
        assert "Rate-limit-saves anchor" in out
        assert "Corpus-size anchor" in out
        # Benchmark anchor absent
        assert "Personal-benchmark anchor" not in out

    def test_share_omits_rate_limit_anchor_when_no_saves(
        self, isolated_home, capsys
    ):
        """Fresh install: don't tweet 'Trinity routed 0 work-units'
        — that's an anti-marketing claim. Skip variant cleanly."""
        from trinity_local.commands.stats import handle_stats
        _seed_prompts(isolated_home, n=10)

        rc = handle_stats(_make_args(share=True))
        assert rc == 0
        out = capsys.readouterr().out
        assert "Rate-limit-saves anchor" not in out
        # But corpus anchor still prints (always shippable)
        assert "Corpus-size anchor" in out

    def test_share_silent_on_completely_empty_install(
        self, isolated_home, capsys
    ):
        """When NOTHING is accumulated yet, the share command should
        produce the header but no anchor variants — there's literally
        nothing to brag about. Output should still be clean (not
        crashy) so onboarding scripts can fire it blindly."""
        from trinity_local.commands.stats import handle_stats
        rc = handle_stats(_make_args(share=True))
        assert rc == 0
        out = capsys.readouterr().out
        # Header still prints (signals the command ran)
        assert "share-ready templates" in out
        # But no anchors at all
        assert "anchor" not in out.replace("share-ready", "")

    def test_share_subcommand_flag_registered(self):
        """argparse wires up --share. Without this, the flag silently
        falls through to as_json branch logic."""
        import argparse
        from trinity_local import main as main_module
        parser = main_module.build_parser()
        sub_actions = [a for a in parser._actions
                       if isinstance(a, argparse._SubParsersAction)]
        choices = sub_actions[0].choices
        stats_parser = choices["stats"]
        share_actions = [a for a in stats_parser._actions if a.dest == "share"]
        assert share_actions, "stats lacks the --share flag"
        assert share_actions[0].const is True  # store_true

    def test_share_renders_leaderboard_when_3_targets(self, isolated_home, capsys):
        """The 3-provider snapshot (launch-arc #116 v1 deliverable):
        when targets list has ≥2 entries, the benchmark anchor
        renders a LEADERBOARD with rank + score + judge — strictly
        stronger marketing than the single-point ('Model X scored
        Y') form. Locks in the leaderboard shape so a future change
        doesn't silently revert to single-point.
        """
        from trinity_local.commands.stats import handle_stats
        # Seed three target result files
        results = isolated_home / "evals" / "results"
        results.mkdir(parents=True, exist_ok=True)
        for tgt, score, judge in [
            ("claude", 1.00, "gemini"),
            ("gemini", 0.83, "claude"),
            ("codex", 0.80, "claude"),
        ]:
            (results / f"eval_abc__model_{tgt}__20260514.json").write_text(
                json.dumps({
                    "eval_id": "eval_abc",
                    "target_provider": tgt,
                    "target_model": f"{tgt}-mock",
                    "aggregate_score": score,
                    "items_completed": 5,
                    "items": [{"item_id": "i1", "judge_provider": judge}],
                }),
                encoding="utf-8",
            )

        rc = handle_stats(_make_args(share=True))
        assert rc == 0
        out = capsys.readouterr().out
        # The leaderboard header form is distinct from single-point
        assert "leaderboard" in out.lower()
        # All three providers named in the ranked output
        for tgt in ("Claude", "Gemini", "Codex"):
            assert tgt in out
        # Judge attribution visible (the "no self-grading" proof)
        assert "judged by gemini" in out
        assert "judged by claude" in out
        # Wedge phrase still ships
        flat = " ".join(out.split())
        assert "Judges rotated so no model grades itself" in flat

    def test_share_falls_back_to_single_point_with_one_target(self, isolated_home, capsys):
        """One target = the old single-point form. Leaderboard would
        be a degenerate 'leaderboard of 1' which reads weak. The
        existing single-point form ('Model X scored Y') is correct
        UX for that state."""
        from trinity_local.commands.stats import handle_stats
        results = isolated_home / "evals" / "results"
        results.mkdir(parents=True, exist_ok=True)
        (results / "eval_abc__model_gemini__20260514.json").write_text(
            json.dumps({
                "eval_id": "eval_abc",
                "target_provider": "gemini",
                "target_model": "gemini-mock",
                "aggregate_score": 0.75,
                "items_completed": 3,
                "items": [{"item_id": "i1", "judge_provider": "claude"}],
            }),
            encoding="utf-8",
        )
        rc = handle_stats(_make_args(share=True))
        assert rc == 0
        out = capsys.readouterr().out
        # Single-point form (the old anchor)
        assert "Gemini scored 0.75" in out
        # Should NOT use the leaderboard form for a single target
        assert "leaderboard" not in out.lower()

    def test_targets_field_in_json_output(self, isolated_home, capsys):
        """The JSON report carries `targets` (leaderboard data) so
        callers can drive their own post-template (Twitter, HN, blog)
        from a single JSON read."""
        from trinity_local.commands.stats import handle_stats
        results = isolated_home / "evals" / "results"
        results.mkdir(parents=True, exist_ok=True)
        for tgt, score in [("claude", 1.0), ("gemini", 0.83), ("codex", 0.8)]:
            (results / f"eval_abc__model_{tgt}__20260514.json").write_text(
                json.dumps({
                    "eval_id": "eval_abc",
                    "target_provider": tgt,
                    "aggregate_score": score,
                    "items_completed": 5,
                    "items": [{"item_id": "i1", "judge_provider": "claude"}],
                }),
                encoding="utf-8",
            )
        rc = handle_stats(_make_args(as_json=True))
        assert rc == 0
        out = json.loads(capsys.readouterr().out)
        targets = out["evals"]["targets"]
        assert len(targets) == 3
        # Sorted by aggregate desc
        assert targets[0]["target"] == "claude"
        assert targets[0]["aggregate_score"] == 1.0
        assert targets[-1]["target"] == "codex"
