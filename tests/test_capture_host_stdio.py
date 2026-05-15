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
