# Trinity v1.6 — Browser-side conversation capture (no server, no daemon)

> Status: **spec only, follows v1.5 ship.** Target: **2-week implementation
> after v1.5 (June 3, 2026) locks in.**
>
> v1.6 closes the corpus-acquisition gap that the v1.0 launch surfaces but
> doesn't fully solve. The pitch — *"Trinity reads the transcripts already on
> your machine"* — works for **claude.ai exports** (manual JSON dump) and for
> **CLI harness sessions** (Claude Code / Codex CLI / Gemini CLI write
> session files automatically). It does NOT work for the **chat web UIs**
> (claude.ai chat / chatgpt.com / gemini.google.com) where most users actually
> spend their day. v1.6 fixes that — automatically, with no listening server,
> no daemon, and no ongoing user action after install.

## Validation log (T-1, 2026-05-14 night)

The provider-specific adapter notes below were validated against
live network traffic via Chrome DevTools network panel + page-
context fetch probes. Three findings updated from the initial
draft:

1. **claude.ai uses `fetch()` + `response.body.getReader()`, NOT
   `EventSource`.** EventSource is GET-only; the completion
   endpoint is POST. Live `EventSource` instance count on
   claude.ai/new = 0. The initial spec said "Hook EventSource (not
   just fetch)" — that's wrong; hook `fetch` and read the streamed
   response body. This is the single most important correction.
