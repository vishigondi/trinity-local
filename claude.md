# claude.md — Trinity Local

> Agent-facing project context. Companions:
> - [`docs/spec-v1.md`](docs/spec-v1.md) — locked v1.0 launch spec (ships May 13–15)
> - [`docs/spec-v1.5.md`](docs/spec-v1.5.md) — **active next-trajectory spec** (target June 3, 2026): MCP-primary, hippocampus+cortex memory, local model dispatch, rate-limit dodge, flagship-as-Conductor (no training)
> - [`docs/spec-v2.md`](docs/spec-v2.md) — sunset (trained-coordinator path). Preserved as architectural-decision history; reopens only if v1.5 hits a quality ceiling.
> - [`docs/scale-plan.md`](docs/scale-plan.md) — long-form roadmap.

## Project Identity

**Trinity Local stops you copy-pasting prompts.** v1 hero (three beats, ratified through three rounds of cross-provider council iteration on `bundle_42f8cea9c9e705e5`):

> **Stop copy-pasting prompts. Own your context. Dream your core memories.**
> *One question. Every model you use. One answer that knows you.*

The brand axis: **prompts** (raw, yours, indexed) → **dream** (the verb only Trinity has — offline synthesis on your data) → **core memories** (what dream creates: picks + the lens + the routing table). Plural intentional — these are structurally distinct memories that survive consolidation, not one monolithic blob. The sub-line carries the mechanic: one→many→one is the council shape ("every model you use" because Trinity isn't structurally locked at three — works whether you have Claude+Gemini today or Claude+GPT+Gemini+Cowork+Ollama tomorrow), and "knows you" is the lens-conditioned chairman.

Three load-bearing pains underneath, each with a direct Trinity answer:
1. You copy-paste prompts between chatbots → Trinity asks all three at once
2. Each chatbot only knows its slice of your thinking → `dream` synthesizes your prompts into core memories
3. Each chatbot over-engineers (or hand-waves) the same problem differently → the lens learns your COMPRESSION rejections; the routing table de-weights over-engineers in your categories

v1 SHIPS: councils + chairman synth + `dream` cold-start + cortex extraction + lens building. What's NOT in the v1 headline: agent loops (v1.5/v1.6), taste marketplaces (future). "Own your memories" (the old standalone tagline) and "Forge your memory" (the council's round-3 wording, made without knowing `dream` is the feature name) are retired — the live tagline has Dream as the active verb because that's literally what the system does offline.

