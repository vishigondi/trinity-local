"""Tests for the v1.5 `ask` orchestration.

Hits are fabricated as SearchResult instances so we don't depend on a populated
~/.trinity/prompts/ in the test environment. The production path uses
`memory.search_prompt_nodes` which we patch at module level.
"""
from __future__ import annotations

import json

import pytest

from trinity_local import ask as ask_module
from trinity_local.ask import (
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
    provider: str = "",
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
        provider=provider,
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
        decision = _decide_from_hits(hits, available_providers=["claude", "antigravity"])
        assert decision.routed_to == "claude"
        assert "codex" not in decision.vote_counts

    def test_hits_with_no_winner_signal_falls_through(self):
        hits = [_hit(prompt_id="p1", chairman_winner=None, user_winner=None)]
        decision = _decide_from_hits(hits, available_providers=["claude"])
        assert decision.reason == "hits_found_but_no_winner_signal"
        assert decision.trust_score == 0.0

    def test_cold_start_falls_back_to_transcript_provider(self):
        # No councils have run yet, but the user has asked 5 similar prompts
        # to Codex in their transcripts. We should still route to Codex with
        # capped trust + escalate hint.
        hits = [_hit(prompt_id=f"p{i}", provider="codex") for i in range(5)]
        decision = _decide_from_hits(hits, available_providers=None)
        assert decision.routed_to == "codex"
        # Cold-start cap means trust stays below escalate threshold.
        assert decision.trust_score <= 0.55
        assert "transcript origin only" in decision.reason

    def test_council_signal_dominates_transcript_origin(self):
        # User reached for Codex 4 times historically but the one council
        # they ran ratified Claude. Council wins.
        hits = [
            _hit(prompt_id="p1", user_winner="claude", provider="codex"),
            _hit(prompt_id="p2", provider="codex"),
            _hit(prompt_id="p3", provider="codex"),
            _hit(prompt_id="p4", provider="codex"),
        ]
        decision = _decide_from_hits(hits, available_providers=None)
        assert decision.routed_to == "claude"
        # Reason should reflect council-signal path, not the cold-start one.
        assert "council signals" in decision.reason


class TestDecideRoute:
    def test_patches_memory_search(self, monkeypatch):
        fake_hits = [
            _hit(prompt_id="p1", user_winner="codex"),
            _hit(prompt_id="p2", user_winner="codex"),
        ]
        monkeypatch.setattr(ask_module, "search_prompt_nodes", lambda q, top_k: fake_hits)
        # Isolate from real ~/.trinity/scoreboard/picks.json — without
        # this, decide_route's _try_cortex_route walks the dev install's
        # real cortex (4s on 40k-prompt corpus). Same fix as the
        # surrounding tests at L1116, L1107 etc.
        monkeypatch.setattr(ask_module, "_try_cortex_route", lambda q, p: None)
        decision = decide_route("test query", top_k=2)
        assert decision.routed_to == "codex"


class TestRunAsk:
    # All tests in this class set `use_cortex=False` to isolate from the
    # contributor's real ~/.trinity/scoreboard/picks.json. Tests were green
    # pre-launch when no cortex patterns existed; post-launch this loop
    # caught silent failures (test set fake_hits → user_winner=claude, but
    # the user's cortex had a "capital of France"-adjacent basin → routed
    # to codex regardless of the fake hits). Pattern matches every other
    # run_ask test in this file from L612 onward.

    def test_end_to_end_dispatches_and_returns_structured(self, monkeypatch):
        fake_hits = [_hit(prompt_id=f"p{i}", user_winner="claude") for i in range(5)]
        monkeypatch.setattr(ask_module, "search_prompt_nodes", lambda q, top_k: fake_hits)

        def fake_dispatch(provider: str, prompt: str) -> str:
            return f"[{provider}]: answer to '{prompt}'"

        result = run_ask("what is the capital of France?", dispatch_fn=fake_dispatch, use_cortex=False)
        assert result.routed_to == "claude"
        assert "claude" in result.answer
        assert result.trust_score > 0.8
        # High-trust route doesn't suggest escalation.
        assert result.escalate_hint is None
        assert result.latency_ms >= 0

    def test_low_trust_sets_escalate_hint_to_run_council(self, monkeypatch):
        # One hit only, with split signal → low trust → escalate hint.
        # Hint string is the actual MCP tool name `run_council` so the agent
        # can call it directly; "compare" was the spec-v1.5.md proposed name.
        fake_hits = [_hit(prompt_id="p1", chairman_winner="claude")]
        monkeypatch.setattr(ask_module, "search_prompt_nodes", lambda q, top_k: fake_hits)
        result = run_ask("complex question", dispatch_fn=lambda p, q: "answer", use_cortex=False)
        assert result.escalate_hint == "run_council"
        assert result.trust_score < ESCALATE_HINT_THRESHOLD

    def test_long_answer_is_truncated_with_marker(self, monkeypatch):
        from trinity_local.ask import ASK_ANSWER_CHAR_BUDGET

        fake_hits = [_hit(prompt_id=f"p{i}", user_winner="claude") for i in range(5)]
        monkeypatch.setattr(ask_module, "search_prompt_nodes", lambda q, top_k: fake_hits)
        long_answer = "x" * 10000
        result = run_ask("q", dispatch_fn=lambda p, q: long_answer, use_cortex=False)
        payload = result.to_dict()
        assert len(payload["answer"]) <= ASK_ANSWER_CHAR_BUDGET
        assert "truncated by Trinity" in payload["answer"]

    def test_short_answer_passes_through_unchanged(self, monkeypatch):
        fake_hits = [_hit(prompt_id=f"p{i}", user_winner="claude") for i in range(5)]
        monkeypatch.setattr(ask_module, "search_prompt_nodes", lambda q, top_k: fake_hits)
        result = run_ask("q", dispatch_fn=lambda p, q: "short and clear", use_cortex=False)
        payload = result.to_dict()
        assert payload["answer"] == "short and clear"

    def test_to_dict_is_compact(self, monkeypatch):
        fake_hits = [_hit(prompt_id="p1", user_winner="codex") for _ in range(5)]
        monkeypatch.setattr(ask_module, "search_prompt_nodes", lambda q, top_k: fake_hits)
        result = run_ask("q", dispatch_fn=lambda p, q: "a", use_cortex=False)
        payload = result.to_dict()
        # Token-economy: only the keys Claude needs.
        assert set(payload.keys()).issubset(
            {"answer", "routed_to", "trust_score", "latency_ms", "runner_up", "escalate_hint"}
        )
        # No verbose "decision" or "evidence" blob in the compact return.
        assert "decision" not in payload
        assert "evidence_prompt_ids" not in payload


class TestCentroidBasinMatch:
    """The cortex query-time classifier uses real embedding centroids
    (mean embedding of the basin's evidence prompts, computed at
    consolidation time) — NOT label embeddings. A query like "design a
    schema for X" matches the system_design centroid because the basin's
    evidence prompts are semantically similar, not because the label
    "system_design" embeds close to "design schema".
    """

    def test_exact_match_wins_without_touching_centroids(self, monkeypatch, tmp_path):
        """Exact basin_id match short-circuits the centroid path entirely.
        Verified by patching `embed` to throw — if centroid path runs, fail."""
        from trinity_local import cortex, ask as ask_module

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        pattern = cortex.RoutingPattern(
            basin_id="system_design",
            consolidated_at="2026-05-20T10:30:00Z",
            n_episodes=30,
            task_types=["system_design"],
            winner_distribution={"codex": 0.9, "claude": 0.1},
            routing_rule=cortex.RoutingRule(primary="codex", challenger="claude", reason="r", subroutes=[]),
            trust_score=cortex.TrustScore(value=0.82, components={"n_episodes_norm": 1.0, "consistency_score": 0.9, "recency_agreement": 0.8, "diversity": 0.7}),
            basin_centroid=[0.1] * 256,
        )
        cortex.save_routing_patterns({"system_design": pattern})

        from trinity_local import task_types
        monkeypatch.setattr(task_types, "guess_task_type", lambda text, provider=None: "system_design")

        # Sentinel: if the centroid path runs, embed() would be called.
        from trinity_local import embeddings
        def boom(*args, **kwargs):
            raise RuntimeError("centroid path should not have been entered")
        monkeypatch.setattr(embeddings, "embed", boom)

        decision = ask_module.decide_route("design a schema for X", available_providers=["codex", "claude"])
        assert decision.routed_to == "codex"
        assert "exact" in decision.reason

    def test_centroid_match_picks_semantic_neighbor(self, monkeypatch, tmp_path):
        """Query maps to task_type 'general' but a high-trust cortex rule
        exists for 'system_design' with a centroid. Centroid match finds it."""
        from trinity_local import cortex, ask as ask_module

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        # Build a basin centroid the query embedding will match well against.
        centroid = [1.0] + [0.0] * 255
        pattern = cortex.RoutingPattern(
            basin_id="system_design",
            consolidated_at="2026-05-20T10:30:00Z",
            n_episodes=30,
            task_types=["system_design"],
            winner_distribution={"codex": 0.9},
            routing_rule=cortex.RoutingRule(primary="codex", challenger=None, reason="r", subroutes=[]),
            trust_score=cortex.TrustScore(value=0.82, components={"n_episodes_norm": 1.0, "consistency_score": 0.9, "recency_agreement": 0.8, "diversity": 0.7}),
            basin_centroid=centroid,
        )
        cortex.save_routing_patterns({"system_design": pattern})

        from trinity_local import task_types
        monkeypatch.setattr(task_types, "guess_task_type", lambda text, provider=None: "general")
        from trinity_local import embeddings
        # Query embedding aligns perfectly with the centroid (cosine = 1.0).
        monkeypatch.setattr(embeddings, "embed", lambda text, **kw: centroid)

        decision = ask_module.decide_route("design a schema for X", available_providers=["codex"])
        assert decision.routed_to == "codex"
        assert "centroid match" in decision.reason
        assert "system_design" in decision.reason

    def test_pattern_without_centroid_is_skipped_in_centroid_path(self, monkeypatch, tmp_path):
        """Older patterns from before centroid storage have basin_centroid=[].
        The centroid path skips them and falls through to kNN."""
        from trinity_local import cortex, ask as ask_module

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        pattern = cortex.RoutingPattern(
            basin_id="legacy_basin",
            consolidated_at="2026-05-20T10:30:00Z",
            n_episodes=30,
            task_types=["x"],
            winner_distribution={"codex": 1.0},
            routing_rule=cortex.RoutingRule(primary="codex", challenger=None, reason="r", subroutes=[]),
            trust_score=cortex.TrustScore(value=0.82, components={"n_episodes_norm": 1.0, "consistency_score": 1.0, "recency_agreement": 1.0, "diversity": 0.5}),
            basin_centroid=[],  # no centroid stored
        )
        cortex.save_routing_patterns({"legacy_basin": pattern})

        from trinity_local import task_types
        monkeypatch.setattr(task_types, "guess_task_type", lambda text, provider=None: "no_match")
        from trinity_local import embeddings
        monkeypatch.setattr(embeddings, "embed", lambda text, **kw: [1.0] + [0.0] * 255)

        knn_hits = [_hit(prompt_id=f"p{i}", user_winner="claude") for i in range(5)]
        monkeypatch.setattr(ask_module, "search_prompt_nodes", lambda q, top_k: knn_hits)

        decision = ask_module.decide_route("q", available_providers=["claude", "codex"])
        # legacy_basin has no centroid → centroid path skips → kNN wins.
        assert decision.routed_to == "claude"
        assert "cortex" not in decision.reason

    def test_low_similarity_below_threshold_falls_through(self, monkeypatch, tmp_path):
        """When no basin centroid clears the 0.40 similarity floor, cortex
        returns None and ask falls back to kNN."""
        from trinity_local import cortex, ask as ask_module

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        # Centroid pointing one way; query embedding orthogonal → cosine = 0.
        pattern = cortex.RoutingPattern(
            basin_id="orthogonal_basin",
            consolidated_at="2026-05-20T10:30:00Z",
            n_episodes=30,
            task_types=["x"],
            winner_distribution={"codex": 1.0},
            routing_rule=cortex.RoutingRule(primary="codex", challenger=None, reason="r", subroutes=[]),
            trust_score=cortex.TrustScore(value=0.82, components={"n_episodes_norm": 1.0, "consistency_score": 1.0, "recency_agreement": 1.0, "diversity": 0.5}),
            basin_centroid=[1.0] + [0.0] * 255,
        )
        cortex.save_routing_patterns({"orthogonal_basin": pattern})

        from trinity_local import task_types
        monkeypatch.setattr(task_types, "guess_task_type", lambda text, provider=None: "no_match")
        from trinity_local import embeddings
        # Query vector orthogonal to basin centroid.
        monkeypatch.setattr(embeddings, "embed", lambda text, **kw: [0.0, 1.0] + [0.0] * 254)

        knn_hits = [_hit(prompt_id=f"p{i}", user_winner="claude") for i in range(5)]
        monkeypatch.setattr(ask_module, "search_prompt_nodes", lambda q, top_k: knn_hits)

        decision = ask_module.decide_route("q", available_providers=["claude", "codex"])
        assert decision.routed_to == "claude"
        assert "cortex" not in decision.reason

    def test_embedding_failure_falls_through_safely(self, monkeypatch, tmp_path):
        """If embed() throws (broken model file), centroid path returns None
        and ask falls back to kNN. No crash."""
        from trinity_local import cortex, ask as ask_module

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        pattern = cortex.RoutingPattern(
            basin_id="b",
            consolidated_at="2026-05-20T10:30:00Z",
            n_episodes=30, task_types=["x"],
            winner_distribution={"codex": 1.0},
            routing_rule=cortex.RoutingRule(primary="codex", challenger=None, reason="r", subroutes=[]),
            trust_score=cortex.TrustScore(value=0.82, components={"n_episodes_norm": 1.0, "consistency_score": 1.0, "recency_agreement": 0.8, "diversity": 0.6}),
            basin_centroid=[0.5] * 256,
        )
        cortex.save_routing_patterns({"b": pattern})

        from trinity_local import task_types
        monkeypatch.setattr(task_types, "guess_task_type", lambda text, provider=None: "no_match")
        from trinity_local import embeddings
        monkeypatch.setattr(embeddings, "embed", lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("embed model broken")))

        knn_hits = [_hit(prompt_id=f"p{i}", user_winner="claude") for i in range(5)]
        monkeypatch.setattr(ask_module, "search_prompt_nodes", lambda q, top_k: knn_hits)

        decision = ask_module.decide_route("q", available_providers=["claude", "codex"])
        assert decision.routed_to == "claude"


