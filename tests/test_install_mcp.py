"""Tests for install-mcp targeting all three harnesses (Claude / Gemini / Codex)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def home(patch_trinity_home: Path) -> Path:
    return patch_trinity_home


def _run_install(monkeypatch, home_dir: Path, scope: str = "user"):
    from types import SimpleNamespace

    from trinity_local.commands.install import handle_install_mcp

    monkeypatch.setattr(Path, "home", lambda: home_dir)
    handle_install_mcp(SimpleNamespace(scope=scope))


class TestInstallMcp:
    def test_writes_claude_and_gemini_json_configs(self, home: Path, monkeypatch, capsys):
        _run_install(monkeypatch, home)

        claude_path = home / ".claude.json"
        gemini_path = home / ".gemini.json"
        assert claude_path.exists()
        assert gemini_path.exists()

        claude_cfg = json.loads(claude_path.read_text())
        assert "trinity-local" in claude_cfg["mcpServers"]
        assert claude_cfg["mcpServers"]["trinity-local"]["args"] == [
            "-m", "trinity_local.main", "--mcp",
        ]

    def test_writes_codex_toml_config(self, home: Path, monkeypatch, capsys):
        # Codex CLI uses ~/.codex/config.toml with [mcp_servers.<name>] sections.
        _run_install(monkeypatch, home)

        codex_path = home / ".codex" / "config.toml"
        assert codex_path.exists(), "install-mcp must write Codex CLI config too"
        content = codex_path.read_text()
        assert "[mcp_servers.trinity-local]" in content
        assert 'args = ["-m", "trinity_local.main", "--mcp"]' in content

    def test_codex_toml_preserves_existing_config(self, home: Path, monkeypatch, capsys):
        codex_path = home / ".codex" / "config.toml"
        codex_path.parent.mkdir(parents=True, exist_ok=True)
        codex_path.write_text(
            'model = "gpt-5.5"\n'
            'model_reasoning_effort = "xhigh"\n'
            '\n'
            '[projects."/Users/me/work"]\n'
            'trust_level = "trusted"\n'
        )

        _run_install(monkeypatch, home)

        content = codex_path.read_text()
        # User config preserved
        assert 'model = "gpt-5.5"' in content
        assert "[projects.\"/Users/me/work\"]" in content
        # Trinity MCP block appended
        assert "[mcp_servers.trinity-local]" in content

    def test_codex_toml_idempotent_no_duplicate_blocks(self, home: Path, monkeypatch, capsys):
        # Re-running install-mcp must replace the prior trinity block, not stack.
        _run_install(monkeypatch, home)
        _run_install(monkeypatch, home)

        codex_path = home / ".codex" / "config.toml"
        content = codex_path.read_text()
        assert content.count("[mcp_servers.trinity-local]") == 1

    def test_codex_toml_strips_quoted_and_nested_prior_blocks(self, home: Path, monkeypatch, capsys):
        # User config might already have [mcp_servers."trinity-local"] (some
        # toolchains generate the quoted form) or nested .env subtables.
        # Re-running install-mcp must clean those out, not pile on top.
        codex_path = home / ".codex" / "config.toml"
        codex_path.parent.mkdir(parents=True, exist_ok=True)
        codex_path.write_text(
            'model = "gpt-5.5"\n'
            '\n'
            '[mcp_servers."trinity-local"]\n'
            'command = "/old/python"\n'
            'args = ["-m", "trinity_local.main", "--mcp"]\n'
            '\n'
            '[mcp_servers."trinity-local".env]\n'
            'TRINITY_HOME = "/tmp/old"\n'
            '\n'
            '[mcp_servers.trinity-local.env]\n'
            'STALE = "true"\n'
        )
        _run_install(monkeypatch, home)

        content = codex_path.read_text()
        # Only the canonical (unquoted) section remains; old blocks gone.
        assert content.count("[mcp_servers.") == 1
        assert "/old/python" not in content
        assert "TRINITY_HOME" not in content
        assert "STALE" not in content
        assert 'model = "gpt-5.5"' in content  # unrelated config preserved

    def test_install_mcp_announces_all_three_targets(self, home: Path, monkeypatch, capsys):
        _run_install(monkeypatch, home)
        out = capsys.readouterr().out
        assert ".claude.json" in out
        assert ".gemini.json" in out
        assert "config.toml" in out
