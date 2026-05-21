---
class: live
---

# Trinity Local — Launch Package (post-Dreaming)

> Status: **active**, supersedes the pre-Dreaming launch narrative in `docs/launch.md`.
> Anchor: VentureBeat, Dec 2025 — *"Anthropic wants to own your agents' memory, evals,
> and orchestration — and that should make enterprises nervous."* This package coordinates
> the launch narrative, copy, and the one metric we need to start tracking publicly from
> day-1.

## The 30-day window

The VentureBeat piece (and the Progressive Robot + ClawBlog follow-ups) created an
enterprise category — *vendor-neutral agent memory* — in one news cycle. Trinity is
structurally the simplest answer. The freshness of that signal is measured in weeks;
the launch happens inside that window.

**Ship window:** v1.7 ships within the May 13–16 window (v1.0's scope
plus the v1.5 cortex-consolidation flow landed early — see CHANGELOG
v1.7 entry). The next forward-spec is `docs/spec-v1.6.md`. The
narrative below ships at v1.7 launch.

## The locked positioning

**Hero:** *Your taste, ported. Lives inside Claude Code, Codex CLI, Antigravity, and Cursor.*
**Sub:** *No new app. No service. No API key. Your transcripts never leave your machine.*

**Lead paragraph (the digital-twin pitch):** *You've already chosen between Claude,
Codex, and Gemini a thousand times. Trinity reads those transcripts, learns the
pattern in how you rephrase, judge, and decide — then runs hard questions through
all three in your voice and picks the answer you would have picked.*

**Prior framing** (pre-2026-05-16, retained for context): Hero was *"Stop copy-pasting
prompts. Own your context. Dream your core memories."* Sub was *"One question. Every
model you use. One answer that knows you."* Pivoted to the digital-twin framing
because the polyharness power user reads "councils" as another tool to learn; reads
"your taste, ported" as something working FOR them.

**One-sentence pitch:** *Anthropic just shipped Dreaming. Trinity does it across Claude,
ChatGPT, and Gemini — and the memory dream creates lives in your folder, not theirs.*

**One-paragraph pitch:** *Anthropic, OpenAI, and Google are commercially prevented from
helping you use a competitor. The agent stack they're each building — session-memory,
rubric-eval, multi-agent orchestration — works, but it only works inside their own
runtime. Trinity is what that stack looks like when the runtime is your laptop and the
memory is your folder. Open source, local-first, MIT.*

**Three-paragraph pitch (HN top-of-thread length):** see `docs/launch.md` → "Hacker News
title + opener" — already updated.

**Three-tier framing** (architecture ratified by `council_ff3da1fa84906791`, 2026-05-16):
Skill primary — `/trinity` in Claude Code is the canonical interaction. Pip — the engine
the skill calls. Chrome extension — optional cross-surface capture + one-click UI. Data
in `~/.trinity/` is the invariant contract across all three; tiers differ in *how* you
invoke Trinity, not *what* Trinity computes. Tier-equivalence invariant (NOT
bit-identical): cosine ≥ 0.9999 between backends, identical k-means cluster
assignments, identical chairman picker output under pinned config. See
`docs/three-tier-architecture.md`.

## The defensive framing — "isn't this just LangChain?"

The first HN comment after the post lands will be some variant of *"why isn't this
LangGraph / CrewAI / Pinecone / DeepEval?"* The answer is one sentence and it has to be
internalized across the team:

> **Trinity sits ABOVE the model choice, not BETWEEN your app and a model.** LangGraph
> orchestrates within-Claude state. Pinecone stores within-Claude memory. DeepEval evaluates
> within-Claude output. Trinity decides *which lab to ask in the first place.* You can
> use all of them; they don't conflict. Trinity is the routing layer, not the orchestration
> layer.

The VentureBeat article frames the enterprise choice as binary: *"ditch your flexible,
modular system in favor of an agent platform that brings almost everything in-house?"*
**Trinity is the third answer the article doesn't name** — keep your modular stack; add
a routing layer that learns across labs.

## The compliance angle — for the regulated-industry conversations

VentureBeat: *"This can become a compliance nightmare for some organizations that have
to prove data residency."* This is the hard regulatory wedge that lock-in-as-anxiety
doesn't fully capture.

- Claude Managed Agents → memory + orchestration on Anthropic's hosted runtime → some
  shops legally cannot deploy it
- Trinity → everything in `~/.trinity/` on infrastructure you own → drop it inside your
  VPC and the council outputs never cross your network boundary

For sales conversations with healthcare / financial-services / govt: lead with data
residency. The lock-in conversation is a softer secondary anchor.

