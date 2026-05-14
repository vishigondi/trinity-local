# Why I stopped trusting any one AI lab with my context

> Draft. Voice belongs to the user. Re-anchored after VentureBeat published "Anthropic
> wants to own your agents' memory, evals, and orchestration — and that should make
> enterprises nervous" (Dec 2025). Publish BEFORE the HN launch — this essay becomes the
> philosophical anchor every subsequent piece of marketing links back to.

---

Last week, Anthropic shipped *Dreaming*. Agents learn from their past sessions, extract
lessons, and improve over time. Harvey reported a 6× task-completion uplift. They also
shipped *Outcomes* (rubric-based evaluation by a separate grader agent) and *Multi-Agent
Orchestration* (specialist sub-agents with independent context windows). The technical
pattern works. The technical pattern is also exactly what I've been building for the past
year — except mine runs locally, across all three labs, with the memory in *my* folder.

That sentence is the entire reason this essay exists.

I have three AI subscriptions and I still copy-paste between tabs like an animal.

Claude is in one terminal. Codex CLI is in another. Gemini CLI is in a browser. None of
them can tell me when the other one is better. None of them can read what I asked the
other one yesterday. None of them can learn that for *my* kind of question, I trust the
one with the cleanest hedge over the one with the boldest claim.

It's not a bug. It's structural. Anthropic isn't allowed to recommend ChatGPT. OpenAI
isn't allowed to recommend Claude. Google isn't allowed to recommend either. The labs
that built the models you trust are commercially prevented from helping you use a
competitor — and the moment you have more than one subscription, the lab that ships the
layer above them is structurally impossible to be a lab. Dreaming makes this more
obvious, not less: Anthropic just shipped session-memory + cross-session learning, and
they shipped it *inside their own runtime*. They had no choice. Cross-provider memory
has to come from someone outside the labs.

So I built it.

## The thing I built

Trinity Local is a CLI that watches all three of your AI tools. Reads the `~/.claude/`
SQLite cache. Reads `~/.codex/`. Reads `~/.gemini/`. Builds one local index over all
your conversations. When you ask it a question it doesn't know how to route — when
you'd otherwise have to guess which lab to bother — it convenes the three of them as a
council, in parallel, and synthesizes one verdict.

The verdict isn't a chat log. It's a structured object:

- **Agreed claims**: what the three models converged on. You can lean on these.
- **Disagreed claims**: where they split. Each disagreement has a *why it matters* note —
  the actual structural difference between the two answers, not just "model X said this."
- **Winner + scores**: a chairman picks one. You can override.

You override by clicking. That click is the only training signal Trinity ever takes.

After ten or so councils, Trinity has built a personal map of which model wins for *your*
kind of question. After fifty, it surfaces something called a `/me` lens — paired
tensions extracted from where you actually pushed back on a model. One of mine reads:

> *leading proxy signal as forecast* vs *official lagging metric as truth*
> failure of one: paranoid pattern-matching, signals everywhere
> failure of the other: consensus follower, lag the move

That's not a personality test. That's the actual tension my taste lives at, distilled
from twenty years of trying to answer hard questions with incomplete data, surfaced
back to me by a tool that watched what I clicked.

## Why local-first

Your transcripts already live on your machine. They always have. `~/.claude/`,
`~/.codex/`, `~/.gemini/` are SQLite caches, sitting on your filesystem, readable by
any process you grant permission to. Trinity reads them. Locally. They never upload.

This is not a privacy theater claim. It's the entire architecture:

- Council fan-out happens directly from your machine to the provider CLIs you already
  authenticated.
- The chairman synthesizes locally; the prompt and the answers stay in `~/.trinity/`.
- Telemetry is opt-in, default off. The only thing that can ever leave is anonymous
  categorical labels: `task_type`, `winner`, `confidence`. No content, ever.
- There's no hosted controller, no API proxy, no account. Trinity is one Python package
  + one MCP server, both subprocess-spawned by your harness.

Break that one time and the brand dies. So we don't.

## Why this is yours forever

