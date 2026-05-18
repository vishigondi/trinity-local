# Launcher Patterns

This note captures the closest product patterns to `trinity-local`'s planned
macOS architecture:

- file-backed local state
- lightweight or static UI
- native deep links / URL schemes
- local automation execution
- no always-on localhost server

## Closest matches

### Raycast

Useful ideas:

- `raycast://` deeplinks can trigger commands from the browser, terminal, or
  other apps.
- commands remain local and native, not web-hosted.
- confirmations can sit between a deeplink and command execution.

What to copy:

- a stable command address space
- a launcher as control plane, not as transcript store
- command-level deep links

What not to copy:

- requiring a full launcher app as Trinity's main UX

### Alfred

Useful ideas:

- workflows are explicit graphs of triggers, scripts, and actions
- strong support for URL opening, shell scripts, and AppleScript
- imported workflows can carry setup metadata and onboarding

What to copy:

- explicit trigger -> action chain
- installable automation recipe
- human-readable workflow configuration

What not to copy:

- making the user live inside the launcher UI

### LaunchBar

Useful ideas:

- custom URL scheme (`x-launchbar`)
- script-based actions
- background execution of local commands

What to copy:

- URL-driven local automation
- command library that can run in background

### Hookmark

Useful ideas:

- works across many apps through automation surfaces instead of owning the
  documents itself
- supports AppleScript, shell, Shortcuts, and x-callback-url
- uses asynchronous callback patterns when apps cannot answer synchronously

What to copy:

- cross-app context layer
- do not force one storage model across providers
- fallback hierarchy: native automation first, UI scripting last

### Obsidian URI

Useful ideas:

- custom URI protocol mapped to concrete app actions
- useful because the action space is small and stable

What to copy:

- action-oriented URI design
- argument encoding discipline

### Apple Shortcuts

Useful ideas:

- native URL-triggerable dispatch on macOS
- compatible with browser links
- can bridge URL -> shell -> file artifact -> app open

What to copy:

- use one named Shortcut as the native dispatcher
- keep browser pages dumb and static

## Conclusion

The shipped architecture is:

1. **Chrome-extension launch is the non-coder path:** the Trinity Chrome
   extension hosts the launchpad — click the toolbar icon to open the
   local launchpad/review cockpit without a terminal window. Native
   Messaging carries launchpad button clicks back to `trinity-local`.
   The earlier `Trinity.app` osacompile wrapper was retired pre-launch
   in favor of the cross-platform Chrome extension.
2. **Direct prompt → council** is the primary action: launchpad has a textarea + autofill suggestions; user types a prompt or picks a replay candidate; click fires `launch_council` via Shortcut.
3. Trinity writes `TaskRecord`, `PromptBundle`, and `CouncilOutcome` files.
4. The static launchpad page renders the personal routing table, the `/me` lenses card, and recent councils.
5. Launch actions use `shortcuts://run-shortcut?...`.
6. A single macOS Shortcut named `Trinity Dispatch` executes the local command via `~/.trinity/bin/trinity-dispatch`.
7. Finished councils write to `council_outcomes/`; the next launchpad render reflects them via on-demand `compute_personal_routing_table()` (no durable state file).
8. **Mobile starts as review links**: the phone opens a web/deep link to a
   council review page, then writes ratings through the paired desktop when
   available.
9. **Watchers are secondary** (`watch-once`, `watch-loop`) — opt-in for users who want background suggestion of council-worthy prompts. The primary path doesn't require them.

## Watcher layer (optional)

When enabled, watcher responsibilities are narrow:

- detect meaningful new transcript activity
- derive or update a `TaskRecord`
- decide whether to emit:
  - `start_council`
  - `recommendation`
  - `workflow_suggestion`
- regenerate the launchpad page
- optionally send a local notification

Watcher should not:

- host a server
- own long-running UI state
- attempt direct browser automation
- be the source of truth for task state

## Action taxonomy

Current dispatch actions (`src/trinity_local/dispatch_registry.py`):

- `launch_council` — primary path; user picks members + task
- `rate_council` — record user's winner choice (closes the supervision loop via `record_outcome`)
- `stop_council` — cancel an in-flight council
- `open_review` — open the unified council page
- `start_council` — alternative entry from a prepared bundle
- `council_iterate` — canonical iteration action (replaces continue/refine/auto-chain). Args: `{rounds: int, prompt: str|None}`. Legacy aliases (`council_continue`, `council_refine`, `council_auto_chain`) still accepted as input — they map to `council_iterate` via the dispatch shim — so old launchpad URLs and saved Shortcuts keep working.
- `open_path`, `open_url`, `run_applescript` — generic dispatch helpers

If multiple pending actions exist for the same task, priority order:

1. `launch_council` / `start_council`
2. `rate_council`
3. `open_review`
4. `recommendation` / `workflow_suggestion`

This keeps the launchpad from becoming noisy and ensures the primary CTA is always the most actionable one.
