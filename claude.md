---
class: live
---

# claude.md — Trinity Local

> Agent-facing project context. Companions:
> - [`docs/spec-v1.md`](docs/spec-v1.md) — locked v1.0 launch spec (shipped May 13–15, 2026)
> - [`docs/spec-v1.5.md`](docs/spec-v1.5.md) — **active next-trajectory spec** (target June 3, 2026): MCP-primary, hippocampus+cortex memory, ~~local model dispatch~~ (shipped 2026-05-20 pre-v1.5), rate-limit dodge, flagship-as-Conductor (no training)
> - [`docs/spec-v1.6.md`](docs/spec-v1.6.md) — **partially shipped 2026-05-14/15** alongside v1.0 (browser extension + Native Messaging host, capturing claude.ai / chatgpt.com conversations to `~/.trinity/conversations/` — Week 1 + Week 2 Days 6-9; gemini.google.com adapter deferred to v1.7 per protocol-fragility risk). No server, no daemon, no listening port. Closes the corpus-acquisition gap for web-chat users; the "Trinity reads transcripts already on your machine" claim becomes literal for everyone, not just CLI power users. **The same extension now also serves as the cross-platform launchpad dispatcher** (Phase 4b, 2026-05-16) — see [`docs/MIGRATION.md`](docs/MIGRATION.md) for the upgrade path from the macOS-only Shortcut. 10 narrow action-allowlist entries cover every launchpad button cross-platform; the Shortcut remains as tier-2 fallback.
> - [`docs/spec-v2.md`](docs/spec-v2.md) — sunset (trained-coordinator path). Preserved as architectural-decision history; reopens only if v1.5 hits a quality ceiling.
> - [`docs/cross-platform-spec.md`](docs/cross-platform-spec.md) — surface-expansion spec: terminal → desktop → mobile, Claude-Code-shaped phasing. Same `~/.trinity/` corpus everywhere; no hosted controller.
> - [`docs/three-tier-architecture.md`](docs/three-tier-architecture.md) — **launch architecture**. Initially ratified by `council_ff3da1fa84906791` (Phase 1, 2026-05-16); trust/audit substrate ratified by `council_c18f739a0234aa58` (Phase 6, 2026-05-16); final v1.0 integration floor and architecture coherence ratified by **`council_37eca30b6e7010df`** (Phase 7, 2026-05-16). **Pivoted 2026-05-19 to MCP-first** (audience-expansion + paste-into-Claude-Desktop install path): three tiers — **MCP server (primary)**, Pip (engine), Chrome Extension (discovery + capture sidecar) — with `~/.trinity/` as the invariant data contract. MCP tool docstrings are the contract the agent reads at handshake; the skill at `~/.claude/skills/trinity/` is kept as a back-compat alias for users who already type `/trinity` in Claude Code, but new users never need to know it exists. Tier-equivalence invariant (NOT bit-identical): cosine ≥ 0.9999 between backends, identical k-means cluster assignments, identical chairman picker output under pinned config.
> - [`docs/scale-plan.md`](docs/scale-plan.md) — long-form roadmap.

## Project Identity

**Trinity Local is your taste, ported.** v1 hero (pivoted 2026-05-16 from
council-mechanic framing to digital-twin framing):

> **Your taste, ported. Lives inside Claude Code, Codex CLI, Antigravity, and Cursor.**
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
`council_runtime.render_member_prompt`) — today chairman is lens-conditioned but dispatch is
not, so members get the raw question, not the user-twisted version. And
**task_type vocabulary unification** (documented KNOWN GAP at
`ranker/chairman_picker.py:_blended_pick`) — the chairman's open-set labels and
the picker's closed-set heuristic labels don't intersect, so personal routing
silently doesn't fire today.

