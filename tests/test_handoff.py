"""Tests for the cross-provider handoff mechanism (task #119).

The handoff CLI + MCP tool is the killer-hook mechanism behind the
60-second launch-arc demo: ask Claude a complex question, hand off
mid-conversation to Gemini, watch the next model pick up the context.

These tests pin the load-bearing behaviors:
  - Prompt-building includes prior assistant text + frames continuity
  - Dispatch routes to the requested provider
  - Failure modes (no context / unknown provider / provider crash)
    return structured error rather than raising
  - The MCP tool returns ok=True on success and the response payload
    carries enough info for the agent to surface the wedge
"""
from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest


@pytest.fixture
def home(patch_trinity_home: Path) -> Path:
    return patch_trinity_home


def _make_node(*, text: str, provider: str, following: str = "", preceding: str = "", turn_idx: int = 0, ts: str = "2026-05-14T10:00:00"):
    """Build a PromptNode the way iter_prompt_nodes would yield."""
    from trinity_local.memory.schemas import PromptNode
    return PromptNode(
        id=f"node_{turn_idx}_{provider}",
        transcript_id=f"t_{provider}",
        provider=provider,
        source_path=f"/fake/{provider}.json",
        turn_index=turn_idx,
        text=text,
        embedding=None,
        created_at=ts,
        timestamp=ts,
        preceding_assistant_text=preceding,
        following_assistant_text=following,
        themes=[],
    )


