---
class: aspirational
---

# Trinity Cross-Platform Spec

> Status: proposed expansion spec.
>
> Verified reference docs: Claude Code docs and Claude support pages on
> 2026-05-19. The pattern is terminal first, then desktop as the no-terminal
> supervision surface, then web/mobile control of the same underlying work.
> Trinity copies the sequencing, not Claude's hosted trust model.
>
> Product directive: for non-coders, Trinity has to launch like a desktop app,
> Cowork-style. The terminal stays the engine, but the ordinary gesture is an
> app icon, menu bar, hotkey, and first-run setup UI. Mobile starts as a thin app
> that opens review links, not as a full Trinity node.

## Thesis

Trinity should expand the way Claude Code expanded:

1. Ship a complete terminal engine.
2. Wrap that engine in a desktop app for users who do not want to live in a
   terminal, using a Cowork-like launch model: install once, then open Trinity
   from an app icon, menu bar, or hotkey.
3. Add mobile as a thin review-link app over the desktop/local node.

The invariant is that all surfaces strengthen the same local corpus:
`~/.trinity/`. There is no hosted controller, no cloud routing brain, and no
second state store. The app surfaces can get nicer; the source of truth stays
file-backed and local.

The current v1 bridge remains the Chrome extension and static launchpad, but it
is not the final non-coder acquisition surface. This spec makes the next product
shape explicit: a real desktop app becomes the local cockpit, followed by a
mobile app that opens review links, records verdicts, and eventually dispatches
work through the paired desktop.

## What Claude Code Did

Claude Code's useful lesson is product sequencing, not architecture to copy
blindly.

As of 2026-05-19, the official docs show this shape:

- **Terminal CLI is complete.** The quickstart still begins with installing
  `claude`, opening a terminal in a project, and starting a session from there.
- **MCP is a first-class extension point.** Claude Code can spawn local stdio
  MCP servers, connect remote MCP servers, import Claude Desktop MCP config, and
  expose Claude Code itself as an MCP server.
- **Desktop is a real Code surface.** Claude Code Desktop can run local,
  remote, and SSH sessions; it owns a visual desktop UI and reads enough shell
  environment to start local work.
- **Web and mobile attach to running work.** Claude Code on the web runs cloud
  sessions; Remote Control lets browser/mobile steer a session running on the
  user's machine.
- **Mobile starts work and monitors work.** Claude mobile exposes Code sessions,
  Remote Control, dispatch, and push notifications.
- **Deep links are product routes.** Claude Desktop and Claude mobile both use
  `claude://` and universal-link routes to open Code sessions, prefill
  composers, and resume existing work from other surfaces.
- **Remote execution is a separate trust decision.** Claude can run in
  Anthropic cloud VMs or route Remote Control through Anthropic's API. Trinity
  must not make that the default because Trinity's claim is cross-provider local
  memory.

Trinity's version:

- **Terminal/MCP first.** `trinity-local` and `trinity-local --mcp` are the
  complete engine.
- **Desktop second.** The desktop app is the Cowork-style local cockpit over
  `~/.trinity/`: councils, handoffs, memory, provider health, verdict capture,
  and mobile pairing.
- **Mobile third.** The mobile app starts as review, rating, and pick-veto. It
  opens review links first, then later dispatches `ask`, `council`, and
  `handoff` through the paired desktop.
- **Deep links are explicit contracts.** `trinity://...` and hosted
  universal-link fallbacks move users between terminal, desktop, static review
  pages, and mobile without creating another state store.
- **Cloud is metadata-only by default.** Hosted routes may help with install,
  universal links, update checks, or public registries. They must not hold
  ordinary users' prompts, provider outputs, memories, routing rules, or private
  council results.

## Product Boundary

Trinity is not trying to become a chat app, IDE, or hosted agent runtime. The
harness owns the work surface. Trinity owns routing, memory, cross-provider
continuity, and the supervision ledger.

