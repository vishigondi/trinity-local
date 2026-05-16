# Install Trinity (Pip tier — CLI only)

> The pip tier is the engine the skill tier calls. Install it directly
> if you want headless / CI use or don't want the Claude Code skill.

## When to use this path

- You don't use Claude Code (the skill tier needs Claude Code to
  drive it).
- You want to script Trinity in CI / cron / shell scripts.
- You want the engine without the orchestration layer.

## Install

```bash
# Pre-PyPI:
pip install git+https://github.com/vishigondi/trinity-local

# After v1.0 ships to PyPI:
pipx install trinity-local
```

The wheel installs:
- `trinity-local` — the CLI entry point (~110 subcommands)
- `trinity-local-capture-host` — Native Messaging host for the
  Chrome extension (installed but inert unless the extension is
  registered separately)

No daemon, no listening port, no background process. Each subcommand
runs to completion and exits.

## Skip the skill registration

```bash
pip install git+https://github.com/vishigondi/trinity-local
# Don't run install-mcp; that's the skill-tier step
trinity-local doctor
```

`trinity-local doctor` verifies provider CLIs + Trinity home +
embedding model availability. If any check fails, it prints a one-
line fix per ✗.

## Common workflows

```bash
# Ingest existing CLI transcripts into ~/.trinity/prompts/
trinity-local seed-from-taste-terminal --limit 1000

# Dream the core memories (~5-15 min depending on corpus size)
trinity-local dream

# Open the launchpad (file:// URL — works without a server)
trinity-local portal-html --open-browser

# Run a council on a single question
trinity-local council-launch --task "what is the right caching strategy"

# Cross-provider continuity (hand the last 3 turns to gemini)
trinity-local handoff gemini

# Personalized eval suite (after enough councils accumulate)
trinity-local eval-build
trinity-local eval-run --target gemini
trinity-local eval-show
```

See `trinity-local --help` for the full command list.

## Trust + audit

The pip tier respects `~/.trinity/trust.toml` and writes to
`~/.trinity/audit.log` exactly like the skill tier. See
[`TRUST-MODE.md`](TRUST-MODE.md).

```bash
trinity-local trust-init
trinity-local trust-show --operation embed_batch --tier pip
trinity-local audit-show --last 20
```

## Heavy ops as standalone scripts

Trinity ships the heavy operations as shebang-runnable Python at
`scripts/` (`embed.py`, `cluster.py`, `pca.py`, `descriptor.py`,
`signature.py`, `anchor.py`). The pip tier imports from these
modules in v1.0; v1.1 inverts so the scripts are the canonical
location and the pip tier is the thin wrapper.

If you cloned the repo and want to run the heavy ops without pip
in the loop:

```bash
git clone https://github.com/vishigondi/trinity-local
cd trinity-local
echo '{"texts": ["hello", "world"]}' | python3 scripts/embed.py
```

The first run creates a script-scoped venv at
`~/.trinity/.venvs/embed/` and installs deps; subsequent runs reuse
it. See `scripts/<name>.py --help` for each script's I/O contract.

## See also

- `INSTALL-skill.md` — install via Claude Code (the primary path)
- `INSTALL-extension.md` — Chrome extension for cross-surface UI
- `three-tier-architecture.md` — full architecture spec
