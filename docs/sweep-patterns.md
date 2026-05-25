---
class: aspirational
---

# Meta-patterns from the pre-launch consistency sweep

> Extracted 2026-05-19 from the pre-launch consistency-sweep iters,
> extended through the post-launch sweep work that's still ongoing
> (live guard count: <!-- canonical:doc_consistency_guards -->104<!-- /canonical --> in `tests/test_doc_count_consistency.py`).
> Complements claude.md's "Patterns extracted from the fixes"
> (principles #1–#21). These are doc-level meta-patterns the sweep
> surfaced that aren't yet in claude.md.

## Why a meta-patterns doc

claude.md's existing principles came from CODE fixes (basins.py truncation,
NaN poisoning, cache shape). This file collects patterns from the multi-iter
DOC sweep — pre-launch + ongoing post-launch passes. Different drift class,
different sources of truth, different fixes — worth a separate inventory.

---

## Pattern 22: Doc classification gates review intensity

Not every doc needs the same scrutiny. Four classes the sweep surfaced:

| Class | Examples | Sweep treatment |
|---|---|---|
| **Live** | README, claude.md status, launch-day/*.md, launchpad templates | Must match current state. Loud-fail any drift. |
| **Historical** | CHANGELOG entries, simplification_log.md, launch_councils/*.json | Timestamped + stale-OK per principle #8. Don't edit. |
| **Aspirational** | spec-v1.5.md, spec-v1.6.md, scale-plan.md future sections | Carry "verify against claude.md for current state" footers + inline pivot-narration callouts when reality moves past them. |
| **Reference** | schemas/*.json $id, pyproject metadata, package data manifest | Should derive from canonical source; multi-pinning is transitional. |

**Extraction:** every doc gets a class label in its front-matter or first
paragraph. The sweep can then allocate effort: 100% on Live, 0% on
Historical, focused-callouts on Aspirational, automation on Reference.

---

## Pattern 23: Pivot-narration over silent edits

When a Live or Aspirational doc needs updating to current truth, the brute
fix is to overwrite. That erases the audit trail. The sweep evolved a
better pattern in iters #70/#72/#75: inline a one-line callout naming
WHAT changed, WHEN, and WHY, with a pointer to the canonical source for
the full story.

**Template:**
```
The current X is Y. (Pivoted YYYY-MM-DD from Z — see claude.md
"## Section Name" for the full pivot narrative.)
```

**Extraction:** when editing a load-bearing claim in any spec/doc, add the
pivot callout instead of silently overwriting. Already applied in:
- spec-v1.md "## The brand" (iter #70)
- spec-v2.md v1.0 rows in version-arc tables (iter #72)
- spec-v1.5.md MCP-tool-surface "spec drift note" (iter #75)

Could be promoted to a doc-style guideline ("when updating a current-state
claim in a load-bearing spec, narrate the change inline").

---

## Pattern 24: Counterfactual-deletion check for dead code/config

For any block of config or dataclass field, ask: *"If I deleted this, what
would observably break?"* If nothing, it's dead.

The sweep caught two examples (iters #51/#52):
- `role_preferences` in config.json — loaded into `Config.role_preferences`
  but no caller indexes into it.
- `task_preferences` in config.json — same shape. Bonus: its key vocabulary
  drifted from `guess_task_type()`'s actual returns.

**Extraction:** add to the pre-launch checklist a "walk every config block +
dataclass field, ask the counterfactual" pass. Could be partially automated:
parse all `raw.get("X", default)` config-reads, cross-check against every
attribute access on the resulting dataclass. Any field loaded but never
read = candidate for deletion or sunset flag.

---

## Pattern 25: Section header vs section body drift

When the contents of a list/table change, the SECTION HEADER describing it
often doesn't. iter #61 caught:
- claude.md `### The eleven MCP tools` with 9 actual tools
- "v1.0 canonical six (lifecycle order):" followed by 5 numbered items + a gap

**Extraction:** any section header containing a number (ordinal or count)
should match the items below it. A linter could parse markdown headings,
find numeric tokens, and cross-check against the bulleted/numbered/table
content immediately below. Or: avoid numbers in section headers when the
count is mutable.

---

## Pattern 26: Numbered list gap = retirement scar

When a slot is retired from a numbered list (e.g., the v1.0 `search_prompts`
slot in claude.md MCP lifecycle), leaving the gap (1, 2, 3, [gone], 5, 6)
looks like a typo to fresh readers. Two acceptable fixes:

1. **Renumber to contiguous** (iter #61's choice) — assumes the retirement is
   recorded elsewhere (e.g., the section's bottom annotation).
2. **Explicit retirement marker** (the alternative) — keep the number but
   replace content with `4. [retired 2026-05-17 — see annotations below]`.

The choice depends on whether numbering is *positional* (sticky meaning
attached to a number, e.g., "MCP tool #4 is search_prompts") or *ordinal*
(just "the 4th item in this list"). Most lists are ordinal; renumber.

**Extraction:** treat numbered-list integrity as part of the review pass —
either renumber on retirement OR add the explicit marker, never leave gaps.

---

## Pattern 27: Past-tense vs present-tense for retired surfaces

iter #68/#69 caught MIGRATION.md saying "the note printed by `shortcut-install`"
(present, implies it still prints) when the CLI was retired pre-launch. The
same file elsewhere correctly past-tense-framed it as "if you previously ran
`shortcut-install`".

**Extraction:** when a CLI/feature retires, do a grep for its name in docs and
check the verb tense. Present-tense ("X does Y", "X prints Z") = candidate for
fix; past-tense ("X did Y", "users who ran X") = correct historical reference.

A simple guard: for each name in a "RETIRED_CLI_NAMES" list, find references
in docs/, fail if any are framed in present tense. Approximate via verb
proximity check (matches like `\b{cli_name}\b.{0,40}(is|are|prints|runs|does|registers)` flagged for human review).

---

## Pattern 28: Multi-name rename leaves wakes

Trinity has done several systemic renames during development:
- `memory/` → `prompts/` (data directory)
- `me-build` → `lens-build` (CLI)
- `persona.md` → `lens.md` (file)
- `task_kind` → `task_type` (runtime classification)
- `portal_*.py` → `launchpad_*.py` (modules)
- `member` ↔ `seat` (briefly attempted)

Each rename leaves a wake of stale references unless the sweep is
exhaustive. Iter #28 swept residual `me-build` in src/; iter #50 swept
residual `doctor` in user-facing docs; iter #29 caught `task_kinds` plural
in a test.

**Extraction:** every rename should follow a SWEEP CHECKLIST:
- src/ (Python code + comments)
- tests/ (assertion strings + test names + fixtures)
- docs/ (markdown prose + code-fenced examples)
- config.json + config.example.json (key names)
- file paths in state_paths.py + on-disk migrations
- schema $id strings
- brand-axis words (if user-facing)
- CLI `--help` text + argparse descriptions
- MCP tool descriptions
- error messages
- launch-day copy

Could be automated as a per-rename validation script: `python scripts/check_rename.py
old_name new_name` greps each surface listed and reports unswept matches.

---

## Pattern 29: Bilateral sync after duplicated artifacts

When the same file lives in N places (e.g., SKILL.md has 3 git-tracked copies:
canonical `skills/trinity/SKILL.md`, package-bundled
`src/trinity_local/data/skills/trinity/SKILL.md`, local dev convenience
`.claude/skills/trinity/SKILL.md`), the pinning test must cover ALL N copies.
iter #53 caught: iter #50 fixed only the bundled copy, missed the canonical;
`test_skill_md_synced_across_all_copies` flagged it on next run.

**Extraction:** when a file is duplicated for distribution reasons, write
the pinning test FIRST. Add to a `tests/test_duplicated_artifacts.py` family:
- Three SKILL.md copies must match
- pyproject.toml package-data manifest must match `find src/trinity_local/data/`
- claude.md "the X MCP tools" count must match `grep "name=" mcp_server.py`

---

## Pattern 30: Long-form docs accumulate drift faster than they get reviewed

scale-plan.md is ~1700 lines. Its Phase 0 status callout at the top
correctly warns readers "many later sections of this file pre-date these
changes" — but readers (including audit sweeps) often stop at the callout
and assume the rest is current.

**Extraction:** for any doc over 500 lines:
- Front-matter must declare class (Live/Historical/Aspirational/Reference)
- Sections older than the front-matter date get an inline "[historical —
  pre-dates 2026-MM-DD pivot]" prefix
- Search-and-replace operations on these docs need a "are we touching a
  pre-dated section?" sanity check

---

## Pattern 31: Tests can lock in retired behavior

iter #48 caught `test_pick_veto_fires_shortcut_url_not_just_clipboard`
PINNING the dead `shortcuts://run-shortcut?` URL fire as canonical. The
test was added in good faith (a P63 audit catch about clipboard-only
behavior) but became wallpaper after Pass B retired the dispatch path
without sweeping the test that pinned it.

**Extraction:** principle #11 ("tests must not pin broken behavior") gets
a corollary: **when retiring a feature, grep for tests pinning it BEFORE
deleting the implementation**. Otherwise tests pass against ghost code.
Approximation: when committing a `_retired_2026-MM-DD` annotation,
require a paired test change in the same commit (lint-style rule).

---

## Pattern 32: Aspirational docs need a "verify against current" footer

Forward-looking specs (spec-v1.5.md, spec-v1.6.md) drift fast as the live
product moves past their assumptions. iter #74 caught spec-v1.6.md saying
"MCP surface stays at 11" (live is 9). iter #75 caught spec-v1.5.md
listing retired `search_prompts` as "stays".

**Extraction:** every aspirational spec gets a footer pointing to
claude.md as the source of current state. Example:

```
---
**Verify against current state:** This is a forward-looking spec. Counts,
tool names, and surface lists here reflect intent at write time. For
canonical current state, see claude.md "## Status" + "## The N MCP
tools (`mcp_server.py`)" sections.
```

---

## Pattern 33: Regression guards with under-scoped allowlists

A guard exists for the load-bearing fact, but its `paths_to_scan` list
misses the most prominent surface — so a known-bad pattern silently
recurs in the un-watched doc. Post-launch tick 24 caught
`seed-from-taste-terminal --limit 10` (a command that crashes because
`--path` is required) in claude.md L830, even though
`TestNoBrokenSeedCommandInUserFacingDocs` had been catching that exact
shape across 9 other surfaces since the launch-eve sweep. claude.md
wasn't in the guard's path list.

**Symptoms:** "we already have a guard for that" + the bug still showed up.

**Extraction:** every doc-consistency guard reviews its allowlist
against the full launch-facing surface set when it's authored. Same
rule applies on every doc-list rename (e.g., new doc added →
re-audit which guards should scan it). Cheap to fix: add the path
+ an inline comment with the tick number that caught the gap, so
future readers see the scaffolding-gap shape (not just the
post-fix line in the list).

---

## Pattern 34: Canonical-renderer placeholder under-coverage

The canonical-source-of-truth renderer (scripts/render_docs.py) keeps
N surfaces auto-synced via `<!-- canonical:KEY -->VAL<!-- /canonical -->`
placeholders. Sometimes a surface carrying the same load-bearing fact
hardcodes the value instead of wrapping it in a placeholder — silent
drift opportunity when KEY changes (e.g., a new MCP tool ships and
`mcp_tool_count` bumps).

Tick 25 caught both `SKILL.md` copies hardcoding `"ships 9 MCP tools"`
when every other doc in the corpus wrapped that 9 in
`<!-- canonical:mcp_tool_count -->9<!-- /canonical -->`. The renderer's
rglob auto-scan picks up files that USE the placeholder syntax;
surfaces that don't use it are invisible to the auto-sync machinery.

**Symptoms:** a fact's canonical value changes, the renderer
re-flows 8 surfaces, two more silently stay stale.

**Extraction:** when adding a `canonical:KEY` placeholder for the
first time, grep for the literal value of KEY across the entire
repo. Any hits in user-facing docs/code that aren't in a placeholder
get either (a) wrapped in the placeholder, or (b) documented as
deliberately frozen (e.g., changelog entries reference a count at
that point in time).

---

## Patterns the sweep DIDN'T find new evidence for (but bear watching)

These appear in claude.md principles #1–#21 and continue to apply, but
the sweep didn't surface any new examples worth promoting:

- Principle #1 (lossless serialization round-trips): the basins.py
  prompt_ids cap drift class — sweep found no new examples
- Principle #6 (test fixtures must mirror production shape): no new
  examples in doc sweep
- Principle #16 (one bad value worse than zero in numerical pipelines):
  no doc-level analog observed
- Principle #18 (embedding similarity isn't structural similarity): no
  new doc-level shape

---

## How to extract these into guards

Of the 13 patterns (22–34), here's a rough ranking of extractable-now
vs. process-shift vs. tooling:

**Extractable as test guards now:**
- #25 Section header vs body — markdown linter, low effort
- #27 Past/present tense for retired surfaces — regex guard with
  RETIRED_CLI_NAMES list, low effort
- #29 Bilateral sync for duplicated artifacts — already partially
  shipped (SKILL.md test); extend to other duplicates

**Extractable as documentation policy:**
- #22 Doc classification (live/historical/aspirational/reference) — add
  to docs/CONTRIBUTING.md or front-matter convention
- #23 Pivot-narration template — promote to a CLAUDE.md principle (#33+)
- #32 Aspirational doc footers — add to spec-vN.md templates

**Process shifts (no automation needed):**
- #24 Counterfactual-deletion pass pre-launch — checklist item
- #28 Rename sweep checklist — `scripts/check_rename.py` helper
- #30 Long-form doc class declaration — checklist item
- #31 Retire-with-test-grep — commit-time discipline

**Already extracted** (after this sweep added them):
- The 4→6 surfaces agree guard (iter #67)
- The hero/sub pinning across 5 surfaces (iter #71)
- The canonical-N regression guard (iter #62)

---

*Generated 2026-05-19 after 62 numbered consistency iterations. Captured
during the pre-launch sweep so the next contributor reading this file
inherits the pattern catalog without having to re-derive it.*
