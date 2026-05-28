---
class: aspirational
---

# Lens redesign — robust lenses that stand the test of time

Design doc. Goal stated by the user: **build lenses that represent me
and stand the test of time.** This evaluates the entire lens pipeline
against that goal, identifies the one structural gap, and specifies the
change — including where #182 (trajectory lens) plugs in.

Status: design only. Nothing here is built. Supersedes the standalone
#182 plan, which this folds into a larger picture.

## The goal, made falsifiable

"Robust + stands the test of time" decomposes into four testable
properties a lens should have:

1. **Stability** — the lens doesn't swing between rebuilds. Two
   rebuilds a day apart over the same corpus produce ~the same lens.
2. **Accretion** — confirming evidence *strengthens* a tension; it
   doesn't just re-derive it from scratch each time.
3. **Graceful decay** — a tension that stops being supported fades
   over time rather than vanishing on the first rebuild that misses it.
4. **Provenance** — every tension traces to the evidence that supports
   it, with a confidence the chairman can weigh.

The current pipeline has (4) and partially (1-via-the-≥3-basin-rule).
It fails (2) and (3) outright, and (1) is fragile — demonstrated this
session: one chairman run produced **0 tensions**, another produced 3.

## The one structural gap: the lens is stateless

Today `lens-build` is a pure function of `(current corpus, a stochastic
chairman)`, regenerated from zero each run. `save_lenses` overwrites
`lenses.json` wholesale. A LensPair carries no identity across rebuilds,
no support score, no last-confirmed timestamp. Consequences:

- A tension the chairman misses this run **vanishes** — no memory it
  was strongly supported last week.
- A single bad chairman call can **reshape the whole lens** (we watched
  it zero out; the #194 clobber guard catches only the all-empty case,
  not subtler drift).
- There is **no decay curve** — it's all-or-nothing per rebuild.

The irony: the accumulator primitive we want is the Beta-Binomial
posterior we *deleted* with the moves substrate (#184). We removed it
from the layer that didn't need it (moves — the chairman derives those
at inference time) when the layer that genuinely needs it is **the lens
itself**.

And the substrate is already half-there: `merges.jsonl` is an
append-only ledger of "every user-expressed-preference act" (turn-pair
overwrites, council winners, cortex overrides). **lens-build writes to
it but never reads it back.** The durable evidence is being recorded and
ignored.

## The design principle

> The lens is a **slowly-evolving accumulator**, not a per-run redraw.
> Each rebuild proposes *candidate* tensions; a reconcile step matches
> them against the existing lens and updates confidence — reinforce on
> confirmation, decay on absence. `merges.jsonl` is the durable evidence
> ledger that survives any single rebuild.

This is the seed-kernel recursion applied where it belongs: "evidence
reinforces, absence decays," on the lens.

## Every stage, evaluated against the goal

