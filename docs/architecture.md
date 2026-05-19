# Trinity Local — architecture

> Long-form companion to the README. The README covers what Trinity does
> and how to install it; this file covers *how* it works under the hood.
> For the full agent-facing context, see [`claude.md`](../claude.md). For
> the long-form roadmap, see [`scale-plan.md`](scale-plan.md).

## Trinity reads what you've already typed

Three subscriptions, three tabs, three half-answers. Trinity sends one question
to every model you use in parallel and runs a synthesis pass that returns one
verdict — what they agreed on, where they disagreed and why it matters, which
one was right.

It also looks back. Two transcript sources feed Trinity's lens: CLI sessions
that live on disk by default (`~/.claude/`, `~/.codex/`, `~/.gemini/`,
`~/.cursor/`) and web chats the Chrome extension auto-captures locally to
`~/.trinity/conversations/` as you use claude.ai / chatgpt.com /
gemini.google.com. Trinity finds questions you asked multiple providers
separately, turns each cross-provider pair into a synthetic council, and
bootstraps your context from your own history before you run a single fresh
council.

## Councils are a GPS — broad when you need coverage, deep when you need conviction

You ask one question; Trinity hands you the right mode. **Broad councils** run
every model you use in parallel — chairman synthesizes the spread, you see where
the labs agree and where they fight. **Deep councils** run a chain — each round
refines the previous round's answer, the chairman steers toward conviction
instead of coverage. Same primitive, two zoom levels. You're never lost in the
answer space because the mechanic moves with you.

The same GPS shape applies inside your own data. Trinity ranks your past prompts
by **depth score** — a pure-geometry signal over your transcript embeddings
(centroid distance × inter-turn movement × intrinsic dimensionality) that picks
out the threads where you actually thought, not the ones where you typed "more".
Broad: see the topology of everything you've asked. Deep: surface the threads
where you went somewhere.

## Context is the durable asset, not the prompts

Prompts are transient strings; *context* is the durable asset that shapes how
every model answers. Trinity treats your context as a first-class object —
indexed, embedded, yours. The labs are commercially prevented from helping you
use a competitor, which means none of them can build the layer that holds
context across them. Someone outside them has to.

## One-paragraph wire diagram

The chairman model synthesizes member outputs, emitting structured Routing JSON
over every council. Members run in parallel (or in `chain` mode for sequential
refinement). The personal routing table is computed on demand from
`~/.trinity/council_outcomes/*.json` — no separate state file. The `/me`
lens-discovery pipeline (4 stages: basins → decisions → pair-mining → basin
post-filter) ratifies tensions that span ≥3 topical basins. Stage 0 turn-pair
gap extraction (REFRAME / COMPRESSION / REDIRECT / SHARPENING) feeds high-signal
behavioral evidence into decision extraction. The `handoff` mechanism
(`trinity-local handoff <provider>` or `mcp__trinity-local__handoff`) reuses
the cross-provider prompt index to package recent (user, assistant) turns as
"continue this thread" context for a different provider — no re-context
required. The `evals/` package consumes mined rejections + `lens.md` to produce
replayable per-rejection-type benchmarks (`eval-build` / `eval-run`). All
artifact shapes are JSON-Schema-validated and documented in
[`PREFERENCE_CORPUS_SPEC.md`](PREFERENCE_CORPUS_SPEC.md) — adoptable by other
tools (Aider / Cline / Continue) under CC0 to interop with Trinity's preference
corpus.
