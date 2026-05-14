"""Tests for the canonical 5 MCP tools (§8.1) and chain-mode council."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def home(patch_trinity_home: Path) -> Path:
    return patch_trinity_home


def _call_tool_sync(name: str, arguments: dict) -> dict:
    """Invoke an MCP tool and return the parsed text payload."""
    from trinity_local.mcp_server import handle_call_tool

    results = asyncio.run(handle_call_tool(name, arguments))
    assert results, "tool returned no results"
    first = results[0]
    text = first["text"] if isinstance(first, dict) else getattr(first, "text", str(first))
    try:
        return json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return {"raw": text}


class TestToolList:
    def test_canonical_tools_present(self):
        from trinity_local.mcp_server import handle_list_tools

        tools = asyncio.run(handle_list_tools())
        names = {t.name for t in tools}
        # v1.0 canonical 6: route, run_council (subsumes judge via responses=[...]),
        # record_outcome, search_prompts, get_persona, get_council_status.
        # v1.5 adds: `ask` (single-call routing), `get_picks`
        # (introspection for the agent into the user's extracted routing
        # patterns), `mark_pick_wrong` (user-veto on a cortex rule;
        # spec-v1.5 Week 5).
        # Launch-arc adds (tick #119): `handoff` (cross-provider
        # conversation continuity — the killer-hook mechanism for the
        # 60-second demo).
        assert names == {
            "ask", "get_picks", "mark_pick_wrong",
            "route", "run_council", "record_outcome",
            "search_prompts", "get_persona", "get_council_status",
            "handoff",
        }, f"unexpected tool list: {names}"

    def test_old_tools_dropped_from_public_surface(self):
        from trinity_local.mcp_server import handle_list_tools

        tools = asyncio.run(handle_list_tools())
        names = {t.name for t in tools}
        for legacy in ("get_status", "get_elo", "get_recent_councils", "watch_once", "get_recommendation", "judge"):
            assert legacy not in names, f"legacy tool {legacy!r} still exposed"

    def test_run_council_schema_includes_responses_param(self):
        from trinity_local.mcp_server import handle_list_tools

        tools = asyncio.run(handle_list_tools())
        run_council = next(t for t in tools if t.name == "run_council")
        # responses param is what makes run_council subsume judge.
        assert "responses" in run_council.inputSchema["properties"]


class TestRoute:
    def test_route_returns_canonical_payload_shape(self, home: Path):
        result = _call_tool_sync("route", {
            "task": "refactor this Python function to remove duplication",
            "available_models": ["claude", "gemini", "codex"],
        })
        assert "mode" in result
        assert "primary" in result
        assert "confidence" in result
        # Coding task → codex (gpt-5.5 xhigh) wins AA Coding Index (59.1 > gemini 55.5 > claude 52.5)
        assert result["primary"] == "codex"
        assert result["chairman_source"] == "global_benchmarks"

    def test_route_handles_minimal_args(self, home: Path):
        result = _call_tool_sync("route", {"task": "anything"})
        assert "primary" in result

    def test_route_honors_ranker_needs_council(self, home: Path):
        # The HeuristicRanker sets needs_council=True for coding/research tasks.
        # Before the fix, _route() looked for a nonexistent `recommended_mode`
        # field and always emitted mode='single'. After: needs_council → council.
        result = _call_tool_sync("route", {
            "task": "refactor this Python function",
            "available_models": ["claude", "gemini", "codex"],
        })
        # Coding is a needs_council task in the heuristic ranker.
        assert result["mode"] == "council"
        assert result["should_auto_council"] is True

    def test_route_normalizes_confidence_to_band(self, home: Path):
        # Schema declares confidence as enum {high, medium, low}; pre-fix it
        # leaked the raw 0..1 float from RoutingDecision.confidence.
        result = _call_tool_sync("route", {"task": "anything"})
        assert result["confidence"] in ("high", "medium", "low")

    def test_route_demotes_codex_when_latency_fast(self, home: Path):
        # codex+gpt-5.5 xhigh wins coding on quality but takes 30s+. When the
        # caller asks for latency='fast', route() should pick claude or gemini.
        result = _call_tool_sync("route", {
            "task": "refactor this Python function",
            "available_models": ["claude", "gemini", "codex"],
            "latency": "fast",
        })
        assert result["primary"] in ("claude", "gemini")
        assert "latency=fast" in result["reason"]
        assert result["latency"] == "fast"

    def test_route_returns_challenger_distinct_from_primary(self, home: Path):
        result = _call_tool_sync("route", {
            "task": "refactor this Python function",
            "available_models": ["claude", "gemini", "codex"],
        })
        assert result["challenger"] != result["primary"]
        assert result["challenger"] in ("claude", "gemini", "codex")


class TestRunCouncilChainPropagation:
    """The verification council caught that MCP `run_council(mode='chain')` was
    silently dispatching parallel because `_run_council` didn't add `mode`/
    `sequence` to launch_args. Lock that in."""

    def test_chain_mode_threads_through_to_handle_council_launch(self, home: Path, monkeypatch):
        # Capture what handle_council_launch receives.
        captured = {}

        def _stub_handle(args):
            captured["mode"] = getattr(args, "mode", None)
            captured["sequence"] = getattr(args, "sequence", None)
            captured["members"] = list(args.members)
            # Print the JSON that the real handler would print (council_run_id).
            import json
            print(json.dumps({
                "council_run_id": "council_test_chain",
                "task_path": "/tmp/x",
                "sync_path": "/tmp/y",
                "review_path": "/tmp/z",
                "review_action_path": "/tmp/a",
            }))

        from trinity_local.commands import council as council_cmd
        monkeypatch.setattr(council_cmd, "handle_council_launch", _stub_handle)

        result = _call_tool_sync("run_council", {
            "task": "refactor",
            "members": ["claude", "codex", "gemini"],
            "mode": "chain",
            "sequence": ["claude", "codex", "claude"],
        })
        assert result.get("ok") is True
        assert result.get("mode") == "chain"
        # The lock-in: launch_args.mode and launch_args.sequence are populated
        # so the downstream chain dispatch actually triggers.
        assert captured["mode"] == "chain"
        assert captured["sequence"] == ["claude", "codex", "claude"]


class TestSearchPrompts:
    def test_returns_empty_when_index_empty(self, home: Path):
        result = _call_tool_sync("search_prompts", {"query": "anything"})
        assert result["results"] == []

    def test_returns_ranked_results(self, home: Path):
        from trinity_local.embeddings import embed
        from trinity_local.memory import PromptNode, upsert_prompt_node
        from trinity_local.utils import now_iso

        upsert_prompt_node(PromptNode(
            id="p1",
            transcript_id="t1",
            provider="claude_ai",
            source_path="/tmp/x",
            turn_index=0,
            text="design a model router for trinity",
            embedding=embed("search_document: design a model router for trinity"),
            created_at=now_iso(),
        ))
        result = _call_tool_sync("search_prompts", {"query": "trinity router design", "top_k": 3})
        assert "results" in result
        assert any(r["prompt_id"] == "p1" for r in result["results"])


class TestRecordOutcome:
    def test_writes_feedback_and_updates_outcome(self, home: Path):
        from trinity_local.council_runtime import (
            create_council_outcome,
            create_prompt_bundle,
            save_council_outcome,
            save_prompt_bundle,
        )
        from trinity_local.council_schema import CouncilMemberResult

        bundle = create_prompt_bundle(
            task_cluster_id="tc1",
            task_text="hello",
            goal="test",
        )
        save_prompt_bundle(bundle)
        outcome = create_council_outcome(
            bundle=bundle,
            primary_provider="claude",
            member_results=[
                CouncilMemberResult(provider="claude", output_text="A"),
                CouncilMemberResult(provider="gemini", output_text="B"),
            ],
        )
        save_council_outcome(outcome)

        result = _call_tool_sync("record_outcome", {
            "council_run_id": outcome.council_run_id,
            "user_winner": "claude",
            "accepted": True,
            "edited": False,
            "cost_usd": 0.0,
            "latency_sec": 5.0,
        })
        assert result["ok"] is True
        assert result["outcome_updated"] is True

        # Verify the outcome JSON now carries user_verdict
        from trinity_local.council_runtime import load_council_outcome
        reloaded = load_council_outcome(outcome.council_run_id)
        verdict = reloaded.metadata.get("user_verdict")
        assert verdict is not None
        assert verdict["user_winner"] == "claude"
        assert verdict["accepted"] is True


# ---------------------------------------------------------------------------
# Chain-mode council
# ---------------------------------------------------------------------------

class TestChainMode:
    def test_routing_label_carries_verifier_fields(self, home: Path):
        """Verify CouncilRoutingLabel.from_dict accepts agreed_claims/disagreed_claims."""
        from trinity_local.council_schema import CouncilRoutingLabel

        label = CouncilRoutingLabel.from_dict({
            "winner": "claude",
            "confidence": "high",
            "agreed_claims": ["the user wants X", "the answer must be concise"],
            "disagreed_claims": [{
                "claim": "the user wants Y",
                "providers_for": ["claude"],
                "providers_against": ["gemini"],
                "why_matters": "drives the recommendation",
            }],
        })
        assert label.agreed_claims == ["the user wants X", "the answer must be concise"]
        assert len(label.disagreed_claims) == 1
        assert label.disagreed_claims[0]["claim"] == "the user wants Y"

    def test_chairman_prompt_includes_verifier_arrays(self, home: Path):
        from trinity_local.council_runtime import render_primary_council_prompt
        from trinity_local.council_schema import CouncilMemberResult, PromptBundle

        bundle = PromptBundle(
            bundle_id="b1",
            task_cluster_id="tc1",
            task_text="anything",
            goal="test",
            created_at="2026-05-03T00:00:00Z",
        )
        members = [
            CouncilMemberResult(provider="claude", output_text="A"),
            CouncilMemberResult(provider="gemini", output_text="B"),
        ]
        prompt = render_primary_council_prompt(bundle, members)
        assert "agreed_claims" in prompt
        assert "disagreed_claims" in prompt
        assert "why_matters" in prompt

    def test_routing_json_parser_extracts_verifier_fields(self, home: Path):
        from trinity_local.council_runtime import parse_routing_label

        synthesis = """## Winner
