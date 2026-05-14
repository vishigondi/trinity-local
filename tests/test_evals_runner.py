"""Tests for the corpus-based eval runner + scorer (task #122 follow-up).

The runner dispatches each eval item's prompt to the target provider;
the scorer asks the chairman-judge whether the candidate response
avoided the rejected response's failure mode. These tests mock provider
dispatch so they don't hit real models — the full run + judge cycle
is too expensive for CI.

Real-corpus validation: a separate manual smoke test runs
`trinity-local eval-run --target gemini --limit 3` on the actual corpus.
"""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest


@pytest.fixture
def home(patch_trinity_home: Path) -> Path:
    return patch_trinity_home


def _make_provider_config(name: str = "gemini", *, model: str = "gemini-3-pro"):
    from trinity_local.config import ProviderConfig
    return ProviderConfig(
        name=name,
        type="cli",
        enabled=True,
        label=name.title(),
        command=[name],
        args=[],
        roles={"member"},
        task_types=set(),
        model=model,
    )


def _make_eval_set(items=None):
    """Build an EvalSet with a few items for runner tests."""
    from trinity_local.evals.builder import EvalSet, EvalItem
    if items is None:
        items = [
            EvalItem(
                eval_item_id="ei_aaa",
                prompt="Write a quick spec",
                rejection_type="REDIRECT",
                rejected_response="Here's a 6-section strategy...",
                user_substitute="Just write the spec",
                rubric_signal="user wanted shape, not strategy",
                basin_id="b03",
                source="rejections",
                source_id="r_001",
                prompt_id="pn_1",
                provider_of_rejected_response="claude",
            ),
            EvalItem(
                eval_item_id="ei_bbb",
                prompt="Explain X concisely",
                rejection_type="COMPRESSION",
                rejected_response="X is a long topic that involves...",
                user_substitute="tldr",
                rubric_signal="user wanted shorter",
                basin_id="b00",
                source="rejections",
                source_id="r_002",
                prompt_id="pn_2",
                provider_of_rejected_response="codex",
            ),
        ]
    return EvalSet(
        eval_id="eval_aaaaaaaaaaaa",
        built_at="2026-05-14T00:00:00",
        source="rejections",
        stats={"items": len(items)},
        items=items,
    )


class FakeProvider:
    """Provider stub that returns a fixed response without shelling out.
    Lets us exercise the full runner path without paying for real models."""
    def __init__(self, response_text="A concise answer.", returncode=0, stderr=""):
        self.response_text = response_text
        self.returncode = returncode
        self.stderr = stderr
        self.calls = []

    def run(self, prompt, cwd):
        from trinity_local.providers import ProviderResult
        self.calls.append({"prompt": prompt, "cwd": cwd})
        return ProviderResult(
            provider="fake",
            stdout=self.response_text,
            stderr=self.stderr,
            returncode=self.returncode,
            elapsed_seconds=0.1,
        )


