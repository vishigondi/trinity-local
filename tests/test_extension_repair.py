"""Tests for `trinity-local extension repair` — diagnose + HAR + prompt build.

Skips the real council dispatch path (would actually shell out to
provider CLIs). The dispatch wiring is exercised end-to-end via the
existing council-runner test suite; here we lock down the new pieces:
diagnosis from `~/.trinity/conversations/`, HAR filtering, and prompt
construction shape.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from trinity_local.commands import extension_repair


@pytest.fixture
def trinity_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
    return tmp_path


def test_diagnose_reports_missing_directory_per_provider(trinity_home):
    diag = extension_repair.diagnose()
    assert set(diag["providers"].keys()) == {"claude", "chatgpt", "gemini"}
    for slug in ("claude", "chatgpt", "gemini"):
        assert diag["providers"][slug]["exists"] is False
        assert diag["providers"][slug]["captures"] == 0
        assert diag["providers"][slug]["hours_since_last"] is None


def test_diagnose_distinguishes_empty_dir_from_missing_dir(trinity_home):
    (trinity_home / "conversations" / "chatgpt").mkdir(parents=True)
    diag = extension_repair.diagnose()
    assert diag["providers"]["chatgpt"]["exists"] is True
    assert diag["providers"]["chatgpt"]["captures"] == 0
    assert diag["providers"]["gemini"]["exists"] is False


def test_diagnose_counts_captures_and_picks_latest(trinity_home):
    claude_dir = trinity_home / "conversations" / "claude"
    claude_dir.mkdir(parents=True)
    (claude_dir / "a.json").write_text("{}")
    (claude_dir / "b.json").write_text("{}")
    diag = extension_repair.diagnose()
    assert diag["providers"]["claude"]["captures"] == 2
    assert diag["providers"]["claude"]["hours_since_last"] is not None
    assert diag["providers"]["claude"]["hours_since_last"] >= 0
    assert diag["providers"]["claude"]["last_capture"]  # ISO string set


def test_diagnose_ignores_dotfiles(trinity_home):
    chatgpt_dir = trinity_home / "conversations" / "chatgpt"
    chatgpt_dir.mkdir(parents=True)
    (chatgpt_dir / ".DS_Store").write_text("noise")
    diag = extension_repair.diagnose()
    assert diag["providers"]["chatgpt"]["captures"] == 0


def _make_har(entries):
    return {"log": {"version": "1.2", "entries": entries}}


def _post(url, status=200, content_type="text/event-stream", body="data: hi"):
    return {
        "request": {"method": "POST", "url": url, "postData": {"text": body}},
        "response": {"status": status, "headers": [{"name": "Content-Type", "value": content_type}]},
    }


def test_extract_chat_posts_matches_chatgpt_new_endpoint():
    har = _make_har([
        _post("https://chatgpt.com/backend-api/f/conversation"),
        _post("https://chatgpt.com/backend-api/conversation/abc123"),  # canonical GET — POST won't match
    ])
    posts = extension_repair.extract_chat_posts(har)
    assert len(posts) == 2  # both are POSTs and on chatgpt.com
    assert all(p["provider"] == "chatgpt" for p in posts)


def test_extract_chat_posts_strips_telemetry_noise():
    har = _make_har([
        _post("https://chatgpt.com/ces/v1/t"),
        _post("https://chatgpt.com/backend-api/sentinel/ping"),
        _post("https://chatgpt.com/ces/statsc/flush"),
        _post("https://chatgpt.com/backend-api/lat/r"),
        _post("https://chatgpt.com/backend-api/f/conversation"),  # the real one
    ])
    posts = extension_repair.extract_chat_posts(har)
    assert len(posts) == 1
    assert "/backend-api/f/conversation" in posts[0]["url"]


def test_extract_chat_posts_provider_filter():
    har = _make_har([
        _post("https://chatgpt.com/backend-api/f/conversation"),
        _post("https://claude.ai/api/organizations/x/chat_conversations/y/completion"),
        _post("https://gemini.google.com/_/BardChatUi/data/batchexecute"),
    ])
    chatgpt_only = extension_repair.extract_chat_posts(har, provider="chatgpt")
    assert len(chatgpt_only) == 1
    assert chatgpt_only[0]["provider"] == "chatgpt"

    claude_only = extension_repair.extract_chat_posts(har, provider="claude")
    assert len(claude_only) == 1
    assert claude_only[0]["provider"] == "claude"


def test_extract_chat_posts_records_status_and_content_type():
    har = _make_har([_post("https://chatgpt.com/backend-api/f/conversation", status=503, content_type="text/event-stream")])
    posts = extension_repair.extract_chat_posts(har)
    assert posts[0]["status"] == 503
    assert posts[0]["content_type"] == "text/event-stream"
    assert posts[0]["has_request_body"] is True


def test_extract_chat_posts_skips_non_chat_domains():
    har = _make_har([
        _post("https://example.com/api/something"),
        _post("https://google.com/search"),  # google.com but not gemini.google.com
    ])
    posts = extension_repair.extract_chat_posts(har)
    assert posts == []


def test_build_repair_bundle_includes_diagnosis_har_and_source():
    diag = {"providers": {"chatgpt": {"captures": 0, "exists": True}}}
    har_posts = [{"provider": "chatgpt", "method": "POST", "url": "https://chatgpt.com/backend-api/f/conversation", "status": 200, "content_type": "text/event-stream", "has_request_body": True}]
    page_hook = "// page-hook.js stub"
    bundle = extension_repair.build_repair_bundle(diag=diag, har_posts=har_posts, page_hook_source=page_hook)
    assert "PROVIDER_PATTERNS" in bundle.task_text
    assert "page-hook.js" in bundle.task_text
    assert "backend-api/f/conversation" in bundle.task_text  # the new endpoint must reach the council
    assert "// page-hook.js stub" in bundle.task_text  # source verbatim
    assert "unified diff" in bundle.task_text  # asks for a patch
    assert bundle.metadata["kind"] == "extension_repair"


def test_build_repair_bundle_truncates_har_posts_at_50():
    diag = {"providers": {}}
    posts = [{"provider": "chatgpt", "method": "POST", "url": f"https://chatgpt.com/backend-api/f/conversation/{i}",
              "status": 200, "content_type": "text/event-stream", "has_request_body": False} for i in range(120)]
    bundle = extension_repair.build_repair_bundle(diag=diag, har_posts=posts, page_hook_source="x")
    # The 50th URL must appear; the 60th must not.
    assert "/backend-api/f/conversation/49" in bundle.task_text
    assert "/backend-api/f/conversation/60" not in bundle.task_text


def test_handle_repair_diagnose_only_doesnt_require_har(trinity_home, capsys):
    class _Args:
        har = None
        provider = None
        as_json = False
    extension_repair.handle_repair(_Args())
    out = capsys.readouterr().out
    assert "Chrome extension capture diagnosis" in out
    assert "claude" in out
    assert "chatgpt" in out
    assert "gemini" in out


def test_handle_repair_har_not_found_exits_nonzero(trinity_home):
    class _Args:
        har = Path("/nonexistent.har")
        provider = None
        as_json = False
    with pytest.raises(SystemExit) as exc:
        extension_repair.handle_repair(_Args())
    assert exc.value.code == 2


def test_handle_repair_json_mode_emits_valid_json_for_diagnose(trinity_home, capsys):
    class _Args:
        har = None
        provider = None
        as_json = True
    extension_repair.handle_repair(_Args())
    out = capsys.readouterr().out
    payload = json.loads(out)
    assert "providers" in payload
    assert set(payload["providers"].keys()) == {"claude", "chatgpt", "gemini"}


def test_cli_registration_lists_extension_subcommand():
    import argparse
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    extension_repair.register(subparsers)
    # Top-level `extension` parser exists.
    args = parser.parse_args(["extension", "repair"])
    assert args.command == "extension"
    assert args.extension_command == "repair"
    assert args.har is None