| Stage | Today | Keep / Change | Why |
|---|---|---|---|
| **0 — turn-pair rejections** | Chairman extracts REFRAME/REDIRECT/COMPRESSION/SHARPENING; now chunked (#195) | **Keep**, but append each kept signal to `merges.jsonl` with a timestamp (already happens) | Rejections are raw evidence — they belong in the durable ledger, not just the rebuildable rejections.jsonl |
| **1 — basins** | k-means topology, 20 basins | **Keep** — but pin basin identity (see Risk 1) | Basins are the semantic coordinate system tension-identity matching relies on; they must be stable across rebuilds |
| **2 — decisions** | Chairman extracts privileged/sacrificed | **Keep** as extraction | Decisions are evidence; unchanged |
| **3 — pair-mining** | Chairman proposes paired tensions | **Reframe**: output is *candidate* tensions, not "the lens" | The chairman proposes; the accumulator disposes |
| **4 — basin post-filter (+T2)** | ≥3-basin count + cosine membership | **Keep** as the gate on candidates | A candidate must still clear the structural bar before entering reconcile |
| **4.5 — reconcile (NEW)** | — | **Add**: match candidates to existing lens by semantic identity; reinforce / add-provisional / decay | This is the load-bearing new stage — turns the lens from stateless to accumulating |
| **5 — distill (core.md)** | Reads tensions | **Change**: read *high-support* tensions first | The distillation should reflect the durable core, not this-run's noise |
| **2.5 — vocabulary** | Homonyms/synonyms | **Keep** — and use it in 4.5 identity matching | Two phrasings of one tension ("refine"/"tighten") must resolve to one identity; vocabulary is that bridge |

## The new accumulation primitive (Stage 4.5)

**Tension identity.** The chairman phrases the same tension differently
across runs ("mechanism inspection ↔ speculative inference" one day,
"rigor ↔ speed" another). Surface-hashing won't match. Use **semantic
identity**: a candidate matches an existing tension if
`cosine(probe(candidate), probe(existing)) ≥ MATCH_THRESHOLD` (~0.80).
This is the same T2 embedding primitive from #186 — recursion again, the
embedder bridging two phrasings of one idea. (Requires MLX; under TF-IDF
fall back to surface-pole overlap — see #185's lesson.)

**Support state per tension** (new fields on the persisted lens entry):
- `tension_id` — stable, assigned on first appearance.
- `alpha` / `beta` — Beta-Binomial. `alpha++` each rebuild that
  reconfirms (a candidate matches); `beta++` each rebuild that runs but
  *doesn't* reconfirm. `support = alpha / (alpha+beta)`.
- `first_seen` / `last_confirmed` — timestamps for the decay clock.
- `basins_spanned` — as today, but unioned across confirmations (a
  tension's basin coverage *grows* as new evidence lands).

**The reconcile algorithm** (deterministic, no LLM):
```
for candidate in stage4_accepted:
    match = best_existing_tension_by_cosine(candidate, existing_lens)
    if match and cosine >= MATCH_THRESHOLD:
        match.alpha += 1
        match.last_confirmed = now
        match.basins_spanned |= candidate.basins_spanned
    else:
        add candidate as provisional (alpha=1, beta=0, first_seen=now)
for tension in existing_lens not matched this run:
    tension.beta += 1                      # ran, didn't reconfirm
# promotion / demotion by support + recency
for tension in lens:
    if support(tension) >= ACTIVE_FLOOR and recent(last_confirmed):
        tension.status = "active"          # rendered in lens.md
    elif support(tension) < DORMANT_FLOOR or stale(last_confirmed):
        tension.status = "dormant"         # kept, not rendered (revivable)
```

**Decay policy.** Dormant ≠ deleted. A tension that drops below
`DORMANT_FLOOR` or hasn't been confirmed in N rebuilds / M days moves to
`dormant` — preserved (like the moves archive was) so a later run can
revive it, but excluded from the rendered lens + chairman context. This
gives the graceful decay property without losing history.

**Stability falls out for free**: a single bad chairman run now
`beta++`s the unconfirmed tensions slightly — it can't *erase* them.
Reshaping the lens requires *sustained* absence across many rebuilds.

## Where #182 (trajectory lens) plugs in

#182's arc-pairs become **another candidate source feeding the same
Stage 4.5 reconcile.** The recursive design from the earlier sketch
still holds (arc = sequence of synchronic rejections in one thread,
mined by the existing Stage 3 primitive). The only change: arc-derived
candidates don't get their own storage or gate — they flow into the
accumulator alongside synchronic candidates and earn support the same
way. A diachronic tension that recurs across threads accrues support
and goes active; one seen once stays provisional and decays.

This is why #182 *should not* ship before the accumulator: built the
old from-scratch way, a trajectory lens is just as fragile. Built on the
accumulator, it's durable by construction.

## Build sequence (proposed)

1. **Lens accumulation core** — add `tension_id` + `alpha`/`beta` +
   `first_seen`/`last_confirmed`/`status` to the lens entry; the Stage
   4.5 reconcile step; render only `active` tensions to lens.md with
   their support score. Wire `merges.jsonl` as the read-back evidence
   source. (This is the load-bearing change.)
2. **Migration** — existing 3-tension lens.md → seed the accumulator
   with `alpha=1` each (provisional), so the first reconciled rebuild
   reinforces rather than replaces.
3. **#182 trajectory arc-pairs** — as a candidate source into 4.5.
4. **Decay tuning** — pick ACTIVE_FLOOR / DORMANT_FLOOR / staleness
   window from real rebuild cadence (needs a few real rebuilds to
   calibrate — same "run on real data" discipline this session kept
   proving).

## Risks / open decisions

1. **Basin identity across rebuilds.** Stage 4.5 identity matching
   leans on basin centroids being stable. k-means with a fixed seed is
   *mostly* stable but not guaranteed as the corpus grows. If basins
   drift, tension-basin links rot. Mitigation: match tensions by
   *probe-text cosine* (basin-independent) as the primary key; treat
   basins_spanned as evidence, not identity. (Already the plan above.)
2. **MATCH_THRESHOLD calibration.** Too high → the same tension splits
   into duplicates each rebuild (no accretion). Too low → distinct
   tensions merge (loss of resolution). Needs real-data tuning; start
   0.80, watch for duplicate-vs-merged.
3. **Cold-start.** First-ever lens-build has no existing lens to
   reconcile against — every candidate is provisional `alpha=1`. That's
   correct: a brand-new user's lens *should* be low-confidence until
   confirmed across rebuilds.
4. **TF-IDF fallback** (no MLX) — semantic identity degrades to
   surface-pole overlap. Acceptable but coarser; same constraint #185
   surfaced. The accumulator still works (support/decay are
   backend-independent); only the matching is coarser.

## What this does NOT change

- The "no LLM outside councils" commitment — reconcile is deterministic.
- The extraction stages (0,2,3) — they still propose; we only changed
  what happens to their output.
- Privacy — everything stays in `~/.trinity/`, append-only ledger
  included.

The net: the chairman keeps *proposing* tensions (good at that); the
accumulator decides what *persists* (the part that makes a lens stand
the test of time).
