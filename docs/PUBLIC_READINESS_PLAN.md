# Public-readiness execution plan

> **Loop-executable.** Each item is one self-contained tick. Pick the
> first uncompleted item, do it, run pytest, commit, then stop. The
> loop will fire again with this same prompt — pick the *next* item.
>
> **Stop condition:** when every item below is checked, the loop should
> not pick more work — call `CronDelete` and report the summary.
>
> **Verification after every fix:**
>
> ```bash
> .venv/bin/python -m pytest -q                       # full suite must stay green
> .venv/bin/python -m pytest -q tests/test_doc_count_consistency.py  # guards must stay green
> ```
>
> **Test-hygiene rule for every item below.** When a fix renames a
> module / deletes a doc / removes a CLI flag, sweep `tests/` in the
> same commit. Two failure modes to catch each tick:
>
> 1. **Stale tests** — `tests/test_X.py` for an `X` that no longer
>    exists, OR tests asserting on a string/path/module that was just
>    deleted. Sunset them (`git rm`) and note in the commit message.
> 2. **Stale guards** — `tests/test_doc_count_consistency.py` rules
>    pointing at a file that just moved (path-anchored asserts) or a
>    count that just shifted (numeric asserts). Update the guard in
>    the same commit; do NOT loosen the guard to make it pass — that
>    silently disables it.
>
> The 4-surface agree-guard already enforces this for some categories
> (test counts, MCP tool counts, brand axis). Each new tier-3 deletion
> below should add or update the corresponding guard.

## Tier 1 — HIGH (fix before flipping public)

