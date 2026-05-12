# Trinity v1.5 — locked next-trajectory spec

> Status: **spec only, follows v1.0 ship.** Target: **ship June 3, 2026.**
>
> v1.5 is where the "SOTA for you + your taste + your subs + saves cost" pitch
> becomes literally true. v1.0 ships the data pipe; v1.5 turns it into a routing
> product Claude Code reaches for.
>
> This spec supersedes the v1.1 / v1.2 / v2.0 trajectory in `docs/spec-v2.md`.
> The trained-coordinator path is sunset (see `docs/spec-v2.md` sunset header
> for why); v1.5's flagship-as-Conductor architecture achieves the same goal
> via context engineering, no training infrastructure required.

## The reframe

v1.0 ships a launchpad-centric council product. **v1.5 inverts the primary
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
| **Dreaming** — agents consolidate past sessions into reusable lessons | **Cortex consolidation** — flagship extracts routing patterns per basin from accumulated council outcomes | Hosted on Anthropic infra vs. runs on your own subscription; single-provider vs. across Claude/GPT/Gemini; memory lives in Anthropic's storage vs. `~/.trinity/cortex/routing_patterns.json` |
| **Outcomes** — rubric-graded eval by a separate grader agent | **Lens** — pair-wise tension evaluation in a separate context | Anthropic-grader vs. user-taste-derived lens from `me/lenses.json` |
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
          "migration strategy" basin; cortex rule says "Codex for impl-mode
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
├── ~/.trinity/memory/prompt_nodes.jsonl       v1 — individual user prompts
├── ~/.trinity/memory/turn_windows.jsonl       v1 — with surrounding context
└── ~/.trinity/council_outcomes/*.json         v1 — individual council decisions

TIER 2 — Cortex (semantic / procedural, slow write, fast recall)
├── ~/.trinity/memories/topics.json                  v1 — task-type clusters
├── ~/.trinity/me/lenses.json                  v1 — taste tensions
├── ~/.trinity/cortex/routing_patterns.json    NEW — routing rules per basin
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
  Write rule to ~/.trinity/cortex/routing_patterns.json keyed by basin_id
```

**Triggers:**
- Every 10 new councils — light pass, only the affected basin
- Nightly — full consolidation, via launchd or `trinity-local watch-loop`
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
an extra decay factor. Checkpoints are detected from the `model_detector.py`
output (which already probes for the strongest model each provider accepts);
when the detected model string changes for a provider, a checkpoint is written.

Without this, the cortex slowly accumulates wrong rules every time a model
materially changes — and that's roughly every 3–6 months per provider.

### MCP tool surface (the agent-facing UX)

Two tiers in v1.5. The third tier (`plan_and_execute`) is **deferred to v1.6**
— packing it into Week 4 alongside dispatch resilience would compromise the
ship date and dilute the launch narrative. Cortex is the v1.5 headline.

```
mcp__trinity-local__ask(query, thread_id?)
  → { answer, routed_to, trust_score, latency_ms, cortex_rule_applied?,
       lens_score?, escalate_hint? }

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

Existing tools that stay: `record_outcome`, `search_prompts`, `get_persona`,
`get_council_status`. `route` (advice-only) is **deprecated** — it's useless
when Claude can't shell out to dispatch.

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
`search_prompts`, `get_persona`, `get_council_status`, `get_cortex_rules`,
`route` (deprecated but retained).

**Deferred to v1.6:** `mcp__trinity-local__plan_and_execute` (Sakana-style
3-list multi-step workflow with `dry_run` mode and recursive verification).
Conductor-as-flagship-prompt mechanics stay valid; just not in the v1.5 ship.

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

### Cortex (routing) vs Lens (evaluation) — two layers, same data

This was implicit; making it explicit because the layers serve different
roles and the spec needs them not to fight.

| Layer | When | Decides | Source |
|---|---|---|---|
| **Cortex** | Pre-fan-out | *Which provider should I ask?* | Routing patterns extracted from accumulated council winners |
| **Lens** | Post-fan-out | *Is this response good enough by my taste?* | Pairwise preference geometry (`/me/lenses.json` + pair-wise rejection vectors) |

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
   `plan_and_execute`. For `ask`, retrieval + cortex rule + heuristic routing
   handles it. No flagship call wasted on meta-planning.

For `plan_and_execute`: a flagship (default Claude Opus) gets the context
package (kNN episodes + cortex rules + lens basins + pool composition + cost
metadata) and outputs Sakana's 3-list. Dispatcher executes. Verification
step reviews.

**The Conductor is NOT a trained model.** It's a flagship prompted with the
right context. Sakana's own paper shows the value is in prompt-engineering
quality (3B vs 7B find same routing; 7B wins on prompt quality). A flagship
with cortex+kNN context outperforms a hypothetical local 7B because the
flagship has 100x the linguistic capability.

### Dispatch layer

New in v1.5:

- **Local model dispatch** — Ollama + MLX added as dispatch targets alongside
  the 3 CLIs. `model_detector.py` extended to probe local runtimes.
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

## 5-week ship plan (target: June 3, 2026)

**Week 1 — MCP `ask` + hippocampus kNN + working memory**
- `mcp__trinity-local__ask(query, thread_id?)` end-to-end (no cortex yet — kNN only)
- kNN retrieval over existing 28k embeddings → dispatch best provider
- Fast-path bypass when retrieval confidence > 0.9 (skip Conductor)
- Heuristic transcript-success labeler (so routing works pre-councils)
- Token-budget enforcement (max 500 tokens for `ask` returns)
- Tool descriptions teach Claude when to use ask vs compare
- `thread_id` working memory across MCP calls

**Week 2 — Cortex consolidation (offline only)**
- `trinity-local consolidate` CLI command + flagship-call extraction
- `~/.trinity/cortex/routing_patterns.json` schema (write only — not yet read by `ask`)
- 6-component `trust_score` computed by the system (not the flagship): n_episodes / consistency / recency / diversity / coherence / audit_score. Plus a multiplicative `effective_trust = trust * 0.5^override_count` layered on top for user vetoes.
- Model-checkpoint detection via `model_detector.py` deltas → version-shift decay
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
- Local model dispatch (Ollama + MLX); `model_detector.py` probes local runtimes
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
   (cortex routing rules and `me/lenses.json` paired tensions) share basin
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
- **Ship before v1.0.** v1.5 follows v1.0. v1.0 ships May 13–15 as planned.

## Path past v1.5 (when / if needed)

If `ask` + `compare` + `plan_and_execute` + cortex consolidation hit a
quality ceiling on real user data, the v2 trajectory opens:

- True trained Conductor (Qwen 7B via DPO or sep-CMA-ES per the
  Sakana-aligned recipe in `spec-v2.md` — deferred, not sunset)
- v1.0 + v1.5 data IS the training set when v2 lands
- Local fine-tune via MLX on Apple Silicon

The decision will be data-driven. If flagship-as-Conductor + cortex extraction
covers 95% of cases at acceptable cost/latency, we don't pay the training
infrastructure cost. If users hit specific failure modes at scale, that's
when v2 (the trained-coordinator) starts.

## Why this beats Sakana's trained-coordinator path for THIS market

Sakana's TRINITY paper proves a 7B trained Conductor beats GPT-5 by ~2.5pts
on benchmarks. Their own ablation (Fig 7) shows the value is in
prompt-engineering quality, NOT routing decision — 3B and 7B find the same
optimal routing; the 7B wins because of better natural-language subtasks.

We can get better-than-7B prompt quality by using a flagship model as the
Conductor with cortex-derived context. The Conductor doesn't have to learn
routing because the cortex rules already encode it. The Conductor doesn't
have to learn user taste because the lens + retrieval already encode it.
The Conductor just writes the per-member subtask prompts — and a flagship
writes those better than any 7B.

The "things change weekly" point is load-bearing: trained Conductors decay
when models update (Claude 4.8 ships, the trained routing decisions for
Claude 4.7 are now stale). The cortex-extraction-via-flagship approach
re-consolidates whenever new councils land. No retraining. Zero compute
investment. The moat is the ledger + the extracted rules, not the weights.
