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
- **k-NN advisory layer** (embedding-based routing suggestions)
- council (cross-provider comparison)
- post-hoc review (Council-lite)
- workflow suggestion → Shortcuts dispatch
- weekly digest
- **research pipeline** (hard mining, evaluation, analytics)

Not:

- the older `run` coordinator loop (LEGACY)
- a standalone chat UX
- an always-on daemon

---

## Architecture Overview

### CLI Dispatcher

Entry: `src/trinity_local/main.py` — thin dispatcher only.

Registered command groups (15 modules):

| Module | Key Commands |
|--------|-------------|
| `commands/run.py` | `run` (LEGACY — deprecated) |
| `commands/ingest.py` | `features`, `examples` |
| `commands/tasks.py` | `task-create`, `task-show`, `task-sync`, `bundle-create`, `launch-create` |
| `commands/council.py` | `council-start`, `council-run`, `council-prompt`, `council-outcome`, `council-html` |
| `commands/portal.py` | `portal-html`, `open-review` |
| `commands/actions.py` | `action-list`, `action-suggest`, `action-council`, `action-notify`, `action-complete` |
| `commands/shortcuts.py` | `shortcut-url`, `shortcut-run`, `action-shortcut`, `shortcut-setup`, `shortcut-install` |
| `commands/watch.py` | `watch-once`, `watch-loop` |
| `commands/workflow.py` | `workflow-create` |
| `commands/digest.py` | `digest` |
| `commands/review.py` | `review` |
| `commands/adapters.py` | `adapters` |
| `commands/status.py` | `status` |
| `commands/helpers.py` | Internal utilities |
| `commands/research.py` | `replay`, `rank`, `hard`, `hardeval`, `analytics` |

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
| Watch | `watch_runtime.py` | Transcript scanner → cost/outcome/switching/task/action + k-NN advisory + drift check |
| Portal | `portal_page.py` | Static HTML launchpad with `shortcuts://` dispatch links |
| Shortcuts | `shortcuts_integration.py`, `dispatch_registry.py`, `shortcut_setup.py` | macOS Shortcuts bridge |
| Notifications | `notifications.py` | Cross-platform native notifications (macOS focus) |
| Adapters | `adapters.py` | Provider adapter detection and version tracking |
| **Embeddings** | `embeddings/` (`__init__`, `backend_mlx`, `backend_tfidf`, `cache`) | Shared embedding layer (nomic-embed-text-v1.5, 512d Matryoshka, persistent cache) |
| **k-NN Advisor** | `knn_advisor.py` | Advisory layer: queries hard-example corpus for routing advice |
| **k-NN Analytics** | `knn_analytics.py` | Production observability: evidence spam, threshold brittleness, product metrics |
| **Hard Mining** | `research/hard_mining.py` | Embedding-based cross-provider hard example mining |
| **Hard Eval** | `research/hard_eval.py` | 5-metric evaluation suite for hard examples |
| Replay | `research/replay.py` | Transcript replay and routing example generation |
| Ranking | `research/ranking.py` | Heuristic vs k-NN ranking evaluation |

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
→ _detect_provider_switch (embedding + word-overlap)
  → if switch: mark_suggestion_outcome (analytics)
→ _build_recommendation (heuristic, evidence-backed)
→ _upgrade_recommendation (k-NN advisory)
  → knn_advisor.advise → embed → k-NN lookup → KnnAdvice
  → _log_advisory (analytics event)
  → upgrade: recommendation → council if neighbors agree
  → annotate: knn_method, top2, evidence
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

**Research pipeline:**

```
trinity-local hard
→ mine_hard_via_embeddings
  → scan 59k sessions, extract features
  → sample 50/provider, embed prompts
  → find cross-provider pairs (sim > 0.7)
  → signal-based: switches, errors, long sessions
→ save to ~/.trinity/research/hard_examples/

trinity-local hardeval
→ load hard examples
→ run heuristic + k-NN evaluators
→ report 5 metrics: reroute recall, needs_council P/R,
  switch prediction, top-2 accuracy, NN evidence quality

trinity-local analytics
→ load ~/.trinity/analytics/knn_advisory.jsonl
→ report: evidence spam, threshold brittleness,
  act rate, switch-after-acted rate, alerts
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
├── bin/
│   └── trinity-dispatch  # Dispatch wrapper script (created by setup.sh)
├── cache/
│   └── embeddings.jsonl  # Persistent embedding cache
├── research/
│   ├── hard_examples/  # Mined hard examples (k-NN corpus)
│   └── replay_examples/  # Replay-generated routing examples
├── analytics/
│   ├── knn_advisory.jsonl        # Every k-NN advisory call
│   └── knn_advisory_report.json  # Latest analytics report
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

Flow:

```
macOS Shortcut "Trinity Dispatch"
→ Receives JSON text input: {"name":"...", "args":{...}, "task_id":"...", "metadata":{...}}
→ Passes to stdin: trinity-dispatch <json-payload>
→ ~/.trinity/bin/trinity-dispatch (Python wrapper)
  → dispatch_registry.make_dispatch_action(...)
  → dispatch_registry.command_for_dispatch(...)
  → exec /bin/zsh -lc '<command>'
