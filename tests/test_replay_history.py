"""Tests for v1 item 5: replay-history + personal routing table."""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def home(patch_trinity_home: Path) -> Path:
    return patch_trinity_home


def _make_node(id: str, text: str, **overrides):
    from trinity_local.embeddings import embed
    from trinity_local.memory import PromptNode
    from trinity_local.utils import now_iso

    base = dict(
        id=id,
        transcript_id=f"t-{id}",
        provider="claude",
        source_path=f"/tmp/{id}.jsonl",
        turn_index=0,
        text=text,
        embedding=embed(f"search_document: {text}"),
        created_at=now_iso(),
    )
    base.update(overrides)
    return PromptNode(**base)


class TestSelectCandidates:
    def test_returns_empty_when_index_empty(self, home: Path):
        from trinity_local.commands.replay import _select_candidates

        result = _select_candidates(limit=5, task_type_filter=None, source_filter=None, force=False)
        assert result == []

    def test_skips_already_evaluated_unless_force(self, home: Path):
        from trinity_local.commands.replay import _select_candidates
        from trinity_local.memory import upsert_prompt_node

        upsert_prompt_node(_make_node("p1", "refactor a function", council_run_ids=["c-1"]))
        upsert_prompt_node(_make_node("p2", "explain async io"))

        # Without force: p1 (has council) is skipped, only p2 returned
        result = _select_candidates(limit=5, task_type_filter=None, source_filter=None, force=False)
        ids = [n.id for n, _ in result]
        assert ids == ["p2"]

        # With force: both included
        result_forced = _select_candidates(limit=5, task_type_filter=None, source_filter=None, force=True)
        forced_ids = {n.id for n, _ in result_forced}
        assert forced_ids == {"p1", "p2"}

    def test_filters_by_task_type(self, home: Path):
        from trinity_local.commands.replay import _select_candidates
        from trinity_local.memory import upsert_prompt_node

        upsert_prompt_node(_make_node("p1", "refactor a function in this code"))
        upsert_prompt_node(_make_node("p2", "research stock market trends today"))

        result = _select_candidates(limit=5, task_type_filter="research", source_filter=None, force=False)
        kinds = {k for _, k in result}
        assert kinds == {"research"}

    def test_filters_by_source(self, home: Path):
        from trinity_local.commands.replay import _select_candidates
        from trinity_local.memory import upsert_prompt_node

        upsert_prompt_node(_make_node("p1", "design a router", provider="claude_ai"))
        upsert_prompt_node(_make_node("p2", "design a router", provider="chatgpt"))

        result = _select_candidates(limit=5, task_type_filter=None, source_filter="chatgpt", force=False)
        providers = {n.provider for n, _ in result}
        assert providers == {"chatgpt"}

    def test_orders_by_replay_value(self, home: Path):
        """High-uncertainty / high-theme prompts rank above low-importance ones."""
        from trinity_local.commands.replay import _select_candidates
        from trinity_local.memory import upsert_prompt_node
        from trinity_local.memory.replay_value import HIGH_VALUE_THEMES

        # Boring prompt
        upsert_prompt_node(_make_node("p_boring", "what time is it"))
        # Hot prompt: themed + uncertain
        themed = next(iter(HIGH_VALUE_THEMES))
        upsert_prompt_node(_make_node("p_hot", "design a model router", themes=[themed], importance=0.9))

        result = _select_candidates(limit=5, task_type_filter=None, source_filter=None, force=False)
        ids = [n.id for n, _ in result]
        # Themed + important node should rank first
        assert ids[0] == "p_hot"


