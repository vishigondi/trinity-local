# trinity-local

**The local intelligence layer for people who use multiple AI coding tools.**

Trinity watches Claude Code, Codex, Gemini, Cowork, and other agentic CLIs from the outside, learns which tool works best for which task, and surfaces insights no single provider can see — without running a server, owning the terminal, or becoming yet another UX.

> **Your AI coding tools don't talk to each other. Trinity watches all of them and tells you what none of them can.**
>
> Everyone has Claude Pro + ChatGPT Plus + Gemini Advanced. Three subscriptions, and still doesn't know which one to use for what. We copy-paste between tabs like animals.

See [docs/product-spec.md](docs/product-spec.md) for the full product spec and GTM strategy.

## Release Status

`trinity-local` is currently an **alpha / developer preview** for technical users.

Best fit:

- people already using Claude Code, Codex, Gemini, or Cowork
- macOS-first workflows
- users comfortable with local CLIs, static HTML artifacts, and manual setup

This is not polished general-availability software yet.

## What It Does

- **Watches** transcripts from Claude Code, Codex, Gemini CLI, and Cowork
- **Extracts** session features: model, tokens, cost, latency, tool calls, completion signal
- **Detects** provider switching — when you abandon one tool and finish in another
- **Tracks** cost and model drift across providers over time
- **Recommends** the right provider for the task, backed by evidence from your own usage
- **k-NN advisory** — embedding-based routing suggestions using mined hard examples
- **Runs councils** — cross-provider comparison with peer review and synthesis
- **Reviews** — ask one provider to critique another's completed output
- **Mines hard examples** — finds cross-provider routing conflicts via embedding similarity
- **Evaluates** routing quality with 5-metric suite (reroute recall, needs_council P/R, switch prediction, top-2 provider accuracy, NN evidence quality)
- **Analytics** — production observability for k-NN advisory: evidence spam, threshold brittleness, act rate, switch-after-acted rate
- **Generates** weekly digests, static portal pages, and macOS notifications
- **Dispatches** actions through macOS Shortcuts without running a server

## Requirements

- macOS
- Python 3.10+
- At least two of: `claude`, `gemini`, `codex`, Cowork

## Install

```bash
pip install -e .
```

For embedding-based features (k-NN advisory, hard mining, eval):

```bash
pip install -e '.[mlx]'
```

For tests:

```bash
pip install -e '.[test]'
pytest tests/ -v
```

Embeddings are optional, but recommended if you want the best routing quality.
Without them, Trinity falls back to heuristics and TF-IDF-compatible behavior.

## Quick Start

## Recommended First-Run Flow

1. Install the base package:

```bash
pip install -e .
```

2. If you want the full advisory and research path, install embedding support:

```bash
pip install -e '.[mlx]'
```

3. Check provider availability:

```bash
trinity-local adapters
trinity-local status --json
```

4. Generate and install the macOS Shortcut bridge:

```bash
trinity-local shortcut-setup
trinity-local shortcut-install
```

5. Render the static launchpad:

```bash
trinity-local portal-html --open-browser
```

6. Run the watcher on your local transcripts:

```bash
trinity-local watch-once --notify
```

7. Inspect what Trinity produced:

```bash
trinity-local action-list
trinity-local analytics
```

### Watch your sessions

```bash
# Scan recent sessions, extract features, surface insights
trinity-local watch-once --notify

# Continuous background watcher
trinity-local watch-loop --source claude --source gemini --source codex --source cowork --notify --interval 30
```

### Weekly digest

```bash
trinity-local digest                  # Summary in terminal
trinity-local digest --open-browser   # Dark-themed HTML report
trinity-local digest --json           # Machine-readable output
```

### Run a council comparison

```bash
# Create a prompt bundle
trinity-local bundle-create "Design the auth system" --goal "Find the best approach"

# Run council with peer review and synthesis
trinity-local council-start --bundle <id> --members claude codex gemini --notify --open-browser
```

### Post-hoc review (Council-lite)

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

### See what's happening

```bash
trinity-local scoreboard              # Provider scores
trinity-local action-list             # Pending actions
trinity-local portal-html --open-browser  # Static launchpad
trinity-local features --source all --limit 20  # Session features
trinity-local adapters                # Provider adapter status
```

### macOS Shortcuts setup

```bash
trinity-local shortcut-setup          # Generates setup recipe at ~/.trinity/shortcut_setup/
trinity-local shortcut-install        # Creates the Trinity Dispatch shortcut (opens Shortcuts app)
```

## Known Limitations

- macOS is the primary supported platform today.
- Shortcuts onboarding is still partially manual.
- Windows and Linux are not first-class UX targets yet.
- The watcher and recommendation system are most useful once you have real transcript history.
- Analytics and advisory metrics remain sparse until you have live watch activity and a hard-example corpus.
- The legacy `run` command still exists, but it is not the product center.

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
- `pytest tests/ -v` — **119 passed, 4 skipped** across 10 test files
- 15 command modules registering 40 CLI subcommands
- `watch-once`, `portal-html`, `digest`, `shortcut-install` — all write correctly to `~/.trinity/`
- `hard`, `hardeval`, `analytics` — research pipeline verified

## Documentation

- [claude.md](claude.md) — Architecture, coding conventions, development guide
- [docs/product-spec.md](docs/product-spec.md) — Product spec, GTM strategy, roadmap
- [docs/training-data.md](docs/training-data.md) — Training data plan and session formats
- [docs/launcher-patterns.md](docs/launcher-patterns.md) — macOS Shortcuts dispatch research

## Product Mantra

**Do not become the agent. Watch the agents.**
**Do not own the workflow. Learn from the workflow.**
**Do not optimize for demos. Optimize for deltas.**
**The magic is not orchestration. The magic is cross-provider memory.**