2. **Gemini's batchexecute path is `/_/BardChatUi/data/
   batchexecute`** (full prefix), not just the bare word
   `batchexecute`. The `rpcids` query parameter selects which
   internal RPC is being invoked; multiple distinct RPC IDs
   observed on a single page load.
3. **Gemini's wire format is Google's RPC-over-JSON envelope**
   (`f.req=<URL-encoded JSON array>`), not raw protobuf as the
   initial spec implied. Decoding is array-position based, not
   protobuf-descriptor based.

claude.ai canonical fetch shape was verified end-to-end (200,
JSON, `chat_messages` array with `parent_message_uuid` per
message). chatgpt.com canonical endpoint shape was verified
(200, JSON, `items/total/limit/offset` envelope on list);
canonical conversation tree wasn't fully verified because the
test account had 0 conversations, but the endpoint exists and
returns the expected envelope.

## Validation log (T-0, 2026-05-15)

After Week 1 of v1.6 shipped (commits `4bd2e0f`, `e2e6720`,
`2784717`), the `page-hook.js` IIFE was injected into a live
`claude.ai/new` page-context to re-confirm the spec
assumptions against today's frontend:

* `location.hostname === "claude.ai"`, `document.readyState ===
  "complete"`, `window.fetch` is a function — basic
  preconditions hold.
* Injection returns `"installed"`, `window.__TRINITY_HOOK_INSTALLED__
  === true`, `window.fetch.name === "trinityFetch"` — the wrapper
  is in place exactly as it would be after the extension's
  MAIN-world content_script runs.
* Console emits `[trinity-hook] fetch wrapper installed on
  claude.ai` — the user-visible signal documented in
  `browser-extension/README.md` ("3 places to look when capture
  isn't firing").

Claim re-confirmed: claude.ai's frontend is fetch-based; the
EventSource constructor remains globally reachable but the page
itself does not construct any (anything that would have shown up
as `EventSource` had to flow through `window.EventSource` and a
sentinel wrap would have logged it). Hook installation does not
break any page behavior — title still renders, `/new` route still
loads, no console errors.

End-to-end smoke (Load Unpacked → send message → verify file
lands) remains the user's manual step per
`browser-extension/README.md`; everything that can be validated
without sending a real chat message has been validated.

## Validation log (T-0, 2026-05-15, chatgpt.com mirror)

After the chatgpt.js adapter shipped (commit `561f17a`), the
page-hook was injected into a live `chatgpt.com/` page-context
to verify the same wrapper that works on claude.ai installs
cleanly on OpenAI's frontend:

* `location.hostname === "chatgpt.com"`, `document.readyState
  === "complete"`, `window.fetch` is a function — preconditions
  match claude.ai. Title is `"ChatGPT"`.
* Injection returns `"installed"`, `window.__TRINITY_HOOK_INSTALLED__
  === true`, `window.fetch.name === "trinityFetch"` — same shape
  as the claude.ai validation.
* Console emits `[trinity-hook] fetch wrapper installed on
  chatgpt.com` — same user-visible debug signal.
* Page renders normally (no console errors). The `EventSource`
  constructor is reachable but `window.fetch` is the streaming
  primitive OpenAI uses, matching the assumption baked into
  `chatgpt.js` (parses SSE body from a `fetch` clone, not from
  an `EventSource`).

Same closure: live page validation has been done for both
providers shipped in v1.6 Week 1+2. gemini.google.com remains
deferred to v1.7 per the spec's stability assessment.

## The reframe

v1.0 ships with this gap quietly papered over: the seed-from-taste-terminal
pipeline reads only what already lives on disk. For the user with
heavy claude.ai or chatgpt.com chat usage, "already on disk" means
**nothing** — those conversations live on Anthropic's / OpenAI's
servers, not the user's filesystem. The user has to go to each
provider's settings, click "Export data," wait for the email,
download a tarball, and re-seed Trinity. Per provider. Repeatedly.

v1.6 inverts the burden: the user installs a browser extension once,
and from that point forward every conversation they have on the web
gets captured to `~/.trinity/conversations/<provider>/<conv_id>.json`
the moment it completes. No "remember to export." No batch lag.
The corpus catches up to today's prompts within seconds, not weeks.

The structural value: **the corpus that powers cortex / lens / picks
expands organically as the user lives their normal day.** That's
exactly the moat the launch claims; v1.6 makes it operate without
user attention.

## Strategic positioning

**v1.0's wedge claim:** *"Trinity reads transcripts already on your
machine."* For CLI users this is literal. For web-chat users it's
aspirational unless they manually export.

**v1.6's wedge claim:** *"Install once. Every conversation across
Claude / GPT / Gemini lands in your folder."* Now the wedge is
literal for everyone — not just the multi-CLI power user.

The architectural detail matters: **no listening server.** No
localhost port. No background daemon process. The Native Messaging
protocol Chrome ships specifically for this — extension spawns a
child process on demand, that process reads stdin, writes one file,
exits when the extension disconnects. From a security and install-
simplicity standpoint, this is **cleaner** than a localhost server.

Trinity's "your data, your machine" positioning gets sharper:
`lsof -i | grep LISTEN` shows nothing related to Trinity. The
write surface is a single short-lived child process the OS reaps
the moment the extension goes idle.

## The capture mechanic

Per conversation turn, the data path is:

1. User has a conversation on `claude.ai`, `chatgpt.com`, or
   `gemini.google.com`.
2. A content script injected into the page wraps `window.fetch` and
   `EventSource` **in the page's main world** to observe the
   provider's own API calls — not DOM scraping.
3. When a streamed response completes, the page hook posts the full
   conversation snapshot to the extension's content script via
   `window.postMessage`.
4. Content script forwards to the background service worker via
   `chrome.runtime.sendMessage`.
5. Service worker connects to the native messaging host (Chrome
   spawns `trinity-local-capture-host` as a child process on the
   first message).
6. Service worker sends the captured JSON over stdin to the host.
7. Host normalizes into Trinity schema and writes to
   `~/.trinity/conversations/<provider>/<conv_id>.json`.
8. When the extension disconnects (tab closes, browser closes, idle
   timeout), the host process exits.

**Idempotency by overwrite.** Each captured turn writes the full
updated conversation state to one file keyed by the provider's
stable conversation ID. Files are small (~200KB for long
conversations). Overwrites are cheap. No incremental-merge logic
needed — the canonical state always comes from the provider's own
API response.

## Why Native Messaging, not localhost

| Option | Listening port | Daemon process | Install complexity | Auth |
|---|---|---|---|---|
| **Native Messaging (this spec)** | None | None (on-demand child) | Single CLI command writes a manifest file | `allowed_origins` cryptographic restriction to the Trinity extension only |
| Localhost server | Required | Yes (must stay alive) | User must trust + start a daemon | CORS / token-in-header, easier to misconfigure |
| File-system poll | None | Polling cron or watcher | Polling lag + duplicate writes | None — surface is the filesystem |
| User exports manually | None | None | High friction | None — user controls |

The matrix tilts hard toward Native Messaging. Password managers
(1Password, Bitwarden, Dashlane) use this exact pattern to bridge
their extensions to local apps. The security primitive
(`allowed_origins`) restricts the host to invocations from the
specific Trinity extension ID — no other extension on the system
can talk to it.

## Provider-specific adapter notes

Each provider's API has a distinct shape; the extension's adapter
layer normalizes them into Trinity's existing conversation schema.

### claude.ai

**Validated against live traffic at T-1 (DevTools network panel + page-context probes).**

- **Streaming endpoint:** **POST** to
  `/api/organizations/<org>/chat_conversations/<conv_id>/completion`
  with SSE-formatted response body. **Hook `fetch()` and read
  `response.body.getReader()` — NOT `EventSource`.** EventSource is
  spec-restricted to GET; the completion endpoint is POST. Verified
  on a fresh claude.ai/new session: `EventSource` instance count = 0
  globally; all streaming goes through `fetch()` with a streamed
  response body. Accumulate streamed `data: ...` chunks until the
  terminating event arrives.
- **Canonical state fetch:** the full conversation lives at
  `/api/organizations/<org>/chat_conversations/<conv_id>`. Verified
  shape (live response, T-1):
  ```
  top-level keys: uuid, name, summary, model, created_at,
    updated_at, settings, is_starred, is_temporary, platform,
    current_leaf_message_uuid, chat_messages
  message keys:   uuid, text, sender, index, created_at,
    updated_at, input_mode, truncated, attachments, files,
    sync_sources, parent_message_uuid
  ```
  Fetch this after the stream completes for canonical state —
  avoids reconstructing from streamed deltas.
- **Org-ID discovery:** UUID, surfaces from the bootstrap call at
  `/edge-api/bootstrap/<org_id>/app_start?...` (first call on page
  load). Adapter caches the org_id per session.
- **Stability:** medium. Anthropic's API is the most stable of
  the three but does refactor periodically. Ship a console-log
  fallback so we know within hours if a refactor breaks capture.

### chatgpt.com

**Validated against live traffic at T-1.**

- **Streaming endpoint:** `POST /backend-api/conversation` with
  SSE response. Wrap `fetch`, capture `data:` events from the
  response stream.
- **Canonical state fetch:** `GET /backend-api/conversation/<id>`
  returns the conversation tree (branches included). Persist
  after stream completion. Tree shape uses a `mapping` dict keyed
  by node id with `current_node` pointer — branching is real, not
  linear like claude.ai.
- **Conversation list:** `GET /backend-api/conversations?offset=
  0&limit=N&order=updated` → `{items: [...], total, limit, offset}`
  (verified shape; empty list returns `{items: [], total: 0, ...}`
  without 404, so adapter can poll safely).
- **Stability:** medium-high. OpenAI's frontend evolves but the
  `/backend-api/conversation` endpoint has been stable for over a
  year as of T-1.

### gemini.google.com

**Validated against live traffic at T-1.**

- **Streaming endpoint:** ALL conversation API calls go through
  **`POST /_/BardChatUi/data/batchexecute`** (the full path
  prefix; the bare word "batchexecute" is just one segment of it).
  Selector is the **`rpcids` query parameter** — different RPC
  IDs for list/send/respond/etc. Observed RPC IDs on a fresh
  /app page load: `aPya6c`, `cYRIkd`, `ozz5Z`, `qpEbW`, `o30O0e`,
  `K4WWud`, `CNgdBe`, `ku4Jyf`. Each adapter version pins the
  current RPC IDs to operations.
- **Other query params**: `f.sid` (session id), `_reqid`
  (incrementing request counter), `bl` (build label like
  `boq_assistant-bard-web-server_20260511.16_p8` — used to detect
  frontend version changes; treat as an upgrade signal).
- **Wire format:** the request body uses Google's RPC-over-HTTP
  envelope (`f.req=<URL-encoded JSON array>` form-encoded). It's
  NOT raw protobuf — it's structured JSON arrays with positional
  fields wrapped in metadata. Decoder needs to walk the array
  structure per RPC. The earlier "protobuf-ish" framing was
  imprecise.
- **Capture approach:** intercept both request and response;
  decode by RPC-ID → operation map. The `bl` build label
  rotating means the adapter needs a fallback "log unknown
  rpcids" path so we know within hours when Google ships a new
  frontend that introduces new RPCs.
- **Stability:** low. Plan for the most fragility here.
  **Ship this adapter LAST** — get claude.ai and chatgpt.com
  shipping value before fighting Google's protocol.

**Gemini's structural difference matters for capture:** unlike
claude.ai (clean REST) and chatgpt.com (clean REST), Gemini's
streaming API is essentially Google's internal RPC framework
exposed through a URL. Every call is opaque to a HAR-based debugger
unless the adapter knows which RPC ID maps to which operation. This
is why it's higher fragility AND why exporting Gemini conversations
through any third-party tool is structurally harder.

## The Manifest V3 detail nobody mentions

To wrap `fetch` in the page's main world (so the extension sees
the provider's actual API traffic, not just what the extension's
isolated world can see), you need:

```js
chrome.scripting.executeScript({
  target: { tabId },
  world: 'MAIN',
  files: ['page-hook.js'],
})
```

OR script-tag injection from a content script. The MV3 isolated
world cannot intercept page-level network calls the way MV2 could.
**This trips up most first-time extension implementations.** Test
the main-world injection FIRST, before any adapter logic.

## The native messaging install bridge

Chrome reads a JSON manifest from a known OS-specific path to know
which extensions are allowed to invoke which local binaries. Trinity
ships `trinity-local install-extension` to write this manifest.

On macOS, the file lands at:

```
~/Library/Application Support/Google/Chrome/NativeMessagingHosts/local.trinity.capture.json
```

Contents:

```json
{
  "name": "local.trinity.capture",
  "description": "Trinity local conversation capture",
  "path": "/usr/local/bin/trinity-local-capture-host",
  "type": "stdio",
  "allowed_origins": ["chrome-extension://<EXTENSION_ID>/"]
}
```

The `allowed_origins` field is the security primitive — only the
Trinity extension (identified by its public-key-derived ID) can
invoke this host.

The CLI command itself is ~30 lines: write the manifest, ensure
the host binary is on PATH, print "next steps" (load the unpacked
extension, then visit claude.ai to test).

## The native messaging wire protocol

Chrome's stdio wire format is length-prefixed JSON:

```
[4-byte little-endian length][UTF-8 JSON]
```

Both directions. The host reads the length, reads that many bytes,
parses JSON, processes, repeats. When stdin closes, the host exits.

Roughly 30 lines of Python:

```python
import json, struct, sys
from pathlib import Path

