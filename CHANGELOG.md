# Changelog

All notable changes to Trinity Local. Format follows [Keep a Changelog](https://keepachangelog.com/);
versioning matches the project's phase + capstone cadence rather than strict semver.

## [v1.0 ship window — day 2 launch-arc workstreams] — 2026-05-14

Three launch-arc workstream ticks shipped: the killer-hook handoff
mechanism, the corpus-based eval harness MVP, and the Preference
Corpus Spec v1.

### Cross-provider handoff (tick #119) — the killer hook

`trinity-local handoff <provider>` CLI + `mcp__trinity-local__handoff`
MCP tool. Pulls the user's most-recent (user, assistant) turns from
the cross-provider prompt index, packages them as "continuing this
thread" context, dispatches to a different provider. The target picks
up exactly where the prior model left off — no re-context, no
copy-paste. Structurally non-refutable: only Trinity has the cross-
provider index, so only Trinity can do continuity. The mechanism
behind the 60-second hero demo (#115 / #120). MCP surface now ships
10 tools (was 9). 12 new tests covering prompt-building + dispatch +
MCP surface. Hard-unblocks #115/#120/#121.

### Corpus-based eval harness — MVP (tick #122)

New `evals/` package. `trinity-local eval-build` reads
`~/.trinity/me/rejections.jsonl` + the prompt index, produces a
personalized eval set at `~/.trinity/evals/eval_<hash>.json`. Each
item is a (prompt, rejection_type, rejected_response, user_substitute,
rubric_signal, basin_id) tuple any candidate model can be scored
against. `trinity-local eval-stats` renders the rejection-type
distribution + basin distribution + sample items. Content-addressed
eval_id → idempotent reruns; results diff across model releases.

Real-corpus build (2026-05-14): 44 items extracted from 44 mined
rejections — REFRAME 45.5% / COMPRESSION 25.0% / REDIRECT 22.7% /
SHARPENING 6.8%. The signature itself is informative: a user with
this distribution should benchmark candidate models primarily on
"did the model match my framing." 13 new tests covering schema +
stats + idempotence + cli registration. Runner + scorer ship in a
follow-up tick.

The wedge: no frontier provider can build personalized eval suites
from cross-provider rejection signal. Anthropic only sees Claude
transcripts; Trinity sees all three plus the user's empirical
rejections of every provider's past output. Unblocks #116 (cross-
provider benchmarks) — the methodology becomes "score the user's
actual rejections" not "pick synthetic prompts."

### Preference Corpus Spec v1 (tick #117) — schema standardization

`docs/PREFERENCE_CORPUS_SPEC.md` + three JSON Schema files under
`schemas/`:

- `council_outcome.schema.json` — one multi-model run + chairman
  synthesis + user verdict. Canonical supervision-signal shape.
- `eval_set.schema.json` — personalized eval suite format
  (matches #122 MVP).
- `rejection_signal.schema.json` — labeled (prompt, response,
  rejection_type) triples from turn-pair gap extraction.

JSON Schema Draft 2020-12, CC0 license. The spec doc covers the four
implicit-rejection signal types (REFRAME / COMPRESSION / REDIRECT /
SHARPENING), what the format is and isn't, and how Aider / Cline /
Continue / custom MCP servers can adopt.

15 new tests across three layers: schema self-validation
(Draft 2020-12 meta-check), synthetic round-trip (build via Trinity
writer → validate against schema), and real-corpus sampling (load
actual `~/.trinity/council_outcomes/*`, validate against schema).
The real-corpus layer immediately caught 4 schema-vs-reality
mismatches in the first iteration — `mode` enum was too tight,
`differences` had to allow arrays not just strings, `confidence`
allows both numeric and categorical, `provider_scores` allows both
flat-score and nested-rubric shapes. Schema fixed; published
contract now reflects what writers actually produce.

Workstream #117 completed. First-mover authority over the schema
locked in while we're still the only consumer.

### Other 2026-05-14 changes

- Reframed launch-arc workstream #2 (first-run wow): the demo is
  cross-provider continuity, NOT council depth. Updated claude.md
  Launch arc section, docs/product-spec.md, README hero with the
  60-second demo block. Continuity is the A-grade hook (one answer
  that knew the prior context); council comparisons are B-grade
  (user has to evaluate three answers).
- Pillar 4 stage 6: `rate_action` field on MCP `run_council` /
  `get_council_status` responses when an outcome is completed-but-
  unrated. Agent reads its own tool result, surfaces the rating
  prompt to the user inline — no launchpad detour. 7 new tests.
- New tasks #114-118 (launch arc workstreams) + #119-121 (handoff
  mechanism / demo recording / Gemini-Google branch) + #122
  (eval harness) + #111-113 (matryoshka shape-similarity for
  principle extraction).
- Status block bumped to day 2 of 3-day ship window.

Test count: 903 → 943 (+40). Both doc-consistency guards green
through the day. Cron loop `8ecb80a7` running every 15 min.

### Day-2 afternoon — handoff demo + Day-1 metric defense

Six more ticks shipped after the morning batch above. Theme: every
shipped surface in the launch-arc gets defended end-to-end (prompt
side + pre-flight side + visible surface side) so the demo recording
tomorrow is deterministic, the launch-package "one metric" is
visible, and pillar-4 verdict-capture has its 7th defense.

**MCP `get_eval_summary` (11th MCP tool).** Third entry point for
the empirical-benchmark surface, alongside CLI `eval-show` and the
launchpad Surface 30 card. Agent-callable from inside Claude Code:
when a user asks "which model is best for X" or "how does gemini
compare", the agent gets per-axis scores from the user's actual
rejection signal instead of guessing. Three empty-state paths
(no evals dir / no runs / filter mismatch) each return a different
CTA. +7 tests, MCP surface 10 → 11.

**`pending_ratings` MCP funnel widener.** Verdict-capture rate was
stuck at 16% (3 of 19) through six shipped surfaces because
`rate_action` only fires when the agent re-polls a specific
council and most councils complete async — the agent never
re-polls. New `_pending_ratings_hint()` rides every `ask` and
`route` response with a structured "here are 3 unrated councils
within the last 7 days" hint. The seventh Pillar-4 surface and the
first ACTIVE widener at the workflow level (others were per-council
or passive visibility). 30s in-process cache so the helper doesn't
re-scan disk on every keystroke. +9 tests.

**First real eval-run on user's corpus + 3-place AST bug.**
`trinity-local eval-run --target gemini --judge claude --limit 3`
ran end-to-end against the user's actual rejection signal: gemini
scored **0.833 aggregate** (REDIRECT 0.900, REFRAME 0.800). The
empirical version of the launch-arc #116 marketing headline shape:
"Model X scored Y.YY on YOUR kind of question." First invocation
caught a real shape bug — `for p in config.providers if p.enabled`
iterates dict KEYS (strings), `p.enabled` blows up. Same shape in
`commands/eval.py`, `commands/handoff.py`, `mcp_server._handoff`.
All three fixed; AST guard via `inspect.getsource` promoted so the
shape can't quietly recur. +1 regression guard.