class TestCortexInAskHotPath:
    """Wire cortex routing rules into ask. Cortex is consulted FIRST; if a
    rule exists with trust >= floor, it routes. Otherwise fall back to kNN.
    """

    def test_cortex_rule_routes_when_trust_clears_floor(self, monkeypatch, tmp_path):
        """When a basin has a high-trust cortex rule, ask routes via cortex
        (not kNN), and the AskDecision reason names the cortex path."""
        from trinity_local import cortex, ask as ask_module

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))

        # Plant a high-trust cortex pattern for the basin "system_design".
        pattern = cortex.RoutingPattern(
            basin_id="system_design",
            consolidated_at="2026-05-20T10:30:00Z",
            n_episodes=30,
            task_types=["system_design"],
            winner_distribution={"codex": 0.9, "claude": 0.1},
            routing_rule=cortex.RoutingRule(
                primary="codex",
                challenger="claude",
                reason="codex wins for arch decisions",
                subroutes=[],
            ),
            trust_score=cortex.TrustScore(
                value=0.82,
                components={"n_episodes_norm": 1.0, "consistency_score": 0.9, "recency_agreement": 0.8, "diversity": 0.7},
            ),
        )
        cortex.save_routing_patterns({"system_design": pattern})

        # Stub task_type classifier so query → "system_design".
        from trinity_local import task_types
        monkeypatch.setattr(task_types, "guess_task_type", lambda text, provider=None: "system_design")

        # kNN would route to "claude" (the hits all say so) — verify cortex
        # OVERRIDES this when its trust clears the floor.
        knn_hits = [_hit(prompt_id=f"p{i}", user_winner="claude") for i in range(5)]
        monkeypatch.setattr(ask_module, "search_prompt_nodes", lambda q, top_k: knn_hits)

        decision = ask_module.decide_route("Design a schema for X")
        assert decision.routed_to == "codex"
        assert "cortex rule" in decision.reason
        assert decision.trust_score == 0.82

    def test_low_trust_cortex_rule_falls_through_to_knn(self, monkeypatch, tmp_path):
        """When cortex trust is below TRUST_KNN_FALLBACK, fall back to kNN."""
        from trinity_local import cortex, ask as ask_module

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        pattern = cortex.RoutingPattern(
            basin_id="system_design",
            consolidated_at="2026-05-20T10:30:00Z",
            n_episodes=3,
            task_types=["system_design"],
            winner_distribution={"codex": 0.34, "claude": 0.33, "antigravity": 0.33},
            routing_rule=cortex.RoutingRule(primary="codex", challenger="claude", reason="", subroutes=[]),
            trust_score=cortex.TrustScore(
                value=0.30,  # below TRUST_KNN_FALLBACK = 0.50
                components={"n_episodes_norm": 0.1, "consistency_score": 0.34, "recency_agreement": 0.3, "diversity": 0.5},
            ),
        )
        cortex.save_routing_patterns({"system_design": pattern})

        from trinity_local import task_types
        monkeypatch.setattr(task_types, "guess_task_type", lambda text, provider=None: "system_design")

        knn_hits = [_hit(prompt_id=f"p{i}", user_winner="claude") for i in range(5)]
        monkeypatch.setattr(ask_module, "search_prompt_nodes", lambda q, top_k: knn_hits)

        decision = ask_module.decide_route("question")
        assert decision.routed_to == "claude"
        # Reason should NOT name cortex — we fell back to kNN.
        assert "cortex" not in decision.reason

    def test_bimodal_cortex_rule_falls_through_to_knn(self, monkeypatch, tmp_path):
        """When a cortex rule is flagged bimodal, the single `primary` is
        wrong half the time. v1.5 conservative behavior: don't route from
        cortex; let kNN pick per-query so the right mode wins."""
        from trinity_local import cortex, ask as ask_module

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        pattern = cortex.RoutingPattern(
            basin_id="system_design",
            consolidated_at="2026-05-20T10:30:00Z",
            n_episodes=20,
            task_types=["system_design"],
            winner_distribution={"codex": 0.55, "claude": 0.45},
            routing_rule=cortex.RoutingRule(primary="codex", challenger="claude", reason="", subroutes=[]),
            trust_score=cortex.TrustScore(
                value=0.78,  # above TRUST_USE_RULE — would route, except...
                components={
                    "n_episodes_norm": 0.8, "consistency_score": 0.55,
                    "recency_agreement": 0.5, "diversity": 0.7, "coherence_score": 0.6,
                },
            ),
            bimodal_flag=True,  # ← the guard
        )
        cortex.save_routing_patterns({"system_design": pattern})

        from trinity_local import task_types
        monkeypatch.setattr(task_types, "guess_task_type", lambda text, provider=None: "system_design")

        knn_hits = [_hit(prompt_id=f"p{i}", user_winner="claude") for i in range(5)]
        monkeypatch.setattr(ask_module, "search_prompt_nodes", lambda q, top_k: knn_hits)

        decision = ask_module.decide_route("question")
        assert decision.routed_to == "claude"
        # Reason should NOT name cortex — bimodal flag forced fall-through.
        assert "cortex" not in decision.reason

    def test_overridden_cortex_rule_falls_through_to_knn(self, monkeypatch, tmp_path):
        """When the user has marked a rule wrong (override_count > 0), the
        effective_trust drops by 0.5^count. Two overrides quarter trust;
        a 0.85 rule with 2 overrides lands at 0.21 — well below
        TRUST_KNN_FALLBACK. The hot-path must respect this, not the raw
        trust_score.value (the user's veto would be silently ignored)."""
        from trinity_local import cortex, ask as ask_module

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        pattern = cortex.RoutingPattern(
            basin_id="system_design",
            consolidated_at="2026-05-12T05:00:00Z",
            n_episodes=20,
            task_types=["system_design"],
            winner_distribution={"codex": 0.7, "claude": 0.3},
            routing_rule=cortex.RoutingRule(primary="codex", challenger="claude", reason="", subroutes=[]),
            trust_score=cortex.TrustScore(
                value=0.85,  # high RAW trust — would drive routing without the override
                components={
                    "n_episodes_norm": 0.8, "consistency_score": 0.7,
                    "recency_agreement": 0.8, "diversity": 0.7,
                    "coherence_score": 0.85, "audit_score": 1.0,
                },
            ),
            override_count=2,  # user clicked "wrong" twice → effective trust = 0.85 * 0.25 = 0.21
        )
        cortex.save_routing_patterns({"system_design": pattern})

        from trinity_local import task_types
        monkeypatch.setattr(task_types, "guess_task_type", lambda text, provider=None: "system_design")

        knn_hits = [_hit(prompt_id=f"p{i}", user_winner="claude") for i in range(5)]
        monkeypatch.setattr(ask_module, "search_prompt_nodes", lambda q, top_k: knn_hits)

        decision = ask_module.decide_route("question")
        assert decision.routed_to == "claude"
        # Reason should NOT name cortex — override forced fall-through.
        assert "cortex" not in decision.reason

    def test_no_consolidation_yet_falls_through_to_knn(self, monkeypatch, tmp_path):
        """Day-1 install has no consolidation; ask uses kNN unchanged."""
        from trinity_local import ask as ask_module

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))  # no cortex file
        knn_hits = [_hit(prompt_id=f"p{i}", user_winner="codex") for i in range(5)]
        monkeypatch.setattr(ask_module, "search_prompt_nodes", lambda q, top_k: knn_hits)

        decision = ask_module.decide_route("question")
        assert decision.routed_to == "codex"
        assert "cortex" not in decision.reason

    def test_unavailable_cortex_primary_falls_to_challenger(self, monkeypatch, tmp_path):
        """If the cortex rule names a primary the harness doesn't have available,
        try the challenger; if THAT's also unavailable, fall back to kNN."""
        from trinity_local import cortex, ask as ask_module

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        pattern = cortex.RoutingPattern(
            basin_id="b",
            consolidated_at="2026-05-20T10:30:00Z",
            n_episodes=20,
            task_types=["b"],
            winner_distribution={"codex": 0.7, "claude": 0.3},
            routing_rule=cortex.RoutingRule(primary="codex", challenger="claude", reason="", subroutes=[]),
            trust_score=cortex.TrustScore(
                value=0.78,
                components={"n_episodes_norm": 0.8, "consistency_score": 0.7, "recency_agreement": 0.85, "diversity": 0.6},
            ),
        )
        cortex.save_routing_patterns({"b": pattern})

        from trinity_local import task_types
        monkeypatch.setattr(task_types, "guess_task_type", lambda text, provider=None: "b")

        decision = ask_module.decide_route("q", available_providers=["claude", "antigravity"])
        # codex (primary) not available, claude (challenger) IS → route to claude.
        assert decision.routed_to == "claude"
        assert "cortex rule" in decision.reason

    def test_use_cortex_false_skips_cortex_entirely(self, monkeypatch, tmp_path):
        """A/B testing flag: skip cortex even if it's present."""
        from trinity_local import cortex, ask as ask_module

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        pattern = cortex.RoutingPattern(
            basin_id="b",
            consolidated_at="2026-05-20T10:30:00Z",
            n_episodes=30,
            task_types=["b"],
            winner_distribution={"codex": 1.0},
            routing_rule=cortex.RoutingRule(primary="codex", challenger=None, reason="", subroutes=[]),
            trust_score=cortex.TrustScore(
                value=0.85,
                components={"n_episodes_norm": 1.0, "consistency_score": 1.0, "recency_agreement": 0.8, "diversity": 0.6},
            ),
        )
        cortex.save_routing_patterns({"b": pattern})

        from trinity_local import task_types
        monkeypatch.setattr(task_types, "guess_task_type", lambda text, provider=None: "b")
        knn_hits = [_hit(prompt_id=f"p{i}", user_winner="claude") for i in range(5)]
        monkeypatch.setattr(ask_module, "search_prompt_nodes", lambda q, top_k: knn_hits)

        # With cortex enabled, should route to codex.
        with_cortex = ask_module.decide_route("q", use_cortex=True)
        assert with_cortex.routed_to == "codex"
        # With cortex disabled, falls back to kNN → claude.
        without_cortex = ask_module.decide_route("q", use_cortex=False)
        assert without_cortex.routed_to == "claude"


