---
class: historical
---

# Cut Candidates — Honest Review

> Written 2026-05-26 as a pre-launch audit pass. **Status 2026-05-27**:
> Phases 1 (doc moves), 3 (shortcuts_integration cut), and the
> Phase-2-pivot (GA4 wiring instead of cut) all landed in commits
> `c99044f` + `90a3f12`. Plus the gstack reliability arc shipped 5 new
> structural guards. Phases 4 + 5 deferred — see "Deferred work" at
> the bottom for the unblock path.
>
> Quantitative snapshot (post-Phase-1-3 + reliability):
> 44.7k LOC `src/` (-50 from shortcuts_integration delete),
> ~6.5k LOC live+aspirational docs (was 11.5k — moved ~5k LOC to
> docs/historical/), 51 CLI subcommands, <!-- canonical:mcp_tool_count -->8<!-- /canonical --> MCP tools, 6 schemas,
> 88 retired-name registry entries (+1 shortcuts_integration).
> Test gate: 2120 passing + 7 skipped (3 skipped via the new
> `@pytest.mark.slow` quarantine; gstack pattern 3).
>
> This is one reader's opinion (Opus 4.7) after walking every module
> and doc against code reality. The user (vishigondi) has final call.
> Each item carries a confidence rating: **HIGH** = cut is safe and
> reversible; **MEDIUM** = cut requires a small migration; **LOW** =
> directional opinion, not a recommendation.

## Headline

**Trinity has grown a ~30% bloat layer in three categories:**

1. **Doc bloat** — 13 aspirational docs (5,400+ LOC) describing futures
   that already shipped or were retired. The active reader has to walk
   through retirement callouts to find current truth.
2. **Feature bloat** — Several CLI verbs / subsystems that earned
   their place during exploration but haven't justified themselves
   post-launch: `telemetry` (5 verbs, endpoint pointing at
   `example.invalid`), `adapters`, `vocabulary`, `decision-log`,
   `replay-history`, share-card rendering (~1k LOC for PNG outputs
   nobody verifies anyone uses).
3. **Defensive infrastructure** — `test_doc_count_consistency.py` is
   6,842 LOC with 60 test classes and 164 guards. It's load-bearing
   (catches real drift) but every cut here costs guard maintenance.
   `retired_names.py` is 765 LOC with 87 entries — its own kind of
   debt.

**What's load-bearing (do not touch):** the lens pipeline (`dream` /
`lens-build` / `me/`), the council runtime, the <!-- canonical:mcp_tool_count -->8<!-- /canonical --> MCP tools, the
Chrome extension + capture-host pipeline, the 6 schemas, the
`import_provider_memory` loop, the moves substrate (just shipped —
give it 4-6 weeks of real use before cutting).

## Cut list (by category)

### CATEGORY A — Doc bloat (cut/move now, no code impact)

