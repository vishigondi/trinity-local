# trinity-local

**The local intelligence layer for people who use multiple AI coding tools.**

Trinity watches Claude Code, Codex, Gemini, Cowork, and other agentic CLIs from the outside, learns which tool works best for which task, and surfaces insights no single provider can see — without running a server, owning the terminal, or becoming yet another UX.

> **Your AI coding tools don't talk to each other. Trinity watches all of them and tells you what none of them can.**

See [docs/product-spec.md](docs/product-spec.md) for the full product spec and GTM strategy.

## What It Does

- **Watches** transcripts from Claude Code, Codex, Gemini CLI, and Cowork
- **Extracts** session features: model, tokens, cost, latency, tool calls, completion signal
- **Detects** provider switching — when you abandon one tool and finish in another
- **Tracks** cost and model drift across providers over time
- **Recommends** the right provider for the task, backed by evidence from your own usage
- **Runs councils** — cross-provider comparison with peer review and synthesis
- **Reviews** — ask one provider to critique another's completed output
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

For tests:

```bash
pip install -e '.[test]'
pytest tests/ -v
```

## Quick Start

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

### See what's happening

```bash
trinity-local scoreboard              # Provider scores
trinity-local action-list             # Pending actions
trinity-local portal-html --open-browser  # Static launchpad
trinity-local features --source all --limit 20  # Session features
```

### macOS Shortcuts setup

```bash
trinity-local shortcut-setup          # Generates setup doc at ~/.trinity/shortcut_setup/
```

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
Signals (recommendations, council triggers, workflow suggestions)
   ↓
Notifications / Static Portal / Shortcuts / Council
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
├── cost_log.jsonl      # Per-session cost estimates
├── outcomes.jsonl      # Per-session outcomes for drift
└── ...
```

## Verified

- `python3 -m compileall src` — clean
- `pytest tests/ -v` — **54 passed**
- CLI command registration — all 12 command modules
- `watch-once`, `portal-html`, `digest`, `shortcut-setup` — all write correctly to `~/.trinity/`

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
