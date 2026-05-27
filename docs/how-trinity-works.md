---
class: live
---

# How Trinity works

> **Own your taste — Trinity picks the answer you would have picked.**

Trinity is a cross-provider memory layer. It reads the transcripts you already have on your machine — from Claude Code, Codex CLI, Antigravity, Cursor, plus claude.ai / chatgpt.com / Gemini — and extracts the pattern in how you rephrase, judge, and decide. When you ask a hard question, all three frontier providers answer in parallel; the chairman synthesizes through your lens and picks the answer you would have picked.

This doc walks the pipeline end-to-end. If you want the install path, see [README](../README.md). If you want the on-disk contract, see [`three-tier-architecture.md`](three-tier-architecture.md).

## The category — and why no lab can ship it

Claude can't recommend ChatGPT. OpenAI can't recommend Claude. Google can't recommend either. The three frontier labs are commercially prevented from looking across each other's traffic.

That asymmetry is the moat. Trinity reads your transcripts from all three locally and learns one model of *you*. Anyone outside the labs can build this layer; no lab can. The architectural ideas — recursive gates, file-based memory, dreaming as out-of-band curation — are reproducible. The cross-provider corpus isn't.

## Where your transcripts come from (4 sources, all local)

| Source | How Trinity gets to it |
|---|---|
| **Claude Code / Codex / Antigravity / Cursor** | Each CLI writes session logs under `~/.claude/projects/`, `~/.codex/sessions/`, etc. Trinity walks them directly. |
| **claude.ai / chatgpt.com / gemini.google.com** | The Chrome extension hooks the XHR responses on those tabs and posts the conversation JSON to a local Native-Messaging host. Files land in `~/.trinity/conversations/`. No upload, no listening port. |
| **Bulk exports** (Claude.ai webapp export, ChatGPT export zip, Gemini Takeout) | `trinity-local import-export <path>` auto-detects the format and ingests. Claude.ai users: Settings → Privacy → Export data. |
| **Provider-side memory loop** | The agent inside Claude Code / Codex / Cursor sees your full conversation history on its side. The `import_provider_memory` MCP tool lets it pipe extracted tensions or rejections to Trinity directly — no scraping, no re-ingest. |

**Trust boundary on source #4.** The provider-side loop trusts the agent inside the harness to extract honestly. A compromised agent could inject fabricated tensions or rejections. Mitigations: the same dedup logic catches duplicates, and the ≥3-basin lens-build threshold raises the bar (a poisoning attack needs to span unrelated topics to take). Single-basin signal is exploitable in principle.

Nothing ever leaves the machine. The MCP server, the embedding model (~140MB), the chairman calls — all run on your hardware or your existing CLI subscriptions.

## From files to embeddings (ingest → index → embed)

Each transcript turn becomes a `PromptNode` row in `~/.trinity/prompts/prompt_nodes.jsonl` — id, provider, role, text, parent_id, created_at. Consecutive nodes get paired into `TurnWindow` records (user → assistant pair) so the analyzer can see "what the model said, and what you said next."

Cursors in `~/.trinity/prompts/cursors.json` track the newest ingested node per source so re-runs are incremental — you can ingest a 50,000-turn corpus once and then top up each day in seconds.

Every node gets passed through `nomic-embed-text-v1.5` (cached locally via Hugging Face Hub, offline by default). If MLX isn't installed it falls back to a stable SHA-1 TF-IDF projection. Same dimensionality either way. This is the only "model" call in the ingest path — no LLM, pure vector math.

## Dream — the offline synthesis pass

`trinity-local dream` walks six phases (cross-reference [CLAUDE.md → glossary](../claude.md) for the verb/noun map):

**Phase 1 — Discover.** Find pairs of nodes across providers that are semantically the SAME question (cosine ≥ 0.85). That's how Trinity knows you asked "the same thing" of Claude AND Codex AND Gemini.

**Phase 2 — Topics / basins.** k-means over all embeddings → 20 "subject basins" written to `~/.trinity/memories/topics.json`. Each basin gets a centroid vector and the top-3 representative verbatim prompts. Basins are the substrate the lens grades against.

**Phase 2.5 — Vocabulary.** Why it matters downstream: without **homonym** resolution, the chairman applies wrong-context lens to context-shifted words ("shipped" = released vs delivered). Without **synonym** resolution, near-identical rejections split into separate tensions ("refine" vs "tighten") and never cross the ≥3-basin threshold the lens-build stage requires. Vocabulary is the dedup substrate the lens stage depends on.

