# Trinity Local

## Stop copy-pasting prompts. Own your context. Dream your core memories.

### One question. Every model you use. One answer that knows you.

> **⚠️ Pre-PyPI:** Use this for now —
> ```bash
> pip install git+https://github.com/vishigondi/trinity-local && trinity-local install-mcp
> ```
> After v1.0 ships, the simpler one is the same wheel:
> ```bash
> pip install trinity-local && trinity-local install-mcp
> ```

One pain, one promise, one install command. On macOS that single command drops
**Trinity.app** on your Desktop too — open it like any other app, no terminal
needed after install. The structure below cashes out each beat of the tagline.

### The 60-second demo

Ask Claude a complex question. Mid-conversation, run `trinity-local handoff gemini`.
Gemini picks up exactly where Claude left off — no re-context, no copy-paste — and adds
what it can see that Claude can't (your Gmail, your Drive, your Calendar). Then hand
off to GPT. Same thread, three perspectives, one continuous conversation.

![the launchpad — real Trinity install, 51k indexed prompts](docs/launchpad_example.png)

That's the wedge. No frontier provider can build it: Anthropic can't read OpenAI's
transcripts, and OpenAI can't read Gemini's. Only the layer above them can.

---

### Stop copy-pasting prompts.

Three subscriptions, three tabs, three half-answers. Trinity sends one question to
every model you use in parallel and runs a synthesis pass that returns one verdict —
what they agreed on, where they disagreed and why it matters, which one was right.

It also looks back: Trinity scans the transcripts already on your machine, finds
questions you asked multiple providers separately, and turns each cross-provider pair
into a synthetic council — bootstrapping your context from your own history before
you run a single fresh council.

### Councils are a GPS — broad when you need coverage, deep when you need conviction.

You ask one question; Trinity hands you the right mode. **Broad councils** run every
model you use in parallel — chairman synthesizes the spread, you see where the labs
agree and where they fight. **Deep councils** run a chain — each round refines the
previous round's answer, the chairman steers toward conviction instead of coverage.
Same primitive, two zoom levels. You're never lost in the answer space because the
mechanic moves with you.

The same GPS shape applies inside your own data. Trinity ranks your past prompts by
**depth score** — a pure-geometry signal over your transcript embeddings (centroid
distance × inter-turn movement × intrinsic dimensionality) that picks out the threads
where you actually thought, not the ones where you typed "more". Broad: see the
topology of everything you've asked. Deep: surface the threads where you went
somewhere.

### Own your context.

Prompts are transient strings; *context* is the durable asset that shapes how every
model answers. Trinity treats your context as a first-class object — indexed, embedded,
yours. The labs are commercially prevented from helping you use a competitor, which
means none of them can build the layer that holds context across them. Someone outside
them has to.

### Dream your core memories.

`trinity-local dream` synthesizes your prompts into **your lens** — one
hierarchical artifact the chairman reads top-down on every council. Four
levels of cognitive shape, generated bottom-up from your prompt corpus:

| level | file | what's in it | brain analog |
|---|---|---|---|
| identity | `~/.trinity/core.md` | one-paragraph manifesto subsuming the rest | distillation |
| tensions | `~/.trinity/memories/lens.md` | paired tensions you'd reject vs accept | value |
| basins | `~/.trinity/memories/topics.json` | subject clusters + evidence map for lens | semantic |
| language | `~/.trinity/memories/vocabulary.md` | anchors + homonyms + synonyms | linguistic |

Two operational scoreboards live alongside but are NOT cognitive
memory — they're derived from your council outcomes (the verdicts you
log) and feed Trinity's model picker, not the chairman's identity context:

| file | what's in it |
|---|---|
| `~/.trinity/scoreboard/picks.json` | extracted model-selection rules per task_type |
| `~/.trinity/scoreboard/routing.json` | per-task-type provider track record |

Inspect your lens any time via the launchpad's lens card, which links to a
local viewer at `~/.trinity/portal_pages/memory.html`. The four cognitive
levels render together as one document: `core.md` manifesto at the top,
`lens.md` tensions below it (with `basins_spanned` chips per pair),
`topics.json` rendered as an Obsidian-style force graph over centroid
cosine similarity with each basin's most-representative prompts on click,
and `vocabulary.md` anchors + homonyms + synonyms tables. Scoreboards
(`picks.json` / `routing.json`) surface as schema-aware Reader views on
the launchpad's routing card, not in the lens viewer. All inlined at
`portal-html` time — works under `file://`, no server needed.

