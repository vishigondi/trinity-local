---
class: aspirational
---

# Spec — Gemini-Google handoff

> Task #121. Sibling to `handoff` (task #119, shipped). Wedge:
> **only Gemini can read the user's Gmail, Drive, and Calendar inline.**
> Cross-provider continuity to Gemini is the one structural lever no
> other lab can match — Anthropic can't read OpenAI's API tokens, and
> neither can read Google Workspace. Trinity sits one layer above all
> three.

## The reframe

Today's `handoff` ports CONTEXT across providers. The next level is
porting CAPABILITY: hand off to Gemini specifically when the user's
question would benefit from Gmail / Drive / Calendar access. Three
worlds where this is the only good answer:

1. **"What's my schedule next week?"** — Claude can't see the calendar.
   Codex can't see the calendar. Only Gemini-handoff lights it up.
2. **"Find that doc I shared with the design team last quarter."** —
   Drive search is Google-side. The handoff dispatches with the prior
   conversation context plus implicit Drive access.
3. **"Did the legal team approve the contract revision?"** — Gmail
   search, scoped to the user's inbox, with the prior conversation
   priming Gemini on what to look for.

The user gets one continuous conversation: Claude/Codex understands the
codebase or the writing context, Gemini handles the Google-side lookup,
Trinity carries the thread between them. **Both layers ride on the
user's existing subscriptions.** No API keys, no per-call costs.

## What's already shipped

The capability-port primitive is **already in place** as of #119.
`src/trinity_local/handoff.py:_CAPABILITY_HINTS` carries a per-target
hint that fires automatically when `target_provider="antigravity"`:

> If you have access to Google Workspace tools (Gmail, Drive,
> Calendar) or web search, USE THEM when they'd enrich your answer
> with data the prior model couldn't see. […]

The hint is **always-on** for antigravity targets (not opt-in via a
flag) — the reasoning is in the source comment: "Soft 'if you have'
form triggers tool use when available without inventing it." A
hard-required flag would push the burden on the user to remember it.

So the MCP + CLI plumbing is done. What's missing is the
**activation path**: agents inside Claude Code / Cursor don't know
WHEN to suggest the handoff. Without that, the capability sits unused.

## What ships (minimum-viable v1)

### 1. SKILL.md — agent-side activation

Add a trigger list to the SKILL teaching agents WHEN to suggest
`handoff(target_provider="antigravity")`:

- User says "my calendar", "my schedule", "this week" + temporal terms
- User says "my email", "my inbox", "did X reply"
- User says "the doc I shared", "that file from <person>", "my Drive"
- User explicitly says "hand off to Gemini" + workspace-adjacent context

The agent surfaces the suggestion in-line ("Want to hand this off to
Gemini? It has Google Workspace access — Gmail/Drive/Calendar inline.")
rather than calling silently — handoff is user-visible action, opt-in.

### 2. Launchpad CTA (optional — Phase 2)

When the user's recent prompts mention email/calendar/schedule terms,
the launchpad surfaces a one-liner card:
*"Gemini-handoff with workspace access — try it on your scheduling
questions."* With a copy-button for the canonical CLI invocation.

Phase 2 because it requires lightweight intent-detection on the prompt
stream; Phase 1 ships the manual path first.

## Out of scope

- **Auto-detection** of workspace-relevant queries in MCP `route()`.
  Could shadow-route to Gemini-with-workspace-hint when intent matches,
  but that's intent-classification work and risks miscalling.
- **Cross-provider tool calls** — Trinity doesn't pipe TOOLS across the
  provider boundary, just context. Gemini calls its own Google Workspace
  tools after the handoff lands; Trinity doesn't proxy.
- **OAuth / credential management** — those live with the user's Gemini
  install (via Antigravity or the Google CLI binary). Trinity never
  touches Google tokens.
- **Streaming results back** — handoff is one-shot dispatch. Multi-turn
  conversation continues in the target provider's harness, not Trinity.

## Verification

```bash
# 1. CLI smoke — the flag is registered + plumbed
trinity-local handoff --help | grep workspace

# 2. MCP smoke — the tool surfaces the new parameter
trinity-local --mcp <<< '{"method":"tools/list"}' | jq '.[] | select(.name=="handoff") | .inputSchema.properties'

# 3. Real handoff (requires antigravity installed + Google Workspace MCP wired)
trinity-local handoff antigravity --with-workspace \
  --continuation "What's on my calendar tomorrow?"

# 4. SKILL.md teaches the trigger conditions
trinity-local --mcp ... # then inspect the active SKILL block in claude code
```

## Why this is the right next ship (post-#116 closure)

Council ratification will determine final priority, but the wedge here
is **structurally non-refutable**: only Trinity has the cross-provider
hand-off, AND only Gemini-among-the-three can touch Google Workspace
data. Combining the two produces a capability no individual provider
can match — same shape as the original `handoff` ratification (#119)
but with capability-port stacked on top of context-port.

Implementation cost is small (flag + hint string + SKILL update +
tests). User-visible value is large (the user's most common
workspace-related questions now have a one-command answer that
Claude/Codex couldn't otherwise produce).

## Related

- `docs/spec-v1.md` § Handoff (#119, shipped) — context-port half
- Task #121 (this) — capability-port half
- Task #120 — 60-second handoff demo (recording stage; this spec
  feeds the script: "watch us hand off a calendar question to Gemini")
- `src/trinity_local/handoff.py` + `commands/handoff.py` — the
  insertion points for the `workspace_hint` plumbing
- `skills/trinity/SKILL.md` § 7 (Cross-provider continuity) — already
  mentions Gemini-Google as the killer demo; this spec adds the
  triggers + the flag