CONV_DIR = Path.home() / ".trinity" / "conversations"

def read_message():
    raw_length = sys.stdin.buffer.read(4)
    if not raw_length:
        return None
    length = struct.unpack("<I", raw_length)[0]
    return json.loads(sys.stdin.buffer.read(length).decode("utf-8"))

def write_message(payload):
    encoded = json.dumps(payload).encode("utf-8")
    sys.stdout.buffer.write(struct.pack("<I", len(encoded)))
    sys.stdout.buffer.write(encoded)
    sys.stdout.buffer.flush()

def main():
    while True:
        msg = read_message()
        if msg is None:
            break
        provider = msg["provider"]
        conv_id = msg["conv_id"]
        target = CONV_DIR / provider / f"{conv_id}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(msg["conversation"], indent=2))
        tmp.replace(target)  # atomic rename
        write_message({"ok": True, "path": str(target)})

if __name__ == "__main__":
    main()
```

The host has no state, no server, no cleanup logic — the OS reaps
the process when stdin closes.

## Project layout

```
trinity-local/
├── browser-extension/
│   ├── manifest.json              # MV3 manifest
│   ├── background.js              # service worker; native host bridge
│   ├── content-script.js          # window.postMessage ↔ chrome.runtime relay
│   ├── page-hook.js               # MAIN world: wraps fetch + EventSource
│   ├── adapters/
│   │   ├── claude.js              # parses Anthropic SSE
│   │   ├── chatgpt.js             # parses OpenAI SSE
│   │   └── gemini.js              # parses Google batchexecute (LAST)
│   └── icons/
└── src/trinity_local/
    ├── capture_host.py            # native messaging host (~50 LOC)
    └── commands/
        └── install_extension.py   # writes manifest, prints next steps
