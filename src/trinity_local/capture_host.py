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

from .state_paths import conversations_dir


def _conv_dir() -> Path:
    return conversations_dir()


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
        # `file_stem`, when present, is what the adapter wants on disk
        # — typically a per-call discriminator like `<conv_id>__<msg_id>`
        # so multiple RPCs per turn (gemini fires several) don't
        # overwrite each other. conv_id stays the semantic field for
        # ingest-side grouping. Falls back to conv_id when absent
        # (claude/chatgpt one-stream-per-turn doesn't need it).
        stem = raw.get("file_stem") or conv_id
        return provider, f"{stem}.stream", dict(raw)
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
# Action kinds in this set are fire-and-forget: capture_host spawns the
# CLI via Popen with stdio redirected to /dev/null and a fresh session
# (so it survives Chrome closing the Native Messaging pipe) and returns
# immediately with `{ok: true, detached: true, pid, status_token?}`.
# The caller is expected to poll via `get-council-status` using the
# status_token it generated.
#
# Without this, council-launch blocks the popup for the full council
# duration (30-90s) and times out at 120s with "Failed: unknown error".
_DETACHED_ACTIONS = {"launch-council"}

# Action kinds handled in-process (no subprocess). The popup uses
# `get-council-status` to poll a council's status JSON without the
# ~150ms-per-call subprocess startup cost — capture_host has direct
# filesystem access so it just reads the JSON.
#
# `open-launchpad` is in-process when launchpad.html already exists —
# the old path (`trinity-local portal-html --open-browser`) ran a full
# refresh_launchpad rebuild on every click (~3-10s on real corpora).
# The static file is kept fresh by council/ingest callbacks, so a
# bare-open is correct in the steady state. Falls through to the
# subprocess regen path only when the file is missing (first install).
_INPROCESS_ACTIONS = {"get-council-status", "open-launchpad", "open-council-page"}

