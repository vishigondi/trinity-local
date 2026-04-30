# Trinity Local: Scale to Every Claude Code User

---

# Phase 0: Refactor / Stability

> Lands before MCP, hooks, or broader distribution. Exit criteria at the bottom.

## Phase 0 Status (audited against codex's checkpoint — 165 tests passing)

| # | Item | Status | Notes |
|---|------|--------|-------|
| 1 | Embedding dim fix | ✅ done | `embed_tfidf(text, dim=dim)` confirmed in `embeddings/__init__.py` |
| 2 | Unify council run-state | ✅ done | `council_status.py` + `runner_pid`/`runner_pgid` in run-state; `os.setpgrp()` in `council_runner.py`; stop handler reads both old `metadata` and new top-level keys. |
| 3 | Remove browser-owned product state | ✅ done | `ACTIVE_OPERATION_KEY` gone from portal_page.py. Only telemetry-dedupe localStorage remains (allowed per plan). |
| 4 | Split portal_page.py | ✅ done | 1,790 lines → `portal_page.py` (35), `portal_data.py` (348), `portal_template.py` (1260), `portal_install.py` (163), `portal_runtime.py` (37) |
| 5 | Share polling runtime JS | ✅ done | `portal_runtime.py` with `portal_runtime_js()` — both launchpad and live council page inject the same `buildShortcutUrl` + `loadStatusScript` (with `!token` guard fixed on launchpad). |
| 6 | Centralize Launchpad refresh | ✅ done | All callers use `refresh_launchpad()` via `refresh.py`. |
| 7 | Standardize subprocess execution | ✅ done | `subprocess_utils.py` with `run_with_runtime_env()`. Wired into `providers.py`, `adapters.py`. |
| 8 | Centralize runtime env | ✅ done | `runtime_env.py` with `build_runtime_env()`, `runtime_path_prefix()`. Used by subprocess_utils, dispatch_runner, shortcut_setup. |
| 9 | Complete state path migration | ✅ done | All duplicate `*_dir()` functions removed from `council_runtime.py`, `review.py`, `shortcut_setup.py`, `research/embeddings.py`, `research/hard_eval.py`, `research/ranking.py`. All use `state_paths.*` imports. |
| 10 | Harden council parsing | ✅ done | `tests/test_council_runtime.py` added with regression cases |
| 11 | Normalize config loading | ✅ done | `load_config(required=False)` for read-only commands; only provider-requiring commands call with `required=True`. |
| 12 | Deduplicate task-kind classification | ✅ done | `task_kinds.py` with `guess_task_kind()`. `watch_runtime.py` and `research/replay.py` both import from it. |
| 13 | Fix dispatch wrapper portability | ✅ done | `dispatch_runner.py` does runtime env construction; `shortcut_setup.py` generates a shell launcher rather than an absolute-path Python shebang. |
| 14 | Operator surfaces (cache-stats, watch errors) | ✅ done | `commands/cache.py` with `cache-stats`/`cache-clear`; `commands/status.py` reads `watch_errors.jsonl`. |
| 15 | Deprecate old council-html path | ✅ done | `council-html` now requires `--outcome`, always uses `write_unified_council_page`. `render_review_html`/`write_review_html` deleted from `council_review.py`. |
| 16 | Legacy module cleanup | ✅ done | `commands/run.py`, `coordinator.py`, `runner.py`, `prompts.py` deleted. `scoreboard` moved to `commands/status.py`. |
| 17 | Vendor static lib prep | ❌ not started | (Implemented as Phase 6) |

**Phase 0 is complete.** All 17 items done. See Phase 1+ for distribution work.

## 1. Fix correctness bugs

1. Fix embedding fallback dimension mismatch in `embeddings/__init__.py:71` — `embed_tfidf(text)` ignores the `dim` parameter and always returns 256d, but the cache key uses the requested 512d. Fix: pass `dim=dim` to `embed_tfidf`. One line.
2. Verify k-NN advisory works correctly without `[mlx]` installed (cosine similarity currently returns 0.0 for all queries due to length mismatch).
3. Add regression tests for fallback embedding dimensions and cached retrieval correctness.

## 2. Unify council run-state

Replace the split between `council_status/` (operation lifecycle) and `council_progress/` (per-member progress) with one disk-backed file per council launch.

