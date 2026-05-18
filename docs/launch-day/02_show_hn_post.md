# Show HN: Trinity Local

## TITLE

Show HN: Trinity Local – your taste, ported across Claude, GPT, and Gemini

(78 chars; leads with the wedge — past transcripts become a lens new questions are answered through.)

## OPENER

I have three AI subscriptions and I still copy-paste between tabs like an animal. Claude can't tell me when ChatGPT would do better. ChatGPT can't tell me when Gemini would. Not because the models are bad — because Anthropic isn't commercially allowed to recommend OpenAI, and OpenAI isn't allowed to recommend Google. The labs that built the models you trust are the labs that *can't* build the layer above them. Someone outside the labs has to.

So I built Trinity Local. It reads `~/.claude/`, `~/.codex/`, and `~/.gemini/` — the transcript caches already on your machine — and does the one thing the labs structurally cannot: distills *your taste* from how you've already been rephrasing, judging, and rejecting their answers. Then, when you have a new hard question, it runs that question through all three providers in parallel and the chairman synthesizes the answers *through your lens*. The verdict comes back in your voice — what the labs agree on, where they split and why it matters, which one was right *for you*. After a few councils Trinity surfaces a `/me` lens: paired tensions distilled from where you actually pushed back on a model. The "wait, it sounds like *me*" reaction is the demo working.

What ships today (v1.7, MIT): multi-model councils with a chairman that reads your lens before synthesizing, a `dream` command that distills your transcripts into the lens, an `eval-run` that scores any new model against that distilled taste, a personal routing table that learns which model wins for *your* kind of question, and structured Routing JSON (`agreed_claims`, `disagreed_claims`, `routing_lesson`) persisted to `~/.trinity/`. MCP server registers into Claude Code, Codex, Gemini CLI, and Cursor. Prompts never upload. No hosted controller, no per-call billing — Trinity rides the subscriptions you already pay for.

Install (macOS, Python 3.10+):

    curl -fsSL https://raw.githubusercontent.com/vishigondi/trinity-local/main/scripts/install.sh | bash

Then `/trinity` in Claude Code, or `trinity-local council-launch --task "..."` from any shell.

## CLOSER

Repo: https://github.com/vishigondi/trinity-local

Happy to answer questions in the thread — architecture decisions, the council/chairman/Routing-JSON shape, the Preference Corpus Spec, or anything about the local-first / no-hosted-controller commitment. If you build with two or more model providers, run one council and tell me what broke.
