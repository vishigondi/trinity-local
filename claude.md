---
class: live
---

# claude.md — Trinity Local

> **Your taste, ported — Trinity picks the answer you would have picked.**

Hero: *"Your taste, ported. Lives inside Claude Code, Codex CLI, Antigravity, and Cursor."*

Sub: *"No new app. No service. No API key. Your transcripts never leave your machine."*

Trinity is an MCP server that reads your existing CLI transcripts (Claude Code, Codex, Antigravity, Cursor — plus claude.ai / chatgpt.com / Gemini Takeout exports), extracts a **lens** (the pattern in how you rephrase, judge, and decide), and runs hard questions through all three frontier providers in your voice. The chairman synthesizes a single answer the user would have picked. Status: v1.7.4 shipped May 13–15, 2026, pyproject `<!-- canonical:version -->1.7.5<!-- /canonical -->`; <!-- canonical:test_count -->1648<!-- /canonical --> tests passing + <!-- canonical:skipped_count -->4<!-- /canonical --> skipped (commit `2bbb333` regenerated `docs/launchpad_example.png` post Phase-3d UI swap and cleared the formerly-intentional fail from the tightened `TestLaunchpadScreenshotFreshness` guard); <!-- canonical:doc_consistency_guards -->103<!-- /canonical --> doc-consistency guards green; <!-- canonical:mcp_tool_count -->8<!-- /canonical --> MCP tools live; <!-- canonical:cli_command_count -->42<!-- /canonical --> CLI subcommands across <!-- canonical:command_module_count -->21<!-- /canonical --> user-facing command modules (20 in `CORE_COMMAND_MODULES` + `install` in `OPTIONAL_COMMAND_MODULES`); <!-- canonical:smoke_surface_count -->34<!-- /canonical -->-surface browser smoke gate passing (`python scripts/browser_smoke.py`).

## Auto-Dream coexistence (load-bearing positioning)

