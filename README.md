# trinity-local

> **Trinity asks all your AIs at once, tells you when they agree, and remembers which one you actually trusted.**

Trinity sits underneath Claude Code, Codex, Gemini CLI, ChatGPT, and Claude.ai. When the answer is obvious, it stays out of your way. When models disagree — when *which model to trust* is itself the problem — it runs them all, shows you what they agreed on, what they disagreed on, and why the disagreement matters. Then it learns from your pick.

**The product question:** *"Which model is best at this current time, for my interests?"*
**The answer:** Trinity re-runs your own past prompts against the current model lineup and builds a personal routing table from your outcomes. No benchmarks, no leaderboards — your taste, scored against today's models.

## What Trinity is

A **routing substrate**, not a workspace. The harness (Claude Code / Codex / Gemini / Cowork) owns the work surface. Trinity owns the question of which model to use, and the verifier that tells you why.

Two surfaces:

1. **MCP server (opt-in)** — six tools available to any MCP-compatible harness once you run `trinity-local install-mcp`:
   - `route(task, ...)` — which model should I use? *(no model calls; cheap; honors `latency`/`budget`)*
   - `run_council(task, members, mode, responses=[...])` — run the task across multiple models. Parallel by default; `mode="chain"` runs sequential refinement. **Pass `responses=[...]`** with pre-supplied member outputs to skip dispatch and get only the chairman's verifier-shaped verdict (agreed claims, disagreed claims with why-it-matters, winner, routing lesson, eval seed). This subsumes the former `judge` tool.
   - `record_outcome(council_run_id, user_winner, ...)` — close the supervision loop. Without this Trinity is just a switchboard; with it, Trinity learns.
   - `search_prompts(query)` — find past prompts worth replaying. Ranks by substring + recency + replay-value heuristics across your full AI history (no embedding model on the read path).
   - `get_persona()` — return `~/.trinity/me.md` (the user's `/me` document; pair-wise rejection lenses + vocabulary + abstract lenses).
   - `get_council_status(council_run_id)` — poll an in-flight or completed council; for harnesses without filesystem access.

2. **Launchpad** — `~/.trinity/portal_pages/launchpad.html`. Type a prompt; autofill suggests replay candidates from your taste history with reason chips. Click → council. See the live response stream, the structured Routing JSON verdict, the personal routing table that emerges as you accumulate councils, and **your `/me` taste lenses** (pair-wise rejection cards distilled from your prompt history; copyable to socials with one click).

## What Trinity is *not*

- Another chat UI.
- A hosted service.
- A model. Trinity dispatches to your existing subscriptions; it never bills per call.

## Privacy and cost basis

- **Prompt content and assistant outputs never leave your machine.** Ever.
- Anonymous categorical routing labels (`task_type`, `provider_scores`, `winner`) can be opted in to power live priors and a public leaderboard (v1.1, opt-in only).
- Trinity rides your $20–$200/mo Claude/ChatGPT/Gemini subscriptions. Never paid per call. The model providers eat the inference cost; Trinity captures the preference signal at zero infrastructure cost.

## Setup (one line)

```bash
./setup.sh
```

Creates a virtual environment, installs Trinity, copies the default config, writes the local dispatch wrapper, imports the macOS Shortcut bridge, adds Trinity to your shell `PATH`, and registers the MCP server with Claude Code / Gemini CLI / Codex.

After setup, open a new terminal. `trinity-local ...` runs without manually activating `.venv`.

## Five-minute first run

```bash
# 1. Index your AI taste history (covers Claude.ai, ChatGPT, Gemini Takeout, Claude Code, Codex, Cowork)
trinity-local seed-from-taste-terminal --path ~/projects/taste-terminal/data/exports

# 2. Re-evaluate your top prompts against the current model lineup
trinity-local replay-history --limit 20

# 3. See your personal routing table
trinity-local portal-html --open
```

Inside Claude Code (or any MCP harness), Trinity is now a five-tool MCP server. Ask:

> "Use Trinity to council this: write a launch announcement for Trinity Local."

Or, ad-hoc from the CLI:

```bash
trinity-local council-launch --task "Write a launch announcement for Trinity Local" --members claude gemini codex
```

Trinity auto-picks the chairman per task — the strongest predicted model for the task type — using your personal routing table when populated, then global priors as a baseline.

## What you get back

Every council writes:

- A **comparative analysis** memo (what each model contributes, key tradeoffs, recommendation).
- A **Routing JSON** label — winner, runner_up, confidence, per-provider scores, routing_lesson, eval_seed, agreed_claims, disagreed_claims with why-it-matters. This is the supervision signal for the future learned router.
- A live HTML review page with full responses streaming as each model finishes — no waiting for the chairman to start before you can read the answers.

After enough councils accumulate, Trinity learns: *"For code_refactor prompts, claude wins 7.8/10. For research_synthesis, gemini wins 8.1/10."* That's your personal routing plan, computed from your own taste — not a generic benchmark.

## Architecture (one paragraph)

The chairman is the verifier — the strongest predicted model for the task — emitting a structured Routing JSON over each council. Member models run in parallel (or chain mode for sequential refinement). The personal routing table is the moat: cross-model preference data that frontier providers can't replicate without breaking enterprise privacy. Per-user, local, learned over time.

For details see [`claude.md`](./claude.md). The long-form Phase 0–9 roadmap lives in [`docs/scale-plan.md`](./docs/scale-plan.md). Phase 8 is the routing-substrate work landing now; Phase 9 is the per-user learned router we'll train once enough councils accumulate.

## Help

- `trinity-local --help` — list all commands
- `trinity-local status` — health check
- `trinity-local replay-history --dry-run` — preview which prompts will be re-evaluated
- `trinity-local seed-from-taste-terminal --help` — seed flags
- `trinity-local install-mcp` — register the MCP server in Claude Code / Gemini CLI / Codex
