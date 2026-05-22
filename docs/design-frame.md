---
class: aspirational
---

# A design frame for Trinity's drift-resistance work

> Applied to Trinity 2026-05-19 after iter #77's architectural-gaps
> analysis. The user surfaced a design framework that re-frames the
> sweep work — and the product itself.
>
> *"It's a design problem, not a prediction problem. Behavior is not
> goal-driven, it's a structural affordance."*
>
> *How to get there: name the roles · enforce the boundaries · put
> signal in its channel · cheap path = right path · narrow waist
> between layers · self-correction built in.*

---

## Why this framework illuminates Trinity specifically

The 62-iter consistency sweep + the 32 principles in
`claude.md` + `sweep-patterns.md` are all PREDICTION work: "this drift
shape recurred; add a guard so we'll catch it next time." The 3
architectural gaps in `architectural-gaps.md` are DESIGN work:
"restructure so the drift can't occur."

The framework gives ideological grounding to that distinction. Below,
each of the six "how to get there" bullets mapped to Trinity:

---

## 1. Name the roles

Trinity has named most of its load-bearing roles well: **chairman**,
**member**, **lens**, **cortex**, **conductor** (v1.5 future). The
glossary in `claude.md` does this work.

Where naming hasn't quite landed:
- **`task_type`** is a label that's doing ROLE work (it's the closed-set
  vocabulary the routing table indexes on, the cortex indexes on, the
  guesser emits) but it READS like a tag. iter #92 unified
  `task_kind` → `task_type` but the role itself stays implicit. A
  `RoutingDimension` named type with finite enum would name the role.
- **`user_verdict`** is the load-bearing signal — Trinity's moat —
  but it lives as a field on `CouncilOutcome.metadata`, not as a
  named entity. The "personal ledger" framing in marketing copy is
  more legible than the code's nested-dict representation.
- The **CONDUCTOR** role is named in v1.5 spec but doesn't exist in
  code yet. Naming-without-implementation is a different failure mode
  than implementation-without-naming.

**Architectural extraction:** name reviews are cheap. Once a quarter,
walk every concept that does work in the code and ask "is it named?
is the code name the same as the doc name?" Trinity does this well
on the user-facing terms (chairman, member); could do better on the
infrastructure terms (task_type, verdict, ledger).

---

## 2. Enforce the boundaries

claude.md principle #3 ("filter at the boundary, not the consumer")
already names this. Trinity's known boundaries:

| Boundary | Enforced? |
|---|---|
| User input ↔ Trinity's own dispatch prompts | ✅ `_is_user_facing_prompt` in ingest.py |
| Embedding cache ↔ downstream pipeline | ✅ NaN-poisoning gate (principle #16) |
| Code state ↔ docs about it | ❌ Gap A (no canonical-source renderer) |
| Live names ↔ retired names | ❌ Gap B (no retirement registry) |
| Live docs ↔ historical docs | ❌ Gap C (no doc-class frontmatter) |
| MCP tool surface ↔ harness expectations | ⚠️ partially (Tool() registrations canonical; doc claims pinned via 6-surfaces guard) |

The pattern: boundaries that exist as INTENT but not as ENFORCEMENT
keep leaking. The 62-iter sweep is the cost of intent-without-enforcement
at five of those boundaries.

---

## 3. Put signal in its channel

Each kind of signal should live in ONE place; everything else derives.

| Signal | Canonical channel | Re-stated in N places (currently) |
|---|---|---|
| Test count | `pytest --collect-only` | 6 doc surfaces |
| MCP tool count | `mcp_server.py` Tool() registrations | 4 doc surfaces |
| Version | `pyproject.toml` `version` | 3 doc surfaces |
| Brand hero | claude.md status block | 5 doc surfaces (pinned) |
| Retirement of X | scattered prose across 5+ files per retirement | undefined |
| User preference signal | `~/.trinity/council_outcomes/*.json` | derived everywhere (good) |

The 4 right-most rows are mixed: some derive, most restate. Gap A
(doc renderer) is literally "put signal in its channel". Once shipped,
the 6-surfaces-agree guard becomes a "did the template expand
correctly" assertion — not a multi-surface agreement check.

The product-side analog: the user's preference signal IS in its
channel (`~/.trinity/council_outcomes/`). Every downstream consumer
(personal routing table, chairman picker, picks.json) derives from
that one source. The product's wedge depends on this discipline; the
docs/code situation should match it.

---

## 4. Cheap path = right path

This is the most under-applied bullet at Trinity, and it's where the
framework points hardest.

**At the product level:**
- Cheap path after a council: **close tab**. Right path: **record_outcome**.
  The 13% verdict capture rate (4/31 on the dev install as of
  2026-05-20; was 3/19 = 16% pre-nudge; task #110) is the cheap path
  winning — the active-nudge mechanism shipped but the proportion
  hasn't moved meaningfully at n=31.
  Until the launchpad redesigns the council-result page so the
  rate-the-winner button is the MOST PROMINENT action (and closing
  costs an extra click), the gap won't close. Note: this isn't a
  user-education problem; it's a structural-affordance problem.
- Cheap path to install: `pip install trinity-local` (doesn't exist
  on PyPI yet) OR `curl install.sh | bash`. Both still require
  reading instructions. Right path: `/trinity` slash command from
  inside Claude Code — and that DOES work today, but the user has
  to know it exists. The bundled SKILL.md is the structural affordance
  that makes `/trinity` the cheap path.

**At the contributor level:**
- Cheap path when retiring a CLI: comment "retired", delete the
  argparse registration, commit. Right path: update registry, sweep
  doc references, add a present-tense guard, document the workaround
  for existing users. The 32 principles + 11 patterns are the cost
  of cheap-path-being-wrong-path at the contributor level. A
  `scripts/retire_cli.py NAME --replacement Y --reason "..."` helper
  would make the right path cheaper than the cheap path.
- Cheap path for a doc change: edit the markdown directly. Right
  path: edit the markdown, search-and-replace any duplicates, run
  the doc-consistency tests. iter #63 (sync 1294 → 1296 across 4
  surfaces) was the cost. Gap A makes this O(1) instead of O(N).

**The recurring pattern:** Trinity has good DISCIPLINE around right
paths (the 62-iter sweep, the <!-- canonical:doc_consistency_guards -->94<!-- /canonical --> guards) but weak STRUCTURE that
makes them cheap. Discipline scales with attention; structure scales
with itself.

---

## 5. Narrow waist between layers

Trinity has good narrow-waist instinct in several places:

| Waist | Above | Below |
|---|---|---|
| `~/.trinity/` schema | Launchpad UI, MCP server, CLI | Storage primitives (JSON, JSONL, npy) |
| `CouncilOutcome` schema | Personal routing table, picks.json, eval harness | Raw provider responses |
| `lens.md` | Chairman prompts (3 providers consume it) | Stage 0-4 pipeline |
| MCP tool surface (<!-- canonical:mcp_tool_count -->8<!-- /canonical --> tools) | Claude Code, Codex, Antigravity, Cursor harnesses | Trinity's internal council/picks/lens logic |

These are intentionally simple + stable. The narrow waist Trinity is
MISSING:

- **A canonical-fact channel** between code and docs. Gap A names it.
  Until shipped, every duplicated fact (test count, MCP count,
  version) is N=2 to N=6 sources that all have to agree.
- **A retirement-state channel** between past and present. Gap B
  names it. Currently retired-state lives as prose across 5+ files
  per retirement.

The framework's bullet says: identify your narrow waist, MAKE SURE
IT'S NARROW, make sure everything depends on it (derives) rather
than restates it. Trinity has narrow waists at the data layer; the
doc layer doesn't yet.

---

## 6. Self-correction built in

claude.md principle #14 ("every shipped feature gets a smoke regression
guard within one tick") is self-correction discipline at the CATCH
level. The <!-- canonical:doc_consistency_guards -->94<!-- /canonical --> doc-consistency guards are self-correction at the test
level. Browser smoke is self-correction at the visual level.

What's missing at the AUTOMATIC-FIX level:
- Numeric drift across 6 surfaces is currently caught by guards but
  fixed by hand (iter #63: 4 manual edits). Gap A would make this
  auto-fix.
- Brand hero pivots across 5 surfaces are currently caught + manually
  swept (iter #70/#71/#72/#73). A canonical-hero source + template
  would auto-propagate the pivot.
- Retired CLI strings in docs are currently caught by
  `TestNoRetiredCliInSrcQuotedStrings` but only locked, not corrected.
  A `RETIRED_NAMES` registry + auto-suggestion linter could rewrite
  "use `me-build`" → "use `lens-build` (formerly `me-build`)" on
  detection.

**The right level of self-correction is debatable:** auto-fix can mask
intentional regressions. But for purely-derived facts (counts,
versions), auto-fix is strictly safer than auto-detection-only.

---

## What this framework adds beyond the existing principles

claude.md's 32 principles + sweep-patterns.md's 11 are inductive
("we kept seeing this; here's the pattern"). The 6-bullet framework
is deductive ("structure causes behavior; here's the structural
template").

The most valuable bullets for Trinity right now:
1. **Cheap path = right path** — applies at the product level
   (verdict capture rate, install discoverability), the contributor
   level (retire-CLI helper, doc-render helper), and the docs level
   (canonical-source pipeline).
2. **Put signal in its channel** — this IS Gap A from
   architectural-gaps.md. The framework gives it a name.
3. **Self-correction built in (auto-fix, not auto-detect)** — extends
   the existing guard discipline from CATCHES to CORRECTIONS.

The other 3 bullets (name the roles, enforce the boundaries, narrow
waist) Trinity already does reasonably well — the framework reinforces
them but doesn't surface new work.

---

## Concrete v1.7.5 additions if we adopt the frame

1. **Build the canonical-source renderer first** (Gap A) — this is
   "put signal in its channel" + makes "cheap path = right path" for
   contributors. Highest leverage from the framework.

2. **Redesign the council-result page so rate-the-winner is the
   cheapest action** — this is "cheap path = right path" applied at
   the product level. Closes the verdict-capture-gap problem (13%
   at n=31; was 3/19 = 16% pre-nudge)
   structurally instead of with reminders.

3. **`scripts/retire_cli.py` helper** — "cheap path = right path" for
   contributors. The right path becomes a one-liner.

4. **Auto-fix mode in doc-consistency guards** (`pytest
   --auto-fix`) — "self-correction built in". For purely-derived
   facts (counts, versions), the guard rewrites the doc when wrong.

These four shift the work from PREDICTION (we'll catch it next time)
to DESIGN (it can't happen). The 62-iter sweep then becomes the
LAST sweep, not the first of a recurring pattern.

---

*Generated 2026-05-19 in response to the user's design-frame question.
Companion to architectural-gaps.md (which named the 3 gaps); this doc
maps the framework to those gaps + the product-level UX work that
shares the same shape.*
