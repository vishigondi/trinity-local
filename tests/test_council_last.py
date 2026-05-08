"""Tests for `trinity-local council-last` — onboarding flow for new users.

Per council_35b2ae198a65b349: onboarding (c) — instant council on a recent
Claude Code prompt — beats (a)/(b)/(d). The hard rule (claude+codex against,
gemini for) was: NO clipboard auto-read on a privacy-positioned launch.
These tests pin: explicit --task path always works, --dry-run never fires
a council, missing-history surfaces a fix line.
"""

from __future__ import annotations


class TestExplicitTaskPath:
    def test_dry_run_with_task_does_not_call_subprocess(self, monkeypatch, capsys):
        # The privacy-safe path: user passes --task "..." rather than letting
        # Trinity auto-read anything. Dry-run mode should never invoke a council.
        from types import SimpleNamespace
        from trinity_local.commands.council_last import handle_council_last
        called = []

        def fake_call(cmd):
            called.append(cmd)
            return 0

        import subprocess
        monkeypatch.setattr(subprocess, "call", fake_call)

        args = SimpleNamespace(
            task="What's the right database for an analytics workload?",
            yes=False,
            members=["claude", "gemini", "codex"],
            dry_run=True,
        )
        rc = handle_council_last(args)
        assert rc == 0
        assert called == []  # dry-run never dispatches
        out = capsys.readouterr().out
        assert "analytics workload" in out


class TestMissingClaudeCodeHistory:
    def test_no_claude_dir_surfaces_fix_line(self, monkeypatch, tmp_path, capsys):
        # Fresh-install user has no ~/.claude/projects/ yet. council-last
        # must surface a concrete fix line, not just fail silently.
        from pathlib import Path
        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        from types import SimpleNamespace
        from trinity_local.commands.council_last import handle_council_last
        args = SimpleNamespace(
            task=None, yes=False,
            members=["claude", "gemini", "codex"],
            dry_run=False,
        )
        rc = handle_council_last(args)
        assert rc == 1
        out = capsys.readouterr().out
        assert "no Claude Code history" in out
        assert "--task" in out  # the fix path is named


class TestPromptDiscovery:
    def test_picks_most_recent_session_user_turn(self, tmp_path, monkeypatch):
        # Drop two synthetic Claude Code session JSONLs with different mtimes
        # and assert council-last picks the LAST user turn from the most
        # recently modified one.
        from pathlib import Path
        import json
        import os
        import time

        projects = tmp_path / ".claude" / "projects" / "myproject"
        projects.mkdir(parents=True)

        old_session = projects / "old_session.jsonl"
        old_session.write_text(json.dumps({
            "type": "user",
            "timestamp": "2026-05-01T10:00:00Z",
            "uuid": "u1",
            "message": {"role": "user", "content": "old prompt should not be picked"},
            "cwd": "/tmp",
        }) + "\n")

        time.sleep(0.05)  # ensure mtime ordering

        new_session = projects / "new_session.jsonl"
        new_session.write_text(json.dumps({
            "type": "user",
            "timestamp": "2026-05-07T10:00:00Z",
            "uuid": "u2",
            "message": {"role": "user", "content": "the latest prompt the user typed in claude code"},
            "cwd": "/tmp",
        }) + "\n")

        monkeypatch.setattr(Path, "home", lambda: tmp_path)

        from trinity_local.commands.council_last import _find_last_user_prompt
        prompt, source = _find_last_user_prompt()
        assert prompt is not None
        assert "latest prompt" in prompt
        assert "new_session.jsonl" in (source or "")
