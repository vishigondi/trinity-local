# Simplification log

Working memory for the simplify-app loop. Each entry records one
audit decision so the loop doesn't reaudit the same surface and so
the user can review proposals in the morning.

Verdict shapes:
- **KILL** — surface deleted outright, no replacement (audience too
  small / overlaps fully with another surface)
- **COLLAPSE-INTO-<other>** — surface folded into another existing
  surface (audience kept, but name eliminated)
- **KEEP** — surface earns its place; do not reaudit
- **PROPOSAL** — call is judgmental or blast radius is large;
  needs user decision before action

## Audited

- 2026-05-18: `trinity-local doctor` → **COLLAPSE-INTO-status + install.sh inline**.
  Tiny post-install audience (errors already name the actual problem);
  install.sh ran it as the install-verification step; MCP rate_action
  uses the same checks via internal helpers. Decision: kill the
  user-facing command, inline checks into install.sh's final verdict
  line, absorb the diagnostic header into `trinity-local status`.
  Internal helpers (provider detection, dir writability, MCP dep
  presence, verdict_rate, macOS Shortcut check) stay as importable
  Python — they're called by install.sh, status, and the MCP server.
  **Status: pending execution by the loop.** The decision was made
  during the conversation that seeded this log; the actual rename
  hasn't shipped yet. The loop should treat this as PROPOSAL until
  the rename ships, then convert to COLLAPSE.

## PROPOSAL: `search_prompts` MCP tool

**Verdict**: KILL (escalated to PROPOSAL — load-bearing per claude.md)

**Why**: The audit agent argued `search_prompts` is a convenience wrapper
over CLI `replay-history` and the lens file — agents with filesystem
access (Claude Code) can use the CLI, and replay is user-driven anyway
(agent suggests, user chooses). 6 files / ~80 lines blast radius.

**Counter**: claude.md explicitly says "Removing any of `route`,
`run_council`, `record_outcome`, `search_prompts` breaks a meaningful
surface." That's a load-bearing architectural commitment, not casual
surface area. It also exists for MCP-only environments where agents
have no shell — the audit dismissed this as speculation but didn't
disprove it.

**Blast radius**: ~6 files, ~80 lines. Sweep: mcp_server.py, claude.md
mentions (×3), spec docs, test_mcp_tools.py, test_doc_count_consistency.py
tool-count expectation.

**Risk**: Killing a v1.0 canonical MCP tool on launch day (T-0) without
data on actual agent call patterns. Tool count claim (11) becomes 10
across all surfaces that pin it.

**Decision**: PENDING USER. My recommendation: defer to v1.1 — collect
agent-call telemetry from the first week of users, then revisit. If
`search_prompts` call count is <5% of total MCP calls, kill it then.
The cost of carrying it for one extra week is one tool-count claim;
the cost of killing it incorrectly is breaking MCP-only agent flows.

**Audited**: 2026-05-18, iteration 1.

- 2026-05-18 (iter 2): README Quickstart `Or use the CLI directly:` +
  `Or, from inside Claude Code:` alternative-path blocks →
  **COLLAPSE-INTO-Help section**. The `/trinity` skill is the primary
  entry point and teaches the full CLI after the first council; the
  Help section already documents every command; offering CLI examples
  as an "Or" alternative in the Quickstart is premature cognitive
  loading for v1.0. Files touched: 1 (README.md, -15 lines).
  Tests: 1402 pass, 4 skip (unchanged).

- 2026-05-18 (iter 3): `--json` flag on `eval-build`, `eval-run`,
  `eval-show` → **KILL**. Zero documented usage (no README/SKILL.md
  mention beyond their own argparse help), zero tests exercise the
  True branch (5 test arg constructors had `as_json=False` but none
  asserted the JSON-output path), zero downstream consumers. The
  result files are already JSON on disk at `~/.trinity/evals/...`;
  power users can `cat | jq`. Pre-launch dead branch removal.
  Files touched: 2 (eval.py -22 lines, test_evals_runner.py -5 stale
  args). Tests: 1402 pass, 4 skip (unchanged). Shipped: e5947a0.

- 2026-05-18 (iter 4): user-facing error strings in `me_builder.py`
  referencing removed command `me-build` → **KILL stale refs, replace
  with `lens-build`** (renamed per task #91 but error strings missed
  the sweep). 4 user-facing strings (lines 327/354/367/389) told the
  user to re-run a command that no longer exists; 9 docstring/comment
  refs swept for hygiene; line 327 also gained the canonical
  `trinity-local` prefix (matches the form in commands/me.py). The
  audit agent first picked SKILL.md doctor refs but that was wrong
  (doctor is still a PROPOSAL, not yet removed); pivoted to this
  category 10 catch. Files touched: 1 (me_builder.py, 13 string
  replacements + 1 prefix addition). Tests: 1402 pass, 4 skip.

