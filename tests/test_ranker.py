"""Tests for ranker types and interface."""
from __future__ import annotations

import pytest

from trinity_local.ranker import RoutingContext, RoutingDecision, build_default_ranker


class TestRoutingContext:
    """RoutingContext contract: construction, immutability."""

    def test_construct_minimal(self):
        """Construct with required fields only."""
        ctx = RoutingContext(
            task_text="Fix the auth bug",
            task_kind="debug",
            current_provider="claude",
            session_id="session-123",
        )
        assert ctx.task_text == "Fix the auth bug"
        assert ctx.task_kind == "debug"
        assert ctx.current_provider == "claude"
        assert ctx.session_id == "session-123"
        assert ctx.has_web is False
        assert ctx.message_count == 0
        assert ctx.metadata == {}

    def test_construct_full(self):
        """Construct with all fields."""
        ctx = RoutingContext(
            task_text="Implement feature",
            task_kind="feature",
            current_provider="codex",
            session_id="session-456",
            task_id="task-789",
            cwd="/home/user/project",
            source="claude",
            switched_from_provider="gemini",
            switched_from_task_id="task-111",
            has_web=True,
            has_tools=True,
            has_edits=True,
            message_count=42,
            metadata={"priority": "high"},
        )
        assert ctx.task_id == "task-789"
        assert ctx.has_web is True
        assert ctx.message_count == 42
        assert ctx.metadata["priority"] == "high"

    def test_frozen(self):
        """RoutingContext is immutable."""
        ctx = RoutingContext(
            task_text="test",
            task_kind="debug",
            current_provider="claude",
            session_id="123",
        )
        with pytest.raises(AttributeError):
            ctx.task_kind = "feature"


class TestRoutingDecision:
    """RoutingDecision contract: construction, immutability, semantics."""

    def test_construct_minimal(self):
        """Construct with defaults."""
        dec = RoutingDecision(recommended_provider="claude")
        assert dec.recommended_provider == "claude"
        assert dec.top_k == []
        assert dec.needs_council is False
        assert dec.confidence == 0.5
        assert dec.backend == "heuristic"
        assert dec.evidence == []

    def test_construct_council(self):
        """Construct a council recommendation."""
        dec = RoutingDecision(
            recommended_provider=None,
            top_k=["claude", "codex"],
            needs_council=True,
            confidence=0.75,
            backend="knn",
            evidence=["k-NN neighbors suggest council"],
        )
        assert dec.recommended_provider is None
        assert dec.needs_council is True
        assert dec.confidence == 0.75
        assert dec.backend == "knn"

    def test_top_k_semantics(self):
        """top_k[0] should match recommended_provider when both present."""
        dec = RoutingDecision(
            recommended_provider="claude",
            top_k=["claude", "codex"],
        )
        assert dec.top_k[0] == dec.recommended_provider

    def test_frozen(self):
        """RoutingDecision is immutable."""
        dec = RoutingDecision(recommended_provider="claude")
        with pytest.raises(AttributeError):
            dec.recommended_provider = "codex"

    def test_no_methods(self):
        """RoutingDecision is pure data: no formatting or policy methods."""
        dec = RoutingDecision(recommended_provider="claude")
        assert not hasattr(dec, "to_message")
        assert not hasattr(dec, "render_evidence")
        assert not hasattr(dec, "to_dict")  # No serio-friendly helpers


class TestBuildDefaultRanker:
    """build_default_ranker() factory is a planning stub."""

    def test_not_implemented(self):
        """Factory raises NotImplementedError until backends are ready."""
        with pytest.raises(NotImplementedError):
            from trinity_local.ranker import build_default_ranker

            build_default_ranker()
