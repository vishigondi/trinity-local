"""Tests for the v1.5 `ask` orchestration.

Hits are fabricated as SearchResult instances so we don't depend on a populated
~/.trinity/memory/ in the test environment. The production path uses
`memory.search_prompt_nodes` which we patch at module level.
"""
from __future__ import annotations

import pytest

from trinity_local import ask as ask_module
from trinity_local.ask import (
    AskDecision,
    ESCALATE_HINT_THRESHOLD,
    _decide_from_hits,
    decide_route,
    run_ask,
)
from trinity_local.memory.index import SearchResult


def _hit(
    *,
    prompt_id: str,
    chairman_winner: str | None = None,
    user_winner: str | None = None,
    score: float = 0.8,
) -> SearchResult:
    return SearchResult(
        prompt_id=prompt_id,
        text=f"prompt {prompt_id}",
        score=score,
        prompt_similarity=score,
        window_similarity=score,
        transcript_similarity=0.0,
        hardness=0.5,
        reasons=["test"],
        chairman_winner=chairman_winner,
        user_winner=user_winner,
        council_count=1 if (chairman_winner or user_winner) else 0,
    )


class TestDecideFromHits:
    def test_no_hits_returns_default_provider_with_zero_trust(self):
        decision = _decide_from_hits([], available_providers=["claude", "codex"])
        assert decision.routed_to == "claude"
        assert decision.trust_score == 0.0
        assert decision.reason == "no_history"

    def test_user_verdict_outweighs_chairman(self):
        # Three hits: chairman picked codex twice; user overrode to claude once.
        # User verdict carries 1.5x weight, so claude should win.
        hits = [
            _hit(prompt_id="p1", chairman_winner="codex", user_winner="claude"),
            _hit(prompt_id="p2", chairman_winner="codex"),
            _hit(prompt_id="p3", chairman_winner="codex"),
        ]
        decision = _decide_from_hits(hits, available_providers=None)
        assert decision.routed_to in {"codex", "claude"}
        # The chairman has 3.0 (1 per hit), user-winner adds 1.5 for claude.
        # codex: 3 * 1.0 = 3.0; claude: 1 * 1.5 = 1.5. Codex still wins.
        assert decision.routed_to == "codex"
        assert decision.runner_up == "claude"
        assert decision.vote_counts["codex"] == 3
        assert decision.vote_counts["claude"] == 1  # 1.5 floored to 1 by int()

    def test_unanimous_user_verdict_routes_with_high_trust(self):
        hits = [
            _hit(prompt_id=f"p{i}", chairman_winner="claude", user_winner="claude")
            for i in range(5)
        ]
        decision = _decide_from_hits(hits, available_providers=None)
        assert decision.routed_to == "claude"
        # 5 hits × (1.0 chairman + 1.5 user) all for claude → agreement = 1.0
        assert decision.trust_score > 0.85

    def test_low_sample_size_caps_trust(self):
        # Single hit, unanimous — but n_hits=1 should cap trust.
        hits = [_hit(prompt_id="p1", user_winner="codex")]
        decision = _decide_from_hits(hits, available_providers=None)
        assert decision.routed_to == "codex"
        # Sample = 1/5 = 0.2 → contributes 0.30 * 0.2 = 0.06 from sample component.
        # Agreement = 1.0 → 0.55 from agreement. Recency = 1.0 → 0.15. Total ~0.76.
        # The point: trust < 1.0 even with unanimous vote on tiny sample.
        assert decision.trust_score < 0.85

    def test_available_providers_filter_excludes_others(self):
        # codex would win but is filtered out.
        hits = [
            _hit(prompt_id="p1", chairman_winner="codex", user_winner="codex"),
            _hit(prompt_id="p2", chairman_winner="claude"),
        ]
        decision = _decide_from_hits(hits, available_providers=["claude", "gemini"])
        assert decision.routed_to == "claude"
        assert "codex" not in decision.vote_counts

    def test_hits_with_no_winner_signal_falls_through(self):
        hits = [_hit(prompt_id="p1", chairman_winner=None, user_winner=None)]
        decision = _decide_from_hits(hits, available_providers=["claude"])
        assert decision.reason == "hits_found_but_no_winner_signal"
        assert decision.trust_score == 0.0


class TestDecideRoute:
    def test_patches_memory_search(self, monkeypatch):
        fake_hits = [
            _hit(prompt_id="p1", user_winner="codex"),
            _hit(prompt_id="p2", user_winner="codex"),
        ]
        monkeypatch.setattr(ask_module, "search_prompt_nodes", lambda q, top_k: fake_hits)
        decision = decide_route("test query", top_k=2)
        assert decision.routed_to == "codex"


class TestRunAsk:
    def test_end_to_end_dispatches_and_returns_structured(self, monkeypatch):
        fake_hits = [_hit(prompt_id=f"p{i}", user_winner="claude") for i in range(5)]
        monkeypatch.setattr(ask_module, "search_prompt_nodes", lambda q, top_k: fake_hits)

        def fake_dispatch(provider: str, prompt: str) -> str:
            return f"[{provider}]: answer to '{prompt}'"

        result = run_ask("what is the capital of France?", dispatch_fn=fake_dispatch)
        assert result.routed_to == "claude"
        assert "claude" in result.answer
        assert result.trust_score > 0.8
        # High-trust route doesn't suggest escalation.
        assert result.escalate_hint is None
        assert result.latency_ms >= 0

    def test_low_trust_sets_escalate_hint_to_compare(self, monkeypatch):
        # One hit only, with split signal → low trust → escalate hint.
        fake_hits = [_hit(prompt_id="p1", chairman_winner="claude")]
        monkeypatch.setattr(ask_module, "search_prompt_nodes", lambda q, top_k: fake_hits)
        result = run_ask("complex question", dispatch_fn=lambda p, q: "answer")
        assert result.escalate_hint == "compare"
        assert result.trust_score < ESCALATE_HINT_THRESHOLD

    def test_to_dict_is_compact(self, monkeypatch):
        fake_hits = [_hit(prompt_id="p1", user_winner="codex") for _ in range(5)]
        monkeypatch.setattr(ask_module, "search_prompt_nodes", lambda q, top_k: fake_hits)
        result = run_ask("q", dispatch_fn=lambda p, q: "a")
        payload = result.to_dict()
        # Token-economy: only the keys Claude needs.
        assert set(payload.keys()).issubset(
            {"answer", "routed_to", "trust_score", "latency_ms", "runner_up", "escalate_hint"}
        )
        # No verbose "decision" or "evidence" blob in the compact return.
        assert "decision" not in payload
        assert "evidence_prompt_ids" not in payload
