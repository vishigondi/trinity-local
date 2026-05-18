---
layout: home
title: "Trinity Local — your taste, ported"
---

# Trinity Local

## Your taste, ported. Lives inside Claude Code, Codex CLI, Gemini CLI, and Cursor.

You've already chosen between Claude, Codex, and Gemini a thousand times. Trinity
reads those transcripts, learns the pattern in how you rephrase, judge, and decide —
then runs hard questions through all three in your voice and picks the answer you
would have picked.

**No new app. No service. No API key. Your transcripts never leave your machine.**

## Install

One line — clones the skill into `~/.claude/skills/trinity/`, drops two thin shell
wrappers in `~/.local/bin/`, registers MCP in every harness you have:

```bash
curl -fsSL https://raw.githubusercontent.com/vishigondi/trinity-local/main/scripts/install.sh | bash
```

Then in Claude Code:

```
/trinity
```

Want to inspect first? Same install in two steps:

```bash
curl -fsSL https://raw.githubusercontent.com/vishigondi/trinity-local/main/scripts/install.sh -o install.sh
less install.sh    # ~150 lines of plain bash
bash install.sh
```

No PyPI, no npm — Trinity is a git clone you can read end-to-end.
Updates: `trinity-local update`.

## The 60-second demo

Ask Claude a complex question. Mid-conversation, run `trinity-local handoff gemini`.
Gemini picks up exactly where Claude left off — no re-context, no copy-paste — and
adds what it can see that Claude can't (your Gmail, your Drive, your Calendar).
Then hand off to GPT. Same thread, three perspectives, one continuous conversation.

That's the wedge. No frontier provider can build it: Anthropic can't read OpenAI's
transcripts, OpenAI can't read Gemini's. Only the layer above them can.

## Three tiers

Trinity ships as three tiers, each independently functional. The data format in
`~/.trinity/` is the contract; the tiers are surfaces.

- **[Tier 1 — Skill (primary)]({{ '/INSTALL-skill/' | relative_url }})**:
  what you interact with when you type `/trinity`. The skill at
  `~/.claude/skills/trinity/SKILL.md` is the user-facing contract.
- **[Tier 2 — Engine]({{ '/INSTALL-pip/' | relative_url }})**:
  the Python engine the skill calls. Pip install-from-clone path for Python-library
  users; not required for normal use.
- **[Tier 3 — Chrome extension (optional)]({{ '/INSTALL-extension/' | relative_url }})**:
  cross-surface capture + one-click UI. Bridges web chats (claude.ai, chatgpt.com,
  gemini.google.com) into your local corpus.

See [`docs/three-tier-architecture.md`]({{ '/three-tier-architecture/' | relative_url }})
for the full architecture spec.

## Trust + audit

Every Trinity operation either prompts you or is pre-granted via
`~/.trinity/trust.toml`. Every operation appends one line to `~/.trinity/audit.log`
— you can `grep` it. See [TRUST-MODE]({{ '/TRUST-MODE/' | relative_url }}) for
the model.

The trust+audit CLI (`trust-init` / `trust-show` / `audit-show`) is
deferred to v1.1 — the library + audit log behavior ship in v1.7.4,
but inspect `~/.trinity/audit.log` directly until the CLI returns:

```bash
tail -20 ~/.trinity/audit.log
trinity-local update           # pull latest + refresh MCP + verify
```

## The wedge

Three subscriptions ($20/mo Claude + $20/mo ChatGPT + Google AI Pro). Each lab is
commercially prevented from helping you use a competitor. Trinity is the layer
above them — local-first, MIT-licensed, lives in your `~/.trinity/` folder.

You bring the subscriptions. Trinity does the routing.

## See also

- [README](https://github.com/vishigondi/trinity-local/blob/main/README.md)
- [`MIGRATION`]({{ '/MIGRATION/' | relative_url }}) — for users coming from
  earlier installs
- [`three-tier-architecture`]({{ '/three-tier-architecture/' | relative_url }}) — full architecture
- [`PREFERENCE_CORPUS_SPEC`]({{ '/PREFERENCE_CORPUS_SPEC/' | relative_url }}) —
  the data format other tools can adopt
- [GitHub repo](https://github.com/vishigondi/trinity-local)
