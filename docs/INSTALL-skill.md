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

Skill tier requires the pip wheel underneath (the engine that does
the work). The skill is the user-facing contract; pip is the
plumbing.

```bash
# Pre-PyPI (today):
pip install git+https://github.com/vishigondi/trinity-local
trinity-local install-mcp
```

After v1.0 ships to PyPI, the same wheel is on the index — no
`git+https://` prefix needed.

The `install-mcp` step:
- Wires the Trinity MCP server into Claude Code, Codex CLI, Gemini
  CLI, and Cursor (edits each harness's MCP config; non-destructive)
- Copies `skills/trinity/SKILL.md` from the wheel's package data into
  `~/.claude/skills/trinity/`. Claude Code reads it when you type
  `/trinity`.

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
trinity-local seed-from-taste-terminal --limit 1000
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

- `INSTALL-pip.md` — install Trinity as a CLI-only tool (no Claude
  Code skill registration; useful for headless / CI use)
- `INSTALL-extension.md` — install the Chrome extension for cross-
  surface capture + one-click UI
- `three-tier-architecture.md` — full architecture
- `TRUST-MODE.md` — trust + audit substrate
