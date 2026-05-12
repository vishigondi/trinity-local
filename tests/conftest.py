"""Shared test fixtures for trinity-local."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest


@pytest.fixture
def tmp_state_dir(tmp_path: Path) -> Path:
    """Create a temporary state directory mimicking trinity-local's ~/.trinity/ layout."""
    state = tmp_path / "trinity_home"
    for sub in [
        "todos", "actions", "prompt_bundles", "council_outcomes",
        "task_sync", "portal_pages", "review_pages", "watcher",
    ]:
        (state / sub).mkdir(parents=True)
    return state


@pytest.fixture
def patch_trinity_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Patch TRINITY_HOME env var so all state goes to temp."""
    home = tmp_path / "trinity_home"
    home.mkdir(exist_ok=True)
    monkeypatch.setenv("TRINITY_HOME", str(home))
    return home


# ---------------------------------------------------------------------------
# Gemini CLI session fixtures
# ---------------------------------------------------------------------------

GEMINI_SESSION_MINIMAL: dict[str, Any] = {
    "sessionId": "gemini-test-001",
    "kind": "INTERACTIVE",
    "startTime": "2026-04-01T12:00:00Z",
    "lastUpdated": "2026-04-01T12:05:00Z",
    "messages": [
        {"type": "user", "content": "Explain Python generators", "timestamp": "2026-04-01T12:00:01Z"},
        {
            "type": "gemini",
            "content": "A generator is a special type of iterator...",
            "model": "gemini-2.5-pro",
            "timestamp": "2026-04-01T12:00:02Z",
            "tokens": {"input": 8, "output": 120},
        },
    ],
}

GEMINI_SESSION_WITH_TOOLS: dict[str, Any] = {
    "sessionId": "gemini-test-002",
    "kind": "INTERACTIVE",
    "startTime": "2026-04-01T13:00:00Z",
    "lastUpdated": "2026-04-01T13:10:00Z",
    "messages": [
        {"type": "user", "content": "List files in /tmp", "timestamp": "2026-04-01T13:00:01Z"},
        {
            "type": "gemini",
            "content": "Let me list the files for you.",
            "model": "gemini-2.5-flash",
            "timestamp": "2026-04-01T13:00:02Z",
            "toolCalls": [
                {"id": "tc1", "name": "list_directory", "args": {"path": "/tmp"}, "result": ["/tmp/foo"]},
            ],
        },
        {"type": "user", "content": "Thanks", "timestamp": "2026-04-01T13:00:03Z"},
        {
            "type": "gemini",
            "content": "You're welcome!",
            "model": "gemini-2.5-flash",
            "timestamp": "2026-04-01T13:00:04Z",
        },
    ],
}


@pytest.fixture
def gemini_session_file(tmp_path: Path) -> Path:
    """Write a minimal Gemini CLI session JSON file."""
    path = tmp_path / "session-gemini-001.json"
    path.write_text(json.dumps(GEMINI_SESSION_MINIMAL), encoding="utf-8")
    return path


@pytest.fixture
def gemini_session_dir(tmp_path: Path) -> Path:
    """Set up a Gemini CLI session directory tree."""
    project = tmp_path / "my-project" / "chats"
    project.mkdir(parents=True)
    (project / "session-001.json").write_text(
        json.dumps(GEMINI_SESSION_MINIMAL), encoding="utf-8"
    )
    (project / "session-002.json").write_text(
        json.dumps(GEMINI_SESSION_WITH_TOOLS), encoding="utf-8"
    )
    return tmp_path


# ---------------------------------------------------------------------------
# Claude Code session fixtures
# ---------------------------------------------------------------------------

CLAUDE_SESSION_LINES: list[dict[str, Any]] = [
    {
        "type": "user",
        "timestamp": "2026-04-02T10:00:00Z",
        "cwd": "/Users/test/project",
        "version": "1.0.30",
        "gitBranch": "main",
        "permissionMode": "auto",
        "message": {"content": "Fix the authentication bug"},
    },
    {
        "type": "assistant",
        "timestamp": "2026-04-02T10:00:05Z",
        "message": {
            "model": "claude-sonnet-4-20250514",
            "content": [
                {"type": "text", "text": "I'll fix the authentication bug."},
                {"type": "tool_use", "id": "tu1", "name": "write_file", "input": {"path": "auth.py", "content": "fixed"}},
            ],
            "usage": {
                "input_tokens": 150,
                "output_tokens": 80,
                "cache_read_input_tokens": 50,
                "cache_creation_input_tokens": 0,
            },
        },
    },
    {
        "type": "assistant",
        "timestamp": "2026-04-02T10:00:10Z",
        "message": {
            "model": "claude-sonnet-4-20250514",
            "content": "The authentication bug has been fixed.",
            "usage": {"input_tokens": 200, "output_tokens": 30},
        },
    },
]


@pytest.fixture
def claude_session_file(tmp_path: Path) -> Path:
    """Write a minimal Claude Code JSONL session file."""
    path = tmp_path / "test-session-123.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for entry in CLAUDE_SESSION_LINES:
            f.write(json.dumps(entry) + "\n")
    return path


# ---------------------------------------------------------------------------
# Codex session fixtures
# ---------------------------------------------------------------------------

CODEX_SESSION_LINES: list[dict[str, Any]] = [
    {
        "type": "session_meta",
        "timestamp": "2026-04-03T14:00:00Z",
        "payload": {
            "id": "codex-session-001",
            "cwd": "/Users/test/codex-project",
            "cli_version": "0.3.2",
            "model_provider": "openai",
        },
    },
    {
        "type": "turn_context",
        "timestamp": "2026-04-03T14:00:01Z",
        "payload": {"model": "o3"},
    },
    {
        "type": "response_item",
        "timestamp": "2026-04-03T14:00:02Z",
        "payload": {
            "type": "message",
            "role": "user",
            "content": "Write a test for the auth module",
        },
    },
    {
        "type": "response_item",
        "timestamp": "2026-04-03T14:00:05Z",
        "payload": {
            "type": "message",
            "role": "assistant",
            "content": "Here's a test for the auth module...",
        },
    },
    {
        "type": "response_item",
        "timestamp": "2026-04-03T14:00:06Z",
        "payload": {
            "type": "function_call",
            "call_id": "fc1",
            "name": "write_file",
            "arguments": '{"path": "test_auth.py", "content": "def test_login(): pass"}',
        },
    },
]


@pytest.fixture
def codex_session_file(tmp_path: Path) -> Path:
    """Write a minimal Codex JSONL session file."""
    path = tmp_path / "rollout-codex-001.jsonl"
    with path.open("w", encoding="utf-8") as f:
        for entry in CODEX_SESSION_LINES:
            f.write(json.dumps(entry) + "\n")
    return path


# ---------------------------------------------------------------------------
# Cowork session fixtures
# ---------------------------------------------------------------------------

COWORK_META: dict[str, Any] = {
    "sessionId": "cowork-session-001",
    "model": "claude-sonnet-4-20250514",
    "cwd": "/Users/test/cowork-project",
    "title": "Research quantum computing",
    "hostLoopMode": "agent",
    "processName": "Claude Desktop",
    "slashCommands": ["/code", "/search"],
    "remoteMcpServersConfig": [{"name": "puppeteer"}],
}

COWORK_AUDIT_LINES: list[dict[str, Any]] = [
    {
        "type": "user",
        "timestamp": "2026-04-04T09:00:00Z",
        "message": {"content": "Research quantum computing basics"},
    },
    {
        "type": "assistant",
        "timestamp": "2026-04-04T09:00:10Z",
        "message": {
            "model": "claude-sonnet-4-20250514",
            "content": "Quantum computing uses qubits...",
            "usage": {"input_tokens": 50, "output_tokens": 200},
        },
    },
]


@pytest.fixture
def cowork_session_dir(tmp_path: Path) -> Path:
    """Create a cowork session with metadata JSON and audit JSONL."""
    meta_path = tmp_path / "local_cowork-session-001.json"
    meta_path.write_text(json.dumps(COWORK_META), encoding="utf-8")
    session_dir = tmp_path / "local_cowork-session-001"
    session_dir.mkdir()
    audit_path = session_dir / "audit.jsonl"
    with audit_path.open("w", encoding="utf-8") as f:
        for entry in COWORK_AUDIT_LINES:
            f.write(json.dumps(entry) + "\n")
    return meta_path
