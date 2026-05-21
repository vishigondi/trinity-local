---
class: aspirational
---

# Trinity Local: Scale to Every Claude Code User

> **Status (2026-05-19):** v1.0 shipped May 13–15, 2026 — see [`../CHANGELOG.md`](../CHANGELOG.md)
> and [`spec-v1.md`](spec-v1.md). Phases 0–8 below describe the v1 substrate (lens
> pipeline, ledger, embeddings, MCP server). All accurate as v1 reference.
>
> **Next trajectory = v1.5** (ships June 3, 2026) — see [`spec-v1.5.md`](spec-v1.5.md).
> The MCP-primary routing product with hippocampus + cortex two-tier memory. The
> The Loop Constitution double-loop substrate (formerly `src/trinity_local/loop/`)
> was removed alongside this trajectory pivot — pre-launch simplification. The
> `cull → re-verify → commit` mechanic the substrate prototyped will be rebuilt
> leaner inside v1.6's `plan_and_execute` (flagship Conductor + recursive
> verification) if v1.5's `ask` + `compare` ceiling on multi-step workflows.
> Spec is preserved in `docs/v2-loop-constitution.md` as architectural reference. Trained-coordinator v2 path is
> **sunset** (see sunset header in [`spec-v2.md`](spec-v2.md) for the architectural-
> decision record).
>
> **MCP surface (v1.0 canonical 5 + v1.5 trio + launch-arc `handoff`,
> 9 total):**
> v1.0 shipped `route` / `run_council` (subsumes `judge` via `responses=[...]`) /
> `record_outcome` / `get_persona` / `get_council_status`.
> (`search_prompts` retired 2026-05-17 — replaced by substring+recency
> heuristics on the hot path; `get_eval_summary` retired 2026-05-18 —
> agents ground via `ask` + picks.)
> v1.5 adds `ask` (cheap default single-call routing via kNN + cortex rules;
> returns `escalate_hint=compare` when trust is low), `get_picks`
> (agent-facing introspection into extracted routing patterns), and
> `mark_pick_wrong` (harness-callable user veto; halves effective
> trust per click, persists across consolidations). Launch-arc adds
> `handoff` (cross-provider conversation continuity). (Spec previously
> listed `get_eval_summary` as a second launch-arc addition — retired
> 2026-05-18 in the simplification pass; agents ground via `ask` + picks.)
>
> Hot-path
> search/autofill/replay are **embedding-free** (substring + recency +
> replay-value heuristics; no nomic on the read path). Personal routing
> table is **computed on demand** from `council_outcomes/*.json` (mtime+size
> cache, no durable state file). `lens-build` IS a single chairman call over
> MMR-sampled prompts (rejection-aware embedding distance for sample
> selection; ~/.taste/ no longer required). Memory tier collapsed:
> `PromptNode` + `TurnWindow` only (`TranscriptNode` retired). Iteration
> commands collapsed: `council-iterate --rounds N [--prompt P]` replaces
> council-continue/refine/auto-chain. Pair-wise `/me` lenses surface on
> the launchpad with copy-to-socials buttons. **Phase 9 (learned tiny
> coordinator) is aspirational** — sibling-repo work, not in this code.
> See `~/.claude/plans/whimsical-imagining-firefly.md` for the focused v1
> execution plan; this file is the long-form Phase 0–9 reference. **Many
> later sections of this file pre-date these changes** and reference dropped
> features (TranscriptNode, judge, peer-review) — treat status block above
> as canonical.

---

# Phase 0: Refactor / Stability

> Lands before MCP, hooks, or broader distribution. Exit criteria at the bottom.

## Phase 0 Status (audited against codex's checkpoint — 165 tests passing)

