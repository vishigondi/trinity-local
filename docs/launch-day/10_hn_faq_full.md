---
class: live
---

# Trinity Local — HN FAQ (launch tab, paste-ready)

Twenty anticipated HN questions, ordered by axis. Each answer is 50–100 words and cites the actual file paths, council outcomes, or test counts you can verify in the repo.

---

## Architecture

### How is the lens actually built?

Four stages, three LLM calls per rebuild (`src/trinity_local/me/`). Stage 1 is pure numpy k-means on PromptNode embeddings (~20 named basins, no LLM). Stage 0 walks (assistant, next-user-turn) pairs and classifies each into REFRAME / COMPRESSION / REDIRECT / SHARPENING via one batch chairman call gated by deterministic post-validators in `me/turn_pairs.py` (e.g. COMPRESSION requires user_text ≤ model_text/10). Stage 2 extracts decisions with valence labels. Stage 3 mines paired tensions; Stage 4 (deterministic) drops pairs whose evidence sits in a single basin. Output: `~/.trinity/memories/lens.md`. Pipeline shape ratified by council `70eaf228d7753074`.

### What is the chairman, exactly?

The chairman is whichever model synthesizes member outputs into a Routing JSON verdict (`council_runtime.py`). It reads `~/.trinity/core.md` first, then `lens.md` for tension context, then the member responses, and emits structured JSON: `winner`, `runner_up`, `confidence`, `agreed_claims`, `disagreed_claims` (each with `why_matters`), `provider_scores`, `routing_lesson`, `eval_seed`. The chairman is auto-selected per task via `chairman_picker.predict_strongest_chairman(task)` — personal routing table → global priors → default order. Manual `--primary-provider` always wins. Parse-success tracked in `analytics/routing_label_events.jsonl`.

### Why MCP instead of a wrapper CLI?

Three reasons. (1) Agents already inside Claude Code / Codex CLI / Antigravity / Cursor reach for tools the harness exposes — MCP is the dropdown. (2) The MCP server is a stdio child of the user's harness — no listening port, `lsof -i | grep LISTEN` shows nothing related to Trinity. (3) Council outcomes write straight to `~/.trinity/council_outcomes/<id>.json` with the chairman's pick as supervision signal — no rate-prompt interrupt needed (`record_outcome` was retired 2026-05-21 in favor of "the chairman pick IS the verdict"). `trinity-local install-mcp` writes `~/.claude.json`, `~/.gemini/settings.json`, `~/.codex/config.toml`, `~/.cursor/mcp.json`. <!-- canonical:mcp_tool_count -->8<!-- /canonical --> tools total (`mcp_server.py`).

### How does the personal routing table get computed?

`compute_personal_routing_table()` (`personal_routing.py`) walks `~/.trinity/council_outcomes/*.json` on demand and aggregates by `task_type`. No separate state file — the outcomes directory IS canonical, so it can't drift from itself. Cached in-process by directory mtime. Inputs per outcome: `chairman_winner` (the `routing_label.winner` the chairman picked) — counted as wins per provider per `task_type`. Best provider = max chairman wins; ties broken by mean overall. Output: per-`task_type` provider table (with `wins` count, `overall` mean, `n` sample count) plus `best_per_task_type` + `wins_per_task_type` for "picked X of Y" rendering. The personal table replaces global priors as data accumulates; the sigmoid-blended picker handles smooth cold-start → personalization without a hard cutover at n=1. (Pre-2026-05-21 the aggregation blended `user_verdict.user_winner` from the retired `record_outcome` MCP tool at 0.7 weight; that path is sunset — chairman pick is the entire supervision signal now.)

---

## Comparison

### How is this different from LangChain / LangGraph?

LangChain orchestrates within-provider state (chains, tools, memory) for *one* model at a time. Trinity sits *above* the model choice — the layer that decides which lab to ask for which kind of question, then dispatches via the CLIs you already pay for. README says it explicitly: *"Trinity doesn't replace LangGraph, CrewAI, Pinecone, DeepEval, or your existing eval pipeline."* The article framing is binary ("ditch your modular stack or stay locked in"); Trinity is the third answer — keep the modular stack, add a learning routing layer across it.

### How is this different from LiteLLM?