class TestAggregateRoutingTable:
    def test_groups_by_task_type_and_picks_winner(self, home: Path):
        from trinity_local.commands.replay import _aggregate_routing_table

        councils = [
            {
                "council_run_id": "c1",
                "task_type": "coding",
                "routing_label": {
                    "task_type": "code_refactor",
                    "provider_scores": {
                        "claude": {"overall": 8.0},
                        "gemini": {"overall": 6.0},
                    },
                },
            },
            {
                "council_run_id": "c2",
                "task_type": "coding",
                "routing_label": {
                    "task_type": "code_refactor",
                    "provider_scores": {
                        "claude": {"overall": 9.0},
                        "gemini": {"overall": 5.0},
                    },
                },
            },
            {
                "council_run_id": "c3",
                "task_type": "writing",
                "routing_label": {
                    "task_type": "writing",
                    "provider_scores": {
                        "claude": {"overall": 7.0},
                        "gemini": {"overall": 8.5},
                    },
                },
            },
        ]
        table = _aggregate_routing_table(councils)
        assert table["councils_aggregated"] == 3
        # code_refactor: claude mean 8.5, gemini 5.5 -> claude wins
        assert table["best_per_task_type"]["code_refactor"] == "claude"
        assert table["by_task_type"]["code_refactor"]["claude"]["overall"] == 8.5
        assert table["by_task_type"]["code_refactor"]["claude"]["n"] == 2
        # writing: gemini wins
        assert table["best_per_task_type"]["writing"] == "gemini"

    def test_empty_input_returns_clean_shape(self, home: Path):
        from trinity_local.commands.replay import _aggregate_routing_table

        table = _aggregate_routing_table([])
        assert table["councils_aggregated"] == 0
        assert table["by_task_type"] == {}
        assert table["best_per_task_type"] == {}
        assert "computed_at" in table

    def test_falls_back_to_task_kind_when_routing_label_missing(self, home: Path):
        """If chairman didn't emit a routing_label.task_type, use the council's task_type."""
        from trinity_local.commands.replay import _aggregate_routing_table

        councils = [
            {
                "council_run_id": "c1",
                "task_type": "general",
                "routing_label": {"provider_scores": {"claude": {"overall": 7.0}}},
            },
        ]
        table = _aggregate_routing_table(councils)
        assert "general" in table["by_task_type"]

    def test_user_verdict_overrides_chairman_winner(self, home: Path):
        """User picked codex even though chairman scored claude higher —
        the personal routing table must credit codex, not claude. record_outcome
        is the most important tool; its signal must propagate."""
        from trinity_local.commands.replay import _aggregate_routing_table

        councils = [
            {
                "council_run_id": f"c{i}",
                "task_type": "code_refactor",
                "routing_label": {
                    "task_type": "code_refactor",
                    "provider_scores": {
                        "claude": {"overall": 8.0},  # chairman likes claude
                        "codex": {"overall": 6.0},
                    },
                },
                "user_winner": "codex",  # user disagreed, every time
            }
            for i in range(3)
        ]
        table = _aggregate_routing_table(councils)
        # codex should win despite chairman scoring it lower.
        assert table["best_per_task_type"]["code_refactor"] == "codex"

    def test_council_with_no_user_verdict_uses_chairman_scores_unchanged(self, home: Path):
        """Backward compat: councils without user_winner aggregate exactly
        as they did before the verdict-weighting change shipped."""
        from trinity_local.commands.replay import _aggregate_routing_table

        councils = [
            {
                "council_run_id": "c1",
                "task_type": "writing",
                "routing_label": {
                    "task_type": "writing",
                    "provider_scores": {
                        "claude": {"overall": 8.0},
                        "gemini": {"overall": 6.0},
                    },
                },
                # No user_winner key — chairman is the only signal.
            },
        ]
        table = _aggregate_routing_table(councils)
        assert table["by_task_type"]["writing"]["claude"]["overall"] == 8.0
        assert table["by_task_type"]["writing"]["gemini"]["overall"] == 6.0

    def test_mixed_user_verdicts_and_chairman_only_blend_correctly(self, home: Path):
        """Some councils have verdicts, others don't. Each contributes its
        own effective score and they get averaged into the same bucket."""
        from trinity_local.commands.replay import _aggregate_routing_table

        councils = [
            # No verdict — chairman scores pass through (claude=8, codex=6)
            {
                "council_run_id": "c1",
                "routing_label": {
                    "task_type": "system_design",
                    "provider_scores": {
                        "claude": {"overall": 8.0}, "codex": {"overall": 6.0},
                    },
                },
            },
            # User picked codex — codex gets boosted, claude gets penalized
            {
                "council_run_id": "c2",
                "routing_label": {
                    "task_type": "system_design",
                    "provider_scores": {
                        "claude": {"overall": 8.0}, "codex": {"overall": 6.0},
                    },
                },
                "user_winner": "codex",
            },
        ]
        table = _aggregate_routing_table(councils)
        # The user-verdict council credits codex with 0.7*10 + 0.3*6 = 8.8;
        # the chairman-only council leaves codex at 6.0. Mean ≈ 7.4.
        # Claude in the user-verdict council = 0.7*0 + 0.3*8 = 2.4; chairman-
        # only leaves it at 8.0. Mean ≈ 5.2.
        codex_mean = table["by_task_type"]["system_design"]["codex"]["overall"]
        claude_mean = table["by_task_type"]["system_design"]["claude"]["overall"]
        assert codex_mean > claude_mean, (
            f"codex (user-preferred) should outrank claude after a single verdict: "
            f"codex={codex_mean} vs claude={claude_mean}"
        )