| # | Item | Status | Notes |
|---|------|--------|-------|
| 1 | Embedding dim fix | ✅ done | `embed_tfidf(text, dim=dim)` confirmed in `embeddings/__init__.py` |
| 2 | Unify council run-state | ✅ done | `council_status.py` + `runner_pid`/`runner_pgid` in run-state; `os.setpgrp()` in `council_runner.py`; stop handler reads both old `metadata` and new top-level keys. |
| 3 | Remove browser-owned product state | ✅ done | `ACTIVE_OPERATION_KEY` removed during portal_page split. Only telemetry-dedupe localStorage remains (allowed per plan). |
| 4 | Split portal_page.py | ✅ done | 1,790 lines → `launchpad_page.py` (35), `launchpad_data.py` (348), `launchpad_template.py` (1260), `launchpad_install.py` (163), `launchpad_runtime.py` (37). Renamed `portal_*` → `launchpad_*` per Tier 2 #4. |
| 5 | Share polling runtime JS | ✅ done | `launchpad_runtime.py` with `launchpad_runtime_js()` — both launchpad and live council page inject the same `buildShortcutUrl` + `loadStatusScript` (with `!token` guard fixed on launchpad). |
| 6 | Centralize Launchpad refresh | ✅ done | All callers use `refresh_launchpad()` via `refresh.py`. |
| 7 | Standardize subprocess execution | ✅ done | `run_with_runtime_env()` in `runtime_env.py` (the planned `subprocess_utils.py` split didn't materialize — both helpers fit in one module). Wired into `providers.py`, `adapters.py`. |
| 8 | Centralize runtime env | ✅ done | `runtime_env.py` with `build_runtime_env()`, `runtime_path_prefix()`, `run_with_runtime_env()`. Used by `providers.py`, `adapters.py`, `dispatch_runner.py`, `shortcut_setup.py`. |
| 9 | Complete state path migration | ✅ done | All duplicate `*_dir()` functions removed from `council_runtime.py`, `review.py`, `shortcut_setup.py`, `research/embeddings.py`, `research/hard_eval.py`, `research/ranking.py`. All use `state_paths.*` imports. |
| 10 | Harden council parsing | ✅ done | `tests/test_council_runtime.py` added with regression cases |
| 11 | Normalize config loading | ✅ done | `load_config(required=False)` for read-only commands; only provider-requiring commands call with `required=True`. |
| 12 | Deduplicate task-type classification | ✅ done | `task_types.py` with `guess_task_type()`. `watch_runtime.py` and `research/replay.py` both import from it. (Renamed from `task_kinds.py` per Tier 1 #3, 2026-05-12.) |
| 13 | Fix dispatch wrapper portability | ✅ done | `dispatch_runner.py` does runtime env construction; `shortcut_setup.py` generates a shell launcher rather than an absolute-path Python shebang. |
| 14 | Operator surfaces (cache-stats, watch errors) | ✅ done | `commands/cache.py` with `cache-stats`/`cache-clear`; `commands/status.py` reads `watch_errors.jsonl`. |
| 15 | Deprecate old council-html path | ✅ done | The `council-html` CLI subcommand was retired entirely; `council_runner.write_unified_council_page()` is the single page writer now and runs after every council. `render_review_html` / `write_review_html` deleted from `council_review.py`. Public surface for sharing council pages is `council-share`. |
| 16 | Legacy module cleanup | ✅ done | `commands/run.py`, `coordinator.py`, `runner.py`, `prompts.py` deleted. `scoreboard` CLI was moved to `commands/status.py` then removed entirely post-v1.5 — see §8.10. |
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

✅ **done (Phase 0 #10).** `council_runtime.parse_synthesis_sections()`
is the surviving parser — `parse_peer_review_sections` was retired
along with the peer-review terminology (Tier 2 #5: "drop verifier
terminology; use Synthesis JSON"). Regression cases in
`tests/test_council_runtime.py` cover case-insensitive headers,
numbered variants, and the `"raw"` fallback when section parse
fails. See Phase 0 Status table above for the canonical record.

## 11. Normalize config loading

`config.py:57` raises `FileNotFoundError` on missing config — but `status`, `telemetry-show`, and other read-only commands don't need provider config and should work offline/pre-setup.

Decide one rule and apply it consistently:
- **Option A**: Return an empty/default `AppConfig` for read-only commands (preferred)
- **Option B**: Hard-fail everywhere with a clear error message

Annotate which commands require config at registration time so the behavior is explicit.

## 12. Deduplicate task-type classification

> **Done (2026-05-12).** Moved into `task_types.py` as `guess_task_type()`.
> Both `watch_runtime.py` and `research/replay.py` import from it; the
> drifted duplicate in `research/replay.py` was removed. Renamed from
> `task_kind` → `task_type` per Tier 1 #3 to disambiguate from
> `category` (the coarser LMArena-aligned grouping).

Historical context: `_guess_task_kind()` had drifted across two call sites
with different keyword sets — `watch_runtime.py` took `(text, provider)`
and was more complete; `research/replay.py` was missing the provider
parameter. Embedding-based classification was deferred until after the
heuristic was canonical (still deferred — heuristic ships in v1).

## 13. Fix dispatch wrapper portability

`shortcut_setup.py:70` bakes the absolute Python path into the shebang at install time. If the venv is relocated or recreated, the wrapper silently breaks.

Fix: make the wrapper do runtime venv detection rather than rely on the shebang:
- Store the venv root path as a variable in the wrapper body (not the shebang)
- On startup, verify the venv Python exists; if not, search known fallback locations
- `#!/usr/bin/env python3` alone is insufficient — it picks up system Python, not the venv

## 14. Add operator surfaces for background behavior

> Retired 2026-05-18 pre-launch. The watcher subsystem (commit 07ea7da)
> and the embedding cache (commit cc52b3b) were both killed in the
> simplification pass. The items below are preserved as historical
> Phase 0 record only.

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
- ~~`trinity-local status` shows watch-loop error count and last error~~ (watcher retired pre-launch)
- ~~`trinity-local cache-stats` and `cache-clear` work~~ (embedding cache retired pre-launch)

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

> Shipped pre-launch (different shape than this plan). The live
> canonical skill is at `skills/trinity/SKILL.md` (one bundled
> `/trinity` skill rather than three separate skills). The shape
> below is preserved as Phase 3 design history; the example commands
> reference retired CLIs (`bundle-create`, `install-skills`) and
> won't parse against the live CLI surface — refer to the live
> SKILL.md for current install/dispatch wiring.

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

**`.claude/skills/watch/SKILL.md`** *(retired 2026-05-18 with the
watcher subsystem kill — MCP `ask` fires passive ingestion now)*
```yaml
---
name: watch
description: (retired) Trigger Trinity Local watcher — scan recent AI sessions and surface routing insights.
allowed-tools: Bash(trinity-local ingest-recent)
---

!`trinity-local ingest-recent`
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
            "command": "trinity-local ingest-recent --deadline 1.0 2>/dev/null || true",
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
| ~~`src/trinity_local/portal_page.py`~~ | ✅ done — split into `launchpad_page.py` / `launchpad_data.py` / `launchpad_template.py` / `launchpad_install.py` (Tier 2 #4 rename `portal_*` → `launchpad_*`). |
| `src/trinity_local/launchpad_runtime.py` | ✅ done — shared client JS runtime (polling, stop, completion). |
| `src/trinity_local/council_runtime.py` | ✅ done — `parse_synthesis_sections` hardened (case-insensitive, numbered variants, `"raw"` fallback). `parse_peer_review_sections` retired with the verifier→synthesis rename (Tier 2 #5). |
| `src/trinity_local/config.py` | Soft-fail for read-only commands; add explicit per-command annotation |
| `src/trinity_local/task_types.py` | ✅ done — single `guess_task_type()` (renamed from `task_kind` per Tier 1 #3). |
| `src/trinity_local/research/replay.py` | ✅ done — drifted duplicate removed; imports from `task_types`. |
| ~~`src/trinity_local/shortcut_setup.py`~~ | ✅ retired pre-launch (commit 53db635) — Chrome extension Native Messaging replaced the macOS Shortcut dispatcher. |
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
├─ 11. Deduplicate guess_task_type() (task_kind → task_type rename, Tier 1 #3)
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
- ~~`trinity-local watch-once` produces meaningful k-NN advisory output without `[mlx]` installed~~ *(watcher retired pre-launch; MCP `ask` fires `ingest_recent()` passively now)*
- `~/.trinity/council_runs/<token>.json` contains a single unified record per launch
- Browser refresh during a running council preserves all state
- No `localStorage.getItem(ACTIVE_OPERATION_KEY)` references in `portal_page.py` outputs
- ~~`trinity-local cache-stats` reports cache size and entry count~~ *(embedding cache retired pre-launch)*
- ~~`trinity-local status` includes watch-loop error summary~~ *(watcher retired)*
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


---

# Phase 8 — Trinity as Routing Substrate

> **The product boundary:** Trinity is not a workspace. It is the routing substrate beneath every harness. Claude Code, Codex, Gemini Code, Cowork, Cursor — they own the work surface. Trinity owns the question: **"Which intelligence should be used here, and how confident are we?"** The harness asks. Trinity answers, runs councils when needed, records outcomes, and gets smarter for every harness.

**Strategic frame:** the coordinator stays small because it does not do the task. It selects models and roles; the larger models do the work. The moat compounds because every harness that calls Trinity contributes to one routing graph that no single model provider can see — Claude Code's outcomes train Codex's recommendations, and vice versa.

**Sharpest positioning:** *Trinity is the exchange layer for model intelligence. Harnesses are brokers. Models are liquidity providers. Trinity routes.*

## 8.-1 The TRM north star (why this phase exists)

Four convergent results give Phase 8 its destination:

| Year | Paper | Claim |
|------|-------|-------|
| 2018 | Lottery Ticket Hypothesis | Useful computation lives in a sparse subnetwork inside a dense scaffold. |
| 2024 | HRM (Sapient Intelligence) | A 27M-param two-timescale recurrent net beats frontier LLMs on ARC-AGI / Sudoku-Extreme via latent reasoning. |
| 2025 | TRM (Samsung SAIL Montréal) | Strip HRM further: 7M params, single network, recursive self-correction. The hierarchy was decorative; the recursion is the active ingredient. |
| 2026 | TRINITY (this project) | The tiny thing doesn't even need to do the reasoning — it coordinates models that can. Recursion = multi-turn delegation to LLMs. |

All four answer one question: **where does capability actually live?** Convergent answer: not in parameter count, but in the structure of the controller.

For Trinity Local that means:

- **The router IS the product.** Not the Launchpad, not the council UI, not the harness integration. Those are scaffolding for the controller to live and learn inside.
- **Phase 8 is dataset-construction, not dashboard polish.** Every artifact in this phase — the hierarchical memory index, the Chairman Routing JSON, the cross-user aggregation — exists to feed a future learned routing head. Phase 9 (below) is where that head gets built.
- **The reference implementation pattern**: a tiny base model (Qwen3-0.6B-class) + a small learned routing head (~10K params) selecting among frontier models. TRM's recursive self-correction, applied at the orchestration layer instead of the latent-reasoning layer.
- **Compute will keep getting commoditized.** Durable IP migrates to whatever small, learned thing decides how that compute gets organized. Lottery Ticket implied it. HRM/TRM proved it at the architecture layer. Trinity is the proof at the orchestration layer.

**The bar shifts.** A feature is "done" in Phase 8 only if it increases either the *quality* or the *quantity* of supervision signal available to the Phase 9 controller. Anything that asks the user to "use Trinity as a workspace" dilutes that signal and gets pushed down the queue.

## 8.0 Architectural commitments

> Shipped pre-launch (different shape than this plan). Phase 0
> sections 8.x below are preserved as design history; the example
> tool list + state paths + module names reference the design's
> original shape, not what shipped. Translations:
>
> - **MCP surface** (8.1): plan said 6 tools (`route`, `judge`,
>   `run_council`, `record_outcome`, `search_prompts`, `get_persona`).
>   Live ships 9: canonical 5 (`route`, `run_council`,
>   `record_outcome`, `get_persona`, `get_council_status`) + v1.5
>   trio (`ask`, `get_picks`, `mark_pick_wrong`) + launch-arc
>   `handoff`. `judge` collapsed into `run_council(responses=[...])`
>   (Tier 1 #2); `search_prompts` dropped pre-launch.
> - **State paths** (8.4): plan said `~/.trinity/memory/...`. Live
>   ships `~/.trinity/prompts/...` (Tier 1 #1 rename, task #90).
>   `TranscriptNode` tier was dropped (Tier 2 #5, task #51).
>   `embeddings.bin` → `embeddings_matrix.npy`. Per-transcript
>   sharding collapsed into single JSONL files.
> - **Dual dispatch** (8.0 #3): plan said "MCP server + macOS
>   Shortcuts." Live dispatch is MCP + Chrome extension Native
>   Messaging; the Shortcut path was retired in Pass A (2026-05-17).
> - **Module names** (8.11 + Critical Files): plan said
>   `portal_*.py`. Live ships `launchpad_*.py` (Tier 2 #4, task #93).
> - **Test count target** (8.13 exit criteria): plan said "~150
>   tests after dead-code removal." Live: <!-- canonical:test_count -->1579<!-- /canonical --> + <!-- canonical:skipped_count -->4<!-- /canonical --> skipped.
>
> Refer to claude.md's Architecture section + state-layout diagram
> for canonical current state.

1. **Invisible-first.** The harness-facing API is the real product. The Launchpad dashboard is secondary — Datadog for model choice, not another IDE.
2. **Tool-triggered ingestion.** No daemons. When an MCP tool is called or the Launchpad is opened, run an incremental cursor-based ingest. Bounded freshness without background processes.
3. **Dual dispatch stays.** MCP server (cross-CLI) and macOS Shortcuts (power users) both route through `dispatch_registry.command_for_dispatch`. One source of truth for actions, two acquisition channels.
4. **Local + global blend.** Personal Elo from this user's outcomes, layered on top of an anonymous global routing prior. Cold-start works on day 1; personalization compounds.

## 8.1 The MCP tool surface

> **Superseded — shipped state is 9 tools, not 6.** This section's
> pre-launch snapshot listed `route` / `judge` / `run_council` /
> `record_outcome` / `search_prompts` / `get_persona` as the product
> surface. Since then: `judge` was collapsed into
> `run_council(responses=[...])` (Tier 1 #2) and `search_prompts` was
> retired in the 2026-05-17 simplification pass (substring + recency
> heuristics replaced the embedding-search hot path). Four tools were
> added: `get_council_status` rounding out the canonical lifecycle to
> 5, plus v1.5 trio (`ask` cheap default routing, `get_picks` agent
> introspection, `mark_pick_wrong` user-veto), plus launch-arc
> `handoff` for cross-provider continuity. Total: **9 tools**.
>
> Canonical current surface lives in
> [`../claude.md`](../claude.md#the-nine-mcp-tools-mcp_serverpy) and
> [`product-spec.md`](product-spec.md). The
> `TestMcpToolNameConsistency` / `TestMcpCanonicalSubsetCountClaims`
> guards in `tests/test_doc_count_consistency.py` pin the count
> against `src/trinity_local/mcp_server.py`.

## 8.2 Tool-triggered ingestion (replaces daemon)

**Rule:** ingestion runs *because* of tool use, not on a schedule.

| Trigger | What happens |
|---|---|
| `route()` / `search_prompts()` MCP call | Cursor-based incremental ingest of new transcript lines since last cursor; embed any new user prompts; update memory index. Bounded by tool-call rate. |
| `record_outcome()` MCP call | Update `PromptNode` and `CouncilOutcome` records inline. |
| Launchpad page render | Same incremental ingest; refresh autofill suggestions. |
| `Stop` hook (Claude Code only) | Optional. Calls `watch_once` after every turn. Off by default; enable explicitly via `trinity-local install-hooks`. |

**Cut entirely:** `daemon_manager.py`, `commands/daemon.py`, the auto-ingest LaunchAgent plist, all `auto-ingest-enable` / `auto-ingest-disable` commands. An MCP install must not write to `~/Library/LaunchAgents/`. That's the wrong primitive.

**Why this works:** the median user calls `route` or types into the Launchpad multiple times per session. Cursor ingest of a single new transcript file is sub-second. Staleness is naturally capped by user activity.

## 8.3 Transcript parsing — fix before indexing

Verified against real `~/.claude/projects/<dir>/<session>.jsonl`. Three real bugs in `ingest.parse_claude_code_session`:

1. **`isSidechain: true` turns are subagent calls**, not user prompts. Currently counted toward user-turn extraction. Skip them when building `PromptNode`s. Keep them in raw session for completeness.
2. **`type:assistant` with `model:"<synthetic>"` and `isApiErrorMessage:true`** are API errors stuffed back into the transcript. Skip for outcome counting and embedding.
3. **`message.content` polymorphism.** Sometimes a string, sometimes a list of `{type:"text"|"tool_use"|"tool_result", ...}` blocks. The user-facing prompt is the concatenation of `text` blocks only. Tool calls/results are separate signal (track them as tool features, not prompt text).

Apply the same audit to `parse_codex_session`, `parse_gemini_cli_session`, `parse_cowork_session`. Each needs a "user-facing prompt extraction" function distinct from raw turn enumeration.

**File:** `src/trinity_local/ingest.py` — refactor each parser to expose two outputs: `SessionRecord` (existing) and `PromptTurn[]` (new — clean user-facing turns only, ready for embedding).

## 8.4 Hierarchical memory index

Replace single-prompt k-NN with four object types. **Do not embed full transcripts.**

| Object | Embedding text | Prefix | Purpose |
|---|---|---|---|
| `PromptNode` | the user's message text only | `search_document:` | The atomic retrieval unit |
| `TurnWindow` | prev/curr/next turn, ~800–2,000 tokens | `search_document:` | Local context when a prompt depends on framing |
| `TranscriptNode` | mean of constituent `PromptNode` embeddings (no LLM call) | — | Routes a query to the right neighborhood, not the answer |
| `CouncilOutcome` | not embedded | — | The label. Routing learns from this, not from embeddings. |

**Embedding model:** `nomic-embed-text-v1.5` at 768d (native), normalized vectors. Use Nomic task prefixes deliberately: `search_document:` when storing, `search_query:` at retrieval, `clustering:` only for cluster centroids if/when added later. Resolve the `[mlx]` extra naming — rename to `[embeddings]` over a deprecation window.

**Schemas:**

```python
@dataclass
class PromptNode:
    id: str
    transcript_id: str
    turn_index: int
    text: str
    embedding: list[float]
    created_at: str
    preceding_context_ids: list[str]
    following_context_ids: list[str]
    cluster_id: str | None = None
    themes: list[str] = field(default_factory=list)
    council_runs: list[str] = field(default_factory=list)  # CouncilOutcome ids
    user_winner: str | None = None
    chairman_winner: str | None = None
    uncertainty: float | None = None
    importance: float | None = None
    last_replayed_at: str | None = None

@dataclass
class TurnWindow:
    id: str
    transcript_id: str
    center_prompt_id: str
    text: str
    embedding: list[float]
    turn_start: int
    turn_end: int

@dataclass
class TranscriptNode:
    id: str
    title: str | None
    prompt_ids: list[str]
    centroid_embedding: list[float]
    themes: list[str] = field(default_factory=list)
    density: float | None = None

@dataclass
class CouncilRun:  # mirror of CouncilOutcome, attached to PromptNode
    id: str
    prompt_id: str
    models_run: list[str]
    chairman_winner: str | None
    user_winner: str | None
    accepted: bool | None
    edited: bool | None
    provider_scores: dict[str, dict[str, float]]
    cost_by_provider: dict[str, float]
    latency_by_provider: dict[str, float]
    created_at: str
```

**Files to add:**
- `src/trinity_local/memory/prompt_node.py`
- `src/trinity_local/memory/turn_window.py`
- `src/trinity_local/memory/transcript_node.py`
- `src/trinity_local/memory/index.py` — unified vector search over the three tiers
- `src/trinity_local/memory/replay_value.py` — score + MMR diversification

**State paths** (add to `state_paths.py`):
```
~/.trinity/memory/prompt_nodes/<transcript_id>.jsonl
~/.trinity/memory/turn_windows/<transcript_id>.jsonl
~/.trinity/memory/transcript_nodes.jsonl
~/.trinity/memory/embeddings.bin     # one mmap-able vector blob
~/.trinity/memory/cursors.json       # per-source ingest cursors
```

## 8.5 Replay-value score (search ranking)

Pure cosine similarity is wrong for autofill. Rank by *replay value* — prompts worth re-running:

```python
def replay_value_score(*,
    prompt_similarity: float,
    window_similarity: float,
    transcript_similarity: float,
    cluster_density: float,
    known_theme: float,
    uncertainty: float,
    importance: float,
    staleness: float,
    recently_run: float,
) -> float:
    return (
        0.30 * prompt_similarity
      + 0.14 * window_similarity
      + 0.06 * transcript_similarity
      + 0.14 * cluster_density
      + 0.14 * known_theme
      + 0.16 * uncertainty
      + 0.10 * importance
      + 0.06 * staleness
      - 0.16 * recently_run
    )
```

**Hardness inference (no LLM calls):**

```python
def infer_hardness(p: PromptNode) -> float:
    score = 0.0
    if not p.user_winner: score += 0.25
    if p.chairman_winner and p.user_winner and p.chairman_winner != p.user_winner: score += 0.30
    if not p.council_runs: score += 0.15
    if len(p.council_runs) > 1: score += 0.10
    if p.themes and any(t in HIGH_VALUE_THEMES for t in p.themes): score += 0.20
    if (p.importance or 0) > 0.7: score += 0.15
    return min(score, 1.0)
```

Apply MMR diversification on the final result list so the autofill UI doesn't show ten near-duplicates.

## 8.6 Autofill loop on existing transcripts

The user has months of `~/.claude/`, `~/.gemini/`, `~/.codex/` data. Index it on first run. After cleanup + parsing fix:

```
existing transcripts
    → ingest.parse_*_session (now emits PromptTurn[])
    → embeddings.embed("search_document: <prompt>")
    → PromptNode written to disk
    → TurnWindow written for each PromptNode
    → TranscriptNode = mean(PromptNode.embedding for prompts in transcript)
```

**Search box behavior:**

- **Empty/focused box** → show watcher recos as defaults: "you ran X yesterday — run a council on it." This is the new home for `_build_recommendation` output. Drops the separate notifications surface.
- **User typing** → embed query as `search_query:`, retrieve top 50 per tier, merge by `prompt_id`, rank by `replay_value_score`, MMR to top 8, render as cards with reason chips: `Similar · Repeated · Uncertain · High value · User override`.

**Card UI (per result):**
```
<center prompt text, ≤120 chars>
<reason chips>  Winner: <provider> (last time)
[Run Council]  [Edit]
```

**Hidden context trick:** when the user clicks a prompt, autofill the original text into the box. But pass the surrounding `TurnWindow` as **hidden context** to the council so it remembers prior framing without cluttering the UI.

## 8.7 Chairman Routing JSON (label producer)

Every council emits, alongside the visible Memo, a fenced `Routing JSON` block. Without this, no aggregation is possible — the moat doesn't compound.

```
{
  "winner": "<provider>",
  "runner_up": "<provider|null>",
  "confidence": "high|medium|low",
  "task_type": "<short_snake_case>",
  "task_domain": "<short_snake_case>",
  "user_likely_values": ["..."],
  "provider_scores": {
    "<provider>": {
      "overall": 0..10, "planning": 0..10, "execution": 0..10,
      "evaluation": 0..10, "specificity": 0..10, "user_fit": 0..10,
      "risk": 0..10, "conciseness": 0..10
    }
  },
  "best_stage_models": {"plan": "...", "execute": "...", "evaluate": "..."},
  "routing_lesson": "For <task_type>, prefer <provider> because <observed reason>.",
  "eval_seed": "A future answer should pass: <check>",
  "should_be_hard_case": true|false,
  "hard_case_reason": "near_new_prompt|dense_cluster|known_theme|uncertain_outcome|high_value_cluster|none"
}
```

**Persistence:** add `routing_label: CouncilRoutingLabel | None` to `CouncilOutcome`. Parse in `council_runtime.parse_synthesis_sections`. On parse failure, store `routing_label_error` in metadata (do not crash). Track parse-success rate; if <85%, route the JSON extraction through a smaller dedicated LLM call.

## 8.8 Local + global routing graph

Keep `global_benchmarks.py` — it's the cold-start prior. Compose two layers:

```
local_score = local_provider_elo(task_type, user_history)
global_score = global_provider_score(task_type)  # anonymous aggregate
blended = alpha * local_score + (1 - alpha) * global_score
alpha = sigmoid(local_council_count / 10)  # fast ramp toward local once enough data
```

**Personal vs global UI** (Launchpad section):
```
Your local preference:
GPT wins strategy prompts 68% of the time.

Global prior:
Claude wins similar writing tasks 61% of the time.

Trinity recommendation:
Use GPT first, Claude as challenger.
```

## 8.9 Aggregation endpoint = cold-start prior + calibration audit

> **Reframed May 2026.** Earlier text called this "the training set for Phase 9." That's no longer true: chairman synthesis is now `/me`-conditioned (§8.4 + `me_builder`), so per-user `winner` and `provider_scores` labels are not apples-to-apples across users. Aggregating them produces a noisy mean, not a clean training signal. The endpoint stays load-bearing for two narrower jobs.

**Job 1 — Cold-start prior.** A new user with an empty `~/.trinity/council_outcomes/` directory and a thin `/me` would otherwise waste their first 10–20 councils rediscovering "codex+gpt-5.5 wins coding." Aggregated `(task_type, task_domain) → default_provider` priors short-circuit that. The chairman + the personal routing table (computed on demand by `compute_personal_routing_table()` walking those outcomes) then take over as a user accumulates their own data. (This is what §8.8 Local + global blend serves — fade from priors to personal as council count grows.)

**Job 2 — Calibration audit.** Periodically compare anonymized aggregate winners to what an individual `/me`-conditioned chairman picks for the same `(task_type, task_domain)`. Large deltas mean either: (a) Trinity's chairman picker has rubber-stamped a single provider too aggressively, or (b) a model silently got worse. Both are actionable; the audit catches them.

**What's no longer claimed:**

- ~~"This bucket is the supervision signal Phase 9 trains on."~~ Phase 9's training data shape is now `(task_text, /me_embedding, available_models, …) → routing_decision`. Without `/me` as an input feature, generic labels collapse the user diversity Phase 9 needs to learn from. The training pipeline should pull from per-user `~/.trinity/council_outcomes/*.json` *with `/me` snapshot attached*, not from cross-user aggregate. See §9.

**Payload (unchanged):** Anonymous opt-in upload of the Chairman `routing_label` JSON only — never prompt text, never harness identifiers. Each upload is `(task_type, task_domain, available_models, winner, runner_up, provider_scores, mode)`. No `/me`-derived fields are uploaded.

**Implementation:** One Cloudflare Worker, R2 storage, GitHub Action for nightly aggregation. ~100 lines. Public read endpoint integrated into `trinity-local update` to refresh local priors weekly.

**Ship discipline (unchanged):**
- Don't open the upload endpoint until Chairman JSON parse-success rate ≥85% (§8.7). Garbage labels poison the prior.
- Don't ship the public leaderboard view until at least dozens of opt-ins are on board — empty board damages social proof.
- Read access stays free for everyone; uploading is opt-in only.

## 8.10 Cleanup + cuts (must precede 8.4–8.9)

| Cut / Action | File(s) | Why |
|---|---|---|
| Delete | `daemon_manager.py`, `commands/daemon.py`, auto-ingest launchctl plist | Tool-triggered ingestion replaces daemon |
| Delete | `task_linking.py`, `commands/ingest.py`'s `build_task_links` call | Embedding-based linking via `PromptNode` k-NN subsumes string-similarity linking |
| Delete | `digest.py`, `commands/digest.py` | Weekly digest is off the routing loop |
| Delete | `workflow_runtime.py`, `commands/workflow.py`, `workflow_create` dispatch action | Watcher side-quest, not on the routing path |
| Move | research handlers (`replay`, `embed`, `rank`, `hardeval`, `analytics`) out of `commands/research.py` | Research-only; doesn't belong in the product CLI. Keep `hard` (produces corpus the advisor reads). |
| ~~Move~~ Deleted | ~~`feature_extractors.py`, `example_builder.py`, `training_schema.py`~~ | All three were v2-trained-coordinator substrate; deleted alongside the 2026-05-11 v2 sunset (`example_builder` earlier, the other two in tick 57 — 523 LOC removed). Reachable via git history if v1.5 hits a quality ceiling. |
| Merge | `knn_advisor.py` into `ranker/knn_ranker.py` | Two adjacent surfaces; unify under one advisor |
| Merge | `embeddings/cache.py` (global dict) + `research/embeddings.py` (disk cache) → `embeddings/store.py` | Single thread-safe, disk-backed embedding store |
| Merge | `review.py` (post-hoc review) → `council_runtime.py` | It's a degenerate council with one member |
| Split | `portal_template.py` (1,277L) → `portal_layout.py` + `portal_cards.py` + `portal_search.py` | The new autofill UI gets its own module |
| Split | `council_review.py` (715L) → `council_review_page.py` + `live_review.py` | Separate page rendering from polling |
| Split | `watch_runtime.py` (595L) → `transcript_indexer.py` + `routing_advisor.py` + `outcome_recorder.py` | Three separable concerns; one feeds the new index |
| Cut | `council_progress.py` shim | Update imports to `council_status.py` directly |
| Cut | `cost_tracker.py` standalone JSONL | Cost lives inside `CouncilOutcome.routing_label.cost_by_provider` |
| Cut | `drift.py` | Wired but no destination for alerts |
| Keep | `global_benchmarks.py`, `telemetry.py` | Bootstrap prior; user wants these |
| Cut | `scoreboard.py` | Removed post-v1.5 — `compute_personal_routing_table()` reads `council_outcomes/*.json` directly; the old success/failure scoreboard has no writers and the `scoreboard.json` file is never populated. CLI `scoreboard` subcommand removed alongside. |
| Keep | `knn_analytics.py` | It's the advisory→outcome signal log — feeds the routing graph |

**Estimated reduction:** ~2,500 lines, ~10 files removed, no spine functionality lost.

## 8.11 What stays as the spine

```
ingest (parsers, fixed)
    ↓
memory/ (PromptNode, TurnWindow, TranscriptNode, index, replay_value)
    ↓
ranker/ (heuristic + k-NN advisor + global prior blend)
    ↓
council_runner / council_runtime / council_status (with Routing JSON)
    ↓
council_feedback (user verdict capture)
    ↓
knn_analytics (advisory→outcome signal log)
    ↓
mcp_server (6 tools: route, judge, run_council, record_outcome, search_prompts, get_persona)
    ↓
dispatch_registry (one source of truth) → {MCP, Shortcuts}
    ↓
portal_data / portal_template (Launchpad, autofill UI, dashboard)
```

## 8.12 Build sequence

1. **Cleanup pass** (1–2 days, no new features): apply the 8.10 cuts, run tests.
2. **Parsing fix** (8.3): refactor `ingest.py` parsers; emit `PromptTurn[]`.
3. **Embedding store** (consolidate `embeddings/cache.py` + `research/embeddings.py`): thread-safe, disk-backed, mmap-friendly.
4. **PromptNode index** (8.4): write the four schemas + `memory/index.py` + state paths. Backfill from existing transcripts (cursor-based, resumable).
5. **Chairman Routing JSON** (8.7): every new council emits a parseable label. Add `routing_label` to `CouncilOutcome`.
6. **Tool-triggered ingest** (8.2): cursor-based incremental ingest fires from MCP tool calls + Launchpad render.
7. **Five MCP tools** (8.1): rename + add `judge`, `record_outcome`, `search_prompts`.
8. **Autofill UI** (8.6): launchpad search box wired to memory index. Watcher recos render in empty-state.
9. **Local + global blend** (8.8): scoreboard view shows personal vs global vs Trinity recommendation.
10. **Aggregation endpoint** (8.9): Cloudflare Worker + opt-in upload of `routing_label` only. **Ship last** — needs critical mass.

## 8.13 Phase 8 exit criteria

- The nine MCP tools (canonical 5 — `route`, `run_council`, `record_outcome`, `get_persona`, `get_council_status`; v1.5 trio — `ask`, `get_picks`, `mark_pick_wrong`; launch-arc — `handoff`) respond correctly via stdio
- No daemon process is created by `install-mcp`
- `~/Library/LaunchAgents/` is untouched after install
- `ingest.parse_claude_code_session` correctly excludes sidechain turns and synthetic-error assistant messages
- `ingest` emits `PromptTurn[]` distinct from raw `SessionRecord`
- `~/.trinity/memory/prompt_nodes/` is populated from existing transcripts
- Launchpad search box returns ranked replay candidates with reason chips
- Empty-state autofill shows watcher recos
- Every new `CouncilOutcome` has a `routing_label` field populated; parse-success ≥85%
- `ranker.advise()` returns concrete neighbor-derived reasons, not raw similarity scores
- Personal vs global vs Trinity-blended view renders on Launchpad
- `task_linking.py`, `daemon_manager.py`, `digest.py`, `workflow_runtime.py` are deleted
- `pytest -q` still green (target: ~150 tests after dead-code removal)

## 8.14 Open questions

- **Backfill cost.** Embedding 59k sessions × N user turns through `nomic-embed-text-v1.5` on-device. Time-box to 2 hours on M-series; if longer, sample down to recent 30 days first and stream the rest in background.
- **Schema drift.** Old `CouncilOutcome` records lack `routing_label`. Deserialize with explicit `None` default; do not migrate.
- **Chairman compliance.** Models will sometimes emit invalid JSON. If parse-success <85% in real runs, switch to a small dedicated extraction LLM call after synthesis.
- **Stop-hook safety.** Phase 4's `Stop` hook still uses `2>/dev/null`. Route hook errors to `~/.trinity/analytics/hook_errors.jsonl` so silent failures are recoverable.

## 8.14a Operational notes from running Trinity MCP (May 2026)

These came up while *using* Trinity to review Trinity. Worth preserving so future agents don't re-discover the same friction.

**The meta-loop works (proof point, May 5 2026).** Trinity used itself to decide one of its own design questions: "should /me come BEFORE or AFTER member outputs in the chairman prompt?" Members disagreed, chairman synthesised, verdict was unanimous on BEFORE with the routing lesson: *"Persona should function as the evaluation rubric, not a post-hoc adjustment. AFTER ordering causes the chairman to anchor on a generic 'best answer' first. Once anchored, persona becomes weak post-hoc reweighting rather than a verdict-flipping signal."* Locked in by `tests/test_council_runtime.py::TestChairmanPromptOrdering`. The system was hard enough to argue with itself meaningfully and converge — that's the bar.


- **Codex-on-xhigh hang — ROOT CAUSE: inherited stdin (FIXED 2026-05-04).** Codex CLI in non-interactive mode reads any non-TTY stdin and appends it to the prompt before responding. `subprocess.run(...)` defaults to inheriting the parent's stdin, so codex blocked reading from the council launcher's pipe until something killed it (30+ min observed). Symptoms: 0-byte stdout, member status "running" forever, claude+gemini already done. Fix: `providers.py:_run_command` now passes `input=""` so codex sees stdin closed immediately. Empirically: same prompt completes in ~8s with `input=""`, hangs >90s without. Also added `DEFAULT_PROVIDER_TIMEOUT_SECONDS = 480` as defense-in-depth for future hangs.
- **Stale MCP server.** The `trinity-local --mcp` server caches imports at process boot. After in-session edits to `mcp_server.py` or anything it imports (e.g. `global_benchmarks`), the running server returns 500 errors with stale code. Either auto-restart the server when files under `src/trinity_local/` change, or document that MCP tool failures during dev mean "restart the MCP server."
- **Codex via CLI is subscription-only.** `codex exec --model gpt-5-5` returns *"not supported when using Codex with a ChatGPT account"* — the CLI requires the `gpt-5.5` slug *with the dot* and reasoning level via `-c model_reasoning_effort="xhigh"`, not the AA-format slug. Slug mapping between AA's data and CLI accepted forms is a per-vendor mess; `tools/sync_reference_evals.py` is the correct place to maintain the translation.
- **Chain mode is underused.** It exists (`run_council(mode="chain", sequence=[...])`) but I haven't fired one yet in normal use. Either wire `route()` to recommend it for specific task types (long-form writing, multi-step refactors) or consider whether chain mode is over-built relative to demand.
- **`record_outcome` capture is the missing UX multiplier.** Every council I've run today produced rich Routing JSON and *zero* user verdicts because the launchpad doesn't surface a "✓ this is what I'd pick" button on member cards. Without that one-click, the personal routing table never populates. This is the single highest-leverage Phase 8 UX gap.
- **`get_persona` deserves promotion in the docs.** The /me + chairman pattern is the strongest piece of new IP today, but the spec mentions `get_persona` only as an MCP tool, not as a *standalone primitive worth pulling at session start by every harness*. Worth a paragraph in §8.0 or a new §8.6a.

## 8.15 The commandment

> **Trinity should only appear when model choice itself is the problem.**
> Everywhere else, it is a quiet function call.

---

# Phase 9 — Tiny Coordinator (the learned router)

> **Where Phase 8 ends, Phase 9 begins.** Phase 8 builds the dataset and supervision signal. Phase 9 trains the small learned thing that consumes them. This is the destination implied by Lottery Ticket → HRM → TRM → TRINITY: as compute commoditizes, durable IP migrates to whatever small, learned controller decides how that compute gets organized.

**Phase 9 is not on the critical path for v1 ship.** Phase 8's heuristic + k-NN router (`ranker/`) is enough to ship the skill, accumulate councils, and grow the dataset. Phase 9 only becomes possible once you have ~5–10k labeled councils across enough users to train on. The point of writing it now is to make sure every Phase 8 decision is defensible against this destination.

## 9.1 The model shape

A two-piece controller, mirroring TRM's "tiny network + recursive refinement":

| Component | Role | Size | Substrate |
|---|---|---|---|
| **Encoder** | Map `(task_text, harness, available_models, budget, latency)` → fixed-dim feature vector | ~600M params (Qwen3-0.6B-class) or smaller, on-device | Local model, frozen after initial fine-tune |
| **Routing head** | Map encoder output → `(mode, primary, challenger, confidence, expected_provider_scores)` | ~10K params (small MLP or shallow attention block) | Trained on Trinity outcomes |

Inference is one encoder pass + one head pass. The head is the learned thing; the encoder is the embedding substrate. Same intuition as TRM's tiny core, applied at the orchestration layer instead of the latent-reasoning layer.

**"Recursion" in this setting** = multi-turn delegation. The head can choose `mode=council` and re-invoke its own decision over the council's responses (an in-loop `judge`). That's the closest analog to TRM's iterative self-correction, just with model calls as the substrate rather than hidden-state updates.

## 9.2 Training data shape

> **Reframed May 2026.** Chairman synthesis is `/me`-conditioned today, so labels are *per-user-per-/me*, not generic. Training data must include a `user_persona_embedding` as input or the head learns the average user's preferences (i.e. "always pick the AA top model"). Source the rows from per-user `~/.trinity/council_outcomes/*.json` with the user's `/me` snapshot attached at training time — **not** from §8.9's anonymized aggregate.

```python
@dataclass
class RouterExample:
    # Inputs
    task_text_embedding: list[float]    # 768d Nomic
    user_persona_embedding: list[float] # 768d Nomic of the user's /me at council time
    harness: str                         # "claude_code" | "codex" | "gemini" | "cowork"
    available_models: list[str]
    budget: str                          # "low" | "normal" | "high"
    latency: str                         # "fast" | "normal" | "patient"
    task_type: str
    task_domain: str

    # Targets (from Chairman Routing JSON + user verdict)
    actual_mode: str                     # what the user actually used
    actual_primary: str
    actual_challenger: str | None
    user_winner: str                     # what the user ultimately picked (gold target)
    chairman_winner: str                 # what /me-conditioned chairman picked (proxy target)
    accepted: bool
    edited: bool

    # Auxiliary supervision (richer signal)
    provider_scores: dict[str, dict[str, float]]
    cost_by_provider: dict[str, float]
    latency_by_provider: dict[str, float]
```

The Chairman Routing JSON (§8.7) is the *single most important* artifact in the codebase by this measure: its parse-success rate × council volume = the size of the training set.

## 9.3 Training objective

Three losses, summed with hand-tuned weights:

1. **Mode classification** (cross-entropy): did the controller pick `single` / `top_2` / `council` correctly given what the user ultimately needed?
2. **Provider ranking** (margin-based): did the predicted ranking of providers match the user's actual selection?
3. **Confidence calibration** (Brier score): does predicted confidence match observed accuracy?

The encoder stays frozen for early iterations. Only the head trains. This is fine — TRM's whole thesis is that the small recursive piece is doing the work, not the encoder.

**Online learning later.** Once the head is stable, add a slow online update: every N user verdicts, do one gradient step on the head. The router gets smarter for that user without re-deploying. This is the personalization layer.

## 9.4 Eval harness

Borrow from current `hardeval` but reframe targets:

| Metric | Definition | Today's baseline (heuristic + k-NN) | Target after Phase 9 |
|---|---|---|---|
| Mode accuracy | % of cases where predicted mode matches retrospective right call | n/a (heuristic always picks `single` unless thresholded) | ≥75% |
| Top-1 provider accuracy | % of cases where predicted primary == user winner | ~50% (current k-NN) | ≥70% |
| Top-2 provider accuracy | % where user winner ∈ {primary, challenger} | 99.5% (current k-NN) | maintain |
| Council triggering | F1 on "should this have been a council?" | 98% precision/recall | maintain |
| Calibration | Brier score on confidence | n/a | ≤0.15 |

Hold out 10% of councils as eval. Re-run after every controller release.

## 9.5 Deployment

> **Reordered May 2026.** Earlier text shipped the shared head first and per-user adapter second. With chairman now `/me`-conditioned, the shared head trained on cross-user data learns "always pick AA's top model" — useless personalization. Flip the order: ship the per-user head first, fall back to a small shared cold-start prior for users with too few labeled councils.

1. **Per-user head with `/me` conditioning.** Each user keeps a small head on top of a shared frozen encoder. The encoder's input is `concat(task_text_embedding, user_persona_embedding)` so the same architecture personalizes via input features rather than weights. Trained from that user's own verdicts (council outcomes + `record_outcome` calls). ~10KB on disk. v1 of the learned router. Privacy-clean — training data + weights stay local.

2. **Shared cold-start prior, distributed in the package.** A small head trained on §8.9's anonymized aggregate, used only when a user has fewer than ~20 labeled councils. As soon as the per-user head has enough signal to beat it on hold-out, swap. Update via `trinity-local update`. v2 — ships once we have enough per-user councils to validate that the per-user head is actually better than the prior.

A hosted controller is explicitly out of scope. Trinity's whole positioning depends on the routing layer running locally.

## 9.6 Build sequence

1. Phase 8 ships and accumulates councils for ~3 months.
2. Pull from §8.9 private R2 bucket: aim for ≥5,000 councils with valid Chairman JSON across ≥50 users.
3. Build encoder + head training pipeline (offline, in `research/controller/`). Frozen encoder, head-only training. ~one weekend of work given the data exists.
4. Eval against the harness above. If lift over heuristic+k-NN is <10% on top-1, iterate on features (add task fingerprint, harness embedding, available-model encoding) before iterating on architecture.
5. Ship v1 weights with `trinity-local update`. Wire `ranker/learned_head.py` to load them. Old `ranker/knn_ranker.py` becomes the fallback when the head is absent.
6. Re-baseline after one month of live deployment. If the metrics didn't move on real traffic, the training set is still too small or too narrow — go back to step 1, accumulate more.

## 9.7 Phase 9 exit criteria

- ≥10K labeled councils in the private R2 bucket
- Encoder + head training pipeline runs reproducibly from a single command
- v1 head ships with `trinity-local update`; package size grows by <50MB
- `ranker/learned_head.py` integrates cleanly with existing `ranker/` ecosystem; falls back to k-NN when weights missing
- On hold-out eval, top-1 provider accuracy ≥70% (vs ~50% current k-NN)
- One blog-post-grade write-up of the architecture + ablations exists

## 9.8 What this implies for Phase 8 (decision-making heuristic)

For every choice in Phase 8, ask:

> **Does this increase either the quality or the quantity of the supervision signal that Phase 9 will train on?**

- Chairman Routing JSON parse-success rate? **Quality.** Push hard on it.
- Filtering agent-injected user prompts from the index? **Quality.** Cut them aggressively.
- Backfilling old transcripts? **Quantity.** Useful but lower-leverage than fixing parse-success.
- Polishing the Launchpad UI? **Neither.** Push down the queue.
- Adding a new dispatch action? **Probably neither.** Skip unless it directly helps users run more councils.

This is the discipline that keeps Phase 8 from drifting into "build a pretty workspace" and instead aimed at "build the dataset that lets us train the small thing."

## Phase 10 — 100-persona audit backlog (2026-05-15)

100 sub-agents each simulated a distinct user persona walking through
Trinity for the first time (or returning, or auditing, or evaluating).
Findings written to `/tmp/persona_findings/persona_NN.md` during the
audit; this section is the aggregated backlog. Themes are ordered by
prevalence × severity; each theme cites the personas that surfaced it
so the evidence trail survives the temp-file cleanup.

Severity counts: **39 HIGH · 45 MED · 16 LOW** across 100 personas.
The META-auditor (persona #100) named the unifying pattern:
**Trinity's README is a single-audience funnel for CLI-coder users, but
multi-audience surfaces (`install-extension`, desktop launch, single-
provider councils, Ollama dispatch) are either already present or
strategically required — they're just invisible above the fold.**
Highest-leverage fix is restaging the README around audience-tagged
entry paths plus a visible "Remove" section. Most of the other themes
follow from that frame.

2026-05-19 supersession: references below to `Trinity.app` / `install-app`
mean the retired osacompile wrapper unless explicitly revised. The current
directive is a real Cowork-style desktop cockpit over `~/.trinity/`; the Chrome
extension remains the v1 bridge for capture and launchpad dispatch, not the
long-term non-coder app shell.

### Theme A — Acquisition path is single-audience (CLI-coder only)

**Evidence**: personas 02, 04, 07, 15, 23, 31, 39, 69, 83, 87, 88, 89,
92, 100. HIGH on most.

**Symptoms**: Designer (P04) and teacher (P15) bounce at `pip install`
on README line 8 within seconds. ChatGPT-only writer (P07) and
claude.ai-only user (P88) cannot install the Chrome extension WITHOUT
running the CLI installer first. Cursor user (P92) finds Trinity not
in `install-mcp`. Codex-only user (P89) gets broken three-column
councils because launchpad/MCP/CLI/skill hardcode `["claude","gemini","codex"]`.

**Fixes (priority order):**

1. **Audience-tagged entry paths above the fold** in README: desktop app for
   non-coders, Chrome extension for browser capture/launchpad dispatch, and
   CLI/MCP for power users. The CLI block stays, but it stops being the only
   visible path.
2. **Chrome Web Store listing for the extension** decoupled from CLI
   install — let claude.ai-only users install JUST the extension.
3. **Signed desktop app** as the non-coder acquisition surface, paired with a
   download button above the fold. Do not revive the old bookmark-shaped
   `Trinity.app` wrapper; this has to be a real local cockpit.
4. **`install-mcp` adds Cursor** to its harness list (P16: 30-line fix;
   P92: same conclusion).
5. **Single-provider council mode** — when only one of claude/gemini/
   codex is configured, ask + run_council degrade to single-call
   instead of broken three-column.

### Theme B — Launchpad is a feature changelog, not a product surface

**Evidence**: personas 20, 24, 50, 52, 53, 55, 56, 63. HIGH on most.

**Symptoms**: 16+ launchpad sections; fresh installer sees brand
pitch + 4-6 empty cards before his actual council. **100% of real-
corpus topology basins have empty `label` field — largest cluster of
3,408 prompts renders as "Hello."** (P53). `mark_pick_wrong` button
copies CLI to clipboard instead of executing veto (P63). Launchpad
copy says "you can hand-edit any of [the memories]" but `lens-build`
flat-overwrites (P56). Unrated councils have no search or unrated-
filter (P50).

**Fixes**:

1. **Launchpad collapse** (already planned, mid-ship per the active
   `/loop`): single lens card + three "use the lens" cards + recent
   councils + training history. Collapse empty-state pairs into one-
   liner CTAs at the top of their parent card.
2. **Basin labeler must actually run** (P53) — `topics.json` has
   `label` field but it's always empty on real corpus. Either run the
   labeler at lens-build time or fall back to a TF-IDF top-term name,
   not "Hello."
3. **`mark_pick_wrong` button calls the MCP tool**, not copies a
   shell command. Show before/after `effective_trust`.
4. **Lens hand-edit preservation**: either pin file (`lens.user.md`
   merged on rebuild) or `lens-add` command. Drop the "you can hand-
   edit any of them" copy until merge-on-rebuild lands.
5. **Per-tension veto chip** + `lens-build --hint` flag for "this
   tension is wrong, rebuild with a different angle."

### Theme C — Multi-platform / multi-harness gaps unstated

**Evidence**: personas 17 (Linux), 18 (Windows/WSL), 22 (headless),
23 (iPad), 66 (Firefox), 92 (Cursor). HIGH on Linux + headless.

**Symptoms**: the retired `install-app` wrapper crashed with raw
`FileNotFoundError: osacompile` on Linux (P17). `setup.sh` shebangs `zsh` with
macOS `shortcuts` CLI calls. `doctor` recommends installing the macOS Shortcut
on Linux. pyproject claims Linux support, README is silent. iPad-only dev (P23)
has zero entry point — mobile spec only ships review-link companion requiring a
paired desktop he doesn't own.

**Fixes**:

1. **Platform-gate the future desktop installer** — bail loudly on unsupported
   OSes with a one-line message linking to the Linux/headless story. The retired
   `install-app` wrapper should not come back.
2. **`#!/usr/bin/env bash`** + macOS-only sections gated in `setup.sh`.
3. **Document the headless story** (P22): engine runs on Linux, no
   GUI needed; use `trinity-local serve` for the local launchpad
   page server.
4. **Trim Windows claim in pyproject** to match README's macOS-first
   reality.

### Theme D — Lifecycle gaps (uninstall, export, backup, retention)

**Evidence**: personas 30 (uninstall), 57 (backup), 58 (migrate), 76
(retention/disk fill), 77 (export+anonymize), 85 (delete recovery).
ALL HIGH.

**Symptoms**: Zero "uninstall" mentions anywhere — contradicts the
"own your data" wedge. Migration breaks (5 re-installs needed,
0 docs). No `trinity-local export` command. Zero anonymization code
across the repo (`grep` 0 hits for anonymize / redact / scrub / pii).
Dev `~/.trinity/` already 4.4GB; no retention/prune/quota; doctor
skips disk check.

**Fixes**:

1. **`trinity-local uninstall`** — removes MCP entries, desktop launcher/app
   entries, Chrome Native Messaging manifest, skill file, optionally
   `~/.trinity/` and the HF model cache. Inverse of `install-mcp`, the desktop
   installer, and `install-extension`. Prints what it'll delete with a single
   `--yes` confirmation.
2. **`trinity-local export [--anonymize]`** — tar of `~/.trinity/`
   with optional pii scrub on prompt content (anchors, code blocks,
   file paths). Schema doc already exists at PREFERENCE_CORPUS_SPEC.md.
3. **`trinity-local restore <archive>`** — inverse of export.
4. **Migration doc** in README: "rsync `~/.trinity/` is necessary but
   not sufficient; also re-run install-mcp + the desktop installer".
5. **Retention story**: doctor reports `~/.trinity/` size; soft warning
   above 5GB; optional `trinity-local prune --older-than 90d`.

### Theme E — Trust gaps in cognitive memory output

**Evidence**: personas 52, 53, 54, 55, 56, 94, 96.

**Symptoms**: lens "isn't me" has no remediation path (P52). Vocabulary
anchors unredacted — leak project names like "Project Apollo" (P54).
core.md viewer renders raw markdown with zero provenance ribbon, so
it reads generic and trust dies on inspection (P55). No lens history
or diff — `save_lenses` destructively overwrites (P94). me-card
silently drops all 3 orderings, leaving 40% empty whitespace despite
JSON reporting `orderings_count: 3` (P96 bug).

**Fixes**:

1. **Provenance ribbon on core.md viewer**: "Generated from N
   tensions, M anchors, K basins. Source: lens.md@<git-hash>." Click-
   through to evidence.
2. **Per-tension veto chip** (also Theme B).
3. **Append-only lens snapshots** at `~/.trinity/memories/lens.history/
   <iso>.md`; `lens-diff` command.
4. **Redaction primitives**: `me-card --safe`, `vocabulary --redact`,
   anchor allowlist file.
5. **me-card orderings render bug** (P96) — guard at me_card.py:247
   silently drops all 3; one-line fix.

### Theme F — Council UX (wait time, partial failures, garbage)

**Evidence**: personas 45, 46, 47, 48, 49, 51, 95.

**Symptoms**: 30-second wait on `run_council` is a void — no live-page
URL in response, no polling cadence guidance for the agent (P45).
`classify_dispatch_failure` is wired only into `ask.py`, not
`council_runner` — rate-limited Codex doesn't demote dispatch_health,
no "councilling without Codex" banner (P46). "Routing label" vs
"Routing JSON" name drift across docs (P48). Verdict click-moment
generic — no before/after delta visible (P49). Garbage detection only
filters empty-stdout + nonzero-exit; mojibake/refusal-strings pass
through to chairman (P95).

**Fixes**:

1. **`run_council` returns `live_page_url` + suggested poll cadence**
   inline in the async response.
2. **Wire `classify_dispatch_failure` into `council_runner`** + emit
   "councilling without X" banner on the live page.
3. **Resolve "Routing label" vs "Routing JSON" name drift** —
   pick one (Routing JSON), search/replace across launchpad +
   council_review.
4. **Verdict click → before/after delta** ("This pushed Codex from
   0.61 → 0.68 trust on `migration` tasks").
5. **Provider-output validator** — empty/refusal/mojibake → flag in
   chairman input as "[provider returned garbage]", don't blend
   silently into synthesis.

### Theme G — Cost story unquantified

**Evidence**: personas 03, 62, 81.

**Symptoms**: rate-limit-saves card shows counts ("28×"), not dollars
(P62). No monthly $ saved estimate. Investor (P81) sees no
monetization path → closes tab.

**Fixes**:

1. **Cost calculator surface**: rate-limit-saves card shows
   `$X saved this month` using a provider-rate table.
2. **Pricing reveal in README** even if free-forever: Trinity Pro
   (v1.2 placeholder) + Teams (v2 custom) keep the monetization
   story visible without committing prices.

### Theme H — i18n / a11y / accessibility

**Evidence**: personas 28 (Spanish), 29 (screen-reader), 73 (RTL),
74 (color).

**Symptoms**: ASCII-only regex strips Spanish accents across 3 files
(vocabulary.py:64, turn_pairs.py:257, basins.py:194) — Spanish
prompts fail validation (P28). HTML surfaces lack ARIA, skip-links,
live-regions; `<html lang="en">` hardcoded; zero a11y tests (P29).
No `dir="auto"` anywhere; Arabic prompts render bidi-mangled (P73).
Chart palette has protan/deutan confusion axis (P74).

**Fixes**:

1. **Unicode-aware regex** in vocabulary + turn_pairs + basins
   (`[^\W\d_]` instead of `[a-zA-Z]`).
2. **Minimal a11y pass**: ARIA roles on cards, focus-trap on modals,
   skip-link, `lang="en"`-but-`dir="auto"` on prompt content. Add
   one a11y smoke test.
3. **Pattern fills on charts** for color-blind safety.

### Theme I — Multi-user / multi-account contamination

**Evidence**: personas 26 (work + personal Claude accounts), 38
(shared dev machine), 70 (pair-programming), 80 (system-wide
install).

**Symptoms**: the retired `install-app` wrapper wrote
`/Applications/Trinity.app` with the installer's absolute launchpad path baked
in — every other user opened user-1's lens (P38 — real cross-user leak).
`~/.trinity/` is one lens per OS user; multi-account users have no scoping
(P26). Pair-programmers pollute each other's lens silently (P70). System-wide
install undocumented; install-mcp hard-codes `$HOME` (P80).

**Fixes**:

1. **Desktop resolves paths per-user at launch** — don't bake the installer's
   path into app metadata or launcher config.
2. **Per-context lens scoping**: `TRINITY_PROFILE=work` env or
   `--profile work` flag selects a subdir under `~/.trinity/<profile>/`.
3. **`doctor` warns on shared-machine install** when other users exist on the
   box and a shared desktop install could expose one user's lens to another.
4. **Document system-wide install** OR loudly deny it (current state
   is silent half-broken).

### Theme J — Documentation drift + onboarding

**Evidence**: personas 01, 10, 24, 32, 40, 48, 59, 67, 86, 90, 91,
92, 97. HIGH on test-count + tool-count drift.

**Symptoms**: Tool count drifts across docs (README 10 / claude.md
status 9 / claude.md arch 11 / prompt 11 — P24). CONTRIBUTING test
counts stale (~950 vs actual 1141; 31 vs 33 surfaces — P67). No
"What's new" / version anchor / upgrade section in README (P40, P91).
No troubleshooting section (P97). Cursor manual MCP wiring works but
undocumented (P92). digest deliberately deleted but claude.md still
mentions `digest_pages/` (P86). Conductor only in CLAUDE.md glossary
— README never names it (P90). install-mcp doesn't tell user to
restart Claude Code so new MCP tools appear (P01).

**Fixes**:

1. **Single source of truth for tool count** (one canonical claim in
   CLAUDE.md status block; everywhere else either drops the number
   or uses an `MCP_TOOL_COUNT` constant the doc-consistency test
   pins).
2. **"What's new" section in README** linking to last 3 CHANGELOG
   entries.
3. **Troubleshooting section** with the top-5 install errors and
   `doctor`-driven fixes.
4. **install-mcp prints "Restart Claude Code to load Trinity tools"**
   at the end (P01).
5. **Cursor manual-wiring doc** in install-mcp help / README.
6. **digest dead-link sweep** in claude.md.

### Theme K — Privacy / compliance posture

**Evidence**: personas 06, 14, 27, 43, 54, 77, 82.

**Symptoms**: Launchpad + memory-viewer load 13 CDN JS (unpkg/jsdelivr)
on every open — contradicts "never leaves your machine" absolutism
(P06). No DPA / SOC2 / ISO27001 artifacts (P27, P43). No anonymizer
for export (P77). NativeMessaging conv_id path traversal risk (P82).

**Fixes**:

1. **Bundle marked / d3 / Vue locally** — drop CDN dependencies from
   launchpad + memory-viewer + live council. Privacy claim becomes
   absolutely true, not "absolutely true except 13 JS files."
2. **Compliance doc** (one-pager): data residency, no telemetry by
   default, sub-processor list (none), DPA template.
3. **Anonymizer** (also Theme D #2).
4. **NativeMessaging conv_id path traversal** — sanitize at
   `capture_host.py` before file write.

### Theme L — Extensibility (new providers, custom dispatchers, CI)

**Evidence**: personas 12 (HTTP/SDK), 60 (Ollama-only), 61
(DeepSeek), 68 (HTTP for Go agent), 79 (GitHub Action).

**Symptoms**: No HTTP API — MCP-stdio only (P12, P68). Roadmap doubles
down on "no listening port." Adding a new provider (DeepSeek) is
undocumented (P61). Ollama plumbing exists in v1.0 but is undocumented
(P60). No GitHub Actions integration (P79).

**Fixes**:

1. **Provider plugin doc** — how to add a new CLI-wrappable provider
   to `config.json` + provider class. DeepSeek as worked example.
2. **Ollama configuration doc** — surface the v1.0 plumbing that
   already exists.
3. **Optional `trinity-local serve --api`** read-only HTTP surface
   (route + search_prompts + get_picks endpoints) for non-MCP-aware
   consumers. Keep the wedge intact: read-only, local-bind, no auth
   surface.
4. **GitHub Action template** in `.github/workflows/example-council.yml`
   showing CI-driven council on a PR diff.

### Priority filter for forward ticks

Pick the next 5-10 ticks from this backlog by prevalence × severity ×
effort. Top candidates (one each from Themes A-F):

| # | Theme | Fix | Effort | Why now |
|---|---|---|---|---|
| 1 | B | Basin labeler runs at lens-build time; fall back to TF-IDF top-term | S | "Hello." cluster of 3,408 prompts is a visible launch-killer |
| 2 | A | Three audience-tagged install paths above the fold | S | Highest acquisition lift; no code change |
| 3 | D | `trinity-local uninstall` | M | Lifecycle gap directly contradicts the wedge |
| 4 | B | `mark_pick_wrong` button calls MCP tool, not clipboard copy | S | Feedback loop visibly broken |
| 5 | F | Wire `classify_dispatch_failure` into `council_runner` | S | Rate-limit-dodge story currently silently breaks |
| 6 | E | me-card orderings render bug (one-line) | XS | Share artifact has 40% empty whitespace right now |
| 7 | A | `install-mcp` adds Cursor | XS | 30-line fix per persona 16 |
| 8 | J | "What's new" section in README + version anchor | S | Returning users (P40, P91) can't bridge |
| 9 | K | Bundle marked/d3/Vue locally | M | Removes the only credible privacy attack on the wedge |
| 10 | I | Desktop resolves paths/profile per-user at launch | S | Real cross-user leak on shared machines |