### One answer that knows you.

The chairman reads `core.md` before synthesizing, so the verdict comes back in your
voice — not in the voice of a model that loves factory patterns. When you push back on
a response, the lens picks it up. The next council's chairman already knows. The labs
can't do this for you because they can't see across each other; only the layer above
them can.

### Local, free, your data.

Your prompts and the models' answers stay on your machine. Trinity rides your existing
subscriptions — never proxies through a hosted API. Open source. macOS today. No account.

### Build your corpus while it's cheap.

Programmatic AI credits are subsidized right now. Every major provider is pricing
inference below cost to grab the model-of-choice slot in your workflow. That window
won't last — once one of them wins, the meter starts on the rest.

The cross-provider preference corpus Trinity builds today (`~/.trinity/`) keeps
working when the subsidy ends. The taste signal is captured forever; the model that
benchmarks best on YOUR rejections today may not benchmark best in six months, and
Trinity's the only layer that can re-score the new lineup against your actual prompts
without re-asking each one. Build the corpus while the inference cost falls on the
provider, not you.

## For teams: vendor-neutral agent memory

Trinity Local is free and built for individuals. **Trinity for Teams** (private beta) brings
the same architecture — local routing across Claude, GPT, and Gemini, with consolidated
patterns staying in your environment — to organizations that want the productivity gains of
agent memory without committing to any one lab's runtime.

**Two enterprise concerns Trinity answers directly:**

- **Data residency / compliance.** Claude Managed Agents runs memory + orchestration on
  Anthropic's hosted runtime. For regulated industries this is a non-starter — you have to
  prove residency. Trinity keeps everything in `~/.trinity/` on infrastructure you own.
  Configure it inside your VPC and the council outputs never cross your network boundary.
- **Stack composability.** Trinity doesn't replace LangGraph, CrewAI, Pinecone, DeepEval,
  or your existing eval pipeline. It sits *above* the model choice — your existing stack
  handles within-Claude state and within-Claude eval; Trinity routes the higher-level
  decision of *which lab to ask for which kind of question.* The article framing is binary:
  *"ditch your flexible modular system, or stay locked into it."* Trinity is the third
  answer — keep the modular stack, add a routing layer that learns across it.

MassMutual, ProgressiveRobot, and others have started naming "agent lock-in" as a
procurement concern; Trinity is the architectural response.

