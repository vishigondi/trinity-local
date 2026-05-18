# Install Trinity (Skill tier — primary)

> The skill IS the spec. `~/.claude/skills/trinity/SKILL.md` drives the
> `trinity-local` CLI from inside Claude Code via the bash tool. This
> is the primary tier — what you interact with when you type `/trinity`.

## What you get

Type `/trinity` in Claude Code. The skill walks the install (if
needed), runs `doctor`, registers the MCP server, ingests your
existing CLI transcripts, dreams your core memories, and dispatches
your first council. Every command Trinity runs is visible (Claude
Code shows the bash invocations) and audited (`~/.trinity/audit.log`).

## Install path

One curl-bash. Trinity is a git clone, not a published package. The
installer drops the skill at `~/.claude/skills/trinity/`, writes thin
shell wrappers in `~/.local/bin/`, registers MCP in every harness it
finds, and runs `doctor`:

```bash
curl -fsSL https://raw.githubusercontent.com/vishigondi/trinity-local/main/scripts/install.sh | bash
```

Prefer to inspect before piping to bash? Same install in two steps:

```bash
curl -fsSL https://raw.githubusercontent.com/vishigondi/trinity-local/main/scripts/install.sh -o install.sh
less install.sh    # ~150 lines of plain bash; read it
bash install.sh
```

What the installer does:
1. Verifies Python 3.10+ is on PATH (doesn't try to install Python
   for you — too many opinions on how it should be managed)
2. `git clone` the repo to `~/.claude/skills/trinity/` (or `git pull`
   if already present — idempotent)
3. Drops `~/.local/bin/trinity-local` + `~/.local/bin/trinity-local-capture-host`
   as thin shell wrappers (~5 lines each; PYTHONPATH-set + exec)
4. Runs `trinity-local install-mcp` to register the MCP server in
   Claude Code, Codex CLI, Gemini CLI, and Cursor (non-destructive
   edits to each harness's config)
5. Runs `trinity-local doctor` to verify

No PyPI, no npm. Updates: `trinity-local update` — pulls + refreshes.

## After install

```bash
# Verify everything's wired:
trinity-local doctor

# In Claude Code, the skill is now active:
# /trinity
```

The skill walks the rest. If you want to script it instead of using
Claude Code:

```bash
trinity-local ingest-recent             # auto-discovers ~/.claude, ~/.codex, ~/.gemini transcripts
trinity-local dream                     # ~5-15 minutes
trinity-local portal-html --open-browser
```

## Trust + audit

Trinity's trust substrate (`~/.trinity/trust.toml`, `~/.trinity/
audit.log`) ships with v1.0. The skill respects it; every operation
either prompts or pre-grants per the trust config. See
[`TRUST-MODE.md`](TRUST-MODE.md) for the model.

```bash
trinity-local trust-init           # writes a default trust.toml
trinity-local trust-show           # inspect the resolved config
trinity-local audit-show --last 20 # grep the audit ledger
```

## What runs locally vs. what doesn't

- **Local-first**: every embedding, k-means, geometric median,
  descriptor extraction, signature distillation, and audit-log write
  runs on your machine. Trinity never makes outbound HTTP except for
  the one-time `nomic-embed-text-v1.5` download from Hugging Face on
  first run (~250 MB; afterwards `HF_HUB_OFFLINE=1` is pinned).
- **Provider CLIs**: council dispatches ride your existing Claude /
  Codex / Gemini CLI subscriptions. Trinity calls those CLIs as
  subprocesses — your credentials never leave your machine via
  Trinity, only via the provider CLIs themselves (the same way they
  always have).
- **No telemetry by default**. Opt in with `trinity-local
  telemetry-enable`; even then only categorical routing labels leave
  (task_type, provider_scores, winner) — never prompt content.

## See also

- `INSTALL-pip.md` — Python-library access for users who want
  `from trinity_local import council_runtime` in their own code
  (uses the same git clone; `pip install -e .` from there)
- `INSTALL-extension.md` — install the Chrome extension for cross-
  surface capture + one-click UI
- `three-tier-architecture.md` — full architecture
- `TRUST-MODE.md` — trust + audit substrate
