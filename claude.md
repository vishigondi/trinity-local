# CLAUDE.md — Trinity Local

## Project Identity

Trinity Local is the **local intelligence layer for people who use multiple AI
coding tools.** It watches Claude Code, Codex, Gemini, Cowork, and other
agentic CLIs from the outside, learns which tool works best for which task, and
surfaces insights no single provider can see — without running a server, owning
the terminal, or becoming yet another UX.

**Product mantra:** Do not become the agent. Watch the agents. Do not own the
workflow. Learn from the workflow. The magic is not orchestration — it is
cross-provider memory.

See [product-spec.md](file:///Users/openclaw/projects/trinity-local/docs/product-spec.md)
for the full product spec, GTM strategy, and roadmap.

The current product center of gravity is:

- watcher → task/action/cost/outcome/drift pipeline
- council (cross-provider comparison)
- post-hoc review (Council-lite)
- workflow suggestion → Shortcuts dispatch
- weekly digest

Not:

- the older `run` coordinator loop (LEGACY)
- a standalone chat UX
- an always-on daemon

---

## Architecture Overview

### CLI Dispatcher

Entry: `src/trinity_local/main.py` — thin dispatcher only.

Registered command groups (12 modules):

| Module | Key Commands |
|--------|-------------|
| `commands/run.py` | `run` (LEGACY — deprecated) |
| `commands/ingest.py` | `features`, `examples` |
| `commands/tasks.py` | `task-create`, `task-show`, `task-sync`, `bundle-create`, `launch-create` |
| `commands/council.py` | `council-start`, `council-run`, `council-prompt`, `council-outcome`, `council-html` |
| `commands/portal.py` | `portal-html`, `open-review` |
| `commands/actions.py` | `action-list`, `action-suggest`, `action-council`, `action-notify`, `action-complete` |
| `commands/shortcuts.py` | `shortcut-url`, `shortcut-run`, `action-shortcut`, `shortcut-setup` |
| `commands/watch.py` | `watch-once`, `watch-loop` |
| `commands/workflow.py` | `workflow-create` |
| `commands/digest.py` | `digest` |
| `commands/review.py` | `review` |

### Core Layers

| Layer | Files | Purpose |
|-------|-------|---------| 
| Config | `config.py`, `config.json` | Provider definitions, role/task preferences, `trinity_home()` |
| Providers | `providers.py` | Subprocess wrappers for CLI/MLX/Codex with latency tracking |
| Coordinator | `coordinator.py` | Heuristic role→provider selection (LEGACY — used by `run` only) |
| Runner | `runner.py` | Multi-turn Thinker/Worker/Verifier loop (LEGACY) |
| Council | `council_runner.py`, `council_runtime.py`, `council_schema.py` | Multi-model comparison with peer review and synthesis |
| Ingest | `ingest.py` | Parsers for Claude Code, Codex, Gemini CLI, Cowork sessions |
| Features | `feature_extractors.py`, `training_schema.py` | Compact session features and model descriptors |
| Cost | `cost_tracker.py` | Per-session cost estimation, JSONL cost log, provider aggregation |
| Drift | `drift.py` | Model drift detection via rolling outcome comparison |
| Digest | `digest.py` | Weekly digest: sessions, costs, drift alerts, static HTML |
| Review | `review.py` | Post-hoc review: ask one provider to critique another's output |
| Tasks | `task_runtime.py`, `task_schema.py` | Durable task records with recommendations |
| Actions | `action_runtime.py`, `action_schema.py` | Pending actions: recommendation, start_council, review_ready, workflow_suggestion |
| Watch | `watch_runtime.py` | Transcript scanner → cost/outcome/switching/task/action + drift check |
| Portal | `portal_page.py` | Static HTML launchpad with `shortcuts://` dispatch links |
| Shortcuts | `shortcuts_integration.py`, `dispatch_registry.py`, `shortcut_setup.py` | macOS Shortcuts bridge |
| Notifications | `notifications.py` | Cross-platform native notifications (macOS focus) |

### Real Function Call Paths

**Watcher** (the main product loop):

```
watch-once
→ commands/watch.py:handle_watch_once
→ watch_runtime.watch_once
→ _iter_recent_paths
→ _parse_source_path
→ extract_session_features
→ compute_session_cost + append_session_cost
→ append_outcome
→ _detect_provider_switch
→ _build_recommendation (evidence-backed)
→ create_prompt_bundle
→ ensure_task_record → save_task_record → save_sync_record
→ optional create_workflow_suggestion_action
→ optional create_council_start_action or create_recommendation_action
→ write_portal_html
→ check_drift (at end of pass)
```

**Council:**

```
council-start
→ commands/council.py:handle_council_start
→ ensure_task_record
→ run_council
→ render_member_prompt → provider subprocess calls
→ optional render_peer_review_prompt → peer review calls
→ synthesis call
→ save_council_outcome → write_review_html
→ task_from_council → save_task_record → save_sync_record
→ create_review_ready_action
```

**Workflow suggestion:**

```
watcher repetition/automation signal
→ _workflow_reason
→ write_cowork_shortcut_prompt
→ create_workflow_suggestion_action
→ dispatch action workflow_create
→ commands/workflow.py → workflow_runtime.create_workflow_task
```

**Portal / Shortcuts dispatch:**

```
saved pending action
→ portal_page.render_portal_html
→ shortcuts://run-shortcut?...
→ macOS Shortcut "Trinity Dispatch"
→ typed dispatch branch → local command or open action
```

---

## State Layout

Live state is under `~/.trinity/` by default (overridable via `TRINITY_HOME`).

```
~/.trinity/
├── tasks/              # Durable task records (one JSON per task)
├── actions/            # Pending action records
├── prompt_bundles/     # Saved prompt bundles
├── council_outcomes/   # Council outcome records
├── reviews/            # Post-hoc review results (JSON)
├── review_pages/       # Review static HTML
├── portal_pages/       # Static launchpad HTML
├── digest_pages/       # Weekly digest HTML
├── task_sync/          # Sync-safe task payloads
├── watcher/            # Cursor files for watch-loop resume
├── workflow_prompts/   # Generated workflow prompt artifacts
├── shortcut_setup/     # Shortcut installer recipe
├── cost_log.jsonl      # Per-session cost estimates
├── outcomes.jsonl      # Per-session outcome records for drift
├── scoreboard.json     # Aggregate provider scores
├── runs.jsonl          # Individual run traces
├── council_runs.jsonl  # Council outcome log
└── launch_events.jsonl # Launch/handoff events
```

### Dispatch Contract

Typed dispatch actions (used by Shortcuts bridge):

- `run_command`, `open_review`, `start_council`, `workflow_create`
- `open_path`, `open_url`, `run_applescript`

The `Trinity Dispatch` Shortcut should branch on `name`, not guess from shell text.

---

## Coding Conventions

### Style

- **Python 3.10+** (declared in `pyproject.toml`).
- **`from __future__ import annotations`** in every module for PEP 604 style.
- **Dataclasses everywhere** — no Pydantic, no attrs. Manual `to_dict()`.
- **No runtime dependencies** — `pyproject.toml` declares `dependencies = []`.
- **54 tests** across 7 test files. Pytest is configured as an optional dependency.

### Patterns

- **Shared utilities**: `utils.py` provides `now_iso()` and `stable_id()`.
- **Stable IDs**: All IDs are `sha1(prefix|parts...)[:16]` via `stable_id()`.
- **JSONL append logs**: `cost_log.jsonl`, `outcomes.jsonl`, `runs.jsonl`, etc.
- **JSON entity files**: Tasks, actions, bundles, outcomes, reviews are individual JSON files.
- **`to_dict()` filtering**: Strip `None`, empty strings, empty dicts, empty lists.
- **`now_iso()`**: UTC ISO 8601 with `microsecond=0`.
- **`trinity_home()`**: Returns `~/.trinity/` (or `$TRINITY_HOME`). All state paths go through this.
- **`project_root()`**: Resolves to the git repo root. Used only for `config.json` and source code.

### CLI structure

- `main.py` is a thin dispatcher using `set_defaults(handler=...)`.
- Command handlers live in `commands/` package (12 modules).
- Every subcommand prints JSON to stdout and returns.
- Config is only loaded for commands that need it.

---

## Product Guidance

### What's Working

1. **Watcher pipeline** — scan → ingest → features → cost → outcome → switch detection → task → action → portal → notification. Full loop works.
2. **Multi-provider ingestion** — four parsers handle real local formats with timestamp and token extraction.
3. **Council with peer review** — member responses → anonymized peer review → synthesis. Flagship cross-provider feature.
4. **Cost and drift tracking** — per-session cost estimation, rolling outcome comparison, drift alerting.
5. **Evidence-backed recommendations** — queries outcome + cost logs for concrete evidence.
6. **Post-hoc review** — Council-lite: ask one provider to critique another's output. Dark-themed HTML.
7. **File-backed state** — one file = one entity. No joins. No migrations.
8. **macOS-native dispatch** — `shortcuts://` URL bridge.
9. **Test coverage** — 54 tests across 7 files, all passing.

### What Needs Attention Next

#### P0 (Done)

- ~~State directory migration~~ ✅
- ~~Cross-provider switching detection~~ ✅
- ~~Evidence-backed recommendations~~ ✅
- ~~Post-hoc review~~ ✅

#### P1 (Next)

- **Council partial failure handling.** If one member provider fails, continue with remaining.
- **Automatic Council trigger.** When the watcher detects a switch with divergent outcomes.
- **Shortcut installer.** Generate a downloadable `.shortcut` file.
- **Provider adapter hardening.** Version detection, path discovery, `trinity-local adapters` command.

#### Lower Priority

- **`_guess_task_kind()` is brittle.** Will be replaced by embedding-based classification (P2 research).
- **Portal auto-refresh.** Add `<meta http-equiv="refresh">` tag.
- **`status` command.** One-shot summary.
- **Watch loop graceful shutdown.** Signal handling or launchd wrapper.

---

## Verified Status

- `python3 -m compileall src` — clean
- `pytest tests/ -v` — **54 passed**
- Command registration — correct (12 command modules)
- `watch-once --source cowork` — runs cleanly
- `portal-html` — writes to `~/.trinity/portal_pages/`
- `shortcut-setup` — writes to `~/.trinity/shortcut_setup/`
- `digest --json` — clean output

---

## Development Notes

- Run tests: `.venv/bin/python -m pytest tests/ -v`
- Or: `TRINITY_HOME=/tmp/trinity-test PYTHONPATH=src python3 -m pytest -q`
- `main.py` is a dispatcher only. Add behavior in `commands/*` or runtime modules.
- Keep the product centered on observing, comparing, dispatching, and learning.
- Not on building another chat frontend.