class TestBuildHandoffPrompt:
    """The prompt rendering is the part the receiving model sees. If
    the frame doesn't establish 'continue this thread' explicitly, the
    model re-introduces itself and breaks the demo's illusion of
    continuity."""

    def test_includes_continuity_frame(self):
        from trinity_local.handoff import build_handoff_prompt
        nodes = [_make_node(text="What is X?", provider="claude", following="X is foo.")]
        prompt, _ = build_handoff_prompt(nodes)
        # The frame must explicitly tell the target it's continuing a
        # conversation another model started. Without this, demo breaks.
        assert "continuing a conversation" in prompt
        assert "don't re-introduce yourself" in prompt

    def test_renders_user_and_assistant_turns_with_provider_attribution(self):
        from trinity_local.handoff import build_handoff_prompt
        nodes = [_make_node(text="hello claude", provider="claude", following="Hi from claude.")]
        prompt, sources = build_handoff_prompt(nodes)
        assert "USER: hello claude" in prompt
        assert "ASSISTANT (claude): Hi from claude." in prompt
        # Source providers reported so the receiving model + the demo
        # surface know which provider's history was passed in.
        assert sources == ["claude"]

    def test_chronological_order_in_prompt(self):
        """iter_prompt_nodes yields most-recent-first, but the
        conversation log should be chronological so the model reads it
        forward like a real chat. Build a 3-turn input newest-first;
        the prompt should land them oldest-first."""
        from trinity_local.handoff import build_handoff_prompt
        nodes = [
            _make_node(text="turn3", provider="claude", following="r3", turn_idx=2, ts="2026-05-14T10:02:00"),
            _make_node(text="turn2", provider="claude", following="r2", turn_idx=1, ts="2026-05-14T10:01:00"),
            _make_node(text="turn1", provider="claude", following="r1", turn_idx=0, ts="2026-05-14T10:00:00"),
        ]
        prompt, _ = build_handoff_prompt(nodes)
        # turn1 should appear before turn3 in the rendered log
        assert prompt.index("turn1") < prompt.index("turn2") < prompt.index("turn3")

    def test_continuation_query_appended_at_end(self):
        from trinity_local.handoff import build_handoff_prompt
        nodes = [_make_node(text="prior", provider="claude", following="resp")]
        prompt, _ = build_handoff_prompt(nodes, continuation="what about Y?")
        # The continuation lands AFTER the prior log so the model
        # reads context first, then the new question.
        assert prompt.index("prior") < prompt.index("what about Y?")
        assert "The user now asks: what about Y?" in prompt

    def test_continuation_omitted_uses_continue_instruction(self):
        from trinity_local.handoff import build_handoff_prompt
        nodes = [_make_node(text="prior", provider="claude", following="resp")]
        prompt, _ = build_handoff_prompt(nodes)
        # Without an explicit continuation, instruct the model to
        # continue the thread naturally rather than asking "what would
        # you like me to do?" — that would break the demo.
        assert "Continue the conversation" in prompt

    def test_multiple_source_providers_deduplicated(self):
        from trinity_local.handoff import build_handoff_prompt
        nodes = [
            _make_node(text="ask claude", provider="claude", following="claude says"),
            _make_node(text="ask codex", provider="codex", following="codex says"),
            _make_node(text="ask claude again", provider="claude", following="claude again"),
        ]
        _, sources = build_handoff_prompt(nodes)
        # Distinct providers, preserving first-appearance order.
        assert sources == ["claude", "codex"]

    def test_gemini_target_gets_google_workspace_capability_hint(self):
        """Launch-arc #121 — Gemini-Google handoff. When the target is
        gemini, the prompt actively names Google Workspace tools so
        gemini's MCP-wired Gmail/Drive/Calendar lights up when the
        continuation question would benefit. Without this, gemini
        often answers from its own internal knowledge and the demo's
        "wait, it read my actual emails" moment never fires."""
        from trinity_local.handoff import build_handoff_prompt
        nodes = [_make_node(text="codebase question", provider="claude",
                            following="here is what claude said")]
        prompt, _ = build_handoff_prompt(
            nodes,
            continuation="what about recent emails on this?",
            target_provider="gemini",
        )
        # Soft-form hint (must say "if you have" so users without
        # google-workspace MCP wired don't get hallucinated tool calls):
        assert "Google Workspace" in prompt
        assert "Gmail" in prompt and "Calendar" in prompt
        # The differentiator framing — "capability not just opinion" —
        # is what makes the demo land. Don't drop it.
        assert "capability" in prompt.lower()

    def test_claude_target_gets_filesystem_capability_hint(self):
        """When handing off TO claude (e.g., from gemini back), claude's
        MCP-wired filesystem/code-exec tools are the differentiator."""
        from trinity_local.handoff import build_handoff_prompt
        nodes = [_make_node(text="email question", provider="gemini",
                            following="gemini said")]
        prompt, _ = build_handoff_prompt(nodes, target_provider="claude")
        assert "filesystem" in prompt.lower() or "MCP" in prompt
        assert "capability" in prompt.lower()

    def test_no_capability_hint_when_target_provider_omitted(self):
        """Backwards-compat: callers that don't pass target_provider get
        the original neutral prompt. The capability hint is opt-in
        because Trinity doesn't always know the target at prompt-build
        time (some tests build the prompt without a target)."""
        from trinity_local.handoff import build_handoff_prompt
        nodes = [_make_node(text="q", provider="claude", following="r")]
        prompt, _ = build_handoff_prompt(nodes)
        # No capability framing leaks in when target is unknown
        assert "Google Workspace" not in prompt
        assert "filesystem" not in prompt.lower()

    def test_unknown_target_provider_no_hint(self):
        """An unknown provider name (e.g., user added a new provider
        Trinity doesn't have a hint for) gets the neutral prompt. Don't
        hallucinate capabilities for unknown targets."""
        from trinity_local.handoff import build_handoff_prompt
        nodes = [_make_node(text="q", provider="claude", following="r")]
        prompt, _ = build_handoff_prompt(nodes, target_provider="grok-7")
        assert "Google Workspace" not in prompt
        assert "filesystem" not in prompt.lower()

    def test_capability_hint_precedes_prior_log(self):
        """The hint must land BEFORE the prior conversation log so the
        receiving model reads "use your tools" first, then the context.
        If it landed after the log, the model's already started
        synthesizing without the tool-use frame."""
        from trinity_local.handoff import build_handoff_prompt
        nodes = [_make_node(text="prior", provider="claude", following="resp")]
        prompt, _ = build_handoff_prompt(nodes, target_provider="gemini")
        assert prompt.index("Google Workspace") < prompt.index("Prior conversation log")


