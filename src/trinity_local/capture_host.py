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


import re

# 100-persona audit D6 fix (security blocker): conv_id + provider arrive
# unsanitized via Chrome Native Messaging. A compromised/malicious extension
# OR adversarial JSON in a captured response (conv.uuid is server-controlled)
# could send provider="../../.." or conv_id="../../../../.ssh/authorized_keys"
# and the host would happily write attacker-controlled JSON anywhere the
# user can write. Strict allowlist on both fields blocks this primitive.
_SAFE_ID_RX = re.compile(r"^[a-zA-Z0-9._-]{1,80}$")


def _sanitize_id(value: str, label: str) -> str:
    """Return value if it's filename-safe; else raise.

    Allows ASCII alnum + `.` `_` `-`, capped at 80 chars (UUIDs +
    `.stream` suffix fit). Rejects:
      - non-string types (a malicious payload could send an int/dict)
      - traversal sequences (`..`)
      - leading dots (would hide files / disrupt globs)
      - path separators (`/` `\\` already excluded by the allowlist)
    """
    if not isinstance(value, str) or not _SAFE_ID_RX.match(value):
        raise ValueError(
            f"unsafe {label}: must match [a-zA-Z0-9._-]{{1,80}}, got {value!r}"
        )
    if ".." in value or value.startswith("."):
        raise ValueError(
            f"unsafe {label}: contains traversal sequence or leading dot, got {value!r}"
        )
    return value


def _write_capture(provider: str, conv_id: str, conversation: dict[str, Any]) -> Path:
    from .utils import atomic_write_text
    provider = _sanitize_id(provider, "provider")
    conv_id = _sanitize_id(conv_id, "conv_id")
    target = _conv_dir() / provider / f"{conv_id}.json"
    atomic_write_text(target, json.dumps(conversation, indent=2, ensure_ascii=False))
    return target


# Phase 1 (Chrome extension transition): action-dispatch messages.
#
# The browser extension sends two message classes:
#   1. `kind` in {"canonical", "adapter_stream", "stream"} → conversation
#       captures (handled by _extract_target above, v1.6 flow)
#   2. `kind` in ACTION_ALLOWLIST → CLI-invocation requests (new in this
#       release — replaces the macOS Shortcuts dispatch path)
#
# The action allowlist is defense-in-depth: even if the extension is
# compromised, the host will only run pre-approved CLI surfaces. New
# action kinds require an explicit ALLOWLIST entry — adding one is a
# security review.

# Each entry can be one of two shapes:
#   2-tuple: (cli_subcommand, [(arg_name, json_field, required), ...])
#   3-tuple: above + a list of *constant* CLI flags appended unconditionally
#            (e.g. always pass `--open` when the launchpad's "Render lens
#            card" button fires render-me-card — the dispatcher path can't
#            shell-chain `open <path>`, so the CLI does it).
# Args are passed as `--<arg_name> <value>`; missing required → reject.
# The allowlist intentionally lists only the buttons the launchpad UI
# exposes today — not the full CLI surface.
ACTION_ALLOWLIST: dict[str, tuple] = {
    "launch-council": (
        "council-launch",
        [
            ("task", "task", True),
            ("goal", "goal", False),
            ("primary-provider", "primary_provider", False),
        ],
    ),
    "ingest-recent": (
        "ingest-recent",
        [],
    ),
    # Phase 4b (council_bf1ab3f4dd70f75e residual-drift fix): stop-council
    # lets the launchpad's "Stop" button work cross-platform. Previously
    # the button fired a `shortcuts://run_command` payload that no-op'd
    # silently off macOS. Narrow allowlist entry — only --status-token,
    # no shell command — preserves the "no run_command" verdict from
    # the council.
    "stop-council": (
        "council-stop",
        [
            ("status-token", "status_token", True),
        ],
    ),
    # Phase 4b (council_bf1ab3f4dd70f75e residual-drift cleanup): the seven
    # settings toggles. Each is a no-arg CLI subcommand — the narrowest
    # possible allowlist surface, satisfying the council's "do NOT add
    # run_command" verdict. Enum-by-kind so spoofed payloads can't trigger
    # arbitrary shell commands.
    "telemetry-enable":   ("telemetry-enable",   []),
    "telemetry-disable":  ("telemetry-disable",  []),
    "telemetry-reset-id": ("telemetry-reset-id", []),
    "auto-chain-enable":  ("auto-chain-enable",  []),
    "auto-chain-disable": ("auto-chain-disable", []),
    "polish-auto-enable":  ("polish-auto-enable",  []),
    "polish-auto-disable": ("polish-auto-disable", []),
    # render-me-card closes the last residual-drift gap from
    # council_bf1ab3f4dd70f75e. The CLI grew an `--open` flag (Phase 4b
    # follow-up) so the host doesn't need to shell-chain `open <path>`.
    # `open` is a no-arg boolean — payload may include `{"open": true}`
    # to fire the cross-platform open after writing the PNG.
    "render-me-card": (
        "me-card",
        [],
        ["--open"],  # always opens the PNG after writing — that's what the
                     # launchpad button means by "render". The CLI honors
                     # --open via notifications.open_path (cross-platform).
    ),
}


