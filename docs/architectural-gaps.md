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
would make ongoing consistency-sweep work UNNECESSARY for the
patterns they cover (the sweep continues iter-by-iter today — see
the live `<!-- canonical:doc_consistency_guards -->94<!-- /canonical -->` guard count in
`tests/test_doc_count_consistency.py`; each new guard is a place
where SSOT could remove the need for the guard entirely).

---

## What this analysis does NOT cover (until Round 2 below)

This was about the DOC + CONSISTENCY layer. claude.md principles #1
(serialization), #3 (boundary filtering), #16 (NaN poisoning), #18
(embedding-vs-structural similarity) are about CODE/DATA architecture
— Round 2 below addresses those.

---

# Round 2 — Architectural gaps at the code + product layer

> Added 2026-05-19 after Gaps A/B/C shipped (iter #80 + commit eb0c06d)
> and stabilized in iters #81-#83. Re-asked: "look at the meta patterns
> and claude.md's principles and see if there is a higher level
> architectural things we are missing." A/B/C were doc-layer. These
> are at the level *underneath* — code, data, runtime, product surface.

## The shape of what remains

Looking at the 32 principles + 11 patterns through the design-frame
lens again, the doc-layer gaps mapped cleanly to *put signal in its
channel*, *enforce the boundaries*, and *self-correction built in*.
What's still under-applied: *name the roles*, *cheap path = right
path*, and *narrow waist between layers* — and each of those points
at code/product architecture, not doc consistency.

Four higher gaps, ordered by Trinity-specific leverage:

---

## Gap D — User-model abstraction (Name the roles, code layer)

**Symptom:** `lens.md` + `vocabulary.md` + `topics.json` + `core.md` +
`picks.json` + the council-outcomes ledger TOGETHER form the user's
model — Trinity's representation of who the user is. But no code
entity declares this. Every consumer (`chairman_runtime`,
`consolidate`, `chairman_picker`, the launchpad's lens card)
reaches into the lens hierarchy separately.

**Underlying issue:** The user-model is doing structural work
(conditioning every council, weighting every routing decision) but
exists only as a *convention* across files.

**What's missing:** A named `UserModel` (or `Lens` / `Twin`)
abstraction:

```python
# src/trinity_local/user_model.py (hypothetical)
class UserModel:
    """Trinity's representation of the user — lens + vocab + topics +
    core + picks + outcome ledger. Single import point for everything
    that conditions on user state."""

    def __init__(self, home: Path = trinity_home()): ...
    def conditioning_prompt(self) -> str: ...  # what chairman reads
    def apply_to(self, prompt: str) -> EnrichedPrompt: ...
    def update_from(self, outcome: CouncilOutcome) -> None: ...
    def freshness(self) -> dict[str, datetime]: ...
    def health(self) -> UserModelHealth: ...
```

Today: 6+ files are read separately by different callers; each can
drift in how it loads, what it caches, and what fields it expects.

**Why this matters architecturally:** The user-model IS the
product. "Your taste, ported" is a claim about a thing — and that
thing should have a name in code, not just in marketing.

---

## Gap E — Product-loop abstraction (Narrow waist, runtime layer)

**Symptom:** Trinity's product loop is:

```
ask question → dispatch council → chairman synthesizes →
user verdict (13% of the time as of 2026-05-20; was 16% pre-nudge) → cortex consolidates →
picks update routing → next ask is better
```

This loop IS the moat. But it's not represented in code. Each stage
is independent. The 13% verdict-capture rate (4/31 on the dev
install; was 3/19 = 16% pre-nudge; task #110) is the
only loop-health metric — and it requires hand-aggregation from
`council_feedback.jsonl`.

**Underlying issue:** The loop is a *concept* in claude.md's
"Forward arc" + the launchpad's routing card, but it's not a
*structure*. Loop health isn't measured at the stage level
because there's no stage-aware abstraction.

**What's missing:** A `ProductLoop` (or `MoatLoop` /
`SupervisionSignal`) abstraction that:
- Names each stage as a phase with a transition function
- Exposes metrics per stage: `verdict_capture_rate`,
  `consolidation_lag_days`, `picks_freshness_days`,
  `routing_coverage_pct`
- Surfaces them on the launchpad as a single "loop health" card
- Triggers alerts when any stage stalls

**Why this matters architecturally:** Until the loop is structural,
"improve verdict capture" is a vague ask. Once the loop is a named
thing, "stage 3 conversion rate is 13% (was 16% pre-nudge), target 50%" becomes a
ratchetable goal. Right now the loop is invisible to the dashboard
that's supposed to measure it.

**Concrete first step:** A `LoopHealth` dataclass + a launchpad card
that reads it. ~3h. Closes the "what's the moat's actual
throughput?" question structurally.

---

## Gap F — Provider protocol (Narrow waist, boundary layer)

**Symptom:** 3 providers (claude, codex, antigravity), 3 subprocess
wrappers in `providers.py`, no unifying interface. Each wrapper:
parses CLI args differently, handles errors differently, normalizes
output differently. Tier-equivalence invariant (cosine ≥ 0.9999
between backends) is asserted in docs but only partially tested.

**Underlying issue:** "A provider" is doing role work but isn't
expressed as a protocol. Each provider's behavior drifts from the
others silently — anyone adding a 4th (mlx, ollama, future Phi-4)
has to copy-paste-modify.

**What's missing:** A `Provider` protocol (Python's
`typing.Protocol`):

```python
class Provider(Protocol):
    name: str
    role: ProviderRole  # frontier / local / experimental

    def dispatch(
        self, task: str, context: ProviderContext
    ) -> ProviderResponse: ...

    def healthcheck(self) -> ProviderHealth: ...
    def cost_estimate(self, task: str) -> CostEstimate: ...
```

`ProviderResponse` becomes a canonical shape (text, tokens, latency,
cost, errors). Every council member returns this shape; every
chairman synthesizer reads it. New providers implement the
protocol.

**Why this matters architecturally:** Trinity's wedge is
cross-provider observation. The protocol IS where the cross
happens. Without a named protocol, "cross-provider" is a
convention; with one, it's a contract.

---

## Gap G — Event log vs derived state (Self-correction, data layer)

**Symptom:** Council outcomes are written once + later mutated
(CLI `council-rate` sets `outcome.metadata.user_verdict` retroactively;
the prior MCP `record_outcome` tool wrote the same mutation until
retired 2026-05-21).
The personal routing table is *computed on demand* from outcomes —
but the outcomes themselves are *both* event records *and* mutable
state.

**Underlying issue:** The principle is "council outcomes is the
canonical store" — but the mutation pattern means outcomes drift if
the verdict-write fails partway, or if the user changes their
verdict later (no revision history).

**What's missing:** Separate the immutable EVENT LOG from the
DERIVED STATE:

- `council_runs.jsonl` already exists as the event log. Extend to
  include verdict events as separate immutable rows
  (`{event: "verdict_recorded", council_run_id: X, winner: Y,
   timestamp: Z}`).
- `council_outcomes/*.json` files become *projections* of the
  event log up to a given point. Re-derive at read time.
- `compute_personal_routing_table()` already projects from
  outcomes; instead, project from the event log directly.

**Why this matters architecturally:** Today a partial verdict-
write or a future-revision use case creates a silent inconsistency
between the outcome JSON and the feedback JSONL. With event-sourced
state, the JSONL IS the truth and any projection is auditable +
rebuildable.

**Why deferred:** This is the biggest architectural change of the
four. Event-sourcing is a significant refactor (~2 weeks). The
current mutate-then-rebuild approach works for v1.0; the gap
becomes load-bearing only when verdict-revision is a feature.

---

## Ordering for v1.7.5+ if these are adopted

Same triage shape as Round 1 (cost vs leverage):

1. **Gap E (product-loop abstraction)** — highest Trinity-specific
   leverage. Closes the verdict-capture measurement gap (13% at
   n=31 as of 2026-05-20)
   structurally. ~3h for the first cut (LoopHealth dataclass +
   launchpad card). Unblocks "is verdict capture improving?" as
   a first-class question.

2. **Gap D (user-model abstraction)** — medium cost (~1 day),
   medium leverage. Mostly mechanical refactor: extract a
   `UserModel` class, route all 6+ existing lens-readers through
   it. Pre-condition for any future feature that wants to query
   the user-model holistically (e.g., a "what's the user's
   COMPRESSION rate this month" surface).

3. **Gap F (provider protocol)** — medium cost (~1 day), defensive
   leverage. Catches silent drift between providers + makes adding
   ollama/mlx/local-models cheaper. Doesn't change product
   behavior; structures what's already there.

4. **Gap G (event-sourced outcomes)** — biggest cost (~2 weeks),
   contingent leverage. Defer until verdict-revision becomes a
   feature OR until a real inconsistency bites.

## How Round 2 relates to Round 1

Round 1 (Gaps A/B/C, shipped) was DOC ↔ CODE consistency. Round 2
(Gaps D/E/F/G, hypothetical) is CODE ↔ CODE structure. The pattern
that recurs: Trinity has STRONG discipline (the 32 principles +
guards) and WEAK structure (named abstractions for the things
discipline protects).

The framework's deeper point — *behavior is not goal-driven, it's
a structural affordance* — applies just as much to contributors
working with the codebase as to users facing the UI. If
"add a new provider" is a copy-paste exercise (today), drift is
the default. If it's "implement Provider protocol" (Gap F), drift
is structurally prevented.

---

*Round 2 generated 2026-05-19 after Gaps A/B/C stabilized through
iters #81-#83. Companion to design-frame.md (which named the 6
framework bullets) and architectural-gaps.md Round 1 above. Treat
this as the next-frontier list: not blocking for v1.7.4 launch,
but the most leverage-able post-launch architectural moves.*
