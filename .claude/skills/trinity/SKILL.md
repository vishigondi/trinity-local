---
name: trinity
description: One-shot Trinity Local onboarding — install the package, register the MCP server in Claude Code / Codex / Gemini CLI, run pre-flight checks, and queue up a first council. Use when the user types /trinity in a fresh session, asks "how do I install Trinity," or wants to set up the local council from scratch.
argument-hint: [optional first-council prompt]
allowed-tools: Bash(pip install *) Bash(pipx install *) Bash(trinity-local *) Bash(command -v *) Bash(which *) Read
---

# Install Trinity Local in one shot

Run the steps below in order. Each step is one shell command; the next step depends on the previous one's success.

## 1. Check whether trinity-local is already on PATH

!`command -v trinity-local || echo "NOT_INSTALLED"`

If the output is a path → skip to step 4 (doctor). If it's `NOT_INSTALLED`, continue.

## 2. Install the package

Prefer `pipx` (isolates the install) when available; fall back to `pip --user` otherwise. Until PyPI publish lands at v1.0 ship, install from GitHub directly.

!`command -v pipx >/dev/null && pipx install git+https://github.com/vishigondi/trinity-local || pip install --user git+https://github.com/vishigondi/trinity-local`

If both fail because the user is on a managed Python, surface the error and recommend `python3 -m venv ~/.trinity-venv && ~/.trinity-venv/bin/pip install git+https://github.com/vishigondi/trinity-local && ln -s ~/.trinity-venv/bin/trinity-local ~/.local/bin/trinity-local`.

(Post-ship: `pipx install trinity-local` — same package, faster, after PyPI publish lands.)

## 3. Register the MCP server in Claude Code, Codex, and Gemini CLI

This wires the Trinity MCP tools into every harness the user has installed. v1.0 ships 6 canonical tools (`run_council`, `route`, `record_outcome`, `search_prompts`, `get_persona`, `get_council_status`); v1.5 adds `ask` (cheap default single-call routing), `get_picks` (introspection into extracted picks), `mark_pick_wrong` (user-veto on a pick — halves effective trust per click); launch-arc adds `handoff` (cross-provider continuity — switch models mid-conversation with full context preserved) and `get_eval_summary` (per-axis benchmark scores from your actual rejection signal) — 11 total. The install edits `~/.claude.json`, `~/.gemini.json`, and `~/.codex/config.toml` — non-destructive, only adds the Trinity entry.

!`trinity-local install-mcp`

## 4. Pre-flight checks

`doctor` verifies provider CLIs are installed + authenticated, the MCP dep is present, the Trinity home directory is writable, and surfaces a one-line fix per ✗.

!`trinity-local doctor`

If any required check fails, stop and walk the user through the surfaced fix line. Don't proceed to step 5 until `doctor` is green on the required checks (`trinity_home_writeable`, `config_loadable`, `mcp_available` — provider CLIs are required for councils but not for the install itself).

## 5. (Optional) First council

If the user passed an argument, launch a council against it so they see a structured Routing JSON on their first run:

```
mcp__trinity-local__run_council(task="$ARGUMENTS", members=["claude","gemini","codex"], mode="parallel")
```

Otherwise, summarize what's installed and suggest the obvious next move:

> Trinity is set up. Try:
> - `/council <a hard question>` — compare Claude / Gemini / Codex on one prompt
> - `trinity-local lens-build` — distill your taste lenses from existing transcripts (after a few councils)
> - `trinity-local me-card` — render your strongest lens as a 1200×630 PNG to share

After any council, remember to call `mcp__trinity-local__record_outcome(council_run_id=..., user_winner=...)` once the user picks the answer they preferred — that's the supervision signal that improves Trinity's chairman picker over time.
