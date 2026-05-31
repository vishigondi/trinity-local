---
class: live
---

# Trinity v1.0 — locked launch spec

> Status: **shipped May 13–15, 2026.** Schema, tagline, MCP surface, and folder layout all
> frozen at v1. Changes to anything in this file are breaking-API changes and need to wait
> for v1.5 (see `docs/spec-v1.5.md` for the next trajectory).
>
> **v1.0 is the data pipe.** It ships the council mechanic, the Routing JSON ledger, the
> lens, and the personal routing table. The pitch users land on is *"Own your taste.
> Lives inside Claude Code, Codex CLI, Antigravity, and Cursor."* with sub *"No new app.
> No service. No API key. Your transcripts never leave your machine."* — the cross-provider
> memory layer the labs can't build. (Pitch pivoted 2026-05-16 from "Stop copy-pasting
> prompts. Own your context. Dream your core memories. One question. Every model you use.
> One answer that knows you." — see "## The brand" section below for the full pivot
> narrative.)
>
> **v1.5 is the routing product** that makes the full "SOTA + your taste + your subs +
> saves cost" pitch literally true. It's MCP-primary, adds the cortex consolidation layer,
> and inverts the surface from launchpad to harness-call. (Local model dispatch already
> landed pre-v1.5 on 2026-05-20 — see `docs/spec-v1.5.md` § "Status update 2026-05-20".)
> See `docs/spec-v1.5.md`. Target: June 3, 2026.
>
> **v2.0 (trained-coordinator) is sunset.** A Conductor's value sits in the prompt-engineering
> quality of the routing prompts it writes, not in the routing decision itself — and a flagship
> model with cortex context produces better prompts than a hypothetical local 7B. v1.5 ships
> the same architectural ideas (three-role action space, per-member prompt formulation,
> recursive verification) without paying the training-infrastructure cost. See the sunset
> header in `docs/spec-v2.md` for the full reasoning.

## The wedge

Polyharness users — people running Claude + ChatGPT + Gemini subscriptions in parallel — are
stuck copy-pasting between tabs. The fragmentation is not solvable by any single lab —
**they're commercially prevented from helping you use a competitor.** Trinity is the only
thing structurally allowed to.

That single sentence — *"the cross-provider memory layer the labs are commercially prevented
from building"* — answers the only question that matters before it's asked: *why won't
Anthropic just ship this?*

## The brand

**Hero:** *Own your taste. Lives inside Claude Code, Codex CLI, Antigravity, and Cursor.*
**Sub:** *No new app. No service. No API key. Your transcripts never leave your machine.*

(Brand axis pivoted 2026-05-16 from the prior "Stop copy-pasting prompts. Own
your context. Dream your core memories." / "One question. Every model you use.
One answer that knows you." framing. Reason: the polyharness power user reads
"councils" as another tool to learn; reads "your taste, ported" as something
working FOR them. The mechanism — councils synthesizing through the lens — is
unchanged; only the surface framing flipped from mechanic-first to user-direct.
See claude.md status block for the full pivot narrative.)

The brand axis splits cleanly into three load-bearing words:
- **transcripts** — what's already on your machine (claude_ai exports, codex sessions, gemini takeout, plus what the Chrome extension captures from web chats)
- **lens** — the pattern of how you rephrase, judge, and decide, extracted offline. Lives as `~/.trinity/memories/lens.md` (paired tensions) + `~/.trinity/memories/topics.json` (basins) + `~/.trinity/memories/vocabulary.md` (anchors) + `~/.trinity/core.md` (distillation). Cognitive shape — what you think and how. Model-selection scoreboards (`picks.json`, `routing.json`) live separately under `~/.trinity/scoreboard/` — operational bookkeeping, not cognition.
- **twin** — Trinity acting in your voice when you ask hard questions. Councils dispatch through all three providers in parallel; chairman condenses members' answers through the lens; you get the answer you would have picked.

Three concrete pains underneath, each with a direct Trinity answer:

| Pain | Trinity's answer |
|---|---|
| You copy-paste prompts between chatbots. | Trinity asks all three at once. |
| Each chatbot only knows its slice of your thinking. | `dream` synthesizes your transcripts into the lens. |
| Each chatbot over-engineers the same problem differently. | The lens learns your COMPRESSION rejections. The routing table de-weights over-engineers in your categories. |

These go in the README H1, the HN title, the Twitter hook, and the homepage hero. Every
piece of launch copy threads back to one of them.

## The magic moment

User installs Trinity, runs `trinity-local council-launch --task "[their actual work]"`,
sees three frontier answers side-by-side with chairman-picked winner **in under a minute**.
The on-screen frame:

