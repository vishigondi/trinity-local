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
                "task_kind": "coding",
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
                "task_kind": "coding",
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
                "task_kind": "writing",
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
        """If chairman didn't emit a routing_label.task_type, use the council's task_kind."""
        from trinity_local.commands.replay import _aggregate_routing_table

        councils = [
            {
                "council_run_id": "c1",
                "task_kind": "general",
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
                "task_kind": "code_refactor",
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
                "task_kind": "writing",
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
        from trinity_local import portal_data
        from trinity_local.adapters import AdapterStatus
        from trinity_local.portal_page import write_portal_html
        from trinity_local.utils import now_iso

        monkeypatch.setattr(portal_data, "check_all_adapters", lambda: [
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
        from trinity_local import portal_data
        from trinity_local.adapters import AdapterStatus
        from trinity_local.portal_page import write_portal_html

        monkeypatch.setattr(portal_data, "check_all_adapters", lambda: [
            AdapterStatus(provider="claude", cli_name="claude", installed=True),
        ])

        path = write_portal_html(title="Launchpad")
        html = path.read_text(encoding="utf-8")
        assert "Run replay-history" in html
        assert "trinity-local replay-history" in html
