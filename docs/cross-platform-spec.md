# Trinity Cross-Platform Spec

> Status: proposed expansion spec.
>
> This document defines the surface expansion path after the v1.0/v1.5 terminal
> and MCP product. It follows the product pattern Claude Code established:
> start with a full-power terminal engine, then wrap the same engine in desktop
> and mobile surfaces. Trinity copies the sequencing, not the trust model.
> Claude Code can use hosted cloud sessions; Trinity's default remains local,
> file-backed, and cross-provider.
>
> 2026-05-14 correction: the CLI remains the engine, but it is not the
> acquisition surface for non-coders. Trinity must launch like a normal desktop
> app, Cowork-style: install once, then double-click an app icon or use a menu
> bar entry. Mobile starts thinner than a full controller: it opens review links
> and closes the rating loop before it grows into paired remote dispatch.

## Reference Pattern

Claude Code's useful lesson is not "build a bigger app." It is:

1. **Terminal first.** The CLI is the complete product, scriptable and useful
   before any graphical shell exists.
2. **Same engine everywhere.** Terminal, IDE, desktop, web, and mobile attach
   to the same underlying Claude Code capability rather than becoming separate
   products.
3. **Desktop adds supervision.** The desktop app is strongest where the
   terminal is weak: visual diffs, multiple parallel sessions, preview servers,
   scheduled/local tasks, and at-a-glance status.
4. **Mobile starts and monitors work.** The phone is not the full development
   environment. It dispatches tasks, monitors progress, and lets the user steer
   or review while away from the keyboard.

Trinity's version:

1. **Terminal/MCP first.** `trinity-local` and `trinity-local --mcp` stay the
   authoritative engine.
2. **Desktop launch for ordinary users.** The CLI can be complete without being
   the default launch gesture. A packaged `Trinity.app` must be the visible
   entry point for users who will not live in a terminal.
3. **Same corpus everywhere.** Every surface reads and writes the same
   `~/.trinity/` corpus and schema.
4. **Desktop is a local cockpit.** It manages councils, handoffs, memories,
   ratings, and device pairing on the user's machine.
5. **Mobile starts as a review companion.** It opens web links to council review
   pages, lets the user rate or mark picks wrong, and only later grows into
   paired dispatch.

## Product Boundary

Trinity is not trying to become a chat app, IDE, or hosted agent runtime.

The job of each surface:

| Surface | Primary job | What it must not become |
|---|---|---|
| Terminal | Complete engine and scriptable control plane | The required day-to-day UI for non-coders |
| MCP | Agent-facing tool surface inside Claude Code, Codex CLI, Gemini CLI, Cowork | A private protocol tied to one harness |
| Desktop | Default non-coder launcher and local cockpit for councils, handoffs, memories, ratings, and pairing | A hosted dashboard or separate state store |
| Mobile | Open review links, rate outcomes, and optionally queue lightweight actions | A standalone full Trinity node in v1 |

The product boundary stays: **the harness owns the work surface; Trinity owns
the routing, memory, cross-provider continuity, and supervision signal.**

## Non-Negotiable Constraints

1. **The CLI remains complete.** Any user can uninstall the desktop and mobile
   apps and keep using `trinity-local` with no data loss.
2. **`~/.trinity/` remains canonical.** No SQLite migration, cloud database, or
   desktop-only state store in the first cross-platform wave.
3. **Prompt content stays local by default.** Mobile may send prompt text to the
   paired desktop node because both devices belong to the user. Trinity must not
   proxy private prompts through an OpenClaw server.
4. **No hosted controller.** A registry or update server is acceptable. A remote
   service deciding routes or holding private memory is not.
5. **Surfaces degrade independently.** If pairing fails, terminal and desktop
   still work. If desktop is closed, terminal and MCP still work. If MCP is not
   installed, desktop still launches councils through the CLI.
6. **File artifacts remain durable.** Council pages, memory pages, and outcomes
   remain reopenable from disk, not trapped in app memory.
7. **Every new action writes a ledger event.** Desktop and mobile interactions
   must feed the same `CouncilOutcome.metadata.user_verdict`,
   `council_feedback.jsonl`, cortex overrides, and routing ledger used by the
   terminal path.

## Phase 1: Terminal Foundation

Status: current product path. This is the surface to harden before graphical
expansion. It remains the complete engine for power users and automation, but
it is not the long-term launch surface for non-coders.

### Jobs To Be Done

- Install Trinity from a terminal.
- Register Trinity in Claude Code, Codex CLI, and Gemini CLI through MCP.
- Run councils directly from shell commands.
- Ask Trinity from inside a harness via MCP.
- Hand off a conversation from one provider to another without copy-paste.
- Dream and inspect local core memories.
- Rate outcomes so the personal routing table improves.

### Required Commands

The terminal product must keep these as stable public entry points:

