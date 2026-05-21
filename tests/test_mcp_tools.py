"""Tests for the 8 MCP tools (canonical 4 + v1.5 trio + launch-arc handoff) and chain-mode council.

Canonical 4: route, run_council (subsumes judge via responses=[...]),
get_persona, get_council_status. (record_outcome retired 2026-05-21.)
v1.5 trio: ask, get_picks, mark_pick_wrong.
Launch-arc: handoff (tick #119, cross-provider conversation continuity).
"""
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
        # Canonical 4: route, run_council (subsumes judge via responses=[...]),
        # get_persona, get_council_status.
        # v1.5 adds: `ask` (single-call routing), `get_picks`
        # (introspection for the agent into the user's extracted routing
        # patterns), `mark_pick_wrong` (user-veto on a cortex rule).
        # Launch-arc adds: `handoff` (cross-provider conversation continuity).
        # (`get_eval_summary` retired 2026-05-18 in commit `1fed7fc`;
        # `record_outcome` retired 2026-05-21 — chairman pick is the
        # supervision signal now, not user_winner verdicts.)
        assert names == {
            "ask", "get_picks", "mark_pick_wrong",
            "route", "run_council",
            "get_persona", "get_council_status",
            "handoff",
        }, f"unexpected tool list: {names}"

    def test_old_tools_dropped_from_public_surface(self):
        from trinity_local.mcp_server import handle_list_tools

        tools = asyncio.run(handle_list_tools())
        names = {t.name for t in tools}
        for legacy in (
            "get_status", "get_elo", "get_recent_councils", "watch_once",
            "get_recommendation", "judge",
            "record_outcome",  # retired 2026-05-21 (rating UX sunset)
        ):
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
            "available_models": ["claude", "antigravity", "codex"],
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
            "available_models": ["claude", "antigravity", "codex"],
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
        # caller asks for latency='fast', route() should pick claude or
        # antigravity (the post-rename fallback set; see mcp_server.py L819).
        result = _call_tool_sync("route", {
            "task": "refactor this Python function",
            "available_models": ["claude", "antigravity", "codex"],
            "latency": "fast",
        })
        assert result["primary"] in ("claude", "antigravity")
        assert "latency=fast" in result["reason"]
        assert result["latency"] == "fast"

    def test_route_returns_challenger_distinct_from_primary(self, home: Path):
        result = _call_tool_sync("route", {
            "task": "refactor this Python function",
            "available_models": ["claude", "antigravity", "codex"],
        })
        assert result["challenger"] != result["primary"]
        assert result["challenger"] in ("claude", "antigravity", "codex")


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
            "members": ["claude", "codex", "antigravity"],
            "mode": "chain",
            "sequence": ["claude", "codex", "claude"],
        })
        assert result.get("ok") is True
        assert result.get("mode") == "chain"
        # The lock-in: launch_args.mode and launch_args.sequence are populated
        # so the downstream chain dispatch actually triggers.
        assert captured["mode"] == "chain"
        assert captured["sequence"] == ["claude", "codex", "claude"]


# TestRecordOutcome class removed 2026-05-21. The record_outcome
# MCP tool was retired per "we are sunsetting user ratings. Full
# retirement including MCP." The chairman's pick (routing_label.winner)
# is the supervision signal now (compute_personal_routing_table reads
# it directly from council_outcomes/). CLI council-rate still works
# for power users; only the MCP surface is gone.


class TestGetCouncilStatus:
    """Same silent-failure shape audit as TestRecordOutcome —
    get_council_status used to swallow load_council_outcome
    exceptions and return `status: completed, outcome: null` with
    no signal of why the outcome was unreadable. The agent would
    show the user a half-rendered status. Now: outcome_load_error
    surfaces the cause."""

    def test_outcome_load_error_surfaces_when_outcome_file_corrupt(self, home: Path):
        from trinity_local.state_paths import council_outcomes_dir

        # Plant a council outcome file with corrupted (un-loadable) JSON
        # AND a matching status payload so the function takes the
        # "outcome_path.exists() so attempt load" branch.
        council_run_id = "council_corrupted_abc"
        outcome_path = council_outcomes_dir() / f"{council_run_id}.json"
        outcome_path.parent.mkdir(parents=True, exist_ok=True)
        outcome_path.write_text("{ this is not valid json ", encoding="utf-8")

        result = _call_tool_sync("get_council_status", {
            "council_run_id": council_run_id,
        })
        # The function still responds (didn't crash).
        # outcome_summary couldn't be built but the error reason is named.
        assert result.get("outcome") is None
        assert "outcome_load_error" in result, (
            "Silent failure regressed: load_council_outcome raised but "
            "the agent has no way to know the outcome JSON is corrupt"
        )
        # The error string mentions the exception class so the agent
        # can distinguish JSONDecodeError (file corrupt) from
        # FileNotFoundError (id wrong) etc.
        assert "Error" in result["outcome_load_error"] or "JSONDecodeError" in result["outcome_load_error"]


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
                "providers_against": ["antigravity"],
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
            CouncilMemberResult(provider="antigravity", output_text="B"),
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
    {"claim": "Z is needed", "providers_for": ["claude"], "providers_against": ["antigravity"], "why_matters": "affects the decision"}
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
                step_index=1, model_provider="antigravity",
                model_name="gemini-x", input_text="prompt 1", output_text="gemini refinement",
            ),
        ]
        outcome = create_council_outcome(
            bundle=bundle,
            primary_provider="claude",
            member_results=[
                CouncilMemberResult(provider="claude", output_text="claude output"),
                CouncilMemberResult(provider="antigravity", output_text="gemini refinement"),
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
        assert reloaded.chain_steps[1].model_provider == "antigravity"


# TestRateActionNudge + TestPendingRatingsHint removed 2026-05-21.
# The _build_rate_action and _pending_ratings_hint mechanism was
# retired in the same commit — agents no longer get a "go capture
# the verdict" hint embedded in MCP responses because the chairman
# pick IS the verdict (auto-recorded). Registry entries:
# `rate_action`, `pending_ratings` in retired_names.py.