**Waitlist:** [GitHub Discussions](https://github.com/vishigondi/trinity-local/discussions) — open an "Interested in Teams" thread, or email teams@openclaw.dev.

## For tool builders: the Preference Corpus Spec

`~/.trinity/` ships an opinionated, JSON-Schema-validated format for the
state a cross-provider tool produces: council outcomes, labeled
rejections, personalized eval sets. See
[`docs/PREFERENCE_CORPUS_SPEC.md`](docs/PREFERENCE_CORPUS_SPEC.md) for
the contract; schemas live under [`schemas/`](schemas/) and are CC0.

If Aider, Cline, Continue, or your own MCP server adopts this format,
preferences stay portable — the corpus you build today survives the
next tool you try tomorrow. Standards outlive products ~10×; first-mover
authority over the shape only holds while one tool ships in it.

## Privacy is the wedge

- **Your prompts and the models' answers never leave your machine.** No exceptions, no opt-in
  tier that changes this.
- **What CAN be opted in (default off):** anonymous categorical routing labels —
  `task_type`, `winner`, `confidence`. No content, ever. Powers a future leaderboard for
  the curious; lives perfectly fine without it.
- **No hosted controller, no per-call billing.** Trinity dispatches via the CLIs you already
  use. The provider eats the inference cost; you keep the preference signal.

## Prereqs

Trinity needs **Python 3.10+** (macOS Sequoia ships with 3.9 by default — check with
`python3 --version`). If you need to upgrade:

```bash
brew install python   # 3.12 or newer
```

Plus the provider CLIs you want in the council: `claude`, `codex`, and/or `gemini` —
each authenticated to your subscription. `trinity-local doctor` will tell you which
are missing.

## Quickstart (desktop first)

```bash
# Fastest today: clone + setup.sh — checks Python, bootstraps venv, Shortcut, Trinity.app
git clone https://github.com/vishigondi/trinity-local && cd trinity-local
./setup.sh                          # one script handles Python check + everything else
trinity-local install-app           # Trinity.app desktop wrapper (non-coder daily-launch)
trinity-local install-mcp           # registers Trinity in Claude Code / Codex / Gemini CLI / Cursor
                                    #   → first MCP spawn auto-scans your local CLI history
                                    #     (~/.claude/, ~/.codex/, ~/.gemini/, cowork) in the
                                    #     background so the first council is already personal
trinity-local install-extension     # optional: Chrome extension for claude.ai + chatgpt.com
                                    #   browser capture (grows the corpus passively)
trinity-local doctor                # verify providers + auth before your first council
trinity-local council-launch --task "Should I use SQLite or DuckDB for analytics?"
trinity-local lens-build            # surface your taste lenses (after a few councils)
trinity-local me-card               # render your strongest lens as a 1200×630 PNG to share

# Or via pip (PyPI publish lands at v1.0 ship; until then use the git+https form):
pip install git+https://github.com/vishigondi/trinity-local
# Post-ship: `pip install trinity-local` — same package, faster.

# Or, from inside Claude Code (after either of the two above):
/trinity                            # the bundled skill re-runs install + first-council
```

**Three install paths, three audiences.** The CLI (`install-mcp`) is the
engine — every other surface wraps it. `install-app` is the non-coder daily
launch. `install-extension` is the compounding moat — your claude.ai and
chatgpt.com conversations grow the corpus passively. None of them gate the
wow: the moment `install-mcp` lands, the first MCP spawn auto-scans the CLI
transcripts you already have on disk, so your first council is personalized.

For non-coders, the intended daily launch is `Trinity.app`: double-click it from
Applications or Desktop, type a task, and review/rate the result in the app's
local pages. The CLI stays complete for power users and automation.

### Removing Trinity

```bash
trinity-local uninstall                # dry-run: lists what would be removed
trinity-local uninstall --yes          # actually remove MCP configs + Trinity.app + skill
trinity-local uninstall --yes --include-data   # also delete ~/.trinity/ (irreversible)
```

The default uninstall removes Trinity from `~/.claude.json`, `~/.gemini.json`,
`~/.cursor/mcp.json`, the `[mcp_servers.trinity-local]` block from
`~/.codex/config.toml`, the `Trinity.app` copies in Applications/Desktop, the
Chrome Native Messaging manifest, and the bundled `/trinity` skill — but
**preserves `~/.trinity/`** (your corpus, lens, scoreboard, council outcomes)
unless you explicitly pass `--include-data`. The wedge cuts both ways: own
your data also means you decide when to delete it.

`trinity-local doctor` checks each provider CLI is installed + authenticated, the MCP server
dependency is present, and your Trinity directory is writable — surfaces a one-line fix for
each ✗ before you hit a live council.

### Offline by default — and a one-time embedding model download

Trinity pins `HF_HUB_OFFLINE=1` at startup, so the running system never makes outbound
HuggingFace calls during normal operation. The embedding model (`nomic-embed-text-v1.5`,
~270MB) ships once via an explicit, opt-in download:

```bash
HF_HUB_OFFLINE=0 huggingface-cli download nomic-ai/nomic-embed-text-v1.5
```

After that the model lives at `~/.cache/huggingface/hub/` (or `$HF_HOME`) and Trinity
loads it from cache — no Hub contact. Override per-invocation if you ever need to pull
a new version (`HF_HUB_OFFLINE=0 trinity-local …`); otherwise the offline guarantee holds
across every CLI call and every MCP child process.

### Drive it from inside Claude Code

`trinity-local install-mcp` also drops a `/trinity` skill into `~/.claude/skills/trinity/`
(no curl, no clone — it's bundled in the wheel). Once the install-mcp step above ran, type
`/trinity` at the Claude Code prompt to redo the install + doctor + first-council on a fresh
machine without touching your shell. The skill respects local edits — if you've customized
the file, future `install-mcp` runs leave it alone.

## What's new — v1.7 (2026-05-15)

Returning from an earlier install? The big shifts since v1.6 are:

- **`picks.json` + `routing.json` moved** from `~/.trinity/memories/` to
  `~/.trinity/scoreboard/` (they're operational scoreboards, not
  cognitive memory). Idempotent migration on first access; no action
  needed. The chairman now reads only the three thinking memories
  (lens, topics, vocabulary) for identity context.
- **Launchpad "Your memories, raw" → "Your lens"** — 6-chip nav
  collapses to a 4-chip card in chairman-read order. picks + routing
  surface on the routing card where they belong.
- **Cold-start auto-scan** — first MCP spawn scans your `~/.claude`,
  `~/.codex`, `~/.gemini` (and cowork) CLI transcripts in the background.
  Your first council is already personalized; no manual `seed-from-taste-
  terminal` step needed.
- **Cursor is a first-class harness** — `trinity-local install-mcp`
  drops `~/.cursor/mcp.json` alongside Claude Code / Codex / Gemini CLI.
- **Basin labels** — the topology graph no longer renders the largest
  cluster as "Hello.". Substantive snippets picked across reps,
  greetings skipped, in both Python (next `lens-build`) and the JS
  viewer (existing on-disk data benefits at render-time).
- **`mark_pick_wrong` actually fires** — the chip on the picks Reader
  now fires the macOS Shortcut to run `cortex-override`, not just copy
  the command to clipboard.
- **Council failures feed `dispatch_health`** — rate-limited Codex in
  a council now demotes the provider for the next ask. Rate-limit-
  saves metric includes council saves.
- **me-card share artifact** no longer drops orderings silently.

Full log in [CHANGELOG.md](./CHANGELOG.md). 100-persona audit backlog
in [docs/scale-plan.md §Phase 10](./docs/scale-plan.md).

## How is this different from \[X\]

| | Trinity Local | LMArena | promptfoo / Claude evals | OpenRouter | Karpathy LLM Council |
|---|---|---|---|---|---|
| Data source | **Your own prompts** | Crowd votes | Test fixtures | n/a (router) | Yours, but no persistence |
| Cost basis | Your own subscriptions | Hosted | Per-call API | Per-call API | Per-call API |
| Output | **Structured Routing JSON + your `/me` lens** | Win-rate ranking | Pass/fail per case | Cheapest route | Three answers + summary |
| Privacy | **Prompts never upload** | n/a | n/a | Prompts route through their servers | Hosted |
| Personalization | **Personal routing table improves with use** | One global ranking | Per-test-suite | None | None |
| Cross-provider continuity | **`handoff` — mid-conversation, switch models, context survives** | n/a | n/a | n/a | n/a |
| Personal benchmarks | **`eval-run` scores any model against YOUR actual rejections** | Synthetic prompts | Static fixtures | n/a | n/a |
| Shareable artifact | **`/me` lens PNG card** | Leaderboard link | Eval report | n/a | Per-prompt summary |

If you want "which model is best in general," LMArena. If you want "which model handles **this
codebase / this voice / this trade-off you keep making**," Trinity.

## What a council produces

Every council writes:

1. **Per-model answers** — Claude / Gemini / Codex each respond. Streamed as they finish; no
   waiting on the slowest member to read the fastest.
2. **Chairman synthesis** — *winner / runner-up / confidence / per-provider scores*, plus
   structured `agreed_claims`, `disagreed_claims` (with `why_matters`), `routing_lesson`, and
   `eval_seed` (the deterministic test a future answer should pass).
3. **A Routing JSON outcome** persisted to `~/.trinity/council_outcomes/<id>.json`. This is
   the moat — cross-model preference data frontier providers can't see.

After enough councils:

- A **personal routing table** emerges: *"For code_refactor prompts, Claude wins 7.8 / 10."*
- A **lens** distills your taste into paired tensions across domains, with the
  failure mode of pure-A and pure-B explicit. Run `trinity-local me-card` to render it as a
  shareable PNG.

## Demo

The launchpad lives at `~/.trinity/portal_pages/launchpad.html` — open it from `trinity-local
portal-html --open` once you've installed:

![the launchpad](docs/launchpad_example.png)

A real council outcome — verbatim from `~/.trinity/council_outcomes/<id>.json` after the
council ran *"name the single biggest remaining launch risk"* against itself:

```json
{
  "winner": "claude",
  "runner_up": "codex",
  "confidence": "high",
  "agreed_claims": [
    "The #1 risk is the /trinity skill not being installed by the pip path.",
    "install-mcp must drop SKILL.md into ~/.claude/skills/trinity/ via package-data before ship.",
    "The deterministic test must build a wheel, install in a fresh venv with isolated HOME, run install-mcp, and assert SKILL.md exists at the target path."
  ],
  "disagreed_claims": [
    {
      "claim": "The post-validator must check for skill cache-staleness via a doctor --json skill_installed field.",
      "providers_for": ["claude"],
      "providers_against": ["gemini", "codex"],
      "why_matters": "Without this check, install-mcp can succeed on disk but /trinity stays invisible in the user's open Claude Code session — exactly the silent-failure shape the fix was meant to eliminate."
    }
  ],
  "routing_lesson": "For launch_readiness_decision, prefer claude — it consistently surfaces second-order failure modes (cache staleness, link rot) and writes layered post-validators."
}
```

That's the moat: agreed claims you can lean on, disagreed claims with the *why*, and a
routing lesson that makes the next council pick the right chairman automatically. Trinity
ran this council against itself to ratify what would ship — the verdict drove the actual
commit you see here.

## How to use it inside Claude Code

The MCP surface ships 11 tools — three of them are the load-bearing user-facing ones:

**Run a council** (multi-model deliberation):

```
mcp__trinity-local__run_council(
  task="Compare three database options for a 50M-row analytics workload: Postgres, SQLite, DuckDB",
  members=["claude", "gemini", "codex"]
)
```

After the council finishes, the user clicks the answer they preferred. That click feeds
`record_outcome` and Trinity's chairman gets smarter at picking *the right model for this
flavor of question* next time. Completed-but-unrated councils carry a `rate_action` hint
in the MCP response so the agent surfaces the rating prompt inline — no launchpad detour.

**Hand off mid-conversation** (the 60-second demo wedge):

```
mcp__trinity-local__handoff(target_provider="gemini")
```

Pulls the user's recent (user, assistant) turns from the cross-provider prompt index,
packages them as "continuing this thread", dispatches to a different provider. Gemini
picks up exactly where Claude left off. Structurally non-refutable: only Trinity has
the cross-provider index, so no other tool can do this.

**Score any model against your actual taste** (empirical benchmarks):

```bash
trinity-local eval-build                       # build eval set from your rejections
trinity-local eval-run --target gemini         # dispatch + score via judge
```

Trinity mines (prompt, rejected_response, rejection_type) triples from your transcripts
— REFRAME / COMPRESSION / REDIRECT / SHARPENING. `eval-run` scores any candidate model
against THOSE empirical rejections, using your `lens.md` as the judge rubric. The
output is "Model X scored 0.73 on YOUR COMPRESSION-prone prompts, 0.91 on REDIRECT" —
a per-axis benchmark no provider can build themselves (they can't see cross-provider
rejection signal).

Or via the CLI directly:

```bash
trinity-local council-launch --task "..." --members claude gemini codex
trinity-local handoff gemini       # mid-conversation continuity
trinity-local doctor               # health check; surfaces the next-step demo command
```

## Architecture (one paragraph)

The chairman model synthesizes member outputs, emitting structured Routing JSON over every council.
Members run in parallel (or in `chain` mode for sequential refinement). The personal routing
table is computed on demand from `~/.trinity/council_outcomes/*.json` — no separate state
file. The `/me` lens-discovery pipeline (4 stages: basins → decisions → pair-mining →
basin post-filter) ratifies tensions that span ≥3 topical basins. Stage 0 turn-pair gap
extraction (REFRAME / COMPRESSION / REDIRECT / SHARPENING) feeds high-signal behavioral
evidence into decision extraction. The `handoff` mechanism (`trinity-local handoff <provider>`
or `mcp__trinity-local__handoff`) reuses the cross-provider prompt index to package recent
(user, assistant) turns as "continue this thread" context for a different provider — no
re-context required. The `evals/` package consumes mined rejections + lens.md to produce
replayable per-rejection-type benchmarks (`eval-build` / `eval-run`). All artifact shapes
are JSON-Schema-validated and documented in
[`docs/PREFERENCE_CORPUS_SPEC.md`](docs/PREFERENCE_CORPUS_SPEC.md) — adoptable by other
tools (Aider / Cline / Continue) under CC0 to interop with Trinity's preference corpus.

For full architecture: [`claude.md`](claude.md) (agent context) and
[`docs/scale-plan.md`](docs/scale-plan.md) (long-form roadmap).

## What's next — Trinity v1.5 (ships June 3, 2026)

v1.0 ships the ledger; **v1.5 turns it into a routing product Claude Code reaches for.**
Same data, MCP-primary surface. When Claude (the agent) hits a hard decision, needs a
different provider, or hits a rate limit on its own subscription, it calls
`mcp__trinity-local__ask` — Trinity routes to your empirically-best model for that
flavor of question (kNN + cortex-extracted rules) and dispatches via the CLIs you
already pay for. Local model fallback (Ollama / MLX) for cheap subtasks.

Two-tier memory architecture (hippocampus + cortex) inspired by how brains
consolidate — kNN over episodes plus flagship-extracted routing rules per basin.
*Free, local, MIT.* Full spec: [`docs/spec-v1.5.md`](docs/spec-v1.5.md).

The trained-coordinator path (former v2) is sunset — Sakana's own ablation shows
flagship prompt quality beats trained 7B routing, so v1.5 gets the same architecture
via context engineering without paying for GPU training infrastructure. See the
sunset header in [`docs/spec-v2.md`](docs/spec-v2.md) for the architectural-decision
record.

For the locked v1 launch spec: [`docs/spec-v1.md`](docs/spec-v1.md).

## Then — Trinity v1.6 (~ 2 weeks after v1.5)

The wedge claim *"Trinity reads transcripts already on your machine"* works literally
for CLI users today — Claude Code, Codex CLI, and Gemini CLI write session files to
disk that Trinity ingests. For users who spend their day on **claude.ai chat**,
**chatgpt.com**, or **gemini.google.com**, the chat UIs keep transcripts on the
provider's servers — the export ritual (settings → Export data → email → tarball)
is high enough friction that most users never do it. v1.6 closes that gap.

**The mechanic:** one-time install of the Trinity browser extension. After that
every conversation you have on the web lands in
`~/.trinity/conversations/<provider>/<conv_id>.json` the moment it completes. No
listening server, no daemon — Chrome spawns a local capture host on demand via
Native Messaging (the same pattern 1Password / Bitwarden use to bridge their
extensions to local apps), and the OS reaps the process when the extension
disconnects. Files are atomic-write-by-overwrite keyed on the provider's stable
conversation ID; the existing incremental-ingest pipeline picks them up and
threads them into your cortex / lens / picks alongside your CLI sessions.

Privacy invariants stay literal: `lsof -i | grep LISTEN` shows nothing related
to Trinity, the host has no networking imports (enforced by AST scanner), the
`allowed_origins` field in Chrome's native-messaging manifest restricts the host
to invocations from *the* Trinity extension only.

Full spec: [`docs/spec-v1.6.md`](docs/spec-v1.6.md). Install ritual:
[`browser-extension/README.md`](browser-extension/README.md). Week 1 of the
2-week ship plan has landed end-to-end for `claude.ai` and `chatgpt.com`;
`gemini.google.com` ships in v1.7 (Google's RPC-over-JSON protocol is higher
fragility per the spec's stability assessment).

## Help

| Command | What it does |
|---|---|
| `trinity-local doctor` | Pre-flight checks; surfaces a fix line per ✗ |
| `trinity-local install-app` | Install or repair the Trinity desktop launcher |
| `trinity-local council-launch --task "..."` | Run a council from the terminal |
| `trinity-local review-link <council_id> --json` | Generate mobile-safe review links |
| `trinity-local lens-build` | Build your lens from prompt history |
| `trinity-local me-card` | Render your strongest lens as a PNG |
| `trinity-local portal-html --open` | Open the launchpad |
| `trinity-local status` | Aggregate scoreboard, recent councils |
| `trinity-local --help` | Full command list |

## License

MIT — see [`LICENSE`](LICENSE).

## The deeper bet (philosophy, not pitch)

The reason we built it: the AI you trained should outlive the provider. Today the labs are
commercially prevented from helping you use a competitor — your accumulated context is locked
to whichever subscription you stop paying for last. The cross-provider memory layer has to live
*outside* the labs. That's what `~/.trinity/` is. The folder is the API; the lens is yours;
switching providers tomorrow doesn't reset what they've learned about you.

The copy-paste pain is the pain you have today. Memory portability is the freedom you'll want
when one of the three labs starts charging triple. Trinity solves both — but leads with the one
you already feel.

## Building Trinity

Issues, traces, weird outputs, lens shares — all welcome at the GitHub repo. The product
gets better as more people run councils against their own taste; cross-pollinating outputs
on socials is how the network effect compounds.

If you want to read what Trinity thinks of itself, every architecture decision in this
repo cites a council outcome ID. Examples in `claude.md`. Yes, it's councils all the way
down.