**Phase 3 — Rejection signals.** For each TurnWindow where you turned around and asked a follow-up, extract WHAT you changed: REFRAME (different question), REDIRECT (different output shape), COMPRESSION (shorter), SHARPENING (more precise). These rejection records (`~/.trinity/me/rejections.jsonl`) are the empirical signal of your taste — the load-bearing input the chairman trains against.

**Phase 4 — Lens-build.** Synthesize the rejections into PAIRED TENSIONS in `~/.trinity/memories/lens.md`. On a working install: things like `mechanism inspection ↔ speculative inference under uncertainty`, `concrete specificity ↔ abstract pattern recognition`. A tension must span ≥3 basins to make the lens; otherwise it's preserved as "ordering" (topic-local preference) or dropped. That floor is why one weird question can't pollute the lens.

**Phase 5 — Distill.** One-paragraph `~/.trinity/core.md` — identity-level summary the chairman reads first at runtime. Drill-down to the other files happens on demand.

**Phase 6 — Moves substrate.** For each rejection, ask "is there a procedural pattern that would have prevented this?" — promote it through the 4-tier gate into `~/.trinity/moves/<slug>/SKILL.md`. Sub-phases 6a (T4 update from completed councils), 6b (promotion), 6c (demotion), 6d (T3↔T4 calibration — the self-correction loop).

### Phase 1.5 — Trajectory lens (planned, see [#182](https://github.com/vishigondi/trinity-local/issues/182))

Stage 0 today extracts preferences from **single adjacent turn-pairs** — synchronic signal. The trajectory lens extends this to **arcs across multiple turns within a thread** — diachronic signal. If you pulled a conversation toward concrete examples three times across ten turns, that's a directional preference Stage 0 can't see.

This is an asymmetric advantage over Anthropic's Auto-Dream (which curates *within-session* memory) and over the synchronic-only rejection signal. Roadmap target: ship after schema versioning ([#183](https://github.com/vishigondi/trinity-local/issues/183)) so trajectory records can migrate cleanly.

## The 4-tier Bayesian gate — what makes it scale

The gate isn't a single chairman call per candidate. It's four tiers running in priority order, cheap first, expensive last. Every candidate move passes through T1 → T2 → T3 → T4; failure at any tier short-circuits the rest. The throughput math is the point:

| Tier | Cost | What it checks | Typical failure mode |
|---|---|---|---|
| **T1 lexical** | ~1ms | Word n-gram Jaccard vs accepted patterns in the candidate's basin | Candidate is lexically alien — its surface words don't overlap with patterns the user has accepted before |
| **T2 embedding** | ~10ms | Cosine similarity of candidate embedding vs basin centroid | Candidate isn't really in the basin it claims — wrong topic, semantically distant |
| **T3 chairman** | ~30s | Chairman scores the candidate against your `lens.md` tensions for that basin | Move is in the right basin and lexically valid but wouldn't actually have addressed the rejection it claims to fix |
| **T4 posterior** | free (state) | Beta-Binomial posterior of `alpha/(alpha+beta)` from actual council usage | Move has drifted in production — won followers early, stopped helping. Demotion fires. |

Without tiering, 20 candidates × 30s each = 10-minute dreams. With tiering, most candidates die at T1 or T2 (the free tiers) and a typical dream sees only the survivors hit the chairman. T3 is the throughput bottleneck; T1/T2 exist to make sure it's the only one.

T3 reads your **lens tensions as the grading rubric**, not as background context — grading against a lens is different from grading in the presence of one. T4's demotion rate feeds back into T3 (Phase 6d): basins where the chairman's picks keep failing in production get a higher promotion bar next cycle. The gate self-corrects.

The gate also applies to the **lens itself**: tensions whose claimed basins don't lexically or semantically resonate with the basin's content get narrowed or archived. The kernel applying to its own substrate.

## What you end up with

After a few dream cycles, your `~/.trinity/` looks like:

```
~/.trinity/
├── core.md                       ← one paragraph: who you are
├── memories/
│   ├── lens.md                   ← paired tensions: how you decide
│   ├── topics.json               ← 20 subject basins + centroids
│   └── vocabulary.md             ← homonyms + synonyms
├── moves/
│   ├── <slug>/SKILL.md           ← one procedural pattern per dir
│   └── archive/                  ← demoted moves preserved
├── scoreboard/
│   ├── picks.json                ← extracted "claude wins on REFRAME" rules
│   └── routing.json              ← per-task-type win-rate
└── me/
    └── rejections.jsonl          ← the empirical training corpus
```

The folder is the API. Everything in it is human-readable Markdown or JSON. Trinity disappearing tomorrow leaves your taste capture intact.

## Skills, moves — same files, different names

