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

## Tier 1 — HIGH (fix before flipping public)

- [x] **H1. Replace `trinity.local/install.sh` vanity URL with the real one.** ✓ done in commit (see git log). Swept `docs/launch-day/01_tweet_thread.md:11,72` and `docs/launch-day/02_show_hn_post.md:19`. Extended `tests/test_doc_count_consistency.py::TestNoUnregisteredVanityDomains` to cover `docs/launch-day/*.md` (was a guard coverage gap — the same shape can't recur) and to match the bare-host form (`curl trinity.local/...`, no protocol prefix) in addition to the existing `https://` form.

- [x] **H2. Reconcile the v1.0 vs v1.7 version story.** ✓ done. Swept `docs/launch.md:90` ("v1" → "v1.7"), `docs/launch-package.md:16` (rewrote ship-window paragraph from "v1.0 lands" → "v1.7 ships"), `docs/launch-package.md:189-191` (git tag `v1.0.0` → `v1.7.0`). Updated `pyproject.toml` version `1.0.0` → `1.7.1` (matches the CHANGELOG `v1.7.1 — public-readiness pass` entry). Added new guard `test_launch_copy_pins_pyproject_minor_version` — reads pyproject's `major.minor` (e.g. `v1.7`), asserts that string appears in all 4 launch surfaces. When v1.8 lands, this fires until the launch copy is swept.

## Tier 2 — MEDIUM (cosmetic drift readers will notice)

- [ ] **M3. Pin the macOS framing.** `README.md:148` says "macOS today", `docs/launch.md:109` says "macOS-only at launch", `pyproject.toml:14-15` lists both `MacOS` AND `POSIX :: Linux` classifiers. Decision: keep "macOS today, cross-platform on the v1.5/v1.6 roadmap" (matches the existing `docs/cross-platform-spec.md`). Sweep `launch.md` to match `README.md`. Verify pyproject classifier is intentional (or drop the Linux one if not).

- [ ] **M4. Caveat the README 60-second demo's prerequisites.** `README.md:55-89` (the new two-demo block) walks `handoff` and `eval-run` but doesn't mention that both require prior `trinity-local seed-from-taste-terminal`. SKILL.md:67-73 mentions this correctly. Add one line under the demo block: *"Both demos require one prior step on first install: `trinity-local seed-from-taste-terminal --limit 1000` to index your existing transcripts. The skill walks you through it."*

- [ ] **M5. Sweep `claude.md` CLI module count + add 6 undocumented commands.** Header at `claude.md:562` says "22 modules", table actually lists 28, filesystem has 34. The 6 missing from the table are `distill.py`, `merges.py`, `stats.py`, `trust.py`, `update.py`, `vocabulary.py` — `vocabulary` and `update` are load-bearing (lens pipeline + the self-update mechanism); the rest are ancillary. Update the header to read "28 modules" and add `vocabulary` and `update` rows to the table.

## Tier 3 — DELETE / SIMPLIFY (after Tier 1+2 land)

- [ ] **D6. Delete `docs/spec-v2.md` (1,500+ LOC).** Explicitly sunset per `claude.md`. Architectural reference preserved in `docs/v2-loop-constitution.md`; git history retains it. Before delete: `grep -rn "spec-v2.md" .` — sweep any remaining live references in CHANGELOG/claude.md to either remove or annotate "sunset, see git history." Commit message should cite the sunset rationale from claude.md.

- [ ] **D7. Investigate `tools/sync_reference_evals.py` + `data/reference_evals.json`.** Last touched May 6, no callers in src/. Either: (a) delete both if truly unused, or (b) wire them into the eval harness if they're the canonical reference suite the harness should compare against. Decision needs human judgment — don't auto-delete; flag with the call sites for the user.

- [ ] **D8. Decide on `docs/founder-essay-draft.md`.** Marked "Draft". Either ship it (rename, link from README, remove "draft" frame) or move to a private branch. Don't leave half-shipped drafts in a public-launch repo.

- [ ] **D9. Consolidate `docs/scale-plan.md` (1,599 LOC) into `docs/spec-v1.5.md`.** Per agent 4: scale-plan is superseded by spec-v1.5; only one test reference. Extract the still-actionable parts into spec-v1.5 as a new section, delete scale-plan, update the test reference. Net: ~1,500 LOC reduction and clearer "what spec is canonical."

- [ ] **D10. Decide on the 3-live-spec layout.** `spec-v1.md` describes what shipped, `spec-v1.5.md` is active, `spec-v1.6.md` is forward-looking. 3,718 LOC combined. Options: (a) keep all three with clearer headers ("Shipped" / "Active" / "Next"), (b) collapse v1 into a CHANGELOG appendix and keep v1.5+v1.6 as the live spec pair, (c) merge all three into a single `SPEC.md` with version sections. Pick option (b) — least churn, clearest entry point — then execute the merge.

## Tier 4 — Verification + close

- [ ] **V11. Re-run the 4-agent audit** (the one that produced this plan) after Tier 1-3 lands. If any new drift surfaces, append to this file as Tier 5. Otherwise: green-stamp the readiness state in `CHANGELOG.md` (`v1.7.2 — final public-readiness pass`) and `CronDelete` the loop.

## How the loop should pick the next item

1. Read this file top to bottom.
2. First `[ ]` (unchecked) item wins.
3. Do that item end-to-end (edit + test + commit).
4. Mark it `[x]` and commit the plan update in the same commit.
5. Stop. The cron will fire again with the same prompt.

When every item is `[x]`: do **V11** as the final tick, then propose `CronDelete` and stop.
