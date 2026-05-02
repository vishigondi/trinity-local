"""Tests for cost tracking module."""
from __future__ import annotations

from trinity_local.cost_tracker import (
    SessionCost,
    _find_cost_rate,
    compute_session_cost,
    summarize_costs,
)
from trinity_local.training_schema import (
    ModelDescriptor,
    OutcomeSignals,
    RawSessionRef,
    SessionFeatures,
)


class TestFindCostRate:
    def test_exact_prefix(self):
        rate = _find_cost_rate("claude-sonnet-4-20250514")
        assert rate["input"] == 3.0
        assert rate["output"] == 15.0

    def test_gemini_flash(self):
        rate = _find_cost_rate("gemini-2.5-flash-preview")
        assert rate["input"] == 0.30

    def test_unknown_model(self):
        rate = _find_cost_rate("totally-unknown-model-v9")
        assert rate["input"] == 0.0
        assert rate["output"] == 0.0

    def test_none_model(self):
        rate = _find_cost_rate(None)
        assert rate["input"] == 0.0


def _make_features(
    *,
    provider: str = "claude",
    model_id: str = "claude-sonnet-4-20250514",
    input_tokens: int = 1000,
    output_tokens: int = 500,
    cached_tokens: int = 200,
) -> SessionFeatures:
    """Create minimal SessionFeatures for cost tests."""
    return SessionFeatures(
        raw=RawSessionRef(
            source=provider,
            native_id="test-001",
            source_path="/test/path.jsonl",
        ),
        provider=provider,
        session_id="test-001",
        model=ModelDescriptor(
            provider=provider,
            normalized_model_id=model_id,
        ),
        started_at="2026-04-01T10:00:00Z",
        outcome=OutcomeSignals(
            token_input=input_tokens,
            token_output=output_tokens,
            token_cached=cached_tokens,
        ),
    )


class TestComputeSessionCost:
    def test_basic_cost(self):
        features = _make_features(input_tokens=1_000_000, output_tokens=1_000_000, cached_tokens=0)
        cost = compute_session_cost(features)
        assert cost.provider == "claude"
        assert cost.input_cost_usd == 3.0  # 1M * $3/1M
        assert cost.output_cost_usd == 15.0  # 1M * $15/1M
        assert cost.total_cost_usd == 18.0

    def test_cached_tokens_free(self):
        features = _make_features(input_tokens=1000, output_tokens=500, cached_tokens=800)
        cost = compute_session_cost(features)
        # Only 200 billable input tokens (1000 - 800)
        expected_input = 200 * 3.0 / 1_000_000
        assert cost.input_cost_usd == round(expected_input, 6)

    def test_zero_tokens(self):
        features = _make_features(input_tokens=0, output_tokens=0, cached_tokens=0)
        cost = compute_session_cost(features)
        assert cost.total_cost_usd == 0.0

    def test_task_kind_passthrough(self):
        features = _make_features()
        cost = compute_session_cost(features, task_kind="coding")
        assert cost.task_kind == "coding"


class TestSummarizeCosts:
    def test_aggregate_by_provider(self):
        costs = [
            SessionCost("s1", "claude", "claude-sonnet-4", 1000, 500, 0, 0.003, 0.0075, 0.0105, "2026-04-01T10:00:00Z", "coding"),
            SessionCost("s2", "claude", "claude-sonnet-4", 2000, 1000, 0, 0.006, 0.015, 0.021, "2026-04-01T11:00:00Z", "coding"),
            SessionCost("s3", "gemini", "gemini-2.5-pro", 5000, 2000, 0, 0.00625, 0.02, 0.02625, "2026-04-01T12:00:00Z", "research"),
        ]
        summaries = summarize_costs(costs)
        assert "claude" in summaries
        assert "gemini" in summaries
        assert summaries["claude"].sessions == 2
        assert summaries["gemini"].sessions == 1
        assert summaries["claude"].by_task_kind["coding"] > 0

    def test_empty_list(self):
        summaries = summarize_costs([])
        assert summaries == {}
