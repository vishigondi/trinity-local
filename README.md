# trinity-local

**The local intelligence layer for people who use multiple AI tools.**

Trinity watches Claude Code, Codex, Gemini, Cowork, and other agentic CLIs from the outside, learns which tool works best for which task, and surfaces insights no single provider can see — without running a server, owning the terminal, or becoming yet another UX.

> **Your AI tools don't talk to each other. Trinity watches all of them and tells you what none of them can.**

Everyone has Claude Pro + ChatGPT Plus + Gemini Advanced. Three subscriptions, and still doesn't know which one to use for what. We copy-paste between tabs like animals.

## Setup (one line)

```bash
./setup.sh
```

That's it. This creates a virtual environment, installs Trinity, copies the default config, writes the local dispatch wrapper, imports the macOS Shortcut bridge, and adds Trinity to your shell `PATH`.

After setup, open a new terminal. You should be able to run `trinity-local ...` directly without activating `.venv` manually.

If you want the current shell to pick it up immediately:

```bash
source ~/.zshrc
```

If you're using bash instead of zsh:

```bash
source ~/.bash_profile
```

## Daily Usage

The fastest first win is a council:

```bash
# Create a prompt bundle
trinity-local bundle-create "Write a launch announcement for Trinity Local" --goal "Find the strongest answer"

# Run a council (watch live progress as members respond)
trinity-local council-start --bundle <id> --members claude gemini codex --primary-provider claude --notify --open-browser
```

Trinity will show live progress (✓ done, ⏳ running, · pending) with reasoning summaries as each member completes.

After that, there are only three commands you need:

```bash
# Watch your AI sessions and surface insights
trinity-local watch-once --notify

# ...or keep watching in the background
trinity-local watch-loop --notify

# See what's happening
trinity-local status
```

Trinity will send macOS notifications when it spots something — a better provider for your task, a council comparison to run, or a repeated workflow worth automating.

### Open the dashboard

```bash
trinity-local portal-html --open-browser
```

The dashboard polls council progress every 1.5 seconds during execution and reloads after settings changes.

### Configure auto-ingest transcript (optional)

Trinity can automatically ingest transcripts from your AI tools in the background:

```bash
# Enable automatic transcript ingestion
trinity-local auto-ingest-enable

# Disable it later
trinity-local auto-ingest-disable
```

You can also toggle this from the dashboard settings.

### Weekly digest

```bash
trinity-local digest --open-browser
```

## Product Shape

Trinity is built around this sequence:

1. **Run a council** on a real task
2. **Watch live progress** as members respond with reasoning summaries
3. **Pick the best answer**
4. **Let Trinity learn your taste**
5. **Let the watcher surface future councils and reroutes**
6. **Later, automate repeated workflows**

Council is the first win. Watcher and workflow suggestions become more valuable after Trinity has seen real choices. Live progress makes councils feel interactive instead of opaque.

## What It Does

- **Runs councils first** — compare the same task across providers with peer review, synthesis, and live progress tracking
- **Shows live progress** — watch council members respond in real-time with reasoning summaries (✓ done, ⏳ running, · pending)
- **Watches** transcripts from Claude Code, Codex, Gemini CLI, and Cowork (optionally auto-ingests in the background)
- **Recommends** the right provider for the task, backed by evidence from your own usage
- **k-NN advisory** — embedding-based routing suggestions using mined hard examples
- **Detects** provider switching — when you abandon one tool and finish in another
- **Tracks** cost and model drift across providers over time
- **Reviews** — ask one provider to critique another's output
- **Analytics** — production observability: evidence spam, threshold brittleness, act/switch rates
- **Generates** weekly digests, static portal pages, and macOS notifications
- **Dispatches** actions through macOS Shortcuts without running a server

## Why This Architecture Matters

Trinity can do things a single provider cannot:

- **Watcher-triggered council** — notice that a task deserves comparison before the user manually switches tools
- **Cross-provider memory** — learn that Claude failed, Gemini recovered, and Codex finished the same task
- **Taste learning** — use council choices and later switching behavior to learn what "better" means for you
- **Workflow detection** — spot repeated patterns across tools, not just inside one chat
- **Provider intelligence from real work** — recommendations based on your transcripts and outcomes, not public benchmark theater

## The Social Layer

The likely breakout features are not just routing. They are the shareable artifacts this architecture can generate from real local usage:

1. **Personal model radar chart** — "on my work, which model is best at research, writing, coding, trust, speed?"
2. **Council battle cards** — the prompt, contenders, winner, and why
3. **AI taste profile** — "you prefer Claude for strategy, Gemini for research, Codex for debugging"
4. **Weekly model report** — how your provider rankings changed this week
5. **Personal provider Elo** — your own leaderboard, not a public benchmark

The council is the engine. The radar chart is the social payload.

## Frontend Stack

The frontend architecture is intentionally simple:

- **static HTML** for durable local artifacts
- **`petite-vue`** for interactive islands
- **`Chart.js`** for radar, Elo, and report visuals
- **`DESIGN.md`** as the visual contract

This keeps Trinity compatible with `file://` pages, local bookmarks, and the
Shortcuts / local-helper execution model.

## Requirements

- macOS
- Python 3.10+
- At least two of: `claude`, `gemini`, `codex`, Cowork

## Going Deeper

### Run a council comparison