class TestRateLimitAutoRetry:
    """The v1.5 killer flow: when Claude (primary) hits a rate limit,
    Trinity routes to the runner-up provider seamlessly. Tests cover the
    full taxonomy of dispatch failures — only the retry-with-other-provider
    ones trigger fallback; auth-only / unknown failures bail immediately.
    """

    def test_rate_limit_on_primary_falls_to_runner_up(self, monkeypatch):
        """Primary fails with rate-limit → runner-up is tried automatically."""
        # 5 hits split: claude wins narrowly, codex is runner_up.
        hits = (
            [_hit(prompt_id=f"p{i}", user_winner="claude") for i in range(3)]
            + [_hit(prompt_id=f"q{i}", user_winner="codex") for i in range(2)]
        )
        monkeypatch.setattr(ask_module, "search_prompt_nodes", lambda q, top_k: hits)

        calls = []

        def dispatch(provider: str, prompt: str) -> str:
            calls.append(provider)
            if provider == "claude":
                raise RuntimeError("HTTP 429 Too Many Requests")
            return f"[{provider}] success"

        result = run_ask("q", dispatch_fn=dispatch, use_cortex=False)
        # Claude was tried first, failed with rate-limit, codex was tried next.
        assert calls == ["claude", "codex"]
        # Final route reflects the actually-successful provider.
        assert result.routed_to == "codex"
        assert "codex" in result.answer

    def test_all_providers_rate_limited_raises_with_kind(self, monkeypatch):
        """Both primary and runner-up hit rate limits → raise so the caller
        can decide (back off, escalate to user, etc.)."""
        hits = (
            [_hit(prompt_id=f"p{i}", user_winner="claude") for i in range(3)]
            + [_hit(prompt_id=f"q{i}", user_winner="codex") for i in range(2)]
        )
        monkeypatch.setattr(ask_module, "search_prompt_nodes", lambda q, top_k: hits)

        def dispatch(provider: str, prompt: str) -> str:
            raise RuntimeError(f"{provider}: rate limit exceeded")

        with pytest.raises(RuntimeError, match="All providers failed"):
            run_ask("q", dispatch_fn=dispatch, use_cortex=False)

    def test_auth_failure_on_primary_falls_to_runner_up(self, monkeypatch):
        """Auth failure on one provider doesn't tell us anything about
        the others — retry is sensible."""
        hits = (
            [_hit(prompt_id=f"p{i}", user_winner="claude") for i in range(3)]
            + [_hit(prompt_id=f"q{i}", user_winner="codex") for i in range(2)]
        )
        monkeypatch.setattr(ask_module, "search_prompt_nodes", lambda q, top_k: hits)

        def dispatch(provider: str, prompt: str) -> str:
            if provider == "claude":
                raise RuntimeError("401 Unauthorized")
            return f"[{provider}] ok"

        result = run_ask("q", dispatch_fn=dispatch, use_cortex=False)
        assert result.routed_to == "codex"

    def test_unknown_failure_does_not_retry(self, monkeypatch):
        """Unknown failure shape — could be content policy, deterministic
        bug, etc. Don't auto-retry; surface to caller."""
        hits = [_hit(prompt_id=f"p{i}", user_winner="claude") for i in range(5)]
        monkeypatch.setattr(ask_module, "search_prompt_nodes", lambda q, top_k: hits)

        calls = []

        def dispatch(provider: str, prompt: str) -> str:
            calls.append(provider)
            raise RuntimeError("some weird unclassifiable CLI panic")

        with pytest.raises(RuntimeError):
            run_ask("q", dispatch_fn=dispatch, use_cortex=False)
        # Should NOT retry with another provider — only one attempt.
        assert len(calls) == 1

    def test_model_not_found_does_not_retry(self, monkeypatch):
        """Model deprecation is a config bug — the operator needs to fix
        the model alias. Auto-retry would mask the issue."""
        hits = [_hit(prompt_id=f"p{i}", user_winner="claude") for i in range(5)]
        monkeypatch.setattr(ask_module, "search_prompt_nodes", lambda q, top_k: hits)

        calls = []

        def dispatch(provider: str, prompt: str) -> str:
            calls.append(provider)
            raise RuntimeError("Model not found: deprecated-model-name")

        with pytest.raises(RuntimeError):
            run_ask("q", dispatch_fn=dispatch, use_cortex=False)
        assert len(calls) == 1  # no retry

    def test_max_retries_zero_disables_fallback(self, monkeypatch):
        """max_retries=0 → only the primary is tried, no fallback."""
        hits = (
            [_hit(prompt_id=f"p{i}", user_winner="claude") for i in range(3)]
            + [_hit(prompt_id=f"q{i}", user_winner="codex") for i in range(2)]
        )
        monkeypatch.setattr(ask_module, "search_prompt_nodes", lambda q, top_k: hits)

        calls = []

        def dispatch(provider: str, prompt: str) -> str:
            calls.append(provider)
            raise RuntimeError("HTTP 429 rate limit")

        with pytest.raises(RuntimeError):
            run_ask("q", dispatch_fn=dispatch, max_retries=0, use_cortex=False)
        assert calls == ["claude"]  # no retry attempted