| Command | Role |
|---|---|
| `trinity-local install-mcp` | Register MCP and install the `/trinity` Claude Code skill |
| `trinity-local install-app` | Install or repair the `Trinity.app` desktop launcher |
| `trinity-local doctor` | Pre-flight provider, auth, schema, and writable-home checks |
| `trinity-local council-launch --task "..."` | Run a multi-provider council |
| `trinity-local handoff <provider>` | Continue the latest thread in a different provider |
| `trinity-local dream` | Build memories from the user's prompt corpus |
| `trinity-local portal-html --open` | Regenerate and open the local launchpad |
| `trinity-local unrated` | Show councils that still need user verdicts |
| `trinity-local consolidate` | Rebuild cortex routing patterns |
| `trinity-local eval-build` / `eval-run` / `eval-show` | Score providers against the user's rejections |

The MCP surface remains the harness-facing mirror:

- `route`
- `ask`
- `run_council`
- `record_outcome`
- `search_prompts`
- `get_persona`
- `get_council_status`
- `get_picks`
- `mark_pick_wrong`
- `handoff`
- `get_eval_summary`

### Terminal Acceptance Criteria

- Fresh install reaches first successful council from shell in under 8 minutes
  on a clean Mac with authenticated provider CLIs.
- `/trinity` in Claude Code can run install, doctor, and first council without
  the user cloning the repo.
- `handoff` works from a real recent transcript and makes the "no copy-paste"
  wedge visible in one command.
- `doctor --json` is useful enough for desktop and mobile setup screens to
  consume without scraping prose.
- All terminal actions are deterministic subprocesses. No desktop daemon is
  required for the CLI path.
- `trinity-local install-app` can regenerate the launchpad and install
  `Trinity.app` to the user's normal app locations without requiring a source
  checkout script.

## Phase 2: Desktop App

Objective: make Trinity feel like a normal local desktop app without making it
always hosted.

The desktop app is the local cockpit over `~/.trinity/`: launch councils, watch
live progress, review results, rate outcomes, inspect memories, pair phones,
and manage provider health. It should make the existing launchpad obsolete as
the daily UI while preserving static HTML artifacts for sharing and durability.
For non-coders, the desktop app is the product surface: they should not need to
know whether `trinity-local`, Shortcuts, or MCP handled the action underneath.

### Product Shape

First screen:

- command bar for `ask`, `council`, and `handoff`
- active councils with provider progress
- unrated outcomes queue
- memory health and last dream/consolidate time
- provider/auth status from `doctor --json`

Expected workflows:

- Run a council from any selected text or clipboard content.
- Use a global hotkey to open Trinity over the current app.
- Watch parallel providers stream and finish without refreshing a browser page.
- Rate a completed council inline.
- Continue a Claude thread in Gemini or Codex from the desktop surface.
- Inspect `lens.md`, `picks.json`, `routing.json`, `topics.json`,
  `vocabulary.md`, and `core.md`.
- Pair or revoke a mobile device.
- Install or repair MCP registrations for harnesses.

Non-coder launch requirements:

- The installed artifact is named `Trinity.app`, appears in Applications or the
  Desktop, and opens without a terminal window.
- First launch runs a setup/doctor screen instead of expecting shell commands.
- Provider fixes are expressed as buttons or copyable one-liners, not stack
  traces.
- The app can repair its own launchpad, Shortcut, and MCP registrations.
- Power-user CLI commands remain visible as advanced details, not the main path.

### Architecture

Recommended first implementation:

- **Shell:** Tauri or SwiftUI. Tauri is preferred if the existing HTML/CSS
  surfaces can be reused quickly; SwiftUI is preferred if native menu bar,
  global shortcut, and device-pairing polish become the primary work.
- **Core:** existing Python package invoked as subprocesses. Do not fork a
  separate desktop-only core.
- **State:** `~/.trinity/` remains canonical. The app may keep UI preferences
  under `~/.trinity/desktop/`, but all product data stays in existing schema
  paths.
- **IPC:** local-only command channel:
  - app invokes `trinity-local` subprocesses for one-shot actions;
  - app may run an optional loopback or Unix-domain-socket supervisor while the
    desktop app is open;
  - no action should require an OpenClaw-hosted service.
- **Deep links:** register `trinity://` for commands such as
  `trinity://council/new`, `trinity://handoff/gemini`, and
  `trinity://review/<council_id>`.
- **Rendering:** reuse existing static pages and shared CSS where practical,
  but move repeated UI primitives into a desktop component layer instead of
  copying launchpad HTML into multiple screens.

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
- `devices/paired_devices.json` stores public keys, display names, created_at,
  last_seen_at, and scopes. It does not store raw prompts.
- `remote_actions` stores requested actions from paired devices before they are
  translated into normal council/handoff/rating records.

### Desktop Security

