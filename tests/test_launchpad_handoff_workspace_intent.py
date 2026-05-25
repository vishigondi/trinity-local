"""launchpad: handoff-nudge workspace-intent detection (task #121 Phase 2).

When the recent prompts (last 5 nodes) mention calendar/email/drive/etc.,
the launchpad's handoff-nudge card should upgrade from the generic
"try the 60-second demo" to a Gemini-specific "hand off for inline
Workspace access" pitch. The capability hint in handoff.py is
always-on for antigravity targets; this surfaces the suggestion at
the point the user would benefit.

Pins both the data computation (_handoff_nudge returns workspace_intent
+ matched_keywords) and the template branching (workspace variant
vs generic variant).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def home(patch_trinity_home: Path) -> Path:
    return patch_trinity_home


def _write_prompt_node(home: Path, text: str, provider: str = "claude") -> None:
    """Append one user prompt to prompt_nodes.jsonl with the user_text
    that the workspace-intent detector scans."""
    from trinity_local.state_paths import prompts_dir
    p = prompts_dir() / "prompt_nodes.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    # PromptNode shape — pulls in the required fields from
    # memory/schemas.py:PromptNode. Empties for unused fields.
    payload = {
        "id": f"pn_{hash(text) & 0xffffff:06x}",
        "transcript_id": "test-transcript",
        "source_path": "/tmp/test-source",
        "provider": provider,
        "session_id": "test-session",
        "thread_id": "test-thread",
        "turn_index": 0,
        "occurred_at": "2026-05-25T16:00:00+00:00",
        "created_at": "2026-05-25T16:00:00+00:00",
        "text": text,
        "preceding_assistant_text": "",
        "following_assistant_text": "",
        "embedding": [],
    }
    with p.open("a") as fh:
        fh.write(json.dumps(payload) + "\n")


def _provider_config(name: str, *, enabled: bool = True):
    from trinity_local.config import ProviderConfig
    return ProviderConfig(
        name=name, type="cli", enabled=enabled, label=name.title(),
        command=[name], args=[], task_types=set(), model=f"{name}-model",
    )


def _make_config(provider_names: list[str]):
    """Build an AppConfig with the named providers all enabled."""
    from trinity_local.config import AppConfig
    providers = {n: _provider_config(n) for n in provider_names}
    return AppConfig(
        max_turns=4,
        notifications=True,
        providers=providers,
        task_preferences={},
    )


class TestWorkspaceIntentDetection:
    def test_calendar_keyword_triggers_workspace_intent(self, home, monkeypatch):
        from trinity_local import launchpad_data
        monkeypatch.setattr(launchpad_data, "load_config",
                            lambda required=False: _make_config(["claude", "antigravity"]))
        _write_prompt_node(home, "What's on my calendar this week?")
        nudge = launchpad_data._handoff_nudge()
        assert nudge["workspace_intent"] is True
        assert "calendar" in nudge["matched_keywords"]
        # Target gets switched to antigravity (the workspace-capable provider)
        assert nudge["target"] == "antigravity"

    def test_email_keyword_triggers(self, home, monkeypatch):
        from trinity_local import launchpad_data
        monkeypatch.setattr(launchpad_data, "load_config",
                            lambda required=False: _make_config(["claude", "antigravity"]))
        _write_prompt_node(home, "Did the legal team reply to my email yet?")
        nudge = launchpad_data._handoff_nudge()
        assert nudge["workspace_intent"] is True
        assert "email" in nudge["matched_keywords"]

    def test_drive_keyword_triggers(self, home, monkeypatch):
        from trinity_local import launchpad_data
        monkeypatch.setattr(launchpad_data, "load_config",
                            lambda required=False: _make_config(["claude", "antigravity"]))
        _write_prompt_node(home, "Find that doc I shared via Drive last quarter.")
        nudge = launchpad_data._handoff_nudge()
        assert nudge["workspace_intent"] is True
        assert "drive" in nudge["matched_keywords"]

    def test_no_workspace_keywords_keeps_generic_nudge(self, home, monkeypatch):
        from trinity_local import launchpad_data
        monkeypatch.setattr(launchpad_data, "load_config",
                            lambda required=False: _make_config(["claude", "antigravity"]))
        _write_prompt_node(home, "Refactor this function to use async/await.")
        nudge = launchpad_data._handoff_nudge()
        assert nudge["workspace_intent"] is False
        assert nudge["matched_keywords"] == []
        # Generic target selection preserved (non-claude preferred)
        assert nudge["target"] == "antigravity"

    def test_antigravity_not_enabled_keeps_generic_nudge(self, home, monkeypatch):
        """Without antigravity in the provider pool, the workspace
        upgrade can't fire — the wedge requires Gemini on the receiving
        end. Stay on the generic demo nudge instead."""
        from trinity_local import launchpad_data
        monkeypatch.setattr(launchpad_data, "load_config",
                            lambda required=False: _make_config(["claude", "codex"]))
        _write_prompt_node(home, "What's on my calendar this week?")
        nudge = launchpad_data._handoff_nudge()
        assert nudge["workspace_intent"] is False

    def test_matched_keywords_capped_at_three(self, home, monkeypatch):
        """Display ergonomics: even if the prompt mentions every trigger,
        only the first 3 appear in the inline copy."""
        from trinity_local import launchpad_data
        monkeypatch.setattr(launchpad_data, "load_config",
                            lambda required=False: _make_config(["claude", "antigravity"]))
        _write_prompt_node(home, "Check my calendar, my email, my drive, and the doc from Bob.")
        nudge = launchpad_data._handoff_nudge()
        assert nudge["workspace_intent"] is True
        assert len(nudge["matched_keywords"]) <= 3


class TestTemplateWorkspaceVariant:
    def test_workspace_variant_renders_when_flag_set(self):
        from trinity_local.launchpad_template import render_launchpad_html
        html = render_launchpad_html(
            page_data={
                "handoffNudge": {
                    "applicable": True,
                    "target": "antigravity",
                    "source_count": 5,
                    "workspace_intent": True,
                    "matched_keywords": ["calendar", "email"],
                },
            },
            recent_cards="",
        )
        # Vue v-if branches; both copy lines present in template source.
        assert "workspace_intent" in html
        # Workspace-themed eyebrow + headline
        assert "Gemini handoff" in html
        assert "Gmail, Drive, and Calendar" in html
        # Matched keywords surface in the message
        assert "matched_keywords.join" in html

    def test_generic_variant_still_present_in_template(self):
        """The v-else branch must remain — when workspace_intent=false
        the generic 60-second demo copy should render."""
        from trinity_local.launchpad_template import render_launchpad_html
        html = render_launchpad_html(
            page_data={
                "handoffNudge": {
                    "applicable": True,
                    "target": "antigravity",
                    "source_count": 5,
                    "workspace_intent": False,
                    "matched_keywords": [],
                },
            },
            recent_cards="",
        )
        # Generic copy line ("Hand off a conversation across models")
        # must be in the template so the v-else branch lights up.
        assert "Hand off a conversation across models" in html
