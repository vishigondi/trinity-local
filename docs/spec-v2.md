# Trinity v2 — held spec (foundation in v1, productization later)

> Status: **spec only**, not shipping in v1. The v1 foundation (folder schema lock,
> stable MCP contract, Routing JSON canonical format, embeddings layer, lens-discovery
> pipeline) is laid so v2 can land without breaking v1 users.
>
> The thesis: v1 ships a *local evidence ledger*. v2 turns it into a *learned coordinator*
> — Trinity gets smarter at routing AND synthesis the more you use it, with the slow
> updates running on your hardware on your schedule.

## The narrative arc

| Version | Pitch in one line | Status |
|---|---|---|
| v1.0 | *Own your memories — three labs, one ledger, your taste* | Ships May 13–15 |
| v1.1 | *Your taste becomes a story you can share* (narrative video pipeline) | Week 8 |
| v1.2 | *Trinity tells you what to learn next* (Coach Lens / `trinity evolve`) | Week 12 |
| v2.0 | *Your local chairman replaces the frontier one for your kinds of questions* | Month 4–6 |
| v2.1+ | *Federated taste — teams share what they trust* | Month 6+ |

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
- New command: `trinity-local evolve` (or `me-evolve` for naming parity with `me-build`).
- Logic: walk recent councils, find ones where the user picked a chairman-disagreed answer,
  surface the *runner-up* and the chairman's `why_matters`. Render as a card.
- UI surface: launchpad gets a "What Trinity wants you to try next" section.

Foundation in v1: the `disagreed_claims` + `routing_lesson` + `why_matters` fields of the
Routing JSON are already canonical. The personal_routing_table already has counter-evidence
when chairman vs user disagree. v2 just renders it.

## v1.2 — Trinity Pro hosted tier ($15/mo)

**Pitch:** *"You bring your own subscriptions for the council members. We host the
chairman + provide cross-machine sync for your `/me` lens. Stays the same in price as one
ChatGPT Plus."*

**What's hosted:**
- Council orchestration via Trinity-managed API proxies (so the user doesn't pay per-call
  for the chairman call when their plan caps out).
- Trinity-managed embedding compute (so big corpora don't melt the user's Mac).
- Cross-machine `/me` lens sync via E2E encryption.

**What's NOT hosted (the privacy line):**
- Prompts. Still locally dispatched, locally synthesized when local capacity allows.
- The Routing JSON ledger. Still in `~/.trinity/`. Pro sync is opt-in per machine.
- Member outputs. Same.

**Cost basis:** at $15/mo with current frontier API economics, hosted chairman call costs
amortize at roughly 200 councils/month per user before margin. Most users do <50.
Cross-machine sync is mostly free (small JSON + encrypted blob).

**Pricing note:** v1 spec had $12; bumped to $15 — see `spec-v1.md` disagreement #6.

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
domain tags inferable from `task_kind`. Pair-mining sources:
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