- [x] **H1. Replace `trinity.local/install.sh` vanity URL with the real one.** ✓ done in commit (see git log). Swept `docs/launch-day/01_tweet_thread.md:11,72` and `docs/launch-day/02_show_hn_post.md:19`. Extended `tests/test_doc_count_consistency.py::TestNoUnregisteredVanityDomains` to cover `docs/launch-day/*.md` (was a guard coverage gap — the same shape can't recur) and to match the bare-host form (`curl trinity.local/...`, no protocol prefix) in addition to the existing `https://` form.

- [x] **H2. Reconcile the v1.0 vs v1.7 version story.** ✓ done. Swept `docs/launch.md:90` ("v1" → "v1.7"), `docs/launch-package.md:16` (rewrote ship-window paragraph from "v1.0 lands" → "v1.7 ships"), `docs/launch-package.md:189-191` (git tag `v1.0.0` → `v1.7.0`). Updated `pyproject.toml` version `1.0.0` → `1.7.1` (matches the CHANGELOG `v1.7.1 — public-readiness pass` entry). Added new guard `test_launch_copy_pins_pyproject_minor_version` — reads pyproject's `major.minor` (e.g. `v1.7`), asserts that string appears in all 4 launch surfaces. When v1.8 lands, this fires until the launch copy is swept.

## Tier 2 — MEDIUM (cosmetic drift readers will notice)

- [x] **M3. Pin the macOS framing.** ✓ done. Test-hygiene sweep caught one additional drift beyond the named target: `docs/spec-v1.md:258` had "Windows / Linux — macOS-only is a feature, not a bug" — a directly-contradictory hard-framing claim. Updated to "macOS-first at launch; cross-platform expansion is the v1.5/v1.6 trajectory per `docs/cross-platform-spec.md`. The core CLI + MCP path runs on Linux today (pyproject's `POSIX :: Linux` classifier reflects this); the launchpad Shortcut dispatcher is macOS-specific until the v1.6 browser-extension fallback ships." Swept `launch.md:109` to match (now "macOS today, cross-platform on the v1.5/v1.6 roadmap"). Component-specific macOS references (Trinity.app, macOS Shortcut, INSTALL-extension.md) are accurate and left alone. Founder essay deferred to D8 (it's "draft" — same fix when essay is finalized). Pyproject classifier intentionally keeps both; the spec text now explains why. Test sweep: 5 test files mention macOS/darwin but all for platform-conditional test logic (not framing assertions) — no test updates needed.

- [x] **M4. Caveat the README 60-second demo's prerequisites.** ✓ done. Added a quoted "First-install prereq" callout right after the demo block's intro line (before both demos), framing the seed step as one-time and explicitly redirecting to the skill for the walkthrough. Position is above both demos so a reader sees the prereq before encountering either `handoff` or `eval-run` — the most user-friendly placement. Test sweep: tests reference "60-second" / "wedge" in marketing-voice assertions (test_doctor.py:425-427, test_mcp_tools.py:45) but none assert on the README's specific demo body text, so the new callout is non-breaking.

- [x] **M5. Sweep `claude.md` CLI module count + add 6 undocumented commands.** ✓ done. Added `vocabulary` row (after `cortex`, before `doctor` — same "extracts patterns from prompts" family) and `update` row (after `install`, the natural neighbor for self-maintenance commands). New table count: 30 rows. Header updated from "22 modules" to "30 modules in the table below; 4 more — `distill`, `merges`, `stats`, `trust` — are ancillary maintenance/debug tools intentionally off the user-surface table" — explicit about why the disk count (34) doesn't equal the table count, so a future reader doesn't re-introduce the same drift. Test sweep: no test asserts on the module count.

## Tier 3 — DELETE / SIMPLIFY (after Tier 1+2 land)

- [x] **D6. Delete `docs/spec-v2.md` — REVERSED, keeping the file.** Investigation surfaced two facts that flip the decision:
  1. **Agent 4 was wrong about the redirect.** Plan claimed "Architectural reference preserved in `docs/v2-loop-constitution.md`." Inspection: v2-loop-constitution.md (262 LOC) covers a DIFFERENT topic — the v2 loop substrate (loop/, frame.py, verify_web.py, since-removed code). spec-v2.md (1,500+ LOC) covers the trained-coordinator architecture and the "why we pivoted to v1.5" rationale. Deleting spec-v2.md would lose architectural-decision history that v2-loop-constitution.md does NOT preserve.
  2. **Live cross-references are load-bearing.** `git grep "spec-v2"` outside CHANGELOG returns 14 hits across 13 files: README.md (×2), claude.md, CONTRIBUTING.md (×2), docs/spec-v1.md, docs/spec-v1.5.md, docs/scale-plan.md, docs/product-spec.md, docs/launch.md, docs/launch-package.md, docs/REPO_PUBLIC_RUNBOOK.md, src/trinity_local/state_paths.py, tests/test_doc_path_consistency.py (special-cases it as a sunset doc), and the launch_councils audit JSONs. All correctly cite it as "the trained-coordinator path we explored and dropped." Bulk-rewriting 14 live cross-links to "see git history" is worse than keeping the 1,500 LOC file with its existing `## ⚠️ Status: superseded by docs/spec-v1.5.md` sunset header.

  **Decision:** keep the file as-is. Its sunset header is the intended pattern for "architectural specs explicitly held back, preserved as decision history." Test sweep confirmed no stale asserts (tests/test_doc_path_consistency.py correctly skips spec-v2.md path-rename checks). This is exactly the "INVESTIGATE → keep on inspection" outcome the plan's footer warned about ("don't auto-delete unless source removal is unambiguous"). The "removable" signal in the original agent audit was a false positive.

- [ ] **D7. Investigate `tools/sync_reference_evals.py` + `data/reference_evals.json`.** Last touched May 6, no callers in src/. Either: (a) delete both if truly unused (and sunset any `tests/test_sync_reference_evals.py` / `tests/test_reference_evals.py` in same commit), or (b) wire them into the eval harness if they're the canonical reference suite the harness should compare against. Decision needs human judgment — don't auto-delete; flag with the call sites for the user.

- [ ] **D8. Decide on `docs/founder-essay-draft.md`.** Marked "Draft". Either ship it (rename, link from README, remove "draft" frame) or move to a private branch. **Test sweep:** the `TestNoUnregisteredVanityDomains` guard already references founder-essay-draft.md as a "blocked context" — if the file is renamed/moved, update that path in the guard. Don't leave half-shipped drafts in a public-launch repo.

- [ ] **D9. Consolidate `docs/scale-plan.md` (1,599 LOC) into `docs/spec-v1.5.md`.** Per agent 4: scale-plan is superseded by spec-v1.5; only one test reference. Extract the still-actionable parts into spec-v1.5 as a new section, delete scale-plan, update the test reference. **Test sweep:** `grep -rn "scale-plan\|scale_plan" tests/` — update the one reference (likely in `test_doc_count_consistency.py`) to point at spec-v1.5 instead. Net: ~1,500 LOC reduction and clearer "what spec is canonical."

- [ ] **D10. Decide on the 3-live-spec layout.** `spec-v1.md` describes what shipped, `spec-v1.5.md` is active, `spec-v1.6.md` is forward-looking. 3,718 LOC combined. Options: (a) keep all three with clearer headers ("Shipped" / "Active" / "Next"), (b) collapse v1 into a CHANGELOG appendix and keep v1.5+v1.6 as the live spec pair, (c) merge all three into a single `SPEC.md` with version sections. Pick option (b) — least churn, clearest entry point — then execute the merge. **Test sweep:** any doc-consistency guard anchored on `spec-v1.md` path must move to the new home (or delete if v1 collapses into CHANGELOG); the existing `TestV16SpecShipPlanCommitHashesResolve` class is the obvious candidate to audit.

- [ ] **T10b. Proactive test-orphan hunt** (NEW). Walk `tests/test_*.py`: for each `test_X.py`, check `src/trinity_local/X.py` (or the matching commands/ module) exists. Flag orphans (test file present, source module absent → stale test). Walk `tests/` for `import` lines referring to modules that no longer exist (use `python -c "import trinity_local.<name>"` to verify). Also check `tests/test_doc_count_consistency.py` guard list for any path that doesn't resolve. Output: a small commit-message punch list of `tests/test_X.py` files to either delete or update. Don't auto-delete unless source removal is unambiguous (e.g., the source path was removed in this same readiness pass).

## Tier 4 — Verification + close

- [ ] **V11. Re-run the 4-agent audit** (the one that produced this plan) after Tier 1-3 lands. If any new drift surfaces, append to this file as Tier 5. Otherwise: green-stamp the readiness state in `CHANGELOG.md` (`v1.7.2 — final public-readiness pass`) and `CronDelete` the loop.

## How the loop should pick the next item

1. Read this file top to bottom.
2. First `[ ]` (unchecked) item wins.
3. Do that item end-to-end (edit + test + commit).
4. Mark it `[x]` and commit the plan update in the same commit.
5. Stop. The cron will fire again with the same prompt.

When every item is `[x]`: do **V11** as the final tick, then propose `CronDelete` and stop.
