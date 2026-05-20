---
class: aspirational
---

# Trinity v1.5 — locked next-trajectory spec

> Status: **spec only, follows v1.0 ship.** Target: **ship June 3, 2026.**
>
> v1.5 is where the "SOTA for you + your taste + your subs + saves cost" pitch
> becomes literally true. v1.0 shipped the data pipe; v1.5 turns it into a routing
> product Claude Code reaches for.
>
> This spec supersedes the v1.1 / v1.2 / v2.0 trajectory in `docs/spec-v2.md`.
> The trained-coordinator path is sunset (see `docs/spec-v2.md` sunset header
> for why); v1.5's flagship-as-Conductor architecture achieves the same goal
> via context engineering, no training infrastructure required.

## The reframe

v1.0 shipped a launchpad-centric council product. **v1.5 inverts the primary
surface from launchpad to MCP.** Most real users won't open the launchpad —
they'll work inside Claude Code (or Codex CLI, or Gemini CLI) and the agent
will call Trinity when it needs:

- A second opinion from a different provider for the user's flavor of a question
- A way to route around a rate limit on its own subscription
- Access to a model it can't dispatch to directly (Codex from inside Claude Code, etc.)
- The user's taste-aware routing decision

The launchpad becomes "what Trinity has learned about you" — the dashboard.
The MCP tools are the actual product.

## Strategic positioning (post-Dreaming)

