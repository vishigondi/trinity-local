"""Parser tests for transcript exports — claude.ai / ChatGPT export /
Gemini Takeout HTML. Originally landed in test_seed.py alongside the
seed-from-taste-terminal CLI round-trip; renamed to test_ingest_parsers.py
when that CLI retired 2026-05-27 (see retired_names.py). The parsers
themselves (in trinity_local.ingest) survive — they're shared by
import-export and the in-process ingest paths."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from trinity_local.ingest import (
    iter_prompt_turns,
    parse_chatgpt_export,
    parse_claude_ai_export,
    parse_gemini_takeout_html,
)


# ---------------------------------------------------------------------------
# Claude.ai webapp export parser
# ---------------------------------------------------------------------------

CLAUDE_AI_FIXTURE = [
    {
        "uuid": "conv-001",
        "name": "Routing thoughts",
        "summary": "",
        "created_at": "2025-03-13T20:36:46Z",
        "updated_at": "2025-03-13T22:03:49Z",
        "chat_messages": [
            {
                "uuid": "msg-001",
                "text": "list the s&p 100 stocks by their CAPE valuation",
                "content": [{"type": "text", "text": "list the s&p 100 stocks by their CAPE valuation"}],
                "sender": "human",
                "created_at": "2025-03-13T20:36:46Z",
            },
            {
                "uuid": "msg-002",
                "text": "Here are the top 10 ranked by Shiller CAPE...",
                "content": [{"type": "text", "text": "Here are the top 10 ranked by Shiller CAPE..."}],
                "sender": None,
                "created_at": "2025-03-13T20:36:55Z",
            },
        ],
    },
    {
        "uuid": "conv-002",
        "name": "",
        "summary": "Quick question",
        "created_at": "2025-04-01T00:00:00Z",
        "updated_at": "2025-04-01T00:00:00Z",
        "chat_messages": [
            {
                "uuid": "msg-101",
                "text": "what is 2+2",
                "content": [{"type": "text", "text": "what is 2+2"}],
                "sender": "human",
                "created_at": "2025-04-01T00:00:00Z",
            },
        ],
    },
]


@pytest.fixture
def claude_ai_export(tmp_path: Path) -> Path:
    path = tmp_path / "conversations.json"
    path.write_text(json.dumps(CLAUDE_AI_FIXTURE), encoding="utf-8")
    return path


class TestClaudeAIParser:
    def test_yields_one_session_per_conversation(self, claude_ai_export: Path):
        sessions = list(parse_claude_ai_export(claude_ai_export))
        assert len(sessions) == 2
        assert sessions[0].provider == "claude_ai"
        assert sessions[0].session_id == "conv-001"
        assert sessions[0].title == "Routing thoughts"

    def test_messages_parsed_correctly(self, claude_ai_export: Path):
        session = next(iter(parse_claude_ai_export(claude_ai_export)))
        assert len(session.messages) == 2
        assert session.messages[0].role == "user"
        assert session.messages[0].text == "list the s&p 100 stocks by their CAPE valuation"
        assert session.messages[1].role == "assistant"

    def test_iter_prompt_turns_yields_user_only(self, claude_ai_export: Path):
        sessions = list(parse_claude_ai_export(claude_ai_export))
        turns_for_first = list(iter_prompt_turns(sessions[0]))
        assert len(turns_for_first) == 1
        assert turns_for_first[0].text == "list the s&p 100 stocks by their CAPE valuation"
        assert turns_for_first[0].following_assistant_text.startswith("Here are")
        assert turns_for_first[0].provider == "claude_ai"


# ---------------------------------------------------------------------------
# ChatGPT webapp export parser
# ---------------------------------------------------------------------------

CHATGPT_FIXTURE = [
    {
        "id": "conv-gpt-1",
        "conversation_id": "conv-gpt-1",
        "title": "Stripe webhook for SaaS",
        "create_time": 1700000000.0,
        "update_time": 1700000100.0,
        "default_model_slug": "gpt-4",
        "current_node": "n3",
        "mapping": {
            "n0": {"id": "n0", "parent": None, "children": ["n1"], "message": None},
            "n1": {
                "id": "n1",
                "parent": "n0",
                "children": ["n2"],
                "message": {
                    "author": {"role": "user"},
                    "content": {"content_type": "text", "parts": ["I have a SaaS app and need a Stripe webhook"]},
                    "create_time": 1700000000.0,
                    "metadata": {"model_slug": "gpt-4"},
                },
            },
            "n2": {
                "id": "n2",
                "parent": "n1",
                "children": ["n3"],
                "message": {
                    "author": {"role": "assistant"},
                    "content": {"content_type": "text", "parts": ["Here's how to wire it up..."]},
                    "create_time": 1700000050.0,
                    "metadata": {"model_slug": "gpt-4"},
                },
            },
            "n3": {
                "id": "n3",
                "parent": "n2",
                "children": [],
                "message": {
                    "author": {"role": "user"},
                    "content": {"content_type": "text", "parts": ["thanks!"]},
                    "create_time": 1700000100.0,
                    "metadata": {"model_slug": "gpt-4"},
                },
            },
        },
    },
]


@pytest.fixture
def chatgpt_export(tmp_path: Path) -> Path:
    path = tmp_path / "conversations-000.json"
    path.write_text(json.dumps(CHATGPT_FIXTURE), encoding="utf-8")
    return path


class TestChatGPTParser:
    def test_walks_tree_to_linear_order(self, chatgpt_export: Path):
        sessions = list(parse_chatgpt_export(chatgpt_export))
        assert len(sessions) == 1
        s = sessions[0]
        assert s.provider == "chatgpt"
        assert s.title == "Stripe webhook for SaaS"
        assert s.model == "gpt-4"
        # n1 (user) → n2 (assistant) → n3 (user)
        assert len(s.messages) == 3
        assert [m.role for m in s.messages] == ["user", "assistant", "user"]
        assert s.messages[0].text.startswith("I have a SaaS app")

    def test_iter_prompt_turns_excludes_assistant(self, chatgpt_export: Path):
        sessions = list(parse_chatgpt_export(chatgpt_export))
        turns = list(iter_prompt_turns(sessions[0]))
        assert len(turns) == 2  # two user turns
        assert turns[0].text.startswith("I have a SaaS app")
        assert turns[0].following_assistant_text.startswith("Here's how to wire")


# ---------------------------------------------------------------------------
# Gemini Takeout HTML parser
# ---------------------------------------------------------------------------

GEMINI_FIXTURE_HTML = """<html><body>
<div class="outer-cell mdl-cell mdl-cell--12-col mdl-shadow--2dp"><div class="mdl-grid"><div class="header-cell mdl-cell mdl-cell--12-col"><p class="mdl-typography--title">Gemini Apps<br></p></div><div class="content-cell mdl-cell mdl-cell--6-col mdl-typography--body-1">Prompted <a href="https://gemini.google.com/app/abc123">Which version of Gemini live are you?</a><br>Apr 12, 2026, 3:34:31 PM EDT<p>I am Gemini 2.5 Pro, the latest preview release.</p></div><div class="content-cell mdl-cell mdl-cell--6-col mdl-typography--body-1 mdl-typography--text-right"></div><div class="content-cell mdl-cell mdl-cell--12-col mdl-typography--caption"><b>Products:</b><br>&emsp;Gemini Apps</div></div></div>
<div class="outer-cell mdl-cell mdl-cell--12-col mdl-shadow--2dp"><div class="mdl-grid"><div class="header-cell mdl-cell mdl-cell--12-col"><p class="mdl-typography--title">Gemini Apps<br></p></div><div class="content-cell mdl-cell mdl-cell--6-col mdl-typography--body-1">Prompted <a href="https://gemini.google.com/app/def456">summarize this article</a><br>Apr 13, 2026, 9:12:00 AM PDT<p>Here is a summary of the article...</p></div><div class="content-cell mdl-cell mdl-cell--6-col mdl-typography--body-1 mdl-typography--text-right"></div><div class="content-cell mdl-cell mdl-cell--12-col mdl-typography--caption"><b>Products:</b><br>&emsp;Gemini Apps</div></div></div>
</body></html>"""


@pytest.fixture
def gemini_takeout_html(tmp_path: Path) -> Path:
    path = tmp_path / "MyActivity.html"
    path.write_text(GEMINI_FIXTURE_HTML, encoding="utf-8")
    return path


class TestGeminiTakeoutParser:
    def test_yields_one_session_per_outer_cell(self, gemini_takeout_html: Path):
        sessions = list(parse_gemini_takeout_html(gemini_takeout_html))
        assert len(sessions) == 2
        assert all(s.provider == "gemini" for s in sessions)

    def test_extracts_prompt_response_and_timestamp(self, gemini_takeout_html: Path):
        sessions = list(parse_gemini_takeout_html(gemini_takeout_html))
        s = sessions[0]
        assert len(s.messages) == 2
        assert s.messages[0].role == "user"
        assert "Which version of Gemini" in s.messages[0].text
        assert s.messages[1].role == "assistant"
        assert "Gemini 2.5 Pro" in s.messages[1].text
        # Timestamp parsed from "Apr 12, 2026, 3:34:31 PM EDT"
        assert s.started_at is not None
        assert s.started_at.startswith("2026-04-12")

    def test_iter_prompt_turns_for_takeout(self, gemini_takeout_html: Path):
        sessions = list(parse_gemini_takeout_html(gemini_takeout_html))
        turns = list(iter_prompt_turns(sessions[0]))
        assert len(turns) == 1
        assert "Which version" in turns[0].text


