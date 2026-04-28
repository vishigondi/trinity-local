# trinity-local

**The local intelligence layer for people who use multiple AI coding tools.**

Trinity watches Claude Code, Codex, Gemini, Cowork, and other agentic CLIs from the outside, learns which tool works best for which task, and surfaces insights no single provider can see — without running a server, owning the terminal, or becoming yet another UX.

> **Your AI coding tools don't talk to each other. Trinity watches all of them and tells you what none of them can.**

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

Once set up, there are only three commands you need:

```bash
# Watch your AI sessions and surface insights
trinity-local watch-once --notify

# ...or keep watching in the background
trinity-local watch-loop --notify

# See what's happening
trinity-local status
```

Trinity will send macOS notifications when it spots something — a better provider for your task, a repeated workflow worth automating, or a council comparison to run.

### Open the dashboard

```bash
trinity-local portal-html --open-browser
```

### Weekly digest

```bash
trinity-local digest --open-browser
```

## What It Does

- **Watches** transcripts from Claude Code, Codex, Gemini CLI, and Cowork
- **Recommends** the right provider for the task, backed by evidence from your own usage
- **k-NN advisory** — embedding-based routing suggestions using mined hard examples
- **Detects** provider switching — when you abandon one tool and finish in another
- **Tracks** cost and model drift across providers over time
- **Runs councils** — cross-provider comparison with peer review and synthesis
- **Reviews** — ask one provider to critique another's output
- **Analytics** — production observability: evidence spam, threshold brittleness, act/switch rates
- **Generates** weekly digests, static portal pages, and macOS notifications
- **Dispatches** actions through macOS Shortcuts without running a server

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
- `pytest tests/ -v` — base test suite is healthy; embedding-path tests depend on the Hugging Face model cache / network availability
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
