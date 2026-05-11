# Changelog

All notable changes to Trinity Local. Format follows [Keep a Changelog](https://keepachangelog.com/);
versioning matches the project's phase + capstone cadence rather than strict semver.

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
  2. HN title de-jargoned: dropped "verifier-shaped" — *"Show HN: Trinity Local — a local
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
  refinement). Chairman synthesis emits verifier-shaped Routing JSON with `agreed_claims`,
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
