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

- **Streaming endpoint:** Server-Sent Events on
  `/api/organizations/<org>/chat_conversations/<conv_id>/completion`.
  Hook `EventSource` (NOT just `fetch`); accumulate streamed chunks
  until the `event: completion` arrives.
- **Canonical state fetch:** the full conversation lives at
  `/api/organizations/<org>/chat_conversations/<conv_id>` — fetch
  that after the stream completes for canonical state. Avoids
  having to reconstruct from streamed deltas.
- **Stability:** medium. Anthropic's API is the most stable of
  the three but does refactor periodically. Ship a console-log
  fallback so we know within hours if a refactor breaks capture.

### chatgpt.com

- **Streaming endpoint:** `POST /backend-api/conversation` with
  SSE response. Wrap `fetch`, capture `data:` events from the
  response stream.
- **Canonical state fetch:** `GET /backend-api/conversation/<id>`
  returns the conversation tree (branches included). Persist
  after stream completion.
- **Stability:** medium-high. OpenAI's frontend evolves but the
  `/backend-api/conversation` endpoint has been stable for over a
  year as of T-1.

### gemini.google.com

- **Streaming endpoint:** Google obfuscates response payloads
  through their internal `batchexecute` protocol. The wire format
  is protobuf-ish: a base64-wrapped, framed message with
  positional fields.
- **Capture approach:** intercept both request and response;
  decode the wire format. Likely needs reverse-engineering each
  Gemini frontend revision.
- **Stability:** low. Plan for the most fragility here.
  **Ship this adapter LAST** — get claude.ai and chatgpt.com
  shipping value before fighting Google's protocol.

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

The MCP tool surface stays at 11 (no new MCP tools needed for v1.6).
The launchpad gains one card: "Browser capture (N conversations
captured today)" — surfaces the rate at which the extension is
landing data so the user notices if it stops working.

## Ship plan (2 weeks post-v1.5)

**Week 1 — claude.ai end-to-end.**

- Day 1-2: scaffold `browser-extension/` directory. MV3 manifest +
  content script + page hook. Test main-world fetch wrapping with a
  no-op adapter (just log captured payloads).
- Day 3: write `capture_host.py` (30 LOC). Test stdio round-trip
  with a manually-spawned host.
- Day 4: `install_extension.py` writes the manifest. End-to-end
  smoke: load extension → visit claude.ai → send a message → file
  lands at `~/.trinity/conversations/claude/<conv_id>.json`.
- Day 5: claude.js adapter. Normalize Anthropic's SSE delta format
  into Trinity's conversation schema. Pin with at least one
  fixture-based unit test.

**Week 2 — chatgpt.com + launchpad surface + ship.**

- Day 6-7: chatgpt.js adapter. Same shape as claude.js, different
  endpoint + slight schema variations.
- Day 8: Launchpad card showing "Browser capture: N conversations
  today across {providers}." Wire a regression guard the way
  Surface 30/32 work.
- Day 9: README section + docs/spec-v1.6.md (this file) + launch
  package update — the "Install once" wedge claim becomes literal.
- Day 10: Ship.

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
