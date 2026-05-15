"""Trinity Local — native messaging host (v1.6 browser capture).

Chrome's stdio wire format is length-prefixed JSON:
    [4-byte little-endian length][UTF-8 JSON]

The browser extension's service worker connects via
``chrome.runtime.connectNative("local.trinity.capture")``. Chrome spawns
this process as a child on first connect, reads stdin until the
connection drops, and reaps the process. No listening port; no daemon.

Capture-host writes the full conversation snapshot to
``~/.trinity/conversations/<provider>/<conv_id>.json`` per payload.
Idempotency is by overwrite — each capture is the canonical state of
that conversation, so subsequent turns overwrite cleanly.

INVARIANT: NO NETWORK. The host imports no networking module. The
"your data, your machine" claim depends on it. Pinned by the regression
guard in ``tests/test_capture_host_no_network.py``.
"""

from __future__ import annotations

import json
import struct
import sys
from pathlib import Path
from typing import Any

from .state_paths import trinity_home


def _conv_dir() -> Path:
    return trinity_home() / "conversations"


def _read_message() -> dict[str, Any] | None:
    raw_length = sys.stdin.buffer.read(4)
    if not raw_length or len(raw_length) < 4:
        return None
    length = struct.unpack("<I", raw_length)[0]
    body = sys.stdin.buffer.read(length)
    if len(body) < length:
        return None
    return json.loads(body.decode("utf-8"))


def _write_message(payload: dict[str, Any]) -> None:
    encoded = json.dumps(payload).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("<I", len(encoded)))
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()


def _extract_target(payload: dict[str, Any]) -> tuple[str, str, dict[str, Any]] | None:
    """Pull (provider, conv_id, conversation_state) out of a capture payload.

    The extension sends two payload kinds:

    * ``kind="stream"`` — raw streamed body text. Day-1 scaffold logs it
      as-is under a synthetic id keyed by url. Once the claude.js / chatgpt
      .js adapters land (Day 5+ of the v1.6 ship plan) they normalize the
      stream into a conversation tree and the kind is "canonical".
    * ``kind="canonical"`` — full conversation JSON from the provider's
      canonical-state endpoint (preferred — avoids reconstructing from
      streamed deltas).
    """
    raw = payload.get("payload") or payload
    provider = raw.get("provider")
    kind = raw.get("kind")
    if not provider:
        return None
    if kind == "canonical":
        conv = raw.get("conversation") or {}
        conv_id = conv.get("uuid") or conv.get("id") or conv.get("conversation_id")
        if not conv_id:
            return None
        return provider, str(conv_id), conv
    if kind == "adapter_stream":
        # Per-provider adapter (e.g. adapters/claude.js) has normalized
        # the streamed SSE body. The adapter provides conv_id directly.
        # The whole adapter result is saved — assistant_text, message_uuid,
        # events_count etc. — so consumers can join with the canonical
        # fetch (which arrives later under the same conv_id).
        conv_id = raw.get("conv_id")
        if not conv_id:
            return None
        # Save under a separate key so the canonical write doesn't get
        # overwritten when both arrive for the same conversation.
        return provider, f"{conv_id}.stream", dict(raw)
    if kind == "stream":
        # Raw (un-adapted) stream — fallback when no adapter is loaded
        # for this provider. Key by URL hash so distinct streams don't
        # overwrite each other.
        from hashlib import sha1
        url = raw.get("url") or ""
        conv_id = "stream-" + sha1(url.encode("utf-8")).hexdigest()[:16]
        return provider, conv_id, {"_raw_stream_body": raw.get("body_text", ""), "_url": url}
    return None


def _write_capture(provider: str, conv_id: str, conversation: dict[str, Any]) -> Path:
    target = _conv_dir() / provider / f"{conv_id}.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(".tmp")
    tmp.write_text(json.dumps(conversation, indent=2, ensure_ascii=False))
    tmp.replace(target)
    return target


def main() -> int:
    while True:
        try:
            msg = _read_message()
        except Exception as e:
            _write_message({"ok": False, "error": f"read_failed: {e}"})
            return 1
        if msg is None:
            return 0
        extracted = _extract_target(msg)
        if extracted is None:
            _write_message({"ok": False, "error": "unrecognized_payload"})
            continue
        provider, conv_id, conversation = extracted
        try:
            target = _write_capture(provider, conv_id, conversation)
            _write_message({"ok": True, "path": str(target), "provider": provider, "conv_id": conv_id})
        except Exception as e:
            _write_message({"ok": False, "error": f"write_failed: {e}"})


if __name__ == "__main__":
    sys.exit(main())