class TestDryRun:
    def test_dry_run_lists_candidates_without_running_councils(self, home: Path, capsys, monkeypatch):
        from trinity_local.commands.replay import handle_replay_history
        from trinity_local.memory import upsert_prompt_node

        upsert_prompt_node(_make_node("p1", "research model routing approaches"))
        upsert_prompt_node(_make_node("p2", "design a verifier loop"))

        # Should never reach run_council in dry-run mode
        called = []
        monkeypatch.setattr(
            "trinity_local.commands.replay.run_council",
            lambda **kw: called.append(kw) or (_ for _ in ()).throw(RuntimeError("must not run")),
        )

        args = SimpleNamespace(
            limit=5, task_type=None, source=None, members=["claude", "gemini"],
            primary_provider=None, force=False, dry_run=True, cwd=".", quiet=True, config=None,
        )
        handle_replay_history(args)
        out = capsys.readouterr().out
        payload = json.loads(out)
        assert payload["dry_run"] is True
        assert payload["candidates"] == 2
        assert {p["prompt_id"] for p in payload["preview"]} == {"p1", "p2"}
        assert called == []


class TestRoundTripThroughCouncil:
    def test_aggregates_run_council_outcomes_into_personal_routing_table(self, home: Path, capsys, monkeypatch):
        """Mock run_council to emit deterministic Routing JSON; verify CLI output contains aggregation."""
        from trinity_local.commands import replay as replay_module
        from trinity_local.council_runner import CouncilRunResult
        from trinity_local.council_runtime import create_council_outcome
        from trinity_local.council_schema import (
            CouncilMemberResult,
            CouncilRoutingLabel,
            PromptBundle,
        )
        from trinity_local.memory import upsert_prompt_node

        upsert_prompt_node(_make_node("p1", "refactor this function"))
        upsert_prompt_node(_make_node("p2", "research market trends"))

        def fake_run_council(**kw):
            bundle: PromptBundle = kw["bundle"]
            label = CouncilRoutingLabel(
                winner="claude",
                runner_up="gemini",
                confidence="high",
                task_type=("code_refactor" if "refactor" in bundle.task_text else "research"),
                provider_scores={
                    "claude": {"overall": 8.5},
                    "gemini": {"overall": 6.2},
                },
            )
            outcome = create_council_outcome(
                bundle=bundle,
                primary_provider="claude",
                member_results=[
                    CouncilMemberResult(provider="claude", model="claude-x", output_text="..."),
                    CouncilMemberResult(provider="gemini", model="gemini-x", output_text="..."),
                ],
                primary_model="claude-x",
                winner_provider="claude",
                synthesis_output="memo body",
                routing_label=label,
            )
            return CouncilRunResult(
                outcome=outcome,
                outcome_path=Path("/tmp/x.json"),
                review_path=Path("/tmp/x.html"),
                launches=[],
            )

        monkeypatch.setattr(replay_module, "run_council", fake_run_council)
        # Skip config loading
        monkeypatch.setattr(replay_module, "load_config", lambda *a, **kw: SimpleNamespace(providers={}))

        args = SimpleNamespace(
            limit=5, task_type=None, source=None, members=["claude", "gemini"],
            primary_provider="claude", force=False, dry_run=False, cwd=".", quiet=True, config=None,
        )
        replay_module.handle_replay_history(args)
        out = capsys.readouterr().out
        payload = json.loads(out)
        assert payload["councils_run"] == 2
        # Aggregation now appears in the CLI output (no durable file written —
        # canonical personal table is computed on demand from council_outcomes/).
        assert payload["best_per_task_type"]["code_refactor"] == "claude"
        assert payload["best_per_task_type"]["research"] == "claude"
        # The personal_routing_table_path key is gone — file is no longer written
        assert "personal_routing_table_path" not in payload


