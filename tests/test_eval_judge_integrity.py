"""#246: an eval run must never persist a fabricated benchmark.

A live run was judged by the 'mlx' embedder backend, which returns empty output
→ every item defaulted to a neutral 0.5 → aggregate_score=0.5 was saved,
indistinguishable from a real score. Two guards: reject non-LLM judges up front,
and suppress the aggregate when scoring is degenerate (>50% empty/unparseable).
"""
from __future__ import annotations

from types import SimpleNamespace

import pytest

from trinity_local.evals import scorer
from trinity_local.evals.runner import EvalItemRun, EvalRunResult


def _run(n_items: int = 4) -> EvalRunResult:
    items = [
        EvalItemRun(
            eval_item_id=f"i{i}",
            rejection_type="REFRAME",
            prompt=f"prompt {i}",
            rejected_response="bad",
            user_substitute="good",
            rubric_signal="",
            basin_id="b0",
            target_response="a real target response of some length",
            target_error=None,
            elapsed_seconds=0.0,
        )
        for i in range(n_items)
    ]
    return EvalRunResult(
        eval_id="e1", target_provider="claude", target_model="claude-opus-4-8",
        started_at="2026-05-29T00:00:00", completed_at="", items_total=n_items,
        items_completed=n_items, items_failed=0, items=items,
    )


def test_rejects_non_llm_judge():
    # 'mlx' is in the configs but is the embedder backend, not an LLM judge.
    cfg = SimpleNamespace(name="mlx", model="mlx-community/Qwen", args=[])
    with pytest.raises(ValueError, match="not a valid LLM judge"):
        scorer.score_run(_run(), "lens text", "mlx", {"mlx": cfg})


def test_degenerate_scoring_suppresses_aggregate(monkeypatch):
    # A judge that returns empty for every item → all 0.5 defaults → the
    # aggregate must be None (not 0.5) and the run flagged degraded.
    class EmptyJudge:
        def run(self, prompt, cwd=None):
            return SimpleNamespace(stdout="")  # empty → 0.5 default
    monkeypatch.setattr(scorer, "make_provider", lambda cfg: EmptyJudge())
    cfg = SimpleNamespace(name="claude", model="claude-opus-4-8", args=[])
    result = scorer.score_run(_run(4), "lens text", "claude", {"claude": cfg})
    assert result.scoring_degraded is True
    assert result.aggregate_score is None, "must not persist a fabricated 0.5 benchmark"


def test_real_scoring_keeps_aggregate(monkeypatch):
    # A judge returning real scores → a genuine aggregate, not suppressed.
    class GoodJudge:
        def run(self, prompt, cwd=None):
            return SimpleNamespace(stdout='{"score": 0.8, "reason": "target is better"}')
    monkeypatch.setattr(scorer, "make_provider", lambda cfg: GoodJudge())
    cfg = SimpleNamespace(name="claude", model="claude-opus-4-8", args=[])
    result = scorer.score_run(_run(4), "lens text", "claude", {"claude": cfg})
    assert result.scoring_degraded is False
    assert result.aggregate_score == pytest.approx(0.8)
