---
name: trinity
description: Your taste, ported. Install Trinity Local — the cross-provider memory + council layer that lives inside Claude Code, Codex CLI, Antigravity, and Cursor. Use when the user types /trinity, asks how to set up Trinity, wants their lens / picks / routing built from existing transcripts, or wants a hard question dispatched to multiple models with synthesis in their voice.
argument-hint: [optional first-council prompt]
allowed-tools: Bash(curl *) Bash(bash *) Bash(trinity-local *) Bash(command -v *) Bash(which *) Bash(open *) Read
---

# Trinity Local — your taste, ported

Trinity reads transcripts already on the user's machine (Claude Code, Codex CLI, Antigravity, Cursor, claude.ai, chatgpt.com, gemini takeout), learns the pattern in how the user rephrases / judges / decides, then runs hard questions through all three frontier providers in their voice and picks the answer they would have picked.

This skill is the orchestration layer that drives the `trinity-local` CLI from inside Claude Code via the bash tool. The CLI is the engine; this file is the user-facing contract. Every command below can be run by hand — the skill is a transparent driver, not a hidden one.

**Three tiers** the user can run Trinity at (this skill is Tier 1):

- **Tier 1 — Skill** (this file): markdown + JSON + tiny scripts at `~/.claude/skills/trinity/`. Trust mode read by Claude Code, no daemon, no listening port. What runs when the user types `/trinity`.
- **Tier 2 — Pip** (the `trinity-local` wheel — install path shown in section 2 below): same engine, performance + convenience upgrade. The `trinity-local` CLI this skill calls.
- **Tier 3 — Chrome Extension**: cross-surface capture (web chats) + one-click launchpad. Optional. See `trinity-local install-extension`.

All three tiers write to `~/.trinity/`. The data format is the contract; the tiers are surfaces.

## 1. Pre-flight: is Trinity installed?

!`command -v trinity-local || echo "NOT_INSTALLED"`

If `NOT_INSTALLED`, run section 2. Otherwise skip to section 3.

## 2. Install

Trinity ships as a git clone, not a published package. The installer drops the skill in `~/.claude/skills/trinity/`, writes thin shell wrappers in `~/.local/bin/`, registers MCP in every harness you have, and runs `status`.

!`curl -fsSL https://raw.githubusercontent.com/vishigondi/trinity-local/main/scripts/install.sh | bash`

If the user wants to inspect first (recommended for trust-cautious users):

```
curl -fsSL https://raw.githubusercontent.com/vishigondi/trinity-local/main/scripts/install.sh -o /tmp/trinity-install.sh
less /tmp/trinity-install.sh
bash /tmp/trinity-install.sh
```

The installer needs `git` + `python3.10+` on PATH. If Python is missing, recommend `brew install python@3.12` (macOS) or the distro equivalent (`apt install python3.12` etc.) — Trinity doesn't manage Python versions itself; too many opinions on how to do that.

## 3. Pre-flight checks

`status` verifies provider CLIs (Claude / Codex / Antigravity) are installed + authenticated, the MCP dep is present, the Trinity home directory is writable, the launchpad dispatch tier is wired, and embeddings can run. Each ✗ surfaces a one-line fix. (The legacy `doctor` CLI was collapsed into `status` pre-launch — `status` is the single health-check entry point.)

!`trinity-local status`

If any required check fails, walk the user through the surfaced fix. Don't proceed until `trinity_home_writeable`, `config_loadable`, and `mcp_available` are green. Provider CLIs are required for councils but not for setup itself.

**Cold-start callout**: the first embedding call downloads `nomic-embed-text-v1.5` from Hugging Face (~600 MB, one-time, ~3 minutes on a fast connection). Mention this if the user is about to run their first ingest.

## 4. Register the MCP server in every harness

The installer in section 2 already ran this. If MCP needs re-registration (after a `trinity-local update`, or to wire a newly-installed harness), run:

Trinity ships <!-- canonical:mcp_tool_count -->8<!-- /canonical --> MCP tools:
- **canonical four** — `route`, `run_council`, `get_persona`, `get_council_status`
- **v1.5 trio** — `ask` (cheap default), `get_picks` (introspection), `mark_pick_wrong` (user-veto)
- **launch-arc** — `handoff` (cross-provider continuity)
  (`search_prompts` retired 2026-05-17; `get_eval_summary` retired 2026-05-18; `record_outcome` retired 2026-05-21 — chairman's pick is the supervision signal now, refinement prompts carry the "what differently" signal)

!`trinity-local install-mcp`

## 5. First-run flow

If the user has CLI transcripts in `~/.claude/projects/`, `~/.codex/sessions/`, or `~/.gemini/sessions/` (likely — Trinity is for power users who already polyharness), the cheapest first-run is to seed from those:

!`trinity-local ingest-recent`

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

The chairman's pick is automatically the supervision signal — `routing_label.winner` is what `compute_personal_routing_table()` aggregates from, no rating call needed (`record_outcome` retired 2026-05-21). Trinity's moat is the personal ledger of cross-model preferences; the chairman writes to it every council. If the user wants to refine ("I would have picked X because Y"), they click Refine on the council page — the refinement prompt itself is the post-pivot signal of "what should it have been instead." No rating step in the loop; the lens governs selection.

If the question doesn't warrant a full 3-provider council (lookups, syntax, mechanical refactors), prefer the cheaper single-call route:

```
mcp__trinity-local__ask(task="...")
```

## 7. Cross-provider continuity (the killer hook)

Trinity's structurally non-refutable demo: hand a conversation off from one provider to another mid-thread. Only Trinity has the cross-provider prompt index, so only Trinity can do continuity.

```
mcp__trinity-local__handoff(target_provider="antigravity", num_turns=3)
```

Pulls the last N (user, assistant) turns from the prompt index, packages them as "continuing this thread" context, dispatches to a DIFFERENT provider. The target picks up exactly where the prior model left off — no re-context, no copy-paste.

Gemini-handoff is especially strong because Gemini brings Gmail / Drive / Calendar data Claude/GPT can't see — "ask Claude about your codebase, hand off to Gemini for related emails" lights up a capability no provider can match alone.

## 8. Personalized evals (Trinity vs Claude vs Codex vs Gemini on YOUR kind of question)

After enough councils accumulate (`~/.trinity/me/rejections.jsonl` has ≥50 entries), build a personal eval suite scored against the user's actual lens:

```
trinity-local eval-build
trinity-local eval-run --target antigravity
trinity-local eval-show
```

The marketing-headline form: "Model X scored 0.YZ on YOUR kind of question." Empirically grounded, structurally asymmetric — only Trinity has cross-provider rejection signal.

## 9. Memory maintenance

- `trinity-local lens-build` — rebuild paired-tension lenses from `me/rejections.jsonl`
- `trinity-local dream` — full memory-rebuild pass (Phase 5 refreshes `~/.trinity/core.md` automatically)
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
> - `trinity-local handoff antigravity` — hand off the last 3 turns to a different model (the demo most people don't realize they can do; `antigravity` is the post-task-#127 slug for the Google CLI binary `agy`)
> - `trinity-local portal-html --open-browser` — the launchpad: recent councils, lens preview, eval leaderboard, topic graph
> - `trinity-local me-card --open` — render your strongest lens as a sharable PNG

---

**Tier-equivalence invariant** (v1.0 commitment): Trinity tiers produce the same outputs under a pinned configuration (model `nomic-ai/nomic-embed-text-v1.5`, tokenizer pinned, numpy ≥ 1.26). Embedding cosine ≥ 0.9999, identical k-means cluster assignments at production N, identical chairman picker output. NOT bit-equality — float-order differs across MLX vs torch CPU vs torch CUDA by SIMD scheduling. The pinned-config equivalence is the falsifiable form.
