---
class: aspirational
---

# Architectural gaps surfaced by the 62-iter doc sweep

> Higher-level observations from looking at claude.md's principles #1–#21
> + sweep-patterns.md #22–#32 together. What classes of problem does the
> overall pattern catalog point at? What architectural pieces are missing
> that would prevent whole CATEGORIES of these patterns rather than
> catching them one-by-one with guards?

---

## The shape underneath the principles

If you cluster the 32 principles by what they're actually protecting
against, three load-bearing themes emerge:

**Cluster 1 — Duplicated truth, kept in sync by agreement guards.**
Principles #8, #20, #25, #26, #29, #32. The 6-surfaces-agree test count.
Hero/sub pinned across 5 surfaces. SKILL.md replicated 3-way. MCP tool
count claimed in 6 places. Section headers vs section bodies.

**Cluster 2 — Retirement as narrative-only event.**
Principles #11, #27, #31. plus the iter #48/#68/#69 catches.
"Retirement" of a CLI / MCP tool / brand axis is recorded in:
prose comments, module docstrings, claude.md status, simplification_log
entries. None of these talk to each other. Tests have to re-discover
"X was retired" via grep + human review.

**Cluster 3 — Doc class not declared, all docs treated equally.**
Principles #22, #30, plus the implicit pattern across the whole sweep.
The sweep treated all 65 markdown files the same way. But the actual
surfaces matter: README, launch-day, claude.md, SKILL.md, T-0 runbook.
Everything else is secondary or historical. Without explicit class
declarations, sweep effort goes to noise + signal in equal measure.

---

## The architectural gap each cluster points at

### Gap A — No canonical-source-of-truth → derived-artifact pipeline

**Symptom:** Multi-surface agreement guards. TestTestCountConsistency went
4 → 6 surfaces in iter #67; adding a 7th means 21 pair-relations. The
6-surface lock is O(N²) where N is the number of places a number is
duplicated.

**Underlying issue:** Docs are static markdown with hand-pinned counts,
version strings, hero text, MCP tool names. The test count, guard count,
MCP tool count, version, and hero text all exist in data already
(pytest output, mcp_server.py, pyproject.toml, claude.md status block).
But docs don't derive from those — they re-state them by hand.

**What's missing:** A build-time doc templating step. Something like:

```python
# scripts/render_docs.py
CANONICAL = {
    "test_count": int(subprocess.run(["pytest", "--collect-only", "-q"]).stdout.split()[-2]),
    "guard_count": count_doc_guards("tests/test_doc_count_consistency.py"),
    "mcp_tool_count": len(parse_mcp_tools("src/trinity_local/mcp_server.py")),
    "version": parse_pyproject_version("pyproject.toml"),
    "hero": read_status_block_hero("claude.md"),
}

# Then docs use {{test_count}} placeholders that get expanded at
# pre-commit or CI render time.
```

**Concrete first step:** Pick one fact (test count) and migrate the 6
surfaces to use a placeholder. Pre-commit hook reads `pytest --collect-only`,
templates the number in, commits. The 6-surfaces-agree guard becomes
"verify the placeholder expanded correctly" — single source, single check.