class TestRunHandoff:
    """The integration shape: pull context, dispatch, return result."""

    def _make_provider_config(self, name: str = "gemini") -> dict:
        from trinity_local.config import ProviderConfig
        return {
            name: ProviderConfig(
                name=name,
                type="cli",
                enabled=True,
                label=name.title(),
                command=["gemini"],  # fake binary; tests patch make_provider
                args=[],
                roles={"member"},
                task_types=set(),
                model="gemini-3-pro",
            )
        }

    def test_unknown_provider_returns_structured_error(self):
        from trinity_local.handoff import run_handoff
        configs = self._make_provider_config("gemini")
        result = run_handoff("nonexistent", configs)
        # Don't raise; return a HandoffResult with .error populated.
        # The CLI / MCP wrapper renders this; raising would crash both.
        assert result.error is not None
        assert "Unknown provider" in result.error
        assert "gemini" in result.error  # mentions the available ones

    def test_no_context_returns_structured_error(self, home):
        """Empty prompt index → can't build a handoff prompt. Should
        suggest the seeding fix rather than crash."""
        from trinity_local.handoff import run_handoff
        configs = self._make_provider_config()
        # patch_trinity_home → empty index → iter_prompt_nodes returns []
        result = run_handoff("gemini", configs)
        assert result.error is not None
        assert "No recent prompts" in result.error
        assert "seed-from-taste-terminal" in result.error  # actionable

    def test_dispatches_to_target_provider_with_threaded_prompt(self, home):
        """The full path: pull a node from disk, build prompt, dispatch,
        return response."""
        from trinity_local.handoff import run_handoff
        from trinity_local.memory.store import upsert_prompt_node

        upsert_prompt_node(_make_node(
            text="Explain monads",
            provider="claude",
            following="Monads are programmable semicolons.",
        ))

        # Mock the provider so the test doesn't shell out to a real CLI.
        captured_prompt = {}
        class FakeProvider:
            def run(self, prompt, cwd):
                captured_prompt["text"] = prompt
                from trinity_local.providers import ProviderResult
                return ProviderResult(
                    provider="gemini",
                    stdout="Continuing: monads also compose like ...",
                    stderr="",
                    returncode=0,
                    elapsed_seconds=1.2,
                )
        configs = self._make_provider_config()
        with patch("trinity_local.handoff.make_provider", lambda cfg: FakeProvider()):
            result = run_handoff("gemini", configs, num_turns=1)
        # Prompt the receiving model actually saw:
        assert "Explain monads" in captured_prompt["text"]
        assert "Monads are programmable semicolons" in captured_prompt["text"]
        # The continuity frame is the load-bearing demo bit:
        assert "continuing a conversation" in captured_prompt["text"]
        # Result shape:
        assert result.error is None
        assert result.target_provider == "gemini"
        assert result.target_model == "gemini-3-pro"
        assert result.context_turns == 1
        assert result.source_providers == ["claude"]
        assert "monads also compose" in result.response_text

    def test_provider_nonzero_exit_propagates_as_error(self, home):
        """Subprocess failure must surface as a structured error the
        CLI/MCP wrapper can render — silent zero-stdout would be the
        worst possible UX for a fresh-install demo."""
        from trinity_local.handoff import run_handoff
        from trinity_local.memory.store import upsert_prompt_node
        upsert_prompt_node(_make_node(text="prompt", provider="claude", following="response"))

        class FailingProvider:
            def run(self, prompt, cwd):
                from trinity_local.providers import ProviderResult
                return ProviderResult(
                    provider="gemini",
                    stdout="",
                    stderr="auth token expired",
                    returncode=1,
                    elapsed_seconds=0.1,
                )
        configs = self._make_provider_config()
        with patch("trinity_local.handoff.make_provider", lambda cfg: FailingProvider()):
            result = run_handoff("gemini", configs, num_turns=1)
        assert result.error is not None
        assert "exit 1" in result.error
        assert "auth token expired" in result.error


class TestHandoffMCPTool:
    """The MCP-tool exposure: agent calls handoff → response carries
    enough info for the agent to surface the demo to the user."""

    def test_handoff_tool_listed_in_mcp_surface(self):
        from trinity_local.mcp_server import handle_list_tools
        tools = asyncio.run(handle_list_tools())
        names = {t.name for t in tools}
        assert "handoff" in names, (
            f"handoff tool must be in the MCP surface. Found: {sorted(names)}"
        )

    def test_handoff_tool_description_explains_wedge(self):
        """The agent (Claude Code etc.) reads the tool description to
        decide when to call it. If the description doesn't tell the
        agent 'this is for cross-provider continuity', it won't ever
        suggest the handoff to the user. The description is GTM."""
        from trinity_local.mcp_server import handle_list_tools
        tools = asyncio.run(handle_list_tools())
        handoff_tool = next((t for t in tools if t.name == "handoff"), None)
        assert handoff_tool is not None
        desc = (handoff_tool.description or "").lower()
        # Wedge keywords the agent uses to decide when to fire.
        assert "cross-provider" in desc or "continuity" in desc
        # USE WHEN guidance — without this the agent rarely fires
        # voluntary tool calls.
        assert "use when" in desc