| Surface | Primary job | Must not become |
|---|---|---|
| Terminal | Complete engine, automation, and debug path | A required daily UI for non-coders |
| MCP | Agent-facing tools inside Claude Code, Codex CLI, Antigravity, Cursor, and similar harnesses | A private protocol tied to one harness |
| Chrome extension | Current v1 launchpad host and browser conversation capture | The long-term non-coder launcher |
| Desktop app | Cowork-style local cockpit for councils, handoffs, memories, ratings, provider health, schedules, and device pairing | A hosted dashboard or desktop-only state store |
| Mobile app | Open review links, rate outcomes, veto picks, receive notifications, and later dispatch through desktop | A full Trinity node in v1 |

## Non-Negotiable Constraints

1. **The CLI remains complete.** Any user can uninstall desktop and mobile apps
   and keep using `trinity-local` with no data loss.
2. **`~/.trinity/` remains canonical.** No SQLite migration, cloud database, or
   desktop-only product state in the first cross-platform wave.
3. **Prompt content stays local by default.** Phone actions may reach the paired
   desktop because both devices belong to the user. OpenClaw infrastructure must
   not proxy private prompt text by default.
4. **No hosted controller.** A registry, update server, app-open URL, or push
   metadata service is acceptable. A service deciding routes or holding private
   memory is not.
5. **Surfaces degrade independently.** If desktop is closed, terminal and MCP
   still work. If pairing fails, desktop still works. If MCP is not installed,
   desktop still launches councils through the CLI.
6. **Static artifacts remain durable.** Council pages, memory pages, share
   cards, and review pages remain reopenable from disk.