**Why this matters architecturally:** every claude.md principle about
duplicated facts (#8, #20, #25, #26) becomes a no-op once the canonical
source is the only place the number lives. The current "lots of guards
catching divergence" pattern is a workaround for not having this layer.

---

### Gap B — No retirement registry as code

**Symptom:** Retirement is narrated everywhere, declared nowhere.
`shortcut-install` retirement (commit 53db635, 2026-05-17) is narrated in:
- claude.md "## Forward arc" section
- docs/MIGRATION.md (multiple places, sometimes contradictory — iter #68/#69)
- docs/simplification_log.md (Pass A entry)
- memory_viewer.py inline comment (iter #48)
- src/trinity_local/state_paths.py:99 comment

Five separate narrations of the same event. iter #68/#69 caught
MIGRATION.md internally contradicting itself ("keep shortcut-install"
vs "the CLI no longer exists" 20 lines apart). The narration doesn't
talk to itself.

**Underlying issue:** "X was retired" is a structured fact (name, date,
commit, replacement, reason) but Trinity stores it as unstructured prose.

**What's missing:** A retirement registry.

```python
# src/trinity_local/retired_names.py
RETIRED: dict[str, RetirementRecord] = {
    "shortcut-install": RetirementRecord(
        retired_at="2026-05-17",
        commit="53db635",
        replacement="install-extension",
        reason="Chrome extension is the cross-platform dispatch path",
        artifact_persists=True,  # macOS Shortcut on existing installs still works
    ),
    "search_prompts": RetirementRecord(
        retired_at="2026-05-17",
        commit="...",
        replacement="substring + recency + replay-value heuristics",
        artifact_persists=False,
    ),
    # ... etc
}
```

Then:
- Docs query the registry at render time ("for retired CLIs, get the
  retirement date inline")
- Tests grep for present-tense references to keys (sweep pattern #27 as
  automated guard)
- `trinity-local <retired-cli>` shows a friendly migration message
  ("`X` was retired on YYYY-MM-DD — use `Y` instead") rather than
  "unknown command"
- A regression-guard `test_no_present_tense_for_retired_names` runs on
  every commit

**Why this matters architecturally:** retirement isn't a one-shot event
that you narrate and forget — it's an ongoing constraint (don't
re-introduce the name, don't write present-tense docs about it, don't
re-add the test that asserted it worked). A registry makes the constraint
queryable. Without one, every retirement leaks into the codebase via
N independent prose-mentions that drift.

---

### Gap C — No doc-class frontmatter

**Symptom:** Every doc was treated as equally authoritative during the
sweep. Effort went to roadmap docs that are intentionally stale
(scale-plan.md historical sections) alongside launch-day docs that are
load-bearing today. The implicit hierarchy lived in my head, not the
docs.

**Underlying issue:** Sweep pattern #22 named four doc classes
(live/historical/aspirational/reference) but they're not declared in
the docs themselves. A future contributor running the same sweep can't
know which docs to focus on without reading every file's framing.

**What's missing:** YAML frontmatter on every doc declaring its class
+ canonical-source references.

```yaml
---
class: live
canonical_for: [test_count, guard_count, mcp_tool_count]
verify_against: code
---
```

```yaml
---
class: aspirational
verify_against: claude.md "## Status"
last_synced: 2026-05-19
---
```

```yaml
---
class: historical
snapshot_date: 2026-05-16
do_not_edit: true
---
```

Then:
- Markdown linter reads frontmatter, applies different validation per class
- `class: live` docs must match canonical sources (extends existing guards)
- `class: aspirational` docs get auto-inserted "verify against current"
  footers
- `class: historical` docs are read-only (any edit triggers a warning)
- Future sweeps allocate effort by class

**Why this matters architecturally:** doc class is a property of the
DOC, not the sweep. Encoding it makes the property queryable +
enforceable. Currently a fresh sweeper has to re-derive "scale-plan.md
historical sections shouldn't be edited" from the Phase 0 status callout
+ reviewer intuition.

---

## Why these three gaps, not the other 29 patterns?

The 32 principles are mostly LOCAL fixes — each protects against a
specific drift shape. Gap A/B/C are STRUCTURAL — each prevents whole
CATEGORIES of drift that the principles individually catch one-at-a-time.

| Local pattern | Structural fix |
|---|---|
| #8, #20, #25, #26 (numeric/duplicated fact drift) | Gap A (doc renderer) |
| #11, #27, #31 (retirement-related drift) | Gap B (retirement registry) |
| #22, #30 (doc class + size drift) | Gap C (doc frontmatter) |

The other principles cluster into validation discipline (#5, #14, #19,
#21), boundary discipline (#3, #16), and audit-for-shape methodology
(#4, #17). Those are operating-mode practices, not architectural pieces.
Gaps A/B/C are missing architectural pieces; the operating-mode practices
will keep being needed regardless.

---

## Concrete ordering for v1.7.5

If we ship one of these post-launch, in what order?

**1st: Gap C (doc frontmatter)** — lowest cost, immediate signal.
Add `class:` to every md file in 30 minutes; markdown linter to enforce
is another hour. Doesn't change any user-facing behavior; just makes the
implicit class declaration explicit.

**2nd: Gap B (retirement registry)** — medium cost, high signal. ~3
hours: define the dataclass, populate from existing retirements (about 15
of them in simplification_log.md), wire `trinity-local <retired-cli>`
friendly-error, write the present-tense regression guard. Closes the
class of drift iter #68/#69 caught most painfully.

**3rd: Gap A (doc renderer)** — highest cost, biggest payoff. ~6 hours
to template the 6-surface test count fact + verify pre-commit hook works.
After that, each new derived fact (MCP count, version, hero) is ~30
minutes to add. Eventually the 6-surfaces-agree guard becomes a "the
template expanded correctly" assertion.

All three are post-launch. Today's discipline (multi-surface guards +
grep + reviewer attention) is functional; these architectural pieces
would make the next 62 iters of consistency work UNNECESSARY for the
patterns they cover.

---

## What this analysis does NOT cover

This is about the DOC + CONSISTENCY layer. claude.md principles #1
(serialization), #3 (boundary filtering), #16 (NaN poisoning), #18
(embedding-vs-structural similarity) are about CODE/DATA architecture.
Those gaps would need a separate analysis (e.g., "do we have a
boundary-validation layer? a type-system for numeric pipelines?").
The 3 gaps here are scoped to what the doc-sweep surfaced.

---

*Generated 2026-05-19 after iter #76. Companion to docs/sweep-patterns.md
(the 11 doc-level meta-patterns) and claude.md's principles #1-#21
(the code-level principles).*