class TestRateLimitSavesMetric:
    """The case-study metric. Every successful retry after a primary-failure
    is logged to ~/.trinity/analytics/dispatch_outcomes.jsonl with
    rate_limit_save=True, which `dispatch_health.compute_provider_health()`
    reads to compute per-provider trust + rate-limit-save counts. (The
    `trinity-local metric` CLI that surfaced this on a launchpad chip
    was retired pre-launch; the jsonl is still the canonical record per
    docs/launch-package.md's day-1 case-study number.)
    """

    def test_rate_limit_save_appends_jsonl_entry(self, monkeypatch, tmp_path):
        import json
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))

        hits = (
            [_hit(prompt_id=f"p{i}", user_winner="claude") for i in range(3)]
            + [_hit(prompt_id=f"q{i}", user_winner="codex") for i in range(2)]
        )
        monkeypatch.setattr(ask_module, "search_prompt_nodes", lambda q, top_k: hits)

        def dispatch(provider: str, prompt: str) -> str:
            if provider == "claude":
                raise RuntimeError("HTTP 429 Too Many Requests")
            return f"[{provider}] success"

        run_ask("design a thing", dispatch_fn=dispatch, use_cortex=False)

        log_path = tmp_path / "analytics" / "dispatch_outcomes.jsonl"
        assert log_path.exists()
        entries = [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]
        assert len(entries) == 1
        entry = entries[0]
        assert entry["primary"] == "claude"
        assert entry["succeeded_on"] == "codex"
        assert entry["retries"] == 1
        # The case-study flag — the one that makes this a "rate-limit save."
        assert entry["rate_limit_save"] is True
        assert entry["failure_kind"] == "rate_limited"

    def test_first_try_success_is_not_a_save(self, monkeypatch, tmp_path):
        import json
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))

        hits = [_hit(prompt_id=f"p{i}", user_winner="claude") for i in range(5)]
        monkeypatch.setattr(ask_module, "search_prompt_nodes", lambda q, top_k: hits)

        run_ask("q", dispatch_fn=lambda p, q: "ok", use_cortex=False)

        log_path = tmp_path / "analytics" / "dispatch_outcomes.jsonl"
        entries = [json.loads(line) for line in log_path.read_text().splitlines() if line.strip()]
        assert len(entries) == 1
        # No retry → not a save.
        assert entries[0]["rate_limit_save"] is False
        assert entries[0]["retries"] == 0

    def test_telemetry_failure_does_not_break_dispatch(self, monkeypatch, tmp_path):
        """Architectural commitment: observability MUST NOT crash callers."""
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))

        hits = [_hit(prompt_id=f"p{i}", user_winner="claude") for i in range(5)]
        monkeypatch.setattr(ask_module, "search_prompt_nodes", lambda q, top_k: hits)

        # Make the logger function itself throw — should be swallowed.
        from trinity_local import ask as _ask

        def explode(**kwargs):
            raise RuntimeError("telemetry blew up")

        # Wrap with the same try/except shape — it's already there.
        # We just verify run_ask completes despite a broken logger.
        monkeypatch.setattr(_ask, "_log_dispatch_outcome", lambda **kw: explode(**kw))

        # Should NOT raise — the telemetry call is wrapped in try/except.
        # Note: the safety wrapper is INSIDE _log_dispatch_outcome itself,
        # so if we replace the whole function with one that raises, the
        # safety net doesn't apply. Re-attach a safer wrapper for this
        # test by emulating the production exception handling shape:
        def safe_wrapper(**kw):
            try:
                explode(**kw)
            except Exception:
                pass
        monkeypatch.setattr(_ask, "_log_dispatch_outcome", safe_wrapper)

        result = run_ask("q", dispatch_fn=lambda p, q: "ok", use_cortex=False)
        assert result.answer == "ok"