- 2026-05-18 (iter 5): stale `~/.trinity/memory/` paths + `me-build`
  command name in module docstrings → **KILL stale refs**. The
  memory/ → prompts/ rename (task #90) and me-build → lens-build
  rename (task #91) both missed two docstrings. Specifically:
  vocabulary.py:3 said `~/.trinity/memory/prompt_nodes.jsonl`;
  incremental_ingest.py:4 said `~/.trinity/memory/cursors.json` +
  line 7 said `me-build`. Confirmed canonical via state_paths.py:196
  (`path = state_dir() / "prompts"`); `memory_dir()` is now just a
  back-compat function name aliasing the prompts/ directory. Files
  touched: 2 (vocabulary.py, incremental_ingest.py — 3 string edits
  total). Tests: 1402 pass, 4 skip.

- 2026-05-18 (iter 6): `commands/research.py` argparse registration
  (6 user-facing CLI commands: `replay`, `embed`, `rank`, `hard`,
  `hardeval`, `analytics`) → **KILL**. claude.md explicitly tags these
  "off the live product path — research pipeline only"; they're not
  in README, SKILL.md, or launchpad. Zero outside importers (the file
  was only consumed by main.py registration). The internal
  `research/*` package stays — tests still pass because they import
  directly from `research/replay.py`, `research/embeddings.py`, etc.
  Net: 6 commands disappear from `trinity-local --help`. Files
  touched: 3 (deleted commands/research.py 431 LOC, main.py -1 line,
  claude.md -1 table row). Tests: 1402 pass, 4 skip (unchanged).

- 2026-05-18 (iter 7): `merges-show` CLI command → **KILL**. Same shape
  as iter 6 — claude.md explicitly tagged it in the "ancillary
  maintenance/debug tools intentionally off the user-surface table"
  list (along with distill, stats, trust). The handler was pure debug
  ("verify the side-channel writers (council_winner / cortex_override
  / in_thread_overwrite) are landing rows") — no user audience, not
  in README/SKILL.md/launchpad. Audit agent first picked README "For
  teams" + "For tool builders" sections but those are the waitlist
  lead-gen + standardization launch-arc workstreams (#117/#118) —
  intentional, not premature. Pivoted to merges-show. Trust /
  cache-stats / distill / stats spared (trust has user-facing CLI in
  docs/INSTALL-skill.md; cache-stats is a real debug tool; distill
  has standalone use post-manual-edit; stats is the launch-package
  one-liner per its own docstring). Files touched: 4 (deleted
  commands/merges.py 50 LOC, main.py -1, claude.md table -1, deleted
  TestMergesShowCLI class in test_merges_log.py -18 LOC). Tests:
  1401 pass, 4 skip (1 test removed with the dead class).

- 2026-05-18 (iter 8): SKILL.md § 3 ("Pre-flight checks") → **KEEP**.
  Audit agent wanted to KILL it as redundant-with-install.sh-doctor,
  but missed that line 26 explicitly routes already-installed users
  directly to § 3 (skipping § 2 install). For re-invocations days/
  weeks after install, § 3 is the user's only verification surface
  (auth expiry, missing CLI, fresh env). Section also carries the
  unique cold-start callout (first-embed downloads ~250MB nomic
  model) that's not in install.sh. Verdict overridden; no code
  change.

## PROPOSAL: `notifications-enable` / `notifications-disable` CLI

**Verdict**: KILL the user-facing CLI toggle pair (audit) — escalated
to PROPOSAL because it's a whole-feature decision

**Why**: Audit agent argued these 2 subcommands have no audience —
off-by-default, no launchpad toggle UI, ~nobody runs `trinity-local
notifications-enable`. But killing them orphans the entire
notifications feature: `notifications.py` is actively imported from
7 modules (watch_runtime.py × 3, action_runtime.py, council.py,
portal.py, review.py, me_card.py, capture_host.py). Without the CLI
toggles, users have no way to flip the feature on, so this is a
de-facto whole-feature kill, not a surface cleanup.

**Blast radius (the surface cleanup, not the feature kill)**:
- commands/telemetry.py: ~12 LOC (2 subparser blocks + 2 handlers)
- Tests: 0 reference these specific subcommands
- CHANGELOG.md mentions stay as historical record

**Blast radius (if you also kill the feature)**:
- notifications.py: ~150 LOC
- 7 importing modules each need their `notify()` call removed or replaced with a no-op
- Tests: light, mostly mocking notify

**Risk**: Notifications are the load-bearing mechanism for the "council
finished, check the result" UX path. Killing them silently removes a
real (if minor) capability for users who'd benefit from system notifs.
The decision isn't a launch-day cleanup; it's a v1.0 feature scope call.

**Decision**: PENDING USER. My recommendation: KEEP for v1.0, revisit
post-launch with telemetry data. If notification opt-in rate is <1%
after a month, kill the whole feature (CLI + notifications.py +
caller sites). Until then, the off-by-default behavior costs nothing.

**Audited**: 2026-05-18, iteration 9.

- 2026-05-18 (iter 10): `review-link --web-base` + `--no-web` flags →
  **KILL**. The `--web-base` flag pointed at `https://trinity.openclaw.
  ai/app`, an unregistered host that 404'd; its default was already
  flipped to None so no `web_url` was ever emitted. `--no-web` was a
  no-op preserved for backward-compat. Pure dormant code — kept the
  CLI surface noisy + carried a hostname promise we don't keep. Files
  touched: 2 (commands/portal.py -23 LOC: 2 flag defs + simplified
  `_review_link_payload` signature dropping the unused web_base param
  + handler simplification; tests/test_review_link.py -10 LOC: drop
  the now-dead `test_no_web_omits_hosted_bootstrap_url` test + remove
  `web_url` assertions from the privacy test). Tests: 1400 pass, 4
  skip (2 tests removed with the dead flag).

- 2026-05-18 (iter 11): dream `--skip-consolidate` / `--skip-lens-build`
  / `--skip-vocabulary` / `--skip-distill` flags → **KEEP**. Zero
  user-facing documentation (no README/SKILL.md mention beyond
  argparse help) AND each phase has a dedicated standalone command
  (`consolidate`, `lens-build`, `vocabulary`, `distill`) — looked like
  a clean kill candidate. But tests/test_dream.py uses them
  extensively as test scaffolding: ~10+ test methods pass
  `skip_consolidate=True, skip_me_build=True` to make dream
  orchestration tests fast by skipping expensive phases. Removing
  the flags would require a test refactor (replace flag-based
  scaffolding with mocks/fixtures) that exceeds the loop's 200-line
  cap. The flags earn their place via internal test affordance even
  though user-facing audience is thin. Audit agent first picked
  test_commands_review.py for kill (a test file, off-mission — loop
  is for user-facing surfaces); pivoted to dream --skip-* and found
  this KEEP rationale.
  Also noted: dream.py:60 has `dest=skip_me_build` (back-compat with
  pre-rename) on `--skip-lens-build`. Minor internal drift; not
  worth fixing standalone since it affects no user surface.

- 2026-05-18 (iter 12): `install-hooks` CLI command → **KEEP**. Audit
  agent flagged it as "0 audience / Phase 4 unfunded scaffolding" but
  the handler at install.py:464-517 is a real Stop-hook installer
  that wires a `~/.claude.json` block to call `watch-once --quiet`
  after every Claude turn. Use case: auto-ingest for CLI-only users
  (non-MCP setups). It's redundant with the MCP first-spawn
  auto-scan for ~95% of users, but the remaining 5% — pure CLI users
  without MCP — depend on this opt-in path. Documented in
  scale-plan.md:793 ("Off by default; enable explicitly via
  `trinity-local install-hooks`") and exercised by
  test_phase8_integration.py:175 (registration smoke test). Killing
  it requires deciding "do non-MCP users matter for v1?" — a product
  scope call, not pre-launch simplification. Verdict: KEEP. (Could
  reopen as PROPOSAL if you decide non-MCP is out of scope.)

## PROPOSAL: Launchpad empty-state eval-summary card

**Verdict**: KILL the empty-state branch (audit, escalated to PROPOSAL —
launchpad UX touch shouldn't ship at 3am without sign-off)

**Why**: Two eval-summary-card sections in launchpad_template.py:
- Line 1296: `has_results` branch — shows actual per-axis scores. Earned.
- Line 1468: `!has_results` empty-state branch — CTA to run `eval-build`
  / `eval-run`. Hit by ~100% of Day-1 users (eval requires N rated
  councils + mined rejections; only starts populating after a few rounds).

The empty-state card is pure scaffolding for a workflow that hasn't
started, doesn't drive any first-run action (the lens / picks empty
states do — they push users into the core council loop), and crowds out
useful cards on the home screen. The populated version stays as is.

**Blast radius**: 1 file (launchpad_template.py, ~22 LOC for lines
1468-1487). `_eval_summary()` in launchpad_data.py is reused by the
populated branch — no data layer change.

**Risk**: scripts/browser_smoke.py:1882 takes a screenshot named
"30-eval-summary.png" — surface 30. If the smoke test runs on a
fresh ~/.trinity (no eval results), the screenshot becomes empty
after this kill. Need to verify what surface 30 actually asserts
(existence of the card vs. text content) before shipping.

**Decision**: PENDING USER. Recommendation: KILL the empty-state
branch + audit surface 30 to either (a) skip if no eval results,
or (b) seed a fake eval result in the smoke fixture so it always
renders the populated card. Simpler choice is (a) — empty launchpad
states aren't useful smoke surfaces anyway.

**Audited**: 2026-05-18, iteration 13.

- 2026-05-18 (iter 14): no actionable surface → **KEEP** (whole iter).
  Audit hunted cat 7 (flag noise on unrated/depth/cache — clean),
  cat 10 (stale refs to renamed/removed commands in docs/scripts/
  skills — all live or already swept), and cat 4 (H3/H4 README
  drift — none). Convergence signal: the easy KILL/COLLAPSE territory
  is exhausted; what's left is the 4 open PROPOSALs queued for user
  decision.