> Trinity asked the three labs for you. Here's what each said. Here's why we picked this
> one. Override if we're wrong.

Conversion event = "did that screen happen, did it feel like cheating, did the user
immediately want to do it again." Every v1 feature is downstream of that question.

## What ships in v1

All of the below is **already in the repo** as of CHANGELOG commit `884615f`. v1 work
remaining = brand reconciliation + final smoke gate (docker), not new features.

### Surfaces
- `trinity-local council` — primary terminal verb for fan-out to Claude/Codex/Antigravity CLIs; chairman synthesizes and returns a Routing JSON outcome. `council-launch` remains as a compatibility alias for existing dispatch paths.
- `trinity-local lens` — primary terminal verb for the lens pipeline. `lens-build` remains as a compatibility alias for existing dispatch paths.
- `trinity-local me-card` — render strongest lens as a 1200×630 PNG (the actual social object — see disagreement #4)
- `trinity-local portal-html` — static launchpad HTML with chart, routing table, recent councils
- `trinity-local status` — pre-flight cold-install checks
- `trinity-local install-mcp` — registers MCP server in Claude Code / Codex / Antigravity / Cursor + drops `/trinity` skill
- `trinity-local serve` — http.server on 127.0.0.1:8765 rooted at `~/.trinity` (debugging surface)
- `trinity-local ingest-recent` — incremental transcript ingest (replaces the retired watch-once / watch-loop CLIs; MCP `ask` also fires this passively on every call)
- ~~`trinity-local handoff <provider>`~~ — *Retired 2026-05-26 (0 production usage). Cross-provider continuity now flows via MCP Resources: agents read `trinity://memories/lens.md` at session handshake, so the user's voice carries between providers without an explicit hand-off verb. Originally shipped as workstream #2, tick #119; see `retired_names.py`.*
- `trinity-local eval-build` / `eval-stats` / `eval-run` — corpus-based eval harness (task #122). `eval-build` produces a personalized eval set from `me/preference_acts.jsonl`; `eval-run --target <provider>` dispatches each prompt then scores via judge against `lens.md`. The empirical benchmark that unblocks launch-arc workstream #3 (cross-provider benchmarks). See [`docs/PREFERENCE_CORPUS_SPEC.md`](PREFERENCE_CORPUS_SPEC.md) for the eval-set schema.

### MCP tool surface (<!-- canonical:mcp_tool_count -->8<!-- /canonical --> total: 4 canonical + 3 v1.5 + 1 in-protocol loop)

The original spec wanted 3 tools (council / query_lens / add_pair). Current ships <!-- canonical:mcp_tool_count -->8<!-- /canonical --> —
4 canonical, 3 v1.5 additions, 1 in-protocol provider loop (`import_provider_memory`).
The launch-arc `handoff` tool was retired 2026-05-26 (0 production usage); cross-provider
continuity flows via MCP Resources (`trinity://memories/lens.md`) now.
(`get_eval_summary` shipped post-#122 and was retired 2026-05-18 in commit `1fed7fc`
— agents ground via `ask` + picks; eval-summary stays on the launchpad card +
`eval-show` CLI for direct user inspection. `record_outcome` retired 2026-05-21 —
chairman's pick is now the supervision signal, fed automatically.) All load-bearing for the
supervision loop
OR the launch hook. Mapping:

| Spec tool | v1 tool | Status |
|---|---|---|
| `council` | `run_council` | Stable contract |
| `query_lens` | ~~`search_prompts`~~ retired 2026-05-17 | Substring + recency + replay-value heuristics replaced embedding search on the hot path. Querying the lens now happens implicitly — every council loads `~/.trinity/memories/lens.md` via `get_persona`. |
| `add_pair` | ~~`record_outcome`~~ retired 2026-05-21 | The MCP rating tool was sunset alongside the rest of the user-rating UX. Chairman's `routing_label.winner` is now the supervision signal, fed automatically into `compute_personal_routing_table()` (commit bb817b6). CLI `council-rate` followed it into retirement on 2026-05-22 (task #134) — full rating retirement, no power-user override; refinement prompts carry the "what should it have been instead" signal inline. |
| — | `route` | Extended (heuristic + k-NN routing decision, no model call) |
| — | `get_council_status` | Extended (async polling for in-flight councils) |
| — | `get_persona` | Extended (reads `lens.md` so harnesses don't re-fetch per call) |
| — | `ask` | v1.5 (single-call routing — the 90% case) |
| — | `get_picks` | v1.5 (agent-facing introspection into extracted cortex rules) |
| — | `mark_pick_wrong` | v1.5 (user-veto on a pick from the agent side) |
| — | `import_provider_memory` | In-protocol provider-side memory loop — agent pipes its own extracted lens/eval signals into Trinity (kind=lens → `lenses.json` + `orderings.json`, kind=eval → `preference_acts.jsonl`). CLI mirrors: `lens-prompt`/`lens-import`, `eval-prompt`/`eval-import`. |
| ~~`handoff`~~ | — | *Retired 2026-05-26 — 0 production usage. Cross-provider continuity via MCP Resources at handshake.* |

Stable contract = locked at v1.0. Extended = may evolve in v1.x but won't disappear.

Rating prompts were retired after launch. `run_council` and
`get_council_status` now treat the chairman's lens-governed winner as the
supervision signal; refinements carry "what should change" inline instead of
writing a separate rating record.

### Folder layout (the licensable artifact)

```
~/.trinity/                   ← TRINITY_HOME (dot-prefix — see disagreement #1)
├── SCHEMA_VERSION            ← v1 forward-compat anchor
├── council_outcomes/{id}.json + {id}.js  ← council data + JSONP wrapper
├── council_outcomes/_thread_{bundle}.js   ← thread manifest
├── council_feedback.jsonl    ← user verdicts (append-only)
├── prompts/                  ← raw prompt index (the "hippocampus" — INPUT to dream)
│   ├── prompt_nodes.jsonl    ←   (was `memory/`; renamed per brand axis: prompts vs memories)
│   ├── turn_windows.jsonl
│   └── cursors.json          ← per-source ingest cursors. (Task #54 dropped embedding-powered search for `search_prompt_nodes`; the embeddings live inline on PromptNode records, the planned `embeddings_matrix.npy` cache file never shipped.)
├── memories/                 ← three thinking memories (cognitive shape, OUTPUT of dream)
│   ├── lens.md               ← value — paired tensions you'd reject vs accept
│   ├── topics.json           ← semantic — subject clusters + evidence map for lens
│   └── vocabulary.md         ← linguistic — anchors + homonyms
├── core.md                   ← singular distillation of the three above; chairman reads first
├── scoreboard/               ← operational scoreboards (NOT cognitive memory)
│   ├── picks.json            ← extracted model-selection rules per task_type
│   └── routing.json          ← per-task-type provider track record
├── me/                       ← lens-discovery intermediate output
│   ├── lenses.json
│   ├── orderings.json
│   ├── preference_acts.jsonl
│   ├── arcs.jsonl
│   └── trajectories.jsonl
├── portal_pages/launchpad.html  ← the conversion event
├── review_pages/             ← per-council review HTML
├── evals/                    ← eval-build suites + evals/results/ per-run scores
├── settings/telemetry.json   ← opt-in only, default off
├── analytics/                ← routing_label_events.jsonl, knn_advisory.jsonl, dispatch_outcomes.jsonl
├── todos/, actions/, prompt_bundles/, task_sync/, share/  ← runtime state (share/ holds me-card / council-share / eval-share PNG outputs)
└── (config layered: source-tree config.json + user-overlay env vars; trinity.toml v1.1+)
```

**Schema is locked at v1.** Breaking changes go through a versioned migration that bumps
`SCHEMA_VERSION` and ships a one-shot converter.

### Privacy posture (non-negotiable)

- **Prompts never upload.** No exceptions, no Pro tier that changes this.
- **Telemetry off by default.** Opt-in via `trinity-local telemetry-enable` sends anonymous
  categorical routing labels (`task_type`, `winner`, `confidence`) — no content, ever.
- **No hosted controller.** Council fan-out happens directly from the user's machine to the
  provider CLIs. The provider eats inference cost; the user keeps the preference signal.
- **Folder is the user's.** No upload unless user explicitly opts in. Break this once and the
  brand dies.

### Install paths (dual)

```bash
# One curl-bash. Clones the skill, drops shell wrappers, registers MCP,
# verifies with status. No PyPI, no npm — Trinity is a git clone.
curl -fsSL https://raw.githubusercontent.com/vishigondi/trinity-local/main/scripts/install.sh | bash

# Then from inside Claude Code:
/trinity                          # one-shot install + first-council
```

The `/trinity` Claude Code skill is co-equal with the terminal path — see disagreement #5.

Shipped 2026-05-13: `curl -fsSL https://raw.githubusercontent.com/vishigondi/trinity-local/main/scripts/install.sh | bash`
— canonical install URL backed by the public repo. Future: `brew install trinity-local` (post-launch),
`npm i -g trinity-local` (post-launch). The `trinity.local` vanity domain was retired pre-launch; the
brand surface is `keepwhatworks.com`.

## Pricing

**Free.** The entire local CLI + MCP server. No account, no phone-home, no API proxy. Trinity
rides on the Claude / Gemini / Codex CLI subscriptions the user already pays for. Hosted
tiers and team plans are out of v1 scope — see `docs/spec-v2.md` for what's held.

## North-star metric

**Time-to-reflex:** days from install until the user reflexively runs `trinity-local
council-launch` instead of opening another tab. Target: **<14 days for the median user**.

Supporting metrics (first 90 days, all local-observable, none require telemetry):

- **Activation:** ran first council successfully (any time after install). Target: 60% of
  installs. Tracked from local `council_runs.jsonl`.
- **Reflex (lite):** user has run ≥3 councils. Target: 30% by day 60.
- **Chairman accuracy:** structurally retired 2026-05-22 when task #134 retired
  the rating UX in full. There is no `user_verdict.user_winner` to compare against
  anymore — the chairman's pick (lens-governed) IS the gold target now. Trinity
  measures chairman pick *stability* across providers via the eval harness
  (`trinity-local eval-run --target <provider>`) instead — see task #116.
- **Share rate:** count of `me-card` exports (visible locally as files in `~/.trinity/share/`).
  Target: 15% of users by week 12.
- **Stars + forks** on GitHub.

The original spec listed "cross-provider switches prevented" as a metric. **Dropped** —
unmeasurable without telemetry that violates the privacy posture (see disagreement #7).

## v1 launch sequence (next 7 days from spec lock)

| Day | Work |
|---|---|
| Day 1 (today) | Brand reconciliation: README hero, launch.md narrative, manifesto callouts |
| Day 2 | Launch-check gates green: `bash scripts/launch-check.sh` (pytest + doc-consistency + install.sh syntax) and `python scripts/browser_smoke.py`. Docker smoke returns in v2 when Linux is in scope. |
| Day 3 | Cold-install test on a fresh Mac (human-gated, ≤8 min from `curl -fsSL .../install.sh | bash` to first council) |
| Day 4 | Founder narrative essay draft (the long-form post — week 2 in the spec, but draft now) |
| Day 5 | 5 tester DMs sent; private install + watch them onboard |
| Day 6 | HN post drafted, Twitter thread polished, Product Hunt assets prepped |
| Day 7 | Final dry-run; ship trigger |

Launch day = May 13–15, 2026 per the multiple councils that ratified the conditional ship.

## Disagreements applied (the pushback from the original spec)

1. **`~/.trinity/` not `~/trinity/`.** Hidden-dir is the macOS convention; visible folders get accidentally moved, iCloud-synced, deleted by Mac cleanup tools.

2. **numpy not FAISS.** Numpy matmul gets ~5ms on a 49k-vector corpus (measured 2026-05-13; was ~28k when the call was first made, scaled linearly with no observable falloff). FAISS would add a heavy native dep for zero observable win. `scorer.toml` knobs (k / weights / thresholds) ship in v1.1.

3. **<!-- canonical:mcp_tool_count -->8<!-- /canonical --> MCP tools shipped (4 canonical + 3 v1.5 additions + 1 in-protocol loop).** The 3-tool subset breaks `get_council_status` (async polling), `get_persona` (lens.md hand-off), and `run_council` (the parallel-dispatch primitive itself). Canonical 4: `route`, `run_council`, `get_persona`, `get_council_status`. v1.5 adds `ask`, `get_picks`, `mark_pick_wrong`. In-protocol provider loop adds `import_provider_memory` (the agent pipes lens / eval signals back into Trinity without copy-paste). (`get_eval_summary` shipped post-#122 then retired 2026-05-18 in commit `1fed7fc` — agents ground via `ask` + picks. `record_outcome` shipped at v1.0 then retired 2026-05-21 — chairman pick is the supervision signal now, fed automatically into the personal routing table. `handoff` shipped at launch then retired 2026-05-26 after 0 production usage — cross-provider continuity now rides MCP Resources at handshake.)

4. **`me-card` is the social object, not the radar chart.** Radar charts are commoditized; the me-card paired-tension PNG is unique to Trinity and renders the lens-discovery output as a shareable artifact. Radar stays as a secondary asset.

5. **`/trinity` Claude Code skill is co-equal with the curl install.** Half the target users live inside Claude Code; the skill is already in the wheel via package-data. README shows both paths.

6. **No pricing tier in v1.** Spec proposed Trinity Pro ($12 → $15/mo) and Trinity for Teams. Both stripped for v1 — tool is free; revenue model decision deferred. Hosted-chairman + cross-machine sync still appear in `docs/spec-v2.md` as held capabilities, not pricing tiers.

7. **"Cross-provider switches prevented" metric is dropped.** Unmeasurable without telemetry the privacy posture forbids. Replaced with locally-observable metrics.

8. **"30-second first council" claim is dropped from public copy.** Realistic is 30–90s including parallel API responses. Public claim: *"one answer in under a minute."* Matches the sub-line ("One question. Every model you use. One answer that knows you.") — the council synthesizes a single answer; "three answers" would contradict the one-→-many-→-one mechanic.

9. **API keys not in `trinity.toml`.** Keychain or env vars only. `trinity.toml` (v1.1) carries preferences + thresholds + persona templates.

10. **Pairs as derived export, not source of truth.** SoT stays `council_outcomes/{id}.json` + `council_feedback.jsonl` (preserves chairman synthesis, member latencies, basin tags). `trinity-local pairs-export` (v1.1) regenerates the spec's `pairs/{nnnn}.md` view on demand.

## What's intentionally NOT in v1.0 (lands in v1.5)

See `docs/spec-v1.5.md` for the next-trajectory plan. Target ship: June 3, 2026.

**Lands in v1.5:**
- **MCP-primary surface** — two-tier tools (`ask` cheap / `run_council` medium). Claude Code calls Trinity as a specialist consult. (The originally-planned third tier `plan_and_execute` was sunset 2026-05-22 — the harness owns multi-step orchestration better than Trinity should.)
- **Cortex consolidation** — flagship-extracted routing patterns per basin, stored at `~/.trinity/scoreboard/picks.json`. Operational scoreboard the chairman picker reads; not a cognitive memory. Hippocampus (kNN) + Cortex (rules) two-tier picker pipeline.
- **Local model dispatch** — Ollama + MLX added to the dispatch layer. Local routes for easy subtasks = zero subscription cost.
- **Rate-limit handling + Conductor replan** — when Claude's own sub hits its limit, Trinity continues your work via Codex/Gemini/local. The cross-provider rate-limit-dodge is the killer flow.
- **Launchpad reframe** — becomes "What Trinity has learned about you" dashboard, not the destination.

**Deferred indefinitely (the labs may build these first; not our wedge):**
- Narrative video pipeline — the me-card PNG is the v1 social object; richer video animation is a future explore-not-commit
- Hosted council orchestration / cross-machine sync — the local-first promise is the brand; revisit only if a real paid tier ever exists
- Federated / shared / team anything — single-user has to be overwhelmingly great first
- Windows / Linux — macOS-first at launch; cross-platform expansion is the v1.5/v1.6 trajectory per `docs/cross-platform-spec.md`. The core CLI + MCP path runs on Linux today (pyproject's `POSIX :: Linux` classifier reflects this). The macOS-specific Shortcut dispatcher was retired 2026-05-17 — the Chrome extension's Native Messaging bridge (`capture_host.py`) shipped as the cross-platform launchpad dispatcher (Phase 4b, 2026-05-16; see `docs/MIGRATION.md` for the upgrade path). What remains Windows/Linux work: `trinity-local install-launcher` (.desktop / Start Menu shortcut emitters) is shipped but not yet end-to-end-tested on those platforms
- Hosted leaderboard from opt-in routing labels

**Sunset (v2.0 trained-coordinator path):**
- Training a local Qwen / 7B Conductor via DPO or sep-CMA-ES. v1.5's flagship-as-Conductor + cortex-via-flagship-extraction achieves the same architecture via context engineering, without 4-8 weeks of training infrastructure. Trained-router ablations in the literature show the value is in prompt-engineering quality (a smaller model can match a larger one on routing decisions; the larger model wins on prompt quality) — and flagships write better prompts than any 7B. If v1.5 hits a quality ceiling, this path re-opens as a future v2, trained on the data v1.0+v1.5 generated. See `docs/spec-v2.md` sunset header.

## The 8-minute bar (the only test that matters)

A curious HN reader, in one browser session (~8 minutes), can go from *"what is this"* on
the HN post → cloned/pip-installed → first council on a real prompt of theirs → screenshot
of the chairman saying *"Codex was better than Claude for your last refactor"* → posted
back to the same HN thread.

If a fresh-Mac install can't make that round-trip in 8 minutes, the launch isn't ready.
Everything in this spec serves that single sentence.