7. **Every action writes the same ledger.** Desktop and mobile pick-vetoes
   must update the same cortex override state (`picks.json` + the
   `mark_pick_wrong` MCP tool's `override_count` cascade) and routing-ledger
   paths as terminal and MCP actions. The pre-2026-05-22 mention of
   `CouncilOutcome.metadata.user_verdict` is retired — the rating UX (task
   #134) no longer accepts user-side winner verdicts; the chairman's
   `routing_label.winner` is the sole supervision signal, fed
   automatically into `compute_personal_routing_table()`. Refinement
   prompts on each council carry the "what should it have been instead"
   signal inline.
8. **Links never carry private content.** Universal links may carry IDs,
   redacted titles, or encrypted user-exported fragments. They must not place
   prompt text or provider outputs in server-visible paths, query strings, or
   request bodies.
9. **Mobile writes through desktop authority.** The phone may queue signed
   actions, but the desktop revalidates scopes and performs normal Trinity
   writes. No mobile shadow ledger.

## Phase 1: Terminal Foundation

Status: current product path. This is the surface to harden before graphical
expansion. The terminal is not the long-term non-coder UI, but it must remain
the complete engine.

### Jobs To Be Done

- Install Trinity from a terminal.
- Register Trinity in Claude Code, Codex CLI, Antigravity, and Cursor through
  MCP.
- Run councils directly from shell commands.
- Ask Trinity from inside a harness via MCP.
- Hand off a conversation from one provider to another without copy-paste.
- Build and inspect the local lens/cortex memory layer.
- Rate outcomes so the personal routing table improves.
- Produce machine-readable status for desktop and mobile setup.

### Stable Terminal Commands

These commands are the public engine surface desktop/mobile should call rather
than importing internal Python modules:

| Command | Role |
|---|---|
| `trinity-local status --json` | Provider, auth, schema, extension, memory, and setup health |
| `trinity-local install-mcp` | Register Trinity as an MCP server in supported harnesses |
| `trinity-local install-extension` | Install the Native Messaging bridge for the Chrome/Edge extension |
| `trinity-local install-launcher` | Install OS launcher where supported |
| `trinity-local council-launch --task "..."` | Run a multi-provider council |
| `trinity-local council-stop <id>` | Stop a running council |
| `trinity-local handoff <provider>` | Continue a recent thread in another provider |
| `trinity-local dream` | Build the personal layer in one pass |
| `trinity-local lens-build` / `lens-show` | Rebuild and inspect the taste lens |
| `trinity-local consolidate` | Rebuild cortex routing patterns |
| `trinity-local cortex-override` | Mark a routing rule wrong |
| `trinity-local review-link --json <id>` | Produce mobile-safe review routes |
| `trinity-local portal-html` | Regenerate static launchpad artifacts |
| `trinity-local open-review <id>` | Reopen an existing review page |

The MCP surface is the harness-facing mirror:

- `ask`
- `route`
- `run_council`
- `get_persona`
- `get_picks`
- `mark_pick_wrong`
- `get_council_status`
- `handoff`

(`record_outcome` was the ninth MCP tool until retired 2026-05-21 alongside
the rest of the rating UX — chairman pick is the supervision signal now,
fed automatically into `compute_personal_routing_table()`.)

### App-Facing Contracts

Before desktop and mobile depend on the engine, the CLI needs stable JSON
contracts. If a command below is not implemented yet, it is part of Milestone 0.
The exact command names can move during implementation, but the contract shape
cannot: stable fields, deterministic errors, and one remediation hint.

| Contract | Producer | Consumers |
|---|---|---|
| Setup/provider status | `status --json` | desktop setup, mobile pairing preflight |
| Recent/active councils | `councils --json --status ...` | desktop home, live progress, mobile queue |
| One council status | `council-status <id> --json` | live progress, notifications |
| Review route | `review-link --json <id>` | desktop share sheet, mobile universal-link bootstrap |
| Memory health | `memory-health --json` | setup warnings, desktop memory screen |
| Device list/revoke | `device-list --json`, `device-revoke <id>` | desktop settings, lost-phone recovery |
| Remote action audit | `remote-actions --json` | desktop settings, support/debug |

### Terminal Acceptance Criteria

- Fresh install reaches first successful council from shell without a desktop
  dependency.
- `/trinity` in Claude Code can run install, status, dream, and first council
  without the user cloning internals by hand.
- `handoff` works from a real recent transcript and demonstrates the
  no-copy-paste wedge in one command.
- All desktop-needed setup state is available via JSON, not prose scraping.
- Every command has deterministic nonzero exits and a one-line remediation.
- No terminal action requires a persistent desktop daemon.

## Phase 2: Desktop App

Objective: make Trinity launch and feel like a normal local desktop app for
non-coders while preserving the terminal engine underneath it.

The desktop app is the cockpit over `~/.trinity/`: launch councils, watch live
progress, inspect memories, review deltas, rate outcomes, repair provider setup,
schedule local rebuilds, and pair phones.

The Chrome extension remains the browser-capture surface and v1 launchpad
bridge. The desktop app is the ordinary Cowork-like launch surface: open an app,
see status, start work, and supervise results without reading terminal docs.

### Product Shape

First screen:

- command bar for `ask`, `council`, and `handoff`
- onboarding/status panel for first-run setup
- active councils with provider progress
- recent outcomes (chairman pick + per-member streams)
- provider/auth health
- memory health and last `dream` / `consolidate` time
- routing picks with trust/override indicators

Expected workflows:

- Run a council from selected text, clipboard content, or a typed prompt.
- Launch from Dock/Applications/Start Menu, menu bar, or global hotkey without a
  terminal window.
- Use a global hotkey or menu bar item to open Trinity over the current app.
- Watch multiple active councils side by side.
- Review provider agreement/disagreement in an evidence pane.
- Mark a cortex pick wrong from the same review flow.
- Continue a Claude thread in Gemini or Codex from desktop.
- Inspect `lens.md`, topics, vocabulary, picks, routing rules, and evidence
  councils.
- Install or repair MCP and browser extension registrations.
- Pair or revoke a mobile device.
- Run scheduled local maintenance: `dream`, `consolidate`, stale-memory checks.

### Desktop App Requirements

- The installed artifact launches without a terminal.
- The app appears as a normal OS application, not a browser bookmark or CLI
  wrapper exposed to the user.
- First launch shows setup/status, not a stack trace.
- Provider fixes are buttons, detected repair actions, or copyable one-liners.
- The app shells out to `trinity-local` for product behavior.
- Desktop never stores product data outside `~/.trinity/`.
- Quitting the app leaves no required background service behind.
- Menu bar mode, global hotkey, and notifications are opt-in.
- Desktop owns mobile pairing and all mobile write authority.

### Architecture

Recommended first implementation:

- **Shell:** Tauri first if reusing existing HTML/CSS and static views is fastest;
  SwiftUI if native menu bar, hotkey, permissions, and pairing become the
  primary complexity.
- **Core:** existing Python package invoked through subprocesses. No forked
  desktop core.
- **State:** product data remains in existing `~/.trinity/` paths. UI-only app
  preferences may live under `~/.trinity/desktop/`.
- **IPC:** one desktop command adapter handles subprocess calls, JSON decoding,
  progress, cancellation, stderr capture, and remediation text.
- **Live progress:** prefer file-backed polling over a persistent daemon at
  first. A local socket supervisor is allowed only while the desktop app is
  open.
- **Deep links:** register `trinity://` for review, council, handoff, settings,
  and pairing routes.
- **Rendering:** reuse existing static pages where it buys speed, then move
  repeated UI primitives into a desktop component layer.

### Desktop State Additions

All additions live under `~/.trinity/`:

```text
~/.trinity/
+-- desktop/
|   +-- preferences.json
|   +-- recent_actions.jsonl
|   +-- window_state.json
+-- devices/
|   +-- paired_devices.json
|   +-- revoked_devices.jsonl
|   +-- pairing_sessions/
+-- remote_actions/
    +-- inbox/
    +-- completed/
    +-- failed/
```

Rules:

- `desktop/preferences.json` is UI-only and can be deleted safely.
- `devices/paired_devices.json` stores public keys, display names, scopes,
  created timestamps, and last-seen timestamps. It does not store prompts.
- `remote_actions` stores signed phone requests before the desktop translates
  them into normal council, handoff, rating, or override records.

### Desktop Acceptance Criteria

- A user can install once, launch desktop, run a first council, and review
  the chairman's verdict without touching the terminal after setup.
- Desktop shows live progress for multiple providers.
- Desktop pick-veto updates the same cortex override state as
  `cortex-override` and MCP `mark_pick_wrong`. (The prior rating UX —
  `council-rate` CLI, MCP `record_outcome`, the `rate_council` dispatch
  action — was retired 2026-05-21/22; chairman pick is the auto-recorded
  supervision signal now. Pick-veto on extracted cortex rules is the
  remaining user-side supervision surface.)
- Desktop can repair MCP and extension setup using JSON status contracts.
- Quitting desktop does not break terminal, MCP, Chrome extension capture, or
  existing static artifacts.

## Phase 3: Mobile App

Objective: let the user review and steer Trinity work from a phone without
making the phone a full Trinity node.

The first mobile app is a review-link companion. Its primary job is to open a
web/deep link to a council review, render the result in a mobile layout, and
send the user's rating or pick veto back through the paired desktop. Later it
becomes a paired controller that can dispatch `ask`, `council`, and `handoff`.

### Product Shape

First screen:

- open review link from browser, Messages, Mail, Notes, Shortcuts, or
  notification
- latest council review (chairman pick + agreed/disagreed claims)
- pick-veto actions on extracted cortex rules
- connection status to paired desktop

Expected workflows:

- Open `trinity://review/<id>` or a universal-link fallback from Messages,
  Mail, Notes, Shortcuts, browser, or notification.
- Treat the link as a pointer: the mobile app resolves review content from the
  paired desktop, a local/static artifact, or an explicit exported share bundle.
- Read chairman synthesis and provider outputs in a mobile-safe view.
- Mark an extracted cortex pick wrong (the remaining user-side
  supervision surface; the rating UX was retired 2026-05-21/22).
- Queue pick-veto actions offline when desktop is unreachable.
- Later: capture a prompt by typing or voice and send it to desktop as `ask`,
  `council`, or `handoff`.

### Link Contract

Initial routes:

```text
trinity://review/<council_id>
trinity://council/new?draft=<local_handoff_id>
trinity://handoff/<provider>?thread=latest
https://trinity.openclaw.ai/app/review/<council_id>
https://trinity.openclaw.ai/app/council/new?title=<optional-redacted-title>
```

Rules:

- `trinity://...` opens the installed desktop or mobile app.
- `https://trinity.openclaw.ai/app/...` is a universal-link bootstrap only:
  open the app if installed, show install/pair instructions if not.
- Hosted fallback routes may log route IDs and redacted metadata, never prompt
  content or provider outputs.
- Review content loads from paired desktop, local static artifacts, or an
  explicit user-exported share bundle.
- Links are pointers to ledger records, not state.
- Encrypted fragment payloads may support explicit share bundles because URL
  fragments are not sent to the server. That is a share feature, not the default
  private workflow.

### Pairing Model

Pairing is optional for read-only public/share review bundles and required for
any action that writes to the ledger.

1. Desktop shows a QR code with a one-time pairing URL.
2. Mobile scans it and generates a device keypair.
3. Desktop asks the user to approve the device and scopes.
4. Desktop stores the mobile public key under `~/.trinity/devices/`.
5. Mobile stores the desktop identity and access token in the OS keychain.
6. Each remote action is signed by the phone and acknowledged by desktop.

Initial transport:

- same-LAN HTTPS or WebSocket served only while desktop is open
- optional user-owned VPN/Tailscale address
- no OpenClaw relay for private prompt content or provider outputs

Future transport:

- push notifications containing only generic completion metadata by default
- optional encrypted relay for wake-up/routing metadata only
- user-owned cloud sync folder for action queues if it preserves the
  no-hosted-controller rule

### Mobile API Contract

The desktop exposes a small paired-device API. The MVP only needs review
and pick-veto endpoints (the rating UX retired 2026-05-21/22 — chairman
pick is the supervision signal; the phone has no rating button).

```text
GET  /v1/status
GET  /v1/reviews/{id}
GET  /v1/councils?limit=N
POST /v1/picks/{basin_id}/mark-wrong
```

Later paired-controller endpoints:

```text
GET  /v1/provider-health
GET  /v1/councils?status=active
POST /v1/actions/ask
POST /v1/actions/council
POST /v1/actions/handoff
POST /v1/devices/revoke
```

Every mutating response includes:

```json
{
  "ok": true,
  "action_id": "remote_...",
  "ledger_paths": ["~/.trinity/..."],
  "next_poll_after_ms": 1000
}
```

Mobile receives structured views for its screen, not unrestricted filesystem
access.

### Mobile Security

- Device scopes are explicit: `open_review`, `rate`, `mark_pick_wrong`,
  `view_summary`, `view_full_outputs`, `compose`, `launch`, `admin`.
- Default mobile scopes are `open_review`, `rate`, `mark_pick_wrong`, and
  `view_summary`.
- Raw provider outputs require separate desktop approval because they may
  contain sensitive prompt content.
- Lost-phone revoke is available from desktop and terminal.
- Desktop revalidates scopes before executing queued offline actions.
- Notifications default to generic copy unless the user opts into showing
  prompt titles.

### Mobile Acceptance Criteria

- A phone can open a council review link from common mobile apps.
- The same link degrades to an install/pair web fallback when the app is not
  installed.
- A paired phone can rate the winner and mark a pick wrong.
- Mobile rating and pick-veto actions update the same ledger paths as terminal,
  MCP, and desktop.
- If desktop is unavailable, mobile shows queued actions honestly and does not
  imply they were recorded.
- Later controller gate: phone starts a council on the paired desktop, watches
  completion, and records a verdict without a hosted controller.
- Revoking a phone immediately blocks new signed actions from that device.

## Implementation Sequence

### Milestone 0: Terminal Readiness

- Keep `status --json` stable enough for setup UIs.
- Add or verify JSON output for recent, active, memory health,
  provider health, review links, and device management.
- Make `handoff` reliable enough to be the cross-surface demo primitive.
- Define stable error envelopes for app callers.

Exit gate: desktop can build every first-run/setup screen from CLI JSON without
scraping prose or importing internals.

### Milestone 1: Desktop Shell

- Package the Cowork-style desktop app.
- Render setup, provider health, active councils, recent councils, and
  memory health.
- Launch council/handoff through the command adapter.
- Register `trinity://` review and handoff routes.
- Preserve static HTML artifact generation.

Exit gate: a non-coder can install once, open Trinity from a normal desktop app
entry point, run a council, and review it without touching the terminal.

### Milestone 2: Desktop Supervision

- Add global hotkey and menu bar mode.
- Add live progress streaming/polling.
- Add inline rating and cortex pick veto.
- Add memory/routing viewer.
- Add scheduled local maintenance and reminders.
- Add app update path.

Exit gate: desktop is materially better than terminal plus browser launchpad for
day-to-day supervision.

### Milestone 3: Mobile Review Links

- Define `trinity://review/<id>` and hosted universal-link fallback.
- Add share/open affordances to desktop and review pages so the phone can open
  the same review link.
- Build mobile review rendering.
- Add paired rating and pick-veto writes.
- Queue ratings while desktop is unreachable.

Exit gate: phone opens a review link, renders the result, and closes the rating
loop when paired.

### Milestone 4: Pairing And Remote Actions

- Add `devices/` schema.
- Add QR pairing.
- Add signed remote action queue.
- Add terminal list/revoke commands.
- Add local paired-device API.

Exit gate: a paired phone can submit a signed no-op action and desktop records
it under `remote_actions/` with a verifiable audit trail.

### Milestone 5: Mobile Controller

- Ship prompt composer.
- Show active councils and recent queue.
- Dispatch `ask`, `council`, and `handoff` through desktop.
- Add generic completion notifications.
- Keep offline queue status explicit.

Exit gate: phone -> desktop -> council -> phone review closes the loop without
a hosted controller (rating UX retired #134; phone shows the chairman's pick
+ routing_lesson, no rating step).

## Non-Goals For The First Cross-Platform Wave

- Running the full Trinity Python stack on iOS or Android.
- Storing private prompt content on OpenClaw infrastructure.
- Replacing Claude Code, Codex, Antigravity, Cursor, or any other harness.
- Creating a desktop-only database.
- Building a hosted web app for ordinary users' private corpora.
- Making mobile the primary surface for long raw model outputs.
- Shipping team/admin policy management in the consumer desktop app.

## Open Questions

1. **Tauri vs SwiftUI.** Tauri reuses existing surfaces faster. SwiftUI likely
   wins on menu bar, hotkey, permissions, and pairing polish.
2. **Away-from-home transport.** User-owned VPN preserves the trust model but
   adds setup friction. A relay improves reachability but can violate the brand
   if it ever sees prompt content.
3. **Universal-link domain.** Useful for mobile UX, but implementation must
   prove private prompt content never enters server-visible URLs, bodies, or
   logs.
4. **Desktop supervisor lifetime.** Menu bar mode may count as explicitly
   running. A surprise daemon does not.
5. **Notification privacy.** Generic notifications are the default. Prompt
   titles require opt-in.
6. **Windows/Linux desktop timing.** The CLI and Chrome extension are
   cross-platform earlier. A polished desktop app can ship macOS-first if the
   command contracts stay portable.

## Decision

Keep terminal complete because that is where Trinity's moat is real: MCP tools,
provider CLIs, local transcripts, and the Routing JSON ledger. Build desktop as
the normal local app for people who do not want a terminal. Build mobile first
as the review/rating companion, then expand it into paired dispatch.

The expansion succeeds only if every surface writes back into the same local
corpus. If a surface requires a separate cloud state store or hosted routing
controller, it is no longer Trinity Local.

## External References

- Claude Code quickstart, terminal-first install and session start:
  <https://code.claude.com/docs/en/quickstart>
- Claude Code MCP docs, local stdio MCP and configuration scopes:
  <https://code.claude.com/docs/en/mcp>
- Claude Code Desktop docs, local/remote/SSH session environments:
  <https://code.claude.com/docs/en/desktop>
- Claude Code web docs, cloud sessions and terminal handoff:
  <https://code.claude.com/docs/en/claude-code-on-the-web>
- Claude Code Remote Control docs, phone/browser control of a local session:
  <https://code.claude.com/docs/en/remote-control>
- Claude Code web quickstart, comparison of web, Remote Control, terminal, and
  desktop:
  <https://code.claude.com/docs/en/web-quickstart>
- Claude Desktop deep links, including Code and Cowork routes:
  <https://support.claude.com/en/articles/14729294-open-claude-desktop-with-a-link>
- Claude mobile deep links and universal-link Code routes:
  <https://support.claude.com/en/articles/14898120-open-the-claude-mobile-app-with-a-link>