## The deepest framing — "models commoditize, tooling locks in"

VentureBeat: *"models may become interchangeable, but the tooling and orchestration
infrastructure will not."* This is the article's most-quoted sentence in the days after
publication; it's the philosophical anchor underneath every "is this a threat?" piece.

Trinity's response: **agreed; therefore the tooling should be user-owned, not lab-owned.**
This single inversion is the entire architectural argument. Lead the founder essay with
it. Bake it into the Twitter thread. Every time someone asks "why does this matter,"
that sentence is the answer.

## The Anthropic-stack alignment table

This table is the single most important asset in the launch — it makes the architectural
parallel crisp without sounding like a knock-off. Use it in: README, HN comment, founder
essay, every social post that includes a diagram.

| What Anthropic shipped | What Trinity does | What's different |
|---|---|---|
| **Dreaming** — agents extract lessons from past sessions, improve over time. Harvey: 6× task completion. | **Cortex consolidation** — flagship extracts routing patterns per basin from accumulated council outcomes. System-computed trust score gates which patterns drive decisions. | Anthropic-hosted vs. runs on YOUR subscription. Single-provider vs. across Claude / GPT / Gemini / local. Memory in Anthropic's infra vs. `~/.trinity/scoreboard/picks.json` you can open in any text editor. |
| **Outcomes** — rubric-based eval by a separate grader agent. | **Lens** — paired-tension evaluation from `me/lenses.json`; pre-fan-out routing + post-fan-out scoring against your taste. | Anthropic-defined rubric vs. your own taste extracted from where you pushed back on a model. |
| **Multi-Agent Orchestration (MAO)** — specialist sub-agents with independent contexts. | **Council** — Claude / GPT / Gemini in parallel; local chairman synthesizes. | Same-lab specialists vs. cross-lab council. Anthropic-owned vs. you-own-the-subs. |

## The one metric we need to track from day 1

Every public claim about Trinity's value over the next 90 days needs a number behind it.
We don't need many — we need **one that's easy to compute, hard to argue with, and gets
sharper as users accumulate councils.** The candidates ranked:

### Recommended: **rate-limit-saves** — # of times Trinity routed around a rate-limited primary

- **What it measures:** the killer-flow win. Every time Claude (the harness) hits its own
  rate limit and Trinity dispatches the work to Codex / Gemini / local instead, that's a
  recorded event.
- **Where it lives:** `~/.trinity/analytics/dispatch_outcomes.jsonl` (NEW) — one line per
  `ask` dispatch with the kind label from `dispatch_errors.py` when retry happened.
- **Why this one:** It directly proves the marketing claim (*"your work continues when
  Claude is rate-limited"*). It's local, no telemetry needed. It compounds as users
  accumulate councils. It's the metric MassMutual / ProgressiveRobot will ask about
  first.
- **Day-90 case study shape:** *"Trinity routed N work-units around rate limits in 90
  days. M of them happened during business hours when blocked work cost the most. Without
  Trinity, those N requests would have been retried after the rate-limit window or
  abandoned."*

### Backup: **cost-saved** — $ value of subtasks routed to local models

- Easy if we know per-token rates per provider; harder if we don't track tokens.
- Less viscerally compelling than rate-limit-saves; harder to attribute.

### Backup: **routing-accuracy** — % of cortex-rule routes the user did NOT override

- Requires more data (need user verdicts to compute) but is the cleanest "is the cortex
  actually learning?" number.

**Decision:** ship rate-limit-saves in v1.5 Week 3 alongside the dispatch error
classification. The plumbing exists (`dispatch_errors.classify_dispatch_failure`); we
just need to write the outcome to an analytics jsonl when a retry happens.

## Day-1 narrative — what publishes when

The launch isn't one event; it's a sequence of artifacts that link to each other and
all point at the same architectural claim.

**T-7 days (pre-launch):**
1. **Founder essay shipped to personal blog** — `docs/founder-essay-draft.md`,
   re-anchored on Dreaming. This is the philosophical anchor every other piece
   links back to.
2. **5 tester DMs sent** — original spec-v1 plan; unchanged. Add the Dreaming hook to
   the message.
3. **Teams interest channel ready** — GitHub Discussions on the trinity-local
   repo (works the moment the repo flips public at T-0; no separate domain
   registration needed). Email fallback: teams@keepwhatworks.com. Goal: every
   enterprise architect searching "Dreaming alternative" / "Anthropic agent
   lock-in" lands here. (Earlier plan: trinity.local/teams as a vanity domain
   waitlist page — deferred; the GitHub-native channel is cheaper to stand up
   and uses the same repo-public-flip gate as the rest of the launch.)

