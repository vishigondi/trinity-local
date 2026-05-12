# Launch copy — Trinity Local v1

> Drafts. Voice belongs to the user. Each block is one shippable artifact: thread, README hero
> rewrite, blog hook, 60s demo script. Send me-card PNG with every external post.
>
> v1 brand: **Stop copy-pasting your prompts between chatbots. Own your prompts. Dream
> creates the memory.** Manifesto sentence: *"the cross-provider memory layer the labs are
> commercially prevented from building."* Three load-bearing pains in order: copy-paste pain →
> siloed-thinking pain → over-engineering pain. The "Own your memories" standalone tagline is
> retired; ownership now attaches to **prompts** (yours, raw) and **dream** is the verb that
> turns them into **memory** (cortex + lens + routing — the only thing only Trinity does).
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

**The bigger thesis (11/12).** *Own your prompts now, because the next thing you'll need to
own is your agent.* The labs are migrating from "the model I rent" to "the agent that acts
for me." Your prompts — the work you've already done, the answers you trusted, the
preferences you've expressed — are the raw asset. Dream synthesizes them into memory: cortex
rules, taste lens, routing brain. The labs can't build this because they can't see across
each other. Trinity is the only layer above them that can.

**CTA (12/12).** Trinity Local v1 ships open-source [date]. github.com/<repo>. If you
build with two or more model providers, run one council. Tell me what you learned.

---

## FAQ pre-empt: Sakana TRINITY (ICLR 2026)

Sakana AI published *"TRINITY: An Evolved LLM Coordinator"* (arXiv:2512.04695, ICLR
2026) the same week Trinity Local ships. Two different things; the names collide. The
question will get asked in HN comments + on X. Pre-empted answer:

> Sakana's TRINITY is a research coordinator that trains a 0.6B SLM + 10K-param head via
> sep-CMA-ES to hit 86.2% pass@1 on LiveCodeBench — beats GPT-5 and Gemini 2.5-Pro on
> coding benchmarks. It's a learned coordinator over multiple LLMs.
>
> Trinity Local is a local-first consumer tool for polyharness users — people running
> Claude + ChatGPT + Gemini subscriptions in parallel. It watches the transcripts on
> your machine, learns your taste, picks the right model for your kind of question, and
> when in doubt convenes them as a council. Free. Open-source. macOS-only at launch.
>
> Same wedge ("coordination beats monolithic scaling"), different audience (researchers
> vs. polyharness power users), different mechanism (their trained cortex vs. our
> ledger + flagship-as-Conductor). The two coexist — the Sakana paper independently
> validates the architectural thesis we're shipping. Their `Thinker / Worker / Verifier`
> role decomposition is absorbed into `docs/spec-v1.5.md` as the `plan_and_execute`
> three-list output schema. The key insight that drove our pivot from a trained
> coordinator: their own 3B vs 7B ablation (Figure 7) shows both Conductor sizes find
> the same routing — the 7B wins on natural-language prompt quality. A flagship model
> with retrieval+cortex context produces better prompts than any 7B you could train,
> so we ship the architecture via context engineering instead of paying for training.

If asked in HN comments specifically: lead with the audience differentiation, link the
arXiv paper, point at `docs/spec-v1.5.md` for our active plan (and the sunset header
in `docs/spec-v2.md` for the trained-coordinator decision record). Don't pretend the
collision isn't there.

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

> ## Stop copy-pasting your prompts between chatbots.
> ### Own your prompts. Dream creates the memory.
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

**Title (current-event hook, post-Dreaming):** *Show HN: Trinity Local — Anthropic's Dreaming,
but across Claude / ChatGPT / Gemini, and the memory lives in your folder*

Backup titles (use if the Dreaming hook decays):
- *Show HN: Trinity Local — the cross-provider memory layer the labs can't build*
- *Show HN: I got tired of copy-pasting between Claude / ChatGPT / Gemini and built this*
- *Trinity Local: local memory layer for polyharness users (open source, macOS)*

**First comment (the timing-anchored post):**

> Last week Anthropic shipped *Dreaming* — agents that learn from their own sessions on
> infrastructure Anthropic owns. Harvey reported 6× task completion uplift. The technique
> works. **Trinity is what learning-from-sessions looks like when the sessions live in your
> folder, across all three labs — Claude, ChatGPT, and Gemini.** Open source, local, MIT.
>
> The structural problem Anthropic is now publicly validating: the three labs are
> commercially prevented from helping you use a competitor. They can ship Dreaming /
> Outcomes / Multi-Agent Orchestration — but only on top of their own runtime. Cross-
> provider memory has to come from someone outside the labs.
>
> Trinity reads `~/.claude/`, `~/.codex/`, `~/.gemini/` — the SQLite caches that already
> live on your machine — and consolidates them the same way Dreaming consolidates Anthropic-
> hosted sessions: episodes → extracted routing patterns per question-kind (we call them
> basins), with a system-computed trust score gating which patterns drive decisions. When
> you don't know which lab to ask, Trinity convenes the three of them as a council and a
> local chairman synthesizes the verdict.
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
> The VentureBeat article has the deepest sentence in the debate: *"models may become
> interchangeable, but the tooling and orchestration infrastructure will not."* Anthropic
> is openly betting the moat is the tooling, not the model. We agree — and we think the
> tooling should be **user-owned**, not lab-owned. Trinity isn't a competitor to LangGraph
> or CrewAI or Pinecone — it sits *above* them, at the layer that decides which lab to
> ask for which kind of question. Keep your modular stack; add a routing layer that
> learns across it. That's the third answer to the binary the article frames.
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

- v1.5 (the MCP-primary routing product + cortex layer) is the *what's next*. Mention
  briefly with a link to `docs/spec-v1.5.md` — ships June 3, 2026. Not the launch
  headline — v1.0 is the ledger / data pipe; v1.5 is the routing turn.
- The personal `/me` lens demo on real data — only mention if I have ≥3 lenses to show.
  An empty `me.md` undersells.
- Hosted leaderboard — opt-in upload not yet wired; v1.5+ if needed.
- Trained-coordinator path is **sunset** (former v2). If someone asks "why aren't you
  training a 7B like Sakana?" answer: their own ablation shows the value is in
  prompt-engineering quality, not routing decision. A flagship with cortex context
  writes better prompts than any 7B. Reopens only if v1.5 ceilings.

---

## Send-with checklist

- [ ] me-card PNG attached (use `trinity-local me-card --out /tmp/me.png` to generate fresh)
- [ ] Repo URL is current (post-pubic-push)
- [ ] LICENSE link in footer of every artifact
- [ ] `trinity-local doctor` output recorded for the demo
- [ ] One real council outcome JSON quoted (not synthetic)
- [ ] Skill discoverability tested in a fresh Claude Code session
