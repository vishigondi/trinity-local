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


class TestPolishAutoIterateSetting:
    def test_default_is_off(self, tmp_path, monkeypatch):
        """Out of the box, polish auto-iterate must NOT fire — feature is
        explicitly opt-in so the user controls the multi-flagship cost."""
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        from trinity_local.telemetry import load_telemetry_settings
        settings = load_telemetry_settings()
        assert settings.polish_auto_iterate is False

    def test_cli_toggle_persists(self, tmp_path, monkeypatch, capsys):
        """polish-auto-enable / polish-auto-disable must round-trip
        through the on-disk settings file."""
        from trinity_local.commands.telemetry import (
            handle_polish_auto_enable, handle_polish_auto_disable,
        )
        from trinity_local.telemetry import load_telemetry_settings
        from types import SimpleNamespace

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        # Stub refresh_launchpad to avoid the full launchpad render.
        import trinity_local.commands.telemetry as telem_mod
        monkeypatch.setattr(telem_mod, "refresh_launchpad", lambda: tmp_path / "x.html")

        handle_polish_auto_enable(SimpleNamespace())
        assert load_telemetry_settings().polish_auto_iterate is True

        handle_polish_auto_disable(SimpleNamespace())
        assert load_telemetry_settings().polish_auto_iterate is False

    def test_council_launch_branches_on_polish_when_setting_on(self, tmp_path, monkeypatch):
        """When polish_auto_iterate=True, council-launch's auto-chain
        branch must fire FOR polish tasks AND NOT fire for non-polish.
        Tests the decision predicate directly — the full council-launch
        handler dispatches real provider CLIs."""
        from trinity_local.task_types import is_polish_task

        # The decision in council.py:
        #   should_auto_chain = bool(settings.auto_chain_enabled) or (
        #       bool(settings.polish_auto_iterate) and is_polish_task(bundle.task_text)
        #   )
        # Pin both branches.
        polish_text = "Make this tagline tighter — any better?"
        non_polish_text = "Pick a Redis vs Memcached for our session cache"

        assert is_polish_task(polish_text) is True
        assert is_polish_task(non_polish_text) is False

        # Simulate the branch:
        for auto_chain, polish_auto, task, expected in [
            (False, False, polish_text, False),        # both off → no fire
            (False, False, non_polish_text, False),    # both off → no fire
            (True,  False, polish_text, True),         # global on → fire
            (True,  False, non_polish_text, True),     # global on → fire
            (False, True,  polish_text, True),         # polish-only → fire (polish task)
            (False, True,  non_polish_text, False),    # polish-only → NO fire (not polish)
            (True,  True,  non_polish_text, True),     # both on, global wins
        ]:
            decision = bool(auto_chain) or (bool(polish_auto) and is_polish_task(task))
            assert decision is expected, (
                f"auto_chain={auto_chain}, polish_auto={polish_auto}, "
                f"task={task!r} → expected {expected}, got {decision}"
            )


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
