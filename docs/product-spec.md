# Trinity Local — Product Spec & GTM Strategy

> **Trajectory note (2026-05-11):** v1.0 ships May 13–15 with the council-centric
> mechanic + Routing JSON ledger described below. **v1.5 ships June 3, 2026** with
> the MCP-primary routing surface (`ask` cheap default + `compare` for hard
> questions) + hippocampus + cortex two-tier memory + local model dispatch + rate-
> limit dodge. Active next-spec: [`spec-v1.5.md`](spec-v1.5.md). Trained-coordinator
> v2 is **sunset** — see sunset header in [`spec-v2.md`](spec-v2.md).

## The One-Liner

> *v1.0 (ships May 13–15):* *"Trinity asks all your AIs at once, tells you when they agree, and remembers which one you actually trusted."*
>
> *v1.5 (ships June 3):* *"Trinity is what Claude Code reaches for when it needs a different provider, a fresh perspective, or a way to dodge a rate limit. Learns at two levels — specific past decisions (hippocampus) and extracted patterns across them (cortex). Gets sharper, not slower, with use."*

Trinity is a **routing substrate** — the layer underneath every AI harness that decides which model to call, runs a verifier-shaped council when uncertainty about model choice is itself the problem, and learns the user's taste from the picks they actually make.

**The wedge is trust calibration, not cost optimization.** Cost savings become a real claim in v1.5 once local model dispatch (Ollama + MLX) lands. The consumer-visible primitive is *"these models agreed on these claims, disagreed on these, here's why the disagreement matters."*

**Product hierarchy** (consumer pitch order):

1. **Trust layer** (the value) — *"models agreed on X, disagreed on Y, here's why."*
2. **Verifier** (the engine) — chairman synthesis emitting structured Routing JSON.
3. **Personal preference graph** (the moat) — every rated council outcome aggregates on demand into a `task_type → strongest provider` table. No durable state file; the council outcomes directory IS canonical.
4. **Router** (the implementation) — `route()` / chain mode / cost optimization.
5. **Closed loop with state and replay** — the v2 product: agents that don't drift over long horizons because Trinity retains state and can replay failures.

The router is the implementation. The verifier is the value. The personal preference graph is the moat. The closed loop with state and replay is the product that doesn't exist yet.

**Reading list (research context, not current shipped identity):** RouteLLM (router baseline), LLM-Blender (generator-verifier asymmetry), Conductor / Fugu (recursive self-orchestration), Sakana TRINITY (tiny coordinator over frontier models). These are the research patterns Trinity Local's *evidence ledger* generates supervision signal for — when a learned controller is eventually trained against the ledger (Phase 9 future work; not in this repo), the ledger is the right shape to feed it. **Today's repo ships the ledger and the synthesizer, not the controller.**

---

## Architectural Philosophy

### Load-bearing commitments (non-negotiable)

1. **No LLM calls outside councils.** Ingest, embedding, theme assignment, search ranking, and clustering use pure heuristics + metadata. The only LLM invocations Trinity makes are council member calls and chairman synthesis — both ride the user's existing CLI subscriptions.
2. **Prompt content never uploads.** Even with future opt-in aggregation, only categorical routing labels (`task_type`, `provider_scores`, `winner`) leave the machine. `/me` content is treated as sensitive derived prompt content; it stays local by default.
3. **Local-first inference.** Phase 9's learned router runs on the user's hardware. No hosted controller, no per-call API billing.
4. **Subsidized consumer credits as cost basis.** Trinity dispatches via the user's CLI subscriptions (Claude Code, Codex CLI, Gemini CLI, Cowork). If anyone proposes a hosted API tier, push back hard — that destroys both the cost basis and the privacy commitment.
5. **Hosted components may only be registries, not controllers.** Trinity may host public registry metadata, public cold-start priors, and curated public/famous persona documents. It must not host ordinary users' private `/me.md`, raw prompts, transcript derivatives, per-call inference, or a routing controller.

### What runs and when

