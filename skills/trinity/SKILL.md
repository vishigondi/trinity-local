---
name: trinity
description: Your taste, ported. Install Trinity Local — the cross-provider memory + council layer that lives inside Claude Code, Codex CLI, Gemini CLI, and Cursor. Use when the user types /trinity, asks how to set up Trinity, wants their lens / picks / routing built from existing transcripts, or wants a hard question dispatched to multiple models with synthesis in their voice.
argument-hint: [optional first-council prompt]
allowed-tools: Bash(pip install *) Bash(pipx install *) Bash(trinity-local *) Bash(command -v *) Bash(which *) Bash(open *) Read
---

# Trinity Local — your taste, ported

Trinity reads transcripts already on the user's machine (Claude Code, Codex CLI, Gemini CLI, Cursor, claude.ai, chatgpt.com, gemini takeout), learns the pattern in how the user rephrases / judges / decides, then runs hard questions through all three frontier providers in their voice and picks the answer they would have picked.

This skill is the orchestration layer that drives the `trinity-local` CLI from inside Claude Code via the bash tool. The CLI is the engine; this file is the user-facing contract. Every command below can be run by hand — the skill is a transparent driver, not a hidden one.

**Three tiers** the user can run Trinity at (this skill is Tier 1):

- **Tier 1 — Skill** (this file): markdown + JSON + tiny scripts at `~/.claude/skills/trinity/`. Trust mode read by Claude Code, no daemon, no listening port. What runs when the user types `/trinity`.
- **Tier 2 — Pip** (`pip install trinity-local`): same engine, performance + convenience upgrade. The `trinity-local` CLI this skill calls.
- **Tier 3 — Chrome Extension**: cross-surface capture (web chats) + one-click launchpad. Optional. See `trinity-local install-extension`.

All three tiers write to `~/.trinity/`. The data format is the contract; the tiers are surfaces.

## 1. Pre-flight: is Trinity installed?

!`command -v trinity-local || echo "NOT_INSTALLED"`

If `NOT_INSTALLED`, run section 2. Otherwise skip to section 3.

## 2. Install

Prefer `pipx` (isolates the install) when available; fall back to `pip --user` otherwise. Until PyPI publish lands at v1.0 ship, install from GitHub directly.

!`command -v pipx >/dev/null && pipx install git+https://github.com/vishigondi/trinity-local || pip install --user git+https://github.com/vishigondi/trinity-local`

If both fail because the user is on a managed Python, surface the error and recommend:

```
python3 -m venv ~/.trinity-venv
~/.trinity-venv/bin/pip install git+https://github.com/vishigondi/trinity-local
ln -s ~/.trinity-venv/bin/trinity-local ~/.local/bin/trinity-local
```

Once PyPI publishes: `pipx install trinity-local`.

## 3. Pre-flight checks

`doctor` verifies provider CLIs (Claude / Codex / Gemini) are installed + authenticated, the MCP dep is present, the Trinity home directory is writable, the launchpad dispatch tier is wired, and embeddings can run. Each ✗ surfaces a one-line fix.

!`trinity-local doctor`

If any required check fails, walk the user through the surfaced fix. Don't proceed until `trinity_home_writeable`, `config_loadable`, and `mcp_available` are green. Provider CLIs are required for councils but not for setup itself.

**Cold-start callout**: the first embedding call downloads `nomic-embed-text-v1.5` from Hugging Face (~250 MB, one-time, ~3 minutes on a fast connection). Mention this if the user is about to run their first ingest.

## 4. Register the MCP server in every harness

Wires the Trinity MCP tools into Claude Code, Codex CLI, Gemini CLI, and Cursor. Edits `~/.claude.json`, `~/.codex/config.toml`, `~/.gemini.json`, `~/.cursor/mcp.json` — non-destructive, only adds the Trinity entry.

v1.0 ships 11 MCP tools:
- **canonical six** — `route`, `run_council`, `record_outcome`, `search_prompts`, `get_persona`, `get_council_status`
- **v1.5 trio** — `ask` (cheap default), `get_picks` (introspection), `mark_pick_wrong` (user-veto)
- **launch-arc pair** — `handoff` (cross-provider continuity), `get_eval_summary` (per-axis benchmark scores)

!`trinity-local install-mcp`

## 5. First-run flow

If the user has CLI transcripts in `~/.claude/projects/`, `~/.codex/sessions/`, or `~/.gemini/sessions/` (likely — Trinity is for power users who already polyharness), the cheapest first-run is to seed from those:

!`trinity-local seed-from-taste-terminal --limit 1000`

That produces `~/.trinity/prompts/prompt_nodes.jsonl` — the indexed corpus. Then dream the core memories (one command, ~5-15 minutes depending on corpus size):

!`trinity-local dream`