LiteLLM is a unified API gateway — same SDK shape, swap providers, pay-per-call. Trinity is the opposite cost model: rides your *existing consumer subscriptions* via subprocess CLIs (`claude`, `codex`, `agy` — the Antigravity CLI, slug `antigravity`), so the provider eats inference cost and Trinity never pays per token. LiteLLM has no preference corpus, no cross-provider memory, no chairman synthesis — it's a router primitive, not a learning layer. You could in principle layer Trinity over LiteLLM if you wanted hosted API access; we don't, by design (architectural commitment #4 in `claude.md`).

### How is this different from OpenRouter?

OpenRouter is hosted, per-call billed, and your prompts route through their servers — which means OpenRouter sees every prompt you send. Trinity is local-first: prompts and answers never leave your machine, MCP child is stdio, no listening port. OpenRouter optimizes for *cheapest route given quality floor*; Trinity optimizes for *which model wins YOUR kind of question* — the chairman picks through your lens (distilled from how you've rephrased, judged, and rejected past answers), and the personal routing table aggregates those picks per task type. Different wedge entirely. The comparison table in the README has the full matrix — privacy, cost basis, output shape, personalization.

### How is this different from Anthropic's Dreaming?

Same mechanic (learning from past sessions → consolidated routing patterns), different scope. Anthropic's Dreaming runs on Anthropic's hosted runtime over Anthropic-only sessions — Harvey reported 6× task-completion uplift, but it's structurally locked to one lab. Trinity runs `dream` locally over `~/.claude/` + `~/.codex/` + `~/.gemini/` — three SQLite caches across three labs, none of which can read each other. The Dreaming paper independently validates the architectural thesis; the cross-provider version of it has to come from outside the labs. See `commands/dream.py`.

---

## Privacy

### What actually leaves my machine?

Nothing by default. Prompts, answers, council outcomes, lens.md, picks, routing table — all stay in `~/.trinity/`. The MCP server is a stdio child of your harness (no listening port). `HF_HUB_OFFLINE=1` is pinned at `main()` startup so HuggingFace gets no outbound calls during normal operation. The embedding model is pulled exactly once via an explicit `huggingface-cli download nomic-ai/nomic-embed-text-v1.5` (~600 MB). Model dispatches go through your authenticated CLI subprocesses (`claude`, `codex`, `agy` — the Antigravity CLI, slug `antigravity`) — the provider sees the prompt because *you* asked them; Trinity adds no relay.

### What about the opt-in telemetry?

Default off. When enabled (`trinity-local telemetry-enable`), only categorical labels ship: `task_type`, `winner`, `confidence`, `harness`. Never prompt content, never member outputs, never lens contents. The intent is a future public leaderboard ("which model wins what kind of question, aggregated across opt-in users") — works fine without it. See `docs/telemetry-spec.md` and `src/trinity_local/telemetry.py`. Break this contract once and the brand dies; it's load-bearing, not aspirational. Endpoint is configurable, anonymous id can be reset (`telemetry-reset-id`).

### What's the GDPR posture?

Trinity processes no personal data on any server — there are no Trinity servers. `~/.trinity/` is on the user's machine, so the user is both the controller and the processor under GDPR Article 4. The opt-in telemetry, when enabled, ships only categorical labels (no content, no PII) with an anonymous reset-able id — which falls under recital 26 (anonymous data is out of scope). Deletion is `rm -rf ~/.trinity/` or `trinity-local uninstall --yes --include-data`. No retention contracts, no DPAs needed for v1.0 because there's no processing to delegate.

---

## Cost

### Is this really free forever?

Yes. v1.0 is MIT, no paid tier, no hosted controller. The cost model: Trinity dispatches via your existing CLI subscriptions (Claude Pro / ChatGPT Plus / Gemini Advanced / Codex), so the provider eats the inference cost — Trinity rides on subsidized consumer credits the labs are pricing below cost to grab default-assistant slot. Architectural commitment #4 in `claude.md` is explicit: *"If anyone proposes a hosted API tier, push back hard — that destroys both cost basis and privacy."* The wedge is structural; we can't charge for inference without breaking it.

### What's the business model, then?

**Trinity for Teams** (private beta) — same architecture, packaged for organizations that need data-residency / vendor-neutrality guarantees. The pitch is in the README: Claude Managed Agents runs memory + orchestration on Anthropic's hosted runtime, which is a non-starter for regulated industries; Trinity keeps everything in `~/.trinity/` on infrastructure the org owns, configurable inside a VPC. MassMutual / ProgressiveRobot have started naming "agent lock-in" as a procurement concern; Trinity is the architectural response. Waitlist: GitHub Discussions or `teams@keepwhatworks.com`. v1 ships with no pricing committed.

### What's the story if I only have one Pro subscription?

Trinity still works — councils degrade to whatever members you have authenticated. With one provider it's not a council, it's a chain-mode refinement loop against itself, and the chairman synthesis still emits Routing JSON over the rounds. The bigger value with one provider is the `lens-build` pipeline and the depth-score-ranked replay over your existing transcripts — the cross-provider continuity wedge (`handoff`) and the comparison benchmarks need two+ providers, but the corpus-grooming surface doesn't. `trinity-local status` tells you which CLIs are missing.

---

## Practical

### Windows / Linux support?

The Python core is platform-agnostic and runs on macOS + Linux today (CLI commands, MCP server, embeddings, lens-build all work). The cross-platform launchpad host is the **Chrome extension** — `install-extension` works on macOS, Linux, and Windows; Chrome's Native Messaging spawns `trinity-local-capture-host` on demand, same shape on all three OSes. The demo screencast was recorded on macOS but every step works identically on Linux through the same extension. (Earlier plans named `Trinity.app` / `install-app` as the macOS launchpad host and used a macOS Shortcut → `~/.trinity/bin/trinity-dispatch` dispatch path; both retired pre-launch in favor of the Chrome extension so non-coders on every OS get the same surface.)

### Single-user vs teams — what changes?

v1.0 is strictly single-user — `~/.trinity/` is one user's corpus, one user's lens, one user's routing table. There's no merge story, no shared council outcomes, no team-level aggregation in v1.0. Trinity for Teams (private beta) keeps the local-first invariant but adds VPC-deployable shared state and routing across team members' verdicts. The architectural commitment doesn't change — prompts still never leave the team's network boundary, and team-level aggregation still uses only categorical labels. Waitlist: GitHub Discussions thread "Interested in Teams".

### What about the Chrome extension — does it run a server?

No listening port, no daemon. The v1.6 extension uses Chrome's Native Messaging — same pattern 1Password / Bitwarden use. Chrome spawns `trinity-local-capture-host` on demand when the extension emits a message; the OS reaps the process when Chrome disconnects. `lsof -i | grep LISTEN` shows nothing related to Trinity. The capture host has no networking imports (AST-enforced by `test_capture_host_no_network.py`). `allowed_origins` in the Chrome manifest restricts the host to invocations from *the* Trinity extension only. Captures land in `~/.trinity/conversations/<provider>/<conv_id>.json`.

---

## Skeptical

### Why should I trust your eval numbers?

You don't have to — `eval-build` produces the suite from *your* `~/.trinity/me/rejections.jsonl`, not ours. The mechanic: Stage 0 mines (prompt, rejected_response, rejection_type) triples from your transcripts (REFRAME / COMPRESSION / REDIRECT / SHARPENING). `eval-run --target <provider>` dispatches each prompt and scores via judge against *your* `lens.md`. Output is "Model X scored 0.79 on YOUR 45-item rejection corpus" — and the *per-axis* breakdown reveals where each model actually struggles. Freshest run on Vishi's corpus (2026-05-23) — all three providers on the SAME N=45 suite: claude 0.79 aggregate (SHARPENING 0.82 / REFRAME 0.81 / REDIRECT 0.80 / COMPRESSION 0.48 n=2), codex 0.76 (SHARPENING peak 0.86 — beats claude, and COMPRESSION 0.78 also beats claude), antigravity 0.61 (COMPRESSION 0.08 — standout weakness; REDIRECT 0.68 is the axis where antigravity stays closest to the trio). The per-axis split is the actual signal; aggregate hides which provider wins which axis. Provider can't game it — only Trinity has cross-provider rejection signal.

### The basin labels look fake — "Hello.", "thanks!", greeting noise.

Caught and fixed in v1.7 (P53). Real-corpus largest cluster of 3,408 prompts was rendering as "Hello." because the picker grabbed the first representative. The fix in `commands/me.py` + JS viewer: drop greetings/acks across top-5 reps, choose the longest substantive snippet. Same algorithm both layers so existing on-disk basins benefit at render-time without forcing `lens-build` rerun. If you see "Hello." or "thanks!" as a basin label in v1.7+, that's a bug — file an issue with the basin id and we'll grep the next picker rule into the deny-list.

### Isn't this just a wrapper around three CLIs?

The CLIs are the substrate — yes, Trinity dispatches via `claude`, `codex`, `agy` (the Antigravity CLI, slug `antigravity`) subprocesses. The product is what gets *written back*: every council emits structured Routing JSON to `~/.trinity/council_outcomes/<id>.json` with `agreed_claims`, `disagreed_claims` (with `why_matters`), `provider_scores`, `routing_lesson`. That's a labeled training example the frontier labs *can't see* — Anthropic can't read OpenAI's transcripts, OpenAI can't read Gemini's. The personal routing table, the `lens`, the corpus-based eval harness all compound on this ledger. The wrapper does dispatch; the moat is the ledger. <!-- canonical:test_count -->2069<!-- /canonical --> tests, <!-- canonical:doc_consistency_guards -->108<!-- /canonical --> doc-consistency guards.
