# Launch copy — Trinity Local v1

> Drafts. Voice belongs to the user. Each block is one shippable artifact: thread, README hero
> rewrite, blog hook, 60s demo script. Send me-card PNG with every external post.
>
> v1 brand: **Own your memories. The AI you trained should outlive the provider.** Manifesto
> sentence: *"the cross-provider memory layer the labs are commercially prevented from
> building."* Narrative beat order (per docs/spec-v1.md): fragmentation pain → structural
> problem → local-first answer → council as engine → taste capture → sovereignty stake →
> bigger thesis.
>
> Prior council ratification: `council_4f34cd1181d5bd08` (Codex won, high, ledger-first
> reordering). Subsequent user spec elevated the brand from ledger-mechanic to memory-
> sovereignty; thread updated to lead with the structural argument, not the mechanic.

## Twitter / X thread (12 tweets, narrative-beats order)

**Hook (1/12).** I have three AI subscriptions and I still copy-paste between tabs like
an animal. Claude can't tell me when to use ChatGPT. ChatGPT can't tell me when to use
Gemini. The labs are *commercially prevented* from helping you use a competitor.

**The structural problem (2/12).** It's not a bug. Anthropic isn't allowed to recommend
ChatGPT. OpenAI isn't allowed to recommend Claude. They built the labs you trust; they
can't build the layer above them. Someone outside the labs has to.

**Local-first answer (3/12).** Your transcripts already live on your machine. ~/.claude/.
~/.codex/. ~/.gemini/. Three SQLite caches owned by three companies, none allowed to read
each other. Trinity reads all three. Locally. No phone-home.

**The council as engine (4/12).** When you don't know which model is best for a question,
ask three of them in parallel. A local chairman synthesizes — *agreed claims, disagreed
claims, why the disagreement matters.* You click the answer you trusted. That click is
the only training signal Trinity ever takes.

**The taste capture (5/12).** After ~10 councils, Trinity has built a personal map of
which model wins YOUR kind of question. From my own ledger:

> *leading proxy signal as forecast* vs *official lagging metric as truth*
> failure of one: paranoid pattern-matching, signals everywhere
> failure of the other: consensus follower, lag the move

That's a paired tension extracted from where I pushed back on a model. Two-poled, both
named. Run `me-card` to render it as a 1200×630 PNG. *This* is the social object.

**The sovereignty stake (6/12).** The harnesses are migrating cloud-side. Your context
is becoming someone else's asset. Right now the .sqlite cache is still on your machine.
Trinity is the local memory layer for the window before that closes.

**The privacy moat (7/12).** Prompts never upload. No exceptions, no Pro tier that
changes this. Telemetry is opt-in and ships only anonymous categorical labels — never
content. Folder is yours. Break this once and the brand dies.

**Why this is structurally yours forever (8/12).** Trinity rides on consumer
subscriptions you already pay for. No per-call billing. No vendor lock-in — if you switch
to Anthropic + Mistral tomorrow, the ledger you built still works. The taste you trained
moves with you.

**The recursive demo (9/12).** I ran Trinity's launch council against its own readiness.
It exposed the failure mode, named the deterministic test, drove the commit. The full
outcome is in the repo: `council_d55953003bb29f9d.json`. Open-source the trail, not
just the code.

**Install (10/12).** `pip install trinity-local && trinity-local install-mcp` — drops a
`/trinity` skill into Claude Code globally. From a fresh terminal OR from inside Claude
Code, you're three commands from a council on your real work. Caveat: Trinity needs the
Claude / Gemini / Codex CLIs authenticated. `trinity-local doctor` tells you which are
missing.

**The bigger thesis (11/12).** *Own your memories now, because the next thing you'll need
to own is your agent.* The labs are migrating from "the model I rent" to "the agent that
acts for me." Your context — the work you've already done, the answers you trusted, the
preferences you've expressed — is the asset that makes any agent useful. Trinity is the
substrate that keeps that asset yours.

**CTA (12/12).** Trinity Local v1 ships open-source [date]. github.com/<repo>. If you
build with two or more model providers, run one council. Tell me what you learned.

---

## Founder narrative angle (use in HN comments + bio)

> I'm a polyharness power user. Architecture background — IIT Kharagpur + Harvard GSD. I
> built the propensity models at Mailchimp and an intelligence layer for the smart-home
> stack at OpenClaw. I built Trinity because *I* needed it: I had Claude Code open in one
> terminal, Codex in another, Gemini CLI in a browser tab, and I was copy-pasting between
> them like an animal. The market is exhausted by visionary AI founders in 2026. Trinity
> is the unsexy answer: my own context, on my machine, working for me.

Don't lead with "I'm building the future of AI." Lead with "I got tired of copy-pasting
between three tabs and I built this for myself." Personal voice scales further than
visionary voice in 2026.

---

## README hero (locked, see README.md)

