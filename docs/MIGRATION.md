# Migration — macOS Shortcut → Chrome extension

> Effective with the v1.0 launch wave. Existing macOS-Shortcut installs
> keep working; nothing breaks. This document explains the *new* path
> and why it's the recommended default.

## TL;DR

If you're on macOS today and `~/.trinity/portal_pages/launchpad.html`
already opens and dispatches: **you're fine, do nothing right now.**
The Shortcut is now the legacy tier-2 fallback. Whenever you have ten
minutes, install the browser extension to gain Linux/Windows support,
faster click → council latency, and structured error responses.

If you're on Linux or Windows: the extension is the only working path.
The Shortcut never worked off macOS — silent breakage was the bug.

## What changed

Before the transition, every launchpad button click fired a
`shortcuts://run-shortcut?name=Trinity%20Dispatch&input=…` URL that
only macOS Shortcuts could intercept. The URL handler was invisible
on Linux/Windows; clicks went nowhere with no error.

After this release the launchpad routes each click through three tiers
in priority order:

1. **Chrome extension** — `chrome.runtime.sendMessage(<id>, …)` to a
   local extension that forwards to a Native Messaging helper
   (`trinity-local-capture-host`) on every platform Chromium runs on.
2. **macOS Shortcut** — the legacy `shortcuts://` URL. Unchanged from
   the prior release; kept so existing macOS installs don't break.
3. **Inline install banner** — when neither tier is wired up, the
   launchpad surfaces a one-paragraph banner that links here.

The dispatch chooser cached the detection state in `sessionStorage`
so normal clicks pay no probe latency (verdict
`council_fb374b01311885cc`).

## Upgrade path

### macOS (Shortcut user today)

```bash
# 1. Load the extension manually (one-time).
#    Open chrome://extensions in Chrome, enable Developer mode,
#    click "Load unpacked", and select browser-extension/ in this repo.
#    Copy the 32-character ID Chrome assigns.

# 2. Register the Native Messaging manifest with Trinity:
trinity-local install-extension --extension-id <ID>

# 3. (Optional) keep the Shortcut around for tier-2 fallback — it
#    costs nothing and means the launchpad still works if the
#    extension is disabled.
```

After step 2 every click goes through tier 1. The Shortcut never
fires unless the extension fails. You can keep `shortcut-install` as
a safety net or drop it.

### Linux

```bash
# 1. Load the extension manually in Chromium / Brave / Edge
#    (chrome://extensions → Developer mode → Load unpacked).

# 2. Register the Native Messaging manifest:
trinity-local install-extension --extension-id <ID>

# 3. Install a desktop launcher entry so the launchpad appears
#    in your application menu:
trinity-local install-launcher
```

The shortcut path was never functional on Linux. If you previously
ran `trinity-local shortcut-install` on Linux, that was a no-op.

### Windows

```bash
# 1. Load the extension manually in Chrome / Edge.
# 2. Register the Native Messaging manifest:
trinity-local install-extension --extension-id <ID>
# 3. Install a Start Menu shortcut:
trinity-local install-launcher
```

Same shape as Linux. If you used Trinity on WSL with the Shortcut,
the Shortcut never reached your Windows host — it stayed inside the
WSL filesystem. The extension is the first cross-host path Trinity
has ever shipped on Windows.

## Why both paths still exist

The macOS Shortcut path predates the extension. Removing it would
break every existing macOS user who hasn't yet loaded the unpacked
extension. The transition pattern is the same one Chrome itself uses
for new APIs: the new path becomes the default, the old path stays as
a fallback, and the old path eventually retires once telemetry shows
nobody uses it.

For Trinity specifically:

- The Shortcut still works on macOS for 100% of installs that already
  ran `shortcut-install`. Don't break what works.
- The extension is platform-portable and returns structured errors
  (`native-host-unavailable`, etc.) that the launchpad surfaces as a
  precise install hint instead of a silent no-op.
- The two paths now have **full button parity** as of Phase 4b:
  every launchpad control has a narrow action-allowlist entry in
  `capture_host.ACTION_ALLOWLIST` (see the table in the
  "Cross-platform parity" section below). The macOS Shortcut path
  stays as tier-2 fallback so existing installs keep working,
  but no button is Shortcut-only anymore.

## When the Shortcut path actually retires

Shortcut retirement is gated on measurement infrastructure we don't
have yet. Trinity ships v1.0 without dispatch-tier telemetry; any
retirement commitment is a future gate, not a calendar date. Concretely:
the macOS Shortcut path will not begin a deprecation-warning release
until (a) an opt-in measured release lands that reports per-install
dispatch-tier usage and (b) that release shows the extension carrying
the dispatch load on macOS for an extended sample. One release after
the warning lands, the path goes away.

Until then: it's a load-bearing fallback. The note printed by
`shortcut-install` (Phase 7) is friendly, not nagging.

## FAQ

### Cross-platform parity (as of Phase 4b)

All ten launchpad controls now have a narrow action-allowlist entry,
so every button works on Linux + Windows when the extension is
wired. The macOS Shortcut path remains as tier-2 fallback for
existing installs.

The current allowlist (capture_host.ACTION_ALLOWLIST):

| Kind | CLI command |
|---|---|
| launch-council | council-launch |
| ingest-recent | ingest-recent |
| stop-council | council-stop --status-token … |
| telemetry-enable / -disable / -reset-id | telemetry-enable / … / -reset-id |
| auto-chain-enable / -disable | auto-chain-enable / -disable |
| polish-auto-enable / -disable | polish-auto-enable / -disable |
| render-me-card | me-card --open |

Each entry is the narrowest possible surface — no `run_command`, no
arbitrary shell. Spoofed payloads can't trigger anything beyond the
specific CLI subcommand named above.

### Will my existing macOS install break when I upgrade?

No. The launchpad detects whether `chrome.runtime.sendMessage` is
reachable to a configured extension ID; if not, it falls back to the
Shortcut URL just like before. The only thing that changes is the
order of tiers — extension is tried first, and the result reaches the
chairman with structured `{ok, error, hint}` instead of just firing
and hoping.

### What if I don't want to install a browser extension?

Don't. The Shortcut path keeps working on macOS. If you're on Linux
or Windows and want to avoid the extension entirely, `trinity-local
serve` opens the launchpad over `http://localhost:8765` and you can
copy/paste commands from there into your terminal.

### What about Safari / Firefox users?

Safari doesn't ship Native Messaging, so there's no extension path
there today. Safari users on macOS fall through to the Shortcut tier
automatically. Firefox does ship Native Messaging with a different
manifest schema; `trinity-local install-extension --firefox` writes
the manifest, but the extension itself needs the Firefox-specific
`applications.gecko.id` field — see browser-extension/README.md.

### How do I check which tier is wired up?

```bash
trinity-local portal-html
# Prints the launchpad path AND the dispatch readiness snapshot:
#   {
#     "dispatch": {
#       "extension_configured": true,
#       "host_on_path": true,
#       "shortcut_applicable": true,
#       "shortcut_installed": true,
#       "ready": true,
#       "recommended_action": null
#     }
#   }
```

`ready: true` plus `recommended_action: null` means at least one tier
is fully wired. When `ready` is false, `recommended_action` tells you
exactly what to fix.

## See also

- `browser-extension/README.md` — extension architecture + Phase 4
  three-tier dispatch logic
- `docs/spec-v1.6.md` — full extension transition spec
- `trinity-local doctor` — pre-flight diagnostics + dispatch readiness
  check at session start