**Status (2026-05-12):** v1.0 locked for May 13–15 ship — see [`docs/spec-v1.md`](docs/spec-v1.md). Brand axis: **prompts** (yours) → **dream** (verb) → **core memories** (synthesized). Hero: *"Stop copy-pasting prompts. Own your context. Dream your core memories."* Sub: *"One question. Every model you use. One answer that knows you."* Three pains: copy-paste / siloed thinking / over-engineering — answered by ask-three / dream-synthesizes / lens-routes-around-weakness. Folder schema locked at `SCHEMA_VERSION = 1`. 8-surface browser smoke gate passing (`python scripts/browser_smoke.py`). 571 tests passing. **v1.5 cortex Weeks 1–5 shipped end-to-end** (see [`CHANGELOG.md`](CHANGELOG.md) 2026-05-12 entry for the full list): 9 MCP tools (canonical 6 + `ask` + `get_picks` + `mark_pick_wrong`); cortex consolidation with **structured geometric prior** (geometric median centroid via Weiszfeld iteration, 6-component `trust_score` with the 6th being mean-cosine-to-median coherence, manifold-dim + bimodality flag fed to the extraction prompt so the flagship does rule-extraction-on-structure not geometry-in-language); **chairman-audit-mode** (`consolidate --audit` runs an independent second flagship to catch drift; loud-fails on stderr); **override mechanism** (CLI `cortex-override` + MCP `mark_pick_wrong`; halves effective trust per click; persists across consolidations); **sigmoid-blended chairman picker** (smooth cold-start→personalization, no hard cut at n=1); **user-verdict-weighted personal routing table** (record_outcome signal flows into aggregation at 0.7 weight); **tool-triggered incremental ingest** (`ask`/`search_prompts` scan new transcripts within 1s, no manual seed re-run); **HF Hub offline default** (`main()` pins `HF_HUB_OFFLINE=1` so Trinity never makes outbound Hub calls at runtime); launchpad surfaces: personalization-% column, Health column (audit / bimodal / override badges with hover-titles), evidence-chip links to source councils. `cortex.py` split: math helpers extracted to `cortex_geometry.py` (304 LOC, dependency-free). Loop Constitution substrate removed pre-launch (was 1,396 lines of v2-trajectory code; the mechanic will be rebuilt leaner inside v1.6's `plan_and_execute`). **Next trajectory = v1.5** (target ship June 3, 2026): the MCP-primary two-tier tool surface is feature-complete; remaining work is calibration data + the v1.6 follow-ons noted in [`docs/spec-v1.5.md`](docs/spec-v1.5.md) "Open questions" (Ollama-vs-MLX preference, cortex-vs-lens cross-check). The Sakana TRINITY paper (arXiv:2512.04388) validates the architectural trajectory but their 3B vs 7B ablation shows the value is in prompt-engineering quality not routing decision — so v1.5 uses a flagship model with cortex context instead of a trained 7B. The trained-coordinator path in [`docs/spec-v2.md`](docs/spec-v2.md) is **sunset** as of 2026-05-11; reopens only if v1.5 hits a quality ceiling on real user data.

**The wedge is structural, not technical.** The three labs are commercially prevented from helping you use a competitor. Someone outside the labs has to ship the layer above them. That's the only sentence the marketing site has to land.

**The moat is the ledger.** Every council emits structured Routing JSON to `~/.trinity/council_outcomes/<id>.json` — `agreed_claims`, `disagreed_claims` with `why_matters`, `winner`, `provider_scores`, `routing_lesson`. Every user click feeds `record_outcome` → `~/.trinity/council_feedback.jsonl` + `outcome.metadata.user_verdict`. Frontier providers can't see the cross-model preference signal; Trinity persists it locally. The personal routing table is computed on-demand from the outcomes directory (no separate state file). Trinity rides on subsidized consumer subscriptions and never pays per call. v1 is free forever; revenue model deferred (see `docs/spec-v2.md` for held hosted-capability description, no pricing committed).

## Architectural commitments (load-bearing, not negotiable)

1. **No LLM calls outside councils.** Ingest, embedding, theme assignment, search ranking, clustering — pure embeddings + heuristics + metadata. The only LLM invocations Trinity makes are council member calls and chairman synthesis calls, both riding user subscriptions.
2. **Prompt content never uploads.** Even with v1.1 aggregation enabled, only categorical routing labels (`task_type`, `provider_scores`, `winner`) leave the machine. Anonymous, opt-in only.
3. **Local-first inference.** Phase 9's learned router runs on the user's hardware. No hosted controller. No per-call API billing.
4. **Subsidized consumer credits as cost basis.** Trinity dispatches via the user's own CLI subscriptions (Claude Code, Codex, Gemini CLI, Cowork). If anyone proposes a hosted API tier, push back hard — that destroys both cost basis and privacy.
5. **HF Hub offline by default.** `main()` pins `HF_HUB_OFFLINE=1` + `TRANSFORMERS_OFFLINE=1` via `setdefault` at startup. The embedding model is pulled once via an explicit `huggingface-cli download nomic-ai/nomic-embed-text-v1.5`; after that Trinity loads from `~/.cache/huggingface/hub/` and never contacts the Hub during normal operation. Privacy + reliability invariant — no surprise outbound calls from the running system, no telemetry to upstream model hosts, MCP child processes inherit the env so the guarantee propagates through every spawn.

## Glossary (load-bearing terms)

A few words do specific work; they get conflated otherwise:

- **prompts** — what the user owns (raw, indexed in `~/.trinity/memory/` for now; will move to `~/.trinity/prompts/` per Tier 1 #1). Inputs to dream.
- **dream** — the verb only Trinity has. Reads prompts, emits core memories (offline, your data).
- **core memories** — the five durable memory types dream creates (plural):

  | memory | what's in it | brain analog |
  |---|---|---|
  | `lens.md` | tensions you'd reject vs accept | value memory |
  | `picks.json` | your model picks per topic, with reasoning | procedural memory |
  | `routing.json` | per-category provider track record (numbers) | empirical memory |
  | `topics.json` | clusters of subjects you ask about | semantic memory |
  | `vocabulary.md` | how you use specific words | language memory |

  All five live in `~/.trinity/memories/`.

- **core** — the singular distillation. `~/.trinity/core.md` is one paragraph that subsumes the five memories above — chairman reads it FIRST on every council, falls through to specific memory files only when it needs depth.
- **council** — multi-model deliberation (parallel or chain) ending in chairman synthesis.
- **chairman** — the synthesis model in a single council. Reads `core.md`, emits structured Routing JSON. Per-call role.
- **Conductor** (v1.5+) — flagship model that *picks which model gets which sub-task* across a session/plan. Different role than chairman; same model family may play both.
- **harness** — the CLI/IDE the user is working inside (Claude Code, Codex CLI, Gemini CLI, Cowork). Trinity registers as an MCP server inside each.
- **seat / member** — a provider acting as one voice in a council. Code uses `members=[...]`; marketing copy will use `seat` (table metaphor).
- **task_type** — the short label for "what kind of question this is" (heuristic on input, also emitted by chairman). NOT the same as `category` (coarser LMArena-aligned grouping).

The map mirrors the tagline: prompts (what you own) → dream (the verb) → core memories (what dream creates, plural) → core (the distillation, singular). When in doubt about a name, look at the brain analog and pick the one that matches what the file actually stores.

## Calling the council from inside Claude Code

Trinity is exposed as an MCP server. v1.0 ships 6 canonical tools (`route`, `run_council`, `record_outcome`, `search_prompts`, `get_persona`, `get_council_status`); v1.5 adds `ask` (cheap default single-call routing), `get_picks` (agent-facing introspection into extracted picks), and `mark_pick_wrong` (user-veto on a pick — halves effective trust per click, persists across consolidations) — 9 total. `run_council(responses=[...])` covers what `judge` used to do — pre-supplied member outputs go straight to chairman synthesis, one model call instead of N+1. When working in this repo, **call `mcp__trinity-local__run_council` for hard questions** and `mcp__trinity-local__ask` for quick single-call consults. The chairman reads `~/.trinity/memories/lens.md` and condenses members through *this user's* taste — that's what makes the council more useful than just asking Claude alone.

Bar for "hard":
- Two senior engineers could reasonably disagree (architecture, API shape, refactor scope, naming, abstraction-vs-duplication)
- I catch myself answering "depends on…" or "you could go either way"
- The decision compounds (data schema, public surface, anything user-visible)
- The user has previously pushed back on my first answer in this area

Skip the council for: trivial bugs, syntax/API lookups, mechanical refactors, information retrieval. Each council costs 3 member calls + 1 chairman call — wasted on questions with one right answer.

After a council, treat the chairman's synthesis (especially `agreed_claims` / `disagreed_claims`) as the source of truth for what the answer should be, then explain it in my own words back to the user. Call `mcp__trinity-local__record_outcome` when the user picks a winner so the personal routing table improves over time.

## Install / surface notes

Run `trinity-local install-mcp` once to register Trinity's MCP server with Claude Code (`~/.claude.json`), Gemini CLI (`~/.gemini.json`), and Codex CLI (`~/.codex/config.toml`). Each harness spawns `trinity-local --mcp` as a stdio child when it starts; it lives until the harness exits. ~62MB resident while connected.

The launchpad → macOS Shortcuts → `~/.trinity/bin/trinity-dispatch` → CLI pipeline is independent of MCP — it's one-shot subprocess at every step, no persistent process required. So the launchpad keeps working even if MCP is disabled.

## MCP server hot-reload (development only)

When MCP is enabled and you're actively editing Trinity, set `TRINITY_MCP_WATCH=1` to enable a file watcher that calls `os._exit(0)` on any `.py` change. The MCP launcher auto-respawns with fresh code. Typical edit → reload cycle is <1s. Never enable in shipped configs.

**Caveat for tool-list changes**: Claude Code caches the tool list from the first connection. Adding *new* MCP tools (vs. modifying existing handlers) may still require a Claude Code restart to make them visible to the harness.

## Architecture (post v1)

### CLI dispatcher

Entry: `src/trinity_local/main.py` — thin dispatcher only. Command modules under `commands/` (22 modules):

| Module | Key commands |
|--------|-------------|
| `commands/ingest.py` | `features`, `examples` |
| `commands/tasks.py` | `task-create`, `task-show`, `task-sync`, `bundle-create`, `launch-create` |
| `commands/council.py` | `council-start`, `council-run`, `council-prompt`, `council-outcome`, `council-launch`, `council-rate`, `council-stop`, `council-share`, `council-iterate` (replaces former `auto-chain`; `--rounds N` for sequential refinement) |
| `commands/council_last.py` | `council-last` (rerun the most recent council bundle against the current model lineup) |
| `commands/portal.py` | `portal-html`, `open-review`, `serve` (local HTTP server for launchpad — alternative to file://) |
| `commands/seed.py` | `seed-from-taste-terminal` |
| `commands/replay.py` | `replay-history` |
| `commands/me.py` | `me-build` (chairman-driven), `me-show` |
| `commands/me_card.py` | `me-card` (render a paired-tension lens as a 1200×630 PNG) |
| `commands/actions.py` | `action-list`, `action-suggest`, `action-council`, `action-notify`, `action-complete` |
| `commands/shortcuts.py` | `shortcut-url`, `shortcut-run`, `action-shortcut`, `shortcut-setup`, `shortcut-install` |
| `commands/watch.py` | `watch-once`, `watch-loop`, `ingest-recent` |
| `commands/review.py` | `review` |
| `commands/adapters.py` | `adapters` |
| `commands/status.py` | `status`, `scoreboard` |
| `commands/cache.py` | `cache-stats`, `cache-clear` |
| `commands/cortex.py` | `consolidate` (extract routing patterns; supports `--audit` for independent-chairman drift check), `cortex-override` (user-veto on a rule; halves effective trust per click; `--reset` clears) |
| `commands/doctor.py` | `doctor` (preflight: providers / MCP dep / writable Trinity home) |
| `commands/dream.py` | `dream` (the one-command cold-start: discover cross-provider pairs across ALL embedded transcripts → synthesize each as a virtual council → consolidate cortex → rebuild /me lenses; Anthropic's *Dreaming* on the user's own data) |
| `commands/bootstrap_pairs.py` | `bootstrap-pairs` (just phase 1+2 of `dream` exposed standalone — discover clusters + synthesize, no consolidate/me-build follow-up) |
| `commands/metric.py` | `metric rate-limit-saves`, `metric dispatch-summary` (read aggregated dispatch metrics from `~/.trinity/analytics/`) |
| `commands/research.py` | `replay`, `rank`, `hard`, `hardeval`, `analytics`, `embed` (off the live product path — research pipeline only) |
| `commands/install.py` | `install-mcp`, `install-hooks` |
| `commands/telemetry.py` | `telemetry-show`, `telemetry-enable`, `telemetry-disable`, `telemetry-reset-id`, `telemetry-endpoint`, `auto-chain-enable`, `auto-chain-disable`, `auto-open-enable` (post-council `open <review_path>` on macOS), `auto-open-disable` |

### Core layers

| Layer | Files | Purpose |
|-------|-------|---------|
| Config | `config.py`, `config.json` | Provider definitions, role/task preferences, `trinity_home()` |
| Providers | `providers.py` | Subprocess wrappers for CLI provider calls |
| Council runner | `council_runner.py` | Parallel + chain-mode multi-model execution |
| Council runtime | `council_runtime.py` | Bundle creation, chairman prompt rendering (with structured JSON contract), Routing JSON parsing, outcome construction |
| Council schema | `council_schema.py` | `PromptBundle`, `LaunchEvent`, `CouncilMemberResult`, `CouncilChainStep` (NEW), `CouncilRoutingLabel` (with `agreed_claims` / `disagreed_claims`), `CouncilOutcome` (with `mode` and `chain_steps`) |
| Council status | `council_status.py` | Live run-state, member streaming, chairman synthesis progress |
| Council review | `council_review.py` | Static HTML review pages, structured Routing label section, live page with streaming member responses |
| Memory | `memory/` package — `schemas.py`, `store.py`, `index.py`, `replay_value.py` | `PromptNode` (atom) + `TurnWindow` (local context) index with replay-value scoring + MMR diversification |
| Embeddings | `embeddings/` — `__init__.py`, `backend_mlx.py`, `backend_tfidf.py`, `cache.py` | `nomic-embed-text-v1.5` at **768d**, batched embed with cache-awareness, Nomic prefix preservation |
| Ingest | `ingest.py` | Parsers: `parse_claude_code_session`, `parse_codex_session`, `parse_gemini_cli_session`, `parse_cowork_session`, `parse_claude_ai_export`, `parse_chatgpt_export`, `parse_gemini_takeout_html`. `iter_prompt_turns(session)` yields clean user-facing turns (sidechain / API errors / synthetic stripped). Gemini Takeout cells are grouped into multi-turn sessions by 30-minute time-proximity (source_format_version "2") so prior-thread context is preserved across cells Google flattened. |
| Thread context | `thread_context.py` | Canonical `build_threaded_prompt()` formatter — prepends preceding-assistant excerpt to short turns ("continue.", "Let me restart.") so fresh models replay with context. Used by both autofill and replay-history. |
| Categories | `categories.py` | Trinity capability categories aligned with the LMArena leaderboard (Coding/Math/Creative Writing/Hard Prompts/Multi-Turn/Instruction Following/Overall). Single source for the task_type→category map and UI labels. |
| Model detection | `model_detector.py` | Probes each provider CLI for the strongest model it accepts. Driven by `data/model_candidates.json` (synced from artificialanalysis.ai). `trinity-local models-detect` writes winners to `~/.trinity/detected_models.json`; runtime prefers detected over config.json. |
| Ranker | `ranker/` — `base.py`, `fallback.py`, `heuristic.py`, `knn_ranker.py`, `chairman_picker.py` (NEW), `types.py` | Routing decisions + chairman auto-selection (personal table → global benchmarks → default order) |
| Council outcome | `council_feedback.py` | Append user verdicts; `record_council_outcome` (in `memory/store.py`) propagates to PromptNode |
| State paths | `state_paths.py` | Single source of truth for `~/.trinity/` paths |
| Runtime env | `runtime_env.py` | PATH-injection env builder + `run_with_runtime_env()` (both helpers live in one module — `subprocess_utils.py` was the original plan but the split didn't materialize) |
| Task kinds | `task_types.py` | Single `guess_task_type()` heuristic classifier (no LLM) |
| Refresh | `refresh.py` | `refresh_launchpad()` — single entry for portal regeneration |
| Dispatch | `dispatch_runner.py`, `dispatch_registry.py`, `shortcut_setup.py`, `shortcuts_integration.py` | macOS Shortcuts bridge + dispatch wrapper |
| MCP | `mcp_server.py` | v1.0 canonical 6 + v1.5 `ask` + `get_picks` + `mark_pick_wrong` (see below) |
| Portal | `portal_data.py`, `portal_template.py`, `portal_runtime.py`, `portal_install.py`, `portal_page.py` | Static HTML launchpad with autofill, personal routing table, council suggestions |
| Telemetry | `telemetry.py`, `notifications.py` | Opt-in telemetry settings (privacy-clean), system notifications |
| Adapters | `adapters.py` | Provider adapter detection + transcript counts |
| Research | `research/` package | Offline research pipeline (replay, hard mining, ranking eval) — not on the live product path |

### The six canonical MCP tools (`mcp_server.py`)

These are the only public surface. Lifecycle order:

1. **`route(task, harness, available_models, budget, latency)`** → `{mode, primary, challenger, confidence, reason, fallback}`. No model calls — heuristic + k-NN + chairman picker. Cheap, called before the harness picks a model.

2. **`run_council(task, members, mode, sequence, primary_provider, responses)`** → council launched asynchronously. `mode="parallel"` (default) runs members concurrently then chairman. `mode="chain"` runs sequence serially with each step seeing prior outputs. **When `responses=[...]` is provided** (pre-supplied member outputs), skips dispatch and runs chairman synthesis only — one model call instead of N+1, returns the structured Routing JSON inline. This subsumes the former `judge` tool.

3. **`record_outcome(council_run_id, user_winner, accepted, edited, tests_passed, cost_usd, latency_sec, answer_label)`** → closes the supervision loop. Updates `council_feedback`, `CouncilOutcome.metadata.user_verdict`, and the originating `PromptNode` via `memory.record_council_outcome`. **The most important tool** — without it Trinity is a switchboard.

4. **`search_prompts(query, top_k)`** → ranked replay candidates from the hierarchical memory index, scored by `replay_value_score`.

5. **`get_persona()`** → returns `~/.trinity/memories/lens.md`. The chairman already loads this internally, but exposing it lets *any* harness (Claude Code, Codex, Gemini CLI) pull the persona once at session start and tailor responses without an MCP round trip per call.

6. **`get_council_status(council_run_id)`** → in-protocol polling for async councils. Returns status (running/completed/failed/canceled), per-member progress, synthesis state, and outcome summary (winner, agreed/disagreed claims, routing_lesson) when complete. Required for harnesses without filesystem access; also the only way to detect a stuck member without watching `~/.trinity/portal_pages/status/`.

Internal helpers (`get_status`, `get_elo`, `get_recent_councils`, `watch_once`) remain importable for the launchpad but are NOT exposed via MCP.

### State layout

Live state under `~/.trinity/` (overridable via `TRINITY_HOME`):

```
~/.trinity/
├── tasks/                          # Durable task records
├── actions/                        # Pending action records
├── prompt_bundles/                 # Saved prompt bundles
├── council_outcomes/               # Council outcome JSON (with routing_label + chain_steps)
├── council_progress/               # Live council progress (JSON + JS) for polling
├── reviews/                        # Post-hoc review JSON
├── review_pages/                   # Static HTML review pages
├── portal_pages/launchpad.html     # The launchpad (always file://)
├── digest_pages/                   # Weekly digest HTML
├── task_sync/                      # Sync-safe task payloads
├── watcher/                        # Cursor files for watch-loop resume
├── shortcut_setup/                 # Shortcut installer recipe
├── settings/                       # Telemetry settings
├── bin/trinity-dispatch            # Shell-launcher dispatch wrapper
├── cache/embeddings.jsonl          # Persistent embedding cache (768d)
├── memory/
│   ├── prompt_nodes.jsonl          # PromptNode index (hierarchical memory tier 1)
│   ├── turn_windows.jsonl          # TurnWindow index (tier 2 — local context)
│   ├── cursors.json                # Per-source memory ingest cursors (consumed by tool-triggered `ingest_recent()`)
│   └── embeddings_matrix.npy       # numpy fast-path matrix (lazy)
├── analytics/
│   ├── routing_label_events.jsonl  # Chairman parse-success rate
│   ├── knn_advisory.jsonl          # k-NN advisory log
│   └── knn_advisory_report.json
├── research/
│   ├── hard_examples/              # Mined hard examples
│   └── replay_examples/
├── outcomes.jsonl                  # Per-session outcome records (drift)
├── scoreboard.json                 # Aggregate provider scores (Elo)
├── runs.jsonl                      # Individual run traces
├── council_runs.jsonl              # Council outcome log
└── launch_events.jsonl             # Launch/handoff events
```

## The closed loop (v1)

```
existing transcripts
    ↓ ingest.parse_*_export / iter_prompt_turns
clean PromptTurn[] (sidechain + api-error + system-injection stripped)
    ↓ embed_batch with search_document: prefix at 768d
PromptNode → TurnWindow (per-prompt + per-window context)
    ↓ memory.search_prompt_nodes (numpy matmul fast-path)
top-N replay candidates
    ↓ replay-history loop
council_runner.run_council per candidate (auto-picked chairman)
    ↓ chairman synthesis
structured Routing JSON (agreed_claims, disagreed_claims, provider_scores, routing_lesson)
    ↓ persisted in ~/.trinity/council_outcomes/{id}.json (the canonical store)
    ↓ compute_personal_routing_table() aggregates on demand by task_type
    ↓ chairman_picker → next council picks the right chairman
↑ better routing decisions feed back into the loop
```

Every council outputs one labeled training example for the eventual Phase 9 learned router. Removing any of `route`, `run_council`, `record_outcome`, `search_prompts` breaks a meaningful surface.

## Coding conventions

- **Python 3.10+**. `from __future__ import annotations` in every module for PEP 604 style.
- **Dataclasses everywhere**. No Pydantic, no attrs. Manual `to_dict()`.
- **No runtime dependencies** beyond `Pillow>=10`. `[mlx]` extras for `sentence-transformers`. `[test]` for pytest.
- **Stable IDs** via `stable_id()` (`utils.py`) — `sha1(prefix|parts...)[:16]`.
- **JSONL append logs** for analytics; JSON entity files for objects.
- **`to_dict()` filters None / empty strings / empty containers**.
- **`now_iso()`** — UTC ISO 8601 with `microsecond=0`.
- **`trinity_home()`** — `~/.trinity/` (or `$TRINITY_HOME`).
- **Graceful degradation** — features depending on `[mlx]` fall back silently.
- **Analytics never crash** — wrap in try/except, watcher must not fail because of observability code.

### CLI structure

- `main.py` is a thin dispatcher using `set_defaults(handler=...)`.
- Every subcommand prints JSON to stdout and returns.
- Config is only loaded for commands that need it.

## What's working (v1 ship)

1. **Memory index live.** `seed-from-taste-terminal` populates `~/.trinity/memory/` from claude_ai + chatgpt + gemini takeout exports. 768d nomic embeddings, batched. Numpy matmul fast-path brings 28k-vector search from ~3s to ~5ms.
2. **Personal routing table.** `replay-history --limit 20` re-evaluates top-N replay candidates against the current model lineup. Aggregation by `task_type` is computed on demand by `compute_personal_routing_table()` walking `~/.trinity/council_outcomes/*.json` (no separate state file — the council outcomes directory is canonical, can't drift from itself). Cached in-process by directory mtime.
3. **Chairman auto-selection.** `predict_strongest_chairman(task)` looks up personal table → global priors → default order. Manual `--primary-provider` always wins.
4. **Structured chairman output.** Every council emits Routing JSON with `agreed_claims`, `disagreed_claims` (with `why_matters`), `winner`, `runner_up`, `provider_scores`, `routing_lesson`, `eval_seed`. Parse-success tracked in `analytics/routing_label_events.jsonl`.
5. **Chain mode.** `run_council(mode="chain", sequence=[...])` runs sequential refinement; chain steps persisted on `CouncilOutcome.chain_steps`.
6. **MCP tool surface (v1.0 canonical 6 + v1.5 `ask` + `get_picks` + `mark_pick_wrong`).** v1.0: `route`, `run_council` (subsumes `judge` via `responses=[...]`), `record_outcome`, `search_prompts`, `get_persona`, `get_council_status`. v1.5 adds `ask` (cheap default single-call routing — the 90% case), `get_picks` (agent-facing introspection into extracted picks), and `mark_pick_wrong` (user-veto on a pick; halves effective trust per click) — 9 total. The five legacy tools (get_status/get_elo/get_recent_councils/watch_once/judge) are dropped from the public MCP surface.
7. **Streaming live council page.** Member responses render full markdown as soon as their status flips to `done`, while chairman is still synthesizing.
8. **Launchpad autofill** wired to `memory.search_prompt_nodes`. Reason chips and "Winner: ..." hints render on each suggestion.
9. **Personal routing table card** on the launchpad with empty-state CTA.
10. **`/me-build` is a 4-stage lens-discovery pipeline aligned with the taste-terminal spec (TASTE_WIKI_SCHEMA.md).** Lenses live at tension boundaries between value poles, not at cluster centers. Pipeline shape ratified by three councils: `council_70eaf228d7753074` (Option C — basins as verifier, not chairman input), `council_6892781d06ac3fa8` (Stage 0 turn-pair gaps as highest-leverage import from taste-terminal), `council_e7560934cb1f1d72` (Stage 0 = ONE batch chairman call gated by deterministic post-validators).
    - **Stage 1 — Topology (no LLM, ~5s)**: numpy k-means on PromptNode embeddings → ~20 named basins (id, size, top-3 TF-IDF terms, centroid). Used to *tag decisions* and to *post-filter pairs* — NOT as a chairman prompt input.
    - **Stage 0 — Turn-pair gap extraction (1 chairman call + deterministic validators)**: walks (assistant_text, user_next_turn) pairs, classifies each into one of the four taste-terminal implicit rejection signal types — REFRAME / COMPRESSION / REDIRECT / SHARPENING. Output: `~/.trinity/me/rejections.jsonl`. Validators (in `me/turn_pairs.py`) drop chairman-skim labels:
       - **COMPRESSION**: user_text word count must be ≤ model_text/10
       - **REDIRECT**: model_text must be structurally multi-part (numbered/bulleted/multi-sentence ≥3)
       - **SHARPENING**: user_text must share ≥2 keywords with model_text
       - **REFRAME**: substituted frame must persist into next user turn (else dropped). Lenient when no next-turn data.
    - **Stage 2 — Decision extraction (1 chairman call)**: emits `decisions.jsonl` with `{privileged, sacrificed, valence, basin, verbatim}` per decision-shaped utterance. Valence enum: `satisfaction | regret | unresolved | correction | cost` (per `council_c63fa273bdc2ed21`). Stage 0 rejections are mixed into the sampled corpus as additional high-signal source material.
    - **Stage 3 — Pair mining (1 chairman call)**: chairman proposes 6–12 pair candidates and applies the three tests as a JSON verifier — **tension** (decisions in both directions), **dual evidence** (regret/correction/cost on both poles), **failure-mode legibility** (named failure mode on each pole). Verdict per pair: `accepted | preserve_as_ordering | dropped`.
    - **Stage 4 — Basin post-filter (deterministic, no LLM)**: drops accepted pairs whose tension evidence sits in a single basin. This is what makes basin tags load-bearing — without the post-filter, the LLM can ignore them and the topology evidence is dead code.
    - Drift instrument (rolling cosine between `embed(me.md)` and weekly turns) was **rejected** as topic-shift-not-value-shift metaphor.
    - Output: pairs → `~/.trinity/me/lenses.json` (4–8 expected, ≤7 per spec), preserved-as-orderings → `me/orderings.json`, rejections → `me/rejections.jsonl`, basins → `me/basins.json`. Rendered to `~/.trinity/memories/lens.md` for chairman context loading.
    - 3 model calls per rebuild (Stage 0 + Stage 2 + Stage 3), all on user subscriptions.
11. **Embedding-free product surface.** Launchpad autofill, MCP `search_prompts`, and `replay-history` candidate selection use pure heuristics (substring + recency + replay-value). No nomic model load on the hot path. `iter_prompt_nodes()` caps at the 5000 most-recent prompts (env var `TRINITY_PROMPT_NODE_LIMIT`) and is cached in-process by file mtime. Embeddings are written during seed and consumed only by `me-build`.
12. **Test suite: 289 passing.**

## What's deferred to v1.1+

- **§8.9 Aggregation endpoint** — Cloudflare Worker for live global priors + public leaderboard. Read access free for all; upload opt-in only with anonymous categorical labels (no prompt content). Ship after Routing JSON parse-success ≥85% sustained and ≥50 opt-in users.
- ~~**Tool-triggered cursor-based ingest**~~ — **shipped.** `incremental_ingest.ingest_recent()` walks transcripts newer than `~/.trinity/memory/cursors.json`, appends `PromptNode` records (no embedding — hot path stays embedding-free), persists the cursor atomically. MCP `ask` and `search_prompts` fire this at the start of each call with a 1s deadline so MCP-driven flows stay fresh without a manual `seed-from-taste-terminal` rerun. CLI: `trinity-local ingest-recent`. Errors swallowed so a parser breakage on one file can't take down the tool surface.
- **Auto-recommended chain mode** — `route()` doesn't auto-recommend `chain` until enough chain councils accumulate.
- **Local + global Elo blend** with sigmoid alpha over local council count (the `personal_routing_table` already replaces global as data accumulates; the explicit blend math is cosmetic for v1).
- **Live server-side autofill on keystroke** — needs a local HTTP endpoint.
- **Phase 9 learned tiny coordinator** — explicitly later. v1 collects the personal data; Phase 9 trains a per-user adapter against it.

## Loop Constitution substrate — removed; preserved in git history + spec

The double-loop substrate (`frame` / `run` / `verify_web`, formerly `src/trinity_local/loop/`)
was **removed from the codebase** as pre-launch simplification. The mechanic —
*execute → verify → cull → re-verify → commit* — will be rebuilt leaner inside
v1.5's `plan_and_execute` tool (ships in v1.6) driven by a flagship Conductor
with cortex context, not by a trained local skill-factory model.

The architectural reference + the ratifying council outcomes live in
[`docs/v2-loop-constitution.md`](docs/v2-loop-constitution.md). Git history
preserves the prior implementation if v1.6 wants to study it.

## Verified status

- `pytest -q` — **576 passed**.
- `trinity-local --mcp` exposes 9 tools: the v1.0 canonical 6 (`route`, `run_council`, `record_outcome`, `search_prompts`, `get_persona`, `get_council_status`) + v1.5 `ask` (cheap single-call routing) + v1.5 `get_picks` (agent-facing introspection into extracted picks) + v1.5 `mark_pick_wrong` (user-veto on a pick; halves effective trust per click).
- `trinity-local seed-from-taste-terminal --limit 10` runs end-to-end on real exports.
- `trinity-local replay-history --dry-run` lists ranked candidates with reason chips.
- `trinity-local portal-html` renders the launchpad with autofill chips, personal routing table card (or empty-state CTA), and global benchmarks.
- Live council page streams full member responses while chairman is synthesizing.
- Chairman prompt emits valid Routing JSON with `agreed_claims` / `disagreed_claims`.
- Chairman auto-selection: personal routing table → global benchmarks → default order.
- HTML well-formed (no orphan refs to peer_review / aggregate_ranking / daemon / workflow_create / task_linking).

## Development notes

- Run tests: `.venv/bin/python -m pytest tests/ -v`
- Or with isolated state: `TRINITY_HOME=/tmp/trinity-test PYTHONPATH=src python3 -m pytest -q`
- Embeddings require `pip install -e '.[mlx]'`. Without it, all embedding features fall back to TF-IDF.
- The agent's source of truth is this file (`claude.md`). The codebase plus `docs/scale-plan.md` and `docs/product-spec.md` round out the picture.
- `AGENTS.md` is a thin redirect to here so Codex / other agent harnesses don't drift.