class TestRunner:
    def test_unknown_provider_raises(self, home):
        from trinity_local.evals.runner import run_eval
        eval_set = _make_eval_set()
        with pytest.raises(KeyError, match="Unknown provider"):
            run_eval(eval_set, "nonexistent", {})

    def test_dispatches_each_item_to_target(self, home):
        from trinity_local.evals.runner import run_eval
        fake = FakeProvider(response_text="Spec: ...")
        with patch("trinity_local.evals.runner.make_provider", return_value=fake):
            result = run_eval(
                _make_eval_set(),
                "gemini",
                {"gemini": _make_provider_config("gemini")},
            )
        # One dispatch per eval item
        assert len(fake.calls) == 2
        # Prompts the target saw are the eval items' prompts
        assert fake.calls[0]["prompt"] == "Write a quick spec"
        assert fake.calls[1]["prompt"] == "Explain X concisely"
        # All marked completed
        assert result.items_total == 2
        assert result.items_completed == 2
        assert result.items_failed == 0
        # Each item carries target_response
        assert all(it.target_response == "Spec: ..." for it in result.items)

    def test_provider_failure_captured_per_item(self, home):
        """One bad dispatch must not abort the whole run."""
        from trinity_local.evals.runner import run_eval
        from trinity_local.providers import ProviderResult

        class HalfFailingProvider:
            def __init__(self):
                self.idx = 0
            def run(self, prompt, cwd):
                self.idx += 1
                if self.idx == 2:
                    return ProviderResult(
                        provider="gemini",
                        stdout="",
                        stderr="rate limit",
                        returncode=1,
                        elapsed_seconds=0.05,
                    )
                return ProviderResult(
                    provider="gemini",
                    stdout="OK",
                    stderr="",
                    returncode=0,
                    elapsed_seconds=0.05,
                )

        with patch("trinity_local.evals.runner.make_provider", return_value=HalfFailingProvider()):
            result = run_eval(
                _make_eval_set(),
                "gemini",
                {"gemini": _make_provider_config("gemini")},
            )
        assert result.items_total == 2
        assert result.items_completed == 1
        assert result.items_failed == 1
        # The failure is captured per-item, not as a top-level error
        assert result.items[0].target_error is None
        assert "rate limit" in (result.items[1].target_error or "")

    def test_limit_caps_dispatched_items(self, home):
        from trinity_local.evals.runner import run_eval
        fake = FakeProvider()
        with patch("trinity_local.evals.runner.make_provider", return_value=fake):
            result = run_eval(
                _make_eval_set(),
                "gemini",
                {"gemini": _make_provider_config("gemini")},
                limit=1,
            )
        assert len(fake.calls) == 1
        assert result.items_total == 1

    def test_save_and_load_roundtrip(self, home):
        from trinity_local.evals.runner import run_eval, save_run_result, load_run_result
        fake = FakeProvider()
        with patch("trinity_local.evals.runner.make_provider", return_value=fake):
            result = run_eval(
                _make_eval_set(),
                "gemini",
                {"gemini": _make_provider_config("gemini")},
            )
        path = save_run_result(result)
        assert path.exists()
        reloaded = load_run_result(path)
        assert reloaded is not None
        assert reloaded.eval_id == result.eval_id
        assert reloaded.target_provider == "gemini"
        assert len(reloaded.items) == 2
        assert reloaded.items[0].eval_item_id == "ei_aaa"