```

The wrapper (`shortcut_setup.py:_render_dispatch_wrapper`) handles PATH injection so the venv's `trinity-local` is always resolvable. The Shortcut calls the wrapper via shell script action.

---

## Coding Conventions

### Style

- **Python 3.10+** (declared in `pyproject.toml`).
- **`from __future__ import annotations`** in every module for PEP 604 style.
- **Dataclasses everywhere** — no Pydantic, no attrs. Manual `to_dict()`.
- **No runtime dependencies** — `pyproject.toml` declares `dependencies = []`.
  - `[mlx]` extras for sentence-transformers + embedding support.
  - `[test]` extras for pytest.
- **123 passed** across 12 `test_*.py` files.

### Patterns

- **Shared utilities**: `utils.py` provides `now_iso()` and `stable_id()`.
- **Stable IDs**: All IDs are `sha1(prefix|parts...)[:16]` via `stable_id()`.
- **JSONL append logs**: `cost_log.jsonl`, `outcomes.jsonl`, `runs.jsonl`, `knn_advisory.jsonl`, etc.
- **JSON entity files**: Tasks, actions, bundles, outcomes, reviews, hard examples are individual JSON files.
- **`to_dict()` filtering**: Strip `None`, empty strings, empty dicts, empty lists.
- **`now_iso()`**: UTC ISO 8601 with `microsecond=0`.
- **`trinity_home()`**: Returns `~/.trinity/` (or `$TRINITY_HOME`). All state paths go through this.
- **`project_root()`**: Resolves to the git repo root. Used only for `config.json` and source code.
- **Graceful degradation**: Features that depend on optional packages (embeddings, MLX) return None or fall back silently.
- **Analytics never crash**: All analytics logging is wrapped in `try/except`. The watcher must never fail because of observability code.

### CLI structure

- `main.py` is a thin dispatcher using `set_defaults(handler=...)`.
- Command handlers live in `commands/` package (15 modules, 40 subcommands).
- Every subcommand prints JSON to stdout and returns.
- Config is only loaded for commands that need it.

---

## Product Guidance

### What's Working

1. **Watcher pipeline** — scan → ingest → features → cost → outcome → switch detection → k-NN advisory → task → action → portal → notification. Full loop works.
2. **k-NN advisory layer** — embedding-based routing suggestions integrated into the watcher. Can upgrade recommendations to council, add evidence, suggest reroutes. Advisory only, never autonomous.
3. **Multi-provider ingestion** — four parsers handle real local formats with timestamp and token extraction.
4. **Council with peer review** — member responses → anonymized peer review → synthesis. Flagship cross-provider feature.
5. **Cost and drift tracking** — per-session cost estimation, rolling outcome comparison, drift alerting.
6. **Evidence-backed recommendations** — queries outcome + cost logs + k-NN neighbors for concrete evidence.
7. **Hard example mining** — embedding-based cross-provider matching finds routing conflicts (1,026 hard examples from 59k sessions).
8. **5-metric evaluation** — reroute recall 38.7%, needs_council P/R 98%, top-2 provider 99.5%, NN agreement 96.6%.
9. **Production analytics** — evidence spam check, threshold brittleness detection, act rate, switch-after-acted rate tracking. Note: the analytics log is populated only after live `watch-once` or `watch-loop` runs with a hard-example corpus present.
10. **Post-hoc review** — Council-lite: ask one provider to critique another's output. Dark-themed HTML.
11. **File-backed state** — one file = one entity. No joins. No migrations.
12. **macOS-native dispatch** — `shortcuts://` URL bridge. Portal includes `<meta http-equiv="refresh" content="30">`.
13. **Test coverage** — 119 passed, 4 skipped across 10 files. Skips are embedding-dependent k-NN advisor tests.

### What Needs Attention Next

#### Done (P0-P1)

- ~~State directory migration~~ ✅
- ~~Cross-provider switching detection~~ ✅
- ~~Evidence-backed recommendations~~ ✅
- ~~Post-hoc review~~ ✅
- ~~Council partial failure handling~~ ✅
- ~~Automatic Council trigger on switch~~ ✅
- ~~Provider adapter hardening~~ ✅ (`trinity-local adapters`)
- ~~Shortcut installer~~ ✅ (`trinity-local shortcut-install`)
- ~~Embeddings package~~ ✅ (nomic-embed-text-v1.5 via sentence-transformers)
- ~~Hard example mining~~ ✅ (embedding-based cross-provider matching)
- ~~Extended evaluation~~ ✅ (5-metric suite)
- ~~k-NN advisory live rollout~~ ✅ (integrated into watcher)
- ~~Production analytics~~ ✅ (evidence spam, threshold brittleness, product metrics)