**Schema for unified run-state file** (`~/.trinity/council_runs/<status_token>.json`):
```json
{
  "status_token": "...",
  "bundle_id": "...",
  "council_id": "...",
  "task_text": "...",
  "status": "running|done|failed|canceled",
  "members": ["claude", "gemini"],
  "member_progress": {
    "claude": { "status": "done", "reasoning_summary": "...", "completed_at": "..." },
    "gemini": { "status": "running", "started_at": "..." }
  },
  "synthesis": { "status": "pending|running|done" },
  "review_path": "/path/to/review.html",
  "runner_pid": 12345,
  "runner_pgid": 12345,
  "started_at": "...",
  "completed_at": "...",
  "error": null
}
```

**Stop semantics:** `runner_pid` is the council runner's Python process; `runner_pgid` is its process group. Stop sends SIGTERM to the pgid (kills runner + all child provider subprocesses in one call). The runner must call `os.setpgrp()` early so child subprocesses inherit the group.

Steps:
1. Create `council_run_state.py` with read/write helpers for this schema (also add `council_runs_dir()` to `state_paths.py`).
2. Update `council_runner.py` to call `os.setpgrp()` on startup and write unified state instead of calling `council_progress` and `council_status` separately.
3. Update stop flow (`commands/council.py`) to read `runner_pgid` and signal the group.
4. Update Launchpad and live review page to read only this file.
5. Delete `council_progress.py` and `council_status.py` once migrated; add a one-time migration helper that converts any in-flight files to the new format.

## 3. Remove browser-owned product state

1. Remove `ACTIVE_OPERATION_KEY` localStorage (Launchpad active council tracking).
2. Remove council review selection localStorage (preferred answer stored in browser).
3. Both should be derived from disk-backed Trinity files:
   - Active council → scan `~/.trinity/council_runs/` for `status=running`
   - Preferred answer → `council_feedback.jsonl` (already exists)
4. Keep localStorage only for low-risk UI concerns: telemetry upload dedupe hash/timestamp.

## 4. Share client runtime logic

Extract a shared browser JS runtime (inline script block or injected file) used by both the Launchpad and the live review page:
- `loadStatusScript()` — poll status from disk-backed JS file
- `loadProgressScript()` — poll member progress
- `stopCouncil()` — trigger stop via Shortcut
- `handleCompletion()` — redirect/reload on done/failed/canceled

Both pages currently duplicate this logic. Extract once, render into both pages from the same Python source.

## 5. Split oversized frontend modules

`portal_page.py` is 1,858 lines. Split into:
- `portal_data.py` — builds the `pageData` dict (all Python/state logic)
- `portal_template.py` — HTML template string
- `portal_js.py` — embedded JS/CSS helpers (polling runtime, petite-vue app)
- `portal_install.py` — launcher/install helpers (`write_launchpad_app`, `install_launchpad_shortcuts`)

Consider similar split for `council_review.py` once the old review path is deprecated.

## 6. Centralize Launchpad regeneration

`write_portal_html()` is called from 12 sites across 3 command modules. Add one `refresh_launchpad()` helper and route all calls through it. Ensures consistent behavior (title, options, error handling) across council/settings/ingest transitions.

## 7. Standardize subprocess execution

Add shared helpers in a new `process.py` (or `exec_utils.py`):
- `run_checked(cmd, ...)` — raises on non-zero, consistent error formatting
- `run_captured(cmd, ...)` — returns stdout/stderr, never raises
- `run_background(cmd, ...)` — fire-and-forget with logging

Standardize across:
- `providers.py` — CLI provider subprocess calls
- `shortcut_setup.py` — osacompile, shortcuts sign, open
- `daemon_manager.py` — launchctl calls
- `adapters.py` — version detection calls
- `portal_page.py` — sips, iconutil, lsregister calls

## 8. Centralize runtime environment construction

One shared `_build_env()` helper used everywhere a subprocess needs PATH injection:
```python
def build_subprocess_env(*, extra: dict | None = None) -> dict:
    env = os.environ.copy()
    prepend = [venv_bin(), Path.home() / ".local/bin",
               "/opt/homebrew/bin", "/usr/local/bin"]
    env["PATH"] = ":".join(str(p) for p in prepend) + ":" + env.get("PATH", "")
    if extra:
        env.update(extra)
    return env
```

Reuse in: providers, dispatch wrapper, daemon plist env, shortcut setup, adapter checks.

## 9. Complete state path migration