**v1.5's cortex consolidation is the local, cross-provider answer to Anthropic's
*Dreaming*** (shipped Dec 2025; see VentureBeat: *"Anthropic wants to own your
agents' memory, evals, and orchestration"*). Anthropic's stack:

| Anthropic feature | Trinity equivalent | What's different |
|---|---|---|
| **Dreaming** — agents consolidate past sessions into reusable lessons | **Cortex consolidation** — flagship extracts routing patterns per basin from accumulated council outcomes | Hosted on Anthropic infra vs. runs on your own subscription; single-provider vs. across Claude/GPT/Gemini; memory lives in Anthropic's storage vs. `~/.trinity/scoreboard/picks.json` |
| **Outcomes** — rubric-graded eval by a separate grader agent | **Lens** — pair-wise tension evaluation in a separate context | Anthropic-grader vs. user-taste-derived lens from `memories/lens.md` |
| **Multi-Agent Orchestration (MAO)** — specialist sub-agents with independent contexts | **Council** — Claude, GPT, Gemini in parallel, chairman synthesizes | Same-lab specialists vs. cross-lab council; Anthropic-owned vs. your-subs-owned |

Same architectural ideas; opposite trust models. Anthropic ships them inside a
runtime that locks you in (Albert: *"You're building an application for Macs —
you don't want to re-implement every detail of macOS"* → Anthropic's stated
goal is "the macOS of agents"). Trinity ships them in a way that keeps your
cognitive substrate yours.

The enterprise context that landed this week: MassMutual won't sign long-term
contracts with any single AI vendor for exactly this reason. ProgressiveRobot
is selling "Anthropic Agent Lock-In" risk audits. There is now a recognized
enterprise category called *vendor-neutral agent memory* — and Trinity is
structurally the simplest answer.

## The killer flow nobody else can offer

```
[User working in Claude Code, mid-refactor]
Claude (harness): I'll use mcp__trinity-local__ask to get a second opinion
                  on the migration strategy...
[Trinity: kNN finds 12 similar past queries; Codex won 9/12 for this user's
          "migration strategy" basin; pick says "Codex for impl-mode
          subroute"]
[Trinity dispatches one call to Codex]
Codex: <answer>
Claude: Codex suggests X. I'll proceed with that plus a safer rollback.

[10 minutes later, Claude's sub hits the daily rate limit]
Claude: I'm rate-limited. Continuing via Trinity...
[Trinity routes all subsequent ops to Codex/Gemini/local Qwen]
[User's work doesn't stop]
```

The labs can't ship this because none of them is allowed to route to a
competitor. The cross-provider rate-limit-dodge is the wedge in one sentence.

## The pitch (HN-ready, locked)

> *"Trinity is what Claude Code reaches for when it needs a different provider,
> a fresh perspective, or a way to dodge a rate limit. It routes through your
> existing subscriptions and local models, and learns at two levels — specific
> past decisions (hippocampus) and extracted patterns across them (cortex). It
> gets sharper, not slower, with use. Free, local, MIT."*

Five claims, each verifiable in the install:

1. **SOTA for YOU** — routes to the user's empirically-best model per question kind
2. **Captures YOUR taste** — kNN over your transcripts + cortex rules extracted from your councils
3. **Personalizes for YOU** — cortex consolidation distills routing rules per task type
4. **USES your existing subs** — dispatches via the CLIs you already pay for
5. **SAVES cost** — local models for easy subtasks, multi-call only when needed

**Pitch caveat — "and local models" is conditional on Week 3 dispatch
resilience.** If Ollama + MLX integration is wobbly at ship, **cut "and local
models" from the pitch.** Promising it and not nailing it is worse than not
promising it; the HN demo will be where we find out. "Your work continues on
Codex when Claude is rate-limited" is itself unbeatable even without the
local-model angle. Re-add to the pitch in v1.6 once stable.

## Architecture

### Two-tier memory (the hippocampus / cortex insight)

Brains don't kNN over raw episodes. They consolidate. Trinity should too.

```
TIER 1 — Hippocampus (episodic, fast write, slow recall)
├── ~/.trinity/prompts/prompt_nodes.jsonl       v1 — individual user prompts
├── ~/.trinity/prompts/turn_windows.jsonl       v1 — with surrounding context
└── ~/.trinity/council_outcomes/*.json         v1 — individual council decisions

TIER 2 — Cortex (semantic / procedural, slow write, fast recall)
├── ~/.trinity/memories/topics.json                  v1 — task-type clusters (cognitive: lens evidence map)
├── ~/.trinity/memories/lens.md                      v1 — taste tensions (cognitive)
├── ~/.trinity/scoreboard/picks.json    NEW — extracted model-selection rules per task_type (operational)
├── ~/.trinity/cortex/failure_modes.json       NEW — per-model failure patterns
└── ~/.trinity/cortex/successful_prompts.json  NEW — per-model good-prompt templates
```

**Hippocampus** stores episodes — specific past decisions. Fast to write
(`record_outcome` appends one file), slow to recall (need to embed-and-search
to find relevant ones).

**Cortex** stores extracted patterns — abstract rules across many episodes.
Slow to write (consolidation pass runs offline), fast to recall (single
basin-to-rule lookup at query time, ~5ms).

At query time both tiers fire — cortex provides the rule, hippocampus provides
the calibration examples. The rule generalizes; the episodes don't.

### Consolidation pass (cortical replay during "sleep")

A flagship model extracts routing patterns from accumulated council outcomes.
Runs offline.

```
For each basin in ~/.trinity/memories/topics.json:
  Gather all council_outcomes whose lens basin matches
  Send them to a flagship model with a prompt that asks for:
    1. Routing rule: primary + challenger + confidence + why (one sentence)
    2. Subroutes: keyword conditions that flip the winner
    3. Failure modes per losing provider (when they lose, HOW do they fail?)
    4. Successful prompt-shape patterns per winning provider
    5. Evidence decay: weight recent over old
  Write rule to ~/.trinity/scoreboard/picks.json keyed by basin_id
```

**Triggers:**
- Every 10 new councils — light pass, only the affected basin
- Nightly — full consolidation, via launchd or a cron job invoking `trinity-local consolidate` directly (the watch-loop CLI was retired pre-launch)
- On demand — `trinity-local consolidate`

**Cost:** ~10–20 flagship calls per nightly pass. Pennies. Runs on user's sub.

**Schema (cortex/routing_patterns.json entry):**
```json
{
  "basin_id": "concrete_shippable_vs_comprehensive_ideal",
  "consolidated_at": "2026-05-20T10:30:00Z",
  "n_episodes": 47,
  "task_types": ["system_design", "architecture_decision", "launch_readiness"],
  "winner_distribution": {"claude": 0.62, "codex": 0.31, "gemini": 0.07},
  "routing_rule": {
    "primary": "claude",
    "challenger": "codex",
    "reason": "Claude surfaces second-order failure modes; Codex provides cleaner shipping plans in implementation mode",
    "subroutes": [
      {"if_keywords": ["ship", "implement", "code"], "prefer": "codex"},
      {"if_keywords": ["risk", "audit", "edge case"], "prefer": "claude"}
    ]
  },
  "trust_score": {
    "value": 0.78,
    "components": {
      "n_episodes": 47,         "n_episodes_norm": 0.94,
      "consistency": 0.62,      "consistency_score": 0.55,
      "recency_agreement": 0.90, "diversity": 0.82
    },
    "computed_by": "system",
    "interpretation": "≥0.75 = use rule; 0.50–0.75 = use with kNN fallback; <0.50 = ignore"
  },
  "failure_modes": {
    "claude": "over-engineers when implementation suffices",
    "codex": "misses second-order failure modes",
    "gemini": "too generic for this user's domain"
  },
  "successful_prompts": {
    "claude": ["What's the SINGLE biggest...", "Audit this against..."],
    "codex": ["Implement... return the deterministic test for..."]
  },
  "decay": {
    "calendar_weight": {"recent_60d": 0.7, "older": 0.3},
    "model_checkpoints": [
      {"provider": "claude", "at": "2026-04-15", "model": "claude-4.7-opus", "pre_decay": 0.4},
      {"provider": "codex", "at": "2026-03-22", "model": "gpt-5.5", "pre_decay": 0.5}
    ]
  },
  "evidence": ["council_a1b2c3d4...", "council_e5f6g7h8...", "..."]
}
```

**Trust is computed by the system, not declared by the flagship.** The flagship
describes the rule; the system computes whether to trust it. The 5-component
score combines:

1. **n_episodes_norm** = `min(1.0, n_episodes / 25)` — small basins are inherently
   shaky; need ≥25 outcomes for full trust on this axis.
2. **consistency_score** = how much the primary winner dominates the distribution
   (e.g., 62/31/7 split → 0.55; 90/8/2 → 0.85).
3. **recency_agreement** = of the last 10 outcomes in this basin, what fraction
   agree with the extracted rule? Catches "the rule used to be true but isn't anymore."
4. **diversity** = embed-distance spread within the basin — high = real cluster of
   varied queries; low = the "basin" is actually 47 near-duplicates and the rule
   is a niche artifact.
5. **coherence_score** = mean cosine similarity from evidence embeddings to the
   geometric median (see "Structured geometric prior" section below). Catches
   "confident rule on noisy basin" — the highest-risk failure mode for a router.
   Without this signal, a 25-episode basin with high consistency but spread-out
   embeddings reads as high-trust when it shouldn't.

Final `trust_score.value` is a weighted geometric mean of the five components.

Evidence citations are mandatory — the consolidator MUST cite which council
outcomes produced each rule. Verifiable against drift.

**Model-version shift handling.** Calendar decay alone isn't sufficient — when
Claude 4.8 ships, all prior Claude outcomes are partially stale regardless of
recency. The `decay.model_checkpoints` array marks dates where a provider
released a material update; pre-checkpoint outcomes for that provider get
an extra decay factor. Checkpoints are detected from the strongest-model
probe output (the planned per-provider "which model do you accept?" check);
when the detected model string changes for a provider, a checkpoint is written.

Without this, the cortex slowly accumulates wrong rules every time a model
materially changes — and that's roughly every 3–6 months per provider.

### MCP tool surface (the agent-facing UX)

Two tiers in v1.5. The third tier (`plan_and_execute`) is **deferred to v1.6**
— packing it into Week 4 alongside dispatch resilience would compromise the
ship date and dilute the launch narrative. Cortex is the v1.5 headline.

```
mcp__trinity-local__ask(query)
  → { answer, routed_to, trust_score, latency_ms, cortex_rule_applied?,
       lens_score?, escalate_hint? }

  Note: the original Week 1 spec proposed `thread_id?` as a working-memory
  carrier. The parameter is **NOT shipped in v1.5** — it was advertised in
  the MCP schema during Weeks 1-4 but the handler discarded it. Removed
  in v1.5 cleanup; will return in v1.6 alongside the `plan_and_execute`
  tool when working memory actually has consumers (see "Deferred to v1.6"
  + "Working memory" sections below).

  Cost: ~$0.01–0.05, <2s typical
  Use when: you want a quick consult from whichever model is best for THIS
  user's flavor of this question. Single dispatch, concise return. The
  90%-of-the-time tool. Default.

  If lens_score on the dispatched response is below threshold, `escalate_hint`
  suggests Claude call `compare` instead.

mcp__trinity-local__compare(query, members=[claude, codex, gemini])
  → { winner, runner_up, agreed, disagreed, why_matters, council_run_id }

  Cost: ~$0.05–0.20, ~10s
  Use when: ask returned an escalate_hint, OR the question is hard enough
  that disagreement between models is informative up front. Returns compact
  structured synthesis (~200 words max).
```

Existing tools that stay: `record_outcome`, `get_persona`,
`get_council_status`. `route` (advice-only) is **deprecated** — it's useless
when Claude can't shell out to dispatch.

(Spec drift note 2026-05-19: `search_prompts` was listed here as "stays" but
retired 2026-05-17 in the pre-launch simplification — replaced by substring +
recency + replay-value heuristics on the hot path. `get_eval_summary`,
referenced elsewhere in earlier drafts, retired 2026-05-18. The v1.5 live
surface as Trinity ships today is: `route`, `ask`, `run_council`,
`record_outcome`, `get_persona`, `get_picks`, `mark_pick_wrong`,
`get_council_status`, `handoff` — 9 total. See claude.md "The nine MCP tools"
section for canonical current shape.)

```
mcp__trinity-local__get_cortex_rules(basin_id?, min_trust?)
  → { rules: [{basin_id, primary, challenger, trust_score, n_episodes,
               failure_modes, winner_distribution, ...}, ...] }

  Cost: free (local read), <50ms
  Use when: an agent wants to introspect why `ask` would route a given basin
  the way it does — surfaces the consolidated routing patterns. Same data the
  launchpad's "What Trinity has learned about you" card renders. Filter by
  basin_id for a single rule, or by min_trust to only see high-confidence
  rules (e.g. 0.75+ for production routing decisions).
```

8 tools total: `ask`, `compare` (aliased to `run_council`), `record_outcome`,
`search_prompts`, `get_persona`, `get_council_status`, `get_picks`,
`route` (deprecated but retained).

**Deferred to v1.6:** `mcp__trinity-local__plan_and_execute` (three-role
multi-step workflow — Thinker / Worker / Verifier — with `dry_run` mode
and recursive verification). Conductor-as-flagship-prompt mechanics stay
valid; just not in the v1.5 ship.

### Basin classifier (gates the entire cortex layer)

The cortex contributes nothing if a query doesn't match a basin. Three
explicit decisions:

**1. Near-miss handling.** A query embed is "in basin B" when its cosine
distance to basin B's centroid is below `basin_match_threshold` (default 0.35,
tuned empirically — needs validation in Week 2 with real basins). When the
nearest basin distance exceeds the threshold, the cortex contributes nothing
and the query falls back to pure kNN over hippocampus. No basin = no rule.

