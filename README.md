# Trinity Local

[![tests](https://github.com/vishigondi/trinity-local/actions/workflows/test.yml/badge.svg)](https://github.com/vishigondi/trinity-local/actions/workflows/test.yml)
[![license](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![python](https://img.shields.io/badge/python-3.10%2B-blue.svg)](pyproject.toml)
[![security](https://img.shields.io/badge/security-policy-green.svg)](SECURITY.md)

## Your taste, ported.

Run any hard question through Claude, Codex, and Gemini in parallel. The chairman synthesizes through the taste distilled from transcripts already on your machine — and picks the answer YOU would have picked, not the generic one.

```bash
trinity-local council-launch --task "Should I use SQLite or DuckDB for this analytics workload?"
# → Claude, Codex, and Gemini answer in parallel.
# → Chairman synthesizes through your taste lens (distilled from your transcripts).
# → Verdict: winner, runner-up, agreed claims, where they split, why each split matters.
```

**No new app. No service. No API key. Your transcripts never leave your machine.**

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/vishigondi/trinity-local/main/scripts/install.sh | bash
```

Then type `/trinity` in Claude Code. The skill walks the rest — `doctor`, ingest, dream, first eval. Free, local, MIT. No PyPI, no npm — Trinity is a git clone you can read end-to-end (`ls ~/.claude/skills/trinity/`).

Requirements: Python 3.10+ and at least one of the `claude` / `codex` / `gemini` CLIs authenticated. Full prereqs, the three install paths (Skill / Trinity.app / Chrome extension), uninstall, and offline-model setup live in [`docs/install-deep.md`](docs/install-deep.md). To remove: `trinity-local uninstall --yes`.

![the launchpad — real Trinity install, 51k indexed prompts](docs/launchpad_example.png)

## How it works

Trinity reads the transcripts already on your machine — Claude Code, Codex CLI, Gemini CLI, Cursor, claude.ai exports, ChatGPT exports, Gemini Takeout — and distills the pattern in **how you rephrase, push back, and decide** into a taste lens. The chairman reads that lens on every council, so the synthesis comes back in your voice, not in the voice of a generic model. The labs can't do this for you because they're commercially prevented from reading across each other; only the layer above them can.

### And — when a new model lands, score it against your taste

```bash
trinity-local eval-build      # one-time: build from your rejection signal (~/.trinity/me/rejections.jsonl)
trinity-local eval-run --target claude-5    # re-target whenever a new model lands
trinity-local eval-show       # per-axis bars: REFRAME / COMPRESSION / REDIRECT / SHARPENING
```

When Claude 5 lands: *"Claude 5 scored 0.88 on my taste — beats Claude 4 by 0.05."* A headline number no lab can produce — because only the layer above the labs sees your transcripts across all three.

---

### Your lens, generated from your prompts.

`trinity-local dream` synthesizes your prompts into **your lens** — a
hierarchical artifact the chairman reads top-down on every council:
`~/.trinity/core.md` (identity), `lens.md` (tensions), `topics.json`
(basins), `vocabulary.md` (language). Inspect via the launchpad's lens
card. Full schema in [`docs/lens.md`](docs/lens.md).

## For teams

Trinity Local is MIT and free for individuals. **Trinity for Teams** (private
beta) brings the same local-routing architecture into your VPC for data
residency and stack composability — see [`docs/teams.md`](docs/teams.md) for
the offering + waitlist.

## For tool builders

`~/.trinity/` ships a JSON-Schema-validated format for council outcomes,
labeled rejections, and personalized eval sets — adoptable by other tools
(Aider / Cline / Continue) under CC0. Contract:
[`docs/PREFERENCE_CORPUS_SPEC.md`](docs/PREFERENCE_CORPUS_SPEC.md); schemas
in [`schemas/`](schemas/).

## Privacy is the wedge

- **Your prompts and the models' answers never leave your machine.** No exceptions, no opt-in
  tier that changes this.
- **What CAN be opted in (default off):** anonymous categorical routing labels —
  `task_type`, `winner`, `confidence`. No content, ever. Powers a future leaderboard for
  the curious; lives perfectly fine without it.
- **No hosted controller, no per-call billing.** Trinity dispatches via the CLIs you already
  use. Build the corpus now while inference is subsidized — the taste signal you capture
  survives the subsidy ending.

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

## Architecture

Chairman synthesizes member outputs into structured Routing JSON; members run in
parallel (or `chain` mode for sequential refinement); lens-discovery is a 4-stage
pipeline ratifying tensions across ≥3 topical basins. Full wire diagram + design
rationale in [`docs/architecture.md`](docs/architecture.md). Agent context lives in
[`claude.md`](claude.md); long-form roadmap in [`docs/scale-plan.md`](docs/scale-plan.md).

## What's next

Trinity Local v1.7 ships today. Roadmap: [`docs/spec-v1.5.md`](docs/spec-v1.5.md) (routing product Claude Code reaches for, June 3) and [`docs/spec-v1.6.md`](docs/spec-v1.6.md) (browser extension for web-chat capture). Locked v1 launch spec: [`docs/spec-v1.md`](docs/spec-v1.md). CHANGELOG: [`CHANGELOG.md`](CHANGELOG.md).

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