- **MCP server** (`trinity-local --mcp`): a stdio child of whatever harness launched it (Claude Code, Codex, Gemini CLI). Lives only while the harness is connected; dies on EOF. ~62MB resident, no embedding model loaded eagerly.
- **CLI** (`trinity-local <command>`): one-shot subprocess. No persistent state.
- **Council launches**: spawned as background subprocesses by `council-launch`. They run member providers in parallel, write outcomes to `~/.trinity/council_outcomes/`, and exit.
- **`/me-build`**: cron-friendly. Runs once on demand or on a schedule (typical: daily). Loads the nomic embedding model (~22s ramp), samples ~80 diverse prompts via embedding-MMR, fires one chairman call, writes `~/.trinity/me.md`. The only place embeddings are loaded on the product path.

The launchpad and search/autofill paths are **embedding-free** (substring + recency + replay-value heuristics). Cold-start is <300ms; warm queries are <200ms across 5000 cached PromptNodes.

### Only surface what a single provider cannot

A single CLI already tells you what it thinks. Trinity's value is the **delta**:

- Provider A gave a different answer than Provider B (council `agreed_claims` / `disagreed_claims`)
- You keep switching from A to B for this type of task (personal routing table)
- You've done this exact workflow N times across N tools — it should be automated
- Provider B would have been faster and cheaper for this task kind (latency-aware routing)
- This task kind looks different in your taste than in the population (chairman reads `/me`)

If a single CLI can already surface the information, Trinity should not duplicate it.

---

## What Trinity Uniquely Solves

These are problems that **require multi-provider observation** and cannot be solved by any individual CLI, no matter how good it gets:

### 1. Personalized Trust Calibration Through Council

> "These models agreed on these claims, disagreed on these, here's why the
> disagreement matters — and which answer fits *you*."

When a task matters, you want more than one opinion. Trinity runs the same prompt through multiple providers and a chairman synthesizes a verifier-shaped Routing JSON: structured `agreed_claims`, `disagreed_claims` (with `why_matters`), `winner`, `runner_up`, `routing_lesson`, and `user_likely_values` derived from your `/me` profile.

The chairman is loaded with `~/.trinity/me.md`, so it doesn't pick the universally best answer — it picks the answer that fits *this* user. Members generate broad; chairman condenses through your taste.

Each council run produces `(prompt, response_A, response_B, response_C, chairman_synthesis, routing_label, your_verdict)`. The Routing JSON is the supervision signal that feeds the personal routing table and, eventually, the Phase 9 learned controller.

**No single provider can do this.** Each provider only sees its own output. Only your `/me` + your verdicts know which answers actually match your taste.

### 2. Personal Routing Table (the moat)

> "For your code-refactor prompts, codex wins 7.8/10. For research synthesis, claude wins 8.1. For real-estate prompts, you've overridden the chairman 4 of the last 6 times — your routing differs from the chairman's."

`replay-history` re-evaluates top-N replay candidates against the current model lineup. Aggregation by `task_type` is computed on demand by walking `~/.trinity/council_outcomes/*.json` — no separate state file, can't drift. The launchpad surfaces the table; `chairman_picker` reads it before every council. Manual `--primary-provider` overrides everything.

**No frontier provider can replicate this** because none of them see the cross-model preference data.

### 3. Behavioral Routing Intelligence

> "You tried this in Claude and switched to Codex. That's the 4th time."

Trinity watches transcript histories across all tools. When it detects a pattern — repeated switches, abandoned sessions, tasks that always end up in a particular provider — it learns which tool is actually best for each task shape.

**No single provider tracks your cross-tool behavior.**

### 4. Latency-Aware Routing

> "GPT-5.5 xhigh wins on quality but takes 30+ seconds. Claude Opus 4.7 is 90% as good in 3 seconds for this task. You said you wanted fast."

