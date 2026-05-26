---
class: live
---

# Trinity Substrate Spec (v2)

> **Status:** v2 draft — locked May 26, 2026. Supersedes v1 (May 14, 2026). v2 reframes the spec as the **union of three existing standards (SKILL.md, AGENTS.md, MCP) plus the Trinity-specific extension fields that let cross-provider preference signal flow through them**. v1's JSON Schemas survive as the council-outcome / rejection-signal / eval-set surface; the spec now names what they extend rather than claiming to be its own standard.
>
> **The v2 thesis:** skill marketplaces are flat directories of curated procedures. Trinity is a hierarchical substrate with eval-gated promotion between layers, exposed via three standards that already ship in 30+ agent tools. The interop story is "we don't invent — we stack."

## Why v2 exists

v1 (May 2026) was an honest first cut: three Trinity-shaped JSON schemas (council outcome, rejection signal, eval set), CC0-licensed, with a "please adopt this" appeal. The problem v1 didn't solve: it left Trinity standing alongside skill marketplaces (anthropics/skills, claude-skills, agentskills.io) and project-guidance formats (AGENTS.md) and MCP resources — as if those were unrelated surfaces.

**They're not unrelated.** They're the same substrate at different abstraction levels:

| CoALA layer ([Sumers et al. 2024](https://arxiv.org/html/2603.07670v1)) | Trinity name | Existing standard | What it stores |
|---|---|---|---|
| Episodic | **transcripts** | (no shared standard yet — MessageList shapes diverge) | Raw conversations across CLIs + web chats |
| Semantic | **memories** | MCP Resources (read-only context) | Extracted facts/observations from dream |
| Procedural | **moves** | [SKILL.md](https://agentskills.io/specification) | Crystallized procedures that consistently produced accepted outputs |
| Preferential | **lens** | [AGENTS.md](https://github.com/agentsmd/agents.md) | The geometry across all of the above — tensions, basins, vocabulary |

Each layer is a compression of the one below. Promotion between layers is what `dream` already does for memories. v2 names the missing piece: **eval-gated promotion** of memories→moves, and the standards-aligned export format for each layer.

## The four-layer substrate

### Layer 1: Transcripts (episodic)

Raw conversations indexed at `~/.trinity/prompts/prompt_nodes.jsonl`. Sourced from CLI sessions (`~/.claude/`, `~/.codex/`, `~/.gemini/`) and browser-captured chats (claude.ai, chatgpt.com, gemini.google.com). No shared standard exists for this; Trinity reads each provider's native format.

### Layer 2: Memories (semantic)

Distilled observations + facts written at `~/.trinity/memories/`. Files: `core.md` (one-paragraph identity), `lens.md` (paired tensions), `topics.json` (subject basins), `vocabulary.md` (anchors + homonyms).

**Standard adopted: MCP Resources.** Trinity exposes each memory file as a readable MCP Resource (URI: `trinity://memories/<file>`). Any MCP-compatible harness lists these at session start and the agent reads on demand. This is the v2 leverage point: a Claude Code session with Trinity loaded sees the lens BEFORE the user types anything.

### Layer 3: Moves (procedural)

> **Note on naming:** internally Trinity calls this layer **moves** — the user's repeatable plays that survived eval. Externally Trinity exports them as **SKILL.md** files for interop. "Move" emphasizes the action-shape; "skill" emphasizes the marketplace-shape. Both refer to the same artifact.

Located at `~/.trinity/moves/<slug>/SKILL.md`. The directory contract follows agentskills.io exactly — YAML frontmatter (required: `name`, `description`) + markdown body, optional `tools` whitelist, no internal routing prescribed.

**Trinity-specific frontmatter extensions** (custom fields are explicitly allowed by the SKILL.md spec and ignored by other tools):

```yaml
---
name: tighten-after-bullet-list
description: |
  When the model returns a 5+ item bulleted list, compress to a 2-3
  sentence paragraph capturing only the load-bearing claims.
trinity_lens_score: 0.84
trinity_promoted_from: ["r_001", "r_042", "r_117"]   # rejection ids
trinity_eval_baseline: 0.79
trinity_eval_runs: 6
trinity_basin_id: b03
trinity_promoted_at: "2026-05-23T14:22:00Z"
trinity_demoted_at: null
---

(markdown body — the actual move)
```

**The promotion gate** (the spec's load-bearing claim):

A move only lands in `~/.trinity/moves/` when:

1. **Cheap pre-filter passes** — basin similarity ≥ 0.7 to ≥ 3 accepted rejection-pairs (the move stays within the user's accepted patterns).
2. **Expensive eval passes** — chairman scores the candidate against the rejection corpus; score ≥ `trinity_eval_baseline` (set at first promotion; tracks personal best).

Both must pass. A move that drifts below baseline on a later dream cycle gets demoted (sets `trinity_demoted_at`, moves to `~/.trinity/moves/archive/`). Demotion is not deletion — the move file persists with the demotion reason logged in the body.

### Layer 4: Lens (preferential)

The geometry across all of the above. Lives at `~/.trinity/memories/` already; v2 also exposes it via **AGENTS.md** at `~/.trinity/AGENTS.md`.

**Standard adopted: AGENTS.md.** Codex CLI, Cursor, and Cline all read AGENTS.md natively. Trinity generates AGENTS.md from the lens on every `dream` cycle so non-MCP harnesses see the lens too. AGENTS.md is the human-readable + agent-readable union; the MCP Resources path is the structured one.

**AGENTS.md structure** (generated by `dream`):

```markdown
---
trinity_generated_from: lens.md
trinity_lens_version: <hash>
trinity_generated_at: <iso>
---

# Your taste, ported

(One-paragraph identity from core.md.)

## Tensions you've consistently picked

- **Pole A vs Pole B** — when X happens, you privilege A. Evidence:
  [r_001], [r_042].
- ...

## Vocabulary

- `term` — you mean X, not Y. See [memory_xyz].

## Active moves

- [tighten-after-bullet-list] — see `moves/tighten-after-bullet-list/`.
- ...
```

## The three adopted standards

| Standard | Trinity layer | URI / location | Trinity extension fields |
|---|---|---|---|
| **[SKILL.md](https://agentskills.io/specification)** | Moves (procedural) | `~/.trinity/moves/<slug>/SKILL.md` | `trinity_lens_score`, `trinity_promoted_from`, `trinity_eval_baseline`, `trinity_eval_runs`, `trinity_basin_id`, `trinity_promoted_at`, `trinity_demoted_at` |
| **[AGENTS.md](https://github.com/agentsmd/agents.md)** | Lens (preferential) | `~/.trinity/AGENTS.md` | `trinity_generated_from`, `trinity_lens_version`, `trinity_generated_at` |
| **[MCP](https://modelcontextprotocol.io)** Resources + Prompts + Tools | All layers | `trinity://memories/<file>`, `trinity://moves/<slug>`, `trinity://prompts/<name>` | Native — uses MCP primitives without extension |

All three are markdown + YAML frontmatter throughout. Custom frontmatter fields are explicitly allowed by SKILL.md and ignored by tools that don't recognize them. Reading a Trinity-shaped SKILL.md in Cursor (which doesn't know about `trinity_lens_score`) still works — the score is just hidden.

## Eval-gated promotion — the Bayesian gate (the wedge)

This is the load-bearing architectural claim. Skill marketplaces ship flat directories of curated procedures. Trinity ships a hierarchy with **Bayesian-gated promotion** between layers: cheap priors filter most candidates, expensive likelihood evaluates the survivors, and live posterior continuously re-validates against actual usage.

The framing matters because the alternative ("always run the chairman eval on every candidate") is either ceremonial (skipped because it would make dream weekly) or computationally prohibitive (10+ minutes per cycle, ~200 corpus items needed for statistical power). Tiering scales sub-linearly with candidate volume because each tier filters the next.

### The promotion loop

1. **`dream` proposes candidates** at the end of each cycle:
   - New memories (extracted facts)
   - Memories→moves promotions (repeated successful patterns)
   - Lens updates (new tensions, vocab terms, basin reshapings)
2. **Each candidate passes through the four-tier gate** below.
3. **Trinity commits surviving candidates** to their respective layers.
4. **Trinity logs rejected candidates** at `~/.trinity/dream_rejections.jsonl` with `why_rejected` + which tier rejected them. Rejection is not failure — it's the gate working.
5. **Active moves continuously update their posterior** via T4 below; drift triggers demotion.

### The four-tier Bayesian gate

Read top-to-bottom as **prior → likelihood → posterior**. Each tier runs only on candidates surviving the previous one.

| Tier | Role | Cost | What it checks | Pass criterion |
|---|---|---|---|---|
| **T1** prior (lexical) | Cheap structural similarity | ~1ms | n-gram overlap with accepted patterns in the candidate's claimed basin | Jaccard ≥ 0.3 vs ≥ 3 accepted patterns |
| **T2** prior (embedding) | Geometric basin membership | ~10ms | Cosine similarity of candidate's embedding vs basin centroid | cos ≥ 0.7 to ≥ 1 accepted basin |
| **T3** likelihood (chairman) | Score against personalized rejection corpus | ~30s | Chairman runs the candidate against rejection items; scores via lens | score ≥ `trinity_eval_baseline` (set at first promotion; tracks personal best) |
| **T4** posterior (live A/B) | Real-world utility | free (side-effect of usage) | When this move was active in a chairman call, did the council win? Rolling N-call win-rate. | win-rate ≥ baseline over rolling N calls |

**T1+T2 are the prior** — cheap, structural, runs on 100% of candidates. Filters ~70-80%.
**T3 is the high-fidelity likelihood** — expensive, definitive, runs on the surviving ~20-30%.
**T4 is the empirical posterior** — free as a side-effect of councils, continuously re-validates active moves against actual usage.

A move that survives all four is: structurally similar to your taste **and** scores well on your rejection corpus **and** demonstrably improves your actual council outcomes. A move that fails any tier loses its "active" status with the failure reason recorded.

### Why T4 is the wedge no one else has

Live A/B requires a verdict on each call. Most systems need explicit user thumbs-up/thumbs-down to learn — which is exactly the feedback loop Trinity retired (chairman pick replaced ratings).

**Trinity's T4 doesn't need an explicit user verdict** because the chairman's pick — conditioned on the lens — IS the verdict. When a move was active during a council, T4 reads whether the chairman picked the response that used the move. The lens makes this a personalized signal; the cross-provider corpus makes it non-replicable for any tool that can't read across labs. **No flat skill marketplace can build T4 without a cross-provider preference signal.**

### Demotion (the regression guard)

Every dream cycle re-runs T1 + T2 against all currently-active moves and updates the T4 rolling win-rate. A move gets demoted when:

- **T1/T2 drift**: candidate's basin shifted under it (the user's accepted patterns moved); OR
- **T3 re-eval failure**: re-run T3 on a sampled corpus item shows score < baseline for ≥ 3 consecutive cycles; OR
- **T4 posterior drift**: rolling win-rate drops below baseline over the last N calls.

Demotion writes:

- `trinity_demoted_at` in the SKILL.md frontmatter
- `trinity_demoted_by_tier` naming which tier triggered the demotion
- `~/.trinity/dream_demotions.jsonl` entry with `why_demoted` + the failing scores
- The move file moves to `~/.trinity/moves/archive/<slug>/`

The archive is preserved so demotion is debuggable. A user inspecting "why did this move stop firing?" can read the archive entry and see whether it was structural drift (T1/T2), corpus-evidence drift (T3), or real-world drift (T4) — each tier's signal tells a different story.

## Layer-by-layer JSON schemas

The v1 schemas survive — they describe the council-outcome / rejection-signal / eval-set surface. v2 adds two new schemas for the move + dream-rejection surface.

| File | Schema | Purpose |
|------|--------|---------|
| `~/.trinity/council_outcomes/council_<hash>.json` | [`council_outcome.schema.json`](../schemas/council_outcome.schema.json) | One multi-model run + chairman synthesis. Unchanged from v1. |
| `~/.trinity/me/rejections.jsonl` | [`rejection_signal.schema.json`](../schemas/rejection_signal.schema.json) | Labeled (prompt, response, rejection_type) triples. Unchanged from v1. |
| `~/.trinity/evals/eval_<hash>.json` | [`eval_set.schema.json`](../schemas/eval_set.schema.json) | Personalized eval suite. Unchanged from v1. |
| `~/.trinity/moves/<slug>/SKILL.md` | SKILL.md spec + Trinity extension frontmatter (this doc) | Promoted moves. New in v2. |
| `~/.trinity/dream_rejections.jsonl` | [`dream_rejection.schema.json`](../schemas/dream_rejection.schema.json) | Candidates the eval gate rejected, with `why_rejected`. New in v2. |
| `~/.trinity/dream_demotions.jsonl` | [`dream_demotion.schema.json`](../schemas/dream_demotion.schema.json) | Moves that drifted below baseline and got archived. New in v2. |

## The four implicit-rejection signal types (unchanged from v1)

Trinity mines four rejection labels from turn-pair gaps:

| Type | What the user did | Validator (in `me/turn_pairs.py`) |
|------|-------------------|-----------------------------------|
| `REFRAME` | Substituted a different frame entirely | Substituted frame must persist into next user turn |
| `COMPRESSION` | Wanted the answer shorter | User text word count ≤ model text / 10 |
| `REDIRECT` | Wanted a structurally different output | Model text was multi-part (numbered/bulleted/multi-sentence) |
| `SHARPENING` | Wanted more precision on same topic | User text shares ≥2 keywords with model text |

These labels carry through into move provenance — a move's `trinity_promoted_from` list points at the rejection-signal IDs that justified the promotion, so a user inspecting a move can see "this exists because of these 3 specific rejections."

## Obsidian compatibility (a consequence, not a feature)

Once Trinity is markdown + YAML frontmatter + wikilinks throughout:

1. **Frontmatter** — already native to Obsidian; Trinity already writes it.
2. **Wikilinks** — Trinity uses `[[r_001]]` to point moves back at the rejection-pairs that justified them; Obsidian renders them as a graph. Same syntax, two readers.
3. **Tags** — `#preference/reframe`, `#move/active`, `#move/archived` for typed categorization. Obsidian filters by them; Trinity's lens-discovery groups by them.
4. **Point Obsidian at `~/.trinity/`** — or point Trinity at an existing Obsidian vault via the `--vault` config flag. The substrate IS the vault.

Obsidian compatibility isn't a feature line — it's a consequence of the standards work. Users who want the graph view get it for free.

## Adopting this in your tool

1. **Read Trinity's lens.** Either through MCP Resources (`trinity://memories/lens.md`) or by reading `~/.trinity/AGENTS.md` directly. Both formats stay in sync via `dream`.
2. **Contribute rejection signal.** Append a record to `~/.trinity/me/rejections.jsonl` following [`rejection_signal.schema.json`](../schemas/rejection_signal.schema.json). Trinity's lens-build picks it up on the next cycle.
3. **Contribute candidate moves.** Drop a SKILL.md file into `~/.trinity/moves/<your-slug>/`. Trinity's next dream cycle runs it through the eval gate; if it passes, it goes live. If not, it lands in `dream_rejections.jsonl` with the `why_rejected`.
4. **Read promoted moves.** Either via MCP Resources or by listing `~/.trinity/moves/`. The SKILL.md format works in Claude Code, Cursor, Codex CLI, Cline, Continue, and 25+ other agent tools natively.
5. **Don't invent a parallel format.** If your tool needs a field Trinity doesn't have, add a `<your_tool>_*` frontmatter field. SKILL.md's spec explicitly supports custom fields.

## Reference implementation

Trinity Local itself is the reference. The canonical writers:

- `src/trinity_local/council_runtime.py::save_council_outcome` — produces `council_outcomes/*.json`
- `src/trinity_local/me/turn_pairs.py::save_rejections` — produces `rejections.jsonl`
- `src/trinity_local/evals/builder.py::save_eval_set` — produces `evals/*.json`
- `src/trinity_local/moves/*` — produces `moves/<slug>/SKILL.md` (NEW in v2)
- `src/trinity_local/dream.py::propose_and_gate` — runs the promotion loop (extended in v2)

Schemas are validated against real on-disk data in `tests/test_preference_corpus_schemas.py`. If a Trinity write doesn't match its schema, that test fails — so the schema can't drift from the reference implementation silently.

## Versioning

v1 (May 14, 2026) — council outcome / rejection signal / eval set schemas; structural lock.
v2 (May 26, 2026) — three-standard adoption (SKILL.md + AGENTS.md + MCP); adds move / dream-rejection / dream-demotion schemas + the Bayesian four-tier gate. v1 schemas survive unchanged; v2 is purely additive.

v2 is structural; backward-compatible additions don't bump the version, removals would.

## Distribution

Trinity ships via **[`uvx`](https://github.com/astral-sh/uv)** (Astral's `uv`-based PyPI runner) as the canonical install path. `uvx` installs into an isolated venv on first run, auto-checks for newer versions on subsequent invocations, and leaves no global Python pollution. The substrate at `~/.trinity/` is the engine's only durable state — `uvx` upgrades reach it without migration steps.

One-line registration per harness:

```bash
# Claude Code / Claude Desktop
claude mcp add trinity-local --command "uvx trinity-local --mcp"

# Codex CLI — pinned in ~/.codex/config.toml
[mcp.trinity-local]
command = "uvx"
args = ["trinity-local", "--mcp"]

# Cursor / Cline / Continue — paste into their MCP config UI
# command: uvx
# args: ["trinity-local", "--mcp"]
```

No `pip install` step runs in the user's environment. No version-pin drift. The pip distribution lives at `pypi.org/project/trinity-local/` and remains the secondary install path for users who prefer it (`pip install trinity-local`); the substrate spec is identical for both.

Updates: `uvx` checks PyPI for newer versions on each invocation. To pin a known-good version: `uvx trinity-local==1.7.11 --mcp`. The `trinity-local update` CLI verb prints the current version, latest available, and the one-line bump command — usable from inside any harness.

The Chrome extension (capture + dispatch) ships independently via `chrome://extensions` Load Unpacked from `browser-extension/`. The extension generates harness-specific paste-in snippets (Phase A), so the user doesn't have to know which harness they're in.

## License

The schemas + this spec are CC0 — adopt them, fork them, embed them in commercial products. The point is interop, not protection.