class TestLaunchpadRendering:
    def test_card_appears_when_table_has_data(self, home: Path, monkeypatch):
        from trinity_local import launchpad_data
        from trinity_local.adapters import AdapterStatus
        from trinity_local.launchpad_page import write_portal_html
        from trinity_local.utils import now_iso

        monkeypatch.setattr(launchpad_data, "check_all_adapters", lambda: [
            AdapterStatus(provider="claude", cli_name="claude", installed=True),
            AdapterStatus(provider="gemini", cli_name="gemini", installed=True),
        ])

        # The launchpad reads via _load_personal_routing_table → compute_personal_routing_table.
        # Inject a synthetic table via monkeypatch so we don't have to seed real outcomes.
        from trinity_local import personal_routing
        monkeypatch.setattr(personal_routing, "compute_personal_routing_table", lambda: {
            "computed_at": now_iso(),
            "councils_aggregated": 5,
            "by_task_type": {"code_refactor": {"claude": {"overall": 8.5, "n": 5}}},
            "best_per_task_type": {"code_refactor": "claude"},
        })

        path = write_portal_html(title="Launchpad")
        html = path.read_text(encoding="utf-8")
        assert "Personal routing table" in html
        assert "personalRoutingTable" in html  # the v-if/data binding hooks

    def test_empty_state_card_shown_when_table_missing(self, home: Path, monkeypatch):
        from trinity_local import launchpad_data
        from trinity_local.adapters import AdapterStatus
        from trinity_local.launchpad_page import write_portal_html

        monkeypatch.setattr(launchpad_data, "check_all_adapters", lambda: [
            AdapterStatus(provider="claude", cli_name="claude", installed=True),
        ])

        path = write_portal_html(title="Launchpad")
        html = path.read_text(encoding="utf-8")
        assert "Run replay-history" in html
        assert "trinity-local replay-history" in html


class TestColdStartAugmentation:
    """The launchpad surfaces sigmoid-blend alpha per task_type (task #40).
    Without this, the personal routing card just shows aggregates with no
    signal about whether to trust them — the user can't tell whether their
    n=1 council is driving routing or being correctly down-weighted."""

    def test_cold_start_block_attached_per_task_type(self, home: Path, monkeypatch):
        from trinity_local import personal_routing, launchpad_data

        monkeypatch.setattr(personal_routing, "compute_personal_routing_table", lambda: {
            "councils_aggregated": 21,
            "by_task_type": {
                "code_refactor": {"claude": {"overall": 8.5, "n": 20}},
                "writing": {"claude": {"overall": 7.0, "n": 1}},
            },
            "best_per_task_type": {"code_refactor": "claude", "writing": "claude"},
        })

        table = launchpad_data._load_personal_routing_table()
        assert table is not None
        assert "cold_start" in table
        # n=20 saturates the sigmoid → ~100% personalized
        refactor = table["cold_start"]["code_refactor"]
        assert refactor["n_personal"] == 20
        assert refactor["personalization_pct"] >= 95
        # n=1 is well below the midpoint → mostly global
        writing = table["cold_start"]["writing"]
        assert writing["n_personal"] == 1
        assert writing["personalization_pct"] <= 15

    def test_personalization_pct_matches_chairman_picker_alpha(self, home: Path, monkeypatch):
        """The launchpad must use the SAME sigmoid the chairman picker uses.
        Without single-source-of-truth, the displayed % would mislead — user
        sees 60% on the card but the chairman is actually weighting at 30%."""
        from trinity_local import personal_routing, launchpad_data
        from trinity_local.ranker.chairman_picker import sigmoid_alpha

        monkeypatch.setattr(personal_routing, "compute_personal_routing_table", lambda: {
            "councils_aggregated": 5,
            "by_task_type": {
                "system_design": {"claude": {"overall": 7.5, "n": 5}},
            },
            "best_per_task_type": {"system_design": "claude"},
        })
        table = launchpad_data._load_personal_routing_table()
        # n=5 is the midpoint → alpha = 0.5 → 50%
        expected_alpha = sigmoid_alpha(5)
        assert table["cold_start"]["system_design"]["alpha"] == round(expected_alpha, 3)