**T-1 day:**
4. **Twitter/X thread drafted** — `docs/launch.md` already has the structure; revise
   to lead with the Dreaming hook in tweet 1.
5. **Product Hunt assets prepped** — me-card PNG + launchpad screenshot + 60-second
   demo video.

**T-0 engineering sequence (run in order before any tweet ships):**

  ```bash
  # 1. Final verification — all guards green on current main
  cd ~/projects/trinity-local
  bash scripts/launch-check.sh               # wraps pytest + doc-consistency + smoke
  # Or run individually:
  #   pytest -q                                  # ~<!-- canonical:test_count -->1605<!-- /canonical --> tests
  #   pytest tests/test_doc_count_consistency.py # <!-- canonical:doc_consistency_guards -->61<!-- /canonical --> doc-consistency guards
  #   pytest tests/test_install_sh_and_update.py # install.sh structural guards
  #   bash -n scripts/install.sh                 # installer syntax check

  # 2. Flip the GitHub repo to public
  gh repo edit vishigondi/trinity-local --visibility public --accept-visibility-change-consequences
  # → every github.com/vishigondi/trinity-local URL in launch copy goes 200

  # 3. Tag v1.7.4 (matches pyproject.toml version)
  git tag -a v1.7.4 -m "Trinity Local v1.7 — shipped May 13–15, 2026"
  git push origin v1.7.4

  # 4. (No PyPI publish — Trinity ships as a git clone via curl-bash; see
  #    docs/INSTALL-pip.md "Why no PyPI publish?" for the architectural reasons.)
  #    Verify the install.sh works end-to-end on a fresh machine:
  curl -fsSL https://raw.githubusercontent.com/vishigondi/trinity-local/main/scripts/install.sh | bash
  trinity-local status    # everything green

  # 5. Verify the live state
  curl -sf -o /dev/null -w "%{http_code}\n" https://github.com/vishigondi/trinity-local # → 200
  curl -sf -o /dev/null -w "%{http_code}\n" https://raw.githubusercontent.com/vishigondi/trinity-local/main/scripts/install.sh # → 200
  curl -sf -o /dev/null -w "%{http_code}\n" https://raw.githubusercontent.com/vishigondi/trinity-local/main/schemas/council_outcome.schema.json # → 200

  # 6. Generate the launchpad screenshot with FRESH eval numbers
  trinity-local portal-html
  trinity-local eval-share --target gemini  # produces the leaderboard PNG for tweets
  # (the v1.7 `stats` + `metric` marketing-voice commands were retired 2026-05-17
  #  pre-launch; the eval-share card is the launch-ready shareable artifact.)
  ```

**T-0 day (launch — May 13–15):**
6. **HN Show HN post goes live** — title and first comment per `docs/launch.md` (now
   updated with Dreaming hook).
7. **Twitter thread posts** — 1 tweet/hour for the first 6 tweets, then the rest
   queued.
8. **Founder essay reshared** with the launch as the proof point.

**T+1 day to T+7:**
9. **Reply to every HN comment** for the first 48 hours.
10. **First case study post** — *"How Trinity routed N requests around a Claude
    rate-limit storm in my own usage in week 1"* — assuming the rate-limit-saves
    counter has data by then.

**T+30 to T+90:**
11. **First external case study post** — recruit one tester to share their numbers.
    Even a small-team usage report gets traction in the post-Dreaming news cycle.
12. **Enterprise outreach** — direct ping to the 5 enterprises named in the
    VentureBeat / ProgressiveRobot pieces. Subject: *"You named vendor lock-in
    last month. Trinity is the architectural answer."*

## The risk we're acknowledging head-on

Anthropic ships Dreaming with audited production deployments (Harvey, Wisedocs, Netflix).
Trinity ships with a personal-use story. The architectural argument is sharper than
Anthropic's; the production-deployment proof is not. **By T+90 we need at least one
case study** — even small. Founder-self-use is acceptable for T+30 if the metric is
clean.

This is why the rate-limit-saves metric ships in v1.5: it's the cleanest single number
that turns "I built this for myself" into a case study other people can verify.

## Cross-references

- Tagline + brand: `claude.md` Project Identity, `README.md` hero
- HN post copy: `docs/launch.md` "Hacker News title + opener"
- Founder essay (the philosophical anchor): `docs/founder-essay-draft.md`
- Active next-trajectory spec (cortex implementation): `docs/spec-v1.5.md`
- v1.0 launch contract: `docs/spec-v1.md`
- v2 sunset reasoning: `docs/spec-v2.md` sunset header