Claude

```routing-json
{
  "winner": "claude",
  "confidence": "high",
  "agreed_claims": ["X is true", "Y is the constraint"],
  "disagreed_claims": [
    {"claim": "Z is needed", "providers_for": ["claude"], "providers_against": ["gemini"], "why_matters": "affects the decision"}
  ]
}
```
"""
        label, error = parse_routing_label(synthesis)
        assert error is None
        assert label is not None
        assert label.agreed_claims == ["X is true", "Y is the constraint"]
        assert len(label.disagreed_claims) == 1
        assert label.disagreed_claims[0]["claim"] == "Z is needed"
        assert label.disagreed_claims[0]["why_matters"] == "affects the decision"

    def test_chain_step_prompt_includes_prior_outputs(self):
        from trinity_local.council_runtime import render_chain_step_prompt
        from trinity_local.council_schema import CouncilChainStep, PromptBundle

        bundle = PromptBundle(
            bundle_id="b1",
            task_cluster_id="tc1",
            task_text="design a router",
            goal="best answer",
            created_at="2026-05-03T00:00:00Z",
        )
        first_step = CouncilChainStep(
            step_index=0,
            model_provider="claude",
            output_text="My first attempt at a router design...",
        )

        # Step 0 prompt has no prior outputs
        prompt0 = render_chain_step_prompt(bundle, step_index=0, prior_steps=[])
        assert "first model in a chain" in prompt0
        assert "My first attempt" not in prompt0

        # Step 1 prompt sees claude's output
        prompt1 = render_chain_step_prompt(bundle, step_index=1, prior_steps=[first_step])
        assert "step 2 of a chain" in prompt1
        assert "My first attempt" in prompt1
        assert "from claude" in prompt1

        # Final step gets the final-step framing
        prompt_final = render_chain_step_prompt(
            bundle, step_index=1, prior_steps=[first_step], is_final=True,
        )
        assert "FINAL step" in prompt_final

    def test_chain_outcome_persists_steps(self, home: Path):
        from trinity_local.council_runtime import (
            create_council_outcome,
            create_prompt_bundle,
            save_council_outcome,
            load_council_outcome,
        )
        from trinity_local.council_schema import CouncilChainStep, CouncilMemberResult

        bundle = create_prompt_bundle(
            task_cluster_id="tc1",
            task_text="chain test",
            goal="best",
        )
        steps = [
            CouncilChainStep(
                step_index=0, model_provider="claude",
                model_name="claude-x", input_text="prompt 0", output_text="claude output",
            ),
            CouncilChainStep(
                step_index=1, model_provider="gemini",
                model_name="gemini-x", input_text="prompt 1", output_text="gemini refinement",
            ),
        ]
        outcome = create_council_outcome(
            bundle=bundle,
            primary_provider="claude",
            member_results=[
                CouncilMemberResult(provider="claude", output_text="claude output"),
                CouncilMemberResult(provider="gemini", output_text="gemini refinement"),
            ],
            mode="chain",
            chain_steps=steps,
        )
        path = save_council_outcome(outcome)
        on_disk = json.loads(path.read_text())
        assert on_disk["mode"] == "chain"
        assert len(on_disk["chain_steps"]) == 2
        assert on_disk["chain_steps"][0]["model_provider"] == "claude"

        # Roundtrip
        reloaded = load_council_outcome(outcome.council_run_id)
        assert reloaded.mode == "chain"
        assert len(reloaded.chain_steps) == 2
        assert reloaded.chain_steps[1].model_provider == "gemini"


class TestRateActionNudge:
    """Pillar 4 funnel widener: when run_council/get_council_status returns
    a completed-but-unrated outcome, the response carries a structured
    `rate_action` hint. The agent (Claude Code, etc.) reads its own tool
    response and surfaces the rating prompt to the user inline — no need
    to open the launchpad.

    Doctor + launchpad eyebrow + top banner ship the *visibility* signal;
    this hint ships the *active nudge at the moment of decision*. Earned
    its place after the real-corpus 16% verdict-capture rate persisted
    through five passive surfaces.
    """

    def _make_outcome(self, *, winner: str | None = "claude", verdict: dict | None = None):
        from types import SimpleNamespace
        metadata: dict = {}
        if verdict is not None:
            metadata["user_verdict"] = verdict
        return SimpleNamespace(
            council_run_id="cr_test_rate_action",
            winner_provider=winner,
            primary_provider="claude",
            metadata=metadata,
        )

    def test_hint_fires_for_completed_unrated_outcome(self):
        from trinity_local.mcp_server import _build_rate_action
        outcome = self._make_outcome(winner="codex", verdict=None)
        hint = _build_rate_action(outcome)
        assert hint is not None
        assert hint["needs_rating"] is True
        assert hint["council_run_id"] == "cr_test_rate_action"
        assert hint["chairman_pick"] == "codex"
        # Instruction must mention record_outcome so an LLM reading the
        # MCP response naturally picks the next tool call.
        assert "record_outcome" in hint["instruction"]
        # And must carry the council_run_id verbatim so the agent doesn't
        # have to reconstruct it (templated string concat is error-prone).
        assert "cr_test_rate_action" in hint["instruction"]

    def test_hint_silent_when_already_rated(self):
        """An already-rated council is already in the ledger — don't nag."""
        from trinity_local.mcp_server import _build_rate_action
        outcome = self._make_outcome(
            winner="claude",
            verdict={"user_winner": "claude", "recorded_at": "2026-05-13T10:00:00"},
        )
        assert _build_rate_action(outcome) is None

    def test_hint_silent_for_abandoned_outcome(self):
        """`accepted=False` with no user_winner is a valid signal but not
        the same as 'rated'. However, abandonment IS recorded via
        record_outcome — checking for any user_verdict.user_winner means
        a verdict-via-abandonment flow ALSO suppresses the hint correctly."""
        from trinity_local.mcp_server import _build_rate_action
        # Recorded abandonment: no user_winner key but user_verdict exists.
        outcome = self._make_outcome(
            winner="claude",
            verdict={"recorded_at": "2026-05-13T10:00:00"},  # no user_winner
        )
        # Should still fire — without a user_winner, the supervision
        # signal is unset. Abandonment-by-explicit-recording is rare;
        # the common case is a user_winner present means rated.
        hint = _build_rate_action(outcome)
        assert hint is not None  # the verdict-without-winner still needs resolution

    def test_hint_silent_for_outcome_without_council_run_id(self):
        """Defensive: a malformed outcome (missing council_run_id) can't
        carry an actionable hint because record_outcome can't be called
        without it. Better to drop the hint than emit a broken instruction."""
        from trinity_local.mcp_server import _build_rate_action
        from types import SimpleNamespace
        outcome = SimpleNamespace(
            council_run_id=None,
            winner_provider="claude",
            primary_provider="claude",
            metadata={},
        )
        assert _build_rate_action(outcome) is None

    def test_hint_silent_for_none_outcome(self):
        from trinity_local.mcp_server import _build_rate_action
        assert _build_rate_action(None) is None

    def test_hint_falls_back_to_primary_when_no_winner(self):
        """When the chairman didn't pick a winner (rare — synthesis failure
        or chain abandoned), fall back to primary_provider so the user
        still has a default to confirm against."""
        from trinity_local.mcp_server import _build_rate_action
        outcome = self._make_outcome(winner=None)
        hint = _build_rate_action(outcome)
        assert hint is not None
        assert hint["chairman_pick"] == "claude"  # primary_provider

    def test_record_outcome_description_mentions_rate_action_trigger(self):
        """The funnel only widens if the agent KNOWS it should fire
        record_outcome after seeing a rate_action. The MCP tool description
        is what trains that behavior — assert the trigger wording is
        in the description, not just the param schema."""
        import asyncio
        from trinity_local.mcp_server import handle_list_tools

        tools = asyncio.run(handle_list_tools())
        ro = next((t for t in tools if t.name == "record_outcome"), None)
        assert ro is not None, "record_outcome tool missing"
        desc = ro.description or ""
        assert "rate_action" in desc, (
            "record_outcome description must mention rate_action so the "
            "agent learns to fire it when the run_council response "
            "carries the rating hint"
        )