class TestScorer:
    def test_unknown_judge_raises(self, home):
        from trinity_local.evals.runner import run_eval
        from trinity_local.evals.scorer import score_run
        fake = FakeProvider()
        with patch("trinity_local.evals.runner.make_provider", return_value=fake):
            result = run_eval(_make_eval_set(), "gemini",
                              {"gemini": _make_provider_config("gemini")})
        with pytest.raises(KeyError, match="Unknown judge provider"):
            score_run(result, "lens text", "nonexistent",
                      {"gemini": _make_provider_config("gemini")})

    def test_parse_judge_response_handles_json(self):
        from trinity_local.evals.scorer import _parse_judge_response
        score, reason = _parse_judge_response('{"score": 0.73, "reason": "matched the user frame"}')
        assert score == pytest.approx(0.73)
        assert reason == "matched the user frame"

    def test_parse_judge_response_handles_markdown_fence(self):
        from trinity_local.evals.scorer import _parse_judge_response
        raw = '```json\n{"score": 0.5, "reason": "neutral"}\n```'
        score, reason = _parse_judge_response(raw)
        assert score == pytest.approx(0.5)
        assert reason == "neutral"

    def test_parse_judge_response_clamps_score_to_unit_interval(self):
        from trinity_local.evals.scorer import _parse_judge_response
        score, _ = _parse_judge_response('{"score": 1.7, "reason": "x"}')
        assert score == 1.0
        score, _ = _parse_judge_response('{"score": -0.2, "reason": "x"}')
        assert score == 0.0

    def test_parse_judge_response_falls_back_to_neutral_on_garbage(self):
        from trinity_local.evals.scorer import _parse_judge_response
        score, reason = _parse_judge_response("the model just emitted prose with no JSON")
        assert score == 0.5
        assert "unparseable" in reason

    def test_score_run_populates_per_item_scores_and_aggregates(self, home):
        from trinity_local.evals.runner import run_eval
        from trinity_local.evals.scorer import score_run

        target_fake = FakeProvider(response_text="The candidate answer")
        judge_responses = iter([
            '{"score": 0.8, "reason": "good match"}',
            '{"score": 0.4, "reason": "too long"}',
        ])
        class JudgeProvider:
            def run(self, prompt, cwd):
                from trinity_local.providers import ProviderResult
                return ProviderResult(
                    provider="claude",
                    stdout=next(judge_responses),
                    stderr="",
                    returncode=0,
                    elapsed_seconds=0.1,
                )

        # Two-step patch: runner gets target_fake, scorer gets judge.
        with patch("trinity_local.evals.runner.make_provider", return_value=target_fake):
            result = run_eval(_make_eval_set(), "gemini",
                              {"gemini": _make_provider_config("gemini")})

        with patch("trinity_local.evals.scorer.make_provider", return_value=JudgeProvider()):
            score_run(
                result, "lens excerpt", "claude",
                {"gemini": _make_provider_config("gemini"),
                 "claude": _make_provider_config("claude")},
            )

        # Per-item scores set
        assert result.items[0].score == pytest.approx(0.8)
        assert result.items[1].score == pytest.approx(0.4)
        assert all(it.judge_provider == "claude" for it in result.items)
        # Aggregate = mean of two scores
        assert result.aggregate_score == pytest.approx(0.6)
        # Per-rejection-type breakdown
        assert "REDIRECT" in result.by_rejection_type
        assert "COMPRESSION" in result.by_rejection_type
        assert result.by_rejection_type["REDIRECT"]["mean_score"] == pytest.approx(0.8)
        assert result.by_rejection_type["COMPRESSION"]["mean_score"] == pytest.approx(0.4)

    def test_score_run_skips_failed_dispatches(self, home):
        """Items that failed dispatch get score=None, not 0 — distinguishing
        'model performed badly' from 'dispatch never landed'."""
        from trinity_local.evals.builder import EvalSet, EvalItem
        from trinity_local.evals.runner import EvalRunResult, EvalItemRun
        from trinity_local.evals.scorer import score_run

        run_result = EvalRunResult(
            eval_id="eval_xxx",
            target_provider="gemini",
            target_model="gemini-3",
            started_at="2026-05-14T00:00:00",
            completed_at="2026-05-14T00:00:00",
            items_total=2,
            items_completed=1,
            items_failed=1,
            items=[
                EvalItemRun(
                    eval_item_id="ok_item", rejection_type="REFRAME",
                    prompt="p", rejected_response="r", user_substitute="u",
                    rubric_signal="s", basin_id=None,
                    target_response="good answer", target_error=None,
                    elapsed_seconds=0.1,
                ),
                EvalItemRun(
                    eval_item_id="failed_item", rejection_type="REFRAME",
                    prompt="p", rejected_response="r", user_substitute="u",
                    rubric_signal="s", basin_id=None,
                    target_response="", target_error="rate limit",
                    elapsed_seconds=0.0,
                ),
            ],
        )

        class JudgeProvider:
            def run(self, prompt, cwd):
                from trinity_local.providers import ProviderResult
                return ProviderResult(
                    provider="claude", stdout='{"score": 0.7, "reason": "ok"}',
                    stderr="", returncode=0, elapsed_seconds=0.1,
                )

        with patch("trinity_local.evals.scorer.make_provider", return_value=JudgeProvider()):
            score_run(run_result, "lens", "claude",
                      {"claude": _make_provider_config("claude")})

        # Only one item scored — the failed dispatch is left None
        assert run_result.items[0].score == pytest.approx(0.7)
        assert run_result.items[1].score is None
        # Aggregate is mean of SCORED items only
        assert run_result.aggregate_score == pytest.approx(0.7)


class TestEvalRunCLI:
    def test_eval_run_subcommand_registered(self):
        import argparse
        from trinity_local import main as main_module
        parser = main_module.build_parser()
        sub_actions = [a for a in parser._actions if isinstance(a, argparse._SubParsersAction)]
        choices = sub_actions[0].choices
        assert "eval-run" in choices
        # Required --target flag
        action = next((a for a in choices["eval-run"]._actions if a.dest == "target"), None)
        assert action is not None and action.required