**Status (2026-05-19, v1.7.4 post-launch simplification + consistency sweep):** v1.7 shipped May 13–15, 2026 (pyproject `1.7.4`; v1.7.1+v1.7.2 = public-readiness; v1.7.3 = share-workflow end-to-end: eval-share PNG, council-share rewrite, me-card install URL, review-link fake-URL fix, launchpad share chips; v1.7.4 = pre-launch simplification + 40+ launch-credibility drift fixes across 48 iters) — see [`docs/spec-v1.md`](docs/spec-v1.md). Brand axis (pivoted 2026-05-16): **transcripts** (already on your machine) → **lens** (the pattern of how you rephrase/judge/decide) → **twin** (Trinity acting in your voice). Hero: *"Your taste, ported. Lives inside Claude Code, Codex CLI, Antigravity, and Cursor."* Sub: *"No new app. No service. No API key. Your transcripts never leave your machine."* Prior framing was *"Stop copy-pasting prompts. Own your context. Dream your core memories."* — pivoted because the polyharness power user reads "councils" as another tool to learn; reads "your taste, ported" as something working FOR them. Folder schema locked at `SCHEMA_VERSION = 1`. <!-- canonical:smoke_surface_count -->34<!-- /canonical -->-surface browser smoke gate passing (`python scripts/browser_smoke.py`). <!-- canonical:test_count -->1599<!-- /canonical --> tests passing + <!-- canonical:skipped_count -->4<!-- /canonical --> skipped, <!-- canonical:doc_consistency_guards -->56<!-- /canonical --> doc-consistency guards green (launch-credibility regression suite: cited councils + install commands + binary asset freshness + brand-axis verbatim across surfaces + numeric MCP tool-count claims pinned to mcp_server.py + retired-CLI strings in both quoted-Python AND HTML-wrapped-Vue forms + DESIGN.md-forbidden hex colors (no indigo/violet/tailwind-blue/pink) in launchpad UI source — see `tests/test_doc_count_consistency.py`). Memory viewer (`~/.trinity/portal_pages/memory.html`) ships with the launchpad and renders the lens hierarchy (core, lens, topics, vocabulary) plus picks + routing scoreboards: markdown via `marked`, picks/routing as schema-aware Reader views, topics as an Obsidian-style force-directed graph (d3-force) over centroid cosine similarity. **basins.py clusters by thread (transcript_id mean centroid)** — a multi-turn conversation contributes one point to k-means instead of fragmenting across N basins; per-basin `representatives` carry the full turn list per representative thread, viewer renders click-to-expand. All sub-pages (memory viewer, live council, council review) share the `.trinity-topbar` nav pattern (pill `← Launchpad`, page title, optional secondary action) defined in `design_system.SHARED_CSS`. **v1.5 cortex Weeks 1–5 shipped end-to-end** (see [`CHANGELOG.md`](CHANGELOG.md) 2026-05-12 entry for the full list): 9 MCP tools (canonical 5 + v1.5 `ask`/`get_picks`/`mark_pick_wrong` + launch-arc `handoff`); cortex consolidation with **structured geometric prior** (geometric median centroid via Weiszfeld iteration, 6-component `trust_score` (n_episodes_norm / consistency_score / recency_agreement / diversity / coherence_score / audit_score — coherence itself is `mean_cosine_to(median, …)` from cortex_geometry.py, audit_score is the audit-mode signal added as the 6th), manifold-dim + bimodality flag fed to the extraction prompt so the flagship does rule-extraction-on-structure not geometry-in-language); **chairman-audit-mode** (`consolidate --audit` runs an independent second flagship to catch drift; loud-fails on stderr); **override mechanism** (CLI `cortex-override` + MCP `mark_pick_wrong`; halves effective trust per click; persists across consolidations); **sigmoid-blended chairman picker** (smooth cold-start→personalization, no hard cut at n=1); **user-verdict-weighted personal routing table** (record_outcome signal flows into aggregation at 0.7 weight); **tool-triggered incremental ingest** (`ask` scans new transcripts within 1s, no manual seed re-run); **HF Hub offline default** (`main()` pins `HF_HUB_OFFLINE=1` so Trinity never makes outbound Hub calls at runtime); launchpad surfaces: personalization-% column, Health column (audit / bimodal / override badges with hover-titles), evidence-chip links to source councils. `cortex.py` split: math helpers extracted to `cortex_geometry.py` (304 LOC, dependency-free). Loop Constitution substrate removed pre-launch (was 1,396 lines of v2-trajectory code; the mechanic will be rebuilt leaner inside v1.7's `plan_and_execute` per task #128 — v1.6 turned out to be browser-extension capture). **Next trajectory = v1.5** (target ship June 3, 2026): the MCP-primary two-tier tool surface is feature-complete; remaining work is calibration data + the v1.6 follow-ons noted in [`docs/spec-v1.5.md`](docs/spec-v1.5.md) "Open questions" (Ollama-vs-MLX preference, cortex-vs-lens cross-check). A flagship model with cortex context writes better routing prompts than any 7B you could train, so v1.5 ships the routing-coordinator architecture via context engineering instead of training. The trained-coordinator path in [`docs/spec-v2.md`](docs/spec-v2.md) is **sunset** as of 2026-05-11; reopens only if v1.5 hits a quality ceiling on real user data.

**The wedge is structural, not technical.** The three labs are commercially prevented from helping you use a competitor. Someone outside the labs has to ship the layer above them. That's the only sentence the marketing site has to land.

**The moat is the ledger.** Every council emits structured Routing JSON to `~/.trinity/council_outcomes/<id>.json` — `agreed_claims`, `disagreed_claims` with `why_matters`, `winner`, `provider_scores`, `routing_lesson`. Every user click feeds `record_outcome` → `~/.trinity/council_feedback.jsonl` + `outcome.metadata.user_verdict`. Frontier providers can't see the cross-model preference signal; Trinity persists it locally. The personal routing table is computed on-demand from the outcomes directory (no separate state file). Trinity rides on subsidized consumer subscriptions and never pays per call. v1 is free forever; revenue model deferred (see `docs/spec-v2.md` for held hosted-capability description, no pricing committed).

## Architectural commitments (load-bearing, not negotiable)

1. **No LLM calls outside councils.** Ingest, embedding, theme assignment, search ranking, clustering — pure embeddings + heuristics + metadata. The only LLM invocations Trinity makes are council member calls and chairman synthesis calls, both riding user subscriptions.
2. **Prompt content never uploads.** Even with v1.1 aggregation enabled, only categorical routing labels (`task_type`, `provider_scores`, `winner`) leave the machine. Anonymous, opt-in only.
3. **Local-first inference.** Phase 9's learned router runs on the user's hardware. No hosted controller. No per-call API billing.
4. **Subsidized consumer credits as cost basis.** Trinity dispatches via the user's own CLI subscriptions (Claude Code, Codex, Antigravity). If anyone proposes a hosted API tier, push back hard — that destroys both cost basis and privacy.
5. **HF Hub offline by default.** `main()` pins `HF_HUB_OFFLINE=1` + `TRANSFORMERS_OFFLINE=1` via `setdefault` at startup. The embedding model is pulled once via an explicit `huggingface-cli download nomic-ai/nomic-embed-text-v1.5`; after that Trinity loads from `~/.cache/huggingface/hub/` and never contacts the Hub during normal operation. Privacy + reliability invariant — no surprise outbound calls from the running system, no telemetry to upstream model hosts, MCP child processes inherit the env so the guarantee propagates through every spawn.

## Patterns extracted from the fixes (meta-principles)

Hundreds of commits since April, with the bulk concentrated on the
2026-05-12 simplification day. The recurring shapes that earned their
rules by costing time:

1. **Lossless serialization round-trips.** If `to_dict()` writes,
   `from_dict()` must return the same dataclass. `me/basins.py::Basin.to_dict`
   capped `prompt_ids` at 50 entries "for readable JSON" — `load_basins()`
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
    `_embedding_is_finite()` in `me/depth.py` (since extracted to
    `is_finite_embedding` in `embeddings/__init__.py` — exactly the
    promotion this principle prescribes), inline
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

**Updated 2026-05-18 (v1.7.4 — post-launch).** The four-pillar
forward arc (Action-from-view / Cross-memory navigation / Drift
surfacing / Supervision-signal moat) shipped end-to-end pre-launch.
The pre-launch simplification pass on 2026-05-18 then removed ~5000
LOC of features that didn't earn their keep (Trinity.app, macOS
Shortcut dispatcher, watcher subsystem, embedding cache, research/
package, 10+ internal CLI commands — see CHANGELOG v1.7.4 entry).

What's next is **distribution + observability of real-corpus signal**.
The product surface is stable; the unblocking work is making sure the
shipped version reaches users and that the supervision-signal loop is
actually firing on real installs.

**Post-launch arc (v1.7.5 → v1.8):**