def _run_action(payload: dict[str, Any]) -> dict[str, Any]:
    """Dispatch an action message to a trinity-local CLI subcommand.

    Subprocess (not in-process) so capture_host stays small + the action
    runs in a fresh interpreter with the user's full env. Output streamed
    back as a single response message — no partial streaming yet, but the
    message shape leaves room for it later via a `stream_id` field.
    """
    import shlex
    import subprocess

    kind = payload.get("kind")
    if kind not in ACTION_ALLOWLIST:
        return {"ok": False, "error": f"action {kind!r} not in allowlist"}
    entry = ACTION_ALLOWLIST[kind]
    if len(entry) == 2:
        cli_subcommand, arg_spec = entry
        constant_flags: list[str] = []
    else:
        cli_subcommand, arg_spec, constant_flags = entry

    argv: list[str] = ["trinity-local", cli_subcommand]
    for arg_name, json_field, required in arg_spec:
        value = payload.get(json_field)
        if value is None or value == "":
            if required:
                return {
                    "ok": False,
                    "error": f"missing required field {json_field!r} for action {kind!r}",
                }
            continue
        if not isinstance(value, (str, int, float)):
            return {
                "ok": False,
                "error": f"field {json_field!r} must be primitive, got {type(value).__name__}",
            }
        argv.extend([f"--{arg_name}", str(value)])

    # Append any constant flags (e.g. always `--open` for render-me-card).
    # These are defined in the allowlist, not in the payload — caller
    # cannot influence them, so they're safe to append unconditionally.
    argv.extend(constant_flags)

    try:
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "error": f"timeout after 120s",
            "argv": " ".join(shlex.quote(a) for a in argv),
        }
    except FileNotFoundError:
        return {
            "ok": False,
            "error": "trinity-local CLI not on PATH; install via `pip install trinity-local`",
        }
    return {
        "ok": result.returncode == 0,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "action": kind,
    }


def _is_action_message(msg: dict[str, Any]) -> bool:
    """An action message has `kind` in the action allowlist. Capture
    messages have `kind` in {canonical, adapter_stream, stream}."""
    return msg.get("kind") in ACTION_ALLOWLIST


def main() -> int:
    while True:
        try:
            msg = _read_message()
        except Exception as e:
            _write_message({"ok": False, "error": f"read_failed: {e}"})
            return 1
        if msg is None:
            return 0
        # Action messages dispatch to the CLI (Phase 1 of the extension
        # transition). Capture messages flow through _extract_target +
        # _write_capture as before. Two distinct paths, one host process.
        if _is_action_message(msg):
            _write_message(_run_action(msg))
            continue
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