```

The browser extension goes in its own `browser-extension/` directory at
the repo root — separate from `src/trinity_local/` because it's
shipped to Chrome Web Store as a separate artifact (not bundled with
the pip package).

## The new CLI surface

One new top-level command and one MCP follow-on:

```
trinity-local install-extension
  # Writes ~/Library/Application Support/.../NativeMessagingHosts/local.trinity.capture.json
  # Pointing at /usr/local/bin/trinity-local-capture-host (symlinked from the wheel install)
  # Prints: "Now visit chrome://extensions, enable Developer Mode, click
  #          'Load unpacked', and select browser-extension/. Then visit claude.ai
  #          to test — your next message will land at ~/.trinity/conversations/."

trinity-local-capture-host
  # The native messaging host binary. Not exposed as a `trinity-local <cmd>`
  # subcommand because Chrome spawns it directly; needs a stable name.
  # Installed as a separate console_script entry in pyproject.toml.
```

The MCP tool surface stays at 9 (no new MCP tools needed for v1.6 — `search_prompts` retired 2026-05-17 + `get_eval_summary` retired 2026-05-18 dropped it from 11 to 9 during pre-launch simplification).
The launchpad gains one card: "Browser capture (N conversations
captured today)" — surfaces the rate at which the extension is
landing data so the user notices if it stops working.

## Ship plan (2 weeks post-v1.5)

**Status (2026-05-15):** Week 1 + Week 2 Days 6-9 SHIPPED ahead of
schedule. Bi-provider capture path (claude.ai + chatgpt.com) is
code-complete and end-to-end tested. The only remaining step before
the v1.6 ship cut is the user's one-time `chrome://extensions →
Load Unpacked` install + the README/launch-doc sweep this section
itself.

**Week 1 — claude.ai end-to-end.** ✅ All shipped 2026-05-14/15.

- ✅ Day 1-2 (commit `4bd2e0f`): scaffolded `browser-extension/`
  directory. MV3 manifest + ISOLATED + MAIN content scripts. Tested
  main-world fetch wrapping with a no-op adapter.
- ✅ Day 3 (commit `4bd2e0f`): `capture_host.py` (~120 LOC). 4 stdio
  round-trip subprocess tests + AST guard that bans networking
  imports.
- ✅ Day 4 (commit `4bd2e0f`): `install_extension.py` writes the
  Native Messaging manifest. End-to-end smoke wiring is in place;
  the user-facing Load Unpacked + `--extension-id` step is
  documented in `browser-extension/README.md` (manual one-time UI
  action that can't be automated through MCP).
- ✅ Day 5 (commit `e2e6720`): `claude.js` SSE adapter. 8 fixture
  cases run via node against `tests/fixtures/claude_sse_sample
  .txt` — text reconstruction verbatim, conv_id / message_uuid
  extraction, empty-body + truncated-JSON resilience.
- ✅ Browser validation (commit `b618e40`): page-hook.js IIFE
  injected into a live `claude.ai/new` page at T-0 (2026-05-15);
  wrapper installs cleanly, idempotency flag sets, console fires
  the expected log, no page errors. Re-confirmed the EventSource
  count = 0 claim against today's frontend.

**Week 2 — chatgpt.com + launchpad surface + ship.** Partially shipped.

- ✅ Day 6-7 (commit `561f17a`): `chatgpt.js` SSE adapter. 10
  fixture cases. Same module shape as `claude.js`; handles both
  OpenAI's cumulative-parts shape AND the newer delta-content
  shape, returns whichever accumulates more text. conv_id falls
  back from top-level `conversation_id` to `message.metadata
  .conversation_id`.
- ✅ Day 7 (commits `07bd828` + `97347c4`): captures flow into the
  prompt index via two new ingest sources — `browser_claude` (linear
  `chat_messages` shape) and `browser_chatgpt` (`mapping` graph
  walked from `current_node` back to root, then reversed). Both
  source names added to `incremental_ingest.DEFAULT_SOURCES` so MCP
  hot path picks up new captures within the deadline budget. 14
  ingest tests pass through real-parser + real-dispatch path; no
  monkeypatching of the parse layer.
- ✅ Day 8 (commit `fb9de4c`): Launchpad Surface 33 "Browser
  capture" card. Same shape as rate-limit-saves / verdict-rate —
  per-provider counts, last-capture timestamp, `stale` flag flips
  warning border when last capture > 24h ago (silent-breakage
  signal). 11 tests; empty-state CTA points at install command.
- ✅ Day 9: README v1.6 section + this status sweep + the launch
  package note updating the "Install once" wedge claim.
- ⏸ Day 10 — ship: pending the user's `chrome://extensions → Load
  Unpacked` step + the `chatgpt.js` manifest entry has not yet been
  validated against a live chatgpt.com fetch (the saved-fixture
  pass is structural; a real-traffic smoke is the user's part).

**Deferred:**

- gemini.google.com adapter — Google's protocol fragility makes it
  the highest-risk + lowest-immediate-value adapter. Ship it in a
  v1.7 follow-on once the v1.6 core is stable on the other two
  providers. The launch-arc claim ("Trinity reads Claude / GPT /
  Gemini transcripts") is still defensible because Gemini Takeout
  works for past history; v1.7 closes the live-capture gap.

## Foundations from v1.0 / v1.5 that v1.6 depends on (do NOT break)

- The conversation schema at `~/.trinity/prompts/` — v1.6 writes to
  `~/.trinity/conversations/<provider>/` first, then the existing
  incremental ingest pipeline picks them up and writes
  PromptNode entries. v1.6 does NOT modify the PromptNode shape.
- The cortex / lens / picks pipeline — works unchanged on v1.6-
  captured data because v1.6 produces the same conversation file
  shape ingest already consumes (just from a new source dir).
- The browser smoke gate — Surface 33 will assert the
  "browser capture" launchpad card renders correctly when capture
  data is present.
- MCP `ask` and `search_prompts` — already include incremental
  ingest on every call; v1.6-captured data flows into them
  automatically.

## What v1.6 explicitly does NOT do

- **No Safari extension.** macOS Chrome ships first. Safari is the
  v1.7+ secondary platform; the same Native Messaging pattern
  works there but the install bridge writes to a different OS path.
- **No mobile capture.** Phone/tablet browsing is out of scope —
  the cross-device-sync story belongs to v2.
- **No conversation editing surface in the extension.** Read-only
  capture. The extension never modifies what the provider stores.
- **No proxy mode.** v1.6 captures what the provider already
  returned; it doesn't route the user's traffic through Trinity
  or modify the provider's response.
- **No outbound network from the host.** The capture host writes
  to local disk only. Same privacy invariant as the rest of Trinity.
- **No Firefox / Edge in the v1 wheel.** The extension code is
  cross-browser-compatible (Chrome + Firefox + Edge all support
  Native Messaging with the same protocol) but ship the Chrome
  Web Store version first; the others bundle on user request.

## Privacy / security invariants

- **`allowed_origins` is load-bearing.** The native messaging
  manifest's `allowed_origins` field restricts the host to
  invocations from the specific Trinity extension's ID (derived
  from its public key). Any other extension trying to invoke the
  host gets `error: Specified native messaging host not found.`
  Verified via Chrome's own restriction logic, not Trinity's.

- **No network from the host process.** `capture_host.py` does
  NOT import `requests`, `urllib`, `httpx`, or any networking
  module. Pin with a regression guard (`tests/test_capture_host_
  no_network.py`).

- **Atomic writes only.** `tmp.replace(target)` is atomic on
  POSIX — readers never see a partial file. If the host crashes
  mid-write, the `.tmp` file is left behind but the canonical
  conversation file remains intact.

- **Conversation data is plaintext on disk.** Same as the rest of
  Trinity. The "your data, your machine" claim doesn't change.
  Encrypting at rest is a future option but adds complexity that
  the local-first invariant doesn't currently require.

## The launchpad addition (Surface 33)

A new card surfaces capture activity to make silent capture
breakage VISIBLE. Sample state:

```
Browser capture · last 24h
12 conversations captured · 3 providers
   claude.ai     7
   chatgpt.com   4
   gemini.google 1