`state_paths.py` already exists but most modules still define their own duplicate `*_dir()` functions. Complete the migration:
- `council_runtime.py` — still defines `prompt_bundles_dir()`, `council_outcomes_dir()`
- `council_review.py` — still defines `review_pages_dir()`
- `review.py` — still defines `_reviews_dir()`
- `task_runtime.py` — still defines `tasks_dir()`, `task_sync_dir()`
- `telemetry.py` — still defines `telemetry_settings_dir()`
- Research modules — `_research_dir()` defined 3 separate times in `embeddings.py`, `hard_eval.py`, `ranking.py`
- `portal_page.py` — still defines `portal_pages_dir()`

Add missing paths to `state_paths.py` (analytics dir, telemetry settings dir, watcher dir, research subdirs) and delete duplicates.

## 10. Harden council output parsing

`council_runtime.py:315` and `:331` — `parse_synthesis_sections()` and `parse_peer_review_sections()` use brittle header matching that collapses silently on minor LLM wording variation.

Add:
- Case-insensitive header matching
- Optional numbering (`## 1. Differences` vs `## Differences`)
- Minor wording variation tolerance
- Fallback: if section parse fails, return the full text in a `"raw"` key rather than returning empty

## 11. Normalize config loading

`config.py:57` raises `FileNotFoundError` on missing config — but `status`, `telemetry-show`, and other read-only commands don't need provider config and should work offline/pre-setup.

Decide one rule and apply it consistently:
- **Option A**: Return an empty/default `AppConfig` for read-only commands (preferred)
- **Option B**: Hard-fail everywhere with a clear error message

Annotate which commands require config at registration time so the behavior is explicit.

## 12. Deduplicate task-kind classification

`_guess_task_kind()` exists in two places:
- `watch_runtime.py:167` — takes `(text, provider)`, more complete
- `research/replay.py:81` — comment says "mirrors watch_runtime" but has drifted (missing provider param, different keyword sets)

Move to `utils.py` or `task_classification.py`. Only after deduplication should embedding-based classification be considered.

## 13. Fix dispatch wrapper portability

`shortcut_setup.py:70` bakes the absolute Python path into the shebang at install time. If the venv is relocated or recreated, the wrapper silently breaks.

Fix: make the wrapper do runtime venv detection rather than rely on the shebang:
- Store the venv root path as a variable in the wrapper body (not the shebang)
- On startup, verify the venv Python exists; if not, search known fallback locations
- `#!/usr/bin/env python3` alone is insufficient — it picks up system Python, not the venv

## 14. Add operator surfaces for background behavior

1. Surface watch-loop error count in `trinity-local status` output — read `analytics/watch_errors.jsonl`, show count and last error timestamp.
2. Add embedding cache commands:
   - `trinity-local cache-stats` — entries, size, path, backend
   - `trinity-local cache-clear` — wipe and confirm

## 15. Deprecate old council review path

`commands/council.py:197` still calls `write_review_html()` (old path) for the `council-html` command. `write_unified_council_page()` is the real UX.

1. Route `council-html` through `write_unified_council_page()`
2. Delete `write_review_html()` and `render_review_html()` from `council_review.py` once migrated
3. Deeper legacy cleanup (commands/run.py, coordinator.py, runner.py, prompts.py) last — don't move until active paths are stable

## 16. Vendor static library prep

> Implementation lives in **Phase 6 — Self-Hosted Static Libraries**. Item kept here only as a Phase 0 reminder that this work bridges into the distribution phase. No additional spec needed at the Phase 0 level.

---

## Phase 0 execution order