**Handoff capability hints (#121 prompt enablement).** The cross-
provider handoff was packaging context but not actively priming the
receiving model to bring capability the prior model didn't have.
New `_CAPABILITY_HINTS` dict per target: gemini → "if you have
Google Workspace tools (Gmail/Drive/Calendar) or web search, USE
THEM"; claude → "if you have MCP/filesystem/code-exec, USE THEM";
codex → "if you have shell/local code, USE THEM." Soft-form ("if
you have") avoids hallucinating tool calls when google-workspace
MCP isn't wired. Hint lands BEFORE the prior log (pinned by test)
so the model reads tool-use frame before context. The
differentiator phrase "bringing capability the prior model
structurally couldn't" is the same wedge sentence baked into every
marketing surface — one voice across the launch. +5 tests.

**Doctor `handoff_ready` composite check (#115/#120 pre-flight).**
Per-provider checks (claude/codex/gemini) pass individually but the
demo PATH fails on three real shapes none of them catches: <2
enabled providers, empty `following_assistant_text` in recent
prompts, single-provider history. New check flags each with
specific fix hints. Real-corpus result on the v1.0 author's install
(day 2 of ship window): *"recent prompts only span 1 provider
(claude) — handoff works but the demo loses the cross-provider
beat. Have a quick conversation in a second provider, then
re-run."* Surfaced a real gap the recording-day surprise would
otherwise have hit. +6 tests.

**Launchpad rate-limit-saves card (Day-1 launch metric visible).**
`docs/launch-package.md` names rate-limit-saves as THE Day-1 number
for the case study post. The plumbing has been live for weeks
(`ask.py` writes `dispatch_outcomes.jsonl`, `trinity-local metric
rate-limit-saves` reads it) but the number was CLI-only — invisible
to users opening the launchpad. New card on the launchpad surfaces
the count + save rate + by-failure-kind breakdown. Real corpus on
v1.0 author's install: **164 saves over 30 days, 18.1% save rate**.
First helper used the wrong field name (`primary_provider` vs
`primary`) which would have grouped everything as "unknown" — CLI
parity test now pins this so the launchpad number and the CLI
metric can't drift. Surface 32 smoke regression guard added in the
same tick (principle #14). +6 tests.

Test count (day 2 close): 943 → **1031 (+88)**. Smoke surfaces:
31 → 32. MCP tool surface: 9 → 11 (`get_eval_summary`, `handoff`).
All 5 doc-consistency guards green throughout the day.

**Launch-arc accumulation today:** every workstream has at least
one shipped artifact except #114 (outreach gated) and #120
(recording gated). #115/#119/#121 (handoff demo) defended end-to-
end. #116/#122 (corpus evals) has the first empirical result on
disk. #117/#118 (schema + narrative) closed earlier. The launch
package's "one metric we need to track from day 1" is now visible
on the launchpad.

## [v1.0 ship day — post-launch quality arc] — 2026-05-13 (late evening)

29 ticks across four substantive arcs. The structural story matters
more than the per-tick diff — capturing the shapes here so a future
audit can pick up where this left off.

### Embedding pipeline NaN safety (ticks #55-59, #68, #83)

Tick #55 caught a real bug via a new opt-in `@pytest.mark.real_corpus`
suite: `thread_lid` was missing the NaN filter that `thread_centroids`
already had, and a single non-finite row was poisoning the entire
cosine similarity matrix → corrupting `depth_score` for ~40 unrelated
`gemini_takeout` transcripts. Three follow-up ticks closed the class:

- **#56**: promoted three inline filter shapes
  (`_embedding_is_finite`, `_valid_embedding`, inline `any(v != v ...)`)
  to one `is_finite_embedding()` helper in `embeddings/__init__.py`.
  Added the filter to two consumers (`cross_provider_pairs`,
  `vocabulary._gather_token_contexts`) that had been missing it entirely.
- **#58**: write-boundary gate. `put_cached` silently refuses non-finite
  vectors; `embed`/`embed_batch` sanitize backend output via TF-IDF
  fallback. The cache is the persistence boundary — once bad data is
  cached it sticks and gets re-served on every hit.
- **#59**: dropped redundant `if not emb` pre-checks now that
  `is_finite_embedding` is the single-source filter.
- **#68 + #83**: real-corpus integration tests for the two other
  matmul pipelines (`cross_provider_pairs`, `vocabulary.find_homonyms`).
  All three matmul-shaped pipelines now have real-data gates.

Earned three new meta-principles in `claude.md`: #16 ("one non-finite
poisons the matrix"), #17 ("three inline shapes = missing helper"),
#18 ("embedding similarity ≠ structural similarity").

### Verdict-capture defense-in-depth (ticks #69-74)

Tick #69's real-corpus census found 3 of 19 council outcomes carried
verdicts (16% capture rate). Trinity's moat thesis rests on this
signal; 84% silent meant the ledger was mostly empty. Five-stage arc:

- **#69 Find**: `~/.trinity/council_outcomes/*.json` walk surfaced the
  real ratio. Reframed task #109 (principles.md) as data-gated.
- **#70 Visible**: launchpad "N of M rated" eyebrow + accent prompt
  when total ≥ 5 AND rate < 50%.
- **#71 Verify-after**: 3s `loadOutcomeScript` re-fetch after click;
  badge flips to "Save failed" when `user_verdict.user_winner` is
  absent post-fire.
- **#72 Preempt-CLI**: `doctor` flags missing macOS Shortcut up front.
- **#73 Preempt-UI**: launchpad top-banner mirrors the doctor check
  with the same remediation copy.

### Invisible-armor catch + AST scanner (ticks #63-65)

Tick #63 found that `test_knn_advisor` and `test_knn_analytics` were
setting `os.environ["TRINITY_HOME"]` at module top-level — pytest
imports every test module during collection, so the env var leaked
process-wide and the real-corpus depth tests silently skipped while
passing in isolation. Three-part fix:

- Both files converted to `autouse` + `monkeypatch.setenv` fixtures.
- `iter_prompt_nodes` cache signature now keys on `str(path)` so a
  future module-level pollution invalidates automatically.
- **#64**: AST scanner at `tests/test_no_module_level_env_mutation.py`
  fails the suite on any future `os.environ[]`/`sys.path` write at
  module top level. Earned meta-principle #19.
- **#65**: CONTRIBUTING.md updated with the rule + pointer.

### Cherry-pick UX + rebuild chip pattern (ticks #60-61, #76-80, #82)

- **#60-61**: Quote chip on each member response — appends
  `> [Provider]: <text>` to the refinement input. Multi-quote stacks.
  Solves the hand-rolled flow that produced
  `bundle_42f8cea9c9e705e5` ("Stop copy-pasting prompts. Own your
  context. Dream your core memories." — Gemini's "Own your context"
  merged with Claude's response). Smoke regression guard on Surface 9.
- **#76-77**: ↻ Rebuild chips on lens and cortex cards (closes
  forward-arc "see a rejected lens → rebuild" + "see stale routing →
  consolidate" gaps). Parameterized `copyText(value, flashKey)` helper
  supports flash-on-copy across the launchpad.
- **#78**: `copyHealthCommand` migrated to delegate to the new helper.
- **#79**: Memory viewer rebuild chip copy unified to `↻ Rebuild`.
- **#80**: Extracted `.lp-rebuild-chip` CSS class — two ~200-char
  inline styles collapsed to one rule.
- **#82**: Provider install ⧉ button gained `✓` flash feedback —
  closes the audit-for-shape on `copyText` flash adoption (5/5 sites
  now use the parameterized helper).

### Other (consolidated)

- knn_advisor + hard_mining: dropped MLX-only gates that locked the
  k-NN advisory layer to `[mlx]`-equipped installs (#66-67).
  watch_runtime's gate stays — the 0.7 cosine threshold is
  MLX-calibrated; comment added so a future audit doesn't "fix" it.
- Doctor gains `_check_feedback_consistency` to surface orphaned
  feedback entries — tick #69 found 16 of 19 feedback entries pointed
  to outcomes deleted by older cleanup passes (#75).
- Forward-arc section in claude.md synced to reflect what's shipped
  across the four pillars (#81).
- Test count 791 → 833 across the session; 29 browser surfaces stay
  green throughout.

## [v1.0 ship day — chip polish + stale-basin handling] — 2026-05-13 (evening)

Three ticks after the cross-memory navigation entry below closed
the chip link graph. The chips themselves shipped fine; their
hover surface had two real issues:

### Tooltip arc (ticks #38–39)

The lens card showed `b03`, the routing-table chip said
`Open basin b07 in the topology graph` — neither told the user
what the basin was *about* until they clicked through.

- `_topology_basin_labels()` reads topics.json once at page-build
  time, returns `{basin_id: "term1 · term2 · term3"}` (top-3 of
  each basin's TF-IDF terms). Threaded through `page_data` as
  `topologyBasinLabels`; a tiny Vue method `basinHoverLabel`
  consumes it for the lens-card + cortex-card chips (`#38`).
- Viewer-side: `loadCrossMemoryMaps` now also exposes a
  `basinLabels` Map. Shared `basinHoverTitle()` helper threads
  through the picks→topology xlink and routing→topology chip
  (`#39`). Same wording on both halves — "Basin <id> — <terms>"
  when terms exist, "Open basin <id> in the topology graph" as
  fallback.

### Stale-basin banner (tick #40)

When a `?basin=<id>` deep-link arrived but no node matched (most
likely cause: lens-build re-ran with different cluster ids since
the chip was rendered), the topology view silently rendered the
empty "click a basin" message — no feedback to the user that the
link they followed was stale.

The detail panel now surfaces a warm-warning banner reusing the
same `.viewer-health-banner` shape the picks Reader's "not yet"
banner uses: "not found" status + a click-to-copy
`trinity-local lens-build` chip so the user can rebuild without
context-switching.

Browser smoke grew 28 → 29 (stale-basin banner); test suite
714 → 727.

## [v1.0 ship day — cross-memory navigation closed] — 2026-05-13 (later same day)

After the forward-arc trilogy below, twelve more ticks closed the
two remaining forward-arc gaps: action affordances on every Reader
view, and a full bidirectional cross-link graph between the three
data memories (picks, routing, topology) plus the lens.

### Action affordances (ticks #26–29)

Every view was read-only at the start of the day. Each Reader now
ships an action chip on its primary unit:

- **picks Reader** (`#26`): per-card `Mark wrong` chip copies
  `trinity-local cortex-override --basin <id>`. Veto path from
  view-side — was CLI-only via `mark_pick_wrong` MCP.
- **viewer header** (`#27`): every memory header carries a
  persistent `Rebuild` chip copying the rebuild CLI via
  `suggestionFor(file)`. Always-on counterpart to the staleness
  chip — the user can refresh a memory *before* staleness fires.
- **topic-graph basin** (`#28`): basin detail panel grows
  `Launch council on this topic` copying
  `trinity-local council-launch --task "<headline>"` with
  bash-safe quoting (4-meta escape: `\`, `"`, backtick, `$`).
- **topic-graph rep** (`#29`): per-representative `Replay` chip
  on every thread in the panel. stopPropagation prevents the
  expand toggle from firing on chip click. `escapeBashArg`
  helper extracted; the basin chip + rep chip share it.

### Cross-memory link graph (ticks #30–36)

Picks, routing, and topology were three silos. The bridge is
centroid cosine similarity (768-d nomic vectors); both Python
and JS sides use the same matcher with a shared
`BASIN_SIM_THRESHOLD = 0.65` (extracted in `#35`).

- **topology → picks** (`#30`): basin detail panel shows
  `Routing rule: <task> →` when this basin has a pick.
- **pick-basin styling** (`#31`): SVG nodes for pick-bearing
  basins get a warm-brown ring + tooltip surfacing the routing
  rule. Visual companion to the panel chip.
- **picks → topology** (`#32`): pick card `View in topology →`
  xlink. Topology view reads `?basin=` on load and calls
  `showDetail + highlightNeighborhood` — same UX as a click.
  `matchBasinsToPicks` + `loadCrossMemoryMaps` extracted as
  shared helpers; both Reader views call them.
- **routing → topology** (`#33`): routing-table row chip via
  task_type → pick → centroid → basin. Reuses the shared map.
- **launchpad recent-card → topology** (`#34`): third chip
  alongside `→ pick` / `→ routing`. Python-side
  `_task_to_topology_basin` mirrors the JS matcher exactly.
- **launchpad cortex card → topology** (`#35`): row-level
  chip when the rule's basin centroid maps to topology.
- **launchpad lens card → basins** (`#36`): each paired lens
  renders `basins_spanned[]` as deep-link chips. Closes the
  "lens → source prompts" arc via the topology view.

### Visual + drift consolidation (tick #37)

Three launchpad chip surfaces (cortex card, lens card, recent-
card row) had duplicated inline styles. Extracted shared
`.cross-memory-chip` base + variant modifiers
(`--label / --id / --inline / --pill`) in launchpad_template.py.
Bumping the chip look now updates all three surfaces from one
CSS rule.

Browser smoke grew from 17 surfaces → 28 with one regression
guard per shipped chip. Test suite from 657 → 714.

## [v1.0 ship day — forward-arc trilogy] — 2026-05-13

Day 1 of the 3-day v1.0 ship window. Yesterday's CHANGELOG entry
("Memory viewer + topic graph + nav harmonization") shipped the
*inspectable* surface. claude.md commit `adc28f9` then extracted
meta-principles + plotted three forward predictions from 241
commits of history. This entry covers the trilogy that turned all
three predictions into working code:

### 1. Drift surfacing (tick #8 — `a723ac2`)

`is_core_stale` / `override_count` / `audit_status` / pre-thread-aware
topics — all four signals already existed but the launchpad never
told the user about them. New `_memory_health()` in launchpad_data.py
aggregates the four into a structured payload; new `.memory-health-card`
section in launchpad_template.py renders it ONLY when non-empty
(silence is the all-good state — no "everything fresh!" badge spam).

Surface 15 added to the smoke. The card renders inline above the
Council card, top of the user's eye path, before they ask a new
question.

### 2. Action-from-view (tick #9 — `d519d4b`)

Memory-health hints stopped being prose-only ("run `trinity-local
distill`") and became click-to-copy chips. Schema gain: each issue
now carries `command` (CLI to copy) OR `href` (in-app navigation
target). The audit-disagreed issue gets href → memory.html?file=picks.json
because inspection is the right next action there, not a re-run.

Chip flow: shows the literal command; click → clipboard + flips to
"✓ Copied" for 2.4s. Same pattern as the existing taste-share copy
button. Closes 90% of the "see drift → act on it" UX gap with zero
new infrastructure (full one-click dispatch via macOS Shortcut is
queued; copy-to-clipboard delivers the value today).

### 3. Cross-memory navigation (tick #10 — `f35f715`)

picks.json and routing.json both key by task_type but lived in
silos. Pure URL plumbing closes the gap:

- Each pick card → "View routing scores →" chip → `memory.html?file=routing.json&task=<basin>`
- Each routing-row task name → dotted-underline link → `memory.html?file=picks.json&task=<task>`
- Both readers honor `?task=` query param: scroll-to + highlight ring/tint on the matching entry

Round-trip stable. No schema changes. ~70 LOC across both renderers.
First cut at the cross-memory pattern; topics/lens links are natural
expansion points.

### Day-1 ship state

- 658 tests pass.
- 16/16 smoke surfaces green (Surface 15 validates the action chip
  actually copies; Surface 14b validates memory viewer renders).
- claude.md status block + patterns + forward arc all reflect
  current state. CHANGELOG (this entry) captures today's work.

### What's still queued (not blocking ship)

- **Full one-click action via Shortcut dispatch.** Chips currently
  copy; making them actually execute needs new dispatch_registry
  actions + macOS Shortcut setup. Copy is 90% of the win.
- **Topics graph / lens cross-memory links.** The bi-directional
  picks↔routing pattern is the template; extending to topics (basin
  → council list) + lens (lens line → source prompts) is mechanical
  follow-up.
- **CHANGELOG entry rolled forward as the day progresses.** This
  entry is the day-1 baseline; later entries should append rather
  than rewrite.

## [Memory viewer + topic graph + nav harmonization] — 2026-05-12 (late)

A second arc, driven by user-flagged UX gaps after the brand-pivot
work shipped. Six commits worth that compound into one user-facing
shift: every memory is now hand-inspectable, with topology that
matches "what conversations I keep having" instead of "what isolated
turns look like alone".

### Memory viewer (new surface)

- `~/.trinity/portal_pages/memory.html` — single-page viewer linked
  from the launchpad's new "Your memories, raw" chip card. Six chips
  (one per memory) → one viewer with a per-file Reader.
- Markdown rendered via bundled `marked` + DOMParser (never
  `innerHTML`); `picks.json` → cards with trust badges; `routing.json`
  → task×provider table with best-cell highlighting; `topics.json` →
  Obsidian-style force-directed graph (d3-force, ~80 KB across split
  submodules — d3-selection, d3-dispatch, d3-timer, d3-quadtree,
  d3-drag, d3-force).
- Memory contents inlined at `portal-html` time into
  `window.__TRINITY_MEMORIES__` (same pattern as the council thread
  manifests) so the viewer works under `file://` from the desktop
  shortcut — no `trinity-local serve` needed.

### Topic graph + thread-aware topology

- `basins.py` now clusters by THREAD (mean of per-turn embeddings
  within a `transcript_id`), not per-turn. A 119-turn Iain M Banks
  essay deep-dive contributes one point to basin-space, not 119
  fragmented turns. Per-basin `Basin.thread_count` (distinct sessions)
  alongside `size` (total turn count).
- `Basin.representatives` is thread-shaped:
  `{transcript_id, turn_count, headline, turns: [{id, snippet, turn_index}]}`.
  Headline = single turn closest to BASIN centroid within this thread.
- Graph labels now read the first 4 words of the top representative's
  headline (`"my attorney is setting"`, `"Hello."`) instead of TF-IDF
  vocabulary (`"get"`, `"give"`).
- Click a basin node → detail panel renders 5 representative thread
  cards. Each card has a "N turns" pill + chevron; click expands to
  10-turn conversational sequence. Single-turn threads (Gemini
  Takeout, the canonical natural fallback) get no expand affordance.
- Plus: pan + scroll-wheel zoom (d3-zoom + d3-interpolate), native
  `<title>` hover tooltip showing full representative.

### Nav harmonization

- New `.trinity-topbar` CSS in `design_system.SHARED_CSS`. Pill
  `← Launchpad` back link + page title + optional secondary action.
  One source of truth for all sub-page navigation.
- Live council, council review, and memory viewer all share the
  shape. Previously they had three different topbar conventions
  (live council buried its back button inside a content card; memory
  viewer had its own bespoke topbar).
- Launchpad stays as-is — it's the root, hero pattern fits its
  identity. DESIGN.md gets a new "Navigation pattern (sub-pages)"
  section so future pages don't drift back to bespoke headers.

### Real-data bugs caught

- **basins.py `prompt_ids[:50]` truncation broke Stage 2/4 of the
  lens pipeline** (`4abdb41`). `to_dict()` capped serialized
  prompt_ids at 50 "for readable JSON", but `load_basins()`
  round-trips the file back into Basin dataclasses. After save→load,
  `basin_for_prompt(basins, prompt_id)` returned None for any prompt
  beyond #50 — silently mis-tagging the bulk of every multi-prompt
  basin. Drop the cap; topics.json is now a faithful serialization.
- **memory viewer initially used indigo/violet** (`4abdb41`), which
  DESIGN.md actually forbids ("Do not introduce purple or neon
  accents"). Switched to the warm-paper palette (forest green +
  warm brown) — identical to launchpad now.
- **memory viewer required `trinity-local serve`** (`a598a88`).
  First-shipped version used `fetch('../memories/...')` which modern
  browsers block under `file://`. Inlined the contents the same way
  the council thread manifests do.

### Smoke + tests

- Surface 14 (a + b) added: launchpad memory chips render with all
  six names, click-through loads the viewer.
- Surface 6 (live council back-trip) updated to use the new
  `.trinity-topbar a.topbar-back` selector instead of text-matching
  "Back to Launchpad".
- Unit tests updated for `← Launchpad` text + thread-aware basin
  fixture.
- 14 surfaces, 658 tests, zero console errors on real `~/.trinity/`.

### Doc consistency sweep

Multi-pass audit (3 ticks of the `/loop 15m ...` cron) caught:

- claude.md / product-spec.md / CONTRIBUTING.md stale stat numbers
  (8-surface → 14-surface, 541/571/657 tests → 658).
- Portal table in claude.md referenced `portal_*.py` modules that
  had been renamed to `launchpad_*.py`.
- frontend-architecture.md `portal_*.py` rows updated +
  `memory_viewer.py` row added.
- spec-v1.md `/me-build` ref + "6 MCP tools" claim → `lens-build`,
  "9 MCP tools (v1.0 canonical 6 + v1.5 ask/get_picks/mark_pick_wrong)".
- product-spec.md sweep: `me-build`/`me.md`/`~/.trinity/memory/` →
  `lens-build`/`lens.md`/`~/.trinity/prompts/`.
- `commands/me.py:94` printed `trinity-local me-build` instructions
  while the actual subcommand was already renamed `lens-build` —
  caught by the doc audit even though it's a code drift.

Unused-imports sweep across 25+ files (pyflakes) — mostly stragglers
from the morning's rename pass, plus two real bugs (undefined `Path`
annotation in `embeddings/cache.py`, duplicate `research_dir()` in
`state_paths.py`).

## [Validation-driven scale + signal-quality fixes] — 2026-05-12 (evening)

Coherent arc of ~10 commits driven by running the actual product
against the user's real 46k-prompt install. Synthetic unit-test data
(≤10 vectors per token) hid these — every issue here was caught by a
hands-on `trinity-local <command>` followed by "wait, that's not
right." Pattern worth keeping: real-data validation > unit tests for
catching prod-scale issues.

### Real-data bugs caught + fixed

- **doctor reported "not seeded" on a 46k-prompt install** (`f7bf19b`).
  The old `_check_memory_seeded` / `_check_me_built` read pre-rename
  paths (`~/.trinity/memory/`, `me.md`) that no longer existed after
  the 5-memories restructure. Renamed to `_check_prompts_seeded` /
  `_check_lens_built` + added `_check_core_distilled`. Doctor now
  reports `46099 prompt nodes indexed`, `lens.md present (6431 bytes)`,
  `core.md present (928 bytes)`.

- **vocabulary distillation: 3 bugs in one feature** (`2dfc769`):
  (a) capped `iter_prompt_nodes` saw 0 embedded prompts despite 18k
  present — uncapped walker fix;
  (b) `_two_means_split_variance` OOM'd on 1000+-context tokens
  (19GB pairwise matrix) — `max_samples=200` deterministic stride;
  (c) NaN cosines leaked into synonym table (`sim < threshold` is
  False for NaN) — explicit `np.isfinite()` check.
  After the three fixes, `vocabulary` produces real signal:
  `assistant↔feature 0.992, com↔https 0.986`.

- **cross_provider_pairs: 350× speedup** (`b511ff6`). Pure-Python
  `_cosine` loop on 17.8k×17.8k pairs = ~106 minutes (extrapolated;
  never finished in any earlier session attempt). Vectorized via
  single BLAS matmul per seed — full clustering now runs in 18s.
  Found 249 cross-provider clusters in real data on first runnable
  execution.

- **dream cluster preview surfaced filler** (`862b93e`). After
  vectorization made dream actually runnable, top 30 clusters were
  conversational filler ("10 more", "Thank you.", "More options").
  Added `min_prompt_words=6` filter so substantive cross-provider
  questions (NextJS+Vercel streaming, japandi cabinet research,
  modular wet-core den) rank first.

- **basins.compute_basins: same cap bug as vocabulary** (`7cb93a1`).
  Used `iter_prompt_nodes()` capped at 5000 — `lens-build --dry-run`
  reported basins=0 on a populated install. Same fix.

- **Architectural smell caught after 3rd repeat** (`6f50087`).
  After vocabulary, basins, and dream all reinvented the uncapped
  walker, audited and discovered `iter_prompt_nodes(limit=None)` is
  the canonical uncapped API. Removed `_all_prompt_nodes_uncapped`
  helper; three modules now share the in-process mtime cache so the
  18k-node parse cost is paid once per process, not 3×.

- **replay-history: top 4/5 candidates were the same scaffolding
  prompt** (`71c3a83`). "You are extracting durable facts about
  the user…" appeared 4× in top-5 because no system-prompt filter and
  no text dedup. Added both: skip text starting with "You are " /
  "You will ", dedup by 200-char prefix.

- **Audit caught 5 more silently-buggy capped callers** (`5812c6b`).
  Same root-cause as vocabulary/basins. Fixed `bootstrap_pairs`,
  `seed`, `incremental_ingest`, `me/turn_pairs`, `replay`. Each was
  silently missing the older embedded cohort (which contains
  embeddings; recent ingest skips embedding to keep the hot path
  fast). The launchpad's `search_prompt_nodes` is intentionally
  kept capped — that's the hot UI path where the cap is correct.

### Copy + naming

- **"cortex rule" → "pick" everywhere it refers to data** (`18eb65f`).
  After `mark_pick_wrong` / `picks.json` renames, descriptive copy
  still said "user-veto on a cortex rule". Now "user-veto on a pick".
  `cortex` retained for the LAYER (consolidation process).
- **core-show CLI** (`2c208f6`). Symmetric with `lens-show`. Prints
  `core.md` verbatim, stderr-only hint when missing (so
  `core-show | pbcopy` doesn't pollute the clipboard).
- **lens.md header**: pipeline.py was writing `# /me` as the file
  header. Renamed → `# Lens`. Legacy `--legacy` build path keeps
  `# /me` since the chairman is instructed to emit that exact name +
  the legacy validator checks for it.

### Validation confirmed end-to-end on real install

- Chairman prompt loads `core.md` FIRST. Spot-checked
  `render_primary_council_prompt()`:
  > User profile (from ~/.trinity/core.md — distilled paragraph
  > subsuming the five plural core memories). … You ship leverage
  > over ownership and the concrete artifact at the boundary over
  > the comprehensive ideal…
- `lens-show`, `core-show`, `doctor`, `vocabulary`, `dream --dry-run`,
  `lens-build --dry-run`, `replay-history --dry-run` all run cleanly
  on real 18k-embedding corpus.
- 657 tests passing across the arc.
- 8/8 browser smoke surfaces green throughout.

### Stats

- 10 commits this evening session (`f7bf19b`, `2dfc769`, `18eb65f`,
  `8972599`, `b511ff6`, `862b93e`, `7cb93a1`, `6f50087`, `71c3a83`,
  `5812c6b`, plus this changelog commit).
- 657 tests passing (was 654 at session start).

## [5-memories restructure + polish-iterate + auto-distill] — 2026-05-12 (late PM)

Cohesive arc of 11 commits after the brand-v2/housekeeping commit
landed. Three load-bearing things ship here:

1. The five plural **core memories** finally have a coherent shape on
   disk + a singular **`core.md`** distillation the chairman reads
   first on every council.
2. **Polish-iterate end-to-end**: detect polish-shape tasks, surface in
   MCP route() output, opt-in setting + CLI + launchpad toggle to
   auto-chain just for them.
3. **Auto-distill is now load-bearing**: `lens-build` and `consolidate`
   auto-fire `distill_via_chairman` so `core.md` stays fresh; staleness
   skip guards the flagship call; launchpad shows a badge when core
   needs distilling.

### Five memories + one core

- **`memories/` directory** now holds the durable plural memories
  (`5-memories restructure` commit `46591e0`):
    - `lens.md`       — value memory (paired tensions)
    - `picks.json`    — procedural memory (model picks per topic)
    - `routing.json`  — empirical memory (per-category provider scores)
    - `topics.json`   — semantic memory (k-means clusters)
    - `vocabulary.md` — language memory (per Phase 2.5)
- **`core.md`** at `~/.trinity/` top-level (singular) — one paragraph
  the chairman reads FIRST before falling through to specific memories.
- **`prompts/`** (was `memory/`) — raw indexed prompts, the INPUT to
  dream. Renamed to disambiguate from `memories/` (one letter apart was
  a confusion grenade).
- **Renames inside `memories/`**: `cortex_rules.json` → `picks.json`,
  `me.md` → `lens.md`, `basins.json` → `topics.json`. All migrate on
  first access; back-compat function names retained.

### Phase 5 distill (commit `46591e0` + follow-ups)

- New `trinity-local distill` CLI + dream Phase 5/5.
- One flagship call reads the five plural memories + emits one
  paragraph in second person ("You ship leverage over...").
- **Chairman reads core.md FIRST** (`b5d4d04`): if present, the
  ~200-char distilled paragraph replaces the full lens in chairman
  context. Falls through to `lens.md` (and explains why) on cold
  installs without `core.md`.
- **Staleness skip** (`188744a`): `is_core_stale()` compares core.md
  mtime to every source. If core is newer than all of them, distill
  short-circuits with `skipped=True`. Saves ~$0.05–0.20 of flagship
  cost per redundant invocation.
- **Auto-distill hooks** (`fcbab35`): `lens-build` and `consolidate`
  call `distill_via_chairman()` on completion. Dry-run paths skip.

### Phase 2.5 vocabulary distillation (commit `d8043b3`)

- New `trinity-local vocabulary` CLI + dream Phase 2.5/5.
- Pure-geometric (no LLM): walks PromptNode embeddings, runs k=2
  silhouette to find homonyms (one word, two meanings) + cosine sim
  of mean-context vectors to find synonyms (two words, one meaning).
- Emits `memories/vocabulary.md` as one of the five plural memories.

### Polish-iterate end-to-end

- **Detection layer** (`d3650ab`): `is_polish_task(text)` heuristic in
  `task_types.py`. Two-path matcher tuned for recall: literal phrases
  ("make this better", "tighten this", "any better?") + short
  imperative hints (≤20 words + "shorter"/"simpler"/etc.).
- **Surfaced in MCP `route()`** as `auto_iterate_recommended: bool` so
  harnesses + the launchpad can offer iteration without us silently
  changing council mode (`d3650ab`).
- **Opt-in setting** (`d893b1a`): `polish_auto_iterate: bool = False`
  on TelemetrySettings. When ON, council-launch fires consensus-round
  iteration ONLY for polish tasks (vs the existing global
  `auto_chain_enabled` which fires for every council).
- **CLI toggle**: `trinity-local polish-auto-enable` / `polish-auto-disable`.
- **Launchpad toggle** (`64332df`): new row in the settings panel
  beneath "Auto-chain new councils" — flip from the UI.

### Other shipped pieces

- **`freeze_routing_to_disk()`** (`1a3d5f9`) — `routing.json` finally
  has a writer. Phase 4 of dream calls it after lens-build runs; the
  per-category provider track record is now visible to the chairman
  via core.md without re-walking council_outcomes/ per call.
- **MCP tool rename** (`218d3e4`): `get_cortex_rules` → `get_picks`;
  `mark_cortex_rule_wrong` → `mark_pick_wrong`. Clean, no aliases —
  pre-launch.
- **`tasks/` → `todos/`** (in `b5d4d04`): user-facing on-disk path
  rename to disambiguate from `task_type` (the classifier label).
  Function name `tasks_dir()` kept for internal back-compat.
- **`me-build` → `lens-build`** (`b5d4d04`, no alias): CLI renamed to
  match the file at `memories/lens.md`.
- **"Personal routing table" → "Routing"** (`188744a`): launchpad
  eyebrow + footer copy matches the filename (`routing.json`) + the
  brain-analog row in README.
- **Launchpad core-status badge** (`56b5acd`): `_core_status()` emits
  `empty` / `missing` / `stale` / `fresh`. Stale + missing render an
  in-card hint inside the Routing card directing the user to
  `trinity-local distill`.

### Stats

- 23 commits this PM session (`46591e0`, `d8043b3`, `b5d4d04`,
  `1a3d5f9`, `188744a`, `218d3e4`, `d3650ab`, `d893b1a`, `64332df`,
  `fcbab35`, `56b5acd`, …).
- 654 tests passing (was 605 at session start; net +49 across the new
  features).
- 8/8 browser smoke surfaces green.

## [Brand v2 + housekeeping pivot] — 2026-05-12 (PM)

A consolidation pass after the v1.5 cortex shipped this morning. No new
features; mostly terminology and brand cleanup so the codebase, docs,
and product surface stop fighting each other.

### Brand

- **Hero pivoted three times in one day**:
  v1: *Own your memories.* (retired — too abstract, no mechanism)
  v1.5: *We copy-paste prompts across chatbots like animals.* (retired —
  strong but standalone)
  v2 final: **Stop copy-pasting prompts. Own your context. Dream your core
  memories.** Sub: *One question. Every model you use. One answer that
  knows you.* Brand axis: **prompts** (raw, yours, indexed) → **dream**
  (the verb only Trinity has — offline synthesis) → **core memories**
  (what dream creates: cortex + lens + routing). Ratified through three
  rounds of cross-provider council iteration (`bundle_42f8cea9c9e705e5`),
  then a fourth user revision swapping the council's "Forge" verdict
  back to "Dream" because the council didn't know Dream is the CLI
  feature name + Anthropic Dreaming analog.
- **README hero + four-row elaboration rewritten**, claude.md project
  identity + status block updated, launchpad title + eyebrow + heroTitle
  + heroLede + cold-start lede all aligned. Older "Own your memories"
  references in earlier entries below describe what was true at the
  time of those commits and are preserved as history.

### Terminology

- **`task_kind`/`task_kinds` → `task_type`/`task_types`** unified across
  ~40 files. Two names for the same axis (heuristic classifier output vs
  Routing JSON schema field); collapsed to `task_type`. `task_kinds.py`
  module renamed `task_types.py`. `guess_task_kind()` kept as a
  back-compat alias to `guess_task_type()`. Distinct from `category`
  (the coarser LMArena-aligned grouping in `categories.py`).
- **`portal_*.py` → `launchpad_*.py`** (5 files: `portal_data`,
  `portal_template`, `portal_runtime`, `portal_install`, `portal_page`).
  User-facing copy says "launchpad" exclusively; the code lost its
  fossil. `~/.trinity/portal_pages/` on-disk path kept for back-compat.
- **"verifier-shaped" terminology dropped** in favor of "structured".
  Sakana's "verifier" has a precise meaning (test cases that pass/fail);
  Trinity's chairman synthesizes structured output, doesn't verify.
  Kept Sakana's exact term in `docs/spec-v2.md` + `docs/v2-loop-constitution.md`
  where it names the actual three-role action space.

### Bug fixes

- **Thread manifest losing iteration rounds** when consensus_round
  rounds shared a deterministic bundle_id. Two stacked bugs in
  `update_thread_manifest`: wrong chain_root_id fallback +
  dedup-by-bundle_id collapsed every round into one. `?thread_id=` URLs
  in the launchpad now show the full chain (3 rounds for the brand
  iteration bundle that exposed the bug).

### UX

- **Notifications default OFF**. `notify()` now reads
  `~/.trinity/settings/notifications.json` and silently skips unless
  explicitly enabled. The config.notifications flag existed but wasn't
  honored anywhere. CLI: `trinity-local notifications-enable` /
  `notifications-disable`.
- **Desktop launchpad icon stays simple**: just
  `exec /usr/bin/open file://.../launchpad.html`. Brief experiment with
  background regen reverted — `refresh_launchpad()` is already wired
  into every state-mutation path (council save, watch cycle, telemetry
  toggle), so the page on disk is fresh by the time the user clicks.
- **`trinity-local dream`** — one-command cold-start from earlier in
  the day kept. Reframed in the brand axis as the verb that produces
  the core memories.

### Stats

- 611 tests passing (added: 6 thread-manifest regression tests, 4
  launchpad-wrapper tests, 8 dream tests; net +13 from morning).
- 8 commits this PM session (`369739b`, `d28f2bf`, `92c1927`,
  `e8a5f21`, `3c44bbd`, `41bd265`, `9a2ef8c`, `7200a9f`, `6940593`).

## [v1.5 cortex Weeks 1–5 shipped] — 2026-05-12

The cortex layer (the v1.5 trajectory's headline) lands end-to-end in
one overnight session. Each piece is small; the composition is what
makes the routing visible to the user.

### Added

- **Tool-triggered incremental ingest** (task #39, `9e8af06`).
  MCP `ask` / `search_prompts` now scan transcripts newer than
  `~/.trinity/memory/cursors.json` at the start of each call, bounded
  at 1s. No manual `seed-from-taste-terminal` required to stay fresh.
  CLI: `trinity-local ingest-recent`.
- **Cortex structured geometric prior** (`c76ce09`). Consolidation
  hands the flagship a tight numeric basin description (geometric
  median via Weiszfeld, coherence via mean-cosine-to-median, manifold
  dim via participation ratio, bimodal flag via excess kurtosis on
  first PC, typicality-ordered evidence) instead of asking it to do
  geometry-in-language. Trust score now has 6 components.
- **Chairman-audit-mode** (task #47, `1844440`). `consolidate --audit`
  runs a second flagship (different provider) to vote on each
  extracted rule. Disagreement demotes trust via the audit_score
  component. Catches both rubber-stamping by the primary chairman and
  silent model regressions. Loud-fails on stderr so a broken audit
  provider can't silently leave everything "unaudited" (`48a2520`).
- **Cortex override mechanism** (`377eab8`, `bffa173`, `a7e9e38`).
  User-veto on a rule via `cortex-override` CLI or MCP
  `mark_pick_wrong`. Each click halves effective trust;
  persists across consolidations. Launchpad Health column surfaces
  overridden state with a hover-title computing the exact demotion.
- **Sigmoid-blended chairman picker** (task #52, `f06dcbb`). Replaces
  the hard "personal beats global the moment any rated council
  exists" cut with `alpha = sigmoid((n - 5) / 2)` — cold-start uses
  global benchmarks, personalization compounds smoothly.
- **User-verdict-weighted personal routing table** (task #45,
  `0bf19bd`). `record_outcome` was the most important tool, but its
  signal was discarded by the aggregator. Now weighted 0.7 over
  chairman scores.
- **Launchpad surface upgrades**: personalization-% column per
  task_type (task #40, `41ac8e7`), Health column (audit / bimodal /
  override badges with hover-titles, `0e8aa31`/`a7e9e38`), "View
  evidence" chips linking to source councils (`70fa970`).
- **HF Hub offline default** (`aa1924d`). `main()` pins
  `HF_HUB_OFFLINE=1` so Trinity never makes outbound Hub calls at
  runtime — one-time `huggingface-cli download` pulls the embedding
  model, after which everything runs from cache.
- **9th MCP tool** (`bffa173`): `mark_pick_wrong` — surface
  is now `ask` / `route` / `run_council` / `record_outcome` /
  `search_prompts` / `get_persona` / `get_council_status` /
  `get_picks` / `mark_pick_wrong`.

### Changed

- **Bimodal cortex rules fall through to kNN** (`a66c360`). v1.5
  conservative behavior promised in spec but not actually wired —
  now bimodal_flag=True forces fall-through regardless of trust.
- **`make_flagship_extractor` honors `--provider`** (`12f86d1`).
  Found-bug fix: previously hardcoded `dispatch_fn("claude", …)`
  regardless of CLI choice; dispatch shim ignored its provider
  argument. Both ends lied to each other so the bug was invisible
  until traced.
- **cortex.py split** (`9fcfbee`). Pure-numerical math (Weiszfeld,
  PCA, kurtosis) extracted into `cortex_geometry.py` (304 LOC,
  dependency-free). cortex.py dropped from 1,123 → 825 lines.

### Tests

571 passing (was 491 at session start). Coverage added for: cortex
override CLI handler, consolidate CLI gating, ingest-recent wrapper,
MCP `mark_pick_wrong`, audit failure stderr surfacing,
end-to-end centroid integration with real TF-IDF embeddings.
`scripts/smoke_install.sh` now verifies the MCP tool list post-wheel-
install — catches packaging gaps before the user hits them.

## [Trajectory pivot — v1.5 added, v2.0 sunset] — 2026-05-11

After deep-reading the Sakana TRINITY paper (arXiv:2512.04388, ICLR 2026), the trajectory
beyond v1.0 changed materially. Their 3B vs 7B Conductor ablation (Figure 7) shows both
sizes find the same routing — the 7B wins only on natural-language prompt quality. A
flagship model (Claude / GPT-5 / Gemini) with retrieval + cortex context produces better
prompts than any local 7B could, so the trained-coordinator path in v2 stops being the
shortest path to the pitch.

### Added
- **`docs/spec-v1.5.md`** — active next-trajectory spec. Ships **June 3, 2026.**
  MCP-primary two-tier tool surface (`ask` cheap default + `compare` for hard
  questions; `plan_and_execute` deferred to v1.6). Hippocampus + cortex two-tier
  memory: kNN over episodes (existing) plus flagship-extracted routing rules per
  basin (NEW). System-computed `trust_score` from 4 components (n_episodes,
  consistency, recency_agreement, diversity). Basin classifier with cosine
  threshold, top-3 soft membership, re-basining every 50 councils. Cortex
  (routing) vs Lens (evaluation) composed flow inside `ask`. Model-version-shift
  decay (not just calendar). Local model dispatch (Ollama + MLX) — contingent on
  Week 3 dispatch resilience or cut from launch pitch. Human calibration gate
  before Week 3 wires cortex into the query hot-path. Killer flow: when Claude
  Code's own sub hits a rate limit, Trinity continues your work on Codex /
  Gemini / local. Five-week plan, ship June 3.

### Changed
- **`docs/spec-v1.md`** — deferred-items section now points at v1.5 not v1.1/v1.2/v2.
  Coach Lens (former v1.2) is absorbed into v1.5's cortex layer (the extracted
  routing patterns ARE the coaching). Narrative video pipeline (former v1.1) is
  deferred indefinitely — me-card PNG is the v1.0 social object.
- **`claude.md`** — companions list + status updated to reflect v1.5 active spec.
- **`README.md`** — *"What's next"* section rewrites to lead with v1.5 (MCP-primary
  routing + cortex + local dispatch + rate-limit dodge). v2 references replaced.
- **`docs/founder-essay-draft.md`** — *"What's next"* section rewrites: v1.5 as the
  routing product, v1.6+ as multi-step orchestration, trained-coordinator path
  explicitly sunset with the reasoning (Sakana ablation, no GPU training for an
  architecture we can ship via context engineering).
- **`docs/launch.md`** — Sakana FAQ updated to reference v1.5 (and v2 sunset header)
  instead of v2 as the active spec. "What I'm holding back" section reframes around
  v1.5 mention vs trained-coordinator decision record.

### Sunset
- **`docs/spec-v2.md`** — sunset header added. Trained-coordinator architecture
  (Qwen3-0.6B + DPO / sep-CMA-ES) preserved below the header as architectural-decision
  history. **Reopens only if v1.5 hits a quality ceiling on real user data.** v1.0
  and v1.5 generate exactly the supervision data v2 would need if/when it lands.

### Why
The pitch — *"SOTA for you + your taste + your subs + saves cost"* — is what we
want to be able to literally say at launch. v1.0 alone can't say it (no routing
intelligence, no cost savings vs single-model). The trained-7B v2.0 path takes
4–8 weeks of GPU training. v1.5's flagship-as-Conductor + cortex-via-flagship-
extraction gets the same architecture in 5 weeks via context engineering. The
world is also changing weekly — trained Conductors decay when models update.
The cortex layer re-consolidates on demand. The moat is the ledger + extracted
rules, not the weights.

## [v1.0 — ship-ready] — 2026-05-09

Closing the v1 launch gap. Brand landed in code + agent context + manifesto essay.
Browser smoke gate covers all 8 testable surfaces. Remaining items are human-gated
(docker daemon, public push, tester DMs, HN timing).

### Added
- **`scripts/browser_smoke.py`** — 8-surface UI smoke via Python playwright. Asserts
  chart bars, settings modal, routing table, Copy-for-sharing clipboard, recent-council
  click → live page, back-trip to launchpad, Launch Council button presence, no
  telemetry console errors. Saves per-surface screenshots to `docs/smoke/`. Exits 0
  green / 1 fail / 2 setup error / 3 playwright missing. Replaces MCP-driven browser
  checks that kept dying between sessions. First run: 8/8 green.
- **`docs/founder-essay-draft.md`** — long-form manifesto piece for week-2 launch. Voice
  belongs to the user; polish + ship after HN front-page lands. Covers: the structural
  problem (labs commercially prevented from helping use a competitor), the local-first
  architecture, why the council shape works, three load-bearing commitments (prompts
  never upload, no LLM outside councils, free forever), the v1.1/v1.2/v2 arc, and the
  bigger thesis (*own your memories now, because the next thing you'll need to own is
  your agent*).

### Updated
- **`claude.md`** — Project identity rewritten to match v1.0 brand: *Trinity Local is
  the cross-provider memory layer the labs are commercially prevented from building.*
  Status block dated 2026-05-09. Points at `docs/spec-v1.md` (locked) and
  `docs/spec-v2.md` (held). Removes the legacy "$20-200/mo Plus tiers" line (true but
  off-brand for v1) — Trinity rides on user's subscriptions; pricing for hosted layers
  is out of v1 scope.
- **`docs/spec-v1.md`** — explicit weekly-digest deferral added to the "intentionally
  NOT in v1" list. `digest.py` was removed during the v1.1 audit and not re-added;
  `me-card` PNG is the v1 weekly-ish artifact. Real digest rendering returns in v1.1.

### Verification (final state)
- `pytest -q`: 400 passed
- `python scripts/browser_smoke.py`: 8/8 surfaces green
- `trinity-local doctor`: all checks green (provider CLIs authenticated)
- `~/.trinity/SCHEMA_VERSION` = "1"
- Hard prompts capability chart bar = 87 (Claude); routing table = 10 rows;
  copy-for-sharing = 318 chars; recent-council card click renders chairman synthesis;
  back-trip to launchpad works.

### Still human-gated (cannot ship autonomously)
- Docker smoke gate close (Docker daemon not running locally)
- Public GitHub push (decision on repo URL + visibility)
- 5 fresh-install tester DMs
- HN post timing (Tuesday 9am ET per launch sequence)
- OBS demo video (60s) — optional substitute is the static README sequence already shipped

---

## [v1.0 — locked for May 13-15 ship] — 2026-05-09

User dropped a fully-formed launch spec. Split into `docs/spec-v1.md` (locked, ships now)
and `docs/spec-v2.md` (held vision, foundation laid in v1). 10 disagreements applied vs
the original three-spec drop — see spec-v1.md for the full list.

### Added
- **`docs/spec-v1.md`** — locked v1 launch spec. Brand: *Own your memories. The AI you
  trained should outlive the provider.* Manifesto: *the cross-provider memory layer the
  labs are commercially prevented from building.* Folder schema lock + Routing JSON
  ledger format + MCP stable contract + 6-tool surface (3 stable, 3 extended) + privacy
  posture + locally-observable metrics (replacing the spec's untrackable "switches
  prevented") + 8-minute HN-reader bar test.
- **`docs/spec-v2.md`** — held vision: v1.1 narrative video pipeline, v1.2 Coach Lens,
  hosted-chairman + cross-machine `/me` sync as described *capabilities* with no pricing
  attached, v2.0 Learned Coordinator (Qwen3-0.6B DPO fine-tune as local chairman + active
  learning loop with surprise score as query selector + retrieval-augmented inference),
  v2.1+ federated taste. Per-member prompt-formulation learning. Adversarial held-out as
  echo-chamber defense.
- **`~/.trinity/SCHEMA_VERSION`** — v2 forward-compat anchor. Written by `state_dir()`
  on first access. Bumping triggers a migration when v2 adds `videos/`, `lens/geometry/`,
  `models/cortex-v{n}/` subdirs.
- **README brand swap**: H1 = *Own your memories*; manifesto callout above the fold;
  no pricing tier (tool is free; revenue decision deferred); v2 tease points at
  `docs/spec-v2.md`.
- **Launchpad cold-start hero** rewritten: first-time users land on H1 *Own your
  memories.* + lede *The AI you trained should outlive the provider. Ask one question
  — Trinity asks Claude, Gemini, and Codex, tells you which agrees and why the
  disagreement matters.*
- **`docs/launch.md` Twitter/HN copy** rewritten to narrative-beats order (fragmentation
  pain → structural problem → local-first → council as engine → taste capture →
  sovereignty stake → bigger thesis). 12 tweets. Founder narrative angle added
  (IIT KGP / Harvard GSD / Mailchimp credibility). HN title de-jargoned.

### Disagreements applied vs original spec
1. `~/.trinity/` not `~/trinity/` (macOS convention)
2. numpy not FAISS (5ms matmul wins on 28k vectors)
3. 6 MCP tools not 3 (stable/extended split — record_outcome / get_council_status / get_persona are load-bearing)
4. me-card not radar chart as the social object
5. `/trinity` Claude Code skill co-equal with curl install
6. No pricing tier — tool is free in v1; hosted-tier capability still described in spec-v2.md but no $ committed
7. Drop "cross-provider switches prevented" metric (unmeasurable under privacy posture)
8. Drop "30-second first council" claim (over-promise; realistic 30–90s)
9. API keys not in `trinity.toml` (keychain only)
10. Pairs as derived export not SoT (preserves runtime metadata)

---

## [v2-alpha] — UNRELEASED

Loop Constitution double-loop for skill graduation. Substrate only — not on the v1 ship path.

### Added
- **`src/trinity_local/loop/` package** — three modules, ~400 LOC:
  - `frame.py` — outer loop. One chairman call emits `inversions` + `eval_seed` for a skill
    intent. Sets the rails the inner loop verifies against.
  - `run.py` — inner-loop state machine. `execute → verify → cull → re-verify → commit`,
    iterated until verify passes or budget exhausts. Per iteration: 1 chairman (execute)
    + 1 verify + 1 chairman (cull). Re-verify only fires when cull modifies the artifact
    (`sha256(pre_cull) != sha256(post_cull)` gate). Structured `state.history` records carry
    verify failures into the next iteration's execute prompt.
  - `verify_web.py` — Browserbase Autobrowse `--env local` subprocess wrapper. Chairman-rubric
    fallback for non-web skills. Three regimes handled: installed+graduating,
    installed+failing, missing entirely.
- **`trinity-loop` CLI** — `frame | run | reframe` subcommands.
- **`docs/v2-loop-constitution.md`** — full spec for the held-back v2 work, with all
  ratifying councils captured inline.

### Council provenance
- `council_5fbf909119830643` (Codex won, high) — ratified the substrate: model called
  per-stage not running the loop, supervisor owns continuity, Autobrowse is the verifier,
  cull→re-verify→commit non-negotiable.
- `council_7a770b8b78b6bd4e` (Codex won, high) — ratified the double-loop compression
  from 8 modules (~1200 LOC) to 3 (~400 LOC); structured `state.history` records;
  hash-based re-verify gate.
- `council_f8174af1be1f646d` — ratified launch order (v1 first, v2 substrate held back
  for the May 13–15 ship window).

---

## [v1] — 2026-05-07 to 2026-05-08

The lens-discovery pipeline + the launch-readiness gates that took it from "shipped" to
"shippable." Trinity now produces taste-terminal-quality output:
**1 cross-basin lens + 6 orderings + 52 validated rejection signals** from a real-corpus run.
**400 tests passing** (was 314 entering this milestone). Three independent councils ratified
**conditional ship for May 13–15** with docker smoke as the only remaining technical gate.

### Launch readiness — pre-flight gates (council_35b2ae198a65b349)
- **`trinity-local doctor`** — pre-flight cold-install checks. Each ✗ surfaces a one-line fix
  command. Detects: provider CLIs installed + authenticated, MCP dep present, Trinity dir
  writable, config valid, memory seeded, `me.md` built. Council eval seed: *name a specific
  cold-install failure mode AND the exact CLI command that detects it before the user hits
  a live council.*
- **`trinity-local me-card`** — render the strongest `/me` lens as a 1200×630 PNG (OG-spec).
  F3 (zero user screenshots in 14 days) mitigation per launch council. Stacked-poles layout
  with horizontal divider + "vs." centered (font-independent — avoids `↔` tofu issue).
  Empty-state fallback when no lenses built yet.
- **`trinity-local council-last`** — instant council on the last Claude Code prompt (or
  explicit `--task`). Onboarding (c) per council; explicitly NOT a clipboard reader (privacy
  positioning self-own per claude+codex agreed claim).
- **README rewrite** — privacy section above the fold (G3), `vs LMArena/promptfoo/OpenRouter/
  Karpathy LLM Council` comparison table (G5), me-card hero image, doctor in quickstart.

### Launch readiness — cold-install gate (council_5699d0e62cf965d0 + council_d55953003bb29f9d)
- **`LICENSE`** (MIT) + `pyproject.toml` PEP 639 license expression (`license = "MIT"`,
  `license-files = ["LICENSE"]`). Setuptools≥77 rejected the deprecated classifier; the
  expression is the modern path.
- **`scripts/smoke_install.sh`** — three-mode (local / docker / both) deterministic gate
  matching council_5699d0e62cf965d0's eval seed verbatim: build wheel, install in fresh
  venv, run `trinity-local doctor --json`, assert Trinity-internal checks pass and
  `LICENSE` exists. Provider CLIs are expected absent in the smoke env and don't fail the
  gate. Local mode green; docker mode pending Docker Desktop.
- **`/trinity` Claude Code skill** — `.claude/skills/trinity/SKILL.md` + bundled copy at
  `src/trinity_local/data/skills/trinity/SKILL.md`. Does pip install + `install-mcp` +
  `doctor` + optional first-council in one invocation.
- **`install-mcp` drops the skill globally** — package-data ships SKILL.md in the wheel;
  `_install_trinity_skill()` writes to `~/.claude/skills/trinity/SKILL.md` via
  `importlib.resources`. Idempotent: no-op when content matches; refuses to clobber
  user-modified copies (Codex's dissent point — protects customizations across pip
  upgrades). The deterministic post-validator extends `smoke_install.sh` to assert the
  file lands at the target path.
- Council `council_d55953003bb29f9d` (Claude won, high) named *"skill not installed by pip
  path"* as the #1 launch risk and ratified package-data integration as the only acceptable
  fix — curl-only install was rejected as launch-day friction. Verdict: **conditional ship
  for May 13–15** with docker smoke as the remaining gate.
- README "Demo" section — launchpad screenshot (`docs/launchpad_example.png`, captured via
  Playwright on the actual rendered page, fullPage 1280×3329 showing the populated personal
  routing table) + verbatim chairman outcome JSON sourced from the launch-readiness council's
  own verdict (the recursive ratification example). Council ratified a static README
  sequence as an acceptable substitute for a 60s OBS demo video.

### Launch copy (council_4f34cd1181d5bd08)
- **`docs/launch.md`** — Twitter/X thread (10 tweets), README hero rewrite candidate,
  HN title + first-comment opener, 60s demo script, failure-modes-to-guard-against list,
  pre-send checklist. Council (Codex won, high) ratified conditional greenlight with five
  edits applied:
  1. Ledger moved to tweets 1–2 (was buried at tweet 6 — F1 wrapper-framing risk).
     Opening verb changed: *"asks all three"* → *"records disagreement as routing
     evidence"* + the behavior-change line *"the click you make today changes which model
     gets trusted tomorrow."*
  2. HN title de-jargoned: dropped "structured" — *"Show HN: Trinity Local — a local
     routing ledger for Claude, Gemini, and Codex."*
  3. Tweet 5 `/me` lens uses verbatim accepted lens from `~/.trinity/me/lenses.json`
     (*"leading proxy signal as forecast"* vs *"official lagging metric as truth,"* with
     both failure modes named). Empty `me.md` would be a launch blocker; we have one.
  4. Tweet 8 install copy adds the CLI-auth setup caveat (the 3-CLI auth cliff would
     otherwise break "rides on subscriptions you have").
  5. Recursive demo (tweet 7) reframed: *"exposed the failure mode, named the test, drove
     the commit."*
- Eval seed pinned at top of file: *tweet 1 or 2 must name the local Routing JSON ledger
  as the primary product behavior, not multi-model comparison.*

### Added (lens-discovery capstone)
- **Lens-discovery pipeline** (`src/trinity_local/me/`):
  - Stage 1 — k-means basins on PromptNode embeddings (`me/basins.py`). Sentinel-aware
    clustering; NaN-row defense.
  - Stage 2 — chairman extracts `decisions.jsonl` (`me/decisions.py`). Valence enum
    `satisfaction | regret | unresolved | correction | cost`. Basin tags re-attached from
    prompt_id ground truth, never trusted from chairman output.
  - Stage 3 — chairman pair-mines with three tests (tension / dual evidence / failure-mode
    legibility) (`me/pair_mining.py`). Verdicts: `accepted | preserve_as_ordering | dropped`.
  - Stage 4 — deterministic basin post-filter. ≥3 basins required for accepted lens
    (TASTE_WIKI_SCHEMA spec). Sentinel ids (`"?"`, `"unknown"`) stripped before counting.
- **Stage 0 — turn-pair gap extraction** (`me/turn_pairs.py`). One batch chairman call classifies
  (model_response, user_next_turn) pairs into REFRAME / COMPRESSION / REDIRECT / SHARPENING.
  **Deterministic post-validators** (the load-bearing piece per `council_e7560934cb1f1d72`):
  - REFRAME: substituted frame must persist into next user turn.
  - COMPRESSION: user word count ≤ model word count / 10.
  - REDIRECT: model answer must be structurally multi-part (numbered/bulleted/≥3 sentences).
  - SHARPENING: user must share ≥2 keywords with model.
  Validator drop log persisted to `me/rejections_dropped.jsonl` so chairman drift is auditable.
- **Thread-per-page UX**: refines append in-place. `?thread_id=` URL stacks all rounds of a chain
  on one scrollable page. Click-to-collapse round dividers (▸/▾ chevrons). Live-streaming
  in-flight rounds via pending manifest registration in `update_thread_manifest`.
- **`bundle_id` as canonical chain root identifier** — stable from launch time (vs.
  `council_run_id` which is allocated at finalize). Fixes the "thread tile loads blank mid-run"
  class of bug.
- **Hero copy** differentiates first-time (`Run Your First Council`) vs returning user
  (`Run a Council`) based on `recentCouncilsCount`.
- **Launchpad** renders `paired_lenses` + `orderings` blocks from the new pipeline; legacy
  rejection cards still render when present.
- **`/me` markdown**: lenses + orderings + rejections (grouped by signal type, capped at 5
  examples per type).

### Changed
- `/me-build` is now a 4-stage pipeline writing `lenses.json`, `orderings.json`,
  `rejections.jsonl`, `basins.json` — replacing the legacy single-pass chairman call (kept
  available behind `--legacy`).
- Lens prompt explicitly demands abstract pole names: BAD examples (`speed/momentum to close`)
  vs GOOD examples (`infrastructure over interface`, `locked corpus over forward theory`).
  Pulled from `~/.taste/wiki/taste/lens.md` to anchor the chairman's standard.
- Drift instrument explicitly **rejected** as "topic-shift, not value-shift" metaphor (per
  `council_70eaf228d7753074` agreed claims). Centroids stay only as basin tags for the
  post-filter.
- Decision parser ground-truths basin tags from `prompt_id` lookup; chairman's `basin` field is
  treated as untrusted.
- Word-boundary truncation in `_truncate()` so tile titles stop ending mid-word
  ("…or p…" → "…or…").
- Conditional pluralization on the lens block label
  ("Paired lens (the tension you live in)" vs "Paired lenses (the tensions you live in)").
- Lens failure modes split onto two lines per pole instead of one long sentence.
- Taste-card meta: dev-facing "Refresh with `trinity-local me-build`" → consumer-friendly
  "Refreshes when /me-build runs".
- Live council page: removed redundant "Continue this thread" eyebrow + "Continue the
  conversation" h2 stack; collapsed to a single clean header. Auto-chain button drops
  "stop when converged" parenthetical.
- Ratings card meta: "Aggregated from N replay councils · /100" → "Scored 0–100 from N replay
  councils".

### Fixed
- **Cache-buster bug on file:// URLs**: browsers treated `?t=…` as part of the literal filename
  and 404'd every JSONP fetch. Skip cache-buster when base starts with `file://`. Affected
  outcome JSONP, status JSONP, and thread manifest JSONP.
- **Notifications spawning Trinity.app**: `notify()` routed via `open -a Trinity.app --args
  notify` and Trinity.app's default action was "open launchpad", so every council start fired a
  duplicate launchpad tab. Switched to direct `osascript display notification`.
- **Chain dispatches auto-opening completion tabs**: `command_for_dispatch()` unconditionally
  passed `--open-browser` to chain `council-iterate` calls. The live page already polls the
  status_token in-place; the auto-open spawned a duplicate tab. Drop the flag for chain
  dispatches.
- **Petite-vue ReferenceErrors**: `providerModels` and `formatProviderLabel` referenced in the
  template but not exposed as app-scope data. Moved to `LaunchpadApp` data + methods.
- **Council-start notification redundancy**: dropped the system notification at run start
  (Script Editor icon, no Trinity branding, redundant with the in-page "Council running" view).
  Completion notification still fires.
- **Round N label on freshly-appended chain segments**: divider showed "Round 1" until
  completion handler overwrote it. Now optimistic increment: `parent.roundNumber + 1` set on
  append.
- **Blank live council page on `?thread_id=`** when the council was running: thread manifest
  had no entry for the in-flight round. `register_pending_round()` writes a placeholder entry
  at init keyed by `bundle_id`, replaced when `save_council_outcome` finalizes.
- **Sentinel basin ids inflating lens spread**: chairman emitted `"?"` or `"unknown"` for
  decisions it couldn't tag, those values counted as distinct basins in the post-filter.
  Stripped at parse and re-stripped defensively in the filter.

### Council provenance for v1 architecture decisions
Lens-discovery pipeline:
- `council_70eaf228d7753074` — Option C ratification (basins as verifier, drop drift instrument)
- `council_c63fa273bdc2ed21` — valence enum expanded to include `correction` and `cost`
- `council_6892781d06ac3fa8` — Stage 0 turn-pair gaps as highest-leverage import from taste-terminal
- `council_e7560934cb1f1d72` — Stage 0 = batch chairman call gated by deterministic validators

Launch readiness:
- `council_35b2ae198a65b349` — pre-flight gates (doctor / me-card / council-last) + onboarding shape
- `council_5699d0e62cf965d0` — cold-install gate (LICENSE + smoke_install.sh + PEP 639)
- `council_d55953003bb29f9d` — #1 risk = skill not in pip path; ratified package-data integration; **conditional ship verdict for May 13–15**
- `council_4f34cd1181d5bd08` — launch copy review (Twitter/HN/demo); five edits ratified

### Remaining ship gates (human-blocked)
- **Docker smoke** — `bash scripts/smoke_install.sh docker` (pending Docker Desktop daemon).
  The only remaining technical gate per `council_d55953003bb29f9d`.
- **Public push** — repo not yet pushed to the GitHub URL referenced in launch copy.
- **5 fresh-install testers** — DM ask, can't automate.
- **OBS demo recording** — optional; council ratified static README sequence as substitute.

---

## [v1.1] — 2026-05-05

4-iteration council audit shipping simplifications + bug fixes.

### Changed
- Dropped `auto_council.py`. Auto-trigger logic folded into `route()`'s heuristic ranker
  (~30 LOC inside `ranker/heuristic.py`). −150 LOC, one fewer module.
- Collapsed `judge()` into `run_council(responses=[...])`. When `responses` is supplied,
  skip member execution and go straight to chairman synthesis. Drops MCP surface from
  7 → **6 canonical tools**: `route`, `run_council`, `record_outcome`, `search_prompts`,
  `get_persona`, `get_council_status`.
- Dropped `personal_routing_table.json` as durable state. Now computed on-demand from
  `~/.trinity/council_outcomes/*.json` via `compute_personal_routing_table()`. Eliminates a
  whole class of state-divergence bugs.
- Dropped `TranscriptNode` tier (zero references in `portal_data.py` / `portal_template.py`).
- Folded `prompt_shape.py` into `ranker/heuristic.py`.
- `/me-build IS a council` — single-pass chairman over MMR-sampled chunks. Drops `~/.taste/`
  dependency entirely.
- Embedding-free product surface: launchpad autofill, MCP `search_prompts`, `replay-history`
  candidate selection use pure heuristics (substring + recency + replay-value). No nomic model
  load on the hot path.

### Fixed
- HIGH#1 — latency-aware routing actually shipped (`route()` now consumes `latency` arg).
- HIGH#2 — `route()` honors `needs_council` from `RoutingDecision`.
- HIGH#3 — personal routing table includes all rated outcomes, not just feedback-rated.
- HIGH#4 — `install-mcp` adds Codex CLI; promote `mcp` dependency.

Council provenance: `council_1a8d7555bd9f959d` (Claude won, high). Routing lesson: *"For
architecture_review, prefer claude because it gives exact deletion targets with risk-aware
sequencing."*

---

## [v1.0] — 2026-04-29 (Phase 0–6 substrate)

The substrate that everything since builds on.

### Added
- **Embeddings package** — `nomic-embed-text-v1.5` at 768d (Matryoshka shrink-tolerant), batched
  `embed_batch()`, persistent disk cache (`~/.trinity/cache/embeddings.jsonl`).
- **Memory hierarchy** — `PromptNode` (atom) + `TurnWindow` (local context) index. Numpy matmul
  fast-path (28k vectors → ~5ms search).
- **Council runner** — parallel-mode (members run simultaneously) and chain-mode (sequential
  refinement). Chairman synthesis emits structured Routing JSON with `agreed_claims`,
  `disagreed_claims`, `winner`, `runner_up`, `provider_scores`, `routing_lesson`, `eval_seed`.
- **6 canonical MCP tools** (settled in v1.1; called out here for substrate completeness).
- **Personal routing table** — chairman-auto-selection via `predict_strongest_chairman()`.
- **macOS Shortcuts dispatch** — `~/.trinity/bin/trinity-dispatch` shell wrapper, Apple-signed
  Shortcut bundle for the launchpad → Shortcut → CLI bridge.
- **Launchpad portal HTML** — petite-vue static page rendered from `portal_data.py` +
  `portal_template.py`. Autofill, personal routing table card, recent councils.
- **Seeded corpus** — 18,274 PromptNodes from claude_ai + chatgpt + gemini-takeout exports
  (parsers in `ingest.py`).
- **Research package** (`src/trinity_local/research/`) — offline replay, hard-mining, ranking
  evaluation. Not on the live product path.

---

## Versioning

- **v1.0 / v1.1 / v1**: cumulative phase + capstone milestones for the lens-discovery substrate.
- **v2-alpha**: Loop Constitution double-loop. In development.
- **Phase 9** (learned tiny coordinator, sibling work): explicitly later. Not in this changelog.