**2. Top-k soft membership.** Even when a query matches one basin cleanly,
we surface the top-3 basin candidates with similarity weights to the
Conductor (or directly to the dispatch decision):

```json
{
  "basin_matches": [
    {"basin_id": "concrete_shippable", "similarity": 0.91, "rule_trust": 0.78},
    {"basin_id": "system_design",      "similarity": 0.74, "rule_trust": 0.62},
    {"basin_id": "launch_readiness",   "similarity": 0.41, "rule_trust": 0.55}
  ]
}
```

When the top match dominates (similarity > 0.85), use that basin's rule alone.
When the top-2 are close (Δ < 0.1), apply both rules and require they agree
on the primary; if they disagree, downweight both and fall back to kNN.

**3. Re-basining pass.** Basins drift. The user's interests shift; new tensions
emerge; old basins go stale. Without re-basining, you accumulate stale basins
that compete with active ones.

- **Trigger:** every 50 new council outcomes OR when basin classifier
  acceptance rate drops below 70% (queries fall outside all basins too often).
- **Mechanism:** re-run the v1 basin-discovery pipeline (k-means + TF-IDF) over
  the current outcomes. Map old basin IDs to new ones where centroids align;
  retire basins with <5 outcomes after re-basining.
- **Rules migrate:** when a basin retires or merges, its routing rule is moved
  to the absorbing basin with its evidence preserved; trust score gets
  recomputed.

