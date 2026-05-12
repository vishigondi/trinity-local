"""Tests for `is_polish_task` + its propagation through MCP `route()`.

A polish-shape task is one that asks for refinement of existing copy:
"make this better", "tighten this", "is this clearer?". The value of
detecting these is that consensus_round mode (iterative refinement)
shines on them — first pass catches the obvious, rounds 2-3 are where
the chairman crystallizes the line. Surfaced via `auto_iterate_recommended`
in route() output so harnesses can offer auto-iterate without us changing
default behavior.
"""
from __future__ import annotations

import json

import pytest


class TestIsPolishTask:
    def test_literal_polish_phrases_trigger(self):
        from trinity_local.task_types import is_polish_task
        for prompt in (
            "Make this better. Does it make sense?",
            "polish this email",
            "tighten this paragraph",
            "any better?",
            "is this clearer?",
            "is this stronger?",
            "Rewrite this for HN.",
            "Refine this opener — too long.",
        ):
            assert is_polish_task(prompt), f"should detect polish in: {prompt!r}"

    def test_short_imperative_hints_trigger(self):
        """≤20 words + a hint word should fire."""
        from trinity_local.task_types import is_polish_task
        for prompt in (
            "Shorter please.",
            "make it crisper",
            "needs to be punchier",
            "this should be simpler",
            "stronger verb here?",
        ):
            assert is_polish_task(prompt), f"should detect short polish hint: {prompt!r}"

    def test_long_task_with_hint_word_does_not_trigger(self):
        """A long technical task that happens to contain 'simpler' shouldn't
        get false-flagged as polish."""
        from trinity_local.task_types import is_polish_task
        long_prompt = (
            "I need to refactor this 800-line Python module that handles "
            "authentication tokens, expiration, refresh, and the cache layer. "
            "It's grown organically over six months and there are multiple "
            "places where the same logic appears in subtly different forms. "
            "Could you suggest a simpler architecture that consolidates the "
            "shared logic while preserving the existing public API?"
        )
        assert not is_polish_task(long_prompt), "long technical task ≠ polish"

    def test_non_polish_tasks_do_not_trigger(self):
        from trinity_local.task_types import is_polish_task
        for prompt in (
            "Should I use SQLite or DuckDB for analytics?",
            "Debug this stack trace.",
            "Write a unit test for the routing function.",
            "Compare Claude vs GPT-4 for legal research.",
            "",
        ):
            assert not is_polish_task(prompt), f"should NOT detect polish in: {prompt!r}"


class TestRouteSurfacesPolish:
    def test_route_includes_auto_iterate_recommended_true_for_polish(self, tmp_path, monkeypatch):
        """When route() is asked about a polish task, the payload's
        `auto_iterate_recommended` field must be True so harnesses + the
        launchpad can offer iteration."""
        import asyncio
        from trinity_local.mcp_server import _route

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        result = asyncio.run(_route({
            "task": "Make this tagline better. Any better?",
            "available_models": ["claude", "gemini", "codex"],
        }))
        payload = json.loads(result[0]["text"])
        assert payload.get("auto_iterate_recommended") is True

    def test_route_includes_auto_iterate_recommended_false_for_non_polish(self, tmp_path, monkeypatch):
        import asyncio
        from trinity_local.mcp_server import _route

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        result = asyncio.run(_route({
            "task": "Which model is best for legal research workflows?",
            "available_models": ["claude", "gemini", "codex"],
        }))
        payload = json.loads(result[0]["text"])
        assert payload.get("auto_iterate_recommended") is False
