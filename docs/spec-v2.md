---
class: historical
---

# Trinity v2 — SUNSET (superseded by v1.5)

> ## ⚠️ Status: superseded by `docs/spec-v1.5.md` as of 2026-05-11.
>
> **The trained-coordinator architecture in this document is no longer the planned
> next-trajectory.** v1.5 achieves the same goals via context engineering — no
> training infrastructure, no 4–8 weeks of GPU time, no MLX fine-tune loop. This
> document is preserved as architectural-decision history, not as the active spec.
>
> **Code substrate deleted 2026-05-20 (tick 57):** the v2 data-schema modules
> `src/trinity_local/training_schema.py` (262 LOC) + `src/trinity_local/feature_extractors.py`
> (261 LOC) had zero callers across src/ and tests/ after the v1.5 pivot. Deleted
> to reduce dead-code surface; reachable via git history if v1.5 hits a quality
> ceiling and a reopen needs the schema definitions. Same precedent as the Loop
> Constitution substrate removal (claude.md L857). See `retired_names.py` for the
> registry entries (`training_schema`, `feature_extractors`).
>
> ### Why we pivoted
>
> Re-reading Sakana's TRINITY paper (arXiv:2512.04388, ICLR 2026) end-to-end, the
> 3B vs 7B Conductor ablation (Figure 7) shows both sizes find the **same optimal
> routing decision**. The 7B wins on **prompt-engineering quality**, not on routing.
> Their own conclusion: *"the increased natural-language capabilities of larger and
> newer base models directly translate into more intelligent prompt engineering."*
>
> A flagship model (Claude Opus, GPT-5, Gemini 2.5 Pro) writes far better natural-
> language subtasks than any 7B trained from scratch. Combined with cortex-extracted
> routing rules (consolidated offline by a flagship pass over the user's council
> outcomes), the Conductor doesn't need to learn routing — the cortex rules already
> encode it. So a flagship-as-Conductor with cortex context outperforms a hypothetical
> local 7B Conductor on the user's specific task distribution.
>
> The world is also changing weekly. Trained Conductors decay when models update
> (Claude 4.8 ships and the trained routing decisions for Claude 4.7 are stale).
> Cortex extraction via flagship re-consolidates on demand. No retraining cost.
> Adaptation cost = one flagship pass over the last N outcomes.
>
> The shortest path to *"SOTA for you + your taste + your existing subs + saves
> cost"* is therefore **retrieval + cortex extraction + flagship-as-Conductor**, not
> a trained 7B. v1.5 ships that path. See `docs/spec-v1.5.md`.
>
> ### What's absorbed into v1.5
>
> The architectural ideas in this document carry over — just implemented via context
> engineering instead of weights:
>
> | v2 idea | How v1.5 implements it |
> |---|---|
> | Three-role action space (Thinker/Worker/Verifier) | The `plan_and_execute` Conductor's three-list output `(model_id, subtasks, access_list)` IS this — role is encoded in the subtask prompt |
> | Per-member prompt formulation | Flagship Conductor writes per-member subtask prompts using cortex-extracted "successful prompt templates" per provider per basin |
> | Recursive verification | `plan_and_execute` verification step — Conductor reviews output, replans if needed |
> | Hippocampus + cortex collaboration | Cortex rules + hippocampus kNN both fire at query time; rule is the primary signal, episodes are calibration |
> | Active learning via surprise score | Cortex consolidation flags basins where lens contradicts the extracted rule for re-review |
> | Adversarial held-out eval | Lens basins serve this role — if cortex rule contradicts user's known lens, flag |
>
> ### What's deferred (the trained-coordinator path stays open if needed)
>
> If `ask` + `compare` + `plan_and_execute` + cortex consolidation hit a quality
> ceiling on real user data in v1.5, the trained-coordinator trajectory below reopens.
> At that point v1.0+v1.5 will have generated the labeled training data, and the
> infrastructure can be built on real signal rather than speculation. The whole
> document below stays here for that contingency.
>
> ### What's deprecated permanently
>
> - **Narrative video pipeline (former v1.1)** — me-card PNG is the v1.0 social object; richer
>   video animation is an explore-not-commit. Removed from the trajectory.
> - **Coach Lens / `trinity evolve` (former v1.2)** — folded into v1.5's cortex layer. The
>   extracted routing patterns ARE the coaching ("for this kind of question you prefer
>   Provider X because Y; runners-up have these failure modes").
> - **Hosted Pro tier, federated taste, team plans** — out of v1.5 scope. The local-first,
>   single-user, free-forever experience has to be overwhelmingly great first. Revisit
>   only after v1.5 has real usage data.
>
> ---
>
> ## Historical content preserved below (the trained-coordinator architecture)
>
> Everything that follows describes the trained-coordinator path. It is **not** the
> shipping plan. Read for context on why v1.5 chose flagship-as-Conductor instead.

## The narrative arc (historical — superseded by spec-v1.5)

| Version | Pitch in one line | Status |
|---|---|---|
| v1.0 | *Your taste, ported. Lives inside Claude Code, Codex CLI, Antigravity, and Cursor.* | Ships May 13–15 (pivoted 2026-05-16 from "Stop copy-pasting prompts. Own your context. Dream your core memories.") |
| v1.5 | *Trinity is what Claude Code reaches for* | **Ships June 3, 2026 (active spec)** |
| v1.1 (narrative video) | n/a | **deprecated** (me-card PNG is the v1 social object) |
| v1.2 (Coach Lens) | n/a | **absorbed into v1.5 cortex layer** |
| v2.0 (trained coordinator) | *Your local chairman replaces the frontier one* | **sunset — contingency path only** |
| v2.1+ (federated taste) | *Teams share what they trust* | **deprecated** |

**Original v2 thesis (no longer the plan):** v1 ships a *local evidence ledger*; v2 turns
it into a *learned coordinator* via local DPO fine-tune.

## The narrative arc

| Version | Pitch in one line | Status |
|---|---|---|
| v1.0 | *Your taste, ported. Lives inside Claude Code, Codex CLI, Antigravity, and Cursor.* | Ships May 13–15 (pivoted 2026-05-16 — see above table footnote) |
| v1.1 | *Your taste becomes a story you can share* (narrative video pipeline) | Week 8 |
| v1.2 | *Trinity tells you what to learn next* (Coach Lens / `trinity evolve`) | Week 12 |
| v2.0 | *Your local chairman replaces the frontier one for your kinds of questions* | Month 4–6 |
| v2.1+ | *Federated taste — teams share what they trust* | Month 6+ |

**Pricing:** undecided. v1 is free. Hosted capabilities below are described as
*capabilities*, not as paid tiers — the revenue model is a separate decision the user
hasn't made yet.

## v1.1 — narrative video pipeline (week 8)

**Pitch:** the radar chart was the v1 social object; the narrative video is the v1.1 one.
60–90 seconds of contradiction-and-resolution rendered from the user's own council
outcomes. Default private. Public toggle creates a permanent shareable URL with prominent
"made with Trinity" watermark. Each shared video is an acquisition asset.

**What's needed:**
- Template renderer: ffmpeg + a JSON template; pulls from `~/.trinity/me/lenses.json` +
  `~/.trinity/council_outcomes/*.json`. Outputs to `~/.trinity/videos/{nnnn}/manifest.json`
  + `output.mp4`.
- Privacy gate: video private by default; explicit `--publish` flag uploads to a Trinity-hosted
  CDN that requires a Pro account (because hosting costs money, not because we want the data).
- Audio: text-to-speech via the system `say` command on macOS; later upgrades to a model.
- Default story arc: *"on May 1 you preferred Codex for X; on May 8 you preferred Claude for
  similar X; here's the lens that emerged."*

Foundation already laid in v1: `me/lenses.json`, `council_outcomes/*.json`, the lens-discovery
pipeline, and the `share/` folder convention.

## v1.2 — Coach Lens (`trinity evolve`, week 12)

**Pitch:** Trinity stops being a passive ledger and becomes an active coach. It surfaces
*"you keep choosing X-style answers; the failure mode of X is Y; the answer that would have
pushed you past Y was hidden in this council you didn't notice."*

**What's needed:**
- New command: `trinity-local evolve` (or `lens-evolve` for naming parity with `lens-build`).
- Logic: walk recent councils, find ones where the user picked a chairman-disagreed answer,
  surface the *runner-up* and the chairman's `why_matters`. Render as a card.
- UI surface: launchpad gets a "What Trinity wants you to try next" section.

Foundation in v1: the `disagreed_claims` + `routing_lesson` + `why_matters` fields of the
Routing JSON are already canonical. The personal_routing_table already has counter-evidence
when chairman vs user disagree. v2 just renders it.

## Held capability — hosted chairman + cross-machine sync (no v1.2 pricing tier)

Description of the *capability* in case there's ever a revenue model. Not committed.

**What it would do:**
- Council orchestration via Trinity-managed API proxies (so the user doesn't pay per-call
  for the chairman call when their plan caps out).
- Trinity-managed embedding compute (so big corpora don't melt the user's Mac).
- Cross-machine `/me` lens sync via E2E encryption.

**What stays local (the privacy line, non-negotiable even if monetized later):**
- Prompts. Still locally dispatched, locally synthesized when local capacity allows.
- The Routing JSON ledger. Still in `~/.trinity/`. Any sync is opt-in per machine.
- Member outputs. Same.

**Status:** the user hasn't decided on a revenue model. Free-forever v1 buys time to
figure that out from real usage data, not from a launch-room pricing guess.

## v2.0 — Learned coordinator (Cortex)

This is the architecture you sketched: hippocampus + cortex via DPO + active learning.
Foundation:

```
Transcripts → extract pairs → DPO seed → Local Chairman v0
                                              ↓
Index (always live) ←──── retrieve ←─── New input → Chairman judges
                                              ↓
                Surprise score → flag for adjudication → new pair → queue
                                              ↓
                          Weekly re-DPO ← consolidation ← queue ≥ N
```

### Phase 0 — Corpus normalization
Already in v1: `~/.trinity/memory/prompt_nodes.jsonl` carries 18k+ normalized prompts with
domain tags inferable from `task_type`. Pair-mining sources:
- Explicit user verdicts from `~/.trinity/council_feedback.jsonl` (already 21+ entries).
- `outcome.metadata.user_verdict.user_winner` per persisted council outcome.
- Stage 0 turn-pair rejections from `~/.trinity/me/rejections.jsonl` (52 validated entries).

### Phase 1 — Pair extraction
- Source A: explicit verdicts (gold). Already structured.
- Source B: frontier model as candidate-pair miner (Claude Opus 4.7 / current frontier). New code: walks transcripts + proposes (chosen, rejected) pairs from observed user reactions.
- Source C: hand-labeling session (one-time ~500 pairs). UI in v2.0: `trinity-local label`.

Target: 2k–5k high-quality pairs before DPO seeds the local chairman. Stop adding source-C pairs once source-A overtakes by 5x.

### Phase 2 — Hippocampus (retrieval, already shipped)
v1 ships nomic-embed-text-v1.5 at 768d, 18k vectors, ~5ms numpy matmul retrieval. v2 adds:
- A `lens/geometry/` index keyed on PAIR vectors (not prompt vectors) — the chosen-minus-rejected delta.
- The scoring kernel from `lens/scorer.toml` (already a v1.1 file).

No FAISS — numpy is fine at this corpus size; revisit at 1M+ pairs.

### Phase 3 — Cortex (Qwen3-0.6B fine-tune via DPO)
- Local fine-tune via MLX on Apple Silicon. ~1hr per consolidation pass on a Mac Studio Ultra.
- DPO objective (not SFT, not RLHF). Pairs from Phase 1. Hold out 10–20% as eval.
- Model weights live in `~/.trinity/models/cortex-v{n}/`.
- Champion-challenger: old chairman stays live until new one beats it on held-out judgments.

### Phase 4 — Inference loop
1. New input arrives.
2. k-NN retrieve k=3–5 past pairs from `~/.trinity/lens/` (hippocampus).
3. Local cortex generates judgment with retrieved context as RAG.
4. Compute log-probability of retrieved precedent's actual user-verdict — that's the **surprise score** (OOD-ness).
5. Output: judgment + confidence + nearest precedent + surprise.

### Phase 5 — Active learning loop
- Surprise > threshold → flag for user adjudication.
- New (chairman prediction, user correction) pair lands in the queue.
- Cross-entropy is the **query selector**, not a trainer. Label budget spent only where the cortex is most uncertain.

This is Disagreement-Based Active Learning (Settles 2009).

### Phase 6 — Consolidation (cortical replay)
- Weekly, or when queue hits ~100 new pairs.
- Re-DPO the cortex on the full accumulated set.
- Watch eval-set performance. If it degrades → capacity gap (signal too rich for 0.6B) or overfitting.
- Champion-challenger gate before the new cortex serves production.

### Adversarial held-out (the user's added defense)
Pre-launch: pick 50 cases where your taste is non-obvious even to you (e.g., councils
where you reversed your initial reaction). Lock them away. Re-test every cortex version
against that set. **The only defense against your own taste echo chamber being reified
into weights.**

Lives at `~/.trinity/me/adversarial_holdout.jsonl`. v1 ships a placeholder; v2 fills it.

### Per-member prompt formulation

Parallel to the chairman replacement: learn what prompt formulation gets the best response
from each frontier member. Same DPO machinery, different objective:

- Pair format: `(prompt_variant_A, response_A, prompt_variant_B, response_B, member, user_winner_variant)`
- Source: ablation runs during v1 dogfood — same task, different system prompts per member, user picks the best one.
- Train per-member adapters that take (task) → (member-tailored prompt).

This is what the user meant by *"figure out which prompt to send to each model."*

## v2.1+ — Federated taste (Teams)

**Pitch:** team members share their `/me` lenses + Routing JSON outcomes; team chairman
learns from the collective. Personal lens stays private; only categorical labels + winner
counts cross the wire.

**What's needed:**
- E2E encryption layer (Pro tier already requires this).
- Team admin observability surface (which models the team trusts for what).
- Federated learning loop: per-user DPO updates → encrypted aggregation → team chairman update.

**Privacy:** team chairman trains on user CONSENT to contribute. Default off. Team can
operate with mixed consent (only consenting users' updates feed the team cortex).

## Foundations laid in v1 that v2 depends on (do NOT break these)

### Folder schema lock
- `~/.trinity/SCHEMA_VERSION` carries the v1 schema version.
- Future schema changes ship as one-shot migrations + bump the version.
- v2 adds new subdirs (`videos/`, `lens/`, `models/`); none rename existing.

### Routing JSON ledger format
- Canonical fields: `winner`, `runner_up`, `confidence`, `agreed_claims`, `disagreed_claims`
  (with `why_matters`), `provider_scores`, `routing_lesson`, `eval_seed`, `task_type`,
  `task_domain`, `user_likely_values`, `major_failure_mode`.
- v2 cortex training corpus = these fields, indexed.

### MCP stable contract
- The 3 spec tools (council/query_lens/add_pair → run_council/search_prompts/record_outcome)
  are the public stable contract. They keep their argument shapes forever.
- The 3 extended tools (route, get_council_status, get_persona) may evolve in v1.x but
  won't disappear without a deprecation cycle.

### Embedding pipeline
- nomic-embed-text-v1.5 at 768d is the v1 baseline.
- Cache lives at `~/.trinity/cache/embeddings.jsonl` — same key format will work for v2 pair
  vectors.

### Lens-discovery output shape
- `~/.trinity/me/lenses.json` + `orderings.json` + `rejections.jsonl` + `basins.json` are the
  taste-terminal-aligned outputs.
- v2 cortex prompts include these as RAG context for chairman judgments.

### Privacy posture
- Prompts never upload. Even Pro tier holds this line.
- v2 adversarial holdout + DPO training all run locally.

## What v2 explicitly does NOT do

- Replace frontier MEMBERS with a local model. Members stay frontier (the council's whole point is asking the best models). Only the CHAIRMAN gets a local trained variant.
- Train on raw transcripts. Distilled pairwise judgments only. Catastrophic-forgetting defense.
- Phone home. Federated taste (Teams) is opt-in per-update; even then, only encrypted aggregates leave the user's machine.
- Charge for v1 features in v2. Free forever stays free forever.

## Open questions for v2

These need decisions before v2 build starts. None block v1.

1. **Cortex model choice:** Qwen3-0.6B is the user's pick. Alternatives at 0.5–1B scale: Llama-3.2-1B, Phi-3.5-mini. Decision criteria: MLX runtime, multilingual coverage, base-model bias against the user's English-heavy corpus.
2. **Hand-labeling UI:** simple CLI prompt loop vs HTML pairwise picker. CLI ships in 2hr; HTML is better UX but takes a week.
3. **Per-member prompt-formulation training:** same DPO loop or separate RLAIF? RLAIF is simpler (no pairs needed; uses the response quality directly) but unstable. DPO needs ablation runs to source pairs. Start with DPO + manually-curated ablation set.
4. **When does Pro tier hosted chairman kick in?** Before or after local cortex graduates? Decision lean: Pro tier launches v1.2 (week 12) BEFORE cortex (month 4) — pricing model needs to exist first.

## Related work / concurrent ratification: Sakana TRINITY (ICLR 2026)

Sakana AI published *"TRINITY: An Evolved LLM Coordinator"* (arXiv:2512.04695, ICLR 2026) the
same week we're shipping. Independent validation of the core thesis — *a lightweight
coordinator over diverse LLMs beats monolithic scaling.* Their numbers:

| | Score |
|---|---|
| Sakana TRINITY (0.6B SLM + 10K head, sep-CMA-ES trained) | **86.2% pass@1 LiveCodeBench** |
| GPT-5 | 83.8% |
| Gemini 2.5-Pro | 67.2% |
| Claude-4-Sonnet | 67.0% |

Three concrete ideas worth absorbing into v2.

### A. Three-role action space (Thinker / Worker / Verifier)

Their paper's mechanism: at each turn, a compact SLM reads the full transcript and a
lightweight head selects an LLM + assigns it one of three roles:

- **Thinker** (strategize — re-frame the problem, propose plans)
- **Worker** (execute — implement the current plan)
- **Verifier** (evaluate — accept or reject the artifact)

The loop halts when Verifier accepts. The sequence isn't fixed —
`Thinker → Thinker → Worker → Verifier → Worker → Verifier` is normal if the trajectory
needs replanning.

**For our v2 inner loop**: replace the fixed `execute → verify → cull → re-verify → commit`
sequence with role-selection per iteration. Each iteration the local cortex picks a role
based on `state.history`; the action space matches the Sakana paper. Outer loop (frame)
stays separate because its timescale is different — outer reframes on model release or
drift, not per-iteration.

### B. sep-CMA-ES vs DPO for training the local chairman

Our v2 spec defaults to DPO (Direct Preference Optimization). The Sakana paper argues
gradient methods fail in our setting:

| Method | LCB | Why |
|---|---|---|
| REINFORCE (RL) | 0.253 | Low SNR under binary rewards; weak parameter coupling |
| SFT | 0.592 | Multi-turn label generation intractable: O(7⁴·3⁵) per question |
| Random Search | 0.374 | Logarithmic improvement, not linear |
| **sep-CMA-ES** | **0.615** | Derivative-free, diagonal covariance matches block-separable structure, linear improvement, only 1.5K–40K evaluations for ~10K parameters |

They don't compare DPO directly, but DPO is gradient-based on pairwise preferences — same
low-SNR + weak-coupling regime as REINFORCE. Worth evaluating sep-CMA-ES as our v2 cortex
training method, not just DPO. **Open question #1 in v2 (cortex training) gets sep-CMA-ES
added as the third option alongside DPO and SFT.**

### C. Per-member prompt formulation as a structural primitive

The Sakana paper's lightweight head selects *which* LLM AND *which* role. The role
selection acts as a learned prompt-formulation: a Thinker-flagged prompt to Claude gets
different scaffolding than a Worker-flagged prompt to Codex.

This is the *per-member prompt formulation* the user named in the prior session:
*"figure out which prompt to send to each model."* The mechanism is now concrete — train
the cortex to emit `(model_id, role, prompt_template)` per turn, where role selection
implicitly chooses the prompt shape.

**v2 work item**: the inner loop's per-iteration call should be
`(cortex_pick) → (model_id, role, scaffolded_prompt) → frontier_member_call`, not the
current `chairman_call(canned_prompt)`.

### What stays the same

- Outer/inner timescale separation (we ratified this with `council_5fbf909119830643`)
- `cull → re_verify → commit` non-negotiable from `council_7a770b8b78b6bd4e`
- Local-first, prompts never upload, free-forever — those are v1 commitments that v2
  inherits unchanged

### Name collision note

Sakana's "TRINITY" + our "Trinity Local" + same-week publication = inevitable conflation
on AI Twitter. Mitigated by audience differentiation:

- **Sakana TRINITY**: research coordinator hitting LiveCodeBench SOTA via sep-CMA-ES
- **Trinity Local**: consumer memory layer for polyharness users; local-first; free

The two names can coexist if our launch copy makes the audience boundary clear in the
hero. Captured in launch.md as a pre-empted FAQ.

## The user's mental model the v2 spec mirrors (verbatim)

> BrainML primitive → Your stack
> - Working memory (PFC) → KV cache / context window → Current prompt to chairman
> - Hippocampus → Retrieval index + online learner → Transcript corpus + pairwise pairs
> - Cortex → Trained small model weights → chairman after fine-tune

The two corrections the user made:

1. **Cross-entropy is a SELECTOR, not a trainer.** Use it to decide which cases need new
   labels. The new pairs are the actual training signal. (Architectural difference between
   RLHF and DPO + active learning.)

2. **Hippocampus and cortex don't compete at inference — they collaborate.** Retrieval
   primes the cortex with relevant context; the cortex generates conditioned on that
   context. The brain analogy: when you remember something, the hippocampus doesn't do the
   remembering — it cues the cortex to render it.

These two principles are the v2 architectural invariants.
