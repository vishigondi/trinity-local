---
class: historical
---

# Patterns extracted from the fixes (meta-principles)

> Historical context relocated from `claude.md` on 2026-05-22 during
> the v1.7.5 cleanup pass (cut claude.md from 918 → ~200 lines). The
> 21 principles below are still authoritative — they earned their
> rules by costing time. The cleanup moved them here so the
> agent-facing `claude.md` could fit Anthropic's Auto-Dream 200-line
> MEMORY.md discipline without losing the institutional learning.

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
    and the smoke output had moved (#57); the depth-score formula in
    `commands/depth.py`'s module docstring (retired in tick #85) +
    argparse `help=` said `corpus_distance × log(1+inter_turn) ×
    log(1+LID)` for two months after tick #54 switched the composite
    to additive, while the same file's print footer had the correct
    formula (#87); claude.md's
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

22. **Empty callbacks swallow dispatch failures.** Earned 2026-05-26
    in the e2e Chrome dogfood arc when `stopCouncil()` was written as
    `dispatcher.dispatch({..., onResult: () => {}})` — the empty arrow
    function silently consumed every failure. Click Stop with no
    extension → council kept polling, no banner, no error, no feedback.
    The defensive shape: every async callback that's intentionally
    empty needs either (a) an inline comment justifying the silence
    (with a load-bearing why), or (b) explicit failure routing into a
    user-visible surface. The `() => {}` shape is a code smell the
    same way `except: pass` is a code smell. The discipline: when
    auditing for the bug's shape (#4), scan for empty arrow functions
    in dispatcher / promise / fetch / subprocess sites — not just for
    bare `except` clauses.

23. **Substring-presence asserts can survive partial reverts.**
    Earned 2026-05-26 by mutation-testing the stuck-token timeout
    regression: deleting the `let missingPollCount = 0;` declaration
    + the surrounding setup block left the regression test green —
    because the orphan threshold-check (`if (missingPollCount >=
    MAX_MISSING_POLLS)`) + the failed-branch error message string
    remained in the source unconnected, matching the test's substring
    checks even though the runtime would throw ReferenceError every
    poll. The defensive shape: regression tests for load-bearing fixes
    need structural assertions (declaration site + increment site +
    constant declaration), not single-substring presence. The 10-min
    validation loop: revert the fix, run the test, confirm it fires
    with a clear message, restore. Until you've done that, you don't
    know whether the test catches the bug or just decorates the source.
    Distinct from #14 (smoke-regression breadth) and #21 (surface-of-
    truth match) — this is about test depth, not coverage.

24. **Optimistic UI must roll back on async failure.** Earned 2026-05-26
    when `launchCouncil()` set `this.operation = {status: 'running'}`
    BEFORE `dispatcher.dispatch(...)` and never reset on failure. If
    the extension wasn't installed, "Council in Progress" panel polled
    forever, Launch button stuck disabled, the user's typed prompt got
    eaten, and the live-council URL was constructed against a
    status_token whose status file would never be written. Same shape
    bit Refine/Continue/Auto-chain (the segment-rollback fix) and Stop
    council (the chainError-restore fix). The defensive shape: any
    state mutation that anticipates an async return value must (a)
    snapshot what it's replacing AND (b) install a rollback path in
    the failure branch of the dispatcher's onResult. Treat optimistic
    UI as a transaction; the failure case must close the transaction
    cleanly, not leak partial state. Related to #16 (one bad value
    worse than zero) — silent corrupt state beats failure, but loud
    failure beats silent corrupt state every time.

25. **Error banners must live outside the gates that hide them.**
    Earned 2026-05-26 when the `chainError` banner I added in the
    Refine fix was nested inside `<section v-if="canChainNext">` —
    which only becomes truthy AFTER the last segment completes. So
    during a running council (the exact moment Stop is most likely
    clicked + failed), `chainError` was correctly set by the handler
    but the banner element was inside an unrendered subtree. The
    failure was invisible. The defensive shape: error surfaces sit at
    the page/app level, not nested inside conditional containers that
    might flip false in the same failure path that needs the error.
    Concretely for Vue / petite-vue: hoist the `v-if="error"` element
    above any `v-if="someCondition"` that could be falsey while the
    error is set. Reviewer's question: "if state X transitions, what
    in this DOM tree disappears, and does any of it need to keep
    showing the error?"