| Doc | LOC | Verdict | Reason | Confidence |
|---|---|---|---|---|
| `docs/scale-plan.md` | 1709 | **MOVE Phase 0–8 sections to `docs/historical/`; keep only the active "Themes" planning sections** | Phase 0 was audited 2026-04-30 against a checkpoint that no longer matches reality. Phases 1–8 are about MCP install + extension capture — both shipped. The active part is "Themes A–K" (lifecycle gaps, retention, etc.). Splitting saves ~1300 LOC of dead planning text. | HIGH |
| `docs/spec-v1.5.md` | 916 | **MOVE to `docs/historical/`** | Front matter already says "**spec only, follows v1.0 ship.** Target: ship June 3, 2026." But v1.5 features (ask, get_picks, mark_pick_wrong, cortex picks) all shipped pre-launch (May 13–15). The doc is mostly retirement notes weaved through prose. The shipped state lives in `claude.md` + `docs/product-spec.md`. | HIGH |
| `docs/spec-v1.6.md` | 643 | **MOVE to `docs/historical/`** | First line says "**mostly shipped 2026-05-14/15** alongside the v1.0 launch window." Browser-extension architecture is documented better in `docs/INSTALL-extension.md` + `docs/three-tier-architecture.md`. Keeping the spec around just creates "wait, what's the actual contract" confusion. | HIGH |
| `docs/cross-platform-spec.md` | 623 | **MOVE to `docs/historical/`** | I added a top-of-file retirement callout this session noting that all `handoff` references describe a retired primitive. The desktop+mobile expansion described here is real future work but the framing (handoff as cross-surface primitive) is wrong post-2026-05-26. Rewrite from scratch when desktop ships. | HIGH |
| `docs/founder-essay-draft.md` | 252 | **DELETE (or move to private notion/google doc)** | It's a marketing draft, not docs. Drafts belong in private writing tools, not `docs/`. If kept, future readers wonder if it's the canonical voice. | HIGH |
| `docs/sweep-patterns.md` | 337 | **MOVE to `docs/historical/`** | Meta-doc explaining how to do doc-sweeping. Useful when the user is actively running sweeps; dead weight for a public-repo reader. Could fold the highest-value patterns into `CONTRIBUTING.md` (one paragraph). | HIGH |
| `docs/simplification_log.md` | 654 | **DELETE from public repo** | Already `class: historical`. It's working memory ("KILL / COLLAPSE-INTO / KEEP / PROPOSAL" log) from the simplification arc. Internal scratchpad — doesn't belong in a public repo at all. Move to private archive. | HIGH |
| `docs/PUBLIC_READINESS_PLAN.md` | 136 | **DELETE from public repo** | Already `class: historical`, completed checklist of pre-launch tasks. Same shape as simplification_log — internal scratch. | HIGH |
| `docs/training-data.md` | 23 | **DELETE** | 23 lines, `class: historical`. Pre-launch training-data planning. Pure noise now. | HIGH |
| `docs/architectural-gaps.md` | 494 | **MOVE to `docs/historical/`, OR keep but rewrite as ~100 lines** | Themes A–K gap analysis. Most are now shipped (Theme A uvx, Theme D uninstall, Theme K CDN bundle); the few still open (e.g. export/restore) are 1-line items. Currently reads like a long pre-launch worry sheet. | MEDIUM |
| `docs/v2-loop-constitution.md` | 268 | **DELETE from public repo** | Already `class: historical`. References the retired trained-coordinator v2 path that was sunset alongside `plan_and_execute`. The architectural ideas are interesting research notes but not production docs. | MEDIUM |
| `docs/frontend-architecture.md` | 443 | **REWRITE or DELETE** | Aspirational doc; reality is `launchpad_template.py` is 3191 LOC of f-string HTML. A pragmatic 50-line "here's where the JS modules live" + "how the IIFE-wrapped petite-vue works" beats 443 lines of planning. | MEDIUM |
| `docs/telemetry-spec.md` | 431 | **DELETE** (see Category C cut of telemetry) | If telemetry stays cut, this doc has no referent. If telemetry survives, the doc is still ~3× longer than the actual code surface needs. | MEDIUM (depends on B) |
| `docs/design-frame.md` | 259 | **MOVE to historical** | One-paragraph design philosophy stretched to 259 lines. Either compress to a section in `claude.md` or move to historical. | LOW |
| `docs/launcher-patterns.md` | 156 | **MOVE to historical or DELETE** | Documents the retired macOS Shortcut + Trinity.app dispatch patterns. The "Tool-triggered ingest replaces watchers" pattern is the only thing alive; that's 1 paragraph in CLAUDE.md already. | MEDIUM |
| `docs/pending-questions.md` | 49 | **DELETE** | Has 0 references from anywhere. Internal Q&A. | HIGH |

**Net doc savings if all HIGH+MEDIUM cuts applied: ~5,200 LOC removed
or moved to historical** (44% of the live+aspirational doc surface).

### CATEGORY B — Live doc consolidation (rewrite, save ~30% LOC)

| Issue | Fix | Confidence |
|---|---|---|
| **4 install docs** (`INSTALL-skill.md` 133 LOC + `INSTALL-pip.md` 136 LOC + `INSTALL-extension.md` 152 LOC + `install-deep.md` 130 LOC = 551 LOC across 4 files) | Collapse to **2**: `INSTALL.md` (primary — curl-bash + uvx, absorbs install-deep + INSTALL-pip) + `INSTALL-extension.md` (Chrome ext only). Target: ~300 LOC total. | MEDIUM |
| **3 launch docs** (`launch.md` 306 + `launch-package.md` 284 + `LAUNCH_CHECKLIST.md` 116 = 706 LOC) | Public: keep `launch.md` only. `launch-package.md` is marketing copy variants — fold into `launch.md` or move to private. `LAUNCH_CHECKLIST.md` is pre-launch todo — move to private after launch ships. Target: ~300 LOC public. | MEDIUM |
| **4 spec docs** (`spec-v1.md` 294 + `spec-v1.5.md` 916 + `spec-v1.6.md` 643 + `spec-v2.md` 414 = 2267 LOC) | Per Category A: move v1.5 + v1.6 + v2 to historical. Keep `spec-v1.md` only as the locked v1 contract. Target: ~300 LOC public. | HIGH |
| **`docs/demo/README.md`** (just rewrote this session — references retired handoff demo) | Already updated, but check the asciinema casts exist (neither does — the file describes recording instructions without any actual recordings). Either record at least one cast or move the dir to historical. | HIGH |