```bash
# Create a prompt bundle
trinity-local bundle-create "Design the auth system" --goal "Find the best approach"

# Run council with peer review and synthesis
trinity-local council-start --bundle <id> --members claude codex gemini --notify --open-browser
```

### Post-hoc review

```bash
# Ask another provider to review a completed task
trinity-local review --task <task_id> --reviewer gemini
```

### Research pipeline

```bash
# Mine hard examples (embedding-based cross-provider matching)
trinity-local hard

# Run 5-metric evaluation on hard examples
trinity-local hardeval

# k-NN advisory analytics report
trinity-local analytics
```

### Inspect state

```bash
trinity-local scoreboard              # Provider scores
trinity-local action-list             # Pending actions
trinity-local features --source all --limit 20  # Session features
trinity-local adapters                # Provider adapter status
```

### macOS Shortcut management

```bash
trinity-local shortcut-install        # Import the Trinity Dispatch shortcut
trinity-local shortcut-setup          # Write setup guide to ~/.trinity/shortcut_setup/
```

### Embedding support (optional)

For the best routing quality (k-NN advisory, hard mining, eval), install embedding support:

```bash
./.venv/bin/pip install -e '.[mlx]'
```

Without embeddings, Trinity falls back to heuristics and TF-IDF-based matching. Everything still works — embeddings just make the recommendations more precise.

## How It Works

```
Provider CLIs (Claude, Codex, Gemini, Cowork)
   ↓
Transcript Adapters (parse session files)
   ↓
Session Feature Extraction (compact signals)
   ↓
File-Backed State (~/.trinity/)
   ↓
Watcher Analysis (cost, outcomes, switching, drift)
   ↓
k-NN Advisory (embedding neighbors from hard-example corpus)
   ↓
Signals (recommendations, council triggers, workflow suggestions)
   ↓
Notifications / Static Portal / Shortcuts / Council
   ↓
Analytics (advisory log, evidence spam, threshold checks, product metrics)
```

## State

All mutable state lives under `~/.trinity/` (overridable via `TRINITY_HOME`):

```
~/.trinity/
├── tasks/              # One JSON per task
├── actions/            # Pending action records
├── prompt_bundles/     # Saved prompt bundles
├── council_outcomes/   # Council outcome records
├── reviews/            # Post-hoc review results
├── review_pages/       # Review HTML
├── portal_pages/       # Static launchpad HTML
├── digest_pages/       # Weekly digest HTML
├── bin/
│   └── trinity-dispatch  # Shortcut dispatch wrapper
├── cache/
│   └── embeddings.jsonl  # Shared embedding cache
├── research/
│   └── hard_examples/  # Mined hard examples (k-NN corpus)
├── analytics/
│   ├── knn_advisory.jsonl        # Advisory event log
│   └── knn_advisory_report.json  # Latest analytics report
├── cost_log.jsonl      # Per-session cost estimates
├── outcomes.jsonl      # Per-session outcomes for drift
└── ...
```

## Verified

- `python3 -m compileall src` — clean
- `pytest -q` — **165 passed** (Phase 0 refactor checkpoint)
- Graceful fallback: if MLX fails at runtime, `embed()` falls back to TF-IDF
- 15 command modules registering 40 CLI subcommands
- `watch-once`, `portal-html`, `digest`, `shortcut-install` — all write correctly to `~/.trinity/`
- `hard`, `hardeval`, `analytics` — research pipeline verified
- `council-start` — live progress tracking with file-based JSON/JS polling (1.5s refresh)
- `auto-ingest-enable`/`auto-ingest-disable` — daemon lifecycle management with telemetry persistence
- `portal-html` — on-demand reload after settings changes, live progress polling during council execution

## Documentation

- [claude.md](claude.md) — Architecture, coding conventions, development guide
- [docs/scale-plan.md](docs/scale-plan.md) — Active refactor + distribution plan: Phase 0 stability work (in progress), then MCP server, skills, hooks, growth flywheel
- [docs/product-spec.md](docs/product-spec.md) — Product spec, GTM strategy, roadmap
- [docs/frontend-architecture.md](docs/frontend-architecture.md) — Static HTML + `petite-vue` + `Chart.js` frontend spec
- [docs/telemetry-spec.md](docs/telemetry-spec.md) — Opt-in telemetry, launchpad view events, Elo snapshot sharing
- [docs/training-data.md](docs/training-data.md) — Training data plan and session formats
- [docs/launcher-patterns.md](docs/launcher-patterns.md) — macOS Shortcuts dispatch research
- [DESIGN.md](DESIGN.md) — visual system and UI rules

## Roadmap

The next big arc is making Trinity available to every Claude Code, Gemini CLI, and Codex CLI user with one command. See [docs/scale-plan.md](docs/scale-plan.md) for the full plan, which covers:

- **Phase 0** — refactor + stability (in progress: embedding fix done, council run-state unified, dispatch wrapper portable, etc.)
- **Phase 1+** — MCP server (`trinity-local --mcp`), `install-mcp` cross-CLI installer, skills, ambient `Stop` hook, vendor-hosted JS, update mechanism, leaderboard

## Product Mantra

**Do not become the agent. Watch the agents.**
**Lead with council. Let the watcher earn trust later.**
**Do not own the workflow. Learn from the workflow.**
**Do not optimize for demos. Optimize for deltas.**
**The magic is not orchestration. The magic is cross-provider memory.**