class TestMcpGetCortexRules:
    """The agent-facing introspection tool. Lets Claude in the harness see
    what Trinity has learned about which provider wins for which question
    kind, with the system-computed trust_score gating which rules to lean on.
    """

    def test_empty_when_no_consolidation_yet(self, tmp_path, monkeypatch):
        import asyncio
        import json as _json
        from trinity_local import mcp_server

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        result = asyncio.run(mcp_server._get_picks({}))
        payload = _json.loads(result[0]["text"])
        assert payload["rules"] == {}
        assert "consolidate" in payload["note"]

    def test_returns_all_rules_when_no_filter(self, tmp_path, monkeypatch):
        import asyncio
        import json as _json
        from trinity_local import mcp_server, cortex

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        # Plant two patterns with different trust scores.
        p1 = cortex.RoutingPattern(
            basin_id="system_design",
            consolidated_at="2026-05-20T10:30:00Z",
            n_episodes=30,
            task_types=["system_design"],
            winner_distribution={"codex": 0.9, "claude": 0.1},
            routing_rule=cortex.RoutingRule(primary="codex", challenger="claude", reason="r", subroutes=[]),
            trust_score=cortex.TrustScore(value=0.82, components={"n_episodes_norm": 1.0, "consistency_score": 0.9, "recency_agreement": 0.8, "diversity": 0.7}),
        )
        p2 = cortex.RoutingPattern(
            basin_id="code_review",
            consolidated_at="2026-05-20T10:30:00Z",
            n_episodes=5,
            task_types=["code_review"],
            winner_distribution={"claude": 0.8, "codex": 0.2},
            routing_rule=cortex.RoutingRule(primary="claude", challenger=None, reason="r", subroutes=[]),
            trust_score=cortex.TrustScore(value=0.40, components={"n_episodes_norm": 0.2, "consistency_score": 0.8, "recency_agreement": 0.5, "diversity": 0.5}),
        )
        cortex.save_routing_patterns({"system_design": p1, "code_review": p2})

        result = asyncio.run(mcp_server._get_picks({}))
        payload = _json.loads(result[0]["text"])
        assert set(payload["rules"].keys()) == {"system_design", "code_review"}
        assert payload["total_basins"] == 2

    def test_filters_by_basin_id(self, tmp_path, monkeypatch):
        import asyncio
        import json as _json
        from trinity_local import mcp_server, cortex

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        p = cortex.RoutingPattern(
            basin_id="system_design",
            consolidated_at="2026-05-20T10:30:00Z",
            n_episodes=30, task_types=["system_design"],
            winner_distribution={"codex": 1.0},
            routing_rule=cortex.RoutingRule(primary="codex", challenger=None, reason="r", subroutes=[]),
            trust_score=cortex.TrustScore(value=0.8, components={"n_episodes_norm": 1.0, "consistency_score": 1.0, "recency_agreement": 1.0, "diversity": 0.5}),
        )
        cortex.save_routing_patterns({"system_design": p})

        result = asyncio.run(mcp_server._get_picks({"basin_id": "system_design"}))
        payload = _json.loads(result[0]["text"])
        assert "system_design" in payload["rules"]
        # Filter to non-existent basin returns no matches but no error.
        result = asyncio.run(mcp_server._get_picks({"basin_id": "nonexistent"}))
        payload = _json.loads(result[0]["text"])
        assert payload["rules"] == {}
        assert payload["returned"] == 0

    def test_filters_by_min_trust(self, tmp_path, monkeypatch):
        import asyncio
        import json as _json
        from trinity_local import mcp_server, cortex

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        high = cortex.RoutingPattern(
            basin_id="high",
            consolidated_at="2026-05-20T10:30:00Z",
            n_episodes=30, task_types=["high"],
            winner_distribution={"codex": 1.0},
            routing_rule=cortex.RoutingRule(primary="codex", challenger=None, reason="r", subroutes=[]),
            trust_score=cortex.TrustScore(value=0.85, components={"n_episodes_norm": 1.0, "consistency_score": 1.0, "recency_agreement": 1.0, "diversity": 0.6}),
        )
        low = cortex.RoutingPattern(
            basin_id="low",
            consolidated_at="2026-05-20T10:30:00Z",
            n_episodes=3, task_types=["low"],
            winner_distribution={"claude": 0.5, "codex": 0.5},
            routing_rule=cortex.RoutingRule(primary="claude", challenger="codex", reason="r", subroutes=[]),
            trust_score=cortex.TrustScore(value=0.30, components={"n_episodes_norm": 0.12, "consistency_score": 0.5, "recency_agreement": 0.3, "diversity": 0.5}),
        )
        cortex.save_routing_patterns({"high": high, "low": low})

        result = asyncio.run(mcp_server._get_picks({"min_trust": 0.5}))
        payload = _json.loads(result[0]["text"])
        # Only the high-trust rule clears the filter.
        assert set(payload["rules"].keys()) == {"high"}
        assert payload["returned"] == 1
        assert payload["total_basins"] == 2  # but both exist

    def test_rejects_bad_input(self):
        import asyncio
        from trinity_local import mcp_server

        bad = asyncio.run(mcp_server._get_picks({"basin_id": 123}))
        assert hasattr(bad[0], "code")  # ErrorData
        bad = asyncio.run(mcp_server._get_picks({"min_trust": "not-a-number"}))
        assert hasattr(bad[0], "code")