- Global hotkey and menu bar mode are opt-in.
- Any remote-dispatch capability is off until a phone is paired.
- First remote action from a new phone requires desktop approval.
- The app shows exactly which provider CLIs are installed and authenticated.
- The desktop app never asks for provider passwords. It delegates auth to the
  provider CLIs and reports status through `doctor`.

### Desktop Acceptance Criteria

- A user can run a first council from the desktop app after `pip install` or
  packaged desktop install, without opening the launchpad in a browser.
- A non-coder can relaunch Trinity by double-clicking `Trinity.app`; no terminal
  command is required after initial setup.
- Desktop can show live council progress for at least three providers.
- Rating from desktop updates the exact same ledger fields as
  `trinity-local council-rate` or MCP `record_outcome`.
- Quitting the desktop app leaves no required background service behind.
- Uninstalling the desktop app does not break terminal, MCP, or existing
  `~/.trinity/` data.

## Phase 3: Mobile App

Objective: let the user review Trinity work from the phone without making the
phone a full Trinity node.

The first mobile app is a review-link companion. It opens web links generated by
the desktop app or shared from a review page, renders the council result in a
mobile-safe view, and sends the user's rating or pick-veto back through the
desktop when paired. It does not run provider CLIs, local embeddings, cortex
consolidation, or the full Python stack.

Full remote dispatch comes after this link-review loop works. Starting with
links keeps the app useful even before a robust same-LAN pairing and transport
story exists.

### Product Shape

First screen:

- open-review link inbox
- latest council review
- unrated queue
- one-tap winner rating
- pick-veto actions exposed from the review page

Expected workflows:

- Open a `https://` or `trinity://review/...` link from Messages, Mail,
  Shortcuts, Notes, or a push notification.
- Read the chairman synthesis and provider outputs in a mobile layout.
- Rate completed councils with one tap.
- Mark an extracted pick wrong from the phone.
- Return to the original web review link when the mobile app is not installed.
- Queue ratings offline and submit when the paired desktop is reachable.
- Later: capture a prompt by voice, send it to desktop as `ask` or `council`.

### Pairing Model

Pairing is optional for read-only review links and required for any action that
writes to the ledger. The desktop remains the authority:

1. Desktop shows a QR code with a one-time pairing URL.
2. Mobile scans it and generates a device keypair.
3. Desktop approves the device and stores the mobile public key under
   `~/.trinity/devices/paired_devices.json`.
4. Mobile stores the desktop identity and an encrypted access token in the OS
   keychain.
5. Each remote action is signed by the phone and acknowledged by the desktop.

Initial transport for rating and later remote actions:

- same-LAN HTTPS or local-network WebSocket served only while desktop is open;
- optional manual Tailscale/WireGuard address for users who already have it;
- no OpenClaw relay in the MVP.

Future transport, after review-link MVP:

- push notifications for "council finished" without prompt content;
- optional encrypted relay for wake-up and routing metadata only;
- user-owned cloud sync folder for remote action queues if it preserves the
  no-hosted-controller rule.

### Mobile API Contract

The desktop exposes a small paired-device API. The MVP only needs review,
rating, and pick-veto endpoints; dispatch endpoints are reserved for the later
paired-controller milestone. The shape stays action-oriented so it mirrors the
dispatch registry instead of inventing a second product model.

```text
GET  /v1/status
GET  /v1/reviews/{id}
GET  /v1/councils?status=unrated|recent
POST /v1/councils/{id}/rate
POST /v1/picks/{task_type}/mark-wrong

Later paired-controller endpoints:
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

Mobile never receives unrestricted filesystem access. It receives only the
structured views needed for the screen it is showing.

### Mobile Security

- Device scopes are explicit: `open_review`, `rate`, `mark_pick_wrong`,
  `view_summary`, `view_full_outputs`, `compose`, `launch`, `admin`.
- Default mobile scope is `open_review`, `rate`, `mark_pick_wrong`,
  `view_summary`.
- Full raw provider outputs require a separate desktop approval because they may
  contain sensitive prompt content.
- Lost-phone revoke must be available from desktop and terminal:
  `trinity-local device-revoke <device_id>`.
- The phone can queue actions offline, but desktop revalidates scopes before
  execution.

### Mobile Acceptance Criteria

- A phone can open a council review link from Messages, Mail, Notes, Shortcuts,
  or a browser.
- The same link degrades to a web review page when the mobile app is not
  installed.
- A paired phone can rate the winner and mark a pick wrong from the review
  screen.
- Mobile rating and pick-veto actions update the same ledger paths as terminal
  and MCP actions.
- If the desktop is unavailable, mobile shows queued ratings and does not imply
  they have been recorded.
- Later controller gate: pairing completes in under 60 seconds on the same LAN,
  and a phone can start a council on the paired desktop, watch it complete, and
  rate the winner.
- Revoking a phone immediately blocks new signed actions from that device.

## Implementation Sequence

### Milestone 0: Terminal Readiness

- Keep `doctor --json` stable enough for app setup UIs.
- Add or verify machine-readable output for `unrated`, active councils, memory
  health, and provider health.
- Make `handoff` reliable enough to be the cross-surface demo primitive.
- Ensure every command has a deterministic error shape and a one-line fix.

Exit gate: terminal path can support desktop without the desktop scraping human
prose or reading internal Python objects.

### Milestone 1: Desktop Shell

- Package Trinity with a desktop launcher (`Trinity.app`) as the non-coder
  entry point.
- Render active councils, recent councils, unrated queue, and provider health.
- Launch council/handoff through subprocess calls.
- Register `trinity://` deep links.
- Preserve static HTML artifact generation.

