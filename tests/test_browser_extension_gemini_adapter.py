"""Fixture-based unit test for browser-extension/adapters/gemini.js.

Task #135 (v1.8): gemini.google.com adapter. Different from claude /
chatgpt because Google's batchexecute RPC is NOT SSE — it's a chunked
length-prefixed JSON envelope with double-encoded inner payloads.

Runs the JS adapter through node against a synthetic batchexecute body;
asserts conv_id (from page URL, not the RPC URL) + best-effort
assistant_text extraction. Skips when node isn't on PATH.

Why no fixture file: Gemini's batchexecute frame shape rotates across
Google's frontend releases. Pinning a real captured body would brittle
the test against shape rotation. Instead, we generate a minimal
synthetic frame matching the documented wire format and assert the
parser's robustness primitives (frame splitter, wrb.fr extractor,
longest-prose walker).
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parent.parent
ADAPTER_PATH = REPO_ROOT / "browser-extension" / "adapters" / "gemini.js"


def _make_batchexecute_body(assistant_text: str, message_id: str = "msg-abcd1234") -> str:
    """Build a synthetic batchexecute body matching Gemini's wire format.

    Wire format:
        )]}'
        <length>\n
        [["wrb.fr","<rpc>","<double-encoded inner JSON>",null,null,"<msg_id>"]]\n
    """
    inner = json.dumps([[
        "irrelevant_envelope_field",
        ["candidate_id", assistant_text, "more_metadata"],
    ]])
    frame = json.dumps([
        ["wrb.fr", "vfBeAd", inner, None, None, message_id],
    ])
    return f")]}}'\n{len(frame)}\n{frame}\n"


def _run_adapter(input_obj: dict) -> dict:
    script = f"""
    const adapter = require({json.dumps(str(ADAPTER_PATH))});
    const result = adapter.adapt({json.dumps(input_obj)});
    process.stdout.write(JSON.stringify(result));
    """
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=10)
    assert out.returncode == 0, f"node failed: {out.stderr}"
    return json.loads(out.stdout)


def _node_available() -> bool:
    return shutil.which("node") is not None


def test_adapter_file_exists():
    assert ADAPTER_PATH.exists(), f"adapter missing: {ADAPTER_PATH}"


def test_adapter_reports_correct_provider():
    if not _node_available():
        import pytest
        pytest.skip("node not available")
    result = _run_adapter({
        "url": "https://gemini.google.com/_/BardChatUi/data/batchexecute",
        "body_text": _make_batchexecute_body("The cross-provider memory layer the labs are commercially prevented from building."),
        "method": "POST",
        "page_href": "https://gemini.google.com/app/abc123def456",
    })
    assert result["provider"] == "gemini"


def test_adapter_kind_is_adapter_stream():
    """Critical: must be `adapter_stream`, not `stream`. The capture
    host writes adapter_stream payloads under `<conv_id>.stream.json`;
    `stream` would create urlhash-keyed orphans (the v1.7 gap).
    """
    if not _node_available():
        import pytest
        pytest.skip("node not available")
    result = _run_adapter({
        "url": "https://gemini.google.com/_/BardChatUi/data/batchexecute",
        "body_text": _make_batchexecute_body("Some Gemini reply with sufficient prose to pass the length filter."),
        "method": "POST",
        "page_href": "https://gemini.google.com/app/abc123def456",
    })
    assert result["kind"] == "adapter_stream"


def test_adapter_extracts_conv_id_from_app_path():
    """Gemini's URL shape /app/<id> is the v1 path. Adapter must pull
    conv_id from page_href because the batchexecute URL doesn't have one.
    """
    if not _node_available():
        import pytest
        pytest.skip("node not available")
    result = _run_adapter({
        "url": "https://gemini.google.com/_/BardChatUi/data/batchexecute?rpcids=...",
        "body_text": _make_batchexecute_body("Some Gemini reply with sufficient prose to pass the length filter."),
        "method": "POST",
        "page_href": "https://gemini.google.com/app/conv-id-from-url",
    })
    assert result["conv_id"] == "conv-id-from-url"


def test_adapter_extracts_conv_id_from_c_query_param():
    """Alternative URL shape: ?c=<id>"""
    if not _node_available():
        import pytest
        pytest.skip("node not available")
    result = _run_adapter({
        "url": "https://gemini.google.com/_/BardChatUi/data/batchexecute",
        "body_text": _make_batchexecute_body("Some Gemini reply with sufficient prose to pass the length filter."),
        "method": "POST",
        "page_href": "https://gemini.google.com/?c=conv-from-query",
    })
    assert result["conv_id"] == "conv-from-query"


def test_adapter_extracts_assistant_text_from_wrb_fr_payload():
    """Longest-prose-leaf walker pulls the model reply from the
    double-encoded inner JSON.
    """
    if not _node_available():
        import pytest
        pytest.skip("node not available")
    reply = "Trinity Local is the cross-provider memory layer the labs are commercially prevented from building."
    result = _run_adapter({
        "url": "https://gemini.google.com/_/BardChatUi/data/batchexecute",
        "body_text": _make_batchexecute_body(reply),
        "method": "POST",
        "page_href": "https://gemini.google.com/app/conv-x",
    })
    assert result["assistant_text"] == reply


def test_adapter_extracts_message_id():
    if not _node_available():
        import pytest
        pytest.skip("node not available")
    result = _run_adapter({
        "url": "https://gemini.google.com/_/BardChatUi/data/batchexecute",
        "body_text": _make_batchexecute_body("Some Gemini reply with sufficient prose to pass the length filter.", message_id="msg-mid-12345"),
        "method": "POST",
        "page_href": "https://gemini.google.com/app/conv-x",
    })
    assert result["message_id"] == "msg-mid-12345"


def test_adapter_preserves_raw_body_for_reextraction():
    """Gemini's frame shape is unstable. Raw body MUST be preserved so
    a future ingest run with an updated extractor can re-parse without
    re-capturing.
    """
    if not _node_available():
        import pytest
        pytest.skip("node not available")
    body = _make_batchexecute_body("Some Gemini reply with sufficient prose to pass the length filter.")
    result = _run_adapter({
        "url": "https://gemini.google.com/_/BardChatUi/data/batchexecute",
        "body_text": body,
        "method": "POST",
        "page_href": "https://gemini.google.com/app/conv-x",
    })
    assert result["_raw_body"] == body


def test_adapter_does_not_crash_on_empty_body():
    if not _node_available():
        import pytest
        pytest.skip("node not available")
    result = _run_adapter({
        "url": "https://gemini.google.com/_/BardChatUi/data/batchexecute",
        "body_text": "",
        "method": "POST",
        "page_href": "https://gemini.google.com/app/conv-x",
    })
    assert result["provider"] == "gemini"
    assert result["assistant_text"] == ""
    assert result["frames_count"] == 0


def test_adapter_handles_missing_xssi_prefix():
    """Some Gemini frontend variants ship batchexecute responses WITHOUT
    the )]}' XSSI prefix. Adapter must handle both.
    """
    if not _node_available():
        import pytest
        pytest.skip("node not available")
    body_without_prefix = _make_batchexecute_body("Some Gemini reply with sufficient prose to pass the length filter.")
    body_without_prefix = body_without_prefix.replace(")]}'\n", "", 1)
    result = _run_adapter({
        "url": "https://gemini.google.com/_/BardChatUi/data/batchexecute",
        "body_text": body_without_prefix,
        "method": "POST",
        "page_href": "https://gemini.google.com/app/conv-x",
    })
    assert "Trinity" in result["assistant_text"] or "Gemini" in result["assistant_text"]


def test_adapter_skips_malformed_frames_without_crashing():
    """A truncated mid-frame body (network drop) must not crash the
    adapter — capture must never break the page.
    """
    if not _node_available():
        import pytest
        pytest.skip("node not available")
    truncated = ")]}'\n100\n[[\"wrb.fr\",\"abc\","  # length 100 but body cut short
    result = _run_adapter({
        "url": "https://gemini.google.com/_/BardChatUi/data/batchexecute",
        "body_text": truncated,
        "method": "POST",
        "page_href": "https://gemini.google.com/app/conv-x",
    })
    assert result["provider"] == "gemini"
    # Just doesn't crash — assistant_text empty is fine here.


def test_adapter_extracts_user_prompt_from_request_body():
    """Critical for Gemini: the user's prompt only exists in the
    batchexecute REQUEST body (Google's RPC response is reply-only).
    Without this extraction, gemini captures contribute zero
    PromptTurn entries — iter_prompt_turns only yields user-facing
    turns and the assistant-only session has none.
    """
    if not _node_available():
        import pytest
        pytest.skip("node not available")
    # Simulate Gemini's batchexecute request body shape:
    #   f.req=<url-encoded JSON>&at=<csrf-token>
    user_prompt = "Refactor the auth flow to use OAuth instead of API keys."
    inner = json.dumps([user_prompt, 0, None, [["context"]]])
    rpc_args = json.dumps([[["StreamGenerate", inner, None, "generic"]]])
    # URL-encode the outer JSON the way batchexecute does
    import urllib.parse
    request_body = "f.req=" + urllib.parse.quote(rpc_args) + "&at=anti-csrf-token"
    result = _run_adapter({
        "url": "https://gemini.google.com/_/BardChatUi/data/batchexecute",
        "body_text": _make_batchexecute_body("Sure, here's how to refactor the auth flow to use OAuth properly."),
        "method": "POST",
        "page_href": "https://gemini.google.com/app/conv-x",
        "request_body": request_body,
    })
    assert result["user_text"] == user_prompt


def test_adapter_returns_empty_user_text_when_no_request_body():
    """Pre-v1.8 captures (without request_body field) — adapter must
    not crash; just return empty user_text.
    """
    if not _node_available():
        import pytest
        pytest.skip("node not available")
    result = _run_adapter({
        "url": "https://gemini.google.com/_/BardChatUi/data/batchexecute",
        "body_text": _make_batchexecute_body("Some Gemini reply with sufficient prose to pass the length filter."),
        "method": "POST",
        "page_href": "https://gemini.google.com/app/conv-x",
    })
    assert result["user_text"] == ""


def test_adapter_file_stem_uses_message_id_when_present():
    """file_stem (per-call discriminator for the on-disk filename) should
    prefer the assistant message_id when extractable. Without this, every
    gemini RPC for a conversation overwrites the previous on disk
    (#145 — caught live 2026-05-23 when StreamGenerate content was
    masked by trailing batchexecute telemetry)."""
    if not _node_available():
        import pytest
        pytest.skip("node not available")
    result = _run_adapter({
        "url": "https://gemini.google.com/_/BardChatUi/data/batchexecute",
        "body_text": _make_batchexecute_body("Some reply with prose.", message_id="msg-deadbeef9999"),
        "method": "POST",
        "page_href": "https://gemini.google.com/app/conv-xyz",
        "captured_at": "2026-05-24T00:30:47.199Z",
    })
    assert result["conv_id"] == "conv-xyz"
    assert result["message_id"] == "msg-deadbeef9999"
    assert result["file_stem"] == "conv-xyz__msg-deadbeef9999"


def test_adapter_file_stem_falls_back_to_captured_at():
    """When no message_id is extractable (some RPC frames don't carry
    one), file_stem falls back to the captured_at timestamp so RPCs
    still land distinctly."""
    if not _node_available():
        import pytest
        pytest.skip("node not available")
    # Synthesize a body where extractMessageId() returns null — message_id
    # field is empty/non-hex-like.
    frame = json.dumps([["wrb.fr", "vfBeAd", json.dumps([["x", "Some prose to pass the filter long enough"]]), None]])
    body = f")]}}'\n{len(frame)}\n{frame}\n"
    result = _run_adapter({
        "url": "https://gemini.google.com/_/BardChatUi/data/batchexecute",
        "body_text": body,
        "method": "POST",
        "page_href": "https://gemini.google.com/app/conv-no-msg",
        "captured_at": "2026-05-24T00:30:47.199Z",
    })
    assert result["conv_id"] == "conv-no-msg"
    assert result["message_id"] is None
    # YYYYMMDDHHMMSSXXX (captured_at digits, first 17)
    assert result["file_stem"].startswith("conv-no-msg__2026052400")


def test_adapter_file_stem_null_when_no_conv_id():
    """No conv_id (user on /app root) → file_stem null → capture host's
    conv_id-required gate still drops it (per existing semantics)."""
    if not _node_available():
        import pytest
        pytest.skip("node not available")
    result = _run_adapter({
        "url": "https://gemini.google.com/_/BardChatUi/data/batchexecute",
        "body_text": _make_batchexecute_body("Reply"),
        "method": "POST",
        "page_href": "https://gemini.google.com/",
        "captured_at": "2026-05-24T00:30:47.199Z",
    })
    assert result["conv_id"] is None
    assert result["file_stem"] is None