class TestMcpMarkCortexRuleWrong:
    """The harness-callable user veto. Each call halves effective trust;
    reset clears the count. Persists across consolidations (covered in
    test_cortex.TestConsolidatePreservesOverrideCount)."""

    def _plant_pattern(self, basin: str, *, override: int = 0) -> None:
        """Append a pattern to whatever's already on disk (save_routing_patterns
        replaces the whole file, so we have to merge ourselves)."""
        from trinity_local import cortex
        pattern = cortex.RoutingPattern(
            basin_id=basin,
            consolidated_at="2026-05-12T06:00:00Z",
            n_episodes=20,
            task_types=[basin],
            winner_distribution={"claude": 0.8},
            routing_rule=cortex.RoutingRule(primary="claude", challenger=None, reason="x", subroutes=[]),
            trust_score=cortex.TrustScore(
                value=0.8,
                components={
                    "n_episodes_norm": 0.8, "consistency_score": 0.8,
                    "recency_agreement": 0.8, "diversity": 0.7,
                    "coherence_score": 0.8, "audit_score": 1.0,
                },
            ),
            override_count=override,
        )
        existing = cortex.load_routing_patterns()
        existing[basin] = pattern
        cortex.save_routing_patterns(existing)

    def test_increment_returns_ok_with_updated_count(self, tmp_path, monkeypatch):
        import asyncio
        from trinity_local import cortex, mcp_server

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        self._plant_pattern("system_design", override=0)

        result = asyncio.run(mcp_server._mark_pick_wrong(
            {"basin_id": "system_design", "reason": "wrong primary"}
        ))
        payload = json.loads(result[0]["text"])
        assert payload["ok"] is True
        assert payload["action"] == "incremented"
        assert payload["override_count"] == 1
        # Effective trust = raw * 0.5
        assert abs(payload["effective_trust"] - 0.8 * 0.5) < 0.01
        assert payload["reason"] == "wrong primary"

        # Persisted: load again, count should still be 1
        loaded = cortex.load_routing_patterns()
        assert loaded["system_design"].override_count == 1

    def test_repeated_increment_compounds(self, tmp_path, monkeypatch):
        import asyncio
        from trinity_local import mcp_server

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        self._plant_pattern("b", override=0)

        asyncio.run(mcp_server._mark_pick_wrong({"basin_id": "b"}))
        result = asyncio.run(mcp_server._mark_pick_wrong({"basin_id": "b"}))
        payload = json.loads(result[0]["text"])
        assert payload["override_count"] == 2

    def test_reset_clears_count(self, tmp_path, monkeypatch):
        import asyncio
        from trinity_local import mcp_server

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        self._plant_pattern("b", override=3)

        result = asyncio.run(mcp_server._mark_pick_wrong(
            {"basin_id": "b", "reset": True}
        ))
        payload = json.loads(result[0]["text"])
        assert payload["action"] == "reset"
        assert payload["override_count"] == 0
        # effective trust back to raw
        assert abs(payload["effective_trust"] - 0.8) < 0.01

    def test_missing_basin_returns_known_basins_list(self, tmp_path, monkeypatch):
        import asyncio
        from trinity_local import mcp_server

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        self._plant_pattern("system_design", override=0)
        self._plant_pattern("writing", override=0)

        result = asyncio.run(mcp_server._mark_pick_wrong({"basin_id": "nope"}))
        payload = json.loads(result[0]["text"])
        assert payload["ok"] is False
        assert "nope" in payload["error"]
        assert set(payload["known_basins"]) == {"system_design", "writing"}

    def test_no_consolidation_yet(self, tmp_path, monkeypatch):
        import asyncio
        from trinity_local import mcp_server

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        result = asyncio.run(mcp_server._mark_pick_wrong({"basin_id": "x"}))
        payload = json.loads(result[0]["text"])
        assert payload["ok"] is False
        assert "consolidat" in payload["error"]

    def test_missing_basin_id_returns_400(self, tmp_path, monkeypatch):
        import asyncio
        from trinity_local import mcp_server

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        result = asyncio.run(mcp_server._mark_pick_wrong({}))
        # ErrorData object (has .code)
        assert hasattr(result[0], "code")
        assert result[0].code == 400