The labs are migrating cloud-side. The Claude Code that runs on your laptop today is on
its way to becoming an agent that runs in Anthropic's datacenter. The same is happening
to ChatGPT. The same to Gemini. Each migration is a step toward your *context* —
everything you've ever asked, every preference you've expressed, every taste you've
revealed — becoming someone else's asset.

Right now, today, the SQLite cache is still on your machine. The window for owning your
own memory is open. Trinity is the memory layer for that window.

When (not if) the labs close the cache and move the context cloud-side, you'll still
have `~/.trinity/`. You'll still have the Routing JSON ledger. You'll still have the
`/me` lens — the thing that actually represents what you trust. If you switch labs
tomorrow, your taste comes with you.

That's what *own your memories* means in operational terms. Not "we promise not to
upload them." Not "we have the strongest encryption." Just: the artifact is a folder
on your laptop. We can't take it from you because we don't have it.

## Why the council, specifically

The council shape — three models in parallel, one chairman synthesizing — feels
ceremonial until you've watched it work on something you actually care about.

The thing that surprised me, the first time I ran one against a real engineering
decision: the disagreement was more useful than the consensus. Two models agreed on
the obvious move. The third proposed a reframing that I would have missed entirely. The
chairman noted: *"Codex re-framed the problem from 'how to scale X' to 'how to retire X.'
Worth surfacing because Y's bias toward incremental improvement may have hidden a
cheaper structural answer."*

That note is the whole product in one paragraph. Frontier models don't disagree because
one is wrong and the others are right; they disagree because each has a slightly
different prior over the answer space, and *those priors are the most valuable thing
about them*. A council surfaces the priors. A chat with any single model erases them.

## What Trinity is not

A subtler thing worth naming: Trinity is not a competitor to LangGraph, CrewAI,
Pinecone, DeepEval, or whatever else you've cobbled together for within-Claude
state and within-Claude evaluation. The VentureBeat piece frames the question
as binary — *"ditch your flexible, modular system, or stay locked into it."*
That's a false binary. Trinity is the third answer: keep your modular stack;
add a routing layer that learns *across* it.

The article's deepest sentence is *"models may become interchangeable, but the
tooling and orchestration infrastructure will not."* That's the Anthropic bet
made openly. I agree with the technical claim and disagree with the
ownership conclusion. Yes, tooling will lock you in. So the tooling should
be **user-owned**, not lab-owned. Trinity is what user-owned tooling at the
routing layer looks like — the layer that decides which lab to ask for which
kind of question, with the decision criteria stored in `~/.trinity/cortex/`
that you can grep, version-control, audit, port to a new machine, or share
with your team. None of the labs can ship that, because none of the labs is
allowed to route to a competitor.

For compliance-driven shops: the local-first architecture isn't just a
philosophical preference. Anthropic's hosted runtime means memory + state +
routing all live on Anthropic infrastructure. Some industries legally cannot
deploy that — data residency, BAA, etc. Trinity inside a VPC is a different
shape entirely; the routing patterns stay in your environment.

## What I learned building this

Three architectural commitments I won't compromise on, ever:

1. **Prompts never upload.** No hosted "convenience" tier that changes this. Even when
   v2 lands a hosted-chairman capability, the prompts stay local; only the
   coordination metadata crosses the wire, and only when you explicitly opt in.
2. **No LLM calls outside councils.** Ingest, embedding, theme assignment, search
   ranking, clustering — all pure embeddings + heuristics. The only LLM invocations
   Trinity makes are the council itself: three frontier members + one synthesis call.
3. **Free forever.** The local CLI + MCP server cost nothing to use and require no
   account. If revenue lands later, it lands on top of capabilities free users don't
   need, not on top of capabilities free users had taken away.

Three product commitments worth flagging:

1. **macOS-only at launch.** Not because Trinity can't run elsewhere. Because shipping
   to one platform first means I can make it actually delightful on that platform
   instead of approximately working on three. Linux and Windows when it makes sense.
2. **No social anything until the local thing is great.** The shareable `/me` lens
   PNG is the social object — *one image, no account.* Federated taste, team plans, all
   of that is v2+. The point is to make the single-user experience overwhelmingly
   compelling, then let the network effects compound.