External benchmarks (artificialanalysis.ai's Intelligence/Coding/Agentic indices) capture quality but ignore latency. Trinity records per-provider latency and routes against your `(budget, latency)` constraints — the most underrated lever once gpt-5.5 xhigh becomes the default-quality winner.

**No single provider benchmarks itself against competitors on your hardware.**

### 5. Persona-Conditioned Synthesis

> "Two senior engineers could reasonably disagree about this — and you've already made similar architectural choices three times. Here's what fits you."

The chairman reads `/me` (composed by `me-build` from sampled diverse prompts) and conditions every synthesis on your demonstrated taste, vocabulary, implicit rejections, and abstract lenses. The persona is built locally, never uploads.

---

## Architecture Today

### CLI dispatcher

`src/trinity_local/main.py` is a thin dispatcher. Command modules live under `commands/`:

| Module | Key commands |
|--------|-------------|
| `commands/council.py` | `council-launch`, `council-rate`, `council-stop`, `council-share`, `council-html` |
| `commands/me.py` | `me-build` (chairman-driven), `me-show` |
| `commands/seed.py` | `seed-from-taste-terminal` (ingest from claude_ai/chatgpt/gemini takeout exports) |
| `commands/replay.py` | `replay-history` |
| `commands/portal.py` | `portal-html` (regenerates the launchpad) |
| `commands/install.py` | `install-mcp`, `install-hooks` |

### MCP — v1.0 canonical 6 + v1.5 `ask` + `get_cortex_rules` + `mark_cortex_rule_wrong`

`src/trinity_local/mcp_server.py` exposes these tools to any MCP-compatible harness (Claude Code, Codex CLI, Gemini CLI). v1.0 ships 6; v1.5 adds three — `ask` for cheap single-call routing, `get_cortex_rules` for agent-facing introspection, `mark_cortex_rule_wrong` for the harness-callable user veto — for 9 total:

1. **`ask(query, available_providers?, thread_id?, top_k?)`** *(v1.5)* — kNN + cortex match → single dispatched call → concise structured return `{answer, routed_to, trust_score, latency_ms, escalate_hint?}`. The 90%-of-consults tool. Returns `escalate_hint=compare` when trust < 0.55 so the calling agent can choose to fan out instead.
2. **`route(task, ...)`** — heuristic + k-NN; returns `{mode, primary, challenger, confidence, reason, shape_signals}`. No model calls. Deprecated in v1.5 in favor of `ask` for in-harness use (the calling agent can't shell out to dispatch via `route`'s advice alone); kept for backwards compatibility.
3. **`run_council(task, members, mode, sequence, primary_provider, responses)`** — spawns a council; runs members in parallel (or chain) then chairman. **When `responses=[...]` is provided**, skips dispatch and runs chairman synthesis only — the verifier-shaped verdict path. Subsumes the former `judge` tool.
4. **`record_outcome(council_run_id, user_winner, accepted, ...)`** — closes the supervision loop. Updates `CouncilOutcome.metadata.user_verdict` and the originating `PromptNode`.
5. **`search_prompts(query, top_k)`** — heuristic search (substring + recency + replay-value); no embedding load.
6. **`get_persona()`** — returns `~/.trinity/me.md`.
7. **`get_council_status(council_run_id)`** — in-protocol polling for async councils.
8. **`get_cortex_rules(basin_id?, min_trust?)`** *(v1.5)* — returns extracted routing patterns per basin (winner distribution, trust score, failure modes, evidence). Lets a calling agent reason about *why* `ask` would route a given basin to a given provider — the cortex made visible.
9. **`mark_cortex_rule_wrong(basin_id, reason?, reset?)`** *(v1.5)* — user-veto on a cortex routing rule. Each call increments `override_count`; `effective_trust = raw_trust × 0.5^count`. Two clicks quarter trust; three drops most rules out of routing entirely. Persists across consolidations — a fresh extraction can't erase the user's signal. Use `reset=true` to clear the count.

### State layout

```
~/.trinity/
├── tasks/                          # Durable task records
├── council_outcomes/               # Council outcome JSON (verifier-shaped routing_label + chain_steps) — CANONICAL store
├── council_progress/               # Live council progress (JSON + JS) for polling
├── reviews/                        # Post-hoc review JSON
├── review_pages/                   # Static HTML review pages
├── portal_pages/launchpad.html     # The launchpad (always file://)
├── settings/                       # Telemetry settings
├── bin/trinity-dispatch            # Shell-launcher dispatch wrapper
├── memory/
│   ├── prompt_nodes.jsonl          # PromptNode index (atomic retrieval unit)
│   ├── turn_windows.jsonl          # TurnWindow index (local context)
│   └── cursors.json                # Per-source ingest cursors
├── me.md                           # Built by `me-build` via chairman call
├── analytics/
│   └── routing_label_events.jsonl  # Chairman parse-success rate
├── outcomes.jsonl                  # Per-session outcome records (drift)
└── council_runs.jsonl              # Council outcome log
```

The **personal routing table is computed on demand** from `council_outcomes/*.json` — no separate state file. Cached in-process by directory mtime.

### What was deliberately deleted from earlier specs

Each was on a previous version of this spec; each was cut to keep the surface honest:

- **Peer review (anonymous member-on-member ranking)** — replaced by chairman Routing JSON. Doubled latency for empty-equivalent data.
- **TranscriptNode tier** — its only call site was the search re-ranker; PromptNode + TurnWindow already covered the same retrieval surface.
- **`personal_routing_table.json` durable state** — computed on demand from `council_outcomes/`.
- **`global_benchmarks.py` separate path** — *deferred*. Today still a separate file; Tier 2 plan merges into one read-time blend.
- **`prompt_shape.py` standalone module** — folded into `ranker/heuristic.py` (`prompt_calls_for_council` lives there now).
- **`judge` MCP tool** — collapsed into `run_council(responses=[...])`. One fewer public surface.
- **Embedding-powered search on the hot path** — replaced with substring + recency + replay-value heuristics. Search cold-start dropped from 22s to ~300ms.
- **Daemon / always-resident server** — the MCP server is a stdio child of whatever harness launched it; dies on EOF. No background process, no launchd, no systemd.
- **`run` command** (Thinker/Worker/Verifier loop) — replaced by council; the user's CLI is the agent loop.
- **Cost aggregation per provider** — subsidized subscriptions = roughly fixed per-task cost; latency is the actual scarce resource.
- **`~/.taste/` dependency** — `me-build` now builds /me from sampled PromptNodes via a chairman call. taste-terminal is no longer a runtime dependency.

---

## What Trinity Is NOT

- **Not a CLI wrapper.** Trinity does not replace `claude`, `gemini`, or `codex`. It does not own the terminal session.
- **Not an orchestrator.** The council is a one-shot multi-provider comparison; chain mode is sequential refinement of one task. Long-horizon orchestration belongs to the harness's agent loop.
- **Not a server.** No `localhost:8080`. No WebSocket. No database. The MCP stdio server is a child process of the harness, not an independent service.
- **Not an always-on daemon.** Nothing runs when no harness is connected.
- **Not a hosted /me warehouse.** The opt-in registry will store metadata + curated public personas only — never private `/me.md`.

---

## What's working today (v1.1)

1. **Memory index live.** `seed-from-taste-terminal` populates `~/.trinity/memory/` from claude_ai + chatgpt + gemini takeout exports. 768d nomic embeddings written at ingest, used by `me-build` only.
2. **Embedding-free hot path.** Launchpad autofill, MCP `search_prompts`, `replay-history`. Substring + recency + replay-value heuristics. ~150ms warm query over 5000 cached recent PromptNodes.
3. **Personal routing table (on-demand).** Computed by walking `council_outcomes/*.json`, mtime-cached. Read by chairman_picker + launchpad.
4. **Chairman auto-selection.** `predict_strongest_chairman(task)` consults personal table → global priors → default order.
5. **Verifier-shaped chairman output.** Every council emits Routing JSON with `agreed_claims`, `disagreed_claims` (with `why_matters`), `winner`, `runner_up`, `provider_scores`, `routing_lesson`, `eval_seed`.
6. **Chain mode.** `run_council(mode="chain", sequence=[...])` runs sequential refinement; chain steps persisted on `CouncilOutcome.chain_steps`.
7. **MCP tool surface (v1.0 canonical 6 + v1.5 `ask` + `get_cortex_rules` + `mark_cortex_rule_wrong`).** v1.0: `route`, `run_council` (subsumes `judge`), `record_outcome`, `search_prompts`, `get_persona`, `get_council_status`. v1.5: `ask` (cheap single-call default), `get_cortex_rules` (agent-facing introspection), and `mark_cortex_rule_wrong` (harness-callable user veto). 9 total.
8. **`/me-build` IS a council.** Embedding-MMR sampling picks ~80 quality-weighted diverse prompts; chairman synthesizes 5-section `/me.md` (recurring topics, vocabulary, implicit rejections, cross-domain analogies, abstract lenses).
9. **Streaming live council page.** Member responses render full markdown as soon as their status flips to `done`, while chairman is still synthesizing.
10. **v1.5 cortex layer (Week 2 shipped, refined post-launch).** `trinity-local consolidate` extracts routing patterns per basin (chairman-classified `task_type`) via flagship call → writes `~/.trinity/cortex/routing_patterns.json`. Each pattern carries a **structured geometric prior** of the basin: geometric median (Weiszfeld iteration, robust under L1), coherence score, manifold dim, bimodality flag (excess kurtosis on first-PC, requires N≥10), and typicality-ordered outcomes. The flagship extraction prompt is *prepended* with a one-paragraph shape description so the LLM does rule-extraction on structure instead of geometry-in-language. `trust_score` has 5 components (n_episodes / consistency / recency / diversity / coherence; weighted geometric mean) — coherence catches "confident rule on noisy basin." Wires into `ask` query hot-path in Week 3 after human calibration gate.
11. **Test suite: 541 passing.** Cortex consolidation (geometric median + coherence + bimodality + bimodal cortex fall-through + chairman-audit-mode); cortex math factored into `cortex_geometry.py` (dependency-free stdlib). `ask` orchestration + MCP handler, tool-triggered incremental ingest, HF offline pinning, user-verdict-weighted personal routing table, sigmoid-blended chairman picker (cold start → personalization), launchpad personalization-% + Health columns. Plus the v1.0 base. 8-surface browser smoke gate green.

---

## What's deferred to v1.2+

- **Tier 2 #7 — merge global_benchmarks + personal table into one read-time blend.** Currently two launchpad cards; collapse to one with sigmoid-alpha confidence as personal `n` grows.
- **Aggregation endpoint (§8.9).** Cloudflare Worker for live global priors + public leaderboard. Read access free for all; upload opt-in only with anonymous categorical labels (no prompt content). Ship after Routing JSON parse-success ≥85% sustained and ≥50 opt-in users.
- **Profile-DB / shared personas (v1.2).** Architecture D from `council_ab29d9e1fbd0ed50` — opt-in registry of metadata + curated famous-person personas built from public sources. **Never** hosts ordinary user `/me.md`.
- **Harness auto-invocation.** `route()` returns `should_auto_council: bool` based on 5 trigger conditions (irreversible state, multi-architecture choice, load-bearing commitment edits, low confidence, user-override history). Rate-limited at 1 per 10 user turns / 1 per 20 min.
- **Tool-triggered cursor-based incremental ingest.** Cursors live at `~/.trinity/memory/cursors.json`; fires on MCP tool invocation rather than the existing one-off `seed-from-taste-terminal`.
- **Phase 9 learned tiny coordinator.** v1 collects the personal data; Phase 9 trains a per-user adapter against it.

---

## GTM Strategy

### Target user

**Power users who already use 2+ AI coding CLIs daily.** They:

- Have Claude Code, Codex CLI, and/or Gemini CLI installed
- Switch between tools based on gut feeling
- Don't have data on which tool is actually better for what
- Lose time re-trying tasks in a second tool when the first fails
- Can install a Python package and run a terminal command

### Positioning

> "Your AI tools don't talk to each other. Trinity watches all of them and tells you things none of them can."

### Launch — council-first

The blog post writes itself:

> "I ran 50 of my favorite prompts through 3 AI coding tools. The chairman synthesized verifier-shaped verdicts personalised to my `/me`. The rankings surprised me. Here's the data — run it on your own prompts."

Why this order:

1. **Council is generative.** It produces a new artifact (cross-provider verdict) that didn't exist before.
2. **Council extracts constitutional data.** Every run feeds Routing JSON into the local evidence ledger; the personal routing table aggregates on demand.
3. **Council is the proof.** Multi-provider chairman synthesis with verifier-shaped Routing JSON (agreed_claims / disagreed_claims with why_matters) already validates the multi-provider thesis.
4. **`/me` lenses are the shareable social object.** Pair-wise principles distilled from your prompt history (title + why-it-matters per implicit rejection); copyable to socials with one click. Verbatim prompts stay local — only the principle ships.

### Distribution

1. **GitHub repo** — `pip install -e .` from source.
2. **MCP-default install** — `trinity-local install-mcp` registers Trinity with Claude Code's MCP host. Codex CLI / Gemini CLI follow the same pattern.
3. **Word of mouth** — the multi-CLI power-user community is small and tight.
4. **Blog post** — "I spent a month tracking which AI coding tool is actually best for what. Here's the data."

### Telemetry model

Public benchmarking should use an **opt-in summary-sharing model**, not raw transcript upload:

- Consent during install (default off)
- Editable later from launchpad settings
- Categorical routing labels only (`task_type`, `provider_scores`, `winner`, `routing_lesson`)
- No raw prompts, outputs, file paths, or repo contents — ever

See [telemetry-spec.md](telemetry-spec.md) for the event schema and upload cadence.

---

## Simplicity principles

1. **One file = one entity.** Tasks, actions, bundles, and outcomes are each a single JSON file. No joins. No foreign keys. No schema migrations.
2. **Append-only logs for history.** JSONL files for runs, launches, and council outcomes. Never rewrite history.
3. **Static HTML for UI.** The launchpad is regenerated from file state. No React. No build step. No WebSocket. Open in any browser.
4. **Filesystem is the index.** Computed views (e.g., the personal routing table) walk canonical directories on demand and cache by mtime. No durable secondary state files for derived data.
5. **CLI for power users.** Every operation is a `trinity-local <subcommand>`. The launchpad has minimal in-page settings (telemetry sharing toggle, anonymous-id reset, ingest controls, auto-chain enable/disable) — no full configuration app.
6. **Minimal dependencies.** Python stdlib + numpy. Optional `[mlx]` extras for embedding writes during seed and embedding-MMR sampling during `me-build`.

---

## Roadmap

For the long-form Phase 0–9 plan (TRM-style learned coordinator, aggregation endpoint, Phase 9 training pipeline), see [`docs/scale-plan.md`](scale-plan.md). This file stays product-spec-shaped: positioning, GTM, what's in/out of v1.

The destination matches the convergence of Lottery Ticket → HRM → TRM → Sakana TRINITY: a small learned controller (~10K params) over frontier models, with a verifier head, that recursively refines via chain mode. The chairman + `/me` primitive Trinity ships today is the supervision-signal generator that feeds Phase 9; chairman synthesis is `/me`-conditioned, so the Phase 9 router learns `(task_text, /me_embedding) → routing_decision` rather than a generic mapping.

## Trinity and the broader pattern

This architecture is isomorphic to earlier work on spatial taste and pattern selection (Kintsugi / IPCo):

| Layer | Trinity (Coding Taste) | IPCo (Spatial Taste) |
|-------|------------------------|----------------------|
| **Observation** | Watcher scans transcripts | Usage telemetry of pattern books |
| **Pairwise judgment** | Council forces cross-provider comparison + `/me`-personalised chairman | Pattern book curator selection |
| **Constitution extraction** | k-NN learns routing from (prompt, response) pairs | SLM learns plan selection from (site, pattern) pairs |
| **Taste licensing** | `/score` endpoint judges code | Design system judges spatial instantiations |

The pattern: **give away the artifact (transcripts/patterns), license the constitution that learned to evaluate artifacts.** This is why Trinity stays free at the user surface. The moat is the taste function, not the router or the digest.