`dream` runs cross-provider pair mining → consolidation → lens build → core distillation end-to-end. Output: `~/.trinity/core.md`, `~/.trinity/memories/lens.md`, `~/.trinity/memories/topics.json`, `~/.trinity/memories/vocabulary.md`. Open the launchpad to inspect:

!`trinity-local portal-html --open-browser`

## 6. Council on a hard question

For complex questions where two senior engineers could reasonably disagree (architecture, API shape, refactor scope), dispatch all three providers in parallel and chairman-synthesize the result:

```
mcp__trinity-local__run_council(task="$ARGUMENTS", mode="parallel")
```

The chairman reads `~/.trinity/memories/lens.md` and synthesizes the members' answers through the user's taste. Output: structured Routing JSON with `agreed_claims`, `disagreed_claims`, `winner`, `runner_up`, `provider_scores`, `routing_lesson`. Persisted at `~/.trinity/council_outcomes/<id>.json`.

After the council, **always** call `record_outcome` once the user picks their answer:

```
mcp__trinity-local__record_outcome(council_run_id=..., user_winner="...")
```

This is the supervision signal that improves Trinity's chairman picker over time. Trinity's moat is the personal ledger of cross-model preferences — `record_outcome` is what writes to it.

If the question doesn't warrant a full 3-provider council (lookups, syntax, mechanical refactors), prefer the cheaper single-call route:

```
mcp__trinity-local__ask(task="...")
```

## 7. Cross-provider continuity (the killer hook)

Trinity's structurally non-refutable demo: hand a conversation off from one provider to another mid-thread. Only Trinity has the cross-provider prompt index, so only Trinity can do continuity.

```
mcp__trinity-local__handoff(target_provider="gemini", num_turns=3)
```

Pulls the last N (user, assistant) turns from the prompt index, packages them as "continuing this thread" context, dispatches to a DIFFERENT provider. The target picks up exactly where the prior model left off — no re-context, no copy-paste.

Gemini-handoff is especially strong because Gemini brings Gmail / Drive / Calendar data Claude/GPT can't see — "ask Claude about your codebase, hand off to Gemini for related emails" lights up a capability no provider can match alone.

## 8. Personalized evals (Trinity vs Claude vs Codex vs Gemini on YOUR kind of question)

After enough councils accumulate (`~/.trinity/me/rejections.jsonl` has ≥50 entries), build a personal eval suite scored against the user's actual lens:

```
trinity-local eval-build
trinity-local eval-run --target gemini
trinity-local eval-show
```

The marketing-headline form: "Model X scored 0.YZ on YOUR kind of question." Empirically grounded, structurally asymmetric — only Trinity has cross-provider rejection signal.

## 9. Memory maintenance

- `trinity-local lens-build` — rebuild paired-tension lenses from `me/rejections.jsonl`
- `trinity-local distill` — refresh `~/.trinity/core.md` from `lens.md` + `topics.json` + `vocabulary.md`
- `trinity-local consolidate` — extract cortex routing patterns from council outcomes (with `--audit` for second-flagship drift check)
- `trinity-local cortex-override` — flag a routing rule wrong; halves effective trust per click
- `trinity-local me-card --open` — render the strongest lens as a 1200×630 PNG for sharing

## 10. Trust + privacy (current state, v1.0)

Trinity does NOT make outbound network calls during normal operation. The embedding model is pulled once from Hugging Face on first run; afterwards `HF_HUB_OFFLINE=1` is pinned in process env. Every dispatch rides the user's own provider CLI subscriptions — no API keys leave the machine.

The personal ledger (`~/.trinity/council_outcomes/`) never uploads. If the user opts into telemetry (`trinity-local telemetry-enable`), only categorical routing labels (`task_type`, `provider_scores`, `winner`) leave — never prompt content.

**v1.1 will add** a uniform trust-mode + audit-log substrate (see `docs/three-tier-architecture.md`). v1.0 invariant: single active tier per `~/.trinity/` directory; concurrent multi-tier use is v1.1.

## 11. Common follow-ups

Suggest these to the user after section 5 succeeds:

> Trinity is set up. Next moves:
> - `/council <a hard question>` — dispatch through all three providers, synthesized in your voice
> - `trinity-local handoff gemini` — hand off the last 3 turns to a different model (the demo most people don't realize they can do)
> - `trinity-local portal-html --open-browser` — the launchpad: recent councils, lens preview, eval leaderboard, topic graph
> - `trinity-local me-card --open` — render your strongest lens as a sharable PNG

---

**Tier-equivalence invariant** (v1.0 commitment): Trinity tiers produce the same outputs under a pinned configuration (model `nomic-ai/nomic-embed-text-v1.5`, tokenizer pinned, numpy ≥ 1.26). Embedding cosine ≥ 0.9999, identical k-means cluster assignments at production N, identical chairman picker output. NOT bit-equality — float-order differs across MLX vs torch CPU vs torch CUDA by SIMD scheduling. The pinned-config equivalence is the falsifiable form.
