---
class: historical
---

# Brand evolution

> Historical context relocated from `claude.md` on 2026-05-22 during
> the v1.7.5 cleanup pass. This file preserves the pivot history so
> the agent-facing `claude.md` doesn't have to carry it. Current
> framing lives in `claude.md`; the trail of how it got there lives
> here.

## Current hook (locked 2026-05-22)

> **Your taste, ported — Trinity picks the answer you would have picked.**

Hero: *"Your taste, ported. Lives inside Claude Code, Codex CLI,
Antigravity, and Cursor."*

Sub: *"No new app. No service. No API key. Your transcripts never
leave your machine."*

The digital-twin axis: **transcripts** (what's already on your
machine) → **lens** (the pattern of how you rephrase/judge/decide,
extracted offline) → **twin** (Trinity acting in your voice when you
ask hard questions). Councils are the mechanism, not the pitch —
the user doesn't think "I want a council," they think "I want what
I would have picked."

## Pivot 2026-05-16: council-mechanic → digital-twin

Prior framing (pre-2026-05-16) was:

> **Stop copy-pasting prompts. Own your context. Dream your core memories.**

with sub:

> **One question. Every model you use. One answer that knows you.**

Three pains were copy-paste / siloed thinking / over-engineering.
Pivoted because the polyharness power user reads "councils" as
another tool to learn; reads "your taste, ported" as something
working FOR them.

Ratified on `bundle_42f8cea9c9e705e5` through three rounds of
cross-provider council iteration; the new framing is a user-direct
rewrite.

## Why the new framing is load-bearing

**The wedge is structural, not technical.** Anthropic can't
recommend ChatGPT. OpenAI can't recommend Claude. Google can't
recommend either. The three labs are commercially prevented from
helping you use a competitor. Someone outside the labs has to ship
the layer above them. That's the only sentence the marketing site
has to land.

**The moat is the ledger.** Every council emits structured Routing
JSON to `~/.trinity/council_outcomes/<id>.json` — `agreed_claims`,
`disagreed_claims` with `why_matters`, `winner`, `provider_scores`,
`routing_lesson`. The chairman's `winner` field IS the supervision
signal — counted as wins per provider per `task_type`, computed on
demand by `compute_personal_routing_table()` walking the outcomes
directory (no separate state file). Frontier providers can't see
the cross-model preference signal; Trinity persists it locally.
Trinity rides on subsidized consumer subscriptions and never pays
per call. v1 is free forever; revenue model deferred.

## What "Your taste, ported" promises

v1 SHIPS: lens building (the twin's substrate) + councils +
chairman synthesis + `dream` cold-start + cortex extraction.

What's NOT in v1 yet but blocks the full twin pitch:

- **Per-member prompt scaffolding** — documented design hole at
  `council_runtime.render_member_prompt`. Today chairman is
  lens-conditioned but dispatch is not, so members get the raw
  question, not the user-twisted version.
- **`task_type` vocabulary unification** — documented KNOWN GAP
  at `ranker/chairman_picker.py:_blended_pick`. The chairman's
  open-set labels and the picker's closed-set heuristic labels
  don't intersect, so personal routing silently doesn't fire
  today.

## Ratifying councils (key historical decisions)

The launch architecture and pipeline shapes were ratified across
many cross-provider councils. The named-anchor ones:

- `council_ff3da1fa84906791` — three-tier architecture Phase 1
  (2026-05-16).
- `council_c18f739a0234aa58` — trust/audit substrate, Phase 6
  (2026-05-16).
- `council_37eca30b6e7010df` — final v1.0 integration floor +
  architecture coherence, Phase 7 (2026-05-16).
- `council_70eaf228d7753074` — `lens-build` Option C (basins as
  verifier, not chairman input).
- `council_6892781d06ac3fa8` — Stage 0 turn-pair gaps as
  highest-leverage import from taste-terminal.
- `council_e7560934cb1f1d72` — Stage 0 = ONE batch chairman call
  gated by deterministic post-validators.
- `bundle_42f8cea9c9e705e5` — brand pivot to "Your taste,
  ported." (three rounds of cross-provider iteration).

These outcomes live in `~/.trinity/council_outcomes/` on the
maintainer's machine; cited council artifacts that the public
launch docs reference are committed to the repo under
`docs/launch_councils/`.

## v1.7.5 cleanup (2026-05-22): + Auto-Dream cite

The 2026-05-22 cleanup pass added a load-bearing differentiator
the prior framing didn't yet need: **Anthropic shipped official
Auto-Dream in Claude Code** (24h+5-sessions trigger, 4-phase
REM-mirror, 200-line MEMORY.md cap — see
https://claudefa.st/blog/guide/mechanics/auto-dream).

Trinity's `dream` verb collides. The cross-provider extension
framing is now load-bearing positioning: Anthropic dreams *Claude*
conversations; Trinity dreams across Claude + Codex + Antigravity
(the labs are commercially prevented from crossing). The structural
wedge gets sharper, not weaker, when the dominant lab ships the
same verb scoped to its own conversations only.

Same cleanup pass also enforced Anthropic's 200-line MEMORY.md
discipline on `claude.md` itself — cut from 918 → ~200 lines, with
historical context (this file + `principles.md` +
`retirement-log.md`) carrying the load that used to live inline.