The basin set IS treated as a versioned artifact, not a static schema.

### Structured geometric prior for consolidation (shipped v1.5)

Cortex consolidation no longer hands the flagship raw outcomes and asks
it to do geometry-in-language. The consolidation pass now extracts a
structured geometric prior from each basin's evidence-prompt embeddings
and *prepends it* to the extraction prompt. The flagship reads "this
basin is BIMODAL with manifold_dim=2.97" and conditions on that fact
directly. This is the core architectural move: **rule-extraction on
structure, not geometry-in-language.**

Components, all in `cortex._compute_basin_geometry`:

1. **Geometric median** (Weiszfeld iteration) replaces the Euclidean
   mean as `basin_centroid`. Robust under L1 — one outlier outcome can
   no longer drag the centroid off the cluster. ~30 LOC, no deps.

2. **Coherence score** = mean cosine similarity of evidence embeddings
   to the geometric median. Saturates naturally at 1.0 (every point
   coincides). Becomes a 5th trust component (weight 0.20) — without
   this signal, a confident rule on a noisy basin reads as high-trust,
   which is the most dangerous failure mode for a router.

3. **Manifold dim** via participation ratio of the centered embedding
   matrix — a descriptive numeric signal surfaced to the LLM prompt.
   Not used directly in trust (PR scales with ambient dim, noisy for
   high-dim embeddings); coherence does the heavy lifting there.

4. **Bimodality flag** via excess kurtosis on the first-PC distribution
   (computed by power iteration; threshold `-1.3`, requires N≥10).
   Negative excess kurtosis flatter than uniform indicates a plausibly
   twin-peaked basin. The extraction prompt then tells the flagship
   "this basin has BIMODAL geometry; return TWO subroutes if the modes
   route to different providers." v1.5 only *flags*; v1.6 wires HDBSCAN
   to actually split.

5. **Typicality ordering** — outcomes sorted by L2 distance from the
   median (typical → outlier). The compressed-outcomes block in the
   extraction prompt receives them in this order so the flagship
   weights the head of the list more heavily.

### Lens-build: depth-first, chairman-in-the-loop (Week 4-5 design)

The v1.0 lens-build pipeline runs k-means once on per-thread mean
centroids, then labels basins with TF-IDF top-terms. Two failure
modes show up on real corpora:

1. **Surface-keyword clustering.** A basin labeled "5 twists" pulled
   in 158 turns spanning Instagram strategy, household art, and
   "give me 5 of X" prompt continuations — clustered because of
   shared shallow tokens, not shared topic.
2. **TF-IDF labels are descriptive of the corpus, not of the user.**
   Top-3 terms = "twists, plot, give" — stopword-adjacent, doesn't
   tell the user *what* they were thinking about.

v1.5's lens-build inverts this around two ideas — **depth ranking**
(geometry-only) for what the chairman should see, and **chairman-in-
the-clustering-loop** for how centroids drift toward coherence.

**Council as GPS.** The architecture treats the chairman as a
navigation tool with two modes — broad (one call, all basins,
breadth) and deep (chain mode, one basin, conviction). Same
primitive as the user-facing council mechanic, applied to the
lens-build itself.

#### Depth-rank: pre-clustering geometry