Trinity calls them **moves** internally because they're patterns you repeatedly accepted, not capabilities the model can run. The physical file format is **SKILL.md** (Anthropic's [agentskills.io](https://agentskills.io) spec) because that's what the agent harnesses already know how to read at runtime.

So a "move" is a logical concept in Trinity's code (a `Move` dataclass passing through the 4-tier gate); a "SKILL.md" is the physical file on disk with `trinity_basin_id`, `trinity_eval_baseline`, `trinity_alpha` / `trinity_beta` frontmatter. Same thing at two abstraction levels.

## Runtime — using Trinity

You drop a hard question into any harness (Claude Code, Codex, Cursor, Antigravity). The agent there sees Trinity registered as an MCP server and calls one of <!-- canonical:mcp_tool_count -->8<!-- /canonical --> MCP tools. The three that matter most:

- **`ask(query)`** — the cheap 90% path. Pulls a high-trust extracted pick if one exists ("looks like a COMPRESSION task → codex wins on those for you"). Returns a single answer.
- **`run_council(task)`** — the flagship. Dispatches the question to Claude + Codex + Gemini in parallel, collects three responses, runs chairman synthesis. The chairman reads `core.md` first, drills to `lens.md` if it needs to weigh tensions, and emits a Routing JSON: agreed claims, disagreed claims, winner, why. **The chairman's job is to pick the answer you would have picked** — that's what the lens is for.
- **`get_persona()`** — hands the lens to the agent at session handshake so it can tailor responses without an MCP round-trip per call.

## The eval surface — score any model against YOUR rejections

When Claude 5 or GPT-5.5 lands, the question isn't "how does it score on MMLU." It's "does this new model handle MY rejections better than the previous one?" Trinity ships the loop:

```
~/.trinity/me/rejections.jsonl         (your empirical preferences)
              │
              ▼
   trinity-local eval-build            (corpus → eval_set)
              │
              ▼
   ~/.trinity/evals/<set_id>/
              │
              ▼
   trinity-local eval-run --provider <new-model>
              │
              ▼
   per-axis scores: REFRAME, REDIRECT, COMPRESSION, SHARPENING
              │
              ▼
   trinity-local eval-show --compare    (leaderboard)
```

The eval is **structurally asymmetric** in your favor: only Trinity sees your cross-provider rejection signal. A public benchmark can rank models on average user behavior; Trinity's eval ranks them on *you*. The same architecture that makes the corpus unfakable also makes the eval personal.

## When does dream run

**Today: manual.** You run `trinity-local dream` when you want a refresh. The launchpad surfaces a "lens is stale" indicator when the rejection-corpus delta vs the last dream crosses a threshold.

**Roadmap: auto-trigger.** Mirroring Anthropic's Auto-Dream cadence (24h + 5-sessions) plus a rejection-corpus-delta trigger. The [CLAUDE.md → Auto-Dream coexistence](../claude.md) section covers the positioning: same primitive (offline synthesis from session transcripts), different scope (Trinity is cross-provider; Auto-Dream is single-provider). Same idea, asymmetric data access.

## Schema versioning — today and tomorrow

**Today:** `~/.trinity/` has no explicit version file. Schema growth has been additive-only (new fields default to absent; old code ignores fields it doesn't know). This has held for ~6 months of post-launch evolution but has obvious limits.

**Roadmap ([#183](https://github.com/vishigondi/trinity-local/issues/183)):** `.trinity-version` file at the root; per-shape schema versions registered for PromptNode / RejectionSignal / Move / CouncilOutcome / DreamCalibration; a migration runner that fires on first launch under a new binary. Targeted before any breaking change.

## The closed loop — how Trinity gets better

Three feedback edges run continuously:

1. **Lens trains the chairman.** When the chairman synthesizes a council, it grades responses against your tensions — not generic axes. The lens IS the rubric.
2. **Chairman's verdict trains the lens.** Council outcomes feed back: basins where chairman picks keep getting demoted trigger calibration; T3's bar for that basin gets raised next dream.
3. **Gate over the lens.** Same T1/T2 primitives that gate moves also gate the lens itself — tensions claiming basins they can't resonate with get archived. The kernel applies to its own substrate.

The taste you build with Trinity is the persistent thing across model generations. When the next frontier model ships, your lens still grades it. That's the layer this thing is.

---

**Related reading:**

- [README](../README.md) — install + the 30-second pitch
- [CLAUDE.md](../claude.md) — internal architecture, glossary, the 200-line discipline
- [`three-tier-architecture.md`](three-tier-architecture.md) — on-disk contract (MCP server / pip engine / Chrome extension)
- [`PREFERENCE_CORPUS_SPEC.md`](PREFERENCE_CORPUS_SPEC.md) — the rejection-corpus + Bayesian gate spec
- [`scale-plan.md`](scale-plan.md) — long-form roadmap