Anthropic shipped official **Auto-Dream** in Claude Code — 24h+5-sessions trigger, 4-phase REM-mirror, 200-line MEMORY.md cap (<https://claudefa.st/blog/guide/mechanics/auto-dream>). Trinity's `dream` verb collides; the **cross-provider extension** framing is now the differentiator. Anthropic dreams *Claude* conversations; Trinity dreams across Claude + Codex + Antigravity. The three labs are commercially prevented from crossing — Anthropic can't recommend ChatGPT, OpenAI can't recommend Claude, Google can't recommend either. Someone outside the labs has to ship the layer above them. This file applies Anthropic's 200-line MEMORY.md discipline to itself; historical context lives in `docs/historical/`.

## Architectural commitments (load-bearing, not negotiable)

1. **No LLM calls outside councils.** Ingest, embedding, theme assignment, search ranking, clustering — pure embeddings + heuristics + metadata. The only LLM invocations Trinity makes are council member calls and chairman synthesis calls, both riding user subscriptions.
2. **Prompt content never uploads.** Even with v1.1 aggregation enabled, only categorical routing labels (`task_type`, `provider_scores`, `winner`) leave the machine. Anonymous, opt-in only.
3. **Local-first inference.** Phase 9's learned router runs on the user's hardware. No hosted controller. No per-call API billing.
4. **Subsidized consumer credits as cost basis.** Trinity dispatches via the user's own CLI subscriptions (Claude Code, Codex, Antigravity). If anyone proposes a hosted API tier, push back hard — that destroys both cost basis and privacy.
5. **HF Hub offline by default.** `main()` pins `HF_HUB_OFFLINE=1` + `TRANSFORMERS_OFFLINE=1` via `setdefault` at startup. The embedding model is pulled once via `huggingface-cli download nomic-ai/nomic-embed-text-v1.5`; after that Trinity loads from `~/.cache/huggingface/hub/` and never contacts the Hub during normal operation.

## MCP surface

### The eight MCP tools (`mcp_server.py`)

The full public surface is **<!-- canonical:mcp_tool_count -->8<!-- /canonical --> tools** — 4 canonical + 3 v1.5 additions + 1 launch-arc addition (`handoff`). Tool docstrings ARE the contract the agent reads at handshake.

**Canonical four (lifecycle order):**

1. **`route(task, harness?, available_models?, budget?, latency?, current_provider?)`** → `{mode, primary, challenger, confidence, reason, fallback}`. No model calls — heuristic + k-NN + chairman picker. Cheap; call before the harness picks a model. `budget` ∈ {`low`, `normal`, `high`}; `latency` ∈ {`fast`, `normal`, `patient`}.

2. **`run_council(task, goal?, members?, mode?, sequence?, primary_provider?, responses?, wait_seconds?)`** → council launched asynchronously. `mode="parallel"` (default) runs members concurrently then chairman; `mode="chain"` runs sequence serially. When `responses=[...]` is provided, skips dispatch and runs chairman synthesis only (subsumes the legacy `judge` tool, formerly registered). `wait_seconds > 0` blocks up to that many seconds for the outcome inline; otherwise returns the `council_run_id` and the caller polls `get_council_status`.

3. **`get_persona()`** → returns `~/.trinity/memories/lens.md`. Exposes the persona once at session start so any harness can tailor responses without an MCP round trip per call.

4. **`get_council_status(council_run_id)`** → in-protocol polling for async councils. Returns status (running/completed/failed/canceled), per-member progress, synthesis state, and outcome summary (winner, agreed/disagreed claims, routing_lesson) when complete.

**v1.5 trio:**

5. **`ask(query, available_providers?, top_k?)`** → cheap single-call default routing. The 90% case: one call, one provider, chairman-blessed verdict. Pulls from cortex picks first (high-trust rule → use directly), falls back to k-NN advisory, finally to heuristic.

6. **`get_picks(basin_id?, min_trust?)`** → agent-facing introspection into extracted cortex routing patterns. Returns `{rules: {basin_id: pattern}, total_basins, returned}` — patterns carry provider/reasoning/trust score/source councils. `basin_id` narrows to one basin; `min_trust` floor filters by `trust_score.value`.

7. **`mark_pick_wrong(basin_id, reason?, reset?)`** → user-veto on an extracted pick. Each call increments `override_count`; `effective_trust = raw_trust × 0.5^count`. Persists across consolidations — a fresh extraction can't erase the user's signal. `reset=true` clears the count.

**Launch-arc addition:**

8. **`handoff(target_provider, continuation?, num_turns?)`** → cross-provider conversation continuity. Pulls recent (user, assistant) turns from the cross-provider prompt index, packages them as "continuing this thread" context, dispatches to a DIFFERENT provider. Structurally non-refutable: only Trinity has the cross-provider index. CLI mirror: `trinity-local handoff <provider>`.

(`record_outcome` retired 2026-05-21 — chairman's pick is the supervision signal now. `get_eval_summary` retired 2026-05-18. See `docs/historical/retirement-log.md`.)

**Actionable rule for agents in this repo:** before calling `AskUserQuestion` with multiple options that are NOT user-personal preferences, FIRST run `mcp__trinity-local__ask` or `mcp__trinity-local__run_council`. Treat `AskUserQuestion` as reserved for *user-personal* choices; Trinity is the default for *product/architectural* choices. Skip Trinity for trivial bugs, syntax lookups, mechanical refactors, information retrieval. After a council, treat the chairman's `agreed_claims` / `disagreed_claims` as the source of truth.

### State layout

Live state under `~/.trinity/`. Two conventions: **entities** use JSON-per-file under a named directory; **event logs** use append-only JSONL. Anything not on this diagram is either retired (see `docs/historical/retirement-log.md`) or written by a feature you haven't run yet.

```
~/.trinity/
├── conversations/                  # Chrome-ext Native-Messaging captures (claude.ai / chatgpt.com / gemini.google.com)
├── todos/                          # Durable todo records (the directory name; `tasks_dir()` migrates legacy `tasks/` → `todos/`)
├── actions/                        # Pending action records
├── prompt_bundles/                 # Saved prompt bundles
├── council_outcomes/               # Council outcome JSON (routing_label + chain_steps) — canonical supervision ledger
├── reviews/                        # Post-hoc review JSON
├── review_pages/                   # Static HTML review pages
├── portal_pages/                   # Static launchpad (file://); status/ holds live council progress
├── task_sync/                      # Sync-safe task payloads
├── share/                          # PNG share-card outputs (me-card / council-share / eval-share defaults)
├── evals/                          # Eval sets (eval-build) + per-run results (eval-run)
├── settings/                       # Telemetry settings
│
├── prompts/                        # Raw prompt index (renamed from memory/; one-time migration in prompts_dir())
│   ├── prompt_nodes.jsonl          #   PromptNode index (tier 1)
│   ├── turn_windows.jsonl          #   TurnWindow index (tier 2 — local context)
│   └── cursors.json                #   Per-source ingest cursors (consumed by ingest_recent())
├── memories/                       # Cognitive lens (the three thinking files)
│   ├── lens.md                     #   paired tensions (value)
│   ├── topics.json                 #   subject basins (semantic + lens evidence map)
│   └── vocabulary.md               #   anchors + homonyms + synonyms (linguistic)
├── core.md                         # Singular distillation chairman reads first
├── scoreboard/                     # Operational scoreboards (NOT cognitive memory)
│   ├── picks.json                  #   extracted model-selection rules per basin
│   └── routing.json                #   per-task-type provider track record
├── me/                             # Lens-build pipeline output (rejections/decisions/lenses/orderings/merges)
│
├── outcomes.jsonl                  # Per-session outcome records (drift)
├── council_runs.jsonl              # Council outcome log
├── launch_events.jsonl             # Launch/handoff events
├── council_feedback.jsonl          # User verdicts feeding the personal routing table
├── analytics/                      # routing_label_events / knn_advisory / dispatch_outcomes
├── cold_start_scan.json            # First-spawn auto-scan
└── research/                       # Optional user-curated k-NN advisory corpus (read-only for Trinity)
```

### Glossary (load-bearing terms)

- **prompts** — what the user owns (raw, indexed in `~/.trinity/prompts/`). Inputs to `dream`.
- **dream** — the verb. Reads prompts, emits core memories (offline, your data). Cross-provider analog of Anthropic's Auto-Dream (see callout above).
- **core memories** — three *thinking* memories that compose the lens. Chairman reads `core.md` (identity) first, drills to `lens.md` (paired tensions), `topics.json` (subject basins), or `vocabulary.md` (linguistic anchors) on demand. Generation runs bottom-up; reads run top-down. Live under `~/.trinity/memories/` (with `core.md` at `~/.trinity/core.md`).
- **scoreboards** — operational bookkeeping at `~/.trinity/scoreboard/` (`picks.json`, `routing.json`). Excluded from chairman context; surfaced on the launchpad routing card. Computed from `council_outcomes/`.
- **council** — multi-model deliberation (parallel or chain) ending in chairman synthesis.
- **chairman** — the synthesis model in a single council. Reads `core.md`, emits structured Routing JSON.
- **Conductor** (v1.5+) — flagship model that picks which model gets which sub-task across a session. Different role than chairman; same model family may play both.
- **member** — a provider acting as one voice in a council. Canonical term in code AND copy.
- **harness** — the CLI/IDE the user is in (Claude Code, Codex CLI, Antigravity, Cursor). Trinity registers as an MCP server inside each via `install-mcp`.
- **task_type** — short label for "what kind of question this is" (heuristic on input, also emitted by chairman). NOT the same as `category` (coarser LMArena-aligned grouping).

### Provider trio across layers

Same lab gets a different name at each layer; what users see depends on the entry surface.

| layer | Anthropic | OpenAI | Google |
|---|---|---|---|
| mobile app brand | Claude | ChatGPT | *(no Antigravity mobile yet)* |
| cloud agent harness | Claude Code | Codex agents | *(no equivalent)* |
| desktop CLI binary | `claude -p` | `codex exec` | `agy -p` |
| Trinity slug (code/config/JSON) | `claude` | `codex` | `antigravity` |
| underlying model | Claude Opus 4.7 / Sonnet 4.6 / Haiku 4.5 | GPT-5.5 | Gemini 3.1 Pro Preview |

Use **slugs** in code/config/file paths/JSON keys. Use **model names** in user-facing UI. Use the mixed marketing trio ("Claude, Codex, and Gemini") in launch copy.

## Architecture pointers

CLI dispatcher: `src/trinity_local/main.py` (thin; `set_defaults(handler=...)`). 21 user-facing command modules in `commands/`. Notable: `dream.py` (cold-start verb), `me.py` (`lens-build`), `council.py` (`council-start` / `council-launch` / `council-stop` / `council-share` / `council-iterate`), `cortex.py` (`consolidate` + `cortex-override`), `eval.py` (`eval-build` / `eval-run` / `eval-show` / `eval-share`), `handoff.py`, `install.py` (`install-mcp` writes Claude Code / Codex / Antigravity / Cursor configs — 4 CLI harnesses), plus `adapters.py`, `debug.py`, `download_embedder.py`, `install_umbrella.py`, `me_card.py`, `portal.py`, `replay.py`, `review.py`, `seed.py`, `status.py`, `telemetry.py`, `update.py`, `vocabulary.py`, `watch.py` (`ingest-recent`).

Core layers (`src/trinity_local/`, selected — full tree is 113 `.py` files; `find src/trinity_local/ -name "*.py"`): `mcp_server.py` (MCP entrypoint), `ask.py` (the v1.5 `ask` MCP handler — cheap single-call routing), `council_runner.py` + `council_runtime.py` + `council_schema.py` + `council_status.py` + `council_review.py`, `personal_routing.py` (chairman-pick aggregation feeding the routing table — load-bearing post-rating-retirement), `memory/` (`schemas.py`, `store.py`, `index.py`, `replay_value.py`), `embeddings/` (`backend_mlx.py`, `backend_tfidf.py`), `ingest.py`, `categories.py`, `ranker/` (`base.py`, `fallback.py`, `heuristic.py`, `knn_ranker.py`, `chairman_picker.py`, `types.py`), `cortex_geometry.py` (geometric median + bimodality + participation-ratio for cortex consolidation; dependency-free stdlib), `me_builder.py` (lens-build pipeline) + `me_lenses.py`, `evals/` (`builder.py` + `scorer.py` — task #122 corpus-based eval harness), `doctor.py` (cold-install + post-install health checks; ~55 callers — `trinity-local status` rides on it), `drift.py` (drift surfacing on launchpad), `design_system.py` (shared CSS + Vue3 chip vocabulary for launchpad/memory-viewer/review pages), `state_paths.py`, `runtime_env.py` (PATH-injection env builder; `subprocess_utils.py` was planned but the split didn't materialize), `task_types.py` (`guess_task_type()`), `refresh.py`, `dispatch_registry.py` + `capture_host.py` + `shortcuts_integration.py` (inert shim — `shortcut_setup.py` / `dispatch_runner.py` retired 2026-05-17), `launchpad_data.py` + `launchpad_template.py` + `launchpad_runtime.py` + `launchpad_page.py` + `memory_viewer.py`, `share_card_base.py` + `me_card.py` + `eval_card.py` + `council_card.py`, `council_feedback.py`, `telemetry.py`, `notifications.py`, `adapters.py`, `config.py`, `providers.py`, `utils.py`, `retired_names.py`.

## Install / surface notes

Run `trinity-local install-mcp` once to register Trinity's MCP server with the four CLI harnesses (Claude Code → `~/.claude.json`, Antigravity → `~/.gemini/settings.json`, Codex CLI → `~/.codex/config.toml`, Cursor → `~/.cursor/mcp.json`). Each harness spawns `trinity-local --mcp` as a stdio child; ~62MB resident while connected. The launchpad → Chrome extension → Native Messaging → `trinity-local-capture-host` → CLI pipeline is independent of MCP (one-shot subprocess at every step).

## MCP server hot-reload (development only)

Set `TRINITY_MCP_WATCH=1` to enable a file watcher that calls `os._exit(0)` on any `.py` change. The MCP launcher auto-respawns. Never enable in shipped configs. Adding *new* MCP tools (vs. modifying existing handlers) may require a Claude Code restart to make them visible.

## Coding conventions

- **Python 3.10+**. `from __future__ import annotations` in every module for PEP 604 style.
- **Dataclasses everywhere**. No Pydantic, no attrs. Manual `to_dict()`.
- **Minimal runtime dependencies.** Three: `Pillow>=10` (PNG share cards), `mcp>=1.0` (MCP server runtime — `install-mcp` registers Trinity in Claude Code / Codex / Antigravity / Cursor), `numpy>=1.26` (lens-build cosine matmul, k-means in `me/basins.py`, vocabulary stats). `[mlx]` extras add `sentence-transformers>=2.2`, `einops`, and `torch>=2.0` for real 768d embeddings; without them the embedder falls back to the stable SHA-1 TF-IDF projection. `[test]` extras add `pytest>=7`.
- **Stable IDs** via `stable_id()` (`utils.py`) — `sha1(prefix|parts...)[:16]`.
- **JSONL append logs** for analytics; JSON entity files for objects.
- **`to_dict()` filters None / empty strings / empty containers**.
- **`now_iso()`** — UTC ISO 8601 with `microsecond=0`. **`trinity_home()`** — `~/.trinity/` (or `$TRINITY_HOME`).
- **Graceful degradation** — features depending on `[mlx]` fall back silently. Analytics never crash.

## Launch arc

The five-workstream distribution arc and full forward-arc narrative now live in [`docs/historical/brand-evolution.md`](docs/historical/brand-evolution.md) and [`docs/scale-plan.md`](docs/scale-plan.md). Known-shipped workstreams: task #117 (Standardize `~/.trinity/` — ✓ shipped), task #118 (Subsidy-window narrative — ✓ shipped), task #119 (Handoff mechanism — ✓ shipped 2026-05-14), task #122 (Corpus-based eval harness — ✓ shipped). Open: #114 MCP-dropdown distribution, #115/#120/#121 first-run wow + Gemini-Google branch, #116 real-corpus benchmarks on shipped installs, #109 `principles.md` pipeline (data-gated, needs ≥100 council outcomes).

## Verified status

- `pytest -q` — **<!-- canonical:test_count -->1648<!-- /canonical --> passed** + <!-- canonical:skipped_count -->4<!-- /canonical --> skipped (167s wall, all gated real-Chrome smokes intentionally skipped). <!-- canonical:doc_consistency_guards -->103<!-- /canonical --> doc-consistency guards in `test_doc_count_consistency.py` defending launch-credibility claims. The screenshot-freshness guard (`TestLaunchpadScreenshotFreshness::test_launchpad_example_not_grossly_stale`) is the canary — it fires when `docs/launchpad_example.png` falls more than a day behind `launchpad_template.py`; clear it with the regen recipe in the test's error message. The screenshot-freshness guard (`TestLaunchpadScreenshotFreshness::test_launchpad_example_not_grossly_stale`) is the canary — it fires when `docs/launchpad_example.png` falls more than a day behind `launchpad_template.py`; clear it with the regen recipe in the test's error message.
- `trinity-local --mcp` exposes <!-- canonical:mcp_tool_count -->8<!-- /canonical --> tools (canonical 4 + v1.5 trio + launch-arc `handoff`).
- `trinity-local install-mcp` writes 4 CLI harnesses (Claude Code, Antigravity, Codex, Cursor).
- `python scripts/browser_smoke.py` — <!-- canonical:smoke_surface_count -->34<!-- /canonical -->-surface browser smoke gate green.

## Development

- Run tests: `.venv/bin/python -m pytest tests/ -v`
- Isolated state: `TRINITY_HOME=/tmp/trinity-test PYTHONPATH=src python3 -m pytest -q`
- Embeddings require the MLX extras (`pip install -e '.[mlx]'`); without them the embedder uses the SHA-1 TF-IDF fallback.
- `AGENTS.md` is a thin redirect to here so Codex / other agent harnesses don't drift.

## Historical context (read these when you need depth)

- [`docs/historical/principles.md`](docs/historical/principles.md) — 21 numbered meta-principles extracted from the fixes. Each earned its place by costing time.
- [`docs/historical/retirement-log.md`](docs/historical/retirement-log.md) — what Trinity used to have, why it was retired, when. Canonical registry is `src/trinity_local/retired_names.py`.
- [`docs/historical/brand-evolution.md`](docs/historical/brand-evolution.md) — pivot trail to "Your taste, ported"; ratifying councils; v1.7.5 Auto-Dream-coexistence framing.
- [`docs/spec-v1.md`](docs/spec-v1.md) — locked v1.0 launch spec.
- [`docs/spec-v1.5.md`](docs/spec-v1.5.md) — active next-trajectory spec.
- [`docs/spec-v1.6.md`](docs/spec-v1.6.md) — browser-extension + Native-Messaging spec.
- [`docs/three-tier-architecture.md`](docs/three-tier-architecture.md) — MCP server (primary) / Pip engine / Chrome Extension; `~/.trinity/` is the invariant data contract.
- [`docs/cross-platform-spec.md`](docs/cross-platform-spec.md) — terminal → desktop → mobile phasing.
- [`docs/scale-plan.md`](docs/scale-plan.md) — long-form roadmap.
- [`docs/product-spec.md`](docs/product-spec.md) — feature-level spec.
- `CHANGELOG.md` — timestamped append-only.
