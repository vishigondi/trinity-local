"""Tests for transcript ingestion parsers.

These are the highest-ROI tests in the project — the parsers are pure functions
that transform provider-specific JSON/JSONL into SessionRecord, and bugs here
propagate through the entire pipeline.
"""
from __future__ import annotations

import json
from pathlib import Path

from trinity_local.ingest import (
    _message_text,
    parse_claude_code_session,
    parse_codex_session,
    parse_cowork_session,
    parse_gemini_cli_session,
    iter_gemini_cli_sessions,
)


# ---------------------------------------------------------------------------
# _message_text helper
# ---------------------------------------------------------------------------

class TestMessageText:
    def test_plain_string(self):
        assert _message_text("hello") == "hello"

    def test_content_blocks(self):
        blocks = [
            {"type": "text", "text": "First part."},
            {"type": "text", "text": "Second part."},
        ]
        assert _message_text(blocks) == "First part.\nSecond part."

    def test_empty_blocks_skipped(self):
        blocks = [
            {"type": "text", "text": "Keep this"},
            {"type": "text", "text": ""},
            {"type": "image", "source": {}},
        ]
        assert _message_text(blocks) == "Keep this"

    def test_none_returns_empty(self):
        assert _message_text(None) == ""

    def test_int_returns_empty(self):
        assert _message_text(42) == ""


# ---------------------------------------------------------------------------
# Gemini CLI parser
# ---------------------------------------------------------------------------

class TestParseGeminiCLI:
    def test_minimal_session(self, gemini_session_file: Path):
        session = parse_gemini_cli_session(gemini_session_file)
        assert session is not None
        assert session.provider == "gemini"
        assert session.session_id == "gemini-test-001"
        assert session.model == "gemini-2.5-pro"
        assert session.started_at == "2026-04-01T12:00:00Z"
        assert session.ended_at == "2026-04-01T12:05:00Z"
        assert len(session.messages) == 2
        assert session.messages[0].role == "user"
        assert session.messages[1].role == "assistant"
        assert session.messages[1].model == "gemini-2.5-pro"

    def test_tool_calls_extracted(self, tmp_path: Path):
        from tests.conftest import GEMINI_SESSION_WITH_TOOLS
        path = tmp_path / "session-tools.json"
        path.write_text(json.dumps(GEMINI_SESSION_WITH_TOOLS), encoding="utf-8")
        session = parse_gemini_cli_session(path)
        assert session is not None
        # Second message (index 1) should have tool calls
        assistant_with_tools = session.messages[1]
        assert len(assistant_with_tools.tool_calls) == 1
        assert assistant_with_tools.tool_calls[0]["name"] == "list_directory"
        assert session.model == "gemini-2.5-flash"

    def test_invalid_json_returns_none(self, tmp_path: Path):
        path = tmp_path / "bad.json"
        path.write_text("not json", encoding="utf-8")
        assert parse_gemini_cli_session(path) is None

    def test_missing_session_id_returns_none(self, tmp_path: Path):
        path = tmp_path / "no-id.json"
        path.write_text(json.dumps({"messages": []}), encoding="utf-8")
        assert parse_gemini_cli_session(path) is None

    def test_iter_sessions(self, gemini_session_dir: Path):
        sessions = list(iter_gemini_cli_sessions(gemini_session_dir))
        assert len(sessions) == 2
        ids = {s.session_id for s in sessions}
        assert "gemini-test-001" in ids
        assert "gemini-test-002" in ids


# ---------------------------------------------------------------------------
# Claude Code parser
# ---------------------------------------------------------------------------