> ## Own your memories.
> ### The AI you trained should outlive the provider.
>
> You use Claude, ChatGPT, and Gemini. They don't talk to each other. Your context lives
> in three different SQLite caches, owned by three different companies, none of which are
> allowed to help you use the others.
>
> Trinity is the local intelligence layer that watches all three, learns which one wins
> for which task, and — when it matters — convenes them as a council so you get the
> strongest answer instead of the most familiar one.
>
> **The cross-provider memory layer the labs are commercially prevented from building.**

---

## Hacker News title + opener

**Title:** *Show HN: Trinity Local — the cross-provider memory layer the labs can't build*

Backup titles:
- *Show HN: I got tired of copy-pasting between Claude / ChatGPT / Gemini and built this*
- *Trinity Local: local memory layer for polyharness users (open source, macOS)*

**First comment (the unfair-advantage post):**

> I have three AI subscriptions and I still copy-paste between tabs like an animal. Claude
> can't tell me when ChatGPT is better. OpenAI can't tell me when Claude is better. It's a
> structural problem — they're commercially prevented from helping you use a competitor.
>
> Trinity is the answer outside the labs. It reads ~/.claude/, ~/.codex/, ~/.gemini/ — the
> SQLite caches that already live on your machine — and learns which model wins for which
> kind of question you ask. When you don't know, it convenes the three of them as a
> council in parallel, and a local chairman synthesizes the answer.
>
> Two architectural commitments worth flagging:
>
> 1. **No hosted controller.** Trinity dispatches via the Claude / Gemini / Codex CLIs
>    you already have. The provider eats inference cost. Trinity rides on subscriptions
>    you're already paying for.
> 2. **Prompts never upload.** What CAN be opted in (default off) is anonymous categorical
>    routing labels — `task_type`, `winner`, `confidence`. Powers a future leaderboard for
>    the curious; works perfectly fine without it.
>
> The interesting bit isn't the comparison — it's that every council emits *Routing JSON*
> (winner / agreed_claims / disagreed_claims / routing_lesson / eval_seed). After a few
> councils, the chairman picker gets smarter at routing *your* flavor of question to the
> *right model for that flavor*. After more, you get a `/me` lens: paired tensions
> distilled from where you pushed back on a model. Pair-wise tensions like *"systems
> thinking that ships"* vs *"elegant theory left in the doc"* — each pole with its named
> failure mode.
>
> Open-source. MIT. Repo: <github.com/...>. Three commands to first council:
>
>     pip install trinity-local
>     trinity-local install-mcp
>     trinity-local council-launch --task "..."
>
> Or `/trinity` inside Claude Code (skill bundled with the wheel).

---

## 60-second demo script (for OBS)

```
0:00–0:08  CLI: pip install trinity-local && trinity-local install-mcp
           (text overlay: "rides Claude / Gemini / Codex subs you already have")
0:08–0:15  CLI: trinity-local doctor   (green checks scroll)
0:15–0:23  Switch to Claude Code. Type /trinity. Show first-council prompt.
0:23–0:38  Type real question (eg "Should I use SQLite or DuckDB for 50M-row analytics?")
           Three model headers stream answers in parallel.
0:38–0:48  Chairman synthesis card: agreed_claims (3 bullets), disagreed_claims
           (1 bullet + why_matters), winner card.
0:48–0:55  Click winner. Open ~/.trinity/council_outcomes/<id>.json — point at the
           Routing JSON: this is a labeled outcome.
0:55–1:00  Switch to launchpad. Personal Routing Table card visible.
           "Best model per task type, from your own councils."
           [End card: github + handle]
```

---

## Failure modes to guard against in launch copy

- **Sounds like wrapper.** Mitigate: every claim leads with the *Routing JSON moat*, not
  the comparison. The data you generate is the wedge, not the act of comparison itself.
- **Sounds like Karpathy LLM Council.** Mitigate: persistence (the ledger) is the
  differentiator. Karpathy's version is per-prompt. Trinity's version compounds.
- **"What's a council." Cognitive load.** Mitigate: lead the demo with one concrete
  question (DuckDB vs SQLite). Concrete > abstract.
- **Privacy claim disbelief.** Mitigate: link to `install-mcp` source. The MCP server
  is a stdio child of the user's harness; verify with `lsof`.
- **"Why not just ask Claude alone."** Answer: because you don't see what the other models
  saw differently, and you don't get the *why_matters* on disagreement. The disagreement
  is the interesting part.

---

## What I'm holding back from the launch

- v2 (Loop Constitution double-loop) is alpha. Mention briefly with a "what's next" link.
  Not the launch headline — v1 is the wedge.
- The personal `/me` lens demo on real data — only mention if I have ≥3 lenses to show.
  An empty `me.md` undersells.
- Anthropic Managed Agents tier — wait for pricing.
- Hosted leaderboard — opt-in upload not yet wired (v1.1).

---

## Send-with checklist

- [ ] me-card PNG attached (use `trinity-local me-card --out /tmp/me.png` to generate fresh)
- [ ] Repo URL is current (post-pubic-push)
- [ ] LICENSE link in footer of every artifact
- [ ] `trinity-local doctor` output recorded for the demo
- [ ] One real council outcome JSON quoted (not synthetic)
- [ ] Skill discoverability tested in a fresh Claude Code session