1. Embedding dim fix (correctness bug, ~5 min)
2. Unify council run-state (biggest structural change)
3. Remove Launchpad/review localStorage (follow-on from #2)
4. Split portal_page.py (must precede shared JS extraction)
5. Share polling runtime JS (now possible after #4)
6. Centralize Launchpad refresh (natural during #4/#5)
7. Standardize subprocess + env handling (#7 and #8 together)
8. Complete state path migration (state_paths.py adoption)
9. Harden council parsing
10. Normalize config loading
11. Deduplicate task-kind classification
12. Fix dispatch wrapper portability
13. Add operator surfaces (cache-stats, watch-loop errors in status)
14. Deprecate old council-html path
15. Legacy module cleanup
16. (Vendor static lib prep — implemented as Phase 6)

## Phase 0 exit criteria

- One disk-backed source of truth for active councils; no browser-owned council lifecycle state
- Launchpad and live review share polling runtime logic
- Council status/progress survives page refresh cleanly
- Fallback embeddings work correctly offline (dim mismatch fixed, tests pass)
- All state path functions imported from `state_paths.py`; no module-local duplicates
- Subprocess calls use shared helpers with consistent PATH injection
- Config/install/runtime behavior is consistent across commands
- Dispatch wrapper resolution is deterministic and survives venv relocation
- `trinity-local status` shows watch-loop error count and last error
- `trinity-local cache-stats` and `cache-clear` work

---

## Context

Trinity Local's current install is a `git clone` + `setup.sh` flow — it works, but it won't scale. The goal is to make Trinity a seamless part of every Claude Code user's environment by distributing it through three channels native to how Claude Code works: as an **MCP server** (a local stdio process that exposes Trinity tools to Claude mid-conversation), as a **skill** (slash commands in every project), and via **hooks** (ambient intelligence without any user action). On top of that, a sharing flywheel turns every council into a growth artifact. Everything runs locally — no hosted server required.

This plan is ordered by impact/effort ratio: the highest-leverage moves first.

---

## Phase 1 — MCP Server Mode (`trinity-local --mcp`)

**Why**: MCP is an open protocol — the same stdio server works in Claude Code, Gemini CLI, and any other MCP-compatible host. Trinity tools become available mid-conversation in whichever AI CLI the user is currently in.

**Provider MCP support status** (verified):
| CLI | Add Command | Config File | Notes |
|-----|-------------|-------------|-------|
| Claude Code | `claude mcp add <name> -- <cmd>` | `~/.claude.json` → `mcpServers` | Full support |
| Gemini CLI | (edit settings directly) | `~/.gemini/settings.json` → `mcpServers` | Full support — same JSON format as Claude |
| Codex CLI | `codex mcp add <name> -- <cmd>` | `~/.codex/config.toml` (nested) | Full support — stdio + HTTP, `--env` flag for env vars; can also run as MCP server itself via `codex mcp-server` |

### Add `[mcp]` extra to `pyproject.toml`

```toml
[project.optional-dependencies]
mcp = ["mcp>=1.0"]
```

MCP Python SDK: https://github.com/modelcontextprotocol/python-sdk

### New file: `src/trinity_local/mcp_server.py`

Expose tools via `stdio` transport using the MCP SDK's `Server` class. Tools to expose in order of value:

| Tool | Maps to | Description shown to host AI |
|------|---------|------------------------------|
| `run_council` | `council-start` | Launch a multi-provider comparison for the current task |
| `get_recommendation` | watcher advisory | Which provider should I use for this task? |
| `watch_once` | `watch-once` | Scan recent sessions and surface insights |
| `get_elo` | `telemetry-show` | Current provider Elo ratings and win rates |
| `get_status` | `status` | Trinity health: configured providers, recent activity |
| `get_recent_councils` | portal page data | List recent councils with outcomes |

Tool descriptions must be self-contained — they're read by Claude, Gemini, and future hosts with no shared context. Front-load key trigger phrases.

Tool input schemas use JSON Schema. All tools return clean JSON or formatted text.

### Wire into `main.py`

Add `--mcp` flag to `argparse`. When present, call `mcp_server.run_stdio()` instead of dispatching to a command handler. No other changes to main.py.

### Generated plist for MCP daemon (optional, future)

The `daemon_manager.py` pattern is directly reusable for an MCP server daemon. Not needed for MVP — both Claude Code and Gemini CLI start the server on demand via their config.

---

## Phase 2 — One-Line Install

**Why**: Remove every friction point from the install path. One command after `setup.sh` and Trinity tools are available in every installed AI CLI.

### `trinity-local install-mcp` command

New subcommand in `commands/portal.py` (or new `commands/install.py`):

```bash
trinity-local install-mcp [--scope user|project]
```

Uses existing `check_all_adapters()` to detect which CLIs are installed, then writes MCP config only for those that support it:

**Claude Code** (`~/.claude.json`):
```json
{
  "mcpServers": {
    "trinity-local": {
      "command": "/path/to/venv/bin/trinity-local",
      "args": ["--mcp"]
    }
  }
}
```

**Gemini CLI** (`~/.gemini/settings.json`) — same JSON structure, same merge logic:
```json
{
  "mcpServers": {
    "trinity-local": {
      "command": "/path/to/venv/bin/trinity-local",
      "args": ["--mcp"],
      "env": {}
    }
  }
}
```

**Codex CLI** — preferred path is to shell out to its CLI rather than edit the TOML directly:
```bash
codex mcp add trinity-local -- /path/to/venv/bin/trinity-local --mcp
```
Codex writes the entry to `~/.codex/config.toml` itself (avoids us guessing the exact nested section name and TOML quoting rules). The `install-mcp` command should `subprocess.run(["codex", "mcp", "add", ...])` and surface stdout/stderr.

If any provider is not installed, skip its config and print the existing `render_missing_provider_guidance()` output for it — reuse the same guidance `setup.sh` already shows.

For project scope, creates `.mcp.json` in `Path.cwd()` (user's current project, not Trinity's source root). Add `.mcp.json` to `.gitignore` by default — venv paths are machine-specific.

### `setup.sh` update

Add `trinity-local install-mcp` call at the end of the existing setup sequence (after the missing-provider guidance step). Idempotent — safe to re-run.

### README one-liner

```bash
trinity-local install-mcp
```

One command after `setup.sh` — Trinity tools appear in Claude Code and Gemini CLI immediately.

---

## Phase 3 — Skills (Slash Commands)

**Why**: Skills are Claude Code's slash command system — separate from MCP. They give users discoverable `/<name>` commands that wrap multi-step Trinity workflows. Skills + MCP are complementary, not coupled: MCP gives Claude tools to call autonomously; skills give the user explicit, documented commands.

**Scope**: Claude Code only. Gemini CLI does not have an equivalent slash command system at the user-skill level. Codex CLI similarly lacks this surface. Trinity's CLI commands remain the cross-provider fallback.

### New directory: `.claude/skills/`

Commit three skills to the project root. Any project that includes `.claude/skills/` (committed or installed via `trinity-local install-skills`) gets these:

**`.claude/skills/council/SKILL.md`**
```yaml
---
name: council
description: Run a Trinity council — compare this task across Claude, Gemini, and Codex to find the strongest answer. Use when the user asks to compare providers, run a council, or wants a second opinion from multiple AI models.
argument-hint: [task description]
allowed-tools: Bash(trinity-local *) Read
---

!`trinity-local bundle-create "$ARGUMENTS" --goal "Find the strongest answer"`

Now start the council with the bundle ID above:
!`trinity-local council-start --bundle [bundle-id] --members claude gemini codex --primary-provider claude --open-browser`
```

**`.claude/skills/trinity-status/SKILL.md`**
```yaml
---
name: trinity-status
description: Show current Trinity Local status — provider Elo ratings, recent councils, and watcher insights. Use when the user asks about provider performance, which AI is best, or recent session activity.
allowed-tools: Bash(trinity-local status) Bash(trinity-local telemetry-show)
---

!`trinity-local status`
!`trinity-local telemetry-show`

Summarize the provider rankings and any notable recent activity.
```

**`.claude/skills/watch/SKILL.md`**
```yaml
---
name: watch
description: Trigger Trinity Local watcher — scan recent AI sessions and surface routing insights. Use when the user asks Trinity to analyze recent sessions or update recommendations.
allowed-tools: Bash(trinity-local watch-once --notify)
---

!`trinity-local watch-once --notify`
```

---

## Phase 4 — Hooks (Ambient Intelligence)

**Why**: Hooks make Trinity invisible and automatic. Users get value without changing their workflow.

### New file: `.claude/settings.json` (committed to Trinity repo)

```json
{
  "permissions": {
    "allow": ["Bash(trinity-local *)"]
  },
  "hooks": {
    "Stop": [
      {
        "matcher": ".*",
        "hooks": [
          {
            "type": "command",
            "command": "trinity-local watch-once --quiet 2>/dev/null || true",
            "async": true
          }
        ]
      }
    ]
  }
}
```

`Stop` hook fires after every Claude turn → runs `watch-once` in background → Trinity passively learns from every session without any user action. `async: true` so it doesn't slow Claude down.

### `trinity-local install-hooks` command (optional addition)

Writes `.claude/settings.json` into the current project. Useful for users who want Trinity intelligence in non-Trinity projects.

---

## Phase 5 — Growth Flywheel

**Why**: Distribution without sharing is a dead end. Each council should be a growth artifact.

### 5a. Shareable Council HTML

The existing `write_unified_council_page` already generates a beautiful dark-themed HTML page. Add:
- `trinity-local council-share --council <id>` → copies the review HTML to `~/Desktop/trinity-council-<id>.html` and opens it
- Add `<meta>` OG tags to council HTML (title = task, description = winner + one-line summary) so it previews correctly when shared via messaging apps or GitHub Gists

### 5b. "Battle Card" Export

New command `trinity-local council-card --council <id>` → generates a 1200×630 PNG summary card. Shows:
- Provider names and Elo ranking
- Key differentiator sentence from synthesis
- Trinity branding

**Implementation**: Use Pillow (already a hard dep — `Pillow>=10` in `pyproject.toml`). Cross-platform; works on macOS, Linux, Windows. Saved locally to `~/Desktop/trinity-card-<id>.png`. Drag to X/LinkedIn/Discord — no upload required.

### 5c. Anonymous Leaderboard

Telemetry already captures `elo_snapshot` events keyed by `share_install_id`. To make these into a leaderboard without running a real backend:

- **Upload endpoint**: One thin Cloudflare Worker (free tier covers this) accepts `POST /snapshots/<share_install_id>` with the user's anonymized JSON, validates schema, rate-limits per IP, and writes to R2. Worker code is ~50 lines, no Trinity-side state.
- **Aggregate**: A GitHub Actions workflow runs nightly, reads R2, merges Elo scores across users, writes `leaderboard.json` back to R2 (or to GitHub Pages).
- **Display**: A static `leaderboard.html` served from GitHub Pages fetches `leaderboard.json` and renders the rankings with Chart.js — no backend.
- **Portal link**: Add "View community leaderboard →" to the portal footer. Drives telemetry opt-in with "You're helping power this."

**Why a Worker and not direct S3 PUT**: a static-only host requires every uploader to have credentials, which leaks blast radius. A Worker gates writes, validates payload size/schema, and rate-limits abuse — the bare minimum for a public-facing endpoint. CF Workers free tier is 100k requests/day, far beyond expected telemetry volume.

### 5d. "Trinity Score" Badge for Repos

`trinity-local badge --format markdown` → generates a static badge string from local Elo data:
```
![Trinity Score](https://img.shields.io/badge/Trinity-Claude%20%E2%86%92%2087%25-8B5CF6?style=flat)
```

Uses `shields.io` static badge endpoint (no custom server needed — the data is baked into the URL). Shows which provider wins most for this repo's task type. Developers add it to README → viral spread.

---

## Phase 6 — Self-Hosted Static Libraries (Analytics + Reliability)

**Why**: `unpkg` and `jsdelivr` are third-party CDNs with no analytics. Hosting petite-vue and Chart.js on your own static host gives download counts = real install telemetry, faster load for users, and zero dependency on external uptime.

### Current situation

`portal_page.py` hardcodes:
```python
PETITE_VUE_MODULE = "https://unpkg.com/petite-vue@0.4.1/dist/petite-vue.es.js"
CHART_JS_SRC = "https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"
```

Every portal page load fetches from unpkg/jsdelivr — no visibility into how many users are active.

### Plan

1. Copy `petite-vue.es.js` and `chart.umd.min.js` into `assets/vendor/` in the repo (pinned versions, committed)
2. On `setup.sh` / `install-mcp`, copy them to `~/.trinity/vendor/` so the portal can load them via `file://` URL — works fully offline
3. Add a `TRINITY_CDN_BASE` env var: if set, portal loads libs from that URL instead of `file://`. Point it at your static host (Cloudflare Pages, S3, GitHub Pages)
4. The CDN host provides request logs = real usage analytics without any tracking code on users' machines

### Files to change

- `portal_page.py`: Replace `PETITE_VUE_MODULE` and `CHART_JS_SRC` constants with a `_lib_url(filename)` helper that checks for `~/.trinity/vendor/<file>` first, then `TRINITY_CDN_BASE/<file>`, then falls back to current CDN URLs
- `setup.sh`: Add vendor copy step

---

## Phase 7 — Update Mechanism

### `trinity-local version`

Prints the installed version (via `importlib.metadata.version("trinity-local")` — works for both `pip install -e .` and pip-installed users) and checks GitHub releases API for the latest tag. If behind, prints the update suggestion inline.

### `trinity-local update`

New command in `commands/install.py`:

1. Detect install mode: if `project_root()` has `.git/`, treat as git clone; otherwise treat as pip install.
2. Git clone mode: `git pull origin main && pip install -e .` inside the venv.
3. Pip mode: `pip install --upgrade trinity-local`.
4. Print version before → after.
5. Re-run `refresh_launchpad()` (the centralized helper from Phase 0 #6) to regenerate the portal page.

### Auto-update check (low-friction)

On `portal-html` generation, check if `last_update_check` in telemetry settings is >7 days old. If so, asynchronously call `https://api.github.com/repos/<owner>/trinity-local/releases/latest` (no auth needed for public repos). If a newer tag exists, add a small dismissable banner to the portal page with a `trinity-local update` copy-paste command.

---

## Critical Files to Modify / Create

### Phase 0 (refactor)
| File | Change |
|------|--------|
| `src/trinity_local/embeddings/__init__.py` | Pass `dim=dim` to `embed_tfidf()` (correctness fix) |
| `src/trinity_local/embeddings/backend_tfidf.py` | Honor `dim` parameter, default to 512 to match MLX |
| `src/trinity_local/council_run_state.py` | **New** — unified disk-backed run-state schema + helpers |
| `src/trinity_local/council_runner.py` | Write unified state, call `os.setpgrp()` on startup |
| `src/trinity_local/council_progress.py` | **Delete** after migration |
| `src/trinity_local/council_status.py` | **Delete** after migration |
| `src/trinity_local/state_paths.py` | Add missing dirs (analytics, telemetry settings, watcher, research, council_runs) |
| `src/trinity_local/process.py` | **New** — `run_checked`, `run_captured`, `run_background`, `build_subprocess_env` |
| `src/trinity_local/portal_page.py` | Split into `portal_data.py` / `portal_template.py` / `portal_js.py` / `portal_install.py` |
| `src/trinity_local/portal_runtime.py` | **New** — shared client JS runtime (polling, stop, completion) |
| `src/trinity_local/council_runtime.py` | Harden `parse_synthesis_sections` and `parse_peer_review_sections`; remove duplicate path helpers |
| `src/trinity_local/config.py` | Soft-fail for read-only commands; add explicit per-command annotation |
| `src/trinity_local/utils.py` | Move `_guess_task_kind()` here (or new `task_classification.py`) |
| `src/trinity_local/research/replay.py` | Remove duplicate `_guess_task_kind()` |
| `src/trinity_local/shortcut_setup.py` | Runtime venv detection in wrapper body, not shebang |
| `src/trinity_local/commands/status.py` | Add watch-loop error count + last error |
| `src/trinity_local/commands/cache.py` | **New** — `cache-stats`, `cache-clear` subcommands |
| `src/trinity_local/commands/council.py` | Route `council-html` through `write_unified_council_page` |

### Phase 1+ (distribution / growth)
| File | Change |
|------|--------|
| `src/trinity_local/mcp_server.py` | **New** — MCP stdio server |
| `src/trinity_local/main.py` | Add `--mcp` flag |
| `src/trinity_local/commands/install.py` | **New** — `install-mcp`, `install-hooks`, `install-skills`, `update`, `version` |
| `src/trinity_local/commands/portal.py` | (no changes — install commands moved to install.py) |
| `pyproject.toml` | Add `[mcp]` optional extra |
| `setup.sh` | Add vendor copy + `trinity-local install-mcp` call |
| `assets/vendor/petite-vue.es.js` | **New** — pinned local copy |
| `assets/vendor/chart.umd.min.js` | **New** — pinned local copy |
| `.github/workflows/leaderboard.yml` | **New** — nightly aggregation job |
| `infra/leaderboard-worker/` | **New** — Cloudflare Worker source for upload endpoint |
| `.claude/skills/council/SKILL.md` | **New** |
| `.claude/skills/trinity-status/SKILL.md` | **New** |
| `.claude/skills/watch/SKILL.md` | **New** |
| `.claude/settings.json` | **New** — Stop hook for ambient watch |
| `README.md` | Add `claude mcp add` + `install-mcp` one-liners, skills section, leaderboard link |

---

## Master Execution Order

```
Phase 0 — Refactor / Stability   (must land first)
├─ 1.  Embedding dim fix
├─ 2.  Unify council run-state
├─ 3.  Remove Launchpad/review localStorage
├─ 4.  Split portal_page.py
├─ 5.  Share polling runtime JS
├─ 6.  Centralize Launchpad refresh (refresh_launchpad)
├─ 7.  Standardize subprocess + env (process.py + build_subprocess_env)
├─ 8.  Complete state_paths.py migration
├─ 9.  Harden council parsing
├─ 10. Normalize config loading
├─ 11. Deduplicate _guess_task_kind()
├─ 12. Fix dispatch wrapper portability
├─ 13. Operator surfaces (status errors, cache-stats, cache-clear)
├─ 14. Deprecate old council-html path
└─ 15. Legacy module cleanup

Phase 1 — MCP Server                ← unlocks everything below
Phase 2 — install-mcp + setup.sh    ← cross-CLI distribution (Claude + Gemini)
Phase 3 — Skills (.claude/skills/)  ← Claude Code only
Phase 4 — Stop hook                 ← ambient learning
Phase 6 — Vendor static libs        ← analytics + offline reliability
Phase 7 — Update mechanism          ← retention
Phase 5b — Battle card export       ← shareable artifact
Phase 5a — Council share command    ← OG-tagged HTML
Phase 5d — Trinity score badge      ← README virality
Phase 5c — Leaderboard              ← needs telemetry critical mass + Worker
```

---

## Risks & Open Questions

- **Codex CLI MCP** — supported via `codex mcp add`. Phase 2 shells out to the CLI rather than writing TOML directly. Open question: should we use `--env` to inject Trinity-specific env vars (e.g. `TRINITY_HOME`)? Probably not — the MCP server respects `TRINITY_HOME` from the user's shell already.
- **Claude Code hook spec drift** — the `Stop` hook spec used in Phase 4 is current as of this plan but may evolve. Verify against `code.claude.com/docs/en/hooks` before implementing.
- **Process group migration** — Phase 0 #2 introduces `os.setpgrp()` in the runner. Any existing in-flight councils started before the upgrade will have no `runner_pgid` — the migration helper must handle missing-field cases.
- **Telemetry → leaderboard chain** — leaderboard (Phase 5c) requires meaningful upload volume. Don't ship until at least dozens of users opt in. Premature rollout shows an empty board and damages the social proof signal.
- **`Stop` hook safety** — silent `watch-once` from a hook means errors disappear into `2>/dev/null`. Trinity needs a separate path for hook errors → `~/.trinity/analytics/hook_errors.jsonl` so failures are recoverable without spelunking.
- **`--quiet` flag** — Phase 4's hook command uses `watch-once --quiet` but the flag may not exist yet. Add it as part of Phase 4 or reuse `2>/dev/null` redirect.

---

## Out of Scope (explicitly)

- Hosted backend / API / database
- Per-user authentication or accounts
- Web app / React frontend (static HTML only)
- Mobile clients
- Notification abstraction layer (notifications.py already covers macOS/Linux/Windows)
- Trinity exposing other providers as MCP backends (e.g. proxying `codex mcp-server` through Trinity) — interesting future direction, not in scope now
- Replacing existing Shortcuts dispatch with a different mechanism
- Migrating `~/.trinity/` to a different state root

---

## Verification

### Phase 0 exit
- `pytest -q` passes (target: ~170+ tests after regression coverage)
- `trinity-local watch-once` produces meaningful k-NN advisory output without `[mlx]` installed
- `~/.trinity/council_runs/<token>.json` contains a single unified record per launch
- Browser refresh during a running council preserves all state
- No `localStorage.getItem(ACTIVE_OPERATION_KEY)` references in `portal_page.py` outputs
- `trinity-local cache-stats` reports cache size and entry count
- `trinity-local status` includes watch-loop error summary
- Reinstalling Trinity to a different venv path doesn't break the dispatch wrapper

### Phase 1+ exit
- `trinity-local --mcp` responds to `tools/list` over stdio
- `claude mcp add trinity-local -- trinity-local --mcp` registers; tools visible in a Claude Code session
- `~/.gemini/settings.json` contains `mcpServers.trinity-local` after `install-mcp`
- `codex mcp list` shows `trinity-local` after `install-mcp`
- `/council` slash command appears in Claude Code with skills installed
- `Stop` hook silently triggers `watch-once` (verify `outcomes.jsonl` grows)
- Portal loads petite-vue + Chart.js from `~/.trinity/vendor/` (Network tab shows no unpkg requests)
- `trinity-local version` reports current version and identifies whether GitHub has a newer release
- `trinity-local update` upgrades cleanly without losing state
- `trinity-local council-card` produces a valid 1200×630 PNG via Pillow
- `infra/leaderboard-worker/` deployed; nightly Action writes `leaderboard.json`