Exit gate: a non-coder can install once, double-click `Trinity.app`, run a first
council, and review/rate it without touching the terminal again.

### Milestone 2: Desktop Supervision

- Add global hotkey and menu bar entry.
- Add live progress streaming.
- Add inline rating and cortex pick veto.
- Add memory viewer with shared design primitives.
- Add app update path.

Exit gate: desktop gives a materially better supervision loop than terminal plus
browser launchpad.

### Milestone 3: Mobile Review Links

- Define `trinity://review/<id>` and web fallback URL shapes.
- Add share/open affordances on desktop review pages.
- Build mobile review rendering for chairman synthesis, provider outputs, and
  verdict controls.
- Add paired rating and pick-veto writes.
- Queue ratings while desktop is unreachable.

Exit gate: phone opens a review link, renders the result, and closes the
rating loop when paired.

### Milestone 4: Pairing And Remote Actions

- Add `devices/` schema.
- Add QR pairing.
- Add signed remote action queue.
- Add terminal revoke/list commands.
- Add local paired-device API.

Exit gate: a paired phone can submit a no-op signed action and desktop records
it under `remote_actions/` with a verifiable audit trail.

### Milestone 5: Mobile Controller

- Build iOS first if constrained; Android follows after API shape stabilizes.
- Ship prompt composer, active council list, recent/unrated list, rating flow,
  and handoff action.
- Add local notifications for completion when reachable.
- Add offline queue with honest status.

Exit gate: phone -> desktop -> council -> phone rating closes the supervision
loop without touching a hosted controller.

## Non-Goals For The First Cross-Platform Wave

- Running the full Trinity Python stack on iOS or Android.
- Storing private prompt content on an OpenClaw server.
- Replacing Claude Code, Codex, Gemini CLI, Cursor, or any other harness.
- Creating a new desktop-only database.
- Building a hosted web app for ordinary users' private corpora.
- Making mobile the primary work surface for long raw model outputs.
- Shipping team/admin policy management in the consumer desktop app.

## Open Questions

1. **Tauri vs SwiftUI.** Tauri reuses the existing web surfaces faster. SwiftUI
   likely wins on menu bar, hotkey, permissions, and phone-pairing polish.
2. **Transport for away-from-home mobile.** Tailscale/manual VPN preserves the
   trust model but has setup friction. A relay improves reachability but risks
   violating the brand if it ever sees prompt content.
3. **Desktop supervisor lifetime.** The app should not create a surprise daemon.
   The open question is whether menu bar mode counts as "explicitly running" for
   most users.
4. **Notification privacy.** Completion notifications are useful, but titles can
   leak prompt content. Default to generic notifications unless the user opts in.
5. **Windows/Linux desktop timing.** Claude Code covers macOS, Windows, and
   Linux. Trinity's v1 scope is macOS-first; cross-platform desktop should wait
   until the macOS local-node model is stable.

## Decision

Keep terminal complete because that is where Trinity's moat is real: MCP tools,
provider CLIs, local prompt corpus, and the Routing JSON ledger. But package
desktop as the default launch path for non-coders. Build mobile first as a
review-link companion that closes verdict capture, then expand it into paired
dispatch once desktop pairing and transport are boring.

The expansion succeeds only if every surface strengthens the same local corpus.
If a surface requires a separate cloud state store or a hosted routing
controller, it is no longer Trinity Local.

## External References

- Claude Code overview: terminal, IDE, desktop app, and browser surfaces:
  <https://code.claude.com/docs/en/overview>
- Claude Code product page: desktop, terminal, IDE, web/iOS, Slack, and phone
  routing to desktop:
  <https://claude.com/product/claude-code>
- Claude Code web docs: cloud sessions, mobile monitoring, and moving tasks
  between web and terminal:
  <https://code.claude.com/docs/en/claude-code-on-the-web>
- Claude mobile deep links: Code tab, existing session, and new-session
  composer:
  <https://support.claude.com/en/articles/14898120-open-the-claude-mobile-app-with-a-link>