3. **The folder is the API.** `~/.trinity/` is locked at SCHEMA_VERSION = 1. Anything
   in it is yours. You can grep it, version-control it, archive it, replay it on a new
   machine, send it to me as a bug report. If the schema needs to evolve, that's a
   one-shot migration we ship and own.

## What's next

Right now, today, v1 ships. Three commands → first council on your real work. The
launchpad shows you which model has been winning for which kind of question you ask. The
`/me` lens distills it into the paired tensions your taste actually lives in.

Then, in order:

- **v1.5 (ships June 3, 2026): the routing product Claude Code reaches for.** Same
  ledger. MCP-primary surface. When Claude (the agent inside Claude Code) hits a hard
  decision or its own rate limit, it calls `mcp__trinity-local__ask` — Trinity routes
  to your empirically-best model for that flavor of question and dispatches via the
  CLIs you already pay for. Local model fallback (Ollama / MLX) sends easy subtasks
  to free compute. The architecture is two-tier memory: kNN over your past prompts
  (hippocampus) plus routing rules a flagship model extracts from your accumulated
  council outcomes per task-type basin (cortex). Both layers fire at query time; the
  rule generalizes, the episodes calibrate. Brains don't kNN over raw episodes.
  Trinity shouldn't either.
- **v1.6+ (post-v1.5): multi-step orchestration.** `plan_and_execute` for the rare
  case Claude wants Trinity to plan a multi-step workflow (Sakana three-list output —
  who plans, who implements, who verifies). v1.5 ships the routing; v1.6 ships the
  orchestrator. The architecture is the same — a flagship Conductor reads cortex
  context + emits the plan. No training. Just better prompts.
- **The trained-coordinator path is sunset.** When Sakana published their TRINITY
  paper in December (arXiv:2512.04388), I read it three times. Their own 3B vs 7B
  ablation shows both Conductor sizes find the same routing — the 7B wins on
  natural-language prompt quality. A flagship model with retrieval+cortex context
  produces better prompts than any 7B you could train. So I'm not paying 4–8 weeks
  of GPU training for an architecture I can ship in 5 weeks via context engineering.
  If v1.5 hits a real quality ceiling on user data, the training path reopens. Not
  until then.

There's a bigger thesis behind all of it. *Own your context now, because the next
thing you'll need to own is your agent.* The labs are migrating from "the model I rent"
to "the agent that acts for me." Your context — what you've already asked, the lens
your taste encodes, the routing your verdicts taught — 
trusted, what you've rejected — are the raw asset. Dream is the verb that turns them into
the agent's memory: cortex rules, taste lens, routing brain.

Dreaming makes this concrete. In two years, enterprises that adopted Anthropic's
agent stack without architectural resistance won't own the playbook their teams built
up; Anthropic will, in the form of agents trained on the patterns Dreaming extracted
from their sessions. MassMutual has publicly said they won't sign long-term contracts
with any AI vendor for exactly this reason. ProgressiveRobot has started selling
"Anthropic Agent Lock-In" risk audits. The fear has a name now.

Trinity is the architectural alternative that makes the cognitive substrate stay with
the people who built it. The folder is yours. The patterns extracted from it are yours
(`~/.trinity/cortex/routing_patterns.json` — open it in any text editor). The agent
built from them belongs to you, not to the lab whose runtime hosted the consolidation.

But you don't need to buy the bigger thesis to use the v1 thing. v1 is one CLI. Three
labs. One ledger. Your taste.

`pip install git+https://github.com/vishigondi/trinity-local && trinity-local install-mcp`.
Then `/trinity` in Claude Code. Three commands. Free forever. (Post-ship: `pip install
trinity-local` — same package, faster, after PyPI publish lands.)

The repo is open-source MIT on GitHub. The folder is yours. The taste is yours. The
AI you trained should outlive the provider.

—

*Acknowledgements: this was built because I needed it. The architecture decisions cite
council outcomes in the repo — Trinity ratified its own launch readiness against
itself. Yes, it's councils all the way down.*
