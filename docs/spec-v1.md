# Trinity v1.0 — locked launch spec

> Status: **locked for May 13–15 ship.** Schema, tagline, MCP surface, and folder layout all
> frozen at v1. Changes to anything in this file are breaking-API changes and need to wait
> for v1.1 or land in `docs/spec-v2.md`.
>
> Source: user's three-spec drop, modified where my gut disagreed. See "Disagreements
> applied" at the bottom for the deltas vs the original.

## The wedge

Polyharness users — people running Claude + ChatGPT + Gemini subscriptions in parallel — are
stuck copy-pasting between tabs. The fragmentation is not solvable by any single lab —
**they're commercially prevented from helping you use a competitor.** Trinity is the only
thing structurally allowed to.

That single sentence — *"the cross-provider memory layer the labs are commercially prevented
from building"* — answers the only question that matters before it's asked: *why won't
Anthropic just ship this?*

## The brand

**Tagline:** *Own your memories.*
**Subhead:** *The AI you trained should outlive the provider.*

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
- `trinity-local council-launch` — fan out to Claude/Gemini/Codex CLIs, chairman synthesizes, returns Routing JSON outcome
- `trinity-local council-last` — instant council on the last Claude Code prompt (zero-data onboarding)
- `trinity-local me-build` — 4-stage lens-discovery pipeline (basins → decisions → pair-mining → basin post-filter) + Stage 0 turn-pair gaps
- `trinity-local me-card` — render strongest `/me` lens as a 1200×630 PNG (the actual social object — see disagreement #4)
- `trinity-local portal-html` — static launchpad HTML with chart, routing table, recent councils
- `trinity-local doctor` — pre-flight cold-install checks
- `trinity-local install-mcp` — registers MCP server in Claude Code / Codex / Gemini CLI + drops `/trinity` skill
- `trinity-local serve` — http.server on 127.0.0.1:8765 rooted at `~/.trinity` (debugging surface)
- `trinity-local watch-once` — incremental transcript ingest
- `trinity-local council-rate` — record user verdict; persists to `outcome.metadata.user_verdict` + `council_feedback.jsonl`

### MCP tool surface (6, all stable)

The original spec wanted 3 tools (council / query_lens / add_pair). Current ships 6 and
they're all load-bearing for the supervision loop. Mapping:

| Spec tool | v1 tool | Status |
|---|---|---|
| `council` | `run_council` | Stable contract |
| `query_lens` | `search_prompts` | Stable contract |
| `add_pair` | `record_outcome` | Stable contract |
| — | `route` | Extended (heuristic + k-NN routing decision, no model call) |
| — | `get_council_status` | Extended (async polling for in-flight councils) |
| — | `get_persona` | Extended (reads `me.md` so harnesses don't re-fetch per call) |

Stable contract = locked at v1.0. Extended = may evolve in v1.x but won't disappear.

### Folder layout (the licensable artifact)

```
~/.trinity/                   ← TRINITY_HOME (dot-prefix — see disagreement #1)
├── SCHEMA_VERSION            ← v1 forward-compat anchor
├── council_outcomes/{id}.json + {id}.js  ← council data + JSONP wrapper
├── council_outcomes/_thread_{bundle}.js   ← thread manifest
├── council_feedback.jsonl    ← user verdicts (append-only)
├── memory/                   ← PromptNode + TurnWindow indexes (the "hippocampus")
│   ├── prompt_nodes.jsonl
│   ├── turn_windows.jsonl
│   └── embeddings_matrix.npy ← numpy matmul fast-path; FAISS-compatible interface
├── me/                       ← lens-discovery pipeline output
│   ├── lenses.json
│   ├── orderings.json
│   ├── rejections.jsonl
│   ├── decisions.jsonl
│   └── basins.json
├── me.md                     ← rendered persona for chairman context
├── portal_pages/launchpad.html  ← the conversion event
├── review_pages/             ← per-council review HTML
├── cache/embeddings.jsonl    ← embedding cache (rebuildable)
├── settings/telemetry.json   ← opt-in only, default off
├── analytics/                ← routing_label_events.jsonl, knn_advisory.jsonl
├── tasks/, actions/, prompt_bundles/, watcher/, share/, skills/, bin/  ← runtime state
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
# from a terminal
pip install trinity-local
trinity-local install-mcp        # registers MCP + drops /trinity skill
trinity-local doctor             # ✓ checks each provider CLI

# from inside Claude Code (after the two commands above)
/trinity                          # one-shot install + first-council
```

The `/trinity` Claude Code skill is co-equal with the terminal path — see disagreement #5.

Future: `curl -sL trinity.local/install | bash` (week 2, gated on domain + GitHub Pages
landing). `brew install trinity-local` (week 2). `npm i -g trinity-local` (week 4).

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
- **Chairman accuracy:** % of councils where chairman-pick = user-pick after the user has
  rated ≥5. Target: 70%. Computed from `outcome.metadata.user_verdict.user_winner` vs
  `outcome.winner_provider`.
- **Share rate:** count of `me-card` exports (visible locally as files in `~/.trinity/share/`).
  Target: 15% of users by week 12.
- **Stars + forks** on GitHub.

The original spec listed "cross-provider switches prevented" as a metric. **Dropped** —
unmeasurable without telemetry that violates the privacy posture (see disagreement #7).

## v1 launch sequence (next 7 days from spec lock)

| Day | Work |
|---|---|
| Day 1 (today) | Brand reconciliation: README hero, launch.md narrative, manifesto callouts |
| Day 2 | (~~Docker smoke~~ — dropped: v1 is macOS-only per scope; `smoke_install.sh local` + `browser_smoke.py` are the actual gates and both green. Docker smoke returns in v2 when Linux is in scope.) |
| Day 3 | Cold-install test on a fresh Mac (human-gated, ≤8 min from `pip install` to first council) |
| Day 4 | Founder narrative essay draft (the long-form post — week 2 in the spec, but draft now) |
| Day 5 | 5 tester DMs sent; private install + watch them onboard |
| Day 6 | HN post drafted, Twitter thread polished, Product Hunt assets prepped |
| Day 7 | Final dry-run; ship trigger |

Launch day = May 13–15 per the multiple councils that ratified the conditional ship.

## Disagreements applied (the pushback from the original spec)

1. **`~/.trinity/` not `~/trinity/`.** Hidden-dir is the macOS convention; visible folders get accidentally moved, iCloud-synced, deleted by Mac cleanup tools.

2. **numpy not FAISS.** Numpy matmul gets ~5ms on 28k vectors; FAISS adds a heavy native dep for zero observable win. `scorer.toml` knobs (k / weights / thresholds) ship in v1.1.

3. **6 MCP tools, not 3.** The 3-tool subset breaks `record_outcome` (supervision loop persistence), `get_council_status` (async polling), `get_persona` (me.md hand-off). Spec's 3 are renamed as the "stable contract"; the other 3 ship as "extended."

4. **`me-card` is the social object, not the radar chart.** Radar charts are commoditized; the me-card paired-tension PNG is unique to Trinity and renders the lens-discovery output as a shareable artifact. Radar stays as a secondary asset.

5. **`/trinity` Claude Code skill is co-equal with the curl install.** Half the target users live inside Claude Code; the skill is already in the wheel via package-data. README shows both paths.

6. **No pricing tier in v1.** Spec proposed Trinity Pro ($12 → $15/mo) and Trinity for Teams. Both stripped for v1 — tool is free; revenue model decision deferred. Hosted-chairman + cross-machine sync still appear in `docs/spec-v2.md` as held capabilities, not pricing tiers.

7. **"Cross-provider switches prevented" metric is dropped.** Unmeasurable without telemetry the privacy posture forbids. Replaced with locally-observable metrics.

8. **"30-second first council" claim is dropped from public copy.** Realistic is 30–90s including parallel API responses. Public claim: *"three answers in under a minute."* Under-promise + over-deliver.

9. **API keys not in `trinity.toml`.** Keychain or env vars only. `trinity.toml` (v1.1) carries preferences + thresholds + persona templates.

10. **Pairs as derived export, not source of truth.** SoT stays `council_outcomes/{id}.json` + `council_feedback.jsonl` (preserves chairman synthesis, member latencies, basin tags). `trinity-local pairs-export` (v1.1) regenerates the spec's `pairs/{nnnn}.md` view on demand.

## What's intentionally NOT in v1

Deferred to `docs/spec-v2.md` (see that file for the held vision):

- Weekly digest (the original spec listed this in v1.0; `digest.py` was removed during the v1.1 audit and not re-added. `me-card` PNG is the v1 weekly-ish artifact users actually share. Real digest rendering returns in v1.1 alongside the narrative video pipeline.)
- Narrative video pipeline (v1.1, week 8)
- Coach Lens / `trinity evolve` aspirational anchor (v1.2, week 12)
- Hosted council orchestration / cross-machine sync (held in spec-v2.md, no pricing decided)
- Federated / shared anything (v2, month 6)
- Windows / Linux (v2+ — macOS-only is a feature, not a bug)
- Loop Constitution double-loop full skill-graduation flow (substrate shipped; productized usage held)
- Learned coordinator (DPO-trained local chairman + per-member prompt formulation) — the Phase 9 Cortex
- Hosted leaderboard from opt-in routing labels

## The 8-minute bar (the only test that matters)

A curious HN reader, in one browser session (~8 minutes), can go from *"what is this"* on
the HN post → cloned/pip-installed → first council on a real prompt of theirs → screenshot
of the chairman saying *"Codex was better than Claude for your last refactor"* → posted
back to the same HN thread.

If a fresh-Mac install can't make that round-trip in 8 minutes, the launch isn't ready.
Everything in this spec serves that single sentence.