class TestParseClaudeCode:
    def test_basic_session(self, claude_session_file: Path):
        session = parse_claude_code_session(claude_session_file)
        assert session is not None
        assert session.provider == "claude"
        assert session.session_id == "test-session-123"
        assert session.model == "claude-sonnet-4-20250514"
        assert session.started_at == "2026-04-02T10:00:00Z"
        assert session.ended_at == "2026-04-02T10:00:10Z"
        assert session.cwd == "/Users/test/project"
        assert session.cli_version == "1.0.30"
        assert session.metadata["git_branch"] == "main"

    def test_messages_parsed(self, claude_session_file: Path):
        session = parse_claude_code_session(claude_session_file)
        assert session is not None
        assert len(session.messages) == 3
        user_msg = session.messages[0]
        assert user_msg.role == "user"
        assert user_msg.text == "Fix the authentication bug"

    def test_tool_calls_parsed(self, claude_session_file: Path):
        session = parse_claude_code_session(claude_session_file)
        assert session is not None
        assistant_msg = session.messages[1]
        assert len(assistant_msg.tool_calls) == 1
        assert assistant_msg.tool_calls[0]["name"] == "write_file"

    def test_tokens_parsed(self, claude_session_file: Path):
        session = parse_claude_code_session(claude_session_file)
        assert session is not None
        assistant_msg = session.messages[1]
        assert assistant_msg.tokens["input"] == 150
        assert assistant_msg.tokens["output"] == 80
        assert assistant_msg.tokens["cached"] == 50  # cache_read only

    def test_missing_file_returns_none(self):
        assert parse_claude_code_session(Path("/nonexistent/file.jsonl")) is None


# ---------------------------------------------------------------------------
# Codex parser
# ---------------------------------------------------------------------------

class TestParseCodex:
    def test_basic_session(self, codex_session_file: Path):
        session = parse_codex_session(codex_session_file)
        assert session is not None
        assert session.provider == "codex"
        assert session.session_id == "codex-session-001"
        assert session.model == "o3"
        assert session.cwd == "/Users/test/codex-project"
        assert session.cli_version == "0.3.2"
        assert session.metadata["model_provider"] == "openai"

    def test_messages_parsed(self, codex_session_file: Path):
        session = parse_codex_session(codex_session_file)
        assert session is not None
        # session_meta + turn_context don't produce messages, then user + assistant + function_call = 3
        roles = [m.role for m in session.messages]
        assert "user" in roles
        assert "assistant" in roles

    def test_function_call_parsed(self, codex_session_file: Path):
        session = parse_codex_session(codex_session_file)
        assert session is not None
        func_msg = [m for m in session.messages if m.tool_calls]
        assert len(func_msg) == 1
        assert func_msg[0].tool_calls[0]["name"] == "write_file"


# ---------------------------------------------------------------------------
# Cowork parser
# ---------------------------------------------------------------------------

class TestParseCowork:
    def test_basic_session(self, cowork_session_dir: Path):
        session = parse_cowork_session(cowork_session_dir)
        assert session is not None
        assert session.provider == "claude"
        assert session.session_id == "cowork-session-001"
        assert session.model == "claude-sonnet-4-20250514"
        assert session.title == "Research quantum computing"
        assert session.cwd == "/Users/test/cowork-project"

    def test_messages_parsed(self, cowork_session_dir: Path):
        session = parse_cowork_session(cowork_session_dir)
        assert session is not None
        assert len(session.messages) == 2
        assert session.messages[0].role == "user"
        assert session.messages[1].role == "assistant"

    def test_metadata_extracted(self, cowork_session_dir: Path):
        session = parse_cowork_session(cowork_session_dir)
        assert session is not None
        assert session.metadata["mcp_servers"] == ["puppeteer"]
        assert session.metadata["host_loop_mode"] == "agent"
        assert "/code" in session.metadata["slash_commands"]

    def test_missing_audit_returns_none(self, tmp_path: Path):
        """If audit.jsonl doesn't exist, return None."""
        meta_path = tmp_path / "local_no-audit.json"
        meta_path.write_text(json.dumps({"sessionId": "no-audit"}), encoding="utf-8")
        session_dir = tmp_path / "local_no-audit"
        session_dir.mkdir()
        # No audit.jsonl created
        assert parse_cowork_session(meta_path) is None

    def test_timestamps_extracted(self, cowork_session_dir: Path):
        """Cowork parser now extracts timestamps from audit JSONL entries."""
        session = parse_cowork_session(cowork_session_dir)
        assert session is not None
        assert session.started_at == "2026-04-04T09:00:00Z"
        assert session.ended_at == "2026-04-04T09:00:10Z"