### CATEGORY C — Feature cuts (code impact, requires care)

| Feature | LOC | Verdict | Reason | Confidence |
|---|---|---|---|---|
| **Telemetry subsystem** (`telemetry.py` 91 LOC + `commands/telemetry.py` 91 LOC + 5 CLI verbs + `~/.trinity/settings/telemetry.json` + `docs/telemetry-spec.md` 431 LOC + telemetry_show / enable / disable / reset-id / endpoint) | ~700 LOC total | **CUT entirely** | The user's own telemetry config has `endpoint: "https://example.invalid/telemetry"`. There's no real endpoint, no consumer of telemetry data, and the launch hasn't happened yet so there's no installed-user data to lose. If/when telemetry is needed for v1.1, design it fresh against a real endpoint. Keeping the surface signals "we collect usage data" — exactly the wrong message for a privacy-first product. | HIGH |
| **`shortcuts_integration.py`** (47 LOC) + 6 import sites in `council_review.py`, `launchpad_data.py` | ~50 LOC + cleanup | **CUT — already an "inert shim"** | The module's own docstring + retired_names.py say it's an inert shim left so legacy imports don't break. But it's imported in 6 places. Either rip it out (and the imports + DEFAULT_SHORTCUT_NAME refs in `council_review.py` / `launchpad_data.py`) or formally retire it. Currently the dead-but-imported pattern is worse than either option. | HIGH |
| **Share-card surface** (`me_card.py` + `me-card` CLI + `eval_card.py` + `council_card.py` + `share_card_base.py` + Pillow runtime dep dedicated to PNG render) | ~1000 LOC + Pillow dep | **CUT or DEFER post-launch** | The pitch ("Trinity picks the answer you would have picked") doesn't need share images. Pillow is the only non-MCP/numpy runtime dep — removing it gets to 2 runtime deps. If users want share images, they screenshot. The "social object" framing was load-bearing pre-launch but post-launch nobody's been observed sharing one. **The eval-share `--compare` PNG might be load-bearing for the eval benchmark publication** (task #116 referenced it) — keep that one; cut the rest. | MEDIUM |
| **`vocabulary.py`** module + `vocabulary` CLI verb | 420 LOC + 70 LOC CLI + dream Phase 2.5 | **CONSIDER CUTTING — see Phase 2.5 of dream** | The vocabulary memory (`memories/vocabulary.md`) is one of the four "thinking memories" the chairman reads. But: dream Phase 5 (`core.md` distill) reads lens.md + topics.json + vocabulary.md and synthesizes core. If `core.md` is the actually-read thing, vocabulary.md is upstream input not direct chairman context. Either: keep as dream-internal (delete the CLI verb + standalone command), or cut entirely if Phase 5 can synthesize core from just lens + topics. | LOW |
| **`decision-log` CLI** (`commands/decision_log.py` 214 LOC + tests + `~/.trinity/me/decision_log.jsonl` schema) | ~250 LOC | **CUT** | Recently shipped (task #137, 2026-05-23). The pitch was "capture strategic decisions at decision-time with would_flip_if counterfactual" — high-quality signal at weight 2.0 to lens Stage 2. But: it requires the user to interactively log decisions, which adds friction. 3 days post-ship, 0 evidence of organic use. The lens pipeline works without it (transcripts are the signal). | MEDIUM |
| **`replay-history` CLI** (`commands/replay.py` 298 LOC) | ~300 LOC | **CUT** | Power-user verb to replay outcomes against current routing. 1 test. The signal it produces (would the new router agree with old verdicts?) isn't surfaced anywhere user-facing. Mark as `debug` subcommand if kept, else cut. | MEDIUM |
| **`seed-from-taste-terminal` CLI** | 339 LOC + 1 test | **CONSIDER CUTTING** | Backward-compat seed verb. Pre-Trinity there was a "taste terminal" sibling project; this verb migrates from its disk format. Almost certainly 0 users will run it now. Document the migration in MIGRATION.md and cut the verb. | LOW |
| **`adapters` CLI verb** | 35 LOC + 0 tests | **MERGE INTO `status`** | The verb shows "provider adapter discovery and status" — exactly what `status` already shows. Zero unique value. | HIGH |
| **`download-embedder` CLI** | 91 LOC + 1 test | **MERGE INTO `status` or `install`** | One-shot setup verb. Belongs as a subaction of `install-mcp` or a sub-flag of `status --setup`. The dedicated top-level verb is bloat. | MEDIUM |
| **`debug` CLI** with `replay-history` / `consolidate` / `vocabulary` / `seed-from-taste-terminal` subverbs | wrapper module | **REVIEW** | The debug umbrella is fine as a power-user hatch. But its subverbs duplicate top-level verbs (`consolidate` is exposed both as top-level AND via `debug`). Pick one location. | LOW |
| **Aspirational `principles.md` pipeline** (mentioned in CLAUDE.md as "data-gated — needs ≥100 council outcomes; not on a numbered task yet") | (not yet built) | **DON'T BUILD** until you cross the 100-outcomes threshold | This is correctly gated. The CLAUDE.md callout is fine — just resist starting it early. | HIGH (advice, not a cut) |

**Net code savings if all HIGH+MEDIUM cuts applied: ~2,500–3,000 LOC**
removed from `src/` (5–7% of source surface). Plus a runtime dep
removed (Pillow), reducing to 2 deps total (mcp + numpy).

### CATEGORY D — Test bloat (the doc-consistency leviathan)

`tests/test_doc_count_consistency.py` is **6,842 lines, 60 test
classes, 164 guards**. It's the single biggest test file in the repo
and ~15% of total test LOC.

**Honest read:** every guard there earned its place from a real doc-
drift bug. The "lying about retired tools" / "stale CLI verb in docs"
/ "wrong count in claude.md" / "retired subsystem still claimed live"
guards are exactly the discipline that kept this codebase honest
through three brand pivots and ~10 retirements.

**But:** ~5,200 LOC of aspirational docs (Category A) carry their own
mirror in this test file. Once the aspirational docs move to
`docs/historical/`, the guards defending them can also retire. **Conservative
estimate: ~30 guards can retire alongside Category A cuts**, dropping
this file by ~2,000 LOC.

**Recommendation:** don't preemptively cut tests. Apply Category A
first; the corresponding guards will fail loudly and you'll know
exactly which ones to retire.

### CATEGORY E — Architectural observations (not cuts, but worth noting)

| Observation | Note |
|---|---|
| **`launchpad_template.py` at 3191 LOC** | Single f-string HTML template. Pragmatic given "no build step" + "works under file://" constraints, but the file is a maintenance hazard. A pre-launch swap to a real template engine (Jinja2 — would add 1 dep) might reduce it 40%. Post-launch cost is much higher. | DECIDE before launch |
| **`council_review.py` at 1954 LOC** | 7 functions/classes — those are big functions. Split into ~3 modules (response rendering / Routing JSON card / shortcut wiring) for clarity. Mechanical refactor. | LOW priority |
| **`mcp_server.py` at 1605 LOC, 23 functions** | <!-- canonical:mcp_tool_count -->8<!-- /canonical --> tool handlers + dispatcher + resource catalog. Could split per-tool into `mcp_tools/<name>.py` files. Cosmetic. | LOW priority |
| **`doctor.py` at 881 LOC, called by `status`** | The `doctor` verb retired but the module survives because `status` calls into it. Either rename `doctor.py` → `status_checks.py` (it's not "doctor" anymore) or fold into `commands/status.py`. The name is misleading. | MEDIUM priority |
| **`retired_names.py` at 765 LOC, 87 entries** | The registry is load-bearing for the agent — tells future-me "this thing was tried, here's why it failed." But 87 entries is a lot. Sort by date and prune entries older than 90 days post-retirement to a `historical/retirement-log.md` file. | LOW priority |
| **`memory_viewer.py` (1923 LOC) + `council_review.py` (1954 LOC) + `launchpad_template.py` (3191 LOC)** | These three HTML-rendering modules total 7,068 LOC. About 16% of `src/`. Whether this is bloat depends on whether the launchpad-as-UI is load-bearing for adoption. If most users live in MCP / CLI and never open the launchpad, this is enormous overhead. Telemetry to "did the user open file:// to the launchpad" would resolve this; without it, judgment call. | DEPENDS |

## What I'm *not* recommending you cut

- **Moves substrate** (just shipped #167–#174). Give it 4–6 weeks of
  real use. The Bayesian gate is theoretically sound; whether it
  earns its keep is empirical and only answerable with usage data.
- **Eval harness** (`eval-build` / `eval-run` / `eval-show` /
  `eval-share` / `eval-prompt` / `eval-import`). Core to the
  "Trinity vs Claude vs GPT on YOUR data" pitch. Load-bearing.
- **MCP Resources** (`trinity://memories/...` + scoreboards). Just
  shipped; cross-provider continuity now rides on them. Load-bearing.
- **Chrome extension + capture-host pipeline**. 2,675 LOC of JS +
  786 LOC of Python — substantial but the only way to capture
  claude.ai / chatgpt.com / gemini.google.com web sessions
  without a cloud proxy. Load-bearing for the wedge.
- **Schema files** (6 schemas + examples + write conformance tests).
  Load-bearing for the "folder is the API" promise. Just shipped
  3 new ones; tests prove the writers conform. Keep.

## Order I'd execute (if I were you)

1. **Today, blast radius low**: Cut all of Category A (move
   aspirational docs to historical, delete drafts/scratch). The
   `~5,200 LOC` removed makes the repo dramatically cleaner for
   public eyeballs. Run tests; retire any failing guards.

2. **Today, blast radius medium**: Cut `shortcuts_integration.py`
   (already an inert shim) and `adapters` CLI verb (zero value).
   Each is a sub-30-LOC change.

3. **This week, blast radius medium**: Cut telemetry subsystem
   end-to-end. The endpoint points at `example.invalid` —
   nothing's calling it. Removing it is one of the cleanest cuts
   available and strengthens the privacy pitch.

4. **This week, blast radius medium**: Collapse 4 install docs to
   2, collapse 3 launch docs to 1. Rename `doctor.py` → `status_checks.py`.

5. **Pre-launch, blast radius higher**: Decide on share-card
   surface. Either commit to it (and prove someone shares) or
   cut Pillow + the 1000 LOC + the dedicated `me-card` /
   `eval-share` / `council-share` CLI verbs to just `eval-share`
   for the cross-provider benchmark PNG (load-bearing for #116).

6. **Post-launch, with usage data**: revisit `decision-log`,
   `vocabulary`, `replay-history`, `seed-from-taste-terminal`,
   `download-embedder`. Cut whatever telemetry confirms isn't used.

## What this would look like as numbers

| Surface | Before | After (HIGH+MEDIUM cuts) | Reduction |
|---|---|---|---|
| Live + aspirational docs | 11,474 LOC | ~6,000 LOC | -48% |
| Source code (`src/trinity_local/`) | 44,700 LOC | ~42,000 LOC | -6% |
| CLI subcommands | 51 | ~38 | -25% |
| Runtime deps | 3 (Pillow, mcp, numpy) | 2 (mcp, numpy) | -33% |
| Top-level `.md` files (docs/) | 38 live+aspirational | ~22 | -42% |
| Test count | 2,117 | ~2,000 (after guard retirement) | -6% |

The product gets meaningfully smaller without losing the wedge.

## The honest summary

Trinity is in good shape — but it grew during exploration, and that
exploration left scaffolding behind. The biggest unforced error is
the **5,400 LOC of aspirational docs describing futures that already
happened or got retired**. A first-time reader walks into spec-v1.5,
spec-v1.6, scale-plan, and cross-platform-spec expecting roadmap, and
finds inline retirement notes weaved through prose that's hard to
parse.

The second-biggest is **`telemetry.py` pointing at `example.invalid`**
— that's an unfinished feature pretending to be finished. Cut it or
finish it; don't ship it half-built into a privacy-first product.

The third is **share-card sprawl** — a thousand lines of PNG-rendering
code defending a pitch that doesn't need PNGs. Cut to just
`eval-share --compare` (the benchmark publication artifact) and the
product gets simpler and the dep tree shorter.

Everything else is judgment-call: keep if the empirical evidence
shows use, cut otherwise. The right answer is gated on telemetry you
won't have until ~2 weeks post-launch. Apply Category A doc cuts
now; defer the rest.

Total cuttable surface area: **~30%**, all without touching the
load-bearing wedge.

---

## Status update (2026-05-27)

### Shipped

- **Category A doc moves (HIGH conf, commit `c99044f`)**: 11 docs moved
  to `docs/historical/` + 1 deleted. `docs/` public surface dropped
  from ~11.5k LOC → ~6.5k LOC (-43%).
- **`shortcuts_integration.py` cut (HIGH conf, commit `c99044f`)**:
  47 LOC inert shim deleted; 2 call sites in `council_review.py` and
  `launchpad_data.py` inline the constant.
- **Telemetry pivot to GA4 (commit `c99044f`, NOT a cut)**: per user
  direction, instead of cutting telemetry we wired it to Google
  Analytics 4 Measurement Protocol (the project GA4 property). Default ON
  per the user's pick; honors the existing `telemetry-disable` opt-out.
  Categorical-only — `task_type`, `winner`, `member_count`, `mode` —
  per CLAUDE.md "Architectural commitments" #2.
- **gstack reliability arc (commit `90a3f12`)**: 5 new structural
  guards from the garrytan/gstack audit:
  - Pattern 1: Executable retirement denylist driven by
    `retired_names.py` — adding a retirement entry instantly extends
    the guard. Caught + fixed a real drift in three-tier-architecture.md.
  - Pattern 2: CLI capability-coverage audit — every CLI subcommand
    must have a test file mention. 48/51 covered + 3 explicit
    exemptions.
  - Pattern 3: Two-tier test split via `@pytest.mark.slow` marker +
    conftest hook. `pytest -q` stays fast; slow shard runs with
    `TRINITY_SLOW=1` or `pytest -m slow`. Discipline guard catches
    "test hits real Chrome without the marker."

### Deferred (and why)

**Status 2026-05-27 (post overnight autonomy run):** items below
either landed or got further documented.

- **Phase 4 (share-card surface trim) — STILL DEFERRED**: `me_card.py`
  has launchpad UI integration (the "Render me-card" button in
  `launchpad_template.py` + extension dispatch action
  `render-me-card`). Cutting cleanly requires JS template surgery
  beyond a single-iteration scope. **Unblock path**: focused session
  that (a) drops the launchpad button, (b) removes `render-me-card`
  from the extension action allowlist, (c) deletes `me_card.py` +
  `commands/me_card.py` + `tests/test_me_card.py`. Keep `eval_card.py`
  (load-bearing for `eval-share --compare`, task #116 benchmark PNG).
  Estimate: ~2 hours, ~400 LOC removed + 1 dep candidate to remove
  (Pillow if nothing else uses it).
- **seed-from-taste-terminal — DEFERRED with refined unblock path**:
  the cut requires consolidating TWO copies of `_existing_prompt_node_ids`.
  `commands/seed.py:74` uses the old `iter_prompt_nodes(limit=None)`
  (loads embeddings ≈ 1.85s on a 1GB corpus); `incremental_ingest.py:87`
  uses the optimized `iter_prompt_nodes_no_embedding(limit=None)`. Naïve
  move-the-helpers refactor would either pick the wrong one or leave
  the duplicate. **Refined unblock path**: (a) create
  `src/trinity_local/ingest_helpers.py` exporting ONLY the optimized
  variant + `_flush_chunk` + `_stage_session`; (b) update both
  `commands/import_export.py` AND `incremental_ingest.py` to import
  from there; (c) delete the slow seed.py copy + the CLI handler;
  (d) verify lens-build / dream / import-export still pass.
  Estimate: ~90min including test runs.
- **`adapters` CLI verb — LANDED 2026-05-27** (commit `d5cdb8c`):
  the bare-cut item. Delete file + drop from CORE_COMMAND_MODULES +
  register 2 retirement records.
- **`decision-log` CLI — LANDED 2026-05-27** (commit `b641f55`):
  214 LOC deleted, loader survives so existing decision_log.jsonl
  files keep flowing into lens-build at weight=2.0.
- **`replay-history` CLI — LANDED 2026-05-27** (commit `f732b6f`):
  298 LOC deleted, launchpad cold-start CTA rewritten to point at
  natural council-launch population path instead of backfill.

### What the gstack patterns will catch going forward

The guards just shipped are forward-protecting. The next time a
contributor:
- Adds a CLI verb but forgets tests → `TestCliCapabilityCoverage`
  fires.
- Retires a module but leaves an import → `test_no_retired_modules_imported`
  fires.
- Renames a retired CLI but leaves a stale reference in active docs
  → `test_no_retired_cli_verbs_in_active_surfaces` fires.
- Adds a test that hits real Chrome without the marker →
  `test_slow_signals_carry_slow_marker_or_mock_context` fires.

Adding a retirement entry to `retired_names.py` automatically
strengthens guards 1 + 2 — no separate denylist constant to maintain.