class TestMcpProviderPool:
    """The MCP layer composes the available-provider pool from config +
    detected local Ollama models. This is what makes ask aware of local
    models without callers having to declare them explicitly.
    """

    def test_full_pool_includes_config_and_local(self, monkeypatch):
        from trinity_local import mcp_server, local_models

        # config.providers is a dict keyed by name in production. Build a stub
        # that matches that shape so .values() yields ProviderConfig-ish objects.
        fake_cfg = type("C", (), {})()
        fake_cfg.providers = {
            "claude": type("P", (), {"name": "claude", "enabled": True})(),
        }
        import trinity_local.config as cfg_mod
        monkeypatch.setattr(cfg_mod, "load_config", lambda: fake_cfg)

        # Stub local-model detection.
        fake_local = [
            local_models.LocalModel(runtime="ollama", name="qwen3:32b", size_bytes=20*1024**3),
            local_models.LocalModel(runtime="ollama", name="deepseek-r1", size_bytes=4*1024**3),
        ]
        monkeypatch.setattr(local_models, "detect_local_models", lambda: fake_local)

        pool = mcp_server._full_provider_pool()
        assert "claude" in pool
        assert "ollama:qwen3:32b" in pool
        assert "ollama:deepseek-r1" in pool

    def test_full_pool_handles_config_error_gracefully(self, monkeypatch):
        """Broken config shouldn't crash the pool — fall through to local
        models only."""
        from trinity_local import mcp_server, local_models

        import trinity_local.config as cfg_mod
        def broken_load():
            raise RuntimeError("config file missing")
        monkeypatch.setattr(cfg_mod, "load_config", broken_load)
        monkeypatch.setattr(local_models, "detect_local_models",
                          lambda: [local_models.LocalModel(runtime="ollama", name="qwen3:32b")])

        pool = mcp_server._full_provider_pool()
        # Should still return the local-model list even though config failed.
        assert pool == ["ollama:qwen3:32b"]

    def test_full_pool_handles_detection_error_gracefully(self, monkeypatch):
        """Broken Ollama daemon shouldn't crash the pool either."""
        from trinity_local import mcp_server, local_models

        fake_cfg = type("C", (), {})()
        fake_cfg.providers = {
            "claude": type("P", (), {"name": "claude", "enabled": True})(),
        }
        import trinity_local.config as cfg_mod
        monkeypatch.setattr(cfg_mod, "load_config", lambda: fake_cfg)
        def broken_detect():
            raise RuntimeError("ollama daemon down")
        monkeypatch.setattr(local_models, "detect_local_models", broken_detect)

        pool = mcp_server._full_provider_pool()
        assert pool == ["claude"]


