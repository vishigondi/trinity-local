---
class: live
---

# ⠕ Trinity Local

[![tests](https://github.com/vishigondi/trinity-local/actions/workflows/test.yml/badge.svg)](https://github.com/vishigondi/trinity-local/actions/workflows/test.yml)
[![license](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)
[![security](https://img.shields.io/badge/security-policy-green.svg)](SECURITY.md)

## Own your taste.

Stop copy-pasting prompts between tabs like an animal. Ask once. Trinity fans it out to Claude, GPT, and Gemini. Shows you where they split. Makes the call the way your taste would.

**Install** — just an MCP and a Chrome extension. No new app, no cloud, no API key.

![the launchpad — what a brand-new install opens to on first run](docs/launchpad_example.png)

Inside Claude Code (or Codex CLI / Antigravity / Cursor) — just ask:

> Run a Trinity council on whether to use SQLite or DuckDB for this analytics workload.

The agent calls `mcp__trinity-local__run_council` for you. Claude, Codex, and Gemini answer in parallel; the chairman synthesizes and returns the verdict inline:

> **Winner: DuckDB** — all three agree it wins on analytical scan speed.
> **Where they split:** Claude flags SQLite's simpler ops story; Codex and Gemini don't. *Why it matters for you:* you've shipped solo before and kept picking the lower-ops option — so the chairman weights that split toward "SQLite if you'll operate it alone."

That last move — the chairman knowing which split matters to **you** — is the part no single chat tab can do. It reads your **lens**: the pattern in how you rephrase, judge, and decide, distilled from your own transcripts. The launchpad above is the same surface in a browser tab — open it from the Chrome extension to scan recent councils, your lens, and the topic graph.

**The Chrome extension does two things.** As you chat on claude.ai / chatgpt.com / gemini.google.com, it captures each conversation to `~/.trinity/conversations/` on your machine — no listening port, no upload; Chrome's Native Messaging spawns a local capture host on demand. And it hosts the launchpad you click open from the toolbar. Together with the CLI sessions on disk (`~/.claude/`, `~/.codex/`, `~/.gemini/`), the extension's captures are what your lens distills from.

**You'll want at least Claude + Codex CLI installed.** The magic is the *disagreement* — a council needs a second voice. One provider runs, but the "where they split" payoff needs two.

**Own your taste — the part that compounds.** The council is the painkiller; the lens is the moat. Every council, every rejected answer, every rephrase sharpens a profile of your judgment that no lab can see across competitors (Anthropic can't read your ChatGPT; OpenAI can't read your Claude). The longer you use it, the more the synthesized answer is the one *you* would have written.

**No new app. No service. No API key.** Captures flow *to* your machine; prompts never leave it. Everything else is an MCP server inside the harnesses you already use. **Free for individuals, forever** — MIT, local. (A hosted Trinity-for-Teams is the eventual revenue path; it never gates the individual experience.)

## Install

**Recommended** — one line. Clones the repo (you can read it end-to-end), installs the runtime deps, registers Trinity's MCP server in every harness it detects (Claude Code, Codex CLI, Antigravity, Cursor), and pre-wires the Chrome-capture host:

```bash
<!-- canonical:install_command -->curl -fsSL https://raw.githubusercontent.com/vishigondi/trinity-local/main/scripts/install.sh | bash<!-- /canonical -->
```

No PyPI, no npm, no API key — just `git clone` + a couple of shell wrappers in `~/.local/bin/`. Verify with `trinity-local status`. To remove: `trinity-local uninstall --yes`.

**Not comfortable in a terminal?** Paste that one line into **Claude Code** — it runs inside your terminal *and* in the **Claude Desktop** app — and let Claude run the install for you. That's the easiest path if you arrived via the Chrome extension and have never opened a shell.

**Manual MCP config** — if the bootstrap missed a harness, or you want to wire one by hand, that's exactly what `trinity-local install-mcp` writes. Substitute `PYTHON` with your interpreter (`which python3`, or the absolute path the bootstrap printed).

For **Claude Code** (`~/.claude.json`), **Cursor** (`~/.cursor/mcp.json`), **Antigravity** (`~/.gemini/settings.json`), and other JSON harnesses — merge into the top-level `mcpServers` object:

```json
{
  "mcpServers": {
    "trinity-local": {
      "command": "PYTHON",
      "args": ["-m", "trinity_local.main", "--mcp"]
    }
  }
}
```

For **Codex CLI**, append to `~/.codex/config.toml`:

```toml
[mcp_servers.trinity-local]
command = "PYTHON"
args = ["-m", "trinity_local.main", "--mcp"]
```

For **Antigravity** (`agy` CLI) — model selection happens inside agy itself, not via MCP. Run `/model` and pick your Gemini (e.g. `Gemini 3.5 Flash (high)`); Trinity's launchpad reads the persisted selection from `~/.gemini/antigravity-cli/settings.json`.

Then ask any of these agents: *"Run a Trinity council on …"* — the MCP tools appear inline. Free, local, MIT. The CLI (`trinity-local status`, `trinity-local dream`, etc.) is the engine; the MCP tools are the agent surface.

Requirements: Python 3.10+ and at least one of the `claude` / `codex` / `agy` CLIs authenticated — Trinity works with just one (chairman synthesis + your lens), gets stronger with two (real disagreement), full canonical council with three. **Ollama / MLX models you've pulled locally are auto-discovered** and join the routing pool as free council members (`ollama:<model>` / `mlx:<model>`) — no config edit, no extra MCP tools. To remove: `trinity-local uninstall --yes`.

## How it works

Trinity reads the transcripts on your machine — CLI sessions on disk (Claude Code, Codex CLI, Antigravity), web chats the Chrome extension auto-captures locally (claude.ai, chatgpt.com, gemini.google.com), and any manual exports you've imported (claude.ai exports, ChatGPT exports, Gemini Takeout) — and distills the pattern in **how you rephrase, push back, and decide** into a taste lens. The chairman reads that lens on every council, so the synthesis comes back in your voice, not in the voice of a generic model.

> **Anthropic can't recommend ChatGPT. OpenAI can't recommend Claude. Google can't recommend either. The competitive constraint is structural, not technical.** The labs that built the models you trust are commercially blocked from helping you use a competitor — so the cross-provider memory layer has to come from outside the labs. That's what Trinity is.

### And — when a new model lands, score it against your taste

```bash
trinity-local eval-build      # one-time: build from your rejection signal (~/.trinity/me/preference_acts.jsonl)
trinity-local eval-run --target claude    # re-target whenever a new model lands (provider name: claude / codex / antigravity)
trinity-local eval-show       # per-axis bars: REFRAME / COMPRESSION / REDIRECT / SHARPENING
```

When Claude 5 lands: *"Claude provider scored 0.88 on my taste — beats last release by 0.05."* A headline number no lab can produce — because only the layer above the labs sees your transcripts across all three.

---

### Your lens, generated from your prompts.

`trinity-local dream` is the consolidation pass. Like sleep: it
**reweights old facts in light of everything that's come in since**,
**resolves memories that contradicted each other**, and connects
**memories that were just sitting there with their neighbors** — turning
a corpus of raw prompts into a hierarchical lens (identity → paired
tensions → subject basins → vocabulary) that the chairman reads top-down
on every council.

**Traceability is non-negotiable.** *If it can't show its work, it
doesn't get to claim the thought.* Every lens entry carries
`tension_decisions` — backreferences to the specific rejection pairs
that justify it. Open the launchpad's lens card and each claim links
back, clickable, to the model-said-vs-you-substituted moments it was
extracted from. No hidden inference, no "trust me." Inspect any claim;
walk the chain to the source.

**The folder is the API.** `~/.trinity/` is a CC0 JSON-Schema-validated
on-disk contract — `memories/lens.md`, `memories/topics.json`,
`memories/vocabulary.md`, `core.md`, `scoreboard/picks.json`. Any tool
(Aider / Cline / Continue / your own) can read or write through that
folder without going through Trinity's process. Schema in
[`docs/lens.md`](docs/lens.md) + [`docs/PREFERENCE_CORPUS_SPEC.md`](docs/PREFERENCE_CORPUS_SPEC.md).

## For teams

Trinity Local is MIT and free for individuals. **Trinity for Teams** (private
beta) brings the same local-routing architecture into your VPC for data
residency and stack composability — see [`docs/teams.md`](docs/teams.md) for
the offering + waitlist.

## For tool builders

`~/.trinity/` is the API surface. CC0, JSON-Schema-validated, adoptable
by Aider / Cline / Continue / anything else. Schema:
[`docs/PREFERENCE_CORPUS_SPEC.md`](docs/PREFERENCE_CORPUS_SPEC.md).

## Privacy is the wedge

- **Your prompts and the models' answers never leave your machine.** No exceptions, no opt-in
  tier that changes this.
- **Anonymous categorical telemetry is on by default** (Google Analytics 4 property
  `539262453`). Two payloads, both categorical/numeric only: the per-council event
  (`task_type`, `winner`, `member_count`, `mode`) and, from the launchpad, an anonymous
  provider win-rate snapshot (per-provider Elo / wins / total games — no task text). No
  prompt content, no lens text, no user_substitute strings ever. Disable any time with
  `trinity-local telemetry-disable`; the data immediately stops flowing. Sending also
  requires GA4 credentials that the public build does **not** ship — without
  `TRINITY_GA4_MEASUREMENT_ID` + `TRINITY_GA4_API_SECRET` set, both the CLI and the
  launchpad silently no-op (nothing leaves your machine).
- **No hosted controller, no per-call billing.** Trinity dispatches via the CLIs you already
  use. Build the corpus now while inference is subsidized — the taste signal you capture
  survives the subsidy ending.

## Objections (the ones I had)

**"I don't want to learn another UI — I just use Claude Code."**
You don't. Trinity is an MCP server inside your existing harness (Claude Code, Codex CLI, Antigravity, Cursor). `/trinity` walks installation in one step. After that, your existing UI is the UI.

**"I don't want a daemon running on my machine."**
Trinity isn't a daemon. The MCP server spawns when your harness opens, exits when it closes. ~62 MB resident while connected. `lsof -i | grep LISTEN` shows nothing — no listening port, no background process.

**"I don't want my data sent to a server."**
Transcripts never leave your machine. Council fan-out goes from your laptop directly to the CLIs you already authenticated. No hosted controller. Anonymous categorical telemetry (the four discrete labels above — no prompt content) is on by default to close the feedback loop; turn it off any time with `trinity-local telemetry-disable`.

**"I want my subscriptions actually used."**
Trinity dispatches via your existing `claude` / `codex` / `agy` CLIs — using the tokens you've already paid for. Every council uses what you have. No new bill.

**"I'm tired of copy-pasting between Claude / GPT / Gemini tabs."**
That's the whole point. Every council runs all three in parallel from one prompt.

**"I want to know if a new model release is actually better for me."**
`trinity-local eval-run --target <provider>` (claude / codex / antigravity — the provider you want to benchmark; the underlying model is whatever that provider currently ships) scores it against the prompts you've already rejected — your actual taste, not a synthetic benchmark.

**"I want the right model picked for the right task, automatically."**
Every council teaches Trinity which model wins for which kind of question — automatically. The chairman's pick (lens-governed) is the signal; `compute_personal_routing_table()` aggregates it per task type. No human rating step. The launchpad surfaces the personal routing table; the cortex extracts the rules; chairman uses them on the next call.

**"How is this different from Anthropic's Dreaming?"**
Same verb, different domain. Dreaming consolidates Claude sessions inside Anthropic's runtime — single-lab. Trinity dreams *across the labs*: `~/.claude/` + `~/.codex/` + `~/.gemini/` + claude.ai + ChatGPT + Gemini exports, on your machine. Even if Anthropic moves Dreaming server-side tomorrow, the server-side version still can't see OpenAI or Google transcripts — the labs are commercially prevented from reading each other. Cross-lab dreaming has to come from outside the labs, by definition. Dreaming makes Claude smarter at being Claude; Trinity learns which model wins which kind of YOUR question.

**"Won't Anthropic just build cross-provider memory themselves?"**
They literally can't. Anthropic can't recommend ChatGPT; OpenAI can't recommend Claude; Google can't recommend either. The competitive constraint is structural, not technical. The cross-provider layer has to come from outside the labs — that's the whole wedge.

**"Who's behind this? Why trust a random repo with my transcripts?"**
Single developer, MIT, public source — small enough to audit in an evening. Trinity reads transcripts on your machine — written there either by your CLI sessions or by the Chrome extension's local capture host. Nothing leaves the machine. If you stop using it, `~/.trinity/` is plain JSON you can `cat | jq` without us.

**"What happens if you abandon this project?"**
The folder is the API. `~/.trinity/memories/lens.md` is Markdown; council outcomes are human-readable JSON; the schema is at [`docs/PREFERENCE_CORPUS_SPEC.md`](docs/PREFERENCE_CORPUS_SPEC.md). Your taste capture survives Trinity disappearing.

## How is this different from \[X\]

| | Trinity Local | LMArena | promptfoo / Claude evals | OpenRouter | Karpathy LLM Council |
|---|---|---|---|---|---|
| Data source | **Your own prompts** | Crowd votes | Test fixtures | n/a (router) | Yours, but no persistence |
| Cost basis | Your own subscriptions | Hosted | Per-call API | Per-call API | Per-call API |
| Output | **Structured Routing JSON + your `lens`** | Win-rate ranking | Pass/fail per case | Cheapest route | Three answers + summary |
| Privacy | **Prompts never upload** | n/a | n/a | Prompts route through their servers | Hosted |
| Personalization | **Personal routing table improves with use** | One global ranking | Per-test-suite | None | None |
| Personal benchmarks | **`eval-run` scores any model against YOUR actual rejections** | Synthetic prompts | Static fixtures | n/a | n/a |
| Council reads through your lens | **Chairman synthesizes in your voice — distilled from past transcripts** | n/a | n/a | n/a | Generic synthesis |
| Shareable artifact | **`lens` PNG card** | Leaderboard link | Eval report | n/a | Per-prompt summary |

If you want "which model is best in general," LMArena. If you want "which model handles **this
codebase / this voice / this trade-off you keep making**," Trinity.

## Demo

A real council outcome — verbatim from `~/.trinity/council_outcomes/<id>.json` after the council ran *"name the single biggest remaining launch risk"* against itself:

```json
{
  "winner": "claude",
  "runner_up": "codex",
  "confidence": "high",
  "agreed_claims": [
    "The #1 risk is the /trinity skill not installing by the pip path.",
    "install-mcp must drop SKILL.md into ~/.claude/skills/trinity/ before ship."
  ],
  "disagreed_claims": [{
    "claim": "Post-validator must check for skill cache-staleness.",
    "providers_for": ["claude"],
    "providers_against": ["antigravity", "codex"],
    "why_matters": "install-mcp can succeed on disk but /trinity stays invisible to the open Claude Code session."
  }],
  "routing_lesson": "For launch_readiness_decision, prefer claude — surfaces second-order failure modes."
}
```

That's the moat: agreed claims you can lean on, disagreed claims with the *why*, and a routing lesson that makes the next council pick the right chairman automatically. Trinity ran this against itself to ratify what would ship.

## Architecture

Chairman synthesizes member outputs into structured Routing JSON; members run in
parallel (or `chain` mode for sequential refinement); lens-discovery is a 5-stage
pipeline (Stage 0 turn-pair rejections + Stages 1-4 basins→decisions→pair-mining→post-filter) ratifying tensions across ≥3 topical basins.

**Want the full picture?** [`docs/how-trinity-works.md`](docs/how-trinity-works.md) walks the pipeline end-to-end — transcripts → embeddings → dream → the 4-tier gate → runtime. Wire diagram + design rationale in [`docs/architecture.md`](docs/architecture.md). Agent context lives in
[`claude.md`](claude.md); long-form roadmap in [`docs/historical/scale-plan.md`](docs/historical/scale-plan.md).

## What's next

Trinity Local v1.7.4 shipped May 13–15, 2026; v1.7.5 post-launch cleanup shipped May 22, 2026 (full rating retirement, claude.md cut to 200 lines, Auto-Dream coexistence framing, ⠕ brand mark — see [`CHANGELOG.md`](CHANGELOG.md)). Roadmap in [`docs/historical/spec-v1.5.md`](docs/historical/spec-v1.5.md) (next: June 3, 2026).

## Help

| Command | What it does |
|---|---|
| `trinity-local status` | Health + scoreboard + recent councils (absorbed `doctor`) |
| `trinity-local council-launch --task "..."` | Run a council from the terminal |
| `trinity-local lens-build` | Build your lens from prompt history |
| `trinity-local me-card` | Render your strongest lens as a PNG |
| `trinity-local portal-html --open-browser` | Open the launchpad |
| `trinity-local review-link <council_id> --json` | Mobile-safe review links |
| `trinity-local --help` | Full command list |

## License

MIT — see [`LICENSE`](LICENSE).
