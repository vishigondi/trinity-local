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

The best immediate architecture is:

1. File watchers detect transcript changes.
2. Trinity writes `TaskRecord` and `PendingAction` files.
3. A static launchpad page renders pending actions.
4. Launch actions use `shortcuts://run-shortcut?...`.
5. A single macOS Shortcut named `Trinity Dispatch` executes the local command.
6. Finished runs emit new actions such as `review_ready`.

## Next watcher layer

Watcher responsibilities should be narrow:

- detect meaningful new transcript activity
- derive or update a `TaskRecord`
- decide whether to emit:
  - `recommendation`
  - `start_council`
  - `review_ready`
  - `workflow_suggestion`
- regenerate the launchpad page
- optionally send a local notification

Watcher should not:

- host a server
- own long-running UI state
- attempt direct browser automation
- be the source of truth for task state

## Action priority

If multiple pending actions exist for the same task:

1. `start_council`
2. `review_ready`
3. `workflow_suggestion`
4. `recommendation`

This keeps the launchpad from becoming noisy and ensures the primary CTA is
always the most actionable one.
