# Show HN: Trinity Local

## TITLE

Show HN: Trinity Local – hand off a conversation between Claude, GPT, and Gemini

(75 chars; leads with the wedge — only Trinity does cross-provider continuity.)

## OPENER

I have three AI subscriptions and I still copy-paste between tabs like an animal. Claude can't tell me when to use ChatGPT. ChatGPT can't tell me when to use Gemini. Not because the models are bad — because Anthropic isn't commercially allowed to recommend OpenAI, and OpenAI isn't allowed to recommend Google. The labs that built the models you trust are the labs that *can't* build the layer above them. Someone outside the labs has to.

So I built Trinity Local. It reads `~/.claude/`, `~/.codex/`, and `~/.gemini/` — the transcript caches already on your machine — and gives you one tool the labs structurally cannot ship: `handoff`. Mid-conversation with Claude, run `trinity-local handoff gemini`. Gemini picks up the last few turns as context and continues the thread — no re-context, no copy-paste, and Gemini adds what it can see that Claude can't (your Gmail, Drive, Calendar). Then hand off to GPT. Same thread, three perspectives, one continuous conversation. The "wait, how did Gemini *know* that?" reaction is the demo working.

What ships today (v1.7, MIT): the handoff tool, multi-model councils with a chairman that synthesizes agreed/disagreed claims into structured Routing JSON, a personal routing table that learns which model wins for *your* kind of question, and a `dream` command that synthesizes your past prompts into a taste lens the chairman reads on every council. MCP server registers into Claude Code, Codex, Gemini CLI, and Cursor. Prompts never upload. No hosted controller, no per-call billing — Trinity rides the subscriptions you already pay for.

Install (macOS, Python 3.10+):

    pip install trinity-local && trinity-local install-mcp

Then `trinity-local handoff gemini` from inside any thread.

## CLOSER

Repo: https://github.com/vishigondi/trinity-local

Happy to answer questions in the thread — architecture decisions, the council/chairman/Routing-JSON shape, why we sunset the trained-coordinator path after Sakana's TRINITY ablation, the Preference Corpus Spec, or anything about the local-first / no-hosted-controller commitment. If you build with two or more model providers, run one council and tell me what broke.