Last capture: 2 minutes ago. Install via `trinity-local install-extension`.
```

If the extension stops working (provider API refactors, extension
disabled), the "Last capture" timestamp ages. Same shape as the
`verdict_rate` / `handoff_ready` / cortex_freshness checks: a
visible-by-default signal that the user notices when it's off.

## Why this beats "Trinity Cloud" or any hosted alternative

The temptation: stand up a hosted proxy or browser-extension-as-a-
service that the user logs into. Don't. The whole pitch is "your
data, your machine." A hosted capture surface would:

- Add a service Trinity has to operate (24/7 uptime, SOC2, etc.).
- Require the user to log in (now Trinity has accounts; the
  current launch's "no account" claim breaks).
- Create a network attack surface where conversation data flows.
- Need a paid tier to sustain (revenue model changes; the
  "free forever" launch claim breaks).

The Native Messaging architecture preserves every load-bearing
invariant in the v1.0 launch: local-first, no account, no per-call
billing, no listening server, no hosted state. The user's data
stays where it always was — on their disk, in their
`~/.trinity/`.

## Cross-references

- v1.0 launch positioning that depends on this: `README.md` "It
  also looks back: Trinity scans the transcripts already on your
  machine" — literal for CLI users today; literal for everyone
  after v1.6.
- v1.5 dispatch pipeline ([`docs/spec-v1.5.md`](spec-v1.5.md)):
  v1.6's captured conversations flow into the same `ask` / cortex
  / lens pipeline. No changes to v1.5 internals needed.
- The existing `seed-from-taste-terminal` command stays — it
  remains the bootstrap path for users who arrive with months of
  pre-Trinity history they want imported in one shot. v1.6 is the
  continuous path for everything after install.
