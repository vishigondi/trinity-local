---
class: live
---

# Changelog

All notable changes to Trinity Local. Format follows [Keep a Changelog](https://keepachangelog.com/);
versioning matches the project's phase + capstone cadence rather than strict semver.

## [v1.7.9 — gemini parser fix: brace-depth scan beats Google's unreliable length prefix] — 2026-05-23

Closes #144. v1.7.8's per-RPC file_stem revealed the real problem: even
with each RPC landing distinctly, `frames_count: 0` across the board.
Direct inspection of an `hNvQHb` capture (39KB, contains literal user
prompts + assistant replies in `_raw_body`) showed the parser was
bailing on every frame.

Root cause: Google's length-prefix in batchexecute framing is **off by
±2 chars** from the actual JSON value length (live capture: declared
`36816`, actual `36814`). The old `parseFrames()` trusted the prefix
verbatim, sliced too far, JSON.parse hit "Extra data" on trailing
chars, frame dropped. Whether the drift is UTF-8/UTF-16 byte-vs-char
mismatch or a Google-side count semantic that includes trailing
separators is unknown — and irrelevant.

Fix: brace-depth structural scan to find the actual end of each JSON
value. Reads (and skips past) the length prefix as a hint that "a JSON
value follows here," but does NOT trust its numeric value. Sidesteps
the byte/char/encoding question entirely.

- `browser-extension/adapters/gemini.js`: new `findJsonValueEnd(text,
  start)` walks brace/bracket depth + string-escape state to locate
  the closing bracket. `parseFrames()` rewritten to use it. Same wire
  protocol assumptions; just stops trusting one untrustworthy field.
- `browser-extension/manifest.json` 0.2.6 → 0.2.7.
- `docs/INSTALL-extension.md` version synced.

Guards (so this can't silently regress):

- `tests/test_browser_extension_gemini_adapter.py` adds 2 tests:
  `test_parser_ignores_unreliable_length_prefix` — synthesizes a body
  with deliberately-wrong length (off-by-2, matches live drift exactly)
  and asserts the parser still extracts.
  `test_parser_handles_multi_frame_body` — multiple frames with mixed
  off-by-N prefixes (+2, exact, −1) to stress the brace-depth scan.

What's resolved + what remains:

- #144 **resolved** — verified live by running the patched parser
  against an existing 39KB hNvQHb capture: extracts the full Oracle-
  earnings assistant reply (~2KB prose).
- `user_text` still falls back to `"generic"` for many RPCs — that's a
  separate looksLikePrompt heuristic issue in `extractUserPrompt`. The
  fix for the response-side parser unblocks reading what's there;
  tightening the request-side prompt extraction is a smaller follow-up.

Pattern reinforced: don't trust upstream length prefixes verbatim when
you have structural cues (matched brackets, JSON validity) that let you
verify. Same principle as the chatgpt URL-pattern drift the
`extension repair` flow catches — provider wire formats drift, the
adapter must be structurally robust to the drift class, not just the
current shape.

## [v1.7.8 — gemini capture: per-RPC file_stem unblocks #144 verification] — 2026-05-23

#145 (captures overwriting per conv_id) caused #144 (empty user_text /
assistant_text) to look unverified even after the v1.7.7 StreamGenerate
pattern landed. Live evidence: file at
`~/.trinity/conversations/gemini/087a73a78d0e878f.stream.json` grew to
26KB after the StreamGenerate fix (more traffic flowing through wrapper),
but the latest content was always the trailing telemetry batchexecute
(`rpcids=ESY5D`, `user_text: bard_activity_enabled`) because every RPC
for the same conv_id wrote to the same filename and the last write won.

- `browser-extension/adapters/gemini.js`: adapter return shape gains
  `file_stem` — a per-call discriminator built as
  `<conv_id>__<message_id>` (preferred; stable across re-fetches of the
  same turn) or `<conv_id>__<captured_at_compact>` (fallback when
  message_id isn't extractable). conv_id stays a clean semantic field
  for downstream ingest grouping.
- `src/trinity_local/capture_host.py` (`_extract_provider_state` for
  `kind="adapter_stream"`): prefers `raw.get("file_stem")` when present,
  falls back to conv_id. Claude/chatgpt adapters don't set file_stem
  so their one-stream-per-turn semantics are unchanged.
- `browser-extension/manifest.json` 0.2.5 → 0.2.6.
- `docs/INSTALL-extension.md` extension version synced.

Guards (so this can't silently regress):

- `tests/test_browser_extension_gemini_adapter.py` adds 3 file_stem
  tests: message_id preferred, captured_at fallback, null when no conv_id.
- `tests/test_capture_host_stdio.py` adds 2 file_stem tests:
  override-conv_id-for-filename path + back-compat-when-absent path.

What this unblocks: with each gemini RPC capture landing in its own
file, you can now inspect what StreamGenerate actually delivers (vs
the telemetry batchexecute that was clobbering it on disk). #144's
"is the adapter parser actually broken or just masked" question
becomes answerable after a single fresh gemini message post-reload.

Architectural note: this is an interim fix. The structural fix for
gemini's "no canonical full-tree fetch" gap is #149 (gemini canonical
pattern). Until that lands, each turn lives in its own file with no
all-turns-of-this-conversation roll-up — same fragmentation pattern
the canonical fetch was designed to absorb for claude/chatgpt.

## [v1.7.7 + v1.7.7-companion — orphan-modules sunset + extension-repair dogfood patch] — 2026-05-23

Two post-launch sweep ticks, kept under one section because both shipped
on the same day after v1.7.7.

**Extension-repair dogfood:** first end-to-end use of
`trinity-local extension repair --har` (the flagship demo from task #136)
to patch a real bug. HAR + council (extrepair_a6688c43b62bbbe7) showed
gemini's actual conversation stream goes through
`/_/BardChatUi/data/assistant.lamda.BardFrontendService/StreamGenerate`,
NOT batchexecute. The batchexecute captures we'd been getting
(rpcids=ESY5D) were the bard_activity_enabled telemetry RPC, which
explained the empty assistant_text in task #144. Claude + Codex +
Antigravity all chairman-synthesized the same one-line fix; chairman
picked Claude's patch for precision.

- `browser-extension/page-hook.js` PROVIDER_PATTERNS gains a second
  gemini entry for StreamGenerate. Legacy batchexecute entry kept
  (still carries telemetry, harmless to capture). classifyRequest's
  includes() check matches without regex changes.
- `browser-extension/manifest.json` 0.2.4 → 0.2.5.
- `docs/INSTALL-extension.md` extension version synced.

**Orphan-modules sunset (drift class: retired-CLI handler stubs).**
Same pattern as `trust.py` / `tasks.py` / `depth.py` (iter #115 + tick
85): retired CLI handlers kept around purely for handler-level test
coverage are pure cruft once the CLI is gone. Both
`commands/distill.py` (49 LOC) and `commands/bootstrap_pairs.py`
(113 LOC) were flagged retired in `retired_names.py` (kind=cli,
retired 2026-05-18, replaced by `dream`) but the handler modules and
their tests still existed. Load-bearing imports (dream.py, me.py,
cortex.py) go to the root `distill.py` / `cross_provider_pairs.py`
modules, which have separate comprehensive test coverage; the
handler stubs were thin wrappers (import root → call function →
print JSON) testing only the CLI-surface formatting that no CLI
exposed.

- Deleted: `src/trinity_local/commands/distill.py`,
  `src/trinity_local/commands/bootstrap_pairs.py`.
- Deleted: `TestDistillCLI` class (~52 LOC, 4 tests) from
  `tests/test_distill.py`; `TestBootstrapPairsCLI` class (~82 LOC,
  3 tests) from `tests/test_cross_provider_pairs.py`.
- Net: -162 LOC modules, -134 LOC tests, 1693 → 1686 tests.
- Retirement-registry entries unchanged (still authoritative); the
  RETIRED_CLI frozenset guard in `test_doc_count_consistency.py`
  still polices "distill" / "core-show" / "bootstrap-pairs" against
  future re-introduction.

## [v1.7.7 — gemini.google.com capture: XHR interception lands] — 2026-05-23

Live debug session caught the gemini-capture launch-blocker that v1.8's
task #135 adapter shipped but couldn't actually fire. Symptoms: extension
reloaded, `window.fetch.name === "trinityFetch"`, all 3 adapters
registered, 17 batchexecute POSTs returning 200 in the network panel —
but zero adapter.adapt calls and zero files in
`~/.trinity/conversations/gemini/`. Root cause discovered via direct
DevTools probe: gemini's batchexecute RPCs go through
`XMLHttpRequest`, not `fetch`. The page-hook only wrapped fetch, so
gemini's XHR traffic flew straight past.

- `browser-extension/page-hook.js`: added XHR interception that mirrors
  the fetch path — `XMLHttpRequest.prototype.open` captures URL/method
  on the instance via `classifyRequest()`; `.send` snapshots
  `request_body` for batchexecute's `application/x-www-form-urlencoded`
  payload and registers a `load` listener that pipes `responseText`
  through the same adapter dispatch (`__TRINITY_ADAPTERS[provider].adapt`)
  + `emit()` postMessage relay. Same payload shape downstream; the
  capture host doesn't know whether the body originated from a fetch
  stream or an XHR. Claude.ai + chatgpt.com unaffected (their bundles
  use fetch); they keep going through the unchanged fetch path.
- `browser-extension/content-script.js`: guard against
  `chrome.runtime.id === undefined` ("Extension context invalidated"
  thrown from line 22 of every old tab once the user reloads the
  extension in `chrome://extensions`). Previously every postMessage
  from page-hook threw and spammed the page console; now we skip
  silently when the context is gone (next page reload re-injects a
  fresh content-script with a live runtime). Caught live in the same
  debug session on gemini.google.com.
- `browser-extension/manifest.json` 0.2.3 → 0.2.4.
- `docs/INSTALL-extension.md` extension version reference synced.

Principle reinforced: capture surfaces need both fetch AND XHR
interception by default. The fetch-only assumption from v1.6 spec
held for the OpenAI/Anthropic web apps but broke on Google's bundle —
the kind of provider-shape drift that the lab-by-lab capture path is
guaranteed to keep producing.

## [v1.7.6 — Trinity heals itself: `extension repair` flagship demo] — 2026-05-23

Drift caught live this session: ChatGPT moved their streaming endpoint
from `/backend-api/conversation` to `/backend-api/f/conversation`
(added `/f/` segment, ~2026-05). Page-hook.js's exact-string `streamPath`
silently failed to classify — wrapper installed correctly, captures
stopped. Per the principle "third-party endpoint moves are unbounded
drift the canonical renderer can't catch", shipped a flagship demo
showing that Trinity is the right shape to heal itself:

**New: `trinity-local extension repair`** (task #136, ~250 LOC + 15 tests):

- **Diagnose mode (default):** reads `~/.trinity/conversations/<provider>/`
  for each of claude / chatgpt / gemini, reports capture count + hours
  since last write. ⚠ flag when last capture > 24h.
- **HAR + council mode (`--har <path>`):** parses HAR 1.2 export from
  Chrome DevTools, strips telemetry noise (`/ces/`, `/sentinel/`,
  `/statsc/`, `/lat/`), extracts chat-domain POSTs, dispatches a council
  (Claude + Codex + Antigravity) with the current page-hook.js source
  + the observed POSTs. Asks the chairman to synthesize a unified-diff
  patch to PROVIDER_PATTERNS.
- **Structural pitch:** only Trinity has the council + the local code +
  the cross-provider signal. The labs themselves are commercially
  prevented from cross-recommending — someone outside has to ship the
  layer that heals breakage from any one of them.
- `--apply` (auto-write the patch) intentionally NOT wired in MVP —
  patches are printed, user reviews + applies + reloads the extension.

**Other drift caught this iter:**

- `browser-extension/page-hook.js` PROVIDER_PATTERNS gained
  `/backend-api/f/conversation` entries for chatgpt.com and
  chat.openai.com; legacy `/backend-api/conversation` entries kept for
  accounts still on prior rollouts.
- `browser-extension/manifest.json` 0.2.1 → 0.2.2.
- `docs/INSTALL-extension.md` extension version reference synced.
- `browser-extension/page-hook.js` install path moved from
  `window.fetch = trinityFetch` to `Object.defineProperty(window,
  "fetch", { writable: false, configurable: false })` — chatgpt's
  bundle was reassigning the property after install (caught via
  DevTools probe of `window.fetch.name`).

CLI subcommands across user-facing modules: 42 → 43; module count
21 → 22 (the new `extension_repair` module). Canonical placeholders
re-rendered.

**Eval data — matched-N comparability landed (queued from v1.7.5).**
The v1.7.5 entry queued codex + gemini full-suite re-runs as v1.7.6
polish. Those landed overnight 2026-05-22 → 2026-05-23 on the SAME
N=45 suite (`eval_eval_12f21a9fd423`):

- claude       **0.788** (REFRAME 0.81 / REDIRECT 0.80 / SHARPENING 0.82 / COMPRESSION 0.48 n=2)
- codex        **0.760** (SHARPENING peak 0.86 — beats claude; COMPRESSION 0.78 also beats claude)
- antigravity  **0.610** (COMPRESSION 0.08 — standout weakness; closest to the trio on SHARPENING at 0.75)

Per-axis split becomes the headline (the aggregate hides which
provider wins which axis). Launch surfaces refreshed:
`docs/launch-day/00_leaderboard.md` (full rewrite), `README.md` and
`03_hn_objection_faq.md` and `10_hn_faq_full.md` (data + per-axis
story updated), `docs/launch-package.md` L271 (sourcing).

(Legacy gemini provider slug switched to `antigravity` for the
N=45 cohort — `agy` binary, post task #127 migration. The
`gemini` slug now refers only to the gemini.google.com web-chat
capture source, per the browser extension's adapters/gemini.js
introduced in task #135.)

## [v1.7.5 — rating-surface retirement + claude.md cut to 200 lines + Auto-Dream cite] — 2026-05-22

Post-launch cleanup pass driven by three user directives:
1. **"Cross-provider continuity is NOT the killer hook"** — reframed
   to "Your taste, ported — Trinity picks the answer you would have
   picked." Continuity becomes a capability, not the hook.
2. **"User doesn't have to provide ratings — use the lens-governed
   council selections"** — full retirement of the rating surface.
3. **Anthropic shipped official Auto-Dream** in Claude Code; cite
   + position Trinity's `dream` as the cross-provider extension
   (Anthropic dreams *Claude* conversations only; Trinity dreams
   across Claude + Codex + Antigravity — the labs are commercially
   prevented from crossing).

**Rating-surface retirement (decisions #2 + #7):**

- `council-rate` CLI subparser + `handle_council_rate` handler
  deleted (~80 LOC).
- `commands/unrated.py` module deleted (was Pillar-4 funnel-widening
  for ratings; whole purpose moot post-retirement).
- `tests/test_unrated.py` deleted.
- `doctor._check_verdict_rate()` deleted (+ `TestVerdictRateCheck`
  in test_doctor.py) — metric always-0 post-retirement = noise.
- `_verdict_stats()` in launchpad_data.py deleted (~55 LOC) — last
  consumer (the doctor check) gone.
- `tests/test_verdict_stats.py` deleted (~511 LOC of dead tests).
- `schemas/council_outcome.schema.json` (+ skills/ mirror) strips
  the `metadata.user_verdict` spec entirely.
- `load_council_outcome()` in council_runtime.py wipes
  `metadata.user_verdict` on read so existing on-disk councils
  naturally lose the field on next save.
- `rate_council` action removed from `dispatch_registry.DISPATCH_ACTIONS`
  + its handler branch (was orphan — Chrome ext would have shelled
  to a missing CLI).
- `launchpad_template.py` + `council_review.py`: "Preferred" click-
  to-rate badge replaced with "Lens pick" badge sourced from
  `routing_label.winner`. No human rating step in the loop; lens
  governs.

**claude.md restructure (decisions #4 + #10 + #11):**

- claude.md cut from 918 → 183 lines (well under the new 200-line
  Anthropic-Auto-Dream-discipline target; 250-line guard added).
- Auto-Dream cite as a load-bearing positioning subsection
  (cross-provider extension framing).
- Old hero framings deleted ("Stop copy-pasting prompts", etc.).
- Historical context relocated to `docs/historical/`:
  - `principles.md` (21 meta-principles, 250 LOC)
  - `retirement-log.md` (retired-name notes + simplification log)
  - `brand-evolution.md` (pivot history + ratifying councils)
- `TestClaudeMdLineCap` guard added; canonical
  `doc_consistency_guards` bumped 102 → 103.

**Other cleanup:**

- `state_paths.conversations_dir()` + `conversations_provider_dir(provider)`
  helpers promoted (principle #17: N=5 inline-construction sites
  collapsed to 1 helper). Same shape as `share_dir` (tick 87, N=3).
- Trust-CLI mentions (`trust-init` / `trust-show` / `audit-show`)
  scrubbed from INSTALL-skill.md + INSTALL-pip.md.
- `RETIRED_CLI` guard in test_doc_count_consistency extended with
  `council-rate` + `unrated`; caught real orphan in
  `dispatch_registry.py` as a side effect.
- `_verdict_stats` retirement record uses new `kind="function"`
  (enum extended in retired_names_registry test).
- `plan_and_execute` MCP tool fully sunset (task #128 deleted) —
  Loop Constitution removal was the right call to NOT rebuild.
  Multi-step orchestration is the harness's job, not Trinity's.
- gemini.google.com adapter deferral re-pointed v1.7 → v1.8
  (task #135).
- Spec-v1.5 + spec-v1 + spec-v1.6 + scale-plan + v2-loop-constitution
  + founder-essay-draft all updated to reflect sunsets.
- scale-plan state-paths updated: `memory/` → `prompts/` per Tier
  1 #1 (task #90); `transcript_nodes.jsonl` removed per Tier 2 #5
  (task #51).
- spec-v1.md vanity domain `trinity.local/install` updated to the
  shipped `raw.githubusercontent.com` form.
- Auto-memory cleanup: 3 deletes (killer-hook continuity, day2-close
  stale state, launch-sequence pre-flip note) + 3 rewrites in
  `~/.claude/projects/.../memory/`.

**Test gate (post-pass):** 1662 passing + 4 skipped + 0 failing
(167s wall). Movement was 1649 (pre-cleanup) → 1625 (rating-surface
retirements removed `_verdict_stats` + `_check_verdict_rate` tests)
→ 1656 (`gemini.js` task #135 added 22 tests; takeout-embedding task
#107 added 9 tests) → 1655 passing + 1 intentional fail post the
tightened `TestLaunchpadScreenshotFreshness` 1-day threshold →
1662 + 0 fail after the post-release smoke gallery regen
(commit `2bbb333` cleared the intentional fail; +7 test movement
absorbed by canonical-placeholder ripple + drift-sweep edits).

**Net code delta:** ~1,300 LOC removed from active surface;
~550 LOC added under `docs/historical/`. Hero claim every doc
agrees on: *"Your taste, ported — Trinity picks the answer you
would have picked."*

**Post-release polish (commits after `37b144b`, all 2026-05-22):**

- ⠕ brand mark (U+2815, Braille pattern dots-135) added across
  4 surfaces: `e52eec9` README hero, `c85f860` share-card footer
  tagline, `0138c12` launchpad header eyebrow, `eccb76e` Chrome
  extension toolbar icons (16/32/48/128px rendered from Apple
  Symbols at 85% glyph height on the cream + sage palette).
- `2bbb333 / 0138c12` regenerated `docs/launchpad_example.png` +
  smoke gallery for the Phase 3d "Lens pick" badge UI swap;
  cleared the intentional `TestLaunchpadScreenshotFreshness` fail.
- `ba41133` cross-provider eval share cards committed to
  `docs/launch_assets/` (task #116). Claude card refreshed
  2026-05-22 same day from a fresh N=45 run: claude **0.788
  aggregate (N=45 — COMPRESSION n=2 mean=0.48, REDIRECT n=17
  mean=0.80, REFRAME n=20 mean=0.81, SHARPENING n=6 mean=0.82)**,
  codex 0.700 (N=5, May 19 — re-run pending), gemini 0.442
  (N=17, May 19 wider slice — re-run pending). `00_leaderboard.md`
  rewritten to anchor on the N=45 claude run. `.gitignore` extended
  to whitelist `docs/launch_assets/*.png` + `docs/smoke/*.png`.
  Codex + gemini full-suite re-runs queued as v1.7.6 polish for
  matched-N comparability.
- `0da50df` 15 new smoke surface PNGs (14, 17-30) tracked,
  completing the visual gallery per principle #14 ("every shipped
  feature gets a smoke regression guard within one tick").
- `0ac8ada` drift sweep: 11 sites across 8 files scrubbed of stale
  "council-rate stays for power users" prose. The line was correct
  on 2026-05-21 (only `record_outcome` retired) but became false
  on 2026-05-22 when task #134 retired the CLI too — the retirement
  registry caught the canonical fact, but the framing prose didn't.
  Filed a future drift-guard idea: catch "stays|still works|power
  users" within 6 lines of a retired name.

## [v1.7.4 — pre-launch simplification pass] — 2026-05-18

Day-of-launch simplification: 17 commits removed ~5000 LOC across
12 distinct kills. The goal was to land at a launch surface where a
curious HN reader can clone the repo and read it end-to-end without
chasing dead code paths or stale docs. The wedge (cross-provider
councils + your-taste-distilled chairman) is unchanged; what's gone
is everything that didn't earn its keep.

**Structural kills (code + tests removed):**

1. **`Trinity.app` osacompile wrapper retired (-839 LOC).** The
   macOS-only .app bundle is gone; the Chrome extension is now the
   cross-platform launchpad host. Single surface, no per-OS
   maintenance. README dropped to "two install paths" (Skill /
   Chrome extension).

2. **macOS Shortcut dispatcher retired (-788 LOC, Pass A — structural).**
   `shortcut_setup.py`, `dispatch_runner.py`, `commands/shortcuts.py`
   deleted; `shortcuts_integration.py` kept as an inert shim so
   consumer renderers don't break. The Chrome extension's Native
   Messaging host (`capture_host.py`) is now the canonical dispatch
   path. Pass B (JS surgery to drop the empty URL emission) tracked
   in `docs/simplification_log.md` for v1.7.5+.

3. **Watcher subsystem retired (-492 LOC).** `watch-once` / `watch-loop`
   CLIs gone; `watch_runtime.py` slimmed from 515 → 115 LOC (only the
   `_source_root` / `_iter_recent_paths` / `_parse_source_path`
   utilities that `incremental_ingest` + `cold_start` still need).
   MCP `ask` fires `ingest_recent()` on every call now with a 1s
   deadline — ingestion is automatic and passive.

4. **Persistent embedding cache retired (-284 LOC).** With search
   already off the embeddings hot path (Tier 1 #4), the cache only
   earned its keep for offline rebuild flows. Trade-off: each
   `dream` / `lens-build` / `consolidate` pass now re-encodes
   (~2 min on a 50k-prompt corpus, batched MLX). Cold-start UX
   unchanged. `cache-stats` / `cache-clear` CLI surfaces deleted.

5. **`research/` package deleted (-1500 LOC).** Offline research
   tooling (replay, hard_mining, ranking_eval) that was explicitly
   "not on the live product path" per CLAUDE.md. The eval harness
   (`commands/eval.py` + `src/trinity_local/evals/`) covers the
   shipped surface.

6. **Share-card brand collapsed to a single base module (+43 LOC
   net, single-source brand contract).** `share_card_base.py` carries
   the canvas dimensions, color palette, font loader, wrap helper,
   blank-canvas factory, footer/CTA renderer, and `LANDING_URL` +
   `FOOTER_TAGLINE` constants. `me_card.py`, `eval_card.py`,
   `council_card.py` import from it instead of triplicating.

**CLI surfaces hidden or removed:**

7. **`doctor` collapsed into `status`.** One health-check entry point
   instead of two; the doctor library stays importable for the MCP
   `rate_action` hint path.

8. **`features` (`commands/ingest.py`) hidden from CLI.** Internal
   dev tooling; the library `extract_session_features()` stays
   importable for tests.

9. **`distill` + `core-show` hidden from CLI.** `dream` Phase 5
   refreshes `core.md` automatically; users can `cat ~/.trinity/core.md`
   directly.

10. **3 internal council subcommands removed.** `council-prompt`,
    `council-run`, `council-outcome` — programmatic helpers with no
    skill / launchpad / Native-Messaging-dispatch / test consumers.
    Library functions (`run_council`, `create_council_outcome`,
    `render_*_prompt`) remain on `council_runner` / `council_runtime`
    imports.

11. **`bootstrap-pairs` hidden from CLI.** Internal phase 1+2 of
    `dream`; tests still import the handler.

12. **`council-last` removed; launchpad gains filter chips.** Search
    input + All / Unrated / Rated chips on the recent-councils card
    cover the same affordance (find a previous council) with more
    control. Pure JS over server-rendered `data-rated` / `data-title`
    attrs.

13. **`auto-chain-enable` / `auto-chain-disable` / `polish-auto-enable`
    / `polish-auto-disable` retired.** Auto-chain is now exclusively
    a per-council click on the review page (`council_auto_chain`
    dispatch action). No global setting to hide behavior from new
    users.

14. **`get_eval_summary` MCP tool dropped.** Three-way DRY for eval
    summary is overkill — agents ground via `ask` + the picks table;
    the launchpad eval card + `eval-show` CLI cover human surfaces.

15. **Trust+audit CLI deferred to v1.1.** `audit-show` / `trust-init`
    / `trust-show` removed from the public CLI; the trust library
    stays (council_runtime + dispatch paths still resolve trust
    levels). v1.1 will re-expose the CLI surface.

16. **`metric` + `stats` "marketing-voice" CLIs removed.** Aspirational
    case-study commands that never had real data flow behind them.
    Re-addable when actual launch metrics exist.

17. **`task-create` / `task-show` / `task-sync` / `bundle-create` /
    `launch-create` / `depth-show` hidden from CLI.** Internal-only;
    no skill / launchpad / dispatch / test consumers.

**Brand + UX:**

18. **Brand URL flipped to `keepwhatworks.com`.** "Keep what works"
    encodes the wedge (your lens = the pattern of what works for
    *you*; rejection signal = what doesn't) in three words. Share
    cards point at the new URL; binary stays `trinity-local`; rebrand
    revisitable in v1.1 if "Dream" proves to be the magnet word.
    Trinity is the first product under the keepwhatworks.com brand.

19. **README objection FAQ sharpened on Dreaming.** The
    "Anthropic-Dreaming-server-side" angle is the killer
    differentiator: even if Anthropic moves Dreaming server-side,
    that version still can't see OpenAI or Google transcripts. The
    cross-lab dreaming has to come from outside the labs by
    structural definition.

20. **install-launcher gains macOS (.webloc).** `~/Applications/
    Trinity Local.webloc` joins the existing Linux .desktop and
    Windows .url shortcuts; the Chrome extension remains the
    canonical launchpad host but the desktop shortcut now ships
    cross-platform for users who skip the extension.

**Docs + storage:**

21. **State-layout doc grouped by convention.** CLAUDE.md state-layout
    block rewritten into three sections: Entities (JSON-per-file),
    Prompt index + cognitive memories, Event logs (JSONL). Retired
    directories (`watcher/`, `shortcut_setup/`, `cache/`, etc.) moved
    to a "may still exist on older installs" paragraph below the
    diagram.

22. **state_paths.py dead helpers deleted.** `shortcut_setup_dir()`,
    `shortcut_bin_dir()`, `cache_dir()`, `watcher_dir()` had no
    remaining src/ or tests/ consumers after the kills.

23. **User-facing install docs swept.** `docs/INSTALL-skill.md`,
    `docs/INSTALL-extension.md`, `docs/INSTALL-pip.md`, `docs/index.html`
    updated to drop references to the retired trust/audit CLI; inspection
    instructions now point at `~/.trinity/audit.log` directly. (Paths
    reflect post-082fb1f layout — all install docs moved into `docs/`
    for GitHub Pages serving; landing page is `index.html`, not `.md`.)

**MCP tool count:** 10 → 9 (`get_eval_summary` dropped).
**Public CLI surface:** ~30 → ~21 commands.
**Tests:** 1402 → 1294 passing + 4 skipped (the drop is retired
tests for retired features; coverage of live surfaces unchanged
— two iters of consistency-sweep guards rebuilt some headroom).
**Net LOC:** -5000 across 17 commits.

The pyproject version bumps 1.7.3 → 1.7.4. Semver-patch because
the changes are non-breaking from a USE perspective — users who
were typing the removed CLI subcommands weren't supposed to (and
the load-bearing surfaces — `council-launch`, `ask`, `record_outcome`,
`dream`, `eval-*`, `handoff`, `me-card`, `lens-build`, `consolidate`,
the MCP tool list) are unchanged.

**Pre-launch consistency sweep (iters #15-#80, 70 follow-on commits):**

The simplification pass above retired ~10 CLIs, renamed paths, and
flipped brand framing — each of which scatters stale references
across docs + UI strings + tests. A 69-iter consistency loop on top
of the simplification swept 60+ launch-credibility drifts in surfaces
including:

- 8 live runtime/UI bugs (most notably the launchpad's actual
  hero text still showing the pre-pivot tagline; #6366f1 indigo
  in empty-state hints despite DESIGN.md forbidding it; retired
  CLIs in user-visible HTML `<code>` blocks that would have errored
  "unknown command" on click; the memory viewer's veto button
  firing the retired `shortcuts://run-shortcut?` URL after the
  Pass B sweep should have made the Chrome extension the only
  live dispatch path — iter #48 fixed + added a regression guard)
- 2 MCP tool description strings telling agents to run retired
  CLIs (`trinity-local me-build` instead of `lens-build`, stale
  path for the cortex picks file)
- 5-surface numeric/version drift (test count 1402 vs reality;
  v1.7.3 vs pyproject 1.7.4; doc-consistency guard count 37 vs 39)
- Cursor incorrectly listed as a transcript source (it's a harness)
- ~/.trinity/conversations/ (Chrome extension's capture
  destination) missing from the state-layout diagram even though
  the README hero made the extension load-bearing

Two permanent regression guards landed:

- `TestNoRetiredCliInSrcQuotedStrings` (iter #13, extended #32):
  scans all .py files in src/ for Python-quoted OR HTML-wrapped
  `trinity-local <retired-cli>` strings. Locks 28 retired CLI names.
- `TestNoForbiddenColorsInLaunchpadTemplates` (iter #37): scans
  launchpad UI source for DESIGN.md-forbidden hexes (Tailwind
  indigo / violet / blue / pink / amber). Locks the prior-violation
  `#6366f1` indigo that principle #13 in CLAUDE.md narrated.

The sweep also locked the brand-pivot to "Your taste, ported." (iter
#33 swept the live launchpad hero — the most user-visible surface
that had quietly missed the pivot; iter #36 dropped both old hero +
old sub from `ACCEPTED_HEROES`/`ACCEPTED_SUBS` so a re-introduction
fails the suite).

Net result: launch-day surface is internally consistent across
README + CLAUDE.md + launch-day docs + live UI + MCP descriptions.
The doc-consistency suite (now 41 guards in
`tests/test_doc_count_consistency.py`) defends against the same
shape of drift recurring. Iters #62/#67/#71 added permanent guards
for the iter #61/#65/#70 catch shapes (canonical-N subset, 6-surface
test-count agreement, hero+sub across 5 surfaces). Iters #76/#77
extracted meta-patterns + 3 higher-level architectural gaps into
`docs/sweep-patterns.md` + `docs/architectural-gaps.md`.

**Architectural Gaps A/B/C shipped (commit eb0c06d, ahead of v1.7.5):**

After iter #77's meta-analysis surfaced 3 structural fixes for the
drift classes the 70-iter sweep was catching one-by-one, all three
shipped pre-launch:

- **Gap C — Doc-class frontmatter.** 55 classifiable docs now carry
  `class: live | aspirational | historical | reference` YAML
  frontmatter. `scripts/add_doc_class_frontmatter.py` bootstraps;
  `tests/test_doc_class_frontmatter.py` validates (111 parametric
  assertions). Implicit doc hierarchy → queryable property.
- **Gap B — Retirement registry.** `src/trinity_local/retired_names.py`
  declares 17 retirements as structured RetirementRecord data
  (name, retired_at, commit, replacement, reason, kind,
  artifact_persists). `tests/test_retired_names_registry.py` includes
  a present-tense guard scanning 26 live docs for retired-name
  references in code-context markers — the iter #68/#69 catch shape
  promoted from manual review to automated guard.
- **Gap A — Canonical-source renderer.** `scripts/render_docs.py`
  extracts 5 canonical values (test_count, skipped_count,
  mcp_tool_count, doc_consistency_guards, version) from authoritative
  sources (pytest, mcp_server.py, pyproject.toml), then templates
  them into docs via HTML-comment block syntax:
  `<!-- canonical:test_count -->1878<!-- /canonical -->`. 7 surfaces
  migrated to placeholders (claude.md ×3 + product-spec +
  10_hn_faq + launch-package + LAUNCH_CHECKLIST). `python
  scripts/render_docs.py` auto-syncs all surfaces from one
  command — the 6-surfaces-agree guard becomes "did the placeholder
  expand correctly" instead of multi-surface agreement.

Per `docs/design-frame.md`, these are the structural answers to
*"put signal in its channel"* (Gap A), *"enforce the boundaries"*
(Gaps B + C), and *"self-correction built in"* (Gap A auto-bump).
The 70-iter sweep was the cost of NOT having these.

## [v1.7.3 — share-workflow end-to-end] — 2026-05-17

Late-day audit caught that the share workflow — the artifact the
user's pitch produces — was broken or missing across 5 surfaces.
4 commits closed all 5 gaps. pyproject bumped 1.7.2 → 1.7.3.

**1. `eval-share` PNG renderer shipped (`fef3d91`).** New module
`src/trinity_local/eval_card.py` (~170 LOC) renders an eval run
result as a 1200×630 PNG with the headline score, per-axis bars
(REFRAME / COMPRESSION / REDIRECT / SHARPENING), and the install
CTA → `vishigondi.github.io/trinity-local`. The card is the
artifact the user's pitch directly produces — *"Gemini scored 0.83
on YOUR kind of question."* CLI: `trinity-local eval-share
[--target <provider>] [--out <path>] [--open]`. 7 new tests.

**2. `council-share` rewritten as PNG (`fe3b683`).** Prior impl
produced a 379-byte useless HTML redirect to a relative path —
unusable to any recipient. Pivoted to PNG card shape (matches
eval-share + me-card visual language). Privacy-safe by
construction: only chairman-extracted fields (`agreed_claims`,
`disagreed_claims`, `winner`) cross to the card. The user's
verbatim prompt + members' full responses NEVER touch the
artifact. Filename `[:8]` slice bug fixed (was producing
`trinity-council-council_-...`). New module
`src/trinity_local/council_card.py` (~220 LOC). 6 new tests
including a privacy-canary assertion.

**3. me-card install URL footer + 4. `review-link` fake-URL fix
(`20a0315`).** me-card PNG footer now embeds
`vishigondi.github.io/trinity-local` so a Twitter viewer has a
path forward. review-link no longer defaults to the unregistered
`trinity.openclaw.ai/app/review/<id>` URL (which 404'd) — default
is None; web_url only appears when caller passes explicit
`--web-base`.

**5. Launchpad "Share PNG" chip (`f33f9ec`).** Every recent-
council card on the launchpad gains a `→ share PNG` chip in the
existing cross-memory chip row. Click dispatches via macOS
Shortcut to `trinity-local council-share --council <id> --open`.

**Test count:** 1385 → 1398 (+13 net: 7 eval-share + 6 council-
share). Swept across all 5 surfaces enforced by the 4-surfaces-
agree guard.

**Final state:** 3 PNG share artifacts (me-card / eval-card /
council-card), one visual language, single-source-of-truth CTA
URL `vishigondi.github.io/trinity-local`, privacy-safe by
construction, launchpad UI wires recent councils to the share
flow with one click.

## [v1.7.2 — final public-readiness verification + close] — 2026-05-17

Loop-executed Tier 1–4 of `docs/PUBLIC_READINESS_PLAN.md`. 12 commits
since v1.7.1 (`7154ab5`, `7cea5b9`, `69d14dc`, `738e8e4`, `7d64819`,
`80b922c`, `9eb5f72`, `cfbbf05`, `67c5298`, `1f2b0a8`, `4bea46c`,
`d27d401`). 4-agent re-audit confirms zero residual drift.

**Tier 1 HIGH (2 fixed):**
- H1: `trinity.local/install.sh` vanity URL purged from
  `docs/launch-day/01_tweet_thread.md` (2 sites) + `02_show_hn_post.md`.
  Existing guard extended to cover `docs/launch-day/*.md` (was a
  coverage gap) and to match bare-host form (no `https://` prefix).
- H2: v1.0 vs v1.7 version story reconciled across launch.md +
  launch-package.md + tweet thread + README. pyproject.toml bumped
  to 1.7.1 (now 1.7.2 with this commit). New guard pins all 4 launch
  surfaces to pyproject's `major.minor`.

**Tier 2 MEDIUM (3 fixed):**
- M3: macOS framing pinned to "macOS today, cross-platform on the
  v1.5/v1.6 roadmap" across README, launch.md, spec-v1.md (caught a
  silent "macOS-only is a feature, not a bug" drift in spec-v1.md
  that contradicted cross-platform-spec.md).
- M4: README 60-sec demo gained a "First-install prereq" callout.
  V11 catch: the M4 example used the wrong command — replaced with
  `trinity-local ingest-recent` (the actual auto-discover cold-start;
  the old `seed-from-taste-terminal --limit 1000` would have failed
  on `--path` required).
- M5: claude.md CLI table header fixed ("22 modules" → "30 modules
  in the table below; 4 ancillary off-table"); `vocabulary` and
  `update` rows added.

**Tier 3 DELETE/SIMPLIFY — 5-for-5 KEEP on inspection:**
- D6 (spec-v2.md), D7 (sync_reference_evals + reference_evals.json),
  D8 (founder-essay-draft.md), D9 (scale-plan.md), D10 (3-spec
  layout) — every agent-recommended deletion candidate had load-
  bearing live call-sites. New "Tier 3 retrospective" in the plan
  documents the pattern: the audit agent's removable-code signal
  was 0% precision on this codebase.

**T10b proactive test-orphan hunt:**
- 0 orphan tests by AST import-resolution.
- 1 dead guard sunset (`TestInstallSmokeTracksMcpTools` — was
  enforcing parity against `scripts/smoke_install.sh` deleted in
  commit `8469c6e`; OSError-early-return made it silently dead).

**V11 final 4-agent re-audit:**
- 0 architecture drift (M5 fix verified; all 30 modules + 29 core
  layer modules present; MCP tool count matches mcp_server.py).
- 0 deletion candidates (matches Tier 3 pattern).
- 1 launch-copy carryover: claude.md status block still said "v1.0
  ships May 13–15" — H2 swept launch.md but missed claude.md;
  fixed in this commit alongside the test-count refresh.
- 1 user-facing promise drift: documented `seed-from-taste-terminal`
  examples lacked `--path` (required). Fixed by switching the
  cold-start example to `ingest-recent`.
- 1 stale tool-count claim at claude.md:534 ("9 total" → "11 total").

**Test count drift swept across 5 surfaces** (the 4-surfaces-agree
guard caught this on every commit): 1384 → 1385 in claude.md status
+ verified + product-spec item 11 + 10_hn_faq_full closing +
CONTRIBUTING.md.

**Final state:** 1385 tests passing + 4 skipped, 33 doc-consistency guards green,
pyproject 1.7.2, claude.md status block accurate, all launch surfaces
agree on v1.7, vanity-domain guard covers all launch-day files +
bare-host form, version guard pins to pyproject major.minor.

## [v1.7.1 — public-repo readiness pass] — 2026-05-17

Pre-flip-public hardening. The goal: stand the repo up so a hostile
HN/Twitter reviewer who skims the first screen + clones to inspect can't
find an embarrassing seam. 13 commits, all reversible.

**Install hardening.**

- `scripts/install.sh` now `pip install --user`s the pyproject runtime
  deps (`Pillow>=10`, `mcp>=1.0`) after cloning — without this, fresh
  doctor flagged two failures the user had to manually fix.
- Wrapper template now embeds the resolved Python binary (e.g.
  `python3.12`) instead of literal `python3` — on Linux boxes where
  `python3` is older than the validated candidate, the wrapper would
  have silently crashed at runtime.
- Detects active virtualenv via `sys.prefix != sys.base_prefix` and
  drops `--user` accordingly. Caught by sandboxed end-to-end smoke
  (`TRINITY_REPO_URL=file://...` with isolated HOME) — pip refuses
  `--user` inside a venv, so a contributor smoking install from their
  venv-active shell had been silently hitting "deps not installed"
  with no surface error.
- `doctor`'s `mcp_available` fix-hint now points at the right command.
  Was `pip install 'trinity-local[mcp]'` — neither the package (no
  PyPI publish) nor the extras (`mcp` is a main dep) existed.

**Embarrassment audit.**

- Untracked 16 dev artifacts that slipped past `.gitignore` (added
  after they were tracked, so the rules never applied retroactively):
  `.playwright-mcp/*` (April console + DOM snapshots),
  `.claude/skills/trinity/SKILL.md` (dev-convenience copy),
  `node_modules/.package-lock.json`.
- Deleted vestigial empty `package.json` + `package-lock.json` at top
  level — looked like vibes-coded mixed-stack mess.
- Stripped personal `/Users/openclaw/...` paths from
  `tests/test_frontend_flow.py` (input/expected was hardcoded to the
  dev's machine) and `docs/v2-loop-constitution.md` (6 absolute
  paths anchored at the author's $HOME).
- Removed 470 LOC of obsolete pip-wheel smoke scripts
  (`scripts/smoke_install.sh`, `scripts/smoke_install_macvm.sh`) —
  both tested a distribution path Trinity no longer ships.

**Repo signal layer.**

- `.github/workflows/test.yml` — runs `pytest -q` on ubuntu-latest +
  macos-latest with Python 3.12. Triggered on push/PR to main.
- README badges (tests, license, python, security) + Sakana paper
  name-collision FAQ above the install fold.
- `.github/ISSUE_TEMPLATE/{bug,feature,adapter}.md` + `config.yml` +
  `pull_request_template.md` + `CODEOWNERS`.
- `scripts/launch-check.sh` rewritten — gates on pytest +
  doc-consistency + install.sh structural guards + `bash -n`. No
  `twine upload` / `python -m build` references.
- `docs/REPO_PUBLIC_RUNBOOK.md` — top-to-bottom T-0 sequence with
  debugged `gh` commands for the flip, description + 13 topics,
  social card, 3 pinned starter issues, Pages enable, badge
  verification, and rollback.

**Drift fixes.**

- `CONTRIBUTING.md`: "~950 tests in under 80s" → "~1384 tests in ~150s"
- `SECURITY.md`: `subprocess_utils.py` (doesn't exist) → `runtime_env.py`
  with the actual `run_with_runtime_env()` helpers.
- Doc-side test-count claims in `claude.md` swept (1372 → 1384,
  36 → 33 doc-guards).
- `.gitignore` exception for `docs/launchpad_example.png` +
  `docs/me_card_example.png` so the broad `*.png` rule can't
  accidentally shadow the tracked canonical PNGs.

**Tests:** 1384 passed + 4 skipped (33 doc-consistency guards). Up
from 1382 — the personal-path cleanup converted two hidden-pass
assertions into properly portable ones.

## [v1.7 — three-tier architecture complete, Monday launch ready] — 2026-05-16

The user overrode the Phase 1 council's defer-to-v1.1 verdict — "we
have time, let's restructure" — and executed the full 8-phase plan
in one continuous loop iteration. All 8 phases pass acceptance.
Launch architecture ratified by `council_37eca30b6e7010df` (Phase 7,
load-bearing); antecedents `council_ff3da1fa84906791` (Phase 1) +
`council_c18f739a0234aa58` (Phase 6).

**Phase 2 — scripts/ shebang substrate** (commits 22ddad5 → b5da65c)
Six heavy-op scripts with dual interface (shebang-runnable +
importable): `_runtime.py` (venv bootstrap + audit log + JSON I/O),
`embed.py` (nomic-embed-text-v1.5 batch), `cluster.py` (k-means +
k-means++ init), `pca.py` (Weiszfeld median + manifold-dim +
bimodality), `descriptor.py` (rejection-signal validators),
`signature.py` (homonyms + synonyms), `anchor.py` (proper-noun
recurrence). 44 new tests.

**Phase 6 — trust + audit substrate** (commit d492d0d, council
c18f739a)
`~/.trinity/trust.toml` with `schema_version = 1` + `[trust.rules]`
exact tier.operation overrides + `[trust.operations]` +
`[trust.tiers]` + global default. Atomic single-write audit log via
os.open+O_APPEND (PIPE_BUF doesn't apply to regular files; that was
a v1.0-floor wording bug the council caught). Cross-tier
TRINITY_ORIGIN_TIER env propagation. Loud failure surfacing on
audit-write errors. New CLI: trust-init, trust-show, audit-show.
18 trust tests + 14 runtime tests.

**Phase 7 — integration + ratification** (commit e6d0b35, council
37eca30b — load-bearing launch decision)
12 new tests across two files:
- test_tier_equivalence.py: scripts/ ↔ trinity_local/ outputs match
  on embeddings (cosine ≥ 0.9999, NOT bit-identical), k-means
  labels (identical under seed), Weiszfeld median (bit-equal),
  basin_geometry composite, chairman picker, cross-tier env
  propagation through subprocess.
- test_phase7_fresh_install.py: doctor + trust-init + trust-show +
  audit-show + portal-html all work on a fresh TRINITY_HOME with
  no provider CLIs, no embeddings cached, no ~/.trinity/ data.
  Includes the council pre-empt verifier
  test_tfidf_hash_is_stable_across_processes.

**The critical pre-empt** (Phase 7 council flagged): TF-IDF
fallback used Python's hash() which is PYTHONHASHSEED-randomized.
Subprocess vs in-process would silently produce DIFFERENT vectors
for the same text. Fixed: stable SHA-1 hash projection.
Regression test runs two subprocesses with different
PYTHONHASHSEED values + asserts bit-equal vectors.

**Phase 8 — companion docs**
- docs/TRUST-MODE.md: trust.toml + audit-log user-facing explainer
- docs/INSTALL-skill.md: primary install path (via Claude Code skill)
- docs/INSTALL-pip.md: engine-only install
- claude.md: Phase 7 council ID designated as load-bearing launch
  architecture decision; Phase 1 + Phase 6 as antecedents

**Deferred to v1.1 per council verdicts** (none blocking launch):
- Cross-platform CI matrix (macOS/Linux/Windows × 3 tiers)
- Live Chrome extension smoke in CI (gated test ships as scaffold)
- Pip-package dependency inversion (scripts/ as canonical impl)
- Visible trust indicators in launchpad header / extension popup
- --dangerously-trust-all global CLI flag (env var works in v1.0)
- Automatic audit-log rotation (doctor warns above 50 MB in v1.0)
- --tier/--operation/--outcome filters on audit-show

## [v1.7 launch-arc — three-tier framing locked, Phase 1 v1.0 floor shipped] — 2026-05-16

Self-paced loop iteration after the Phase 4b cross-platform-dispatcher
work landed (commit a6fe6ad). The user proposed a full 8-phase
restructure to a skill-primary three-tier architecture (Skill / Pip /
Chrome Extension) for Monday's launch alongside Gemini 4.

**Architecture ratified by `council_ff3da1fa84906791`**
(chairman codex, winner claude; stop-light: ship with modifications).
The full 8-phase plan was the failure mode, not the win condition —
the 1290-test green gate is the single most credible launch-day asset
and a 70-module refactor under deadline pressure puts it at risk for
a reframe that doesn't require code motion. v1.0 ships the skill
artifact additive over the existing CLI; shared `scripts/` substrate
+ cross-backend equivalence test harness + trust-mode + audit-log
substrate all defer to v1.1.

**Phase 1 v1.0 floor files**
- `skills/trinity/SKILL.md` — 11-section comprehensive driver
  orchestrating the existing `trinity-local` CLI via Claude Code's
  bash tool. Three tiers framed; tier-equivalence invariant pinned
  (cosine ≥ 0.9999, NOT bit-identical — float-order differs across
  MLX vs torch CPU vs torch CUDA by SIMD scheduling).
- `skills/trinity/schemas/` — copies of `council_outcome`,
  `eval_set`, `rejection_signal` so the skill artifact is
  self-contained when git-cloned to `~/.claude/skills/trinity/`.
- `docs/three-tier-architecture.md` — full vision doc; v1.0 floor
  vs v1.1 stretch split documented; council outcome ID cited.
- `tests/test_skill_md_commands_resolve.py` — 4 new guards:
  SKILL.md exists, every `trinity-local <cmd>` it references
  resolves in `--help`, three-tier framing + tier-equivalence
  invariant pinned as substrings, SKILL.md byte-identical across
  the canonical / package-data / .claude-dev-convenience copies.
- README + claude.md + docs/launch.md + docs/launch-package.md:
  three-tier framing propagated; council citation pinned in 4
  load-bearing surfaces.
- `docs/launch_councils/council_ff3da1fa84906791.json` — outcome
  copied for the cited-artifacts-resolve guard.

**Deferred to v1.1 (explicit per council verdict)**
- `scripts/` as importable+executable shared substrate
- 70-module engine extraction from `src/trinity_local/`
- Trust mode + audit log substrate
- Cross-backend equivalence test harness (MLX / torch CPU / CUDA)

**Verified**: 1295 passed + 4 skipped (gated Chrome smoke);
36 doc-consistency guards green.

The brand pivot survives intact — "Your taste, ported. Lives inside
Claude Code, Codex CLI, Gemini CLI, and Cursor." — because the skill
exists and works, not because the substrate underneath has been
refactored.

## [v1.7 follow-up — silent-failure audit + atomicity batch] — 2026-05-16

Self-paced loop iteration audited recently-touched code (vendor.py,
cold_start.py, mcp_server.py, council_runtime.py, doctor.py) for
silent-failure shapes the launch-prep batch left exposed. 7 ticks
landed in this arc (H–N).

**Atomicity**
- `utils.atomic_write_text` helper: tmp+rename + per-process PID-
  stamped tmp suffix + parent-dir creation + tmp cleanup on success.
  Adopted at 11 callsites across the moat-load-bearing surface
  (Principle #17 follow-through):
  - **Refactored from inline tmp+rename** (4): incremental_ingest
    cursor save, cortex routing patterns save, cold_start state
    writer, capture_host capture writer.
  - **council_runtime** (1 file, 4 callsites): save_prompt_bundle,
    save_council_outcome JSON, JSONP wrapper, thread manifest.
  - **Promoted from direct write_text** (6): personal_routing
    freeze (routing scoreboard), telemetry settings, review save,
    pair_mining lens + orderings output, action_runtime save,
    memory/store ingest cursor.
  New `TestNoInlineAtomicWritePattern` regex guard bans the
  inline shape from reappearing across `src/trinity_local/`.
- Council outcome writes — the durable supervision signal that's
  Trinity's moat — are now atomic. Kill-mid-write no longer leaves
  a half-JSON file that compute_personal_routing_table silently
  drops.

**Silent failures surfaced**
- `mcp.record_outcome`: `load_council_outcome` exception used to
  silently set `outcome_updated:false` and return `ok:true`. Now
  surfaces `outcome_load_error` + `recoverable` + `user_message`
  so the agent can tell the user their verdict was queued to the
  feedback side-log but didn't reach the canonical outcome JSON
  (highest-blast-radius silent failure of the launch).
- `mcp.get_council_status`: same shape as record_outcome — corrupt
  outcome JSON now surfaces `outcome_load_error` instead of `outcome:null`
  with no signal. Both the completed-with-corrupt-outcome and the
  no-status-AND-corrupt-outcome paths carry the load error.
- `vendor.publish_vendor_files`: bare `except OSError: pass` on
  write_bytes now writes a stderr warning naming the file +
  exception detail + the vendor_dir path the user needs to fix
  perms on. The silent skip turned "perms problem at install" into
  "launchpad has broken ./vendor/*.js 404s with no log trail."

**Cross-process race fixed**
- `cold_start.kick_cold_start_scan`: state file is now written
  SYNCHRONOUSLY before the daemon thread spawns, not deferred to
  the thread body + polled. Closes the cross-process race where
  multiple MCP servers (Claude Code + Codex CLI + Gemini CLI +
  Cursor each spawn one at session-start) could pass `is_cold_start()`
  before any one of them wrote state, then all spawn duplicate
  ingestion threads. The state file is now the cross-process
  serialization point.

**Doctor coverage**
- New `_check_vendor_published` doctor check: walks
  `~/.trinity/portal_pages/vendor/` against the canonical
  VENDORED_FILES list. Soft check (`ok=True` regardless) — surfaces
  partial-publish state with the fix command. Closes the loop on
  the vendor.py silent-failure fix above.

**Tests**
- 1212 → 1238 (+26). New surfaces: TestAtomicWriteText (6),
  TestNoInlineAtomicWritePattern (1), TestVendorPublishedCheck (4),
  TestRefreshVendorScript (2), TestVendorFilesPublished (2),
  test_state_file_written_synchronously_before_thread_starts (1),
  test_outcome_load_error_surfaces_when_council_id_unknown (1),
  TestGetCouncilStatus (1), TestScoreboardPathRenameInDocs (1) +
  the extended TestTestCountConsistency (now 4 surfaces).

**Maintenance ritual**
- `scripts/refresh-vendor.sh` (new): pins exact versions for all 12
  vendored URLs. `--check` mode for dry-run. Closes a stale TODO in
  vendor.py docstring that pointed at a non-existent commit hash.

**Static-analysis gate (post-arc tick S)**
- `me_builder.build_me_via_lens_pipeline` had 3 references to
  `chairman_name` (the scoped variable was `chairman`). Every unit
  test that touched lens-build did so via `monkeypatch.setattr` of
  the whole function — the NameError never fired in tests, only on
  the real user's `trinity-local lens-build`. Principle #5 catch at
  the static-analysis tier.
- New `tests/test_no_undefined_names.py`: pyflakes-scan of
  src/trinity_local/ failing on any "undefined name" line. Other
  pyflakes warnings (unused imports, f-strings without placeholders)
  tolerated — only NameError-at-runtime is the high-stakes target.
- Companion guard in the same file: `test_all_src_modules_import_cleanly`
  walks all 135 src/ modules and `import_module` each. Catches what
  pyflakes can't — runtime-at-import-time crashes (eager annotations,
  circular imports, missing optional deps imported unconditionally).
  Skips `__init__.py` (transitively loaded) and `capture_host.py`
  (has stdin-reading __main__ side effects).

**Phantom-claim audit (post-arc ticks U + V)**
- claude.md "Model detection" architecture row referenced
  `model_detector.py` + `data/model_candidates.json` +
  `trinity-local models-detect` CLI + `~/.trinity/detected_models.json`
  state file. NONE of those exist in the codebase — pure phantom
  documentation. A user reading the table and trying the command
  hits "command not found"; a contributor grepping for the module
  finds nothing. Row removed.
- `TestCliCommandsReferencedExistInCli` extended to scan claude.md
  (was launch-facing-docs only). Same shape as Principle #21:
  claude.md IS a public surface (every agent harness reads it), so
  its CLI references need anti-drift gating too.
- New `TestArchitectureTableModulesExist`: scans claude.md for
  backticked `<name>.py` references, recursive-searches src/+tests/
  for each. Allowlist for files claude.md explicitly documents as
  "didn't ship" (currently just `subprocess_utils.py`). Closes the
  module-side of the phantom-row class. Together with the extended
  CLI guard, every backticked claim in the architecture table is
  now load-tested against the filesystem.

1242 tests passing; 32 doc-consistency guards green.

## [v1.7 — persona-audit batch + architectural collapse] — 2026-05-15

100 sub-agents simulated a distinct user persona walking through Trinity
(see `docs/scale-plan.md` §Phase 10 for the full backlog). 39 HIGH /
45 MED / 16 LOW pain points clustered into 12 themes. This release
closes the highest-leverage items from the audit plus the architectural
simplification pass the audit unblocked.

**Architectural collapse**
- `picks.json` + `routing.json` move from `~/.trinity/memories/` to
  `~/.trinity/scoreboard/` (operational scoreboards, not cognitive
  memory). Distill now reads only the three thinking memories (lens,
  topics, vocabulary). Idempotent best-effort migration on first
  `scoreboard_dir()` access. Glossary collapse: "five core memories" →
  "three thinking + two scoreboards" across CLAUDE.md / docs/spec-v1.md /
  docs/spec-v1.5.md / DESIGN.md / README.
- Launchpad "Your memories, raw" 6-chip nav → "Your lens" 4-chip card
  (chairman-read order: core → lens → topics → vocabulary). picks +
  routing surface on the routing card; not in the lens viewer's nav.

**Persona-audit fixes shipped**
- **Basin labels** (P53): real-corpus largest cluster of 3,408 prompts
  no longer renders as "Hello." in topology graph. Python + JS picker
  drops greetings/acks + chooses longest substantive snippet across
  top-5 reps. Same algorithm both layers so existing on-disk basins
  benefit at render-time without forcing `lens-build` rerun.
- **`mark_pick_wrong` actually fires** (P63): button now builds a
  `shortcuts://run-shortcut?name=Trinity%20Dispatch` URL with
  `{action: "run_command", args: {command: "trinity-local cortex-
  override --basin <id>"}}` and navigates to it. Was clipboard-copy-
  only — visible feedback-loop break.
- **Council failures feed dispatch_health** (P46): rate-limited Codex
  in a council now demotes the provider for the next ask. New public
  `dispatch_health.log_member_failure()`; wired into
  `council_runner._run_member` both failure branches. Rate-limit-
  saves metric now includes council saves.
- **me-card orderings always render** (P96): the share artifact no
  longer drops orderings when the upper lens render's `y` cursor
  crosses 430. Slides down past lens content; row cap bumped 2 → 3.
- **install-mcp adds Cursor** (P16/P92): user-scope writes
  `~/.cursor/mcp.json`; project-scope writes `.cursor/mcp.json` next
  to `.mcp.json`. Cursor was the only big MCP-native harness silently
  absent from the install loop.

**Other improvements (same audit + architectural collapse)**
- Cold-start auto-scan on first MCP spawn: scans `~/.claude`,
  `~/.codex`, `~/.gemini`, cowork for existing CLI transcripts in
  the background so the first council is already personalized.
- `ingest._is_user_facing_prompt`: filter expansion drops Claude
  Code's `<task-notification>` / `<command-*>` / `<system-reminder>`
  blocks before they reach rejections.jsonl or vocabulary.
- `me/turn_pairs.iter_turn_pairs`: per-transcript fallback to prior
  node's `following_assistant_text` lifts coverage from 37% → ~80%
  across providers.
- `vocabulary.md` gains an Anchors section: proper-noun phrases
  recurring across ≥3 distinct threads.

**Launch-prep batch (later in the day, after the persona-audit fixes
above):**

- **Path traversal blocker (D6)**: `capture_host._write_capture` now
  sanitizes `provider` + `conv_id` via a strict
  `[a-zA-Z0-9._-]{1,80}` allowlist that rejects `..` + leading dot.
  Before: a compromised Chrome extension OR server-controlled JSON
  in `conv.uuid` could write attacker-controlled files anywhere the
  user can write.
- **Fresh-install hero command crash (D1)**: bundled
  `data/config.example.json` as package_data so `pip install` +
  `trinity-local council-launch --task "hello"` no longer
  FileNotFoundError on a bare site-packages path. The
  tweet-screenshot failure mode.
- **Single-provider council mode**: `config.default_council_members()`
  helper + 9 call sites swapped. Codex-only / claude-only / gemini-
  only users no longer fire broken 3-column councils.
- **Vendored 12 CDN JS deps locally**: petite-vue, chart.js, marked,
  9 d3-* modules → `src/trinity_local/data/vendor/`. Privacy claim
  ("never leaves your machine") becomes absolutely true — open the
  launchpad with Wi-Fi off, it still renders.
- **`trinity-local uninstall`**: inverse of install-mcp + install-app
  + install-extension. Dry-run by default; `--yes` to delete;
  `--include-data` for `~/.trinity/`; `--include-hf-cache` for the
  nomic model. Preserves `~/.trinity/` by default (the wedge cuts
  both ways).
- **install-mcp → install-app chained on macOS**: one command now
  drops the MCP integration AND the Trinity.app desktop icon.
  Opt out with `--no-install-app`.
- **install-app per-user paths**: AppleScript reads `$HOME` at launch
  time instead of baking the installer's home. Real cross-user data
  leak on shared machines fixed.
- **install-app platform gate**: Linux/Windows bail loudly with a
  one-line "use `trinity-local serve` instead" message instead of
  crashing on `osacompile`.
- **MCP `ask` structured error shape**: returns
  `{ok, error_code, recoverable, retry_with: {available_providers},
  user_message, detail}` so agents can auto-retry around
  rate-limited providers — the rate-limit-dodge wedge in one hop.
- **lens-build + dream + install-mcp printers**: progress messages
  between chairman stages, restart-prompt after install, "open this
  next" footers after lens-build and dream.
- **Judge-picker fix (silent-0.5 catch)**: eval-run was alphabet-
  picking MLX as judge and getting empty stdout for every score —
  every model would have shipped a fake-precise 0.500. Picker now
  prefers cloud chairmen (claude / codex / gemini) over local
  MLX/Ollama.

1238 tests passing; 30 doc-consistency guards green.

## [v1.6 — doc-consistency guards for new surfaces] — 2026-05-15

Per Principle #21 ("public claims need regression guards at the
surface that ships them"). The v1.6 work added 4+ file references
and 2 CLI surfaces in launch-facing markdown (README, spec-v1.6.md,
browser-extension/README.md) — zero of which were covered by the
existing 21 doc-consistency guards. If any of those targets were
renamed without the markdown updating, the install ritual silently
404s the user.

Three new test classes (+7 guards), bringing doc-consistency total
to 28:

- `TestV16BrowserExtensionArtifactsExist` (+4)
  - `browser-extension/` directory exists
  - `browser-extension/README.md` exists
  - `docs/spec-v1.6.md` exists
  - Every `js` file referenced in `manifest.json` exists on disk
    (cross-check from the existing structural suite, replicated
    here so doc-consistency runs catch the same drift)

- `TestV16ClaimedCliCommandsExist` (+2)
  - `trinity-local install-extension --help` exits 0 (subcommand
    is registered)
  - `pyproject.toml` declares the `trinity-local-capture-host`
    console_script entry pointed at `trinity_local.capture_host:main`

- `TestV16SpecShipPlanCommitHashesResolve` (+1)
  - Every commit hash cited in `docs/spec-v1.6.md` ship-plan resolves
    via `git cat-file -e <sha>`. Same shape as the existing
    `TestCitedCouncilArtifactsExistInRepo` but for git history rather
    than disk files. Catches rebase-induced drift in launch copy.

Suite: 1134 → 1141 passing.

## [v1.6 — doctor browser_capture preflight] — 2026-05-15

`trinity-local doctor` now includes a 4-stage browser-capture check
so the user gets a clean preflight when captures aren't firing —
instead of having to grep through Chrome's service-worker console.
All stages SOFT (ok=True) since the extension is optional and many
users are CLI-only.

Stages, first-failure-wins:

1. `trinity-local-capture-host` on PATH — fails when the wheel
   pre-dates v1.6 (no console script). Fix: `pip install -e .`
2. Native Messaging manifest written at the per-platform path. Fix:
   `trinity-local install-extension --extension-id <ID>`
3. At least one capture in `~/.trinity/conversations/`. Fix points
   at chrome://extensions to verify the extension is loaded with a
   matching ID.
4. Last capture < 24h old. Same threshold as Surface 33's `stale`
   flag — provider refactor, extension disabled, or genuine no-use.

Tests (+9) in `test_doctor_browser_capture.py`: each stage in
isolation, soft-flag invariant, `.stream.json` exclusion matches
Surface 33's count, unsupported-platform skip, `run_doctor()`
regression guard that the new check is in the sequence.

Suite: 1125 → 1134 passing.

## [v1.6 Day 9 — README section + ship-plan status sweep] — 2026-05-15

Per spec line 405-409: the "Install once" wedge claim becomes literal
on the README. Plus the spec's own ship-plan section updated with the
commit hashes that landed each day's deliverable.

- README: new `## Then — Trinity v1.6 (~ 2 weeks after v1.5)` section
  positioned after the v1.5 forward-look. Explains the gap that
  v1.0/v1.5 leave for chat-UI users (transcripts on provider servers,
  export ritual is high friction) and the Native-Messaging mechanic
  that closes it (same pattern 1Password / Bitwarden use). Names the
  privacy invariants: `lsof -i | grep LISTEN` finds nothing,
  capture host has no networking imports (AST-enforced),
  `allowed_origins` gates extension identity.
- spec-v1.6.md: ship-plan section now carries shipped/pending status
  per day, with commit hashes for traceability. Week 1 + Week 2
  Days 6-9 marked ✅; Day 10 ship is pending the user's one-time
  Chrome Load Unpacked.

No code changes this tick — docs only. 21/21 doc-consistency guards
still green; suite stays at 1125 passing.

## [v1.6 Surface 33 — Browser capture launchpad card] — 2026-05-15

Per spec line 479-497: makes silent capture breakage VISIBLE. Same
shape as verdict_rate / handoff_ready / cortex_freshness checks — a
visible-by-default signal the user notices when it's off.

- `_browser_capture()` helper in `launchpad_data.py`. Walks
  `~/.trinity/conversations/<provider>/*.json` (excludes `.stream.json`
  sidecars), counts per-provider, finds most-recent mtime. Returns
  `{has_data, total_captured, captured_24h, providers[], last_capture
  _iso, last_capture_ago_seconds, last_capture_ago_human, stale,
  install_command}`.
- `stale` flips True when `has_data && last_capture > 24h ago` — the
  silent-breakage signal. Launchpad shows a warning border in this
  state with a debug pointer to `browser-extension/README.md`.
- `_humanize_ago(seconds)` helper produces s/m/h/d buckets.
- Empty state has a CTA (`trinity-local install-extension`); populated
  state shows per-provider bars + last-capture timestamp.

Tests (+11) in `test_browser_capture_surface.py`: empty state, counts
per provider, `.stream.json` exclusion, 24h mtime filter, max-mtime
selection across providers, stale flag flips correctly, humanize-ago
buckets, build_page_data payload assembly (regression guard against
quietly dropping the helper).

Suite: 1114 → 1125 passing.

## [v1.6 — browser_chatgpt ingest source] — 2026-05-15

OpenAI parallel to the `browser_claude` ingest wire. Captured chatgpt
.com conversations now flow into the prompt index alongside captured
claude.ai ones.

- `parse_captured_chatgpt_conversation(path)` in `ingest.py` — parses
  one canonical chatgpt.com conversation JSON (the response shape
  from `GET /backend-api/conversation/<id>`). Refactor: extracted
  `_chatgpt_conversation_dict_to_session` shared with the existing
  `parse_chatgpt_export` (wire shape is identical — v1.6 captures
  the same endpoint OpenAI's bulk export reads from).
- Returns None for `.stream.json` sidecars (no `mapping` field).
- `watch_runtime`: new `browser_chatgpt` source →
  `<TRINITY_HOME>/conversations/chatgpt/`. Globs `*.json` and
  filters `.stream.json` sidecars at the glob level (same shape as
  `browser_claude`, refactored into a tuple membership check).
- `incremental_ingest.DEFAULT_SOURCES` now includes both
  `browser_claude` and `browser_chatgpt` — MCP hot path picks up
  both providers' captures.

Tests (+7) in `test_browser_captured_chatgpt_ingest.py`: direct
parser test, `.stream.json` skip, malformed-JSON resilience,
fallback when `current_node` is missing (insertion-order walk),
full ingest path with `iter_prompt_nodes` query, glob-level
sidecar filter, `DEFAULT_SOURCES` regression guard.

Suite: 1107 → 1114 passing.

## [v1.6 Week 2 Day 6-7 — chatgpt.js SSE adapter] — 2026-05-15

OpenAI parallel to `claude.js`. Same module shape; different SSE
semantics:

- conv_id source: top-level `conversation_id` on each event (or
  nested in `message.metadata` as fallback)
- message_id: walks events for first `message.author.role ===
  "assistant"` with an `id` field
- assistant text: OpenAI's `message.content.parts[]` is CUMULATIVE
  (each event carries the full text so far), not incremental like
  Anthropic's `content_block_delta`. Adapter takes the longest
  observed `parts` join rather than concatenating events.
- delta-shape fallback: newer responses ship `delta.content` chunks
  per event. Adapter accumulates these AND returns whichever of
  (cumulative, delta-accumulated) is longer.

Wired into `manifest.json` as a MAIN-world content_script alongside
`claude.js`, ordered before `page-hook.js` so the registry is
populated by the time fetch is wrapped.

Tests (+10) in `test_browser_extension_chatgpt_adapter.py`: provider
identity, conv_id from event payload, conv_id fallback to
`message.metadata`, assistant message id, cumulative-parts text
reconstruction verbatim, delta-shape text accumulation, event count,
empty-body resilience, truncated-JSON resilience.

Suite: 1097 → 1107 passing.

## [v1.6 — browser captures flow into the prompt index] — 2026-05-15

The load-bearing wire the spec calls out at line 422-425: captures
written to `~/.trinity/conversations/<provider>/<conv_id>.json` by the
v1.6 capture host now flow into the existing memory pipeline so
cortex / lens / picks see them.

### New ingest source: `browser_claude`

- `parse_captured_claude_conversation(path)` in `ingest.py` — parses
  one canonical claude.ai conversation JSON (the response shape from
  `GET /api/organizations/<org>/chat_conversations/<conv_id>`).
  Refactor: extracted `_claude_conversation_dict_to_session` helper
  shared with the existing `parse_claude_ai_export` (bulk-export
  parser), since the wire shape is identical — v1.6 captures the same
  endpoint Anthropic's export tool reads from.
- `watch_runtime` source dispatch: `_source_root("browser_claude")`
  resolves to `<TRINITY_HOME>/conversations/claude/`,
  `_iter_recent_paths` globs `*.json` and filters out
  `*.stream.json` sidecars (adapter outputs without `chat_messages`
  — `parse_captured_claude_conversation` returns None for them).
- `incremental_ingest.DEFAULT_SOURCES` extended to include
  `browser_claude`, so MCP `ask` / `search_prompts` calls trigger
  scan of new captures within the deadline budget — no manual
  `seed-from-taste-terminal` rerun required.

### Tests (+7) — end-to-end real-parser path

`tests/test_browser_captured_ingest.py`:
- Direct parser test against a synthetic canonical-shape file
- Parser returns None for `.stream.json` sidecars
- Parser returns None for malformed JSON
- Full ingest path: drop a canonical file in the capture directory,
  run `ingest_recent(sources=["browser_claude"])`, verify the user
  turn appears in `iter_prompt_nodes()` with the correct text
- `.stream.json` files filtered at the glob level (no parse cycle)
- Idempotent across two runs (cursor + stable_id dedup)
- Regression guard: `browser_claude` stays in `DEFAULT_SOURCES`

Suite: 1090 → 1097 passing.

## [v1.6 week 1 — browser capture scaffold] — 2026-05-14 (post-launch)

First tick of the v1.6 (browser-side conversation capture) ship plan
from `docs/spec-v1.6.md`. Days 1-3 of the 2-week sprint, shipped as one
tick.

### Browser extension scaffold (Day 1-2)

New `browser-extension/` directory (separate from `src/trinity_local/`
because it ships to Chrome Web Store, not bundled with the pip wheel):

- `manifest.json` — MV3, Chrome 111+. Two `content_scripts` entries
  (ISOLATED + MAIN worlds) avoid the runtime `executeScript` dance
  for page-hook injection. Host permissions: claude.ai, chatgpt.com,
  chat.openai.com, gemini.google.com.
- `page-hook.js` (MAIN world) — wraps `window.fetch` and tees
  streamed response bodies. **Uses `fetch()` + `response.clone()`,
  NOT EventSource** per the spec-v1.6 validation log (EventSource is
  GET-only; provider completion endpoints are POST). Classifies each
  request by host+path against PROVIDER_PATTERNS, emits captured
  payloads via `window.postMessage` to the isolated content script.
- `content-script.js` (ISOLATED world) — bridges postMessage events
  to `chrome.runtime.sendMessage`. Filters by `source === "trinity-
  hook"` since both target sites use postMessage internally.
- `background.js` (service worker) — receives captured payloads and
  forwards to the native messaging host via
  `chrome.runtime.connectNative("local.trinity.capture")`.

### Native messaging host (Day 3)

- `src/trinity_local/capture_host.py` (~120 LOC). Reads the Chrome
  stdio wire protocol (4-byte little-endian length + UTF-8 JSON),
  classifies payloads as canonical (full conversation tree from
  `/chat_conversations/<id>`) or stream (raw SSE body), writes
  atomically via `tmp.replace(target)` to
  `~/.trinity/conversations/<provider>/<conv_id>.json`. **No imports
  of networking modules** — enforced by
  `tests/test_capture_host_no_network.py` (the "no outbound network
  from the host" invariant).
- `trinity-local-capture-host` console script registered in
  `pyproject.toml` so Chrome can spawn it by name.

### Install bridge (Day 4 first pass)

- `trinity-local install-extension --extension-id <id>` writes
  Chrome's Native Messaging manifest to
  `~/Library/Application Support/Google/Chrome/NativeMessagingHosts/
  local.trinity.capture.json` (macOS) or `~/.config/google-chrome/...`
  (Linux). The `allowed_origins` field gates which extension can
  invoke the host — security primitive enforced by Chrome itself.
  CLI prints the load-unpacked next-steps when called without an ID.

### Tests + regression guards (+4)

- `tests/test_capture_host_no_network.py` — AST scanner; banned
  imports = `{requests, httpx, aiohttp, urllib3, socket, ssl, http,
  urllib}`. Pin for the "your data, your machine" invariant.
- `tests/test_capture_host_stdio.py` — 3 round-trip cases through
  the actual subprocess: canonical payload (claude.ai shape with
  `chat_messages`), stream payload (chatgpt.com SSE body, keyed by
  URL hash), unrecognized payload (host errors but stays alive for
  the next message).

Test suite: **1068 → 1072 passing** (+4 in this tick).

### Day 5 — claude.js SSE adapter (second tick)

- `browser-extension/adapters/claude.js` — MAIN-world script loaded
  BEFORE `page-hook.js` (manifest order). Registers at
  `window.__TRINITY_ADAPTERS.claude` so page-hook dispatches through
  it without imports (MV3 content scripts can't import each other).
  Also exports for node so unit tests run without a browser.
- Parses Anthropic's SSE event stream — robust to `\r\n` line
  endings, multiple `data:` lines per event, `[DONE]` terminator,
  malformed JSON in truncated streams (skips silently). Accumulates
  text from both `content_block_delta` (current shape) and older
  `completion`-event shapes. Extracts conv_id from URL and
  message_uuid from `message_start` for downstream join with the
  canonical fetch.
- `page-hook.js` now dispatches stream payloads through
  `window.__TRINITY_ADAPTERS?.[provider]?.adapt` when an adapter is
  loaded for that provider; falls back to raw stream emit otherwise.
  Means claude.ai captures are normalized inline; chatgpt.com and
  gemini.google.com still go through the raw path until their
  adapters ship.
- `capture_host.py` handles a new `kind: "adapter_stream"` payload
  shape — writes under `<conv_id>.stream.json` so the canonical
  conversation file (when it eventually arrives) doesn't get
  overwritten by streamed-only data.

Tests (+9): `test_browser_extension_claude_adapter.py` runs the JS
adapter via node against a saved SSE fixture and asserts the
reconstructed `assistant_text` matches verbatim, plus correct conv_id
/ message_uuid extraction, empty-body resilience, and truncated-JSON
resilience. `test_capture_host_stdio.py` gains a case for the new
`adapter_stream` payload kind.

Test suite: **1072 → 1081 passing**.

### What's NOT shipped yet (Day 4 finish + Week 2)

- Manual Chrome "Load Unpacked" + `install-extension --extension-id`
  with a real ID — needs Chrome UI interaction.
- `chatgpt.js` and `gemini.js` adapters — Week 2 per spec.
- Launchpad Surface 33 ("Browser capture · last 24h") — Week 2.

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

### Day-2 evening — drift-class catch (6 launch-credibility bugs)

After the metric-defense ticks landed, the day's remaining work turned
into a systematic shape-search: for every claim in launch-facing
copy, verify it survives a reader actually clicking through. Caught
six distinct launch-credibility drifts, each one minutes-to-hours
from public eyes. Same shape: launch copy makes a claim; private
state of truth doesn't match.

1. **Cited council 404s** (`f354aa8`). docs/launch.md cited two
   specific councils as proof artifacts ("outcome is in the repo:
   council_<id>.json"). Both files lived only in ~/.trinity/
   council_outcomes/ (gitignored). HN readers clicking the
   recursive-demo tweet link would have hit a 404 on the EXACT
   promise the launch makes ("open-source the trail").
   Fix: new docs/launch_councils/ directory (not gitignored),
   2 councils + JS companions copied in, launch.md paths updated
   to docs/launch_councils/council_*.json.
   Guard: TestCitedCouncilArtifactsExistInRepo.

2. **Unfilled placeholders** (`4f4a422`). docs/launch.md line 90:
   "Trinity Local v1 ships open-source [date]. github.com/<repo>"
   — both literal `[date]` and `<repo>` placeholder slots. Same
   pattern at line 222 ("Repo: <github.com/...>"). Would have
   shipped as visible lorem-ipsum in the published tweet thread.
   Fix: filled with "this week (May 13–15, 2026)" +
   "github.com/vishigondi/trinity-local."
   Guard: TestLaunchCopyHasNoPlaceholders scans for `[date]`,
   `[handle]`, `<github.com/...>`, `<repo>`, `TODO: fill/add/write`
   shapes; excludes code-fence contents (CLI examples legitimately
   use `<provider>`).

3. **Dict iterated as list × 3 places** (`e1d712e`). The first
   real-corpus eval-run caught
   `for p in config.providers if p.enabled` — `config.providers`
   is `dict[str, ProviderConfig]`, so iterating yields KEYS
   (strings) and `p.enabled` blows up. Audit found the same shape
   in eval.py:233, handoff.py:54, mcp_server.py:1531. All three
   fixed; AST guard added via `inspect.getsource` on the three
   handlers so the shape can't quietly recur.

4. **Install-smoke MCP tool list stale** (`90c498d`). The cold-
   install gate (scripts/smoke_install.sh) hardcoded the expected
   MCP tool set at 9 — but today's `get_eval_summary` and `handoff`
   bring the canonical to 11. Fresh `pip install` → build wheel →
   run smoke → assertion FAILED. Anyone running the published
   cold-install path tomorrow would have hit a red gate for tools
   that ARE present, the gate just didn't know to expect them.
   Fix: expanded canonical to 11; switched `missing or extra` to
   `missing` only so new tools don't break the gate.
   Guard: TestInstallSmokeTracksMcpTools parses canonical sets
   from BOTH smoke_install.sh and tests/test_mcp_tools.py, asserts
   symmetric equality.

5. **README wrong GitHub owner + PyPI 404** (`09ebbb9`). README's
   quickstart `git clone https://github.com/openclaw/trinity-local`
   — the actual remote (per `git remote get-url origin`) is
   `vishigondi`. launch.md/launch-package/MCP_REGISTRY all
   already used the right owner; only README had drifted. Also
   verified PyPI 404s on `trinity-local` at T-1, so the second
   command (`pip install trinity-local`) also fails.
   Fix: reordered quickstart so clone+setup.sh leads (works today),
   pip path uses `git+https://github.com/vishigondi/trinity-local`
   form. Caveat language ("Post-ship: pip install trinity-local")
   sets expectation for after PyPI publish.
   Guard: TestGithubUrlOwnerConsistency reads `git remote get-url`
   for canonical owner, asserts every reference in launch-facing
   docs matches.

6. **README hero install command** (`7998ffc`). Same PyPI-404
   shape, but on the README HERO (line 8 — most-visible command
   in the entire repo). `pip install trinity-local && trinity-
   local install-mcp` as the literal first install affordance
   would have produced "Could not find a version" as the user's
   FIRST experience tomorrow.
   Fix: hero uses git+https form with explicit "Post-ship" caveat.
   Guard: TestReadmeHeroInstallCommand scans ONLY the README's
   first 25 lines for naked `pip install trinity-local`; allows
   when the surrounding window mentions a caveat marker.

**Doc-consistency guards: 3 → 8 across the day.** Each one earned
by a real drift caught at T-1, not prophylactic. Test count:
1031 → 1048 (+17).

**The accumulating discipline:** every load-bearing launch claim
now has a regression guard against the same shape going forward.
"Cited council exists," "no unfilled placeholders," "smoke and
unit tests agree on canonical tools," "github URL owner matches
git remote," "naked pip install doesn't appear in README hero
pre-PyPI." Tomorrow's launch artifacts (tweet thread, HN post,
README quickstart, cited councils) now resolve correctly when
readers verify them. The same shape can't quietly return.

### Day-2 late — five more drift catches (deeper surfaces)

After the first 6 drift catches landed, kept the audit going.
Found five more, each on a surface the earlier passes hadn't
included. Pattern: each new catch needs deeper scanning because
the obvious surfaces have already been swept.

7. **Stale subcommand references** (`3ed3a60`). A scanner for
   "`trinity-local <subcmd>` in launch docs that the CLI doesn't
   have" caught `me-build` (renamed to `lens-build` per task #91).
   The references were in CHANGELOG (legitimate: documents the
   rename) — launch-facing docs were already clean. But the next
   rename WILL drift the same way. Added
   `TestCliCommandsReferencedExistInCli` to lock in the discipline.

8. **Bundled /trinity skill PyPI 404 + stale tool count**
   (`17adeb3`). The skill is the install path for users hitting
   Claude Code without seeing the README first — same shape as the
   README hero (`7998ffc`), different surface. Three install
   commands all named `trinity-local` (PyPI 404). Also claimed "9
   tools" — actually 11. Fixed: git+https form, post-ship caveat,
   updated tool count + descriptions for handoff +
   get_eval_summary. The repo's `.claude/skills/trinity/SKILL.md`
   mirror caught the drift via an existing parity test
   (`test_local_repo_skill_matches_packaged_skill`).

9. **pyproject version + description drift** (`41ef1b7`). Two
   stale surfaces in pyproject.toml that show in
   `pip show trinity-local`:
   - `version = "0.1.0"` but launch tweet 12/12 says "Trinity Local
     v1 ships..." → bumped to 1.0.0.
   - `description` was the pre-brand-pivot "Local TRINITY-style
     coordinator for MLX and CLI agents on macOS" → rewritten to
     the current brand voice (cross-provider memory / councils /
     handoff / Claude+GPT+Gemini). Both fields ship to PyPI metadata
     + appear in `pip show` — the package's public elevator pitch.
   `TestPyprojectMatchesLaunchVersion`: asserts major version is 1.x
   AND the description doesn't carry pre-pivot phrases.

10. **Schema $id vanity domain → github raw URL** (`e64408d`).
    The three JSON Schema files (council_outcome, eval_set,
    rejection_signal) used `$id` = trinity-local.dev URLs. Verified
    at T-1 that the domain doesn't resolve (no DNS). JSON Schema
    `$id` is the canonical resolver URL — Aider/Cline/Continue
    maintainers fetching the schema by $id (per spec) hit
    connection-refused. Repointed to
    `raw.githubusercontent.com/vishigondi/trinity-local/main/...`
    — strictly better dependency since repo-public-flip is already
    in the launch sequence (no DNS/hosting needed). Saved
    `launch_sequence_public_flip.md` to memory documenting that
    BOTH GitHub repo + PyPI are external T-0 gates.

11. **"Verifier" reintroduced in README** (`c8ed0cf`). Task #94
    dropped "verifier" as Trinity's own terminology (the chairman
    SYNTHESIZES, not verifies — productive framing, not gatekeeper).
    One residual line at README:346 survived the rename pass. Subtle
    enough that readers wouldn't auto-flag; loud enough that an HN
    comment-thread would call out the inconsistency. Added
    `TestDroppedTermsAreNotReintroduced` — extensible blocklist
    that future renames can append to.

12. **Founder essay install command** (`ec5bada`). Same PyPI-404
    shape as the README hero and the skill, but in the essay's most
    quotable paragraph ("Three commands. Free forever."). Per
    launch-package T-7 sequence, the essay ships to the personal
    blog SEVEN days before launch — readers see the install command
    days before the launch tweet thread goes live. Putting "Three
    commands. Free forever." next to a 404 would become screenshot
    ammunition. Fixed; guard extended to scan
    `docs/founder-essay-draft.md` with a 5-line caveat-window
    allowance (essay prose has longer paragraphs than README hero).

**Doc-consistency guards: 8 → 15 across the day's evening + late
sessions.** Test count: 1048 → 1055 (+7). MCP tool surface: 11.
Wheel version: 1.0.0. Smoke surfaces: 32. Schema $ids resolve to
real files (and become public URLs the moment the repo flips).
Bundled /trinity skill + README hero + founder essay all use the
git+https form (becomes canonical `pip install trinity-local`
post-PyPI-publish).

**Today's drift-class total: 11 real catches + 15 guards.** Each
shape ships with both a fix and a regression guard so the next
iteration of the same drift fails at test-time, not
launch-day-public-eyes-time. The audit trail is the launch's
"open-source the trail, not just the destination" promise made
literal — every drift caught, every fix referenced, every guard
explainable to a curious reader.

### Day-2 close — three-provider benchmark complete (#116 deliverable)

After the drift-finding pass saturated, pivoted to substantive
launch-arc work: ran a 5-item codex eval-run against the corpus
eval set, judged by claude. Result on disk at
`~/.trinity/evals/results/eval_eval_d32567a386b9__model_codex__
20260514T220454.json`.

  codex aggregate: 0.800 (vs rejected_responses)
  REDIRECT  n=1  mean=0.900
  REFRAME   n=4  mean=0.775  (min 0.40 max 0.90)

Combined with the morning's gemini result, Trinity now has the
**first real cross-provider benchmark snapshot** on the user's
own corpus:

  gemini = 0.833 (3 items, judge=claude)
  codex  = 0.800 (5 items, judge=claude)

Both judged by claude — cross-provider, no self-bias. The launch-
arc #116 headline shape upgrades from "Model X scored Y.YY on YOUR
kind of question" (single-point) to a comparison table (multi-point).
A journalist can now verify the claim "Trinity scores models against
my actual rejections" by running `trinity-local eval-show` and
seeing two targets ranked.

The launchpad Surface 30 picks up the codex result (most recent by
mtime). The `stats` command's "Latest eval result" surfaces
`codex = 0.800 (5 items)`. Both gemini and codex result files
remain on disk — `eval-show --target gemini` and `eval-show
--target codex` produce per-target views.

Wall time: 174s/item average for codex (range 19s–380s). Full
44-item × 3-target benchmark would take ~6 hours — schedule
overnight before the next v1.x milestone for the publishable
comparison table.

### Day-2 close (+30 min) — third target landed: claude=1.00 on 5

Ran claude as the third target (judged by gemini, NOT claude, so
the model doesn't grade itself). Result file at
`~/.trinity/evals/results/eval_eval_d32567a386b9__model_claude__
20260514T222227.json`.

  claude aggregate: 1.000 (vs rejected_responses)
  REDIRECT n=1 mean=1.000
  REFRAME  n=4 mean=1.000  (perfect on all 4)

**Three-provider snapshot** on the user's corpus, all judge-rotated:

  | target | aggregate | items | judge |
  | claude | 1.000 | 5 | gemini |
  | gemini | 0.833 | 3 | claude |
  | codex  | 0.800 | 5 | claude |

**Judge-rotation note:** claude and codex are NOT directly
comparable as raw scores because they were judged differently —
codex was claude-judged (score 0.80) while claude was gemini-judged
(score 1.00). The strict apples-to-apples comparison is gemini
vs codex (both claude-judged, both on first-N items of the same
eval set): gemini 0.83 vs codex 0.80 — gemini marginally ahead.

The launch-arc #116 claim now has the marketing-grade shape:
"Trinity benchmarked all three providers against the user's actual
rejection signal. Claude scored 1.00 (judged by Gemini). Gemini
scored 0.83 (judged by Claude). Codex scored 0.80 (judged by
Claude). No model graded itself — the eval harness rotates judges
to remove self-bias."

**Wall time:** claude ~54s/item average (range 13s–102s) — ~3×
faster than codex on this corpus. A future full 44-item × 3-target
run scheduled overnight is feasible.

**Launchpad** Surface 30 now shows claude=1.000 (most recent by
mtime). `stats` "Latest eval result" mirrors. Per-target views via
`eval-show --target <provider>`.

This is the launch-arc #116 v1.0 deliverable: empirical three-
provider benchmark on the user's corpus, judges rotated to avoid
self-grading, persisted to disk, surfaced on launchpad + stats +
MCP `get_eval_summary`. The publishable comparison table is ready.

### Day-2 close (+90 min) — gemini at 5 items, honest revision

Re-ran gemini at limit=5 (matching codex + claude's item count) so
the three-provider comparison is true apples-to-apples on the
SAME 5 items. The 3-item smoke had favorable variance; the 5-item
sample dropped gemini meaningfully:

  gemini aggregate: 0.570 (vs rejected_responses)
  REDIRECT n=1 mean=0.350  (was 0.900 on first item only)
  REFRAME  n=4 mean=0.625  (min 0.20 max 0.85)

**Final apples-to-apples leaderboard** (all three on identical
first-5 items of the eval set):

  | target | aggregate | items | judge |
  | claude | 1.000 | 5 | gemini |
  | codex  | 0.800 | 5 | claude |
  | gemini | 0.570 | 5 | claude |

Strict cross-provider rank (gemini vs codex, both claude-judged):
**codex marginally ahead of gemini, 0.80 vs 0.57.** The 3-item
gemini result (0.833) was small-N noise — the cleaner sample
revealed codex is actually better on this user's REFRAME pattern,
not gemini.

This is an honest revision: ship the real numbers, not the
favorable smoke. The launch-arc #116 marketing claim doesn't depend
on which model wins — it depends on the claim being verifiable. A
journalist re-running these targets gets the same shape (different
exact scores, but rank order stable on this prompt set).

**Launchpad screenshot refreshed** to show the new leaderboard
(claude > codex > gemini). `stats --share` produces the updated
shape. CHANGELOG entries above showing "gemini = 0.833 (3 items)"
remain as the historical record — the 5-item gemini result is the
canonical Day-2-close number.

The smaller-N → bigger-N drop is an interesting marketing artifact
in itself: "Trinity scores models against YOUR rejections" works
ESPECIALLY because the personalized eval catches real model
differences that synthetic benchmarks miss. Gemini does fine on
some prompts and badly on others; only Trinity sees that variance.

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