1. **MCP-dropdown distribution (task #114, in_progress).** Submit
   Trinity to curated MCP server lists: Claude Code's directory,
   Codex CLI's registry, Cursor's MCP catalog, Cline + Continue
   community indexes. Being in the dropdown beats being technically
   perfect — discoverability is the only thing standing between the
   shipped product and the user who needs it.

2. **First-run wow demo (task #115, in_progress).** Cross-provider
   continuity in 60s: ask Claude a hard question mid-conversation,
   `trinity-local handoff gemini` continues the thread on Gemini with
   the same context. The killer hook is the user's *"wait, how did
   it know?"* moment — structurally non-refutable because only
   Trinity has the cross-provider prompt index. The handoff CLI +
   MCP tool shipped (task #119); what's queued is the screencast +
   landing-page embed (task #120) and the Gemini-Google variant
   (task #121, Gmail/Drive/Calendar inline).

3. **Real-corpus benchmarks on shipped installs (task #116).**
   `eval-build` + `eval-run` ship in v1.7.4; the empirical-leaderboard
   variant (Trinity vs Opus on design, vs GPT-5 on coding, vs Gemini
   on long-context) lands when ≥10 install logs are available to
   normalize against personal corpora. Per-axis bars on the eval
   card + the launchpad's Personalized Benchmark card are the
   surfaces; the harness is shipped.

4. **Supervision-signal uplift measurement.** The 6-stage rate-
   capture defense shipped pre-launch (census → visible →
   verify-after → preempt-CLI → preempt-UI → active nudge via MCP
   `rate_action`). Pre-launch the real-corpus rate was 3/19 (16%);
   first post-launch measurement (2026-05-20) on the same install:
   4/31 (13%). Council count grew faster than verdict count, so the
   proportion slipped slightly — the active nudge shipped but n=31
   is too small to conclude (binomial noise dominates). Prediction
   was ≥50% within a week. If still <2× the baseline at n≥50,
   revisit by surfacing the nudge through the macOS notification
   system (notifications.py exists) on council completion. The
   personal ledger of cross-model preferences is the moat — empty
   ledger = no moat.

5. **`principles.md` pipeline (task #109).** Data-gated. Needs ≥100
   council outcomes AND verdict rate ≥50% before k-means in 768-d
   space is meaningful. Revisits after the rate-capture work in #4
   produces enough signal.

**What's NOT in the post-launch arc (deliberately):**

- More CLI surface kills. The simplification pass is done; the
  shipped 21-command surface is the v1.7.4 contract. Adding new
  CLIs only when MCP isn't a better entry point.
- Architectural pivots. The trained-coordinator path remains sunset
  (per docs/spec-v2.md); the MCP-primary architecture is the
  trajectory. Reopens only if user data shows a quality ceiling.
- Trinity Pro hosted tier. v1 is free forever; pricing remains
  deferred until ≥1k installs + measurable Pro-worthy value
  (per docs/spec-v2.md).
- Re-adding the dropped CLIs (trust-init/show, audit-show, stats,
  metric, council-last, watch-once, etc.). Trust+audit CLI returns
  in v1.1 per the deferral; the rest stay killed unless real user
  data shows demand.
- Pass B of the macOS Shortcut kill (JS-side cleanup to drop the
  inert `shortcuts_integration` shim). Tracked in
  `docs/simplification_log.md` for v1.7.5; the live product works
  today because the JS Tier-1 (Chrome extension dispatch) is the
  canonical path and Tier-2 (Shortcut) silently no-ops on empty URLs.

**The unblocking question for v1.7.4 stability:** does the active
nudge actually pressure agents into surfacing the rate prompt? The
mechanism shipped; the measurement is the next week's work via
`compute_personal_routing_table()` walks over fresh council_outcomes
on installs that opt into telemetry (anonymous categorical labels
only — no prompt content ever leaves the user's machine).

## Launch arc (v1.0 → v1.1) — distribution beats elegance

Setting alongside the Forward Arc above, but on a different axis: that
arc is about what the app *does internally*. This one is about how the
app *reaches users*. During the consumer-AI land-grab phase, the
dominant pressure is being in the right dropdowns at the moment users
go looking. Five workstreams, ordered by leverage:

**Distribution correction (2026-05-14, revised 2026-05-19):** non-coders launch
Trinity like a desktop app, Cowork-style. `trinity-local` remains the complete
engine, but the ordinary user gesture is an app icon, menu bar entry, hotkey, and
first-run setup UI, not a terminal command and not a browser-extension toolbar
as the long-term cockpit. The Chrome extension remains the v1 bridge for static
launchpad hosting, browser capture, and Native Messaging dispatch while the real
desktop shell is built.

The mobile app starts as a review-link companion: open the web/deep link to the
review page, rate the winner, mark bad picks, and write the same ledger through
the paired desktop. Full phone-to-desktop dispatch comes after that rating loop
is reliable.

The earlier `Trinity.app` (osacompile-generated .app bundle) was retired
pre-launch because it was only a launchpad wrapper. The next desktop surface has
to be a real local cockpit over `~/.trinity/`, not a bookmark-shaped app.

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

- **prompts** — what the user owns (raw, indexed in `~/.trinity/prompts/`; renamed from `memory/` per Tier 1 #1, automatic one-time migration inside `prompts_dir()` itself, see `state_paths.prompts_dir`). Inputs to dream.
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
- **harness** — the CLI/IDE the user is working inside (Claude Code, Codex CLI, Antigravity, Cursor). Trinity registers as an MCP server inside each via `install-mcp`. (Antigravity ships TWO binaries both named `agy`: an IDE binary at `~/.antigravity/antigravity/bin/agy` v1.107+ that opens chat sessions in a window — NOT a CLI dispatch target — and the standalone CLI at `~/.local/bin/agy` v1.0+ installed via `curl -fsSL https://antigravity.google/cli/install.sh | bash`, which DOES support `-p / --prompt` non-interactive dispatch and is the one Trinity invokes. PATH ordering in the user's shell determines which `agy` resolves first; the standalone CLI installer prepends `~/.local/bin` to `.zshrc` so it wins by default. Both binaries read MCP servers from `~/.gemini/settings.json`; the Antigravity CLI also stores conversations as `.pb` protobuf files at `~/.gemini/antigravity-cli/conversations/` — distinct from the legacy `gemini` binary's `~/.gemini/tmp/` JSON sessions. Cowork — Anthropic Managed Agents — is an ingest source via `parse_cowork_session`, not a dispatch target or MCP harness; adapter wanted but blocked on Anthropic's stable API, see `CONTRIBUTING.md`.)
- **member** — a provider acting as one voice in a council. Canonical term across code AND marketing copy (the Tier 2 #6 "rename to seat" was unwound; "seat" was tried as a table metaphor but never caught on, and code structures like `members=[...]` made the rename costly without payoff).
- **provider trio across layers** — the same lab gets a different name at each layer; what users see depends on the entry surface. Consolidating here so future code/docs don't re-derive it:

  | layer | Anthropic | OpenAI | Google |
  |---|---|---|---|
  | mobile app brand | Claude | ChatGPT | *(no Antigravity mobile yet)* |
  | cloud agent harness | Claude Code | Codex agents | *(no equivalent)* |
  | desktop CLI binary | `claude -p` | `codex exec` | `agy -p` |
  | Trinity slug (code/config/JSON) | `claude` | `codex` | `antigravity` |
  | underlying model | Claude Opus 4.7 / Sonnet 4.6 / Haiku 4.5 | GPT-5.5 | Gemini 3.1 Pro Preview |

  Use **slugs** in code, config, file paths, JSON keys (operational identifiers). Use **model names** in user-facing UI (mobile review cards, launchpad outcome rows — what users recognize). Use the **mixed marketing trio** ("Claude, Codex, and Gemini" per README L14) — that's each lab's strongest brand at its strongest layer (Claude is symmetric all the way down, Codex is a stronger dev brand than GPT for code work, Gemini is more recognizable than the new Antigravity harness). Trinity councils CANNOT fire from mobile apps directly today — mobile is read/review-only per `docs/cross-platform-spec.md` because Trinity is local-first (no hosted controller); phone-to-desktop dispatch is v1.6+ territory.
- **task_type** — the short label for "what kind of question this is" (heuristic on input, also emitted by chairman). NOT the same as `category` (coarser LMArena-aligned grouping).

The map mirrors the tagline: prompts (what you own) → dream (the verb) → core memories (what dream creates, plural) → core (the distillation, singular). When in doubt about a name, look at the brain analog and pick the one that matches what the file actually stores.

## Calling the council from inside Claude Code

Trinity is exposed as an MCP server. v1.7 ships 5 canonical tools (`route`, `run_council`, `record_outcome`, `get_persona`, `get_council_status`); v1.5 adds `ask` (cheap default single-call routing), `get_picks` (agent-facing introspection into extracted picks), and `mark_pick_wrong` (user-veto on a pick — halves effective trust per click, persists across consolidations); launch-arc adds `handoff` (cross-provider continuity) — 9 total. `run_council(responses=[...])` covers what `judge` used to do — pre-supplied member outputs go straight to chairman synthesis, one model call instead of N+1. The chairman reads `~/.trinity/memories/lens.md` and condenses members through *this user's* taste — that's what makes the council more useful than just asking Claude alone.

**When to call these tools** is in the MCP description itself (per tick 111 — every harness reads it at handshake) AND in the actionable rule below. The two surfaces are intentionally aligned; the rule below is the Claude-Code-specific elaboration.

**The actionable rule (the one that fires automatically):** before calling `AskUserQuestion` with multiple options that are NOT user-personal preferences, FIRST run `mcp__trinity-local__ask` (cheap, ~$0.01–0.05, ~2–30s) or `mcp__trinity-local__run_council` (3 members + chairman) on the same question. Treat `AskUserQuestion` as reserved for *user-personal* choices — preferences, priorities, taste — and Trinity as the default for *product/architectural* choices where the question is "which option is RIGHT" (the user's lens already answered, applied through the chairman) rather than "which option do YOU want" (the user has to weigh in fresh).

This rule learned from tick 104 (2026-05-21): a council that took 60s reversed a decision I would have made wrong via solo deliberation. The friction is real (30s latency on `ask`) but lower than the cost of building toward the wrong answer + later finding out.

Bar for `run_council` vs `ask` once you're past the trigger:
- `ask` (cheap, single-call): quick second opinion, cross-provider check, rate-limit dodge, 90% of consults
- `run_council` (parallel members + chairman): when you need disagreement-vs-agreement structure surfaced. If the question form is "is X or Y better," `run_council` exposes whether 3 models agree or split — silently picking either is what `ask` would do.

Skip Trinity entirely for: trivial bugs, syntax/API lookups, mechanical refactors, information retrieval. Each council costs 3 member calls + 1 chairman call — wasted on questions with one right answer.

After a council, treat the chairman's synthesis (especially `agreed_claims` / `disagreed_claims`) as the source of truth for what the answer should be, then explain it in your own words back to the user. Call `mcp__trinity-local__record_outcome` when the user picks a winner so the personal routing table improves over time.

**Why this rule propagates:** other Claude Code instances reading this file inherit the rule. The fact that it's encoded in the repo's own `claude.md` means anyone with Trinity installed + this repo cloned gets the behavior. No hook needed; the instruction itself is the dispatch mechanism.

## Install / surface notes

Run `trinity-local install-mcp` once to register Trinity's MCP server with Claude Code (`~/.claude.json`), Antigravity (`~/.gemini/settings.json` — merges into existing `mcpServers`; both `agy` binaries read the same file), and Codex CLI (`~/.codex/config.toml`). Each harness spawns `trinity-local --mcp` as a stdio child when it starts; it lives until the harness exits. ~62MB resident while connected.

The launchpad → Chrome extension → Native Messaging → `trinity-local-capture-host` → CLI pipeline is independent of MCP — it's one-shot subprocess at every step, no persistent process required. So the launchpad keeps working even if MCP is disabled. (The earlier macOS Shortcut dispatch path through `~/.trinity/bin/trinity-dispatch` was retired pre-launch in favor of the cross-platform Chrome extension; an inert `shortcuts_integration` shim survives so older renderers don't break before their JS surgery lands.)

## MCP server hot-reload (development only)

When MCP is enabled and you're actively editing Trinity, set `TRINITY_MCP_WATCH=1` to enable a file watcher that calls `os._exit(0)` on any `.py` change. The MCP launcher auto-respawns with fresh code. Typical edit → reload cycle is <1s. Never enable in shipped configs.

**Caveat for tool-list changes**: Claude Code caches the tool list from the first connection. Adding *new* MCP tools (vs. modifying existing handlers) may still require a Claude Code restart to make them visible to the harness.

## Architecture (post v1)

### CLI dispatcher

Entry: `src/trinity_local/main.py` — thin dispatcher only. Live CLI surface after pre-launch simplification (Passes A–BB collapsed task/bundle/launch/watch/distill/cache/depth/metric/trust/shortcut/council-last/auto-chain/auto-open). 22 user-facing command modules (21 in `CORE_COMMAND_MODULES` + `install` in `OPTIONAL_COMMAND_MODULES`); 4 more (`bootstrap_pairs`, `distill`, `helpers`, `trust`) survive as importable utilities for tests + internal callers but no longer register CLIs (the `shortcuts_integration` inert shim at the package root falls into the same category). (Survivor list trimmed in tick 85: `commands.tasks` + `commands.depth` retired as orphan modules whose docstrings lied about test coverage; `commands.ingest` was already retired in tick 58 but had lingered on this list.) Live argparse surface: <!-- canonical:cli_command_count -->44<!-- /canonical --> subparser registrations (each one shows in `trinity-local --help`); count auto-rendered from main.py's registration via `scripts/render_docs.py` so docs and the actual CLI surface can't drift.

| Module | Key commands |
|--------|-------------|
| `commands/adapters.py` | `adapters` |
| `commands/cortex.py` | `consolidate` (extract routing patterns; supports `--audit` for independent-chairman drift check), `cortex-override` (user-veto on a rule; halves effective trust per click; `--reset` clears) |
| `commands/council.py` | `council-start`, `council-launch`, `council-rate`, `council-stop`, `council-share`, `council-iterate` (sequential refinement via `--rounds N`; replaces former `auto-chain`) |
| `commands/debug.py` | `debug` (discovery umbrella: lists power-user verbs `replay-history` / `consolidate` / `vocabulary` / `seed-from-taste-terminal`; bare names still work — `debug` is the help shortcut, not a re-nesting) |
| `commands/download_embedder.py` | `download-embedder` (one-shot pull of `nomic-ai/nomic-embed-text-v1.5` ~600 MB to `~/.cache/huggingface/hub/`; required for `lens-build` / `dream` / `vocabulary` write paths; gates the agent UX with a Trinity verb instead of a raw `huggingface-cli` external command) |
| `commands/dream.py` | `dream` (the one-command cold-start: discover cross-provider pairs across ALL embedded transcripts → synthesize each as a virtual council → consolidate cortex → rebuild /me lenses; Anthropic's *Dreaming* on the user's own data — subsumes the retired `distill` and `bootstrap-pairs` CLIs) |
| `commands/eval.py` | `eval-build` / `eval-stats` / `eval-run` / `eval-show` / `eval-share` (corpus-based eval harness — task #122; `eval-build` produces the suite from `me/rejections.jsonl`, `eval-run --target <provider>` dispatches each prompt + scores via judge against `lens.md`, `eval-show` renders a past run with per-axis bars + top/bottom samples without re-dispatch. `eval-share` renders the result as a 1200×630 PNG share card with install CTA + GH Pages URL — the tweet-shaped artifact for "Gemini scored 0.83 on YOUR kind of question.") |
| `commands/handoff.py` | `handoff <provider>` (cross-provider conversation continuity — task #119, launch-arc workstream #2; pulls recent turns from `~/.trinity/prompts/` index, dispatches to target provider with "continue this thread" frame; mirror of `mcp__trinity-local__handoff`) |
| `commands/install.py` | `install-mcp`, `install-hooks`, `install-extension` (Chrome Native Messaging manifest), `install-launcher` (Linux .desktop / Windows Start Menu .url), `uninstall` |
| `commands/install_umbrella.py` | `install` (discovery umbrella: `trinity-local install --help` lists the 5 specific install verbs above; symmetric with `debug`) |
| `commands/me.py` | `lens-build` (chairman-driven), `lens-show` |
| `commands/me_card.py` | `me-card` (render a paired-tension lens as a 1200×630 PNG) |
| `commands/portal.py` | `portal-html`, `open-review`, `review-link`, `serve` (local HTTP server for launchpad — alternative to file://) |
| `commands/replay.py` | `replay-history` |
| `commands/review.py` | `review` |
| `commands/seed.py` | `seed-from-taste-terminal` |
| `commands/status.py` | `status` |
| `commands/telemetry.py` | `telemetry-show`, `telemetry-enable`, `telemetry-disable`, `telemetry-reset-id`, `telemetry-endpoint` |
| `commands/unrated.py` | `unrated` (list councils without user verdict; Pillar 4 funnel-widening — one-line-per-council with chairman pick + copy-paste rate command) |
| `commands/update.py` | `update` (pull latest, refresh MCP configs, verify with status — the post-curl-bash self-update mechanism) |
| `commands/vocabulary.py` | `vocabulary` (scan prompts for terminology overloads — one word ↔ two meanings; two words ↔ one meaning. Emits `~/.trinity/memories/vocabulary.md`; runs as Phase 2.5 of `dream` and as a standalone CLI. NOT a lens-pipeline stage — the lens pipeline has its own Stages 0–4 inside `me/pipeline.py`, ending at the basin post-filter.) |
| `commands/watch.py` | `ingest-recent` (cursor-based incremental ingest; Chrome ext + MCP `ask` fire this same path. Legacy `watch-once`/`watch-loop` CLIs retired pre-launch — tool-triggered ingest replaces the daemon model) |

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
| Embeddings | `embeddings/` — `__init__.py`, `backend_mlx.py`, `backend_tfidf.py` | `nomic-embed-text-v1.5` at **768d**, batched embed, Nomic prefix preservation. Persistent cache retired 2026-05-17 — offline rebuild passes re-encode their corpus per run (~2 min on 50k prompts); cold-start UX unchanged. |
| Ingest | `ingest.py` | Parsers: `parse_claude_code_session`, `parse_codex_session`, `parse_gemini_cli_session`, `parse_cowork_session`, `parse_claude_ai_export`, `parse_chatgpt_export`, `parse_gemini_takeout_html`. `iter_prompt_turns(session)` yields clean user-facing turns (sidechain / API errors / synthetic stripped). Gemini Takeout cells are grouped into multi-turn sessions by 30-minute time-proximity (source_format_version "2") so prior-thread context is preserved across cells Google flattened. |
| Categories | `categories.py` | Trinity capability categories aligned with the LMArena leaderboard (Coding/Math/Creative Writing/Hard Prompts/Multi-Turn/Instruction Following/Overall). Single source for the task_type→category map and UI labels. |
| Ranker | `ranker/` — `base.py`, `fallback.py`, `heuristic.py`, `knn_ranker.py`, `chairman_picker.py` (NEW), `types.py` | Routing decisions + chairman auto-selection (personal table → global benchmarks → default order) |
| Council outcome | `council_feedback.py` | Append user verdicts; `record_council_outcome` (in `memory/store.py`) propagates to PromptNode |
| State paths | `state_paths.py` | Single source of truth for `~/.trinity/` paths |
| Runtime env | `runtime_env.py` | PATH-injection env builder + `run_with_runtime_env()` (both helpers live in one module — `subprocess_utils.py` was the original plan but the split didn't materialize) |
| Task kinds | `task_types.py` | Single `guess_task_type()` heuristic classifier (no LLM) |
| Refresh | `refresh.py` | `refresh_launchpad()` — single entry for portal regeneration |
| Dispatch | `dispatch_registry.py`, `capture_host.py`, `shortcuts_integration.py` (inert shim) | Chrome extension Native Messaging bridge — canonical dispatch path. The macOS Shortcuts wrapper (`shortcut_setup.py` + `dispatch_runner.py` + `commands/shortcuts.py`) was retired 2026-05-17; `shortcuts_integration.py` survives only as a backward-compat stub so old renderers don't break before their JS surgery lands. |
| MCP | `mcp_server.py` | v1.0 canonical 5 + v1.5 `ask` + `get_picks` + `mark_pick_wrong` + launch-arc `handoff` (see below) |
| Launchpad | `launchpad_data.py`, `launchpad_template.py`, `launchpad_runtime.py`, `launchpad_page.py`, `memory_viewer.py` | Static HTML launchpad + memory viewer (memory.html with inlined memory contents) — autofill, personal routing table, council suggestions, 4-chip lens card (core / lens / topics / vocabulary) — picks + routing surface on the routing card |
| Share cards | `share_card_base.py`, `me_card.py`, `eval_card.py`, `council_card.py` | Three 1200×630 PNG renderers + a shared base module (canvas, fonts, palette, footer/CTA). One visual language (cream BG + sage accent + serif headline). `me_card` renders the strongest lens, `eval_card` renders an eval run's per-axis bars, `council_card` renders a council outcome's chairman-extracted agreed/disagreed claims. All three carry the same install CTA + `keepwhatworks.com` landing URL (brand flipped 2026-05-17 from `vishigondi.github.io/trinity-local`); council_card is privacy-safe by construction (chairman fields only, no user prompt or member text) |
| Telemetry | `telemetry.py`, `notifications.py` | Opt-in telemetry settings (privacy-clean), system notifications |
| Adapters | `adapters.py` | Provider adapter detection + transcript counts |
| Research | `research/` package | Offline research pipeline (replay, hard mining, ranking eval) — not on the live product path |

### The nine MCP tools (`mcp_server.py`)

The full public surface is **9 tools** — 5 canonical (v1.0) + 3 v1.5
additions + 1 launch-arc addition (`handoff`, tick #119, 2026-05-14).
The canonical 5 are the lifecycle order; the v1.5 trio sits adjacent
to the v1.0 supervision loop; `handoff` surfaces the cross-provider
continuity demo to agents inline. (`get_eval_summary` shipped post-#122
then retired 2026-05-18 in commit `1fed7fc` — agents ground via
`ask` + `get_picks`.)

**v1.0 canonical five (lifecycle order — note: this is the *teaching* order, "what you call when, and why"; mcp_server.py registers tools in a UX order that interleaves the v1.5 trio for `tools/list` discoverability — cheap+common first: `route`, `ask`, then `run_council`, etc. Both orderings are correct for their purpose):**

1. **`route(task, harness, available_models, budget, latency)`** → `{mode, primary, challenger, confidence, reason, fallback}`. No model calls — heuristic + k-NN + chairman picker. Cheap, called before the harness picks a model.

2. **`run_council(task, members, mode, sequence, primary_provider, responses)`** → council launched asynchronously. `mode="parallel"` (default) runs members concurrently then chairman. `mode="chain"` runs sequence serially with each step seeing prior outputs. **When `responses=[...]` is provided** (pre-supplied member outputs), skips dispatch and runs chairman synthesis only — one model call instead of N+1, returns the structured Routing JSON inline. This subsumes the former `judge` tool.

3. **`record_outcome(council_run_id, user_winner, accepted, edited, tests_passed, cost_usd, latency_sec, answer_label)`** → closes the supervision loop. Updates `council_feedback`, `CouncilOutcome.metadata.user_verdict`, and the originating `PromptNode` via `memory.record_council_outcome`. **The most important tool** — without it Trinity is a switchboard.

4. **`get_persona()`** → returns `~/.trinity/memories/lens.md`. The chairman already loads this internally, but exposing it lets *any* harness (Claude Code, Codex, Antigravity) pull the persona once at session start and tailor responses without an MCP round trip per call.

5. **`get_council_status(council_run_id)`** → in-protocol polling for async councils. Returns status (running/completed/failed/canceled), per-member progress, synthesis state, and outcome summary (winner, agreed/disagreed claims, routing_lesson) when complete. Required for harnesses without filesystem access; also the only way to detect a stuck member without watching `~/.trinity/portal_pages/status/`.

**v1.5 trio:**

6. **`ask(task, harness, available_models, budget)`** → cheap single-call default routing. The 90% case: harness has a question, wants one model's answer with a chairman-blessed verdict, doesn't need a full council. Pulls from cortex picks first (high-trust rule → use directly), falls back to k-NN advisory, finally to heuristic.

7. **`get_picks(basin_id?, min_trust?)`** → agent-facing introspection into extracted cortex routing patterns. Returns `{rules: {basin_id: pattern}, total_basins, returned}` — patterns are keyed by basin_id (cortex consolidation is per-basin, not per-task_type), each carrying provider/reasoning/trust score/source councils inside the pattern dict. `basin_id` filter narrows to one basin; `min_trust` floor filters by `trust_score.value`. Empty cortex returns `{rules: {}, note: "..."}`. Lets a harness inspect what Trinity has learned about which model wins for which basin without firing route().

8. **`mark_pick_wrong(task_type)`** → user-veto on an extracted pick. Halves effective trust per click, persists across consolidations. Same shape as the launchpad's pick-veto chip (Surface 17) but from the agent side.

**Launch-arc addition (tick #119, 2026-05-14):**

9. **`handoff(target_provider, continuation?, num_turns?)`** → cross-provider conversation continuity. Pulls the user's most-recent (user, assistant) turns from the cross-provider prompt index, packages them as "continuing this thread" context, dispatches to a DIFFERENT provider. Target picks up exactly where the prior model left off — no re-context, no copy-paste. This is the mechanism behind the 60-second hero demo (#115/#120). Structurally non-refutable: only Trinity has the cross-provider index. CLI mirror: `trinity-local handoff <provider>`.

<!-- get_eval_summary retired 2026-05-18 (commit 1fed7fc) — agents ground
via `ask` + picks; the eval-summary surface remains on the launchpad
card and `eval-show`. -->

Internal helpers (`get_status`, `get_elo`, `get_recent_councils`, `watch_once`) remain importable for the launchpad but are NOT exposed via MCP.

### State layout

Live state under `~/.trinity/` (overridable via `TRINITY_HOME`). Two
conventions throughout: **entities** use JSON-per-file under a named
directory; **event logs** use append-only JSONL. Anything not on this
diagram is either retired or written by a feature you haven't run yet.

```
~/.trinity/
│
│  ── Captured web chats (Chrome extension writes; ingest reads) ──
├── conversations/                  # Native-Messaging captures from
│   └── <provider>/<conv_id>.json   #   claude.ai / chatgpt.com / gemini.google.com
│
│  ── Entities (JSON-per-file) ────────────────────────────────────
├── todos/                          # Durable todo records
├── actions/                        # Pending action records
├── prompt_bundles/                 # Saved prompt bundles
├── council_outcomes/               # Council outcome JSON (routing_label + chain_steps)
├── reviews/                        # Post-hoc review JSON
├── review_pages/                   # Static HTML review pages
├── portal_pages/                   # Static launchpad surface (always file://)
│   ├── launchpad.html              #   The launchpad
│   └── status/                     #   Live council progress (JSON + JS) for polling
├── task_sync/                      # Sync-safe task payloads
├── share/                          # PNG share-card outputs (me-card / council-share / eval-share defaults)
├── evals/                          # Eval sets (`eval-build`) + per-run results (`eval-run`)
│   ├── <eval_id>.json              #   built suite of (prompt, rejection_type) items
│   └── results/                    #   eval_<id>__model_<provider>__<ts>.json
├── settings/                       # Telemetry settings
│
│  ── Prompt index + cognitive memories ──────────────────────────
├── prompts/                        # Raw prompt index (renamed from memory/ per Tier 1 #1; legacy memory/ still readable on older installs)
│   ├── prompt_nodes.jsonl          #   PromptNode index (hierarchical memory tier 1)
│   ├── turn_windows.jsonl          #   TurnWindow index (tier 2 — local context)
│   ├── cursors.json                #   Per-source ingest cursors (consumed by tool-triggered `ingest_recent()`)
│   └── embeddings_matrix.npy       #   numpy fast-path matrix (lazy)
├── memories/                       # Cognitive lens (the three thinking files)
│   ├── lens.md                     #   paired tensions (value)
│   ├── topics.json                 #   subject basins (semantic + lens evidence map)
│   └── vocabulary.md               #   anchors + homonyms + synonyms (linguistic)
├── core.md                         # Singular distillation of the three above
├── scoreboard/                     # Operational scoreboards (NOT cognitive memory)
│   ├── picks.json                  #   extracted model-selection rules per task_type
│   └── routing.json                #   per-task-type provider track record
├── me/                             # Lens-build pipeline working output (intermediates between prompts/ and memories/)
│   ├── rejections.jsonl            #   Stage 0 turn-pair rejection signals (REFRAME/COMPRESSION/REDIRECT/SHARPENING)
│   ├── rejections_dropped.jsonl    #   Validator-rejected turn pairs (audit trail)
│   ├── decisions.jsonl             #   Stage 2 chairman-extracted decisions
│   ├── lenses.json                 #   Stage 3 accepted tension pairs (renders into `memories/lens.md`)
│   ├── orderings.json              #   Stage 3 preserved-as-ordering pairs
│   └── merges.jsonl                #   Manual cherry-pick merge log
│
│  ── Event logs (JSONL append-only) ─────────────────────────────
├── outcomes.jsonl                  # Per-session outcome records (drift)
├── council_runs.jsonl              # Council outcome log
├── launch_events.jsonl             # Launch/handoff events
├── council_feedback.jsonl          # User verdicts feeding the personal routing table
├── analytics/                      # Long-tail event logs
│   ├── routing_label_events.jsonl  #   Chairman parse-success rate
│   ├── knn_advisory.jsonl          #   k-NN advisory log
│   ├── knn_advisory_report.json    #   (entity exception: rolled-up snapshot)
│   └── dispatch_outcomes.jsonl     #   `ask` dispatch outcomes — Day-1 rate-limit-saves metric
│
│  ── First-run state ────────────────────────────────────────────
├── cold_start_scan.json            # First-spawn auto-scan (status, sources, added count)
│
│  ── Optional / off-path ────────────────────────────────────────
└── research/                       # Offline research outputs (not on the live product path)
    ├── hard_examples/
    └── replay_examples/
```

Retired directories that may still exist on older installs (Trinity no
longer reads or writes them): `tasks/` (→ `todos/`), `memory/` (→
`prompts/`), `watcher/` (cursor files for watch-loop, retired with the
watcher subsystem), `shortcut_setup/` + `bin/trinity-dispatch` (macOS
Shortcut dispatcher, retired in favor of the Chrome extension),
`cache/embeddings.jsonl` (offline rebuild passes re-encode now),
`models/` (was created as a side-effect of the retired `models_dir()`
helper but never written to; actual nomic weights live in
`~/.cache/huggingface/hub/` — retired 2026-05-20, tick 28),
`cortex/` (was created as a side-effect of the retired `cortex_dir()`
helper; spec-v1.5 originally described `cortex/failure_modes.json` +
`cortex/successful_prompts.json` but the shipped picks.json embeds
both inline — retired 2026-05-20, tick 51),
`digest_pages/` (weekly digest feature deleted pre-launch).

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

Every council outputs one labeled training example for the eventual Phase 9 learned router. Removing any of `route`, `run_council`, `record_outcome` breaks a meaningful surface.

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
3. **Chairman auto-selection.** `predict_strongest_chairman(task)` runs a sigmoid blend of personal routing table + global benchmarks (per task #52 / Tier 2 #7): `alpha = sigmoid((n - 5) / steepness)`, where n is the personal-council count for the task_type. At n=0 the chairman pick is ~100% global priors; at n≈5 the blend is ~50/50; at n≈10 the personal table dominates (~99%). When both signals are empty, falls back to `available_providers[0]` (default order). Manual `--primary-provider` always wins.
4. **Structured chairman output.** Every council emits Routing JSON with `agreed_claims`, `disagreed_claims` (with `why_matters`), `winner`, `runner_up`, `provider_scores`, `routing_lesson`, `eval_seed`. Parse-success tracked in `analytics/routing_label_events.jsonl`.
5. **Chain mode.** `run_council(mode="chain", sequence=[...])` runs sequential refinement; chain steps persisted on `CouncilOutcome.chain_steps`.
6. **MCP tool surface (v1.0 canonical 5 + v1.5 `ask` + `get_picks` + `mark_pick_wrong` + launch-arc `handoff`).** v1.0: `route`, `run_council` (subsumes `judge` via `responses=[...]`), `record_outcome`, `get_persona`, `get_council_status`. v1.5 adds `ask` (cheap default single-call routing — the 90% case), `get_picks` (agent-facing introspection into extracted picks), and `mark_pick_wrong` (user-veto on a pick; halves effective trust per click) — 8 total before launch-arc. Launch-arc adds `handoff`. (`get_eval_summary` shipped then retired 2026-05-18 in commit `1fed7fc` — agents ground via `ask` + picks.) The five legacy tools (get_status/get_elo/get_recent_councils/watch_once/judge) are dropped from the public MCP surface.
7. **Streaming live council page.** Member responses render full markdown as soon as their status flips to `done`, while chairman is still synthesizing.
8. **Launchpad autofill** wired to `memory.search_prompt_nodes`. Reason chips and "Winner: ..." hints render on each suggestion.
9. **Personal routing table card** on the launchpad with empty-state CTA.
10. **`lens-build` is a 5-stage lens-discovery pipeline adapted from the external taste-terminal spec.** (taste-terminal is no longer a runtime dependency — see `docs/product-spec.md` "What was deliberately deleted" — but its lens-at-tension-boundary frame is the conceptual anchor; the rules below were ratified into Trinity's own pipeline by the three councils named.) Lenses live at tension boundaries between value poles, not at cluster centers. Pipeline shape ratified by three councils: `council_70eaf228d7753074` (Option C — basins as verifier, not chairman input), `council_6892781d06ac3fa8` (Stage 0 turn-pair gaps as highest-leverage import from taste-terminal), `council_e7560934cb1f1d72` (Stage 0 = ONE batch chairman call gated by deterministic post-validators).
    - **Stage 1 — Topology (no LLM, ~5s)**: numpy k-means on PromptNode embeddings → ~20 named basins. Per-basin shape (`me/basins.py::Basin`): `id`, `size`, `centroid`, `top_terms` (top-3 TF-IDF residual phrases), `representatives` (closest-to-centroid prompts with full turn lists for the click-to-expand viewer affordance), `label` (chairman-generated semantic label per tick #49 — empty on older runs, UI falls back to `top_terms`). Used to *tag decisions* and to *post-filter pairs* — NOT as a chairman prompt input.
    - **Stage 0 — Turn-pair gap extraction (1 chairman call + deterministic validators)**: walks (assistant_text, user_next_turn) pairs, classifies each into one of the four taste-terminal implicit rejection signal types — REFRAME / COMPRESSION / REDIRECT / SHARPENING. Output: `~/.trinity/me/rejections.jsonl`. Validators (in `me/turn_pairs.py`) drop chairman-skim labels:
       - **COMPRESSION**: user_text word count must be ≤ model_text/10
       - **REDIRECT**: model_text must be structurally multi-part (numbered/bulleted/multi-sentence ≥3)
       - **SHARPENING**: user_text must share ≥2 keywords with model_text
       - **REFRAME**: substituted frame must persist into next user turn (else dropped). Lenient when no next-turn data.
    - **Stage 2 — Decision extraction (1 chairman call)**: emits `decisions.jsonl` with `{privileged, sacrificed, valence, basin, verbatim}` per decision-shaped utterance. Valence enum: `satisfaction | regret | unresolved | correction | cost`. Stage 0 rejections are mixed into the sampled corpus as additional high-signal source material.
    - **Stage 3 — Pair mining (1 chairman call)**: chairman proposes 6–12 pair candidates and applies the three tests as a JSON verifier — **tension** (decisions in both directions), **dual evidence** (regret/correction/cost on both poles), **failure-mode legibility** (named failure mode on each pole). Verdict per pair: `accepted | preserve_as_ordering | dropped`.
    - **Stage 4 — Basin post-filter (deterministic, no LLM)**: drops accepted pairs whose tension evidence sits in a single basin. This is what makes basin tags load-bearing — without the post-filter, the LLM can ignore them and the topology evidence is dead code.
    - Drift instrument (rolling cosine between `embed(lens.md)` and weekly turns) was **rejected** as topic-shift-not-value-shift metaphor.
    - Output: pairs → `~/.trinity/me/lenses.json` (4–8 expected, ≤7 per spec), preserved-as-orderings → `me/orderings.json`, rejections → `me/rejections.jsonl`, basins → `me/basins.json`. Rendered to `~/.trinity/memories/lens.md` for chairman context loading.
    - 3 model calls per rebuild (Stage 0 + Stage 2 + Stage 3), all on user subscriptions.
11. **Embedding-free product surface.** Launchpad autofill and `replay-history` candidate selection use pure heuristics (substring + recency + replay-value). No nomic model load on the hot path. `iter_prompt_nodes()` caps at the 5000 most-recent prompts (env var `TRINITY_PROMPT_NODE_LIMIT`) and is cached in-process by file mtime. `iter_prompt_nodes(limit=None)` lifts the cap — what `lens-build`, `dream`, `vocabulary`, `consolidate`, and the seed/incremental_ingest dedup all consume. Embeddings are written during seed and read uncapped by consolidation passes.
12. **Test suite: <!-- canonical:test_count -->1599<!-- /canonical --> passing** + <!-- canonical:skipped_count -->4<!-- /canonical --> skipped (live count auto-rendered; post-Pass-A-BB simplification dropped ~80 tests alongside the watcher subsystem, distill CLI, metric/stats CLIs, council-last, depth-show, trust CLI deferral, embedding cache, and other surface kills. Test count growth since then is from the post-launch consistency-sweep work adding regression guards as drift catches accumulate. The four skipped tests are gated real-Chrome smokes that need a loaded extension to run).

## What's deferred to v1.1+

- **§8.9 Aggregation endpoint** — Cloudflare Worker for live global priors + public leaderboard. Read access free for all; upload opt-in only with anonymous categorical labels (no prompt content). Ship after Routing JSON parse-success ≥85% sustained and ≥50 opt-in users.
- ~~**Tool-triggered cursor-based ingest**~~ — **shipped.** `incremental_ingest.ingest_recent()` walks transcripts newer than `~/.trinity/prompts/cursors.json`, appends `PromptNode` records (no embedding — hot path stays embedding-free), persists the cursor atomically. MCP `ask` fires this at the start of each call with a 1s deadline so MCP-driven flows stay fresh without a manual `seed-from-taste-terminal` rerun. CLI: `trinity-local ingest-recent`. Errors swallowed so a parser breakage on one file can't take down the tool surface.
- **Auto-recommended chain mode** — `route()` doesn't auto-recommend `chain` until enough chain councils accumulate.
- **Local + global Elo blend** with sigmoid alpha over local council count (the `personal_routing_table` already replaces global as data accumulates; the explicit blend math is cosmetic for v1).
- **Live server-side autofill on keystroke** — needs a local HTTP endpoint.
- **Phase 9 learned tiny coordinator** — explicitly later. v1 collects the personal data; Phase 9 trains a per-user adapter against it.

## Loop Constitution substrate — removed; preserved in git history + spec

The double-loop substrate (`frame` / `run` / `verify_web`, formerly `src/trinity_local/loop/`)
was **removed from the codebase** as pre-launch simplification. The mechanic —
*execute → verify → cull → re-verify → commit* — will be rebuilt leaner inside
v1.5's `plan_and_execute` tool (ships in v1.7 per task #128 — v1.6 turned out to be browser-extension capture) driven by a flagship Conductor
with cortex context, not by a trained local skill-factory model.

The architectural reference + the ratifying council outcomes live in
[`docs/v2-loop-constitution.md`](docs/v2-loop-constitution.md). Git history
preserves the prior implementation if v1.6 wants to study it.

## Verified status

- `pytest -q` — **<!-- canonical:test_count -->1599<!-- /canonical --> passed** + <!-- canonical:skipped_count -->4<!-- /canonical --> skipped (<!-- canonical:doc_consistency_guards -->56<!-- /canonical --> in `test_doc_count_consistency.py` defending launch-credibility claims; 4 skipped are the gated real-Chrome smokes that need a loaded extension to run).
- `trinity-local --mcp` exposes 9 tools: the v1.0 canonical 5 (`route`, `run_council`, `record_outcome`, `get_persona`, `get_council_status`) + v1.5 `ask` (cheap single-call routing) + v1.5 `get_picks` (agent-facing introspection into extracted picks) + v1.5 `mark_pick_wrong` (user-veto on a pick; halves effective trust per click) + launch-arc `handoff` (cross-provider conversation continuity).
- `trinity-local ingest-recent` runs end-to-end against `~/.claude/` / `~/.codex/` / `~/.gemini/` transcripts (auto-discovers; no required flags). `seed-from-taste-terminal --path <export-dir> --limit 10` ingests claude.ai / chatgpt / Gemini-Takeout exports — `--path` is required.
- `trinity-local replay-history --dry-run` lists ranked candidates with `task_type` / source-provider / existing-council-count / prompt excerpt per row. (The "reason chips" affordance is a launchpad UI concept on the autofill card, not a CLI column.)
- `trinity-local portal-html` renders the launchpad with autofill chips, personal routing table card (or empty-state CTA), and the Personalized Benchmark card (which blends `globalBenchmarks` data into the user's per-provider scoreboard — the user-visible card label is "Personalized benchmark," not "Global benchmarks").
- Live council page streams full member responses while chairman is synthesizing.
- Chairman prompt emits valid Routing JSON with `agreed_claims` / `disagreed_claims`.
- Chairman auto-selection: sigmoid blend of personal routing table + global benchmarks (per task #52), falling back to default order only when both signals are empty. See "Chairman auto-selection" in What's Working above for the curve.
- HTML well-formed (no orphan refs to peer_review / aggregate_ranking / daemon / workflow_create / task_linking).

## Development notes

- Run tests: `.venv/bin/python -m pytest tests/ -v`
- Or with isolated state: `TRINITY_HOME=/tmp/trinity-test PYTHONPATH=src python3 -m pytest -q`
- Embeddings require the MLX extras (`pip install -e '.[mlx]'` from a clone, for the contributor dev path). Without it, all embedding features fall back to the stable SHA-1 TF-IDF projection.
- The agent's source of truth is this file (`claude.md`). The codebase plus `docs/scale-plan.md` and `docs/product-spec.md` round out the picture.
- `AGENTS.md` is a thin redirect to here so Codex / other agent harnesses don't drift.
