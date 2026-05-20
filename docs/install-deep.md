---
class: live
---

# Install — deep dive

> The README has the one-line install. This file is the long-form
> companion: prereqs, the three install paths, the embedding model
> download, what `uninstall` removes, and how to drive Trinity from
> inside Claude Code.

## Prereqs

Trinity needs **Python 3.10+** (macOS Sequoia ships with 3.9 by default —
check with `python3 --version`). If you need to upgrade:

```bash
brew install python   # 3.12 or newer
```

Plus the provider CLIs you want in the council: `claude`, `codex`, and/or
`gemini` — each authenticated to your subscription. `trinity-local status`
will tell you which are missing.

## Quickstart (desktop first)

```bash
# One-liner — clones to ~/.trinity/code/ (with a back-compat symlink
# at ~/.claude/skills/trinity/), drops wrappers in ~/.local/bin/,
# registers MCP in every harness you have, runs status.
curl -fsSL https://raw.githubusercontent.com/vishigondi/trinity-local/main/scripts/install.sh | bash

# Then, in Claude Code, just type:  /trinity
# The skill walks you through status + ingest + dream + your first council.
```

The `/trinity` skill is the primary entry point; it teaches the full CLI
after the first council. For the raw command reference, run
`trinity-local --help`.

## Two install paths, two audiences

The CLI (`install-mcp`) is the engine — every other surface wraps it.

- **Skill** (primary; `/trinity`) — what you reach for inside Claude Code.
- **Chrome extension** (`install-extension`) — also the launchpad host.
  Pin the toolbar icon, click it to open the static launchpad; Native
  Messaging dispatches launchpad buttons back to the local CLI. Your
  claude.ai and chatgpt.com conversations grow the corpus passively.

Neither gates the wow: the moment `install-mcp` lands, the first MCP
spawn auto-scans the CLI transcripts you already have on disk, so your
first council is personalized.

## Removing Trinity

```bash
trinity-local uninstall                # dry-run: lists what would be removed
trinity-local uninstall --yes          # actually remove MCP configs + skill
trinity-local uninstall --yes --include-data   # also delete ~/.trinity/ (irreversible)
```

The default uninstall removes Trinity from `~/.claude.json`,
`~/.gemini.json`, `~/.cursor/mcp.json`, the `[mcp_servers.trinity-local]`
block from `~/.codex/config.toml`, the Chrome Native Messaging manifest,
and the bundled `/trinity` skill — but **preserves `~/.trinity/`** (your
corpus, lens, scoreboard, council outcomes) unless you explicitly pass
`--include-data`. The wedge cuts both ways: own your data also means you
decide when to delete it.

`trinity-local status` checks each provider CLI is installed +
authenticated, the MCP server dependency is present, and your Trinity
directory is writable — surfaces a one-line fix for each ✗ before you hit
a live council.

## Offline by default — and a one-time embedding model download

Trinity pins `HF_HUB_OFFLINE=1` at startup, so the running system never
makes outbound HuggingFace calls during normal operation. The embedding
model (`nomic-embed-text-v1.5`, ~600 MB) ships once via an explicit, opt-in
download:

```bash
HF_HUB_OFFLINE=0 huggingface-cli download nomic-ai/nomic-embed-text-v1.5
```

After that the model lives at `~/.cache/huggingface/hub/` (or `$HF_HOME`)
and Trinity loads it from cache — no Hub contact. Override per-invocation
if you ever need to pull a new version (`HF_HUB_OFFLINE=0 trinity-local …`);
otherwise the offline guarantee holds across every CLI call and every MCP
child process.

## Drive it from inside Claude Code

`trinity-local install-mcp` also drops a `/trinity` skill into
`~/.trinity/code/skills/trinity/` (resolved through the back-compat
symlink at `~/.claude/skills/trinity/` so Claude Code's skill loader
finds it). Once the install-mcp step above ran, type `/trinity` at the Claude
Code prompt to redo the install + status + first-council on a fresh
machine without touching your shell. The skill respects local edits — if
you've customized the file, future `install-mcp` runs leave it alone.
