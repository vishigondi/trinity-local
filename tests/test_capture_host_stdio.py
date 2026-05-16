"""Stdio round-trip test for the v1.6 capture host.

Spawns trinity_local.capture_host as a subprocess, writes a length-
prefixed JSON capture payload to its stdin, reads the ack, and asserts
the captured conversation landed in the expected ``~/.trinity/
conversations/<provider>/<conv_id>.json`` location.

Validates:
* The 4-byte little-endian length prefix
* UTF-8 JSON envelope shape
* Atomic-rename write target (no leftover .tmp file)
* Both canonical and stream payload kinds
"""

from __future__ import annotations

import json
import os
import struct
import subprocess
import sys
from pathlib import Path

import pytest


def _frame(payload: dict) -> bytes:
    body = json.dumps(payload).encode("utf-8")
    return struct.pack("<I", len(body)) + body


def _read_frame(stream) -> dict:
    raw_len = stream.read(4)
    assert raw_len and len(raw_len) == 4, f"missing length prefix; got {raw_len!r}"
    length = struct.unpack("<I", raw_len)[0]
    body = stream.read(length)
    assert len(body) == length, f"short read: expected {length} bytes, got {len(body)}"
    return json.loads(body.decode("utf-8"))


def _spawn_host(tmp_trinity_home: Path) -> subprocess.Popen:
    env = os.environ.copy()
    env["TRINITY_HOME"] = str(tmp_trinity_home)
    env["PYTHONPATH"] = str(Path(__file__).resolve().parent.parent / "src")
    return subprocess.Popen(
        [sys.executable, "-m", "trinity_local.capture_host"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )


def test_canonical_payload_writes_conversation_file(tmp_path):
    trinity_home = tmp_path / "trinity"
    proc = _spawn_host(trinity_home)

    payload = {
        "kind": "captured",
        "payload": {
            "provider": "claude",
            "kind": "canonical",
            "url": "https://claude.ai/api/organizations/org/chat_conversations/abc-123",
            "method": "GET",
            "conversation": {
                "uuid": "abc-123",
                "name": "Test conversation",
                "chat_messages": [
                    {"uuid": "m1", "sender": "human", "text": "hi", "parent_message_uuid": None},
                    {"uuid": "m2", "sender": "assistant", "text": "hello", "parent_message_uuid": "m1"},
                ],
            },
            "captured_at": "2026-05-14T23:00:00Z",
        },
    }

    proc.stdin.write(_frame(payload))
    proc.stdin.flush()

    ack = _read_frame(proc.stdout)
    proc.stdin.close()
    proc.wait(timeout=5)

    assert ack["ok"] is True, f"host returned error: {ack}"
    assert ack["provider"] == "claude"
    assert ack["conv_id"] == "abc-123"

    written = Path(ack["path"])
    assert written.exists(), f"expected file at {written}"
    assert written == trinity_home / "conversations" / "claude" / "abc-123.json"

    saved = json.loads(written.read_text())
    assert saved["uuid"] == "abc-123"
    assert len(saved["chat_messages"]) == 2
    assert not list(written.parent.glob("*.tmp")), "atomic rename should leave no .tmp files"


def test_stream_payload_keyed_by_url_hash(tmp_path):
    trinity_home = tmp_path / "trinity"
    proc = _spawn_host(trinity_home)

    payload = {
        "kind": "captured",
        "payload": {
            "provider": "chatgpt",
            "kind": "stream",
            "url": "https://chatgpt.com/backend-api/conversation",
            "method": "POST",
            "body_text": "data: {\"delta\": \"hi\"}\n\ndata: [DONE]\n\n",
            "captured_at": "2026-05-14T23:00:00Z",
        },
    }

    proc.stdin.write(_frame(payload))
    proc.stdin.flush()

    ack = _read_frame(proc.stdout)
    proc.stdin.close()
    proc.wait(timeout=5)

    assert ack["ok"] is True
    assert ack["provider"] == "chatgpt"
    assert ack["conv_id"].startswith("stream-")

    written = Path(ack["path"])
    assert written.exists()
    saved = json.loads(written.read_text())
    assert "_raw_stream_body" in saved
    assert "data: [DONE]" in saved["_raw_stream_body"]


def test_adapter_stream_writes_with_stream_suffix(tmp_path):
    """``kind: "adapter_stream"`` payloads land under ``<conv_id>.stream.json``
    so they don't overwrite the canonical conversation file when both
    arrive for the same conv_id.
    """
    trinity_home = tmp_path / "trinity"
    proc = _spawn_host(trinity_home)

    payload = {
        "kind": "captured",
        "payload": {
            "provider": "claude",
            "kind": "adapter_stream",
            "conv_id": "conv-xyz",
            "message_uuid": "msg-aa11",
            "url": "https://claude.ai/api/organizations/o/chat_conversations/conv-xyz/completion",
            "method": "POST",
            "assistant_text": "Hello world.",
            "events_count": 5,
        },
    }

    proc.stdin.write(_frame(payload))
    proc.stdin.flush()
    ack = _read_frame(proc.stdout)
    proc.stdin.close()
    proc.wait(timeout=5)

    assert ack["ok"] is True
    assert ack["conv_id"] == "conv-xyz.stream"

    written = Path(ack["path"])
    assert written.exists()
    assert written == trinity_home / "conversations" / "claude" / "conv-xyz.stream.json"

    saved = json.loads(written.read_text())
    assert saved["assistant_text"] == "Hello world."
    assert saved["message_uuid"] == "msg-aa11"


def test_unrecognized_payload_errors_but_keeps_host_alive(tmp_path):
    trinity_home = tmp_path / "trinity"
    proc = _spawn_host(trinity_home)

    # Missing provider — should error but not crash.
    proc.stdin.write(_frame({"kind": "captured", "payload": {"junk": True}}))
    proc.stdin.flush()
    ack = _read_frame(proc.stdout)
    assert ack["ok"] is False

    # Send a valid payload after the bad one — host must still be running.
    proc.stdin.write(_frame({
        "kind": "captured",
        "payload": {
            "provider": "claude",
            "kind": "canonical",
            "conversation": {"uuid": "after-error"},
        },
    }))
    proc.stdin.flush()
    ack2 = _read_frame(proc.stdout)
    assert ack2["ok"] is True
    assert ack2["conv_id"] == "after-error"

    proc.stdin.close()
    proc.wait(timeout=5)


# 100-persona audit D6 fix: path traversal blocker.
def test_provider_path_traversal_rejected(tmp_path, monkeypatch):
    """Compromised extension sends provider='../../etc' — host MUST refuse
    instead of writing outside ~/.trinity/conversations/."""
    import pytest
    from trinity_local.capture_host import _write_capture

    monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
    with pytest.raises(ValueError, match="unsafe provider"):
        _write_capture("../../etc", "innocent_conv", {"chat_messages": []})

    # Confirm nothing was written outside the conversations dir.
    forbidden = tmp_path / ".." / "etc"
    assert not forbidden.exists(), "path traversal succeeded — should have raised"


def test_conv_id_path_traversal_rejected(tmp_path, monkeypatch):
    """Same shape on conv_id — adversarial JSON in conv.uuid can't escape."""
    import pytest
    from trinity_local.capture_host import _write_capture

    monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
    with pytest.raises(ValueError, match="unsafe conv_id"):
        _write_capture("claude", "../../../etc/passwd_attempt", {"chat_messages": []})


def test_conv_id_with_slash_rejected(tmp_path, monkeypatch):
    import pytest
    from trinity_local.capture_host import _write_capture

    monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
    with pytest.raises(ValueError, match="unsafe conv_id"):
        _write_capture("claude", "abc/def", {"chat_messages": []})


def test_overlong_id_rejected(tmp_path, monkeypatch):
    """DoS guard — 80-char cap blocks filename-length attacks
    (cap is 80 to fit `<uuid>.stream` adapter suffix)."""
    import pytest
    from trinity_local.capture_host import _write_capture

    monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
    long_id = "x" * 81
    with pytest.raises(ValueError, match="unsafe conv_id"):
        _write_capture("claude", long_id, {"chat_messages": []})


def test_valid_uuid_passes(tmp_path, monkeypatch):
    """Legitimate UUIDs (the common case) MUST keep working."""
    from trinity_local.capture_host import _write_capture
    monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
    target = _write_capture("claude", "abc123-def456_xyz-uuid", {"chat_messages": []})
    assert target.exists()


# ─── Phase 1: action-dispatch messages (Chrome extension transition) ──

def test_launch_council_action_dispatches_to_cli(monkeypatch, tmp_path):
    """An action message with kind=launch-council must dispatch via
    subprocess to `trinity-local council-launch --task <task>`. The host
    builds the argv from the ACTION_ALLOWLIST spec; this test verifies
    the argv shape without actually invoking the CLI."""
    from trinity_local import capture_host

    captured_argv: list[list[str]] = []

    class _FakeCompletedProcess:
        returncode = 0
        stdout = '{"ok": true, "council_run_id": "council_test123"}'
        stderr = ""

    def _fake_run(argv, **kwargs):
        captured_argv.append(list(argv))
        return _FakeCompletedProcess()

    monkeypatch.setattr(capture_host.subprocess if hasattr(capture_host, "subprocess") else __import__("subprocess"), "run", _fake_run, raising=False)
    # _run_action imports subprocess locally, so we patch the module:
    import subprocess as real_subprocess
    monkeypatch.setattr(real_subprocess, "run", _fake_run)

    result = capture_host._run_action({
        "kind": "launch-council",
        "task": "Compare Rust vs Go for a CLI",
        "primary_provider": "codex",
    })

    assert result["ok"] is True
    assert result["returncode"] == 0
    assert result["action"] == "launch-council"
    assert "council_run_id" in result["stdout"]
    assert captured_argv, "_run_action did not invoke subprocess.run"
    argv = captured_argv[0]
    assert argv[0] == "trinity-local"
    assert argv[1] == "council-launch"
    assert "--task" in argv
    assert argv[argv.index("--task") + 1] == "Compare Rust vs Go for a CLI"
    assert "--primary-provider" in argv
    assert argv[argv.index("--primary-provider") + 1] == "codex"


def test_action_missing_required_field_rejected(monkeypatch):
    """launch-council requires `task`. Missing → reject without invoking CLI."""
    from trinity_local import capture_host

    invoked = []
    import subprocess as real_subprocess
    monkeypatch.setattr(
        real_subprocess, "run", lambda *a, **k: invoked.append(a) or None,
    )

    result = capture_host._run_action({"kind": "launch-council"})  # no task
    assert result["ok"] is False
    assert "missing required field" in result["error"]
    assert "task" in result["error"]
    assert not invoked, "subprocess.run should not be invoked when validation fails"


def test_action_not_in_allowlist_rejected(monkeypatch):
    """Defense in depth: unknown kind → reject. Even if a compromised
    extension sends arbitrary action names, the host won't run them."""
    from trinity_local import capture_host

    invoked = []
    import subprocess as real_subprocess
    monkeypatch.setattr(
        real_subprocess, "run", lambda *a, **k: invoked.append(a) or None,
    )

    result = capture_host._run_action({
        "kind": "rm-rf-everything",
        "task": "x",
    })
    assert result["ok"] is False
    assert "not in allowlist" in result["error"]
    assert not invoked


def test_action_non_primitive_field_rejected(monkeypatch):
    """Field values must be str/int/float — reject dicts/lists. Defends
    against payloads that could be misinterpreted as shell metacharacters."""
    from trinity_local import capture_host

    invoked = []
    import subprocess as real_subprocess
    monkeypatch.setattr(
        real_subprocess, "run", lambda *a, **k: invoked.append(a) or None,
    )

    result = capture_host._run_action({
        "kind": "launch-council",
        "task": {"nested": "payload"},
    })
    assert result["ok"] is False
    assert "primitive" in result["error"]
    assert not invoked


def test_is_action_message_recognizes_action_kinds():
    from trinity_local.capture_host import _is_action_message
    assert _is_action_message({"kind": "launch-council"}) is True
    assert _is_action_message({"kind": "ingest-recent"}) is True
    assert _is_action_message({"kind": "canonical"}) is False
    assert _is_action_message({"kind": "adapter_stream"}) is False
    assert _is_action_message({"kind": "stream"}) is False
    assert _is_action_message({}) is False
