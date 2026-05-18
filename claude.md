# claude.md — Trinity Local

> Agent-facing project context. Companions:
> - [`docs/spec-v1.md`](docs/spec-v1.md) — locked v1.0 launch spec (ships May 13–15)
> - [`docs/spec-v1.5.md`](docs/spec-v1.5.md) — **active next-trajectory spec** (target June 3, 2026): MCP-primary, hippocampus+cortex memory, local model dispatch, rate-limit dodge, flagship-as-Conductor (no training)
> - [`docs/spec-v1.6.md`](docs/spec-v1.6.md) — **post-v1.5 spec** (~2 weeks after June 3): browser extension + Native Messaging host that captures claude.ai / chatgpt.com / gemini.google.com conversations to `~/.trinity/conversations/`. No server, no daemon, no listening port. Closes the corpus-acquisition gap for web-chat users; the "Trinity reads transcripts already on your machine" claim becomes literal for everyone, not just CLI power users. **The same extension now also serves as the cross-platform launchpad dispatcher** (Phase 4b, 2026-05-16) — see [`docs/MIGRATION.md`](docs/MIGRATION.md) for the upgrade path from the macOS-only Shortcut. 10 narrow action-allowlist entries cover every launchpad button cross-platform; the Shortcut remains as tier-2 fallback.
> - [`docs/spec-v2.md`](docs/spec-v2.md) — sunset (trained-coordinator path). Preserved as architectural-decision history; reopens only if v1.5 hits a quality ceiling.
> - [`docs/cross-platform-spec.md`](docs/cross-platform-spec.md) — surface-expansion spec: terminal → desktop → mobile, Claude-Code-shaped phasing. Same `~/.trinity/` corpus everywhere; no hosted controller.
> - [`docs/three-tier-architecture.md`](docs/three-tier-architecture.md) — **launch architecture**. Initially ratified by `council_ff3da1fa84906791` (Phase 1, 2026-05-16); trust/audit substrate ratified by `council_c18f739a0234aa58` (Phase 6, 2026-05-16); final v1.0 integration floor and architecture coherence ratified by **`council_37eca30b6e7010df`** (Phase 7, 2026-05-16) — the **load-bearing launch decision**. Three tiers — Skill (primary), Pip (engine), Chrome Extension (optional capture+UI) — with `~/.trinity/` as the invariant data contract. v1.0 ships the skill artifact at `skills/trinity/SKILL.md` orchestrating the existing CLI + the `scripts/` shebang substrate around the pip-tier engine; v1.1 inverts (pip imports from scripts/) + adds cross-platform test matrix + visible trust indicators. Tier-equivalence invariant (NOT bit-identical): cosine ≥ 0.9999 between backends, identical k-means cluster assignments, identical chairman picker output under pinned config.
> - [`docs/scale-plan.md`](docs/scale-plan.md) — long-form roadmap.

## Project Identity

**Trinity Local is your taste, ported.** v1 hero (pivoted 2026-05-16 from
council-mechanic framing to digital-twin framing):

> **Your taste, ported. Lives inside Claude Code, Codex CLI, Gemini CLI, and Cursor.**
>
> You've already chosen between Claude, Codex, and Gemini a thousand times.
> Trinity reads those transcripts, learns the pattern in how you rephrase,
> judge, and decide — then runs hard questions through all three in your
> voice and picks the answer you would have picked.
>
> *No new app. No service. No API key. Your transcripts never leave your machine.*

The digital-twin axis: **transcripts** (what's already on your machine) → **lens**
(the pattern of how you rephrase/judge/decide, extracted offline) → **twin** (Trinity
acting in your voice when you ask hard questions). Councils are the mechanism, not
the pitch — the user doesn't think "I want a council," they think "I want what I
would have picked." The chairman lens-conditioning + per-member scaffolding (slot
documented at `council_runtime.render_member_prompt`) is the twin's mechanism for
"twisting the models the way you would."

Prior framing (pre-2026-05-16, retained for context): hero was *"Stop copy-pasting
prompts. Own your context. Dream your core memories."* with sub *"One question.
Every model you use. One answer that knows you."* Three pains were copy-paste /
siloed thinking / over-engineering. Pivoted because the polyharness power user
reads "councils" as another tool to learn; reads "your taste, ported" as something
working FOR them. Ratified on `bundle_42f8cea9c9e705e5` through three rounds of
cross-provider council iteration; the new framing is a user-direct rewrite.

