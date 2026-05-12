# Trinity Local

## Stop copy-pasting prompts. Own your context. Dream your core memories.

### One question. Every model you use. One answer that knows you.

Trinity asks Claude, GPT, and Gemini at once — then synthesizes your prompts into core memories only you can see: cortex rules (what models you trust for what), a lens (what you reject and accept), a routing brain (which provider stays simple for your kind of problem). Your prompts are yours. The core memories built from them are yours too. The labs are commercially prevented from building this layer; someone outside them has to.

```bash
pip install trinity-local && trinity-local install-mcp
```

That's it. One pain, one promise, one install command.

---

### 1. Ask once, get one answer.

Three subscriptions, three tabs, three half-answers. Trinity sends your question to all of them
in parallel and runs a synthesis pass that returns one verdict — what they agreed on, where they
disagreed and why it matters, which one was right.

It also looks back: Trinity scans the transcripts already on your machine, finds questions you
asked multiple providers separately, and turns each cross-provider pair into a synthetic
council — bootstrapping your personal routing table from your own history before you run a
single fresh council.

### 2. It knows what you'd reject.

Every time a model over-engineers and you push back to "just one line", Trinity logs it.
Every five-level class hierarchy you reject, every "actually, just inline it" you write, every
"no, simpler" — `dream` watches the *compression rejections* and builds a personal lens from
them. Paired tensions like *"Leverage of present-state assets > ground-up structural
ownership."* That's not a quote from a model; that's the shape your decisions actually take.
The chairman reads this lens before synthesizing, so the verdict comes back in your voice —
*not* in the voice of a model that loves factory patterns.

### 3. It learns which model stays simple for your kind of problem.

Claude over-engineers Python refactors 3× more than GPT does. GPT hand-waves systems
questions Gemini grinds through. *Your version of these scores* is different from anyone
else's, because over-engineering is contextual — what's clean for a startup is sloppy for a
bank. Trinity builds a per-category routing brain from your own corrections and routes the
next question accordingly. The labs can't do this for you because they can't see across each
other; only the layer above them can.

### 4. Local, free, your data.

Your prompts and the models' answers stay on your machine. Trinity rides your existing
subscriptions — never proxies through a hosted API. Open source. macOS today. No account.

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

**Waitlist:** [trinity.local/teams](https://trinity.local/teams) — or email teams@openclaw.dev.

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

## Quickstart (3 paths)

```bash
# Fastest: pip + install-mcp (assumes Python 3.10+ already)
pip install trinity-local
trinity-local install-mcp           # registers Trinity in Claude Code / Codex / Gemini CLI
trinity-local doctor                # verify providers + auth before your first council
trinity-local council-launch --task "Should I use SQLite or DuckDB for analytics?"
trinity-local me-build              # surface your taste lenses (after a few councils)
trinity-local me-card               # render your /me lens as a 1200×630 PNG to share

# Or: clone + setup.sh — checks Python, bootstraps venv, Shortcut, Desktop launchpad icon
git clone https://github.com/openclaw/trinity-local && cd trinity-local
./setup.sh                          # one script handles Python check + everything else

# Or, from inside Claude Code (after either of the two above):
/trinity                            # the bundled skill re-runs install + first-council
```

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

## How is this different from \[X\]

| | Trinity Local | LMArena | promptfoo / Claude evals | OpenRouter | Karpathy LLM Council |
|---|---|---|---|---|---|
| Data source | **Your own prompts** | Crowd votes | Test fixtures | n/a (router) | Yours, but no persistence |
| Cost basis | Your own subscriptions | Hosted | Per-call API | Per-call API | Per-call API |
| Output | **Structured Routing JSON + your `/me` lens** | Win-rate ranking | Pass/fail per case | Cheapest route | Three answers + summary |
| Privacy | **Prompts never upload** | n/a | n/a | Prompts route through their servers | Hosted |
| Personalization | **Personal routing table improves with use** | One global ranking | Per-test-suite | None | None |
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
- A **`/me` lens** distills your taste into paired tensions across domains, with the
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

```
mcp__trinity-local__run_council(
  task="Compare three database options for a 50M-row analytics workload: Postgres, SQLite, DuckDB",
  members=["claude", "gemini", "codex"]
)
```

Or via the CLI:

```bash
trinity-local council-launch --task "..." --members claude gemini codex
```

After the council finishes, the user clicks the answer they preferred. That click feeds
`record_outcome` and Trinity's chairman gets smarter at picking *the right model for this
flavor of question* next time.

## Architecture (one paragraph)

The chairman model is the verifier, emitting structured Routing JSON over every council.
Members run in parallel (or in `chain` mode for sequential refinement). The personal routing
table is computed on demand from `~/.trinity/council_outcomes/*.json` — no separate state
file. The `/me` lens-discovery pipeline (4 stages: basins → decisions → pair-mining →
basin post-filter) ratifies tensions that span ≥3 topical basins. Stage 0 turn-pair gap
extraction (REFRAME / COMPRESSION / REDIRECT / SHARPENING) feeds high-signal behavioral
evidence into decision extraction.

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

## Help

| Command | What it does |
|---|---|
| `trinity-local doctor` | Pre-flight checks; surfaces a fix line per ✗ |
| `trinity-local council-launch --task "..."` | Run a council from the terminal |
| `trinity-local me-build` | Build your `/me` lens from prompt history |
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
