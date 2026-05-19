# Trinity Local

[![tests](https://github.com/vishigondi/trinity-local/actions/workflows/test.yml/badge.svg)](https://github.com/vishigondi/trinity-local/actions/workflows/test.yml)
[![license](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)
[![security](https://img.shields.io/badge/security-policy-green.svg)](SECURITY.md)

## Your taste, ported.

Run any hard question through Claude, Codex, and Gemini in parallel. The chairman synthesizes through your taste lens — distilled from your own transcripts, on your machine — and picks the answer YOU would have picked, not the generic one.

![the launchpad — real Trinity install, 51k indexed prompts](docs/launchpad_example.png)

Inside Claude Code (or Codex CLI / Gemini CLI / Cursor) — just ask:

> Run a Trinity council on whether to use SQLite or DuckDB for this analytics workload.

The agent calls `mcp__trinity-local__run_council` for you. Claude, Codex, and Gemini answer in parallel. The chairman synthesizes through your lens and returns the verdict inline: winner, runner-up, agreed claims, where they split, why each split matters. The launchpad above is the same surface in a browser tab — open it from the Chrome extension when you want to scan recent councils, your `/me` lens, and the topic graph without leaving the keyboard for a chat window.

**The Chrome extension does two things.** As you chat on claude.ai / chatgpt.com / gemini.google.com, it captures each conversation to `~/.trinity/conversations/` on your machine — no listening port, no upload; Chrome's Native Messaging spawns a local capture host on demand. And it hosts the launchpad you click open from the toolbar. Together with the CLI sessions on disk (`~/.claude/`, `~/.codex/`, `~/.gemini/`), the extension's captures are what your lens distills from.

**No new app. No service. No API key.** Captures flow *to* your machine; prompts never leave it. Everything else is an MCP server inside the harnesses you already use.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/vishigondi/trinity-local/main/scripts/install.sh | bash
```

Then type `/trinity` in Claude Code. The skill walks the rest — `status`, ingest, dream, first eval. Free, local, MIT. No PyPI, no npm — Trinity is a git clone you can read end-to-end (`ls ~/.claude/skills/trinity/`).

Requirements: Python 3.10+ and at least one of the `claude` / `codex` / `gemini` CLIs authenticated. Full prereqs, the two install paths (Skill / Chrome extension), uninstall, and offline-model setup live in [`docs/install-deep.md`](docs/install-deep.md). To remove: `trinity-local uninstall --yes`.

## How it works

Trinity reads the transcripts on your machine — CLI sessions on disk (Claude Code, Codex CLI, Gemini CLI), web chats the Chrome extension auto-captures locally (claude.ai, chatgpt.com, gemini.google.com), and any manual exports you've imported (claude.ai exports, ChatGPT exports, Gemini Takeout) — and distills the pattern in **how you rephrase, push back, and decide** into a taste lens. The chairman reads that lens on every council, so the synthesis comes back in your voice, not in the voice of a generic model. The labs can't do this for you because they're commercially prevented from reading across each other; only the layer above them can.

### And — when a new model lands, score it against your taste

```bash
trinity-local eval-build      # one-time: build from your rejection signal (~/.trinity/me/rejections.jsonl)
trinity-local eval-run --target claude-5    # re-target whenever a new model lands
trinity-local eval-show       # per-axis bars: REFRAME / COMPRESSION / REDIRECT / SHARPENING
```

When Claude 5 lands: *"Claude 5 scored 0.88 on my taste — beats Claude 4 by 0.05."* A headline number no lab can produce — because only the layer above the labs sees your transcripts across all three.

---

### Your lens, generated from your prompts.

`trinity-local dream` synthesizes transcripts into a hierarchical lens the chairman reads top-down on every council. Inspect via the launchpad's lens card; schema in [`docs/lens.md`](docs/lens.md).

## For teams

Trinity Local is MIT and free for individuals. **Trinity for Teams** (private
beta) brings the same local-routing architecture into your VPC for data
residency and stack composability — see [`docs/teams.md`](docs/teams.md) for
the offering + waitlist.

## For tool builders

`~/.trinity/` ships a CC0 JSON-Schema-validated format adoptable by other tools (Aider / Cline / Continue). Contract: [`docs/PREFERENCE_CORPUS_SPEC.md`](docs/PREFERENCE_CORPUS_SPEC.md).

## Privacy is the wedge

- **Your prompts and the models' answers never leave your machine.** No exceptions, no opt-in
  tier that changes this.
- **What CAN be opted in (default off):** anonymous categorical routing labels —
  `task_type`, `winner`, `confidence`. No content, ever. Powers a future leaderboard for
  the curious; lives perfectly fine without it.
- **No hosted controller, no per-call billing.** Trinity dispatches via the CLIs you already
  use. Build the corpus now while inference is subsidized — the taste signal you capture
  survives the subsidy ending.

## Objections (the ones I had)

**"I don't want to learn another UI — I just use Claude Code."**
You don't. Trinity is an MCP server inside your existing harness (Claude Code, Codex CLI, Gemini CLI, Cursor). `/trinity` walks installation in one step. After that, your existing UI is the UI.

**"I don't want a daemon running on my machine."**
Trinity isn't a daemon. The MCP server spawns when your harness opens, exits when it closes. ~62 MB resident while connected. `lsof -i | grep LISTEN` shows nothing — no listening port, no background process.

**"I don't want my data sent to a server."**
Transcripts never leave your machine. Council fan-out goes from your laptop directly to the CLIs you already authenticated. No hosted controller. Telemetry is opt-in, default off, categorical labels only.

**"I want my subscriptions actually used."**
Trinity dispatches via your existing `claude` / `codex` / `gemini` CLIs — using the tokens you've already paid for. Every council uses what you have. No new bill.

**"I'm tired of copy-pasting between Claude / GPT / Gemini tabs."**
That's the whole point. Every council runs all three in parallel from one prompt. `handoff` hands a thread between providers without re-pasting context.

**"I want to know if a new model release is actually better for me."**
`trinity-local eval-run --target <new-model>` scores it against the prompts you've already rejected — your actual taste, not a synthetic benchmark.

**"I want the right model picked for the right task, automatically."**
Every council you rate teaches Trinity which model wins for which kind of question. The launchpad surfaces the personal routing table; the cortex extracts the rules; chairman uses them on the next call.

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
| Output | **Structured Routing JSON + your `/me` lens** | Win-rate ranking | Pass/fail per case | Cheapest route | Three answers + summary |
| Privacy | **Prompts never upload** | n/a | n/a | Prompts route through their servers | Hosted |
| Personalization | **Personal routing table improves with use** | One global ranking | Per-test-suite | None | None |
| Personal benchmarks | **`eval-run` scores any model against YOUR actual rejections** | Synthetic prompts | Static fixtures | n/a | n/a |
| Council reads through your lens | **Chairman synthesizes in your voice — distilled from past transcripts** | n/a | n/a | n/a | Generic synthesis |
| Shareable artifact | **`/me` lens PNG card** | Leaderboard link | Eval report | n/a | Per-prompt summary |

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
    "providers_against": ["gemini", "codex"],
    "why_matters": "install-mcp can succeed on disk but /trinity stays invisible to the open Claude Code session."
  }],
  "routing_lesson": "For launch_readiness_decision, prefer claude — surfaces second-order failure modes."
}
```

That's the moat: agreed claims you can lean on, disagreed claims with the *why*, and a routing lesson that makes the next council pick the right chairman automatically. Trinity ran this against itself to ratify what would ship.

## Architecture

Chairman synthesizes member outputs into structured Routing JSON; members run in
parallel (or `chain` mode for sequential refinement); lens-discovery is a 4-stage
pipeline ratifying tensions across ≥3 topical basins. Full wire diagram + design
rationale in [`docs/architecture.md`](docs/architecture.md). Agent context lives in
[`claude.md`](claude.md); long-form roadmap in [`docs/scale-plan.md`](docs/scale-plan.md).

## What's next

Trinity Local v1.7 ships today. Roadmap in [`docs/spec-v1.5.md`](docs/spec-v1.5.md) (June 3); CHANGELOG in [`CHANGELOG.md`](CHANGELOG.md).

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
