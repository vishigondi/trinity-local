"""Tests for v1 item 2: autofill UI wired to memory.search_prompt_nodes."""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def home(patch_trinity_home: Path) -> Path:
    return patch_trinity_home


class TestReplayCandidates:
    def test_falls_back_to_strings_when_memory_empty(self, home: Path):
        from trinity_local.launchpad_data import _load_replay_candidates

        result = _load_replay_candidates(limit=8)
        assert isinstance(result, list)
        # Empty memory → fallback returns hard-coded EXAMPLE_PROMPTS as strings
        assert all(isinstance(item, str) for item in result)
        assert len(result) > 0

    def test_returns_dicts_when_memory_populated(self, home: Path):
        from trinity_local.embeddings import embed
        from trinity_local.memory import PromptNode, upsert_prompt_node
        from trinity_local.launchpad_data import _load_replay_candidates
        from trinity_local.utils import now_iso

        upsert_prompt_node(PromptNode(
            id="p1",
            transcript_id="t1",
            provider="claude",
            source_path="/tmp/x",
            turn_index=0,
            text="design a model router for trinity",
            embedding=embed("search_document: design a model router for trinity"),
            created_at=now_iso(),
            user_winner="claude",
            council_run_ids=["c1"],
        ))
        upsert_prompt_node(PromptNode(
            id="p2",
            transcript_id="t1",
            provider="antigravity",
            source_path="/tmp/x",
            turn_index=1,
            text="write a launch announcement",
            embedding=embed("search_document: write a launch announcement"),
            created_at=now_iso(),
        ))

        result = _load_replay_candidates(limit=8)
        assert isinstance(result, list)
        assert len(result) >= 2
        first = result[0]
        assert isinstance(first, dict)
        assert "text" in first
        assert "reasons" in first
        assert "score" in first
        assert "council_count" in first
        assert "winner" in first
        assert "prompt_id" in first


class TestLaunchpadRenderWithAutofill:
    def test_template_renders_dict_suggestions_with_chips(self, home: Path, monkeypatch):
        """When the memory index is populated, the launchpad HTML should
        include the suggestion-chip / suggestion-winner UI structure."""
        from trinity_local.embeddings import embed
        from trinity_local.memory import PromptNode, upsert_prompt_node
        from trinity_local.utils import now_iso
        from trinity_local.launchpad_page import write_portal_html
        # Stub out the heavy adapter check to keep this test fast/deterministic
        from trinity_local import launchpad_data
        from trinity_local.adapters import AdapterStatus
        monkeypatch.setattr(
            launchpad_data,
            "check_all_adapters",
            lambda: [
                AdapterStatus(provider="claude", cli_name="claude", installed=True),
                AdapterStatus(provider="antigravity", cli_name="antigravity", installed=True),
                AdapterStatus(provider="codex", cli_name="codex", installed=True),
            ],
        )

        upsert_prompt_node(PromptNode(
            id="p1",
            transcript_id="t1",
            provider="claude",
            source_path="/tmp/x",
            turn_index=0,
            text="route a question to the right model",
            embedding=embed("search_document: route a question to the right model"),
            created_at=now_iso(),
            user_winner="claude",
            council_run_ids=["c1"],
        ))

        path = write_portal_html(title="Launchpad")
        html = path.read_text(encoding="utf-8")
        # Template contains the dict-aware helpers and the prior-thread preview.
        assert "suggestionText(suggestion)" in html
        assert "suggestionWinner(suggestion)" in html
        assert "suggestion-winner" in html
        assert "suggestion-thread" in html
        assert "suggestionPriorPreview" in html