#### Next

- **Threshold tuning.** Per-task-kind council thresholds based on analytics data.
- **Corpus refresh strategy.** When to re-mine hard examples (stale corpus warning after 7 days).
- **Real switch tracking.** Watcher should detect temporal provider transitions within N minutes.
- **TT integration.** If web transcripts (taste-terminal) are needed, requires a new parser.

#### Lower Priority

- **`_guess_task_kind()` refinement.** Currently keyword-based. Embedding-based classification would be more robust.

#### Shortcut Dispatch Architecture

The Trinity Dispatch shortcut integration (new, April 2026):

1. **Shortcut setup** (`shortcut_setup.py`):
   - Three-tier install: already installed? → bundled .shortcut file? → manual setup
   - `write_dispatch_wrapper()` generates `~/.trinity/bin/trinity-dispatch` (Python executable)
   - `run_installer()` signs bundled shortcut and opens import dialog

2. **Dispatch wrapper** (generated `trinity-dispatch`):
   - Reads JSON from stdin or argv[1]
   - Calls `dispatch_registry.make_dispatch_action()` + `command_for_dispatch()`
   - Injects venv bin into PATH before subprocess execution
   - Runs command via `/bin/zsh -lc '<command>'`

3. **Shortcut invocation** (macOS Shortcuts app):
   - Get text input → Run shell script with wrapper
   - Sets Input=text, Pass Input=to stdin

#### Known Risks

- **Legacy run stack.** `commands/run.py`, `coordinator.py`, `runner.py`, `prompts.py` are marked LEGACY/deprecated but still present. Maintenance-drift risk — if core schemas change, legacy code may silently break. Not worth removing yet, but don't extend.
- **watch_loop operator surface.** Errors now log to `analytics/watch_errors.jsonl` + optional notification, but there's no stronger operator surface (e.g., `trinity-local errors` command, error count in `status`). A recurring bug can still go unnoticed without checking the log file.
- **`[mlx]` extra naming.** The `[mlx]` extra in `pyproject.toml` actually installs `sentence-transformers`, not a pure MLX stack. Name is slightly overloaded. Renaming to `[embeddings]` would be clearer but is a breaking change for existing installs.
- ~~**Dispatch command injection risk**~~ ✅ Fixed in dispatch_registry.py:75 using `shlex.quote()` for proper shell escaping.
- **Dispatch wrapper venv binding.** The wrapper's shebang points to the Python executable at install time. If venv is relocated/deleted, wrapper becomes stale. No validation of venv existence before execution.
- **Shortcut import silent failure.** If `open <shortcut_file>` fails, user sees "import dialog opened" but nothing happens. No timeout/retry logic. `shortcuts sign` may not exist on older macOS versions.

---

## Key Product Metrics

The analytics system (`trinity-local analytics`) tracks:

| Metric | Purpose |
|--------|---------|
| `act_rate` | What % of suggestions are acted on? |
| `switch_after_acted_rate` | Of acted-on suggestions, how many later switched? **The key metric — if this drops, the product is getting smarter.** |
| `upgrade_rate` | How often does k-NN override heuristic? |
| `evidence_count_p95` | Is evidence spam growing? |
| `confidence_by_task_kind` | Is the threshold stable across task types? |

---

## Verified Status

- `pytest tests/ -v` — **123 passed** across 12 `test_*.py` files
- 15 command modules registering 40 CLI subcommands
- `watch-once --source cowork` — runs cleanly
- `portal-html` — writes to `~/.trinity/portal_pages/`
- `shortcut-install` — creates Trinity Dispatch shortcut + dispatch wrapper
- `setup.sh` — one-line setup: venv, package, config, wrapper, shortcut import
- `digest --json` — clean output
- `hard` — mines 1,026 hard examples from 59k sessions
- `hardeval` — 5-metric eval: k-NN beats heuristic on all metrics
- `analytics` — report structure verified (log is empty until live watch runs with corpus)
- Dispatch wrapper (`~/.trinity/bin/trinity-dispatch`) — reads JSON from stdin, resolves to CLI commands

---

## Development Notes

- Run tests: `.venv/bin/python -m pytest tests/ -v`
- Or: `TRINITY_HOME=/tmp/trinity-test PYTHONPATH=src python3 -m pytest -q`
- `main.py` is a dispatcher only. Add behavior in `commands/*` or runtime modules.
- Keep the product centered on observing, comparing, dispatching, and learning.
- Not on building another chat frontend.
- Embeddings require `pip install -e '.[mlx]'` — all embedding features gracefully degrade without it.