ACTION_ALLOWLIST: dict[str, tuple | None] = {
    "launch-council": (
        "council-launch",
        [
            ("task", "task", True),
            ("goal", "goal", False),
            ("primary-provider", "primary_provider", False),
            # status-token threads through to the council runner so the
            # status JSON at ~/.trinity/portal_pages/status/<token>.json
            # is written under a token the caller chose, not the bundle_id.
            # The popup uses this for its incremental status display.
            ("status-token", "status_token", False),
        ],
    ),
    # In-process: reads ~/.trinity/portal_pages/status/<token>.json
    # directly via council_status.load_council_status. No CLI subcommand.
    "get-council-status": None,
    # In-process when live_council.html exists; falls back to portal-html
    # regen via the open-launchpad entry below (which writes both pages
    # as a side effect) on first install.
    "open-council-page": None,
    "ingest-recent": (
        "ingest-recent",
        [],
    ),
    # Memory Health "Refresh memory" button (council_1f9cbecd7104f90f #3).
    # The user's intent is "don't make me open a terminal" — not "auto-run
    # LLM calls without my knowledge." Dream is expensive and surprising
    # (10+ flagship calls, several minutes). A single button labeled
    # "Refresh memory" that the user clicks explicitly satisfies the
    # intent. No args from the launchpad — the defaults (full pipeline
    # incl. vocabulary, consolidate, lens-build, distill) are what
    # "refresh memory" means for someone whose lens has drifted.
    "dream": (
        "dream",
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
    # Refine / iterate / auto-chain / continue all dispatch to
    # `trinity-local council-iterate`. The legacy alias names
    # (council_refine / council_continue / council_auto_chain) map
    # to council_iterate per dispatch_registry.py L145, so a single
    # extension allowlist entry covers all four buttons on the
    # council-review page. council_review.py L519 was firing
    # shortcuts:// for this until tick 140 — the macOS Shortcut
    # dispatcher was retired pre-launch (claude.md L578), so the
    # supervision loop's only signal path was silently dead. This
    # entry restores it via the Chrome extension dispatch tier.
    "council-iterate": (
        "council-iterate",
        [
            ("council", "council", True),
            ("prompt", "prompt", False),
            ("rounds", "rounds", False),
            ("status-token", "status_token", False),
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
    # open-launchpad regenerates ~/.trinity/portal_pages/launchpad.html
    # and opens it in the user's default browser. The extension popup
    # uses this as the single "Open Trinity launchpad" entry point —
    # the extension's own launchpad.html duplicate was removed in
    # favor of one canonical file:// surface.
    "open-launchpad": (
        "portal-html",
        [],
        ["--open-browser"],
    ),
}


def _trinity_local_bin() -> str:
    """Locate the ``trinity-local`` CLI.

    Chrome launches Native Messaging hosts with a minimal PATH that
    typically excludes ``~/.local/bin`` / user-installed pip script
    dirs. Bare ``subprocess.run(["trinity-local", ...])`` PATH lookup
    fails under that env. But ``trinity-local`` and
    ``trinity-local-capture-host`` are installed by pip as siblings in
    the same ``bin/`` directory — we can resolve the CLI relative to
    THIS process's own binary path and skip PATH lookup entirely.

    Falls back to the bare name for the PATH-lookup path if the
    sibling isn't found (e.g., editable installs with unusual
    layouts) — that branch then surfaces the FileNotFoundError →
    "CLI not on PATH" error to the user, which is still informative.
    """
    try:
        host_bin = Path(sys.argv[0]).resolve()
        sibling = host_bin.parent / "trinity-local"
        if sibling.exists():
            return str(sibling)
    except (OSError, ValueError):
        pass
    return "trinity-local"


def _open_council_page(payload: dict[str, Any]) -> dict[str, Any]:
    """In-process handler for `open-council-page`.

    Opens the live council review page for a specific status_token —
    not the launchpad. URL shape mirrors the launchpad's
    liveCouncilUrl computed property: live_council.html with
    status_token + task + members as query params.

    The popup uses this both for the "Open council page" button and
    for the auto-open-on-completion handoff (so the user lands on
    the specific council that just finished, not the launchpad).
    """
    import webbrowser
    from .state_paths import review_pages_dir

    token = payload.get("status_token") or payload.get("status-token")
    if not isinstance(token, str) or not _SAFE_ID_RX.match(token):
        return {"ok": False, "error": "invalid status_token"}

    live = review_pages_dir() / "live_council.html"
    if not live.exists():
        # First-install fallback — fall through to portal-html regen so
        # live_council.html gets written, then re-open.
        return {"ok": False, "needs_regen": True}

    params: list[tuple[str, str]] = [("status_token", token)]
    task = payload.get("task")
    if isinstance(task, str) and task.strip():
        params.append(("task", task.strip()))
    members = payload.get("members")
    if isinstance(members, list) and members:
        params.append(("members", ",".join(str(m) for m in members)))

    # Inline %-encoder: the no-network regression guard bans `urllib`
    # at the namespace level (whole-stdlib safety net — see
    # tests/test_capture_host_no_network.py). The CGI rules for query
    # values are simple enough to do here without pulling in urllib.parse.
    _SAFE = frozenset(
        "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789_.-~"
    )
    def _q(s: str) -> str:
        out = []
        for ch in s:
            if ch in _SAFE:
                out.append(ch)
            else:
                for byte in ch.encode("utf-8"):
                    out.append(f"%{byte:02X}")
        return "".join(out)
    query = "&".join(f"{_q(k)}={_q(v)}" for k, v in params)
    url = live.as_uri() + "?" + query
    try:
        opened = webbrowser.open(url)
    except Exception as exc:
        return {"ok": False, "error": f"open_failed: {exc}"}
    return {
        "ok": bool(opened),
        "action": "open-council-page",
        "url": url,
        "opened": bool(opened),
    }


def _open_launchpad(payload: dict[str, Any]) -> dict[str, Any]:
    """In-process handler for `open-launchpad`.

    Fast path: if ~/.trinity/portal_pages/launchpad.html already exists,
    just open it. The launchpad is regenerated as a side effect of every
    council/ingest run via refresh_launchpad, so the static file is
    fresh in the steady state.

    Slow path: file missing → fall back to running `trinity-local
    portal-html --open-browser` which writes + opens. Returns a sentinel
    {"ok": False, "needs_regen": True} so _run_action's caller layer
    re-dispatches via the subprocess branch.
    """
    from .notifications import open_path
    from .state_paths import trinity_home
    launchpad_path = trinity_home() / "portal_pages" / "launchpad.html"
    if not launchpad_path.exists():
        return {"ok": False, "needs_regen": True}
    opened = open_path(str(launchpad_path))
    return {
        "ok": bool(opened),
        "action": "open-launchpad",
        "path": str(launchpad_path),
        "opened": bool(opened),
    }


def _read_council_status(payload: dict[str, Any]) -> dict[str, Any]:
    """In-process handler for `get-council-status` polling.

    Reads ~/.trinity/portal_pages/status/<token>.json directly rather
    than shelling out — saves ~150ms per poll, which matters when the
    popup polls every 1.5s.
    """
    token = payload.get("status_token") or payload.get("status-token")
    if not isinstance(token, str) or not _SAFE_ID_RX.match(token):
        return {"ok": False, "error": "invalid status_token"}
    try:
        from .council_status import load_council_status
        status = load_council_status(token)
    except Exception as exc:
        return {"ok": False, "error": f"status_read_failed: {exc}"}
    # status is None until the runner writes the first record. That's
    # the normal early-poll case — return ok:true with status:null so
    # the popup can keep rotating its loading copy without flashing
    # an error.
    return {"ok": True, "status": status, "status_token": token}


def _run_action(payload: dict[str, Any]) -> dict[str, Any]:
    """Dispatch an action message.

    Three paths:

    * In-process (``_INPROCESS_ACTIONS``) — handled by a dedicated
      function. Used for tight-loop polling like `get-council-status`
      where a 150ms subprocess startup per call is wasteful.
    * Detached (``_DETACHED_ACTIONS``) — subprocess.Popen with stdio
      redirected and a new session, returns immediately. Used for
      `launch-council` so the popup doesn't block 30-90s on a council.
    * Default — ``subprocess.run`` with capture_output, blocks until
      the CLI exits, returns stdout/stderr/returncode.
    """
    import shlex
    import subprocess

    kind = payload.get("kind")
    if kind not in ACTION_ALLOWLIST:
        return {"ok": False, "error": f"action {kind!r} not in allowlist"}

    # In-process fast paths. Each returns early on success; on a
    # `needs_regen` sentinel, we fall through to the subprocess regen
    # path below by re-binding `kind` to `open-launchpad` (which the
    # allowlist maps to `portal-html --open-browser` — that subcommand
    # writes BOTH launchpad.html and live_council.html so the next click
    # gets the fast path).
    if kind == "get-council-status":
        return _read_council_status(payload)
    if kind == "open-council-page":
        result = _open_council_page(payload)
        if result.get("needs_regen") is not True:
            return result
        kind = "open-launchpad"  # fall through to regen
    if kind == "open-launchpad":
        result = _open_launchpad(payload)
        if result.get("needs_regen") is not True:
            return result
        # First-install: portal-html regen writes the file then opens.

    entry = ACTION_ALLOWLIST[kind]
    if entry is None:
        return {"ok": False, "error": f"action {kind!r} has no CLI binding"}
    if len(entry) == 2:
        cli_subcommand, arg_spec = entry
        constant_flags: list[str] = []
    else:
        cli_subcommand, arg_spec, constant_flags = entry

    argv: list[str] = [_trinity_local_bin(), cli_subcommand]
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

    # Detached path — fire-and-forget. Child inherits NOTHING from the
    # host's stdio (Chrome owns those FDs as the Native Messaging wire),
    # and runs in a new session so SIGHUP to the host doesn't take it
    # down. Caller polls status via `get-council-status`.
    #
    # Pass build_runtime_env() so the child can find provider binaries
    # (claude, codex, agy) — Chrome's spawn env strips ~/.local/bin
    # and Homebrew dirs, which is where those CLIs live. Without this,
    # every council launched from the popup fails with "Provider
    # binary not found: claude" within ~10s.
    from .runtime_env import build_runtime_env
    if kind in _DETACHED_ACTIONS:
        try:
            child = subprocess.Popen(
                argv,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
                close_fds=True,
                env=build_runtime_env(),
            )
        except FileNotFoundError:
            return {
                "ok": False,
                "error": "trinity-local CLI not on PATH; install via `pip install trinity-local`",
            }
        response: dict[str, Any] = {
            "ok": True,
            "action": kind,
            "detached": True,
            "pid": child.pid,
        }
        # Echo the status_token back so the popup doesn't have to remember
        # what it sent (and so a misroute is visible).
        token = payload.get("status_token")
        if token:
            response["status_token"] = token
        return response

    try:
        result = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            check=False,
            timeout=120,
            # Same PATH augmentation rationale as the detached branch
            # above — every CLI we dispatch may itself shell out to
            # claude / codex / agy binaries, which Chrome's minimal
            # PATH doesn't see.
            env=build_runtime_env(),
        )
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "error": "timeout after 120s",
            "argv": " ".join(shlex.quote(a) for a in argv),
        }
    except FileNotFoundError:
        return {
            "ok": False,
            "error": "trinity-local CLI not on PATH; install via `pip install trinity-local`",
        }
    # Real error message when the CLI exited non-zero. Previously the
    # popup got `ok: false` with no `error` field and rendered "Failed:
    # unknown error". Surface returncode + the last useful line of stderr
    # so the popup can show something diagnosable.
    ok = result.returncode == 0
    response = {
        "ok": ok,
        "returncode": result.returncode,
        "stdout": result.stdout,
        "stderr": result.stderr,
        "action": kind,
    }
    if not ok:
        last_stderr = (result.stderr or "").strip().splitlines()
        response["error"] = (
            last_stderr[-1] if last_stderr else f"exit code {result.returncode}"
        )
    return response


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