`src/trinity_local/me/depth.py` (shipped ticks #50-51) computes a
three-component per-thread depth score from raw embeddings, no
LLM calls:

| Component | Formula | Literature backing |
|---|---|---|
| **Corpus distance** | cosine(thread_centroid, corpus_centroid), equal-weight per thread | TAD-Bench novelty (arXiv:2501.11960) |
| **Inter-turn distance** | mean cosine between consecutive turn embeddings | Stalling Index analog (arXiv:2601.09570) |
| **LID via TwoNN** | per-thread MLE: `d_hat = N / Σ log(d2/d1)` | Facco et al. 2017 (Sci. Reports); NeurIPS 2023 — fluent human prose LID ≈ 9, AI text ≈ 7.5 |

Composite: `depth_score = corpus_distance × log(1+inter_turn) × log(1+LID)`.
Multiplicative — noise in any one component drags the score to 0;
a thread is "deep" only when all three signals agree.

This is what the chairman sees as input. The chairman never reads
the noisy 80% of the corpus; it sees the top-K-by-depth threads
of each candidate basin.

#### k-LLMmeans: chairman steers the centroids

Rather than label basins after k-means converges geometrically,
the chairman is in the loop:

```
for iteration in 1..N (N = 2-3 in practice):
    1. Assign each thread to nearest current centroid (pure geometry)
    2. ONE batched chairman call: for each basin, summarize from
       the top-K depth-ranked representatives → semantic label
    3. Embed each label → that's the next iteration's centroid
    4. Test convergence (mean centroid drift < threshold)
```

The chairman call is **one batched call per iteration**, not one
per basin. With N=3 iterations + 1 final patterns/nuggets call,
the entire dream pipeline fits in 4 chairman calls. The 5th is
reserved as council-chain validation on the final-round labels
(seat-vs-chairman dispute resolution on contested basins).

Reference: ClusterLLM (EMNLP 2023, arXiv:2305.14871),
k-LLMmeans (arXiv:2502.09667).

#### Why this is the v1.5 path, not v2

The pure-geometry lens-build (v1.0) hits a ceiling on noisy
real-world corpora — the b11 basin failure is reproducible.
Chairman-in-the-loop fixes it without needing a trained
coordinator. Same architectural axis as `docs/spec-v2.md`'s
sunset rationale: prompt engineering + context engineering
in a flagship beats a 7B trained model on the dataset sizes
v1.5 users will have.

The 5-call budget per dream stays intact. The council mechanic
stays the only place LLMs touch the data. Depth-rank stays
pure-geometry, no chairman dependency.

### Deferred to v1.6

**HDBSCAN sub-basin discovery.** v1.5 *flags* bimodality; the flagship
is told "return two subroutes" but the basin itself stays unified in
the consolidated patterns file. v1.6 should: detect when bimodality
flag has fired ≥3 consolidations in a row, run HDBSCAN on that basin's
embeddings, persist each cluster as a separate basin with its own
centroid + rule. ~150 LOC vendored or one `hdbscan` dep.

**Calibration gate before promoting HDBSCAN to v1.5:** if Week 2
calibration data shows >15% of basins flagging bimodal, promote HDBSCAN
to v1.5. If <5%, the flag is enough.

**Isomap geodesic centroid.** Skip. Only beats geometric median +
HDBSCAN in one specific data shape (single connected curved manifold,
not multimodal). Revisit only if calibration shows curved-single-manifold
is a real failure class.

**principles.md (the sixth core memory) — on hold, data-gated.** The
original pipeline plan: cluster per-council `routing_lesson` strings,
prefer councils where `user_winner != chairman pick` (the "reverted
commit" analog), require ≥3 distinct basins per cluster (cross-domain
recurrence as the meta-principle signal). Tick #69's data audit found
the pipeline is premature:

- 19 total councils in the corpus; 19 have routing_lesson.
- 3 have ANY user verdict; 0 have an override.
- The routing_lessons are routing-shaped ("For copywriting_polish,
  prefer codex…"), not engineering-principle-shaped. They map to
  per-task provider preferences already captured in
  `personal_routing_table` — they aren't the kind of meta-principle
  the 15 in `claude.md` are ("filter at the boundary," "audit for
  shape").

Gates for revisiting:
1. **Verdict capture rate ≥ 50%** (currently 13%, 4/31 on the dev
   install as of 2026-05-20; baseline was 3/19 = 16% pre-nudge).
   Trinity's moat thesis rests on this signal — at 13%, 87% of
   councils contribute zero supervision data. The active-nudge
   mechanism shipped pre-launch but the proportion hasn't moved
   meaningfully at this sample size. Task #110 is the investigation.
2. **N ≥ 100 councils** with routing_lessons before any k-means
   clustering in 768-d embedding space is meaningful.
3. **A different signal source** may be more appropriate for
   meta-principles than routing_lesson. Candidates: git commit
   pair history (commit + fix-commit), explicit chairman invocations
   with a "principle-extraction" prompt instead of "routing rule,"
   or session transcripts where the user named the pattern
   ("audit for shape," "we keep hitting this").

Same structural shape as the lens Stage 4 post-filter remains the
right pattern when the data arrives — just at the cross-event
level instead of cross-decision. Tracked as task #109.

### Cortex (routing) vs Lens (evaluation) — two layers, same data

This was implicit; making it explicit because the layers serve different
roles and the spec needs them not to fight.

| Layer | When | Decides | Source |
|---|---|---|---|
| **Cortex** | Pre-fan-out | *Which provider should I ask?* | Routing patterns extracted from accumulated council winners |
| **Lens** | Post-fan-out | *Is this response good enough by my taste?* | Pairwise preference geometry (`/memories/lens.md` + pair-wise rejection vectors) |

A successful council outcome feeds both:
- **Cortex signal:** this provider won → reinforce routing rule for this basin
- **Lens signal:** the chosen response embed is closer to the user's "preferred
  pole" of the relevant tension than the rejected ones → reinforce evaluation geometry

The data is the same; the consumption is different. The spec must keep them
complementary or they'll contradict (cortex says "ask Claude", lens says
"but Codex's response geometry is closer to your taste on this kind of
question").

**Composed flow inside `ask`:**

```
1. Cortex picks primary (and challenger) based on basin match
2. Dispatch ONLY to primary
3. Score primary's response against the user's lens (embed → distance to
   "preferred pole" of relevant tension; cheap, no extra LLM call)
4. If lens_score ≥ threshold (default 0.65): ship it. Done. 1 call.
5. If lens_score < threshold but > floor (0.40): dispatch challenger.
   Pick the better-scoring response.
6. If both below floor: surface `escalate_hint=compare` to Claude.
```

Net cost:
- Easy + clean basin match: 1 call (just primary)
- Murky: 2 calls (primary + challenger)
- Confused: 2 calls + escalation to `compare` (Claude decides to invoke)

This is what makes `ask` the 90% tool: most queries clear the lens threshold
on the first dispatched answer. Council is rare-and-expensive, used only when
lens says neither candidate is good enough.

### Conductor layer

There are two conductor layers, not one:

1. **Claude-in-the-harness** — already there, decides which Trinity tool to
   call. Free for us. Most of the routing-decision intelligence happens here.

2. **Trinity's internal mini-conductor** — only kicks in for `compare` and
   `plan_and_execute`. For `ask`, retrieval + pick + heuristic routing
   handles it. No flagship call wasted on meta-planning.

For `plan_and_execute`: a flagship (default Claude Opus) gets the context
package (kNN episodes + picks + lens basins + pool composition + cost
metadata) and outputs the three-role plan (Thinker / Worker / Verifier
assignments per step). Dispatcher executes. Verification step reviews.

**The Conductor is NOT a trained model.** It's a flagship prompted with the
right context. The value sits in prompt-engineering quality, not in the
routing decision itself — smaller models find the same routing as larger
ones, but the larger model writes better natural-language subtasks. A
flagship with cortex+kNN context outperforms a hypothetical local 7B
because the flagship has 100x the linguistic capability.

### Dispatch layer

New in v1.5:

- **Local model dispatch** — Ollama + MLX added as dispatch targets alongside
  the 3 CLIs. Strongest-model probe extended to local runtimes.
- **Rate-limit detection** — parse stderr from each CLI for known
  rate-limit / billing-exceeded patterns. Surface as structured error.
- **Conductor replan** — on dispatch failure, the planner gets called back
  with the failure reason + reduced pool. Max 2 retries.
- **Pool composition** — exposed in every tool response so the calling Claude
  knows what's available.
- **Cost metadata** — per-call cost estimates (free for local, ~$/token for
  each provider) so the Conductor can optimize for cost as well as quality.

### Working memory (per-MCP-session)

`thread_id` parameter on `ask` and `plan_and_execute`. Same thread → Trinity
carries context across calls (recent decisions, recent retrieval results,
recent failures). Decays after ~30 min idle.

Already half-built via the council thread manifests in v1; v1.5 generalizes
to all tool calls.

### Personalized evals from corpus history (the empirical benchmark)

Synthetic benchmarks are the standard surface providers compete on:
HumanEval, MMLU, MT-Bench, etc. They share a property nobody admits:
they're picked by the benchmark author, not the user. Trinity owns a
different surface — the user's own prompt corpus + rejection signal —
which is structurally asymmetric in our favor.

**The asymmetry:** No frontier provider can build personalized eval
suites from cross-provider rejection signal. Anthropic only sees
Claude transcripts; OpenAI only sees GPT transcripts. Trinity sees
all three plus the rejections of each provider's past output by the
same user. The eval set is the user's empirical taste, not anyone's
synthetic guess at it.

**Inputs (already on disk for any seeded install):**

- `~/.trinity/me/rejections.jsonl` — (prompt, assistant_response,
  rejection_type ∈ {REFRAME, COMPRESSION, REDIRECT, SHARPENING})
  mined by `me/turn_pairs.py`. Each entry is empirical proof the
  user rejected a specific response shape on a specific prompt.
- `~/.trinity/prompts/prompt_nodes.jsonl` — full cross-provider
  index with nomic-768d embeddings; the basin clustering in
  `topics.json` provides per-task-type slicing.
- `~/.trinity/memories/lens.md` — the JUDGE rubric. Paired tensions
  encode what this user privileges vs. sacrifices.
- `bootstrap_pairs.py` already extracts cross-provider pairs (same
  prompt, multiple providers) — each pair is N candidate responses
  to one prompt where the user implicitly preferred *something*.

**Mechanism (SHIPPED 2026-05-14 — task #122 complete):**

```
trinity-local eval-build [--limit N] [--source rejections]
trinity-local eval-stats [--eval-id ID]
trinity-local eval-run --target <provider> [--judge <provider>]
                       [--eval-id ID] [--limit N] [--no-score]
```

1. **`eval-build`** assembles an eval set at `~/.trinity/evals/eval_<hash>.json`
   with schema `{prompt, rejection_type, rejected_response,
   user_substitute, rubric_signal, basin_id, source, source_id,
   prompt_id, provider_of_rejected_response}` — formally specified in
   [`schemas/eval_set.schema.json`](../schemas/eval_set.schema.json).
2. **`eval-run`** dispatches each prompt to `--target` via existing
   `providers.make_provider` → `dispatch_runner` path.
3. **Auto-scoring** asks `--judge` (auto-picked to differ from
   `--target` for bias-trap avoidance) to grade `target_response` vs
   `rejected_response` on the rejection_type axis, conditioned on
   `lens.md`. Returns `{score, reason}` per item.
4. Aggregates per rejection_type (`by_rejection_type` map) into
   `~/.trinity/evals/results/eval_<hash>__model_<provider>__<ts>.json`.
   Timestamped path so multiple runs of the same (eval, provider) pair
   coexist for diffing across model releases.

**Output (the marketing surface):**

The headline becomes "model X scored 0.73 on this user's
COMPRESSION-prone coding prompts, 0.91 on REDIRECT-prone writing
prompts" — empirical, defensible, and impossible for any single
provider to refute. Same harness produces routing signal
(`compute_personal_routing_table()`) AND launch-arc benchmark
content (workstream #116). The two surfaces share a mechanism
instead of being two unrelated efforts.

**Status (post-2026-05-14):** SHIPPED in the v1.0 launch-arc window
as task #122. Inputs were already on disk (44 rejections; 49k+ prompt
nodes; lens.md built); the missing builder + runner + scorer + CLI
landed in two ticks today. Real-corpus first run produced REFRAME
45.5% / COMPRESSION 25.0% / REDIRECT 22.7% / SHARPENING 6.8% on the
maintainer's corpus — the signature itself is informative as a
benchmark axis. Compounds with #111-113 (matryoshka shape-sim feeds
into basin-aware eval slicing — pending) and #119 (handoff mechanism
reuses the same `make_provider` dispatch path the eval harness uses).

**Future hub angle:** the eval-set JSON (without raw prompt text,
just `rejection_type` + `rubric_axes` shape) is shareable. A
community-aggregated "Trinity Bench" emerges naturally if even a
small fraction of users opt-in to publishing their eval shape.
Anonymous taste topology that no provider can collect themselves.

## 5-week ship plan (target: June 3, 2026)

**Week 1 — MCP `ask` + hippocampus kNN** (working memory deferred to v1.6)
- `mcp__trinity-local__ask(query)` end-to-end (no cortex yet — kNN only)
- kNN retrieval over existing prompt-node embeddings (~50k on real corpus 2026-05-13; grows over time) → dispatch best provider
- Fast-path bypass when retrieval confidence > 0.9 (skip Conductor)
- Heuristic transcript-success labeler (so routing works pre-councils)
- Token-budget enforcement (max 500 tokens for `ask` returns)
- Tool descriptions teach Claude when to use ask vs compare
- ~~`thread_id` working memory across MCP calls~~ → **deferred to v1.6**.
  Lived in the MCP schema as a no-op through Weeks 1-4; removed in
  cleanup. Returns alongside `plan_and_execute` when there's a real
  consumer.

**Week 2 — Cortex consolidation (offline only)**
- `trinity-local consolidate` CLI command + flagship-call extraction
- `~/.trinity/scoreboard/picks.json` schema (write only — not yet read by `ask`)
- 6-component `trust_score` computed by the system (not the flagship): n_episodes / consistency / recency / diversity / coherence / audit_score. Plus a multiplicative `effective_trust = trust * 0.5^override_count` layered on top for user vetoes.
- Model-checkpoint detection via strongest-model-probe deltas → version-shift decay
- Evidence citations required; consolidator MUST cite council IDs per rule
- Scheduled triggers (every 10 councils + nightly via launchd)
- **🛑 GATE: Human calibration checkpoint before Week 3.** Founder reads 30
  extracted rules and rates each: matches my behavior / doesn't / can't tell.
  If agreement < 70%, iterate the consolidation prompt before wiring cortex
  into the query hot-path. **kNN fails visibly with bad neighbors; bad rules
  fail silently with confident-sounding wrong advice.** This checkpoint is
  non-negotiable.

**Week 3 — Cortex query-time + dispatch resilience + local dispatch**
- Basin classifier hot-path (cosine threshold, top-3 soft membership)
- Cortex rule retrieval at query time, gated by `trust_score ≥ 0.5`
- Re-basining trigger (every 50 councils OR <70% basin acceptance rate)
- Cortex (routing) + Lens (evaluation) composed flow inside `ask`
- Rate-limit detection per provider; structured error codes
- Conductor replan with reduced pool (for `compare`)
- Local model dispatch (Ollama + MLX); strongest-model probe extended to local runtimes
- Pool composition + cost metadata exposed in tool responses

**Week 4 — `compare` + per-provider failure-mode tracking + cold-install resilience**
- `mcp__trinity-local__compare(query, members)` — opt-in side-by-side (alias of run_council)
- Per-provider failure-mode tracking extending cortex schema
- Strict-format inference via cortex retrieval
- Macvm smoke covers the v1.5 MCP path end-to-end (install → ask → compare → record_outcome)
- Empty-state cortex handling (cold start: no basins, no rules → pure kNN)

**Week 5 — Launchpad reframe + ship**
- **Launchpad homepage = cortex rules.** The extracted routing rules per basin
  are the lead artifact, with trust score + evidence citations. The radar
  chart and recent-councils list sit below. This is what makes the cortex
  *visible* to the user — otherwise the two-tier architecture is invisible
  plumbing and the pitch has no proof.
- Each rule shows: basin label, primary + challenger, why, trust_score
  components, recent agreement, "View evidence" link to underlying outcomes
- Override mechanism: user can mark a rule wrong → it's downweighted next consolidation
- README + launch.md + founder essay lead with harness-call narrative
- Cold-install smoke verifies the MCP path (Claude Code → install-mcp → ask)
- **Ship: June 3, 2026**

**Explicitly deferred to v1.6 (post-ship):**
- `mcp__trinity-local__plan_and_execute` — full Conductor mode with 3-list
  output and recursive verification. Packing into v1.5 risks the ship date
  and dilutes the cortex headline. The Conductor mechanics described in the
  Architecture section all stay valid; they just ship in v1.6.

## Open questions (status after Weeks 1–5)

Weeks 1–5 have shipped; here's where each open question landed:

1. **Default Conductor model.** ✅ Resolved: `--provider claude` is the
   default for `consolidate`, `--audit-provider gemini` (or codex when
   `--provider gemini`) for the audit pass. Per-task-kind override is a
   v1.6 item if pattern demands it.
2. **Local model preference order** (Ollama vs MLX for the same model).
   🟡 Deferred. Local dispatch shipped behind env-gated detection;
   preference order will get tuned when the v1.5 user cohort has enough
   local-dispatch outcomes to inform the call. v1.6 follow-up.
3. **Cortex consolidation cost.** ✅ Resolved: `--provider` defaults to
   `claude` (Opus is the slow path; user wants the best extraction);
   `--audit` opts into a second flagship via `--audit-provider`. Cheaper
   Haiku-class fallback is a v1.6 toggle.
4. **`compare` retrieval-confidence trigger.** ✅ Resolved at
   `ESCALATE_HINT_THRESHOLD = 0.55` in `ask.py`. Below that the `ask`
   return carries `escalate_hint=compare` so the calling agent can choose.
5. **Cortex eval signal vs lens basins.** 🟡 Outstanding. The two layers
   (cortex routing rules and `memories/lens.md` paired tensions) share basin
   semantics but no automated cross-check fires today. v1.6 item:
   compare them, soft-warn on disagreement (don't hard-fail — the user
   may have shifted preferences faster than the consolidator caught up).

## Foundations from v1.0 that v1.5 depends on (do NOT break)

| v1 thing | v1.5 use |
|---|---|
| `~/.trinity/SCHEMA_VERSION` lock | v1.5 adds `cortex/` subdir without renaming existing |
| Routing JSON ledger canonical fields | v1.5 cortex extracts patterns from these — schema is the training data shape |
| MCP stable contract | `record_outcome`, `search_prompts`, `get_persona`, `get_council_status` unchanged; `run_council` aliased to `compare`; `route` deprecated |
| Embeddings pipeline (nomic 768d) | v1.5 uses same index — no re-embedding required |
| Lens-discovery outputs (basins, lenses, rejections) | topics.json is the cortex consolidation key; lenses are the eval set |
| Privacy posture (prompts never upload) | unchanged. Cortex consolidation runs on user's flagship sub — local dispatch, not hosted. |

## What v1.5 explicitly does NOT do

- **Train a model.** The Conductor is a flagship with context. No GRPO, no DPO,
  no SFT. (If v1.5 hits a quality ceiling, the trained-model path in
  `spec-v2.md` opens — but we don't pay that cost until we have evidence it's
  needed.)
- **Replace v1's council mechanic.** Council mode stays for the rare case the
  user wants the parallel-fan-out comparison AND the data acquisition for
  cortex consolidation. `compare` IS the council mechanic, exposed as MCP.
- **Phone home.** Same privacy posture as v1. Cortex consolidation runs locally
  on the user's own subscription.
- **Charge.** Free-forever stays.
- **Ship before v1.0.** v1.5 follows v1.0. v1.0 shipped May 13–15, 2026 as planned.

## Path past v1.5 (when / if needed)

If `ask` + `compare` + `plan_and_execute` + cortex consolidation hit a
quality ceiling on real user data, the v2 trajectory opens:

- True trained Conductor (Qwen 7B via DPO or sep-CMA-ES per the
  recipe in `spec-v2.md` — deferred, not sunset)
- v1.0 + v1.5 data IS the training set when v2 lands
- Local fine-tune via MLX on Apple Silicon

The decision will be data-driven. If flagship-as-Conductor + cortex extraction
covers 95% of cases at acceptable cost/latency, we don't pay the training
infrastructure cost. If users hit specific failure modes at scale, that's
when v2 (the trained-coordinator) starts.

## Why this beats a trained-coordinator path for THIS market

Trained-router research shows that for a fixed routing problem, model size
buys you better natural-language *subtask prompts* more than better
*routing decisions* — smaller models find roughly the same optimal routing
as larger ones; the larger model wins because it writes cleaner subtasks.

We can get better prompt quality than any local 7B by using a flagship
model as the Conductor with cortex-derived context. The Conductor doesn't
have to learn routing because the cortex rules already encode it. The
Conductor doesn't have to learn user taste because the lens + retrieval
already encode it. The Conductor just writes the per-member subtask
prompts — and a flagship writes those better than any 7B.

The "things change weekly" point is load-bearing: trained Conductors decay
when models update (Claude 4.8 ships, the trained routing decisions for
Claude 4.7 are now stale). The cortex-extraction-via-flagship approach
re-consolidates whenever new councils land. No retraining. Zero compute
investment. The moat is the ledger + the extracted rules, not the weights.