class TestCortexRulesHealthSurface:
    """The launchpad cortex rules card shows a "Health" column derived from
    audit_status + bimodal_flag (the operational signals trust_score doesn't
    surface on its own)."""

    def test_audit_status_and_bimodal_flag_surfaced(self, home: Path):
        from trinity_local import cortex, launchpad_data

        pattern = cortex.RoutingPattern(
            basin_id="system_design",
            consolidated_at="2026-05-12T03:00:00Z",
            n_episodes=20,
            task_types=["system_design"],
            winner_distribution={"claude": 0.7, "codex": 0.3},
            routing_rule=cortex.RoutingRule(primary="claude", challenger="codex", reason="x", subroutes=[]),
            trust_score=cortex.TrustScore(
                value=0.75,
                components={
                    "n_episodes_norm": 0.8, "consistency_score": 0.7,
                    "recency_agreement": 0.7, "diversity": 0.7,
                    "coherence_score": 0.7, "audit_score": 1.0,
                },
            ),
            audit_status="disagreed",
            bimodal_flag=True,
        )
        cortex.save_routing_patterns({"system_design": pattern})

        surface = launchpad_data._load_cortex_rules()
        assert surface is not None
        assert len(surface["rules"]) == 1
        r = surface["rules"][0]
        # Both health signals must round-trip onto the launchpad surface
        # so the Vue template can render the Health column.
        assert r["audit_status"] == "disagreed"
        assert r["bimodal_flag"] is True

    def test_defaults_unaudited_and_not_bimodal_when_absent(self, home: Path):
        from trinity_local import cortex, launchpad_data

        # Save a pattern with the older shape (no audit_status / bimodal_flag).
        # Even though current dataclass defaults populate them, the surface
        # must tolerate older serialized files via getattr.
        pattern = cortex.RoutingPattern(
            basin_id="writing",
            consolidated_at="2026-05-12T03:00:00Z",
            n_episodes=5,
            task_types=["writing"],
            winner_distribution={"gemini": 1.0},
            routing_rule=cortex.RoutingRule(primary="gemini", challenger=None, reason="", subroutes=[]),
            trust_score=cortex.TrustScore(
                value=0.4,
                components={
                    "n_episodes_norm": 0.2, "consistency_score": 1.0,
                    "recency_agreement": 0.5, "diversity": 0.5,
                    "coherence_score": 0.5, "audit_score": 1.0,
                },
            ),
        )
        cortex.save_routing_patterns({"writing": pattern})

        surface = launchpad_data._load_cortex_rules()
        r = surface["rules"][0]
        assert r["audit_status"] == "unaudited"
        assert r["bimodal_flag"] is False

    def test_evidence_council_ids_surfaced_capped_at_five(self, home: Path):
        """Each rule should expose a small list of council_run_ids so the
        launchpad can render "View evidence" chips per spec-v1.5 Week 5."""
        from trinity_local import cortex, launchpad_data

        pattern = cortex.RoutingPattern(
            basin_id="system_design",
            consolidated_at="2026-05-12T04:00:00Z",
            n_episodes=20,
            task_types=["system_design"],
            winner_distribution={"claude": 0.6},
            routing_rule=cortex.RoutingRule(primary="claude", challenger=None, reason="", subroutes=[]),
            trust_score=cortex.TrustScore(
                value=0.6,
                components={
                    "n_episodes_norm": 0.8, "consistency_score": 0.6,
                    "recency_agreement": 0.6, "diversity": 0.5,
                    "coherence_score": 0.6, "audit_score": 1.0,
                },
            ),
            evidence=[f"council_{i:04d}" for i in range(15)],
        )
        cortex.save_routing_patterns({"system_design": pattern})

        surface = launchpad_data._load_cortex_rules()
        r = surface["rules"][0]
        # Cap at 5 — the launchpad only needs a peek; full set is in
        # ~/.trinity/council_outcomes/.
        assert len(r["evidence"]) == 5
        assert r["evidence"][0] == "council_0000"
        assert r["evidence"][4] == "council_0004"