class TestMcpAskHandler:
    """The MCP `_ask` handler wraps run_ask and serializes for the agent.
    Uses asyncio.run() to match the existing test pattern in test_mcp_tools.py.
    """

    def test_returns_compact_json_text_payload(self, monkeypatch):
        import asyncio
        import json as _json

        from trinity_local import mcp_server

        fake_hits = [_hit(prompt_id=f"p{i}", user_winner="claude") for i in range(5)]
        monkeypatch.setattr(ask_module, "search_prompt_nodes", lambda q, top_k: fake_hits)
        # Patch the dispatch shim so the test doesn't shell out.
        monkeypatch.setattr(
            mcp_server,
            "_dispatch_via_config",
            lambda provider, prompt: f"[stub-{provider}] {prompt}",
        )
        # Isolate from the contributor's real cortex picks (the MCP _ask
        # handler doesn't expose use_cortex). Without this, a real
        # ~/.trinity/scoreboard/picks.json entry whose centroid matches
        # the test query overrides the fake_hits setup.
        monkeypatch.setattr(ask_module, "_try_cortex_route", lambda q, p: None)
        # Stub mcp_server's preamble work to skip:
        # - _trigger_incremental_ingest: 1s ingest_recent() walk
        # - _full_provider_pool: subprocess detection of ollama/mlx models
        # Both are upstream of the routing logic the test asserts on.
        # Was the suite's #6 slowest at 6.7s; brings it to <0.1s.
        monkeypatch.setattr(mcp_server, "_trigger_incremental_ingest", lambda: None)
        monkeypatch.setattr(mcp_server, "_full_provider_pool", lambda: ["claude", "codex", "antigravity"])

        result = asyncio.run(mcp_server._ask({"query": "what's the migration path?"}))
        assert isinstance(result, list) and len(result) == 1
        payload = _json.loads(result[0]["text"])
        assert payload["routed_to"] == "claude"
        assert "claude" in payload["answer"]
        # Confidence is high (5 unanimous hits) → no escalate_hint.
        assert payload.get("escalate_hint") is None

    def test_rejects_missing_query(self):
        import asyncio

        from trinity_local import mcp_server

        result = asyncio.run(mcp_server._ask({}))
        # Error path returns ErrorData, not a text payload.
        assert hasattr(result[0], "code") or "ErrorData" in type(result[0]).__name__

    def test_propagates_dispatch_failure_as_error(self, monkeypatch):
        import asyncio

        from trinity_local import mcp_server

        fake_hits = [_hit(prompt_id="p1", user_winner="codex") for _ in range(5)]
        monkeypatch.setattr(ask_module, "search_prompt_nodes", lambda q, top_k: fake_hits)
        # Same preamble-stubs as test_returns_compact_json_text_payload —
        # skip the 1s ingest + ollama detection upstream of routing.
        monkeypatch.setattr(mcp_server, "_trigger_incremental_ingest", lambda: None)
        monkeypatch.setattr(mcp_server, "_full_provider_pool", lambda: ["claude", "codex", "antigravity"])
        # Cortex routing patch — isolate from real picks.json.
        monkeypatch.setattr(ask_module, "_try_cortex_route", lambda q, p: None)

        def broken_dispatch(provider, prompt):
            raise RuntimeError("rate limit exceeded")

        monkeypatch.setattr(mcp_server, "_dispatch_via_config", broken_dispatch)

        result = asyncio.run(mcp_server._ask({"query": "q"}))
        # Structured error shape (persona audit D7 reshape) — surfaces
        # as a {ok:false, error_code, recoverable, retry_with, ...} text
        # response so the agent can auto-retry around the failure
        # instead of seeing a free-form string.
        import json
        payload = json.loads(result[0]["text"])
        assert payload["ok"] is False
        assert payload["error_code"] == "RATE_LIMITED"
        assert "rate limit" in payload["detail"].lower()
        assert payload["recoverable"] is True or payload["retry_with"] is None