v1 SHIPS: lens building (the twin's substrate) + councils + chairman synthesis
+ `dream` cold-start + cortex extraction. What's NOT in v1 yet but blocks the
full twin pitch: **per-member prompt scaffolding** (documented design hole at
`council_runtime.py:113`) — today chairman is lens-conditioned but dispatch is
not, so members get the raw question, not the user-twisted version. And
**task_type vocabulary unification** (documented KNOWN GAP at
`ranker/chairman_picker.py:_blended_pick`) — the chairman's open-set labels and
the picker's closed-set heuristic labels don't intersect, so personal routing
silently doesn't fire today.

**Status (2026-05-17, v1.7.3 share-workflow pass):** v1.7 ships May 13–15 (pyproject `1.7.3`; v1.7.1+v1.7.2 = public-readiness; v1.7.3 = share-workflow end-to-end: eval-share PNG, council-share rewrite, me-card install URL, review-link fake-URL fix, launchpad share chips) — see [`docs/spec-v1.md`](docs/spec-v1.md). Brand axis (pivoted 2026-05-16): **transcripts** (already on your machine) → **lens** (the pattern of how you rephrase/judge/decide) → **twin** (Trinity acting in your voice). Hero: *"Your taste, ported. Lives inside Claude Code, Codex CLI, Gemini CLI, and Cursor."* Sub: *"No new app. No service. No API key. Your transcripts never leave your machine."* Prior framing was *"Stop copy-pasting prompts. Own your context. Dream your core memories."* — pivoted because the polyharness power user reads "councils" as another tool to learn; reads "your taste, ported" as something working FOR them. Folder schema locked at `SCHEMA_VERSION = 1`. 33-surface browser smoke gate passing (`python scripts/browser_smoke.py`). 1402 tests passing, 37 doc-consistency guards green (launch-credibility regression suite: cited councils + install commands + binary asset freshness + brand-axis verbatim across surfaces + numeric MCP tool-count claims pinned to mcp_server.py — see `tests/test_doc_count_consistency.py`). Memory viewer (`~/.trinity/portal_pages/memory.html`) ships with the launchpad and renders the lens hierarchy (core, lens, topics, vocabulary) plus picks + routing scoreboards: markdown via `marked`, picks/routing as schema-aware Reader views, topics as an Obsidian-style force-directed graph (d3-force) over centroid cosine similarity. **basins.py clusters by thread (transcript_id mean centroid)** — a multi-turn conversation contributes one point to k-means instead of fragmenting across N basins; per-basin `representatives` carry the full turn list per representative thread, viewer renders click-to-expand. All sub-pages (memory viewer, live council, council review) share the `.trinity-topbar` nav pattern (pill `← Launchpad`, page title, optional secondary action) defined in `design_system.SHARED_CSS`. **v1.5 cortex Weeks 1–5 shipped end-to-end** (see [`CHANGELOG.md`](CHANGELOG.md) 2026-05-12 entry for the full list): 11 MCP tools (canonical 6 + v1.5 `ask`/`get_picks`/`mark_pick_wrong` + launch-arc `handoff`/`get_eval_summary`); cortex consolidation with **structured geometric prior** (geometric median centroid via Weiszfeld iteration, 6-component `trust_score` with the 6th being mean-cosine-to-median coherence, manifold-dim + bimodality flag fed to the extraction prompt so the flagship does rule-extraction-on-structure not geometry-in-language); **chairman-audit-mode** (`consolidate --audit` runs an independent second flagship to catch drift; loud-fails on stderr); **override mechanism** (CLI `cortex-override` + MCP `mark_pick_wrong`; halves effective trust per click; persists across consolidations); **sigmoid-blended chairman picker** (smooth cold-start→personalization, no hard cut at n=1); **user-verdict-weighted personal routing table** (record_outcome signal flows into aggregation at 0.7 weight); **tool-triggered incremental ingest** (`ask`/`search_prompts` scan new transcripts within 1s, no manual seed re-run); **HF Hub offline default** (`main()` pins `HF_HUB_OFFLINE=1` so Trinity never makes outbound Hub calls at runtime); launchpad surfaces: personalization-% column, Health column (audit / bimodal / override badges with hover-titles), evidence-chip links to source councils. `cortex.py` split: math helpers extracted to `cortex_geometry.py` (304 LOC, dependency-free). Loop Constitution substrate removed pre-launch (was 1,396 lines of v2-trajectory code; the mechanic will be rebuilt leaner inside v1.6's `plan_and_execute`). **Next trajectory = v1.5** (target ship June 3, 2026): the MCP-primary two-tier tool surface is feature-complete; remaining work is calibration data + the v1.6 follow-ons noted in [`docs/spec-v1.5.md`](docs/spec-v1.5.md) "Open questions" (Ollama-vs-MLX preference, cortex-vs-lens cross-check). The Sakana TRINITY paper (arXiv:2512.04388) validates the architectural trajectory but their 3B vs 7B ablation shows the value is in prompt-engineering quality not routing decision — so v1.5 uses a flagship model with cortex context instead of a trained 7B. The trained-coordinator path in [`docs/spec-v2.md`](docs/spec-v2.md) is **sunset** as of 2026-05-11; reopens only if v1.5 hits a quality ceiling on real user data.

**The wedge is structural, not technical.** The three labs are commercially prevented from helping you use a competitor. Someone outside the labs has to ship the layer above them. That's the only sentence the marketing site has to land.

**The moat is the ledger.** Every council emits structured Routing JSON to `~/.trinity/council_outcomes/<id>.json` — `agreed_claims`, `disagreed_claims` with `why_matters`, `winner`, `provider_scores`, `routing_lesson`. Every user click feeds `record_outcome` → `~/.trinity/council_feedback.jsonl` + `outcome.metadata.user_verdict`. Frontier providers can't see the cross-model preference signal; Trinity persists it locally. The personal routing table is computed on-demand from the outcomes directory (no separate state file). Trinity rides on subsidized consumer subscriptions and never pays per call. v1 is free forever; revenue model deferred (see `docs/spec-v2.md` for held hosted-capability description, no pricing committed).

## Architectural commitments (load-bearing, not negotiable)

1. **No LLM calls outside councils.** Ingest, embedding, theme assignment, search ranking, clustering — pure embeddings + heuristics + metadata. The only LLM invocations Trinity makes are council member calls and chairman synthesis calls, both riding user subscriptions.
2. **Prompt content never uploads.** Even with v1.1 aggregation enabled, only categorical routing labels (`task_type`, `provider_scores`, `winner`) leave the machine. Anonymous, opt-in only.
3. **Local-first inference.** Phase 9's learned router runs on the user's hardware. No hosted controller. No per-call API billing.
4. **Subsidized consumer credits as cost basis.** Trinity dispatches via the user's own CLI subscriptions (Claude Code, Codex, Gemini CLI, Cowork). If anyone proposes a hosted API tier, push back hard — that destroys both cost basis and privacy.
5. **HF Hub offline by default.** `main()` pins `HF_HUB_OFFLINE=1` + `TRANSFORMERS_OFFLINE=1` via `setdefault` at startup. The embedding model is pulled once via an explicit `huggingface-cli download nomic-ai/nomic-embed-text-v1.5`; after that Trinity loads from `~/.cache/huggingface/hub/` and never contacts the Hub during normal operation. Privacy + reliability invariant — no surprise outbound calls from the running system, no telemetry to upstream model hosts, MCP child processes inherit the env so the guarantee propagates through every spawn.

## Patterns extracted from the fixes (meta-principles)

241 commits since April, 86 of them on 2026-05-12 alone. The recurring
shapes that earned their rules by costing time:

1. **Lossless serialization round-trips.** If `to_dict()` writes,
   `from_dict()` must return the same dataclass. `basins.py:68` capped
   `prompt_ids` at 50 entries "for readable JSON" — `load_basins()`
   round-tripped through that JSON, then `basin_for_prompt()`
   silently returned `None` for any prompt beyond #50, breaking the
   bulk of every multi-prompt basin. Truncation "for display" belongs
   in the renderer, not the serializer.

2. **File:// is the substrate.** Trinity opens via the macOS desktop
   shortcut at `file:///…/launchpad.html`. New static pages can't
   `fetch()` because modern browsers block file:// XHR. Inline data
   at `portal-html` time the way `live_council.html` does its thread
   manifests (`window.__TRINITY_COUNCIL_THREAD__`). Memory viewer's
   first cut required `trinity-local serve`; second cut inlined.

3. **Filter at the boundary, not the consumer.** Trinity's own
   dispatch prompts ("You are extracting durable facts…") get
   captured into the user's CLI transcripts as role=user, then
   re-ingested as if the user typed them. The only correct filter
   point is `_is_user_facing_prompt` in `ingest.py`. Filtering at the
   launchpad autofill consumer was whack-a-mole — replay-history hit
   the same poisoned data; vocabulary distillation did too.

4. **When you fix a bug, audit for its shape.** Vocabulary
   distillation hit a 5000-node cap because `iter_prompt_nodes()`
   defaults to capped. Audit found 5 more callers with the same
   bug — basins.compute_basins, bootstrap_pairs, replay,
   incremental_ingest, me/turn_pairs. Bug shapes repeat; grep for
   the pattern, not just the symptom.

5. **Real-data validation is the substantive test.** Unit tests
   catch regressions of known bugs. Running `trinity-local <command>`
   on 46k prompts catches scale/shape bugs that synthetic ≤10-vector
   fixtures hide: vocabulary OOM at 19 GB, cross_provider_pairs
   running 106 minutes on pure-Python cosine, basins NaN poisoning,
   doctor reading pre-rename paths, replay-history dup-flooding, the
   basins prompt_ids round-trip. Synthetic data passes; production
   shape doesn't.

6. **Test fixtures must mirror production shape.** A test that gave
   30 fixture nodes the same `transcript_id="t"` collapsed under
   thread-aware basin clustering (correct behavior — one thread →
   one cluster). Fixture had to vary `transcript_id` to exercise the
   k-means path. If the synthetic shape isn't the production shape,
   the test silently passes broken code.

7. **Clean renames before shipping.** Trinity hasn't shipped yet, so
   `memory/` → `prompts/`, `me-build` → `lens-build`, `portal_*.py`
   → `launchpad_*.py`, `task_kind` → `task_type` all happened
   without deprecation aliases. Aliases accumulate maintenance debt
   that compounds; once shipped, you pay them forever. "We haven't
   shipped anything yet, so no need to worry about deprecation. Just
   do it cleanly without any cruft." Treat that as policy until v1.0
   ships.

8. **Numeric claims in long-form docs drift.** "8-surface smoke",
   "541 tests", "571 tests", "657 tests" all appeared in
   claude.md/product-spec.md/CONTRIBUTING.md after the actual counts
   had moved. Either don't put numbers in prose docs, or treat them
   as canonical-source-of-truth-managed (CHANGELOG entries are
   timestamped + okay to be stale; status-block claims are not).

9. **Show user content, not statistical summaries.** TF-IDF top
   terms ("get / give / like") surface vocabulary — not intent.
   When a cluster's label needs to convey "what this is about",
   prefer the actual closest-to-centroid prompt over aggregated
   tokens. Same principle: representatives over `top_terms` in the
   memory viewer, prompts in the autofill over "you-might-also-like"
   summaries.

10. **Cluster at the unit users think in.** Multi-turn conversations
    are threads, not turns. K-means on per-turn embeddings fragments
    "draft a tweet → make it shorter → add a CTA" across three
    basins. K-means on thread-mean centroids puts it in one. The
    user's mental model is the conversation; the topology has to
    track that.

11. **Shared UI primitives live in `design_system.py`.** Three
    sub-pages (memory viewer, live council, council review) all
    grew bespoke `.page-header-bar` / `.topbar` CSS independently.
    Drift accumulated invisibly until a user flagged the
    inconsistency. New rule: when DESIGN.md describes a UI contract,
    the CSS for that contract lives once in `SHARED_CSS`. Pages
    reference, don't re-type.

12. **Smoke selectors are structural, not text-based.** Surface 6
    used `a.button.ghost` + "Back to Launchpad" text-match — broke
    when the topbar pattern changed the text to "← Launchpad".
    Switched to `.trinity-topbar a.topbar-back`. Selectors that
    track structure survive normal copy edits; text-matching
    selectors couple the regression guard to UX copy.

13. **Design system is a contract, not a suggestion.** DESIGN.md
    explicitly forbids "purple or neon accents". Memory viewer's
    first cut shipped `#6366f1` indigo + `#8b5cf6` violet anyway,
    because nothing enforced the palette. New rule: when adding a
    new surface, the palette has to come from `design_system.COLORS`,
    not from "what looks good right now".

14. **Every shipped feature gets a smoke regression guard within
    one tick.** Observed across four consecutive feature ticks:
    tick #8 health row → wired in-tick; tick #13 per-file banner →
    tick #14 Surface 16; tick #15 cross-memory chips → tick #16
    Surface 10 extension. The smoke suite grows in lockstep with
    shipped surfaces — when a feature lands today, tomorrow's run
    catches it if it breaks. The selector is structural (per
    principle #12); the assertion tolerates legacy-data variants
    (Surface 13's lens empty-state, Surface 10's xlink-less legacy
    councils) by treating the *consistent* invariant as the gate,
    not a fixed expectation. Without this discipline, smoke
    coverage drifts behind feature volume and the gate stops
    catching real regressions — it just becomes wallpaper.

15. **When you extend a regression guard, update its description in
    the same commit.** Sub-rule of #14, earned its own bullet after
    tick #22. Five smoke surfaces (3, 10, 13, 15, 16) had gained
    real assertions across ticks but the docstring header still
    described their pre-extension state. The fix is small; the
    failure mode isn't — a future contributor reads "Surface 3:
    >=1 row, columns readable" and thinks the cortex basin links
    aren't covered, so they add a redundant check or, worse, drop
    the existing one because it looks orphaned. Same shape applies
    to docstrings on `_memory_health`, the design system COLORS
    dict, etc. — every doc that's load-bearing for "what does this
    function/gate actually do" needs to evolve with the code or it
    becomes invisible armor.

16. **In numerical pipelines, one bad value is worse than zero.** A
    single non-finite row in a cosine similarity matrix propagates
    NaN through every column-wise inner product downstream — the bad
    row corrupts every *other* thread's distance, not just its own.
    Tick #55 hit this exact shape (`thread_lid` poisoned downstream
    `depth_score` for ~40 unrelated `gemini_takeout` transcripts via
    one stale-embedding row). The fix is two-layer: gate at the write
    boundary (cache + `embed`/`embed_batch` sanitize) so the bad
    value can't enter the pipeline, AND keep consumer-side filters
    as defense in depth because the cost-on-leak is catastrophic.
    Generalizes beyond embeddings: any numpy/matmul-shaped pipeline
    (Elo updates, attention layers, normalization passes) has this
    same one-poisons-many failure mode. Filter at the boundary; the
    cache is the boundary's permanent half.

17. **Three inline shapes of the same check means a missing helper.**
    Tick #56 found the NaN filter inlined three different ways —
    `_embedding_is_finite()` in `me/depth.py`, inline
    `any(v != v or v == inf …)` in `me/basins.py`,
    `_valid_embedding()` (bundled with a dim check) in `me_builder.py`.
    Two more consumers (`cross_provider_pairs`, `vocabulary`) had
    forgotten the check entirely. When the same logical operation
    is implemented inline in ≥3 places with subtle differences, that
    drift is a bug magnet: principle #4 ("audit for shape") only
    finds bugs that have already manifested. Promote to a function
    at threshold N=3 so the audit-for-shape future-you has one name
    to grep. Distinct from premature abstraction — the function
    already exists, it's just inlined N times.

18. **Embedding similarity isn't structural similarity.** Trinity's
    embedder (nomic-768d) measures *topic-near*. Two fixes with the
    same shape (basins.py prompt_ids cap → silent membership lookup
    failure; vocabulary 5000-node cap → corpus truncation) live in
    completely different parts of embedding space because they talk
    about different domains. Meta-principles — and any other
    "structurally similar despite topic-different" signal — need a
    second pass: extract a label per item via chairman/rule-
    extraction, embed *those*, then cluster across topic-different
    basins. The principles.md pipeline (task #109) is the concrete
    artifact; the lens Stage 4 post-filter ("drop pairs whose
    tension evidence sits in a single basin") is the same shape at
    a different level. When asked to find "patterns that recur,"
    don't reach for the embedder — reach for a label extractor first.

19. **Tests must not mutate process-global state at module level.**
    Tick #63 found `os.environ["TRINITY_HOME"] = tempfile.mkdtemp(...)`
    at the top of `test_knn_advisor.py` and `test_knn_analytics.py`.
    pytest imports every test module during collection, before any
    test runs — so the env var leaked for the rest of the process
    and the real-corpus depth tests (the strongest gate Trinity has
    on `depth_score` non-degeneracy) silently skipped with
    "0 embedded prompt nodes" for an unknown stretch of session
    history. The leak is *worse* than #14's "guard becomes wallpaper"
    because the guard didn't even become visible wallpaper — it
    skipped invisibly. Scope test state via fixtures (`autouse` +
    `monkeypatch.setenv`), never at module top-level. Enforced by
    `tests/test_no_module_level_env_mutation.py`, an AST scanner
    that fails the suite if any `tests/test_*.py` mutates
    `os.environ` or `sys.path` outside a function/class. Same shape
    as #14 (regression guards must run to count) at a meta level:
    the guards must not be silenced by their neighbors.

20. **Duplicated facts drift in the oldest surface.** Generalization
    of #8 beyond numeric claims. Three concrete cases this session:
    test count 791 stuck in claude.md status block while CHANGELOG
    and the smoke output had moved (#57); the depth-score formula
    in `commands/depth.py`'s module docstring + argparse `help=` said
    `corpus_distance × log(1+inter_turn) × log(1+LID)` for two months
    after tick #54 switched the composite to additive, while the same
    file's print footer had the correct formula (#87); claude.md's
    "### The six canonical MCP tools" section heading + "These are
    the only public surface" intro stayed at 6 even though the same
    file's status block and verified-status section both correctly
    said 9 (#88). The rule: when a load-bearing fact (formula, count,
    name, signature) lives in N≥3 places, the *oldest* surface drifts
    behind because edits typically touch the recent/top surface. The
    fix is either single-source-of-truth (compute the claim at render
    time) or pin every duplicate in the same commit so future-me
    notices on a single grep. Distinct from #8 (specifically numeric)
    — this covers formulas, headings, type signatures, command-help
    strings, anywhere prose carries a fact that another file owns.

21. **Public claims need regression guards at the surface that ships
    them.** Earned 2026-05-14 (T-1 of v1.0 launch) when a systematic
    pass through launch-facing surfaces caught 14 separate drifts —
    each a "claim X is made in surface Y; the private state of truth
    in surface Z doesn't match" shape. Shapes ranged from launch
    copy (cited councils not in repo, `[date]` placeholders, wrong
    github owner) to programmatic (pyproject version+description
    stale, schema $id pointing at an unregistered domain, smoke-
    install hardcoded tool list 2 behind reality, bundled `/trinity`
    skill using a 404 install command, README hero install command,
    founder essay install command, demo recording timecode install
    command, "verifier" reintroduced after the rename pass) to
    binary assets (launchpad screenshot 6 days behind the
    launchpad's source; me-card example PNG 6 days behind
    me_card.py). Each had been live for hours-to-weeks before the
    audit. The fix is two-step: (a) fix the immediate drift, (b)
    add a test under `tests/test_doc_count_consistency.py` that
    reads the canonical source of truth (`git remote get-url`,
    `trinity-local --help`, file mtime, repo glob) and asserts the
    public-facing surface matches. Treat the test as the surface's
    own scar tissue from the bug — same shape can't quietly recur.
    The audit trail itself becomes a launch-credibility artifact —
    "open-source the trail" is literal when the trail names each
    bug + fix + guard by commit hash. By T-1 close: 18 doc-
    consistency guards green; each one earned by a real catch.

## Forward arc

What the commit volume + theme distribution suggests for the next 50–100
commits. **Updated 2026-05-13** after ticks #69–80 shipped most of the
original three pillars and surfaced a fourth.

**Pillar 1 — Action-from-view.** Mostly shipped. The remaining bullet
is the meaty one:

- ~~Click a basin → launch a council~~ ✓ Surface 19
- ~~Cortex pick wrong → one-click veto from picks Reader~~ ✓ Surface 17
- ~~See a rejected lens → "rebuild lens.md" link~~ ✓ Tick #76 chip
- ~~Cortex/routing card → rebuild chip~~ ✓ Tick #77 chip
- ~~Per-file rebuild on memory viewer~~ ✓ Surface 18
- **Open**: click a turn in an expanded thread → "open the source
  session" or "replay this through the council." Needs the turn UI
  to carry source-prompt metadata and a `start_council` shortcut
  call. Bigger than a single tick — split into "turn carries
  source_id" + "replay button wired."
- **Deferred**: per-pick regeneration. The current rebuild chips
  fire the full `consolidate` / `lens-build` — granular per-pick
  regeneration would need a different CLI surface.

**Pillar 2 — Cross-memory navigation.** Largely shipped via Surfaces
21–27 (topology↔picks centroid match, picks↔topology with `?basin=`,
routing→topology chip triangle, launchpad cards → topology, lens →
basins_spanned chips). The remaining gap is the topic graph
distinguishing picks-having basins from noise basins visually —
data is there (Surface 22 styles `.pick-basin` nodes), the visual
contrast could be tighter.

**Pillar 3 — Drift surfacing.** Shipped via Surface 15 (memory health
card on launchpad) + Surface 16 (per-file health banner inside
viewer) + memoryHealth.issues structured payload with one-click
command chips.

**Pillar 4 (NEW after ticks #69–74) — Supervision-signal moat.** Tick
#69's real-corpus census found 3 of 19 outcomes carry verdicts (16%
capture rate). Trinity's moat thesis ("the personal ledger of
cross-model preferences other labs can't see") rests on this signal;
84% silent means the ledger is mostly empty. 6-stage defense-in-depth
shipped:

- Census (#69) — `~/.trinity/council_outcomes/*.json` walk surfaces
  the real ratio
- Visible (#70) — launchpad eyebrow "N of M rated" + accent prompt
- Verify-after (#71) — 3s `loadOutcomeScript` re-fetch after click;
  badge flips to "Save failed" when `user_verdict.user_winner` is
  absent post-fire
- Preempt-CLI (#72) — `doctor` flags missing macOS Shortcut + verdict_rate
- Preempt-UI (#73) — launchpad top-banner mirrors the doctor check
- **Active nudge (#107)** — MCP `run_council` and `get_council_status`
  responses carry a structured `rate_action` field when an outcome is
  completed-but-unrated. The agent (Claude Code / Codex CLI / Gemini
  CLI) reads its own tool result, sees the hint, surfaces the rating
  prompt to the user inline — no launchpad detour. `record_outcome`'s
  MCP description was extended to teach the agent to fire it on
  `rate_action`. The first five stages were *visibility* (passive
  surfaces the user has to seek out); this one is *action at the
  moment of decision* — the missing kind of pressure.

**Open under Pillar 4**: even with the active nudge, an agent that
never calls `get_council_status` after a fire-and-forget `run_council`
won't see the hint. Measuring real-corpus uplift requires waiting for
the next consolidation pass — `rate_action` ships with no opt-out
because abandoning a low-cost field through the MCP surface costs the
agent nothing if it ignores the hint. If uplift is <2× after a week,
revisit by surfacing the nudge through the macOS notification system
(`notifications.py` already exists) on council completion.

**What's NOT in the forward arc:**

- More rename churn. The cleanup discipline burned off the major
  drift; future drift is bounded by the smoke selectors + the AST
  scanner from tick #64.
- More architectural pivots. The trained-coordinator path is sunset;
  v1.5 spec is feature-complete; v2 reopens only if v1.5 hits a real
  ceiling on user data.
- More launchpad surfaces. The launchpad is the home. New artifacts
  go to sub-pages with the `.trinity-topbar` shape, not as new
  launchpad cards.
- `principles.md` pipeline (task #109). Data-gated — 19 council
  outcomes is too sparse for k-means clustering in 768-d space, and
  the verdict capture rate has to climb first. Revisit when N≥100 AND
  verdict rate ≥50%.

**The unblocking question for v1 ship:** is the supervision-signal
loop actually firing on real installs? The view side closes (user can
see picks, rebuild memories, navigate cross-memory). The act side
closes (rebuild chips, veto chips, launch chips). The remaining gate
is the *learn* side — does the verdict from each council reach
`user_verdict.user_winner`? The 6-stage arc (#106 active-nudge being
the latest) made the failure mode loud and built the active prompt;
measuring uplift is the next month's work.

## Launch arc (v1.0 → v1.1) — distribution beats elegance

Setting alongside the Forward Arc above, but on a different axis: that
arc is about what the app *does internally*. This one is about how the
app *reaches users*. During the consumer-AI land-grab phase, the
dominant pressure is being in the right dropdowns at the moment users
go looking. Five workstreams, ordered by leverage:

**Distribution correction (2026-05-14):** non-coders must launch Trinity like a
desktop app, Cowork-style. `trinity-local` remains the complete engine, but
`Trinity.app` is the acquisition and daily-use surface for ordinary users. The
mobile app starts as a review-link companion: open the web review page, rate the
winner, mark bad picks, and write the same ledger through the paired desktop.
Full phone-to-desktop dispatch comes after that rating loop is reliable.

1. **MCP-dropdown distribution** (task #114). Get Trinity into the
   curated MCP server lists for Claude Desktop, Codex CLI (whose MCP
   support landed earlier this year), Cursor, Cline, Continue. Each
   registry is its own submission. Being in the dropdown beats being
   technically perfect. `install-mcp` already wires the three CLI
   harnesses; the missing surface is *discoverability* — users who
   don't know Trinity exists never run `install-mcp`.

2. **First-run wow — cross-provider continuity, NOT council depth**
   (task #115, reframed 2026-05-14). The 60-second demo path: user
   asks Claude a complex question, then mid-conversation runs
   `handoff gemini` (or agent suggests it). Gemini picks up exactly
   where Claude left off — no re-context, no copy-paste. ONE answer
   that visibly knew what the prior model said. "Wait, how did it
   know?" IS the demo working. Structurally non-refutable: only
   Trinity has the cross-provider prompt index, so only Trinity can
   do continuity (Anthropic can't read OpenAI's transcripts, etc.).

   Council depth is the *quality engine* (Trinity's continued
   responses get better as the corpus learns the user's lens). But
   council comparisons are a B-grade hook — they require the user
   to evaluate three answers. Continuity is the A-grade hook because
   the wedge demonstrates itself in one beat.

   Gemini-handoff branch is especially strong because Gemini brings
   Google data (Gmail/Drive/Calendar) Claude/GPT can't see — a
   "ask Claude about your codebase, hand off to Gemini for related
   emails" demo lights up a capability no provider can match alone.

   Depends on new handoff infrastructure: tasks #119 (mechanism),
   #120 (demo recording), #121 (Gemini-Google branch). See
   memory/killer_hook_cross_provider_continuity.md.

3. **Cross-provider benchmarks** (task #116, methodology by #122).
   Publish Trinity vs. Opus on design, vs. GPT-5 on coding, vs.
   Gemini on long-context. NEW METHODOLOGY 2026-05-14: instead of
   picking synthetic benchmark prompts, use the corpus-based eval
   harness (#122) to score each provider against the user's
   *actual* prompts + rejection signal. The marketing headline
   becomes "Model X scored 0.73 on YOUR kind of question" —
   empirical, personal, and structurally non-refutable because
   only Trinity has cross-provider rejection signal. No provider
   can build the equivalent eval suite (Anthropic only sees Claude
   transcripts; OpenAI only sees GPT; etc.). The harness produces
   routing signal AND benchmark content from one mechanism. See
   docs/spec-v1.5.md "Personalized evals from corpus history".

4. **Standardize `~/.trinity/`** (task #117). If Aider, Cline,
   Continue adopt the same preference-corpus schema, Trinity becomes
   a standard, not a product. Standards have ~10× the longevity of
   products. Push a JSON Schema for `council_outcomes/*.json` +
   `memories/*` into the open while we have first-mover authority.

5. **Subsidy-window narrative** (task #118). Tell users explicitly:
   "Programmatic credits are subsidized right now. Build your
   preference corpus while it's cheap; the corpus has lifetime
   value once subscriptions tighten." Legitimate FOMO motivator
   because it's true. Threads through launch copy, README hero, and
   the onboarding ribbon.

**Priority filter for the cron loop:** when picking the next tick,
prefer one that advances workstreams 1–5 over one that doesn't.
Internal cleanup is OK only when it's a hard blocker for one of
these. Tasks #114–118 break out one per workstream.

## Glossary (load-bearing terms)

A few words do specific work; they get conflated otherwise:

- **prompts** — what the user owns (raw, indexed in `~/.trinity/prompts/`; renamed from `memory/` per Tier 1 #1, automatic one-time migration in `memory_dir()`). Inputs to dream.
- **dream** — the verb only Trinity has. Reads prompts, emits core memories (offline, your data).
- **core memories** — the three *thinking* memories that compose your lens. The four-level hierarchy chairman reads top-down (drill only when needed):

  | level | file | what's in it | brain analog | status |
  |---|---|---|---|---|
  | identity | `core.md` | one-paragraph manifesto | distillation | shipped |
  | tensions | `lens.md` | paired tensions you'd reject vs accept | value | shipped |
  | basins | `topics.json` | clusters of subjects + evidence map for lens | semantic | shipped |
  | language | `vocabulary.md` | anchors + homonyms + synonyms | linguistic | shipped |

  Generation runs bottom-up (vocabulary + topics → lens → core); reads run
  top-down (core first, drill to lens / topics / vocabulary on demand). The
  three thinking files live in `~/.trinity/memories/`; `core.md` is the
  distillation at `~/.trinity/core.md`. Together they ARE the lens — not
  four separate "memories" — and that is what the launchpad surfaces as one
  card with drill-down chips.

  *Deferred:* `principles.md` (meta-cognitive, data-gated, task #109).

- **scoreboards** — operational bookkeeping derived from council outcomes,
  not cognitive shape. Excluded from distill (chairman doesn't read them as
  identity context) and from the memory viewer's cognitive surface; surfaced
  on the launchpad routing card. Two files under `~/.trinity/scoreboard/`:

  | file | what's in it | what reads it |
  |---|---|---|
  | `picks.json` | extracted model-selection rules per task_type | `ask`, chairman picker |
  | `routing.json` | per-task-type provider track record (numbers) | route, chairman picker, launchpad |

  Both are computed from `council_outcomes/` (the user verdicts are the
  ground truth). `picks.json` is a cortex-extraction over the outcomes;
  `routing.json` is the on-demand aggregation frozen for read-only display.

- **core** — the singular distillation at `~/.trinity/core.md`. One
  paragraph that subsumes the three thinking memories above. Chairman reads
  it FIRST on every council, falls through to lens / topics / vocabulary
  only on demand.
- **council** — multi-model deliberation (parallel or chain) ending in chairman synthesis.
- **chairman** — the synthesis model in a single council. Reads `core.md`, emits structured Routing JSON. Per-call role.
- **Conductor** (v1.5+) — flagship model that *picks which model gets which sub-task* across a session/plan. Different role than chairman; same model family may play both.
- **harness** — the CLI/IDE the user is working inside (Claude Code, Codex CLI, Gemini CLI, Cursor, Cowork). Trinity registers as an MCP server inside each.
- **seat / member** — a provider acting as one voice in a council. Code uses `members=[...]`; marketing copy will use `seat` (table metaphor).
- **task_type** — the short label for "what kind of question this is" (heuristic on input, also emitted by chairman). NOT the same as `category` (coarser LMArena-aligned grouping).

The map mirrors the tagline: prompts (what you own) → dream (the verb) → core memories (what dream creates, plural) → core (the distillation, singular). When in doubt about a name, look at the brain analog and pick the one that matches what the file actually stores.

## Calling the council from inside Claude Code

Trinity is exposed as an MCP server. v1.7 ships 6 canonical tools (`route`, `run_council`, `record_outcome`, `search_prompts`, `get_persona`, `get_council_status`); v1.5 adds `ask` (cheap default single-call routing), `get_picks` (agent-facing introspection into extracted picks), and `mark_pick_wrong` (user-veto on a pick — halves effective trust per click, persists across consolidations); launch-arc adds `handoff` (cross-provider continuity) and `get_eval_summary` (per-axis benchmark scores) — 11 total. `run_council(responses=[...])` covers what `judge` used to do — pre-supplied member outputs go straight to chairman synthesis, one model call instead of N+1. When working in this repo, **call `mcp__trinity-local__run_council` for hard questions** and `mcp__trinity-local__ask` for quick single-call consults. The chairman reads `~/.trinity/memories/lens.md` and condenses members through *this user's* taste — that's what makes the council more useful than just asking Claude alone.

Bar for "hard":
- Two senior engineers could reasonably disagree (architecture, API shape, refactor scope, naming, abstraction-vs-duplication)
- I catch myself answering "depends on…" or "you could go either way"
- The decision compounds (data schema, public surface, anything user-visible)
- The user has previously pushed back on my first answer in this area

Skip the council for: trivial bugs, syntax/API lookups, mechanical refactors, information retrieval. Each council costs 3 member calls + 1 chairman call — wasted on questions with one right answer.

After a council, treat the chairman's synthesis (especially `agreed_claims` / `disagreed_claims`) as the source of truth for what the answer should be, then explain it in my own words back to the user. Call `mcp__trinity-local__record_outcome` when the user picks a winner so the personal routing table improves over time.

## Install / surface notes

Run `trinity-local install-mcp` once to register Trinity's MCP server with Claude Code (`~/.claude.json`), Gemini CLI (`~/.gemini.json`), and Codex CLI (`~/.codex/config.toml`). Each harness spawns `trinity-local --mcp` as a stdio child when it starts; it lives until the harness exits. ~62MB resident while connected.

The launchpad → macOS Shortcuts → `~/.trinity/bin/trinity-dispatch` → CLI pipeline is independent of MCP — it's one-shot subprocess at every step, no persistent process required. So the launchpad keeps working even if MCP is disabled.

## MCP server hot-reload (development only)

When MCP is enabled and you're actively editing Trinity, set `TRINITY_MCP_WATCH=1` to enable a file watcher that calls `os._exit(0)` on any `.py` change. The MCP launcher auto-respawns with fresh code. Typical edit → reload cycle is <1s. Never enable in shipped configs.

**Caveat for tool-list changes**: Claude Code caches the tool list from the first connection. Adding *new* MCP tools (vs. modifying existing handlers) may still require a Claude Code restart to make them visible to the harness.

## Architecture (post v1)

### CLI dispatcher

Entry: `src/trinity_local/main.py` — thin dispatcher only. Command modules under `commands/` (30 modules in the table below; 4 more — `distill`, `merges`, `stats`, `trust` — are ancillary maintenance/debug tools intentionally off the user-surface table):

| Module | Key commands |
|--------|-------------|
| `commands/ingest.py` | `features`, `examples` |
| `commands/tasks.py` | `task-create`, `task-show`, `task-sync`, `bundle-create`, `launch-create` |
| `commands/council.py` | `council-start`, `council-run`, `council-prompt`, `council-outcome`, `council-launch`, `council-rate`, `council-stop`, `council-share`, `council-iterate` (replaces former `auto-chain`; `--rounds N` for sequential refinement) |
| `commands/council_last.py` | `council-last` (rerun the most recent council bundle against the current model lineup) |
| `commands/portal.py` | `portal-html`, `open-review`, `serve` (local HTTP server for launchpad — alternative to file://) |
| `commands/seed.py` | `seed-from-taste-terminal` |
| `commands/replay.py` | `replay-history` |
| `commands/me.py` | `lens-build` (chairman-driven), `lens-show` |
| `commands/me_card.py` | `me-card` (render a paired-tension lens as a 1200×630 PNG) |
| `commands/actions.py` | `action-list`, `action-suggest`, `action-council`, `action-notify`, `action-complete` |
| `commands/shortcuts.py` | `shortcut-url`, `shortcut-run`, `action-shortcut`, `shortcut-setup`, `shortcut-install` |
| `commands/watch.py` | `watch-once`, `watch-loop`, `ingest-recent` |
| `commands/review.py` | `review` |
| `commands/adapters.py` | `adapters` |
| `commands/status.py` | `status` |
| `commands/cache.py` | `cache-stats`, `cache-clear` |
| `commands/cortex.py` | `consolidate` (extract routing patterns; supports `--audit` for independent-chairman drift check), `cortex-override` (user-veto on a rule; halves effective trust per click; `--reset` clears) |
| `commands/vocabulary.py` | `vocabulary` (scan prompts for terminology overloads — one word ↔ two meanings; two words ↔ one meaning. Emits `~/.trinity/memories/vocabulary.md`; load-bearing Stage 4 of the lens pipeline) |
| `commands/doctor.py` | `doctor` (preflight: providers / MCP dep / writable Trinity home) |
| `commands/dream.py` | `dream` (the one-command cold-start: discover cross-provider pairs across ALL embedded transcripts → synthesize each as a virtual council → consolidate cortex → rebuild /me lenses; Anthropic's *Dreaming* on the user's own data) |
| `commands/bootstrap_pairs.py` | `bootstrap-pairs` (just phase 1+2 of `dream` exposed standalone — discover clusters + synthesize, no consolidate/lens-build follow-up) |
| `commands/depth.py` | `depth-show` (top-N threads by depth-score composite: corpus_distance + 0.5·log(1+inter_turn) + 0.5·tanh(LID/10); LID gated to N≥5 turns by default, `TRINITY_LID_MIN_TURNS` env tunes) |
| `commands/unrated.py` | `unrated` (list councils without user verdict; Pillar 4 funnel-widening — gives the user their rating backlog one-line-per-council with chairman pick + copy-paste rate command) |
| `commands/handoff.py` | `handoff <provider>` (cross-provider conversation continuity — task #119, launch-arc workstream #2; pulls recent turns from `~/.trinity/prompts/` index, dispatches to target provider with "continue this thread" frame; mirror of `mcp__trinity-local__handoff`) |
| `commands/eval.py` | `eval-build` / `eval-stats` / `eval-run` / `eval-show` / `eval-share` (corpus-based eval harness — task #122; `eval-build` produces the suite from `me/rejections.jsonl`, `eval-run --target <provider>` dispatches each prompt + scores via judge against `lens.md`, `eval-show` renders a past run with per-axis bars + top/bottom samples without re-dispatch. `eval-share` renders the result as a 1200×630 PNG share card with install CTA + GH Pages URL — the tweet-shaped artifact for "Gemini scored 0.83 on YOUR kind of question.") |
| `commands/metric.py` | `metric rate-limit-saves`, `metric dispatch-summary` (read aggregated dispatch metrics from `~/.trinity/analytics/`) |
| `commands/research.py` | `replay`, `rank`, `hard`, `hardeval`, `analytics`, `embed` (off the live product path — research pipeline only) |
| `commands/install.py` | `install-mcp`, `install-hooks` |
| `commands/update.py` | `update` (pull latest, refresh MCP configs, verify with doctor — the post-curl-bash self-update mechanism; ships the staleness check `doctor` surfaces) |
| `commands/telemetry.py` | `telemetry-show`, `telemetry-enable`, `telemetry-disable`, `telemetry-reset-id`, `telemetry-endpoint`, `auto-chain-enable`, `auto-chain-disable`, `auto-open-enable` (post-council `open <review_path>` on macOS), `auto-open-disable` |

### Core layers

| Layer | Files | Purpose |
|-------|-------|---------|
| Config | `config.py`, `config.json` | Provider definitions, role/task preferences, `trinity_home()` |
| Providers | `providers.py` | Subprocess wrappers for CLI provider calls |
| Council runner | `council_runner.py` | Parallel + chain-mode multi-model execution |
| Council runtime | `council_runtime.py` | Bundle creation, chairman prompt rendering (with structured JSON contract), Routing JSON parsing, outcome construction |
| Council schema | `council_schema.py` | `PromptBundle`, `LaunchEvent`, `CouncilMemberResult`, `CouncilChainStep` (NEW), `CouncilRoutingLabel` (with `agreed_claims` / `disagreed_claims`), `CouncilOutcome` (with `mode` and `chain_steps`) |
| Council status | `council_status.py` | Live run-state, member streaming, chairman synthesis progress |
| Council review | `council_review.py` | Static HTML review pages, structured Routing label section, live page with streaming member responses |
| Memory | `memory/` package — `schemas.py`, `store.py`, `index.py`, `replay_value.py` | `PromptNode` (atom) + `TurnWindow` (local context) index with replay-value scoring + MMR diversification |
| Embeddings | `embeddings/` — `__init__.py`, `backend_mlx.py`, `backend_tfidf.py`, `cache.py` | `nomic-embed-text-v1.5` at **768d**, batched embed with cache-awareness, Nomic prefix preservation |
| Ingest | `ingest.py` | Parsers: `parse_claude_code_session`, `parse_codex_session`, `parse_gemini_cli_session`, `parse_cowork_session`, `parse_claude_ai_export`, `parse_chatgpt_export`, `parse_gemini_takeout_html`. `iter_prompt_turns(session)` yields clean user-facing turns (sidechain / API errors / synthetic stripped). Gemini Takeout cells are grouped into multi-turn sessions by 30-minute time-proximity (source_format_version "2") so prior-thread context is preserved across cells Google flattened. |
| Thread context | `thread_context.py` | Canonical `build_threaded_prompt()` formatter — prepends preceding-assistant excerpt to short turns ("continue.", "Let me restart.") so fresh models replay with context. Used by both autofill and replay-history. |
| Categories | `categories.py` | Trinity capability categories aligned with the LMArena leaderboard (Coding/Math/Creative Writing/Hard Prompts/Multi-Turn/Instruction Following/Overall). Single source for the task_type→category map and UI labels. |
| Ranker | `ranker/` — `base.py`, `fallback.py`, `heuristic.py`, `knn_ranker.py`, `chairman_picker.py` (NEW), `types.py` | Routing decisions + chairman auto-selection (personal table → global benchmarks → default order) |
| Council outcome | `council_feedback.py` | Append user verdicts; `record_council_outcome` (in `memory/store.py`) propagates to PromptNode |
| State paths | `state_paths.py` | Single source of truth for `~/.trinity/` paths |
| Runtime env | `runtime_env.py` | PATH-injection env builder + `run_with_runtime_env()` (both helpers live in one module — `subprocess_utils.py` was the original plan but the split didn't materialize) |
| Task kinds | `task_types.py` | Single `guess_task_type()` heuristic classifier (no LLM) |
| Refresh | `refresh.py` | `refresh_launchpad()` — single entry for portal regeneration |
| Dispatch | `dispatch_runner.py`, `dispatch_registry.py`, `shortcut_setup.py`, `shortcuts_integration.py` | macOS Shortcuts bridge + dispatch wrapper |
| MCP | `mcp_server.py` | v1.0 canonical 6 + v1.5 `ask` + `get_picks` + `mark_pick_wrong` (see below) |
| Launchpad | `launchpad_data.py`, `launchpad_template.py`, `launchpad_runtime.py`, `launchpad_install.py`, `launchpad_page.py`, `memory_viewer.py` | Static HTML launchpad + memory viewer (memory.html with inlined memory contents) — autofill, personal routing table, council suggestions, 4-chip lens card (core / lens / topics / vocabulary) — picks + routing surface on the routing card |
| Share cards | `me_card.py`, `eval_card.py`, `council_card.py` | Three 1200×630 PNG renderers, one visual language (cream BG + sage accent + serif headline). `me_card` renders the strongest lens, `eval_card` renders an eval run's per-axis bars, `council_card` renders a council outcome's chairman-extracted agreed/disagreed claims. All three carry the same install CTA + `vishigondi.github.io/trinity-local` landing URL; council_card is privacy-safe by construction (chairman fields only, no user prompt or member text) |
| Telemetry | `telemetry.py`, `notifications.py` | Opt-in telemetry settings (privacy-clean), system notifications |
| Adapters | `adapters.py` | Provider adapter detection + transcript counts |
| Research | `research/` package | Offline research pipeline (replay, hard mining, ranking eval) — not on the live product path |

### The eleven MCP tools (`mcp_server.py`)

The full public surface is **11 tools** — 6 canonical (v1.0) + 3 v1.5
additions + 2 launch-arc additions (`handoff`, tick #119, 2026-05-14;
`get_eval_summary`, post-#122). The canonical 6 are the lifecycle
order; the v1.5 trio sits adjacent to the v1.0 supervision loop; the
launch-arc pair surfaces the cross-provider continuity demo and the
empirical-benchmark surface to agents inline.

**v1.0 canonical six (lifecycle order):**

1. **`route(task, harness, available_models, budget, latency)`** → `{mode, primary, challenger, confidence, reason, fallback}`. No model calls — heuristic + k-NN + chairman picker. Cheap, called before the harness picks a model.

2. **`run_council(task, members, mode, sequence, primary_provider, responses)`** → council launched asynchronously. `mode="parallel"` (default) runs members concurrently then chairman. `mode="chain"` runs sequence serially with each step seeing prior outputs. **When `responses=[...]` is provided** (pre-supplied member outputs), skips dispatch and runs chairman synthesis only — one model call instead of N+1, returns the structured Routing JSON inline. This subsumes the former `judge` tool.

3. **`record_outcome(council_run_id, user_winner, accepted, edited, tests_passed, cost_usd, latency_sec, answer_label)`** → closes the supervision loop. Updates `council_feedback`, `CouncilOutcome.metadata.user_verdict`, and the originating `PromptNode` via `memory.record_council_outcome`. **The most important tool** — without it Trinity is a switchboard.

4. **`search_prompts(query, top_k)`** → ranked replay candidates from the hierarchical memory index, scored by `replay_value_score`.

5. **`get_persona()`** → returns `~/.trinity/memories/lens.md`. The chairman already loads this internally, but exposing it lets *any* harness (Claude Code, Codex, Gemini CLI) pull the persona once at session start and tailor responses without an MCP round trip per call.

6. **`get_council_status(council_run_id)`** → in-protocol polling for async councils. Returns status (running/completed/failed/canceled), per-member progress, synthesis state, and outcome summary (winner, agreed/disagreed claims, routing_lesson) when complete. Required for harnesses without filesystem access; also the only way to detect a stuck member without watching `~/.trinity/portal_pages/status/`.

**v1.5 trio:**

7. **`ask(task, harness, available_models, budget)`** → cheap single-call default routing. The 90% case: harness has a question, wants one model's answer with a chairman-blessed verdict, doesn't need a full council. Pulls from cortex picks first (high-trust rule → use directly), falls back to k-NN advisory, finally to heuristic.

8. **`get_picks(basin_id?, min_trust?)`** → agent-facing introspection into extracted cortex routing patterns. Returns `{rules: {basin_id: pattern}, total_basins, returned}` — patterns are keyed by basin_id (cortex consolidation is per-basin, not per-task_type), each carrying provider/reasoning/trust score/source councils inside the pattern dict. `basin_id` filter narrows to one basin; `min_trust` floor filters by `trust_score.value`. Empty cortex returns `{rules: {}, note: "..."}`. Lets a harness inspect what Trinity has learned about which model wins for which basin without firing route().

9. **`mark_pick_wrong(task_type)`** → user-veto on an extracted pick. Halves effective trust per click, persists across consolidations. Same shape as the launchpad's pick-veto chip (Surface 17) but from the agent side.

**Launch-arc addition (tick #119, 2026-05-14):**

10. **`handoff(target_provider, continuation?, num_turns?)`** → cross-provider conversation continuity. Pulls the user's most-recent (user, assistant) turns from the cross-provider prompt index, packages them as "continuing this thread" context, dispatches to a DIFFERENT provider. Target picks up exactly where the prior model left off — no re-context, no copy-paste. This is the mechanism behind the 60-second hero demo (#115/#120). Structurally non-refutable: only Trinity has the cross-provider index. CLI mirror: `trinity-local handoff <provider>`.

11. **`get_eval_summary(target?, eval_id?)`** → latest empirical-benchmark result from the eval harness (task #122). Same data path as the launchpad's Personalized Benchmark card and the CLI `eval-show` — third entry point so the agent can ground "which model is best for me at X" in actual rejection-signal scores rather than global priors. Returns `{has_results, target_provider, aggregate_score, by_rejection_type[REFRAME|COMPRESSION|REDIRECT|SHARPENING], items_total/completed/failed, result_path}` or an empty-state shape with a CTA `next_command` so the agent can suggest the next step.

Internal helpers (`get_status`, `get_elo`, `get_recent_councils`, `watch_once`) remain importable for the launchpad but are NOT exposed via MCP.

### State layout

Live state under `~/.trinity/` (overridable via `TRINITY_HOME`):

```
~/.trinity/
├── todos/                          # Durable todo records (was `tasks/` pre-rename — disambiguates from `task_type` classifier label)
├── actions/                        # Pending action records
├── prompt_bundles/                 # Saved prompt bundles
├── council_outcomes/               # Council outcome JSON (with routing_label + chain_steps)
├── council_progress/               # Live council progress (JSON + JS) for polling
├── reviews/                        # Post-hoc review JSON
├── review_pages/                   # Static HTML review pages
├── portal_pages/launchpad.html     # The launchpad (always file://)
├── digest_pages/                   # Weekly digest HTML
├── task_sync/                      # Sync-safe task payloads
├── watcher/                        # Cursor files for watch-loop resume
├── shortcut_setup/                 # Shortcut installer recipe
├── settings/                       # Telemetry settings
├── bin/trinity-dispatch            # Shell-launcher dispatch wrapper
├── cache/embeddings.jsonl          # Persistent embedding cache (768d)
├── memory/
│   ├── prompt_nodes.jsonl          # PromptNode index (hierarchical memory tier 1)
│   ├── turn_windows.jsonl          # TurnWindow index (tier 2 — local context)
│   ├── cursors.json                # Per-source memory ingest cursors (consumed by tool-triggered `ingest_recent()`)
│   └── embeddings_matrix.npy       # numpy fast-path matrix (lazy)
├── memories/                       # Cognitive memories: the three thinking files that compose your lens
│   ├── lens.md                     #   paired tensions (value)
│   ├── topics.json                 #   subject basins (semantic + lens evidence map)
│   └── vocabulary.md               #   anchors + homonyms + synonyms (linguistic)
├── core.md                         # Singular distillation of the three above (one paragraph manifesto)
├── scoreboard/                     # Operational scoreboards: model-selection bookkeeping (NOT cognitive memory)
│   ├── picks.json                  #   extracted model-selection rules per task_type
│   └── routing.json                #   per-task-type provider track record
├── cold_start_scan.json            # State file for first-spawn auto-scan (status, sources, added count)
├── analytics/
│   ├── routing_label_events.jsonl  # Chairman parse-success rate
│   ├── knn_advisory.jsonl          # k-NN advisory log
│   └── knn_advisory_report.json
├── research/
│   ├── hard_examples/              # Mined hard examples
│   └── replay_examples/
├── outcomes.jsonl                  # Per-session outcome records (drift)
├── council_runs.jsonl              # Council outcome log
└── launch_events.jsonl             # Launch/handoff events
```

## The closed loop (v1)

```
existing transcripts
    ↓ ingest.parse_*_export / iter_prompt_turns
clean PromptTurn[] (sidechain + api-error + system-injection stripped)
    ↓ embed_batch with search_document: prefix at 768d
PromptNode → TurnWindow (per-prompt + per-window context)
    ↓ memory.search_prompt_nodes (numpy matmul fast-path)
top-N replay candidates
    ↓ replay-history loop
council_runner.run_council per candidate (auto-picked chairman)
    ↓ chairman synthesis
structured Routing JSON (agreed_claims, disagreed_claims, provider_scores, routing_lesson)
    ↓ persisted in ~/.trinity/council_outcomes/{id}.json (the canonical store)
    ↓ compute_personal_routing_table() aggregates on demand by task_type
    ↓ chairman_picker → next council picks the right chairman
↑ better routing decisions feed back into the loop
```

Every council outputs one labeled training example for the eventual Phase 9 learned router. Removing any of `route`, `run_council`, `record_outcome`, `search_prompts` breaks a meaningful surface.

## Coding conventions

- **Python 3.10+**. `from __future__ import annotations` in every module for PEP 604 style.
- **Dataclasses everywhere**. No Pydantic, no attrs. Manual `to_dict()`.
- **No runtime dependencies** beyond `Pillow>=10`. `[mlx]` extras for `sentence-transformers`. `[test]` for pytest.
- **Stable IDs** via `stable_id()` (`utils.py`) — `sha1(prefix|parts...)[:16]`.
- **JSONL append logs** for analytics; JSON entity files for objects.
- **`to_dict()` filters None / empty strings / empty containers**.
- **`now_iso()`** — UTC ISO 8601 with `microsecond=0`.
- **`trinity_home()`** — `~/.trinity/` (or `$TRINITY_HOME`).
- **Graceful degradation** — features depending on `[mlx]` fall back silently.
- **Analytics never crash** — wrap in try/except, watcher must not fail because of observability code.

### CLI structure

- `main.py` is a thin dispatcher using `set_defaults(handler=...)`.
- Every subcommand prints JSON to stdout and returns.
- Config is only loaded for commands that need it.

## What's working (v1 ship)

1. **Memory index live.** `seed-from-taste-terminal` populates `~/.trinity/prompts/` from claude_ai + chatgpt + gemini takeout exports. 768d nomic embeddings, batched. Numpy matmul fast-path brings 49k-vector search (real corpus, 2026-05-13) from ~3s to ~5ms — same ms-per-vector profile as the original 28k measurement, so the fast-path absorbs corpus growth linearly without falling off.
2. **Personal routing table.** `replay-history --limit 20` re-evaluates top-N replay candidates against the current model lineup. Aggregation by `task_type` is computed on demand by `compute_personal_routing_table()` walking `~/.trinity/council_outcomes/*.json` (no separate state file — the council outcomes directory is canonical, can't drift from itself). Cached in-process by directory mtime.
3. **Chairman auto-selection.** `predict_strongest_chairman(task)` looks up personal table → global priors → default order. Manual `--primary-provider` always wins.
4. **Structured chairman output.** Every council emits Routing JSON with `agreed_claims`, `disagreed_claims` (with `why_matters`), `winner`, `runner_up`, `provider_scores`, `routing_lesson`, `eval_seed`. Parse-success tracked in `analytics/routing_label_events.jsonl`.
5. **Chain mode.** `run_council(mode="chain", sequence=[...])` runs sequential refinement; chain steps persisted on `CouncilOutcome.chain_steps`.
6. **MCP tool surface (v1.0 canonical 6 + v1.5 `ask` + `get_picks` + `mark_pick_wrong`).** v1.0: `route`, `run_council` (subsumes `judge` via `responses=[...]`), `record_outcome`, `search_prompts`, `get_persona`, `get_council_status`. v1.5 adds `ask` (cheap default single-call routing — the 90% case), `get_picks` (agent-facing introspection into extracted picks), and `mark_pick_wrong` (user-veto on a pick; halves effective trust per click) — 9 total. The five legacy tools (get_status/get_elo/get_recent_councils/watch_once/judge) are dropped from the public MCP surface.
7. **Streaming live council page.** Member responses render full markdown as soon as their status flips to `done`, while chairman is still synthesizing.
8. **Launchpad autofill** wired to `memory.search_prompt_nodes`. Reason chips and "Winner: ..." hints render on each suggestion.
9. **Personal routing table card** on the launchpad with empty-state CTA.
10. **`lens-build` is a 4-stage lens-discovery pipeline aligned with the taste-terminal spec (TASTE_WIKI_SCHEMA.md).** Lenses live at tension boundaries between value poles, not at cluster centers. Pipeline shape ratified by three councils: `council_70eaf228d7753074` (Option C — basins as verifier, not chairman input), `council_6892781d06ac3fa8` (Stage 0 turn-pair gaps as highest-leverage import from taste-terminal), `council_e7560934cb1f1d72` (Stage 0 = ONE batch chairman call gated by deterministic post-validators).
    - **Stage 1 — Topology (no LLM, ~5s)**: numpy k-means on PromptNode embeddings → ~20 named basins (id, size, top-3 TF-IDF terms, centroid). Used to *tag decisions* and to *post-filter pairs* — NOT as a chairman prompt input.
    - **Stage 0 — Turn-pair gap extraction (1 chairman call + deterministic validators)**: walks (assistant_text, user_next_turn) pairs, classifies each into one of the four taste-terminal implicit rejection signal types — REFRAME / COMPRESSION / REDIRECT / SHARPENING. Output: `~/.trinity/me/rejections.jsonl`. Validators (in `me/turn_pairs.py`) drop chairman-skim labels:
       - **COMPRESSION**: user_text word count must be ≤ model_text/10
       - **REDIRECT**: model_text must be structurally multi-part (numbered/bulleted/multi-sentence ≥3)
       - **SHARPENING**: user_text must share ≥2 keywords with model_text
       - **REFRAME**: substituted frame must persist into next user turn (else dropped). Lenient when no next-turn data.
    - **Stage 2 — Decision extraction (1 chairman call)**: emits `decisions.jsonl` with `{privileged, sacrificed, valence, basin, verbatim}` per decision-shaped utterance. Valence enum: `satisfaction | regret | unresolved | correction | cost` (per `council_c63fa273bdc2ed21`). Stage 0 rejections are mixed into the sampled corpus as additional high-signal source material.
    - **Stage 3 — Pair mining (1 chairman call)**: chairman proposes 6–12 pair candidates and applies the three tests as a JSON verifier — **tension** (decisions in both directions), **dual evidence** (regret/correction/cost on both poles), **failure-mode legibility** (named failure mode on each pole). Verdict per pair: `accepted | preserve_as_ordering | dropped`.
    - **Stage 4 — Basin post-filter (deterministic, no LLM)**: drops accepted pairs whose tension evidence sits in a single basin. This is what makes basin tags load-bearing — without the post-filter, the LLM can ignore them and the topology evidence is dead code.
    - Drift instrument (rolling cosine between `embed(lens.md)` and weekly turns) was **rejected** as topic-shift-not-value-shift metaphor.
    - Output: pairs → `~/.trinity/me/lenses.json` (4–8 expected, ≤7 per spec), preserved-as-orderings → `me/orderings.json`, rejections → `me/rejections.jsonl`, basins → `me/basins.json`. Rendered to `~/.trinity/memories/lens.md` for chairman context loading.
    - 3 model calls per rebuild (Stage 0 + Stage 2 + Stage 3), all on user subscriptions.
11. **Embedding-free product surface.** Launchpad autofill, MCP `search_prompts`, and `replay-history` candidate selection use pure heuristics (substring + recency + replay-value). No nomic model load on the hot path. `iter_prompt_nodes()` caps at the 5000 most-recent prompts (env var `TRINITY_PROMPT_NODE_LIMIT`) and is cached in-process by file mtime. `iter_prompt_nodes(limit=None)` lifts the cap — what `lens-build`, `dream`, `vocabulary`, `consolidate`, and the seed/incremental_ingest dedup all consume. Embeddings are written during seed and read uncapped by consolidation passes.
12. **Test suite: 1385 passing** + 4 skipped (1290 baseline at session start → 1382 after the three-tier restructure landed 82 new tests across scripts/, trust/audit, tier-equivalence, fresh-install, and Phase 7 council pre-empts; +3 net from the May 17 public-readiness pass: personal-path leaks fixed in `test_frontend_flow.py`, install-sh venv-detection + runtime-deps guards added, pyproject-pinned launch-version guard added, vanity-domain guard extended to docs/launch-day/, dead `TestInstallSmokeTracksMcpTools` guard removed in T10b).

## What's deferred to v1.1+

- **§8.9 Aggregation endpoint** — Cloudflare Worker for live global priors + public leaderboard. Read access free for all; upload opt-in only with anonymous categorical labels (no prompt content). Ship after Routing JSON parse-success ≥85% sustained and ≥50 opt-in users.
- ~~**Tool-triggered cursor-based ingest**~~ — **shipped.** `incremental_ingest.ingest_recent()` walks transcripts newer than `~/.trinity/prompts/cursors.json`, appends `PromptNode` records (no embedding — hot path stays embedding-free), persists the cursor atomically. MCP `ask` and `search_prompts` fire this at the start of each call with a 1s deadline so MCP-driven flows stay fresh without a manual `seed-from-taste-terminal` rerun. CLI: `trinity-local ingest-recent`. Errors swallowed so a parser breakage on one file can't take down the tool surface.
- **Auto-recommended chain mode** — `route()` doesn't auto-recommend `chain` until enough chain councils accumulate.
- **Local + global Elo blend** with sigmoid alpha over local council count (the `personal_routing_table` already replaces global as data accumulates; the explicit blend math is cosmetic for v1).
- **Live server-side autofill on keystroke** — needs a local HTTP endpoint.
- **Phase 9 learned tiny coordinator** — explicitly later. v1 collects the personal data; Phase 9 trains a per-user adapter against it.

## Loop Constitution substrate — removed; preserved in git history + spec

The double-loop substrate (`frame` / `run` / `verify_web`, formerly `src/trinity_local/loop/`)
was **removed from the codebase** as pre-launch simplification. The mechanic —
*execute → verify → cull → re-verify → commit* — will be rebuilt leaner inside
v1.5's `plan_and_execute` tool (ships in v1.6) driven by a flagship Conductor
with cortex context, not by a trained local skill-factory model.

The architectural reference + the ratifying council outcomes live in
[`docs/v2-loop-constitution.md`](docs/v2-loop-constitution.md). Git history
preserves the prior implementation if v1.6 wants to study it.

## Verified status

- `pytest -q` — **1402 passed** + 4 skipped (33 in `test_doc_count_consistency.py` defending launch-credibility claims; 4 skipped are the gated real-Chrome smokes that need a loaded extension to run).
- `trinity-local --mcp` exposes 11 tools: the v1.0 canonical 6 (`route`, `run_council`, `record_outcome`, `search_prompts`, `get_persona`, `get_council_status`) + v1.5 `ask` (cheap single-call routing) + v1.5 `get_picks` (agent-facing introspection into extracted picks) + v1.5 `mark_pick_wrong` (user-veto on a pick; halves effective trust per click) + launch-arc `handoff` (cross-provider conversation continuity) + launch-arc `get_eval_summary` (latest empirical-benchmark result for the agent surface).
- `trinity-local seed-from-taste-terminal --limit 10` runs end-to-end on real exports.
- `trinity-local replay-history --dry-run` lists ranked candidates with reason chips.
- `trinity-local portal-html` renders the launchpad with autofill chips, personal routing table card (or empty-state CTA), and global benchmarks.
- Live council page streams full member responses while chairman is synthesizing.
- Chairman prompt emits valid Routing JSON with `agreed_claims` / `disagreed_claims`.
- Chairman auto-selection: personal routing table → global benchmarks → default order.
- HTML well-formed (no orphan refs to peer_review / aggregate_ranking / daemon / workflow_create / task_linking).

## Development notes

- Run tests: `.venv/bin/python -m pytest tests/ -v`
- Or with isolated state: `TRINITY_HOME=/tmp/trinity-test PYTHONPATH=src python3 -m pytest -q`
- Embeddings require the MLX extras (`pip install -e '.[mlx]'` from a clone, for the contributor dev path). Without it, all embedding features fall back to the stable SHA-1 TF-IDF projection.
- The agent's source of truth is this file (`claude.md`). The codebase plus `docs/scale-plan.md` and `docs/product-spec.md` round out the picture.
- `AGENTS.md` is a thin redirect to here so Codex / other agent harnesses don't drift.
