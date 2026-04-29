# Trinity Local — Product Spec & GTM Strategy

## The One-Liner

Trinity is a **council-first intelligence layer**: it compares real tasks
across multiple providers, learns your taste from the choices you make, and
turns that cross-provider memory into routing, workflow, and social artifacts
that no single provider can generate.

The council is the engine. The constitution is the moat. The social payload is
the personal radar chart.

---

## Architectural Philosophy

### The Three Rules

**1. You are not a UX. You are a nervous system.**

Claude Code, Gemini CLI, Codex CLI, and Cowork already own the user experience.
They have terminals, editors, agent loops, and tool-use pipelines. Trinity does
not compete with any of them. Trinity watches their output, compares it, and
sends signals back — via notifications, static pages, and Shortcuts.

**2. Nothing runs unless something changed.**

No resident server. No database. No daemon taxing the machine's CPU or RAM
while the user works. Trinity loads **async**: a file watcher polls transcript
directories on a schedule (or on-demand), writes JSON files, and exits.
Automations and Shortcuts bridge file state to actions. Everything is
event-driven, not poll-driven at the UX layer.

**3. Only surface what a single provider cannot.**

A single CLI already tells you what it thinks. Trinity's value is the **delta**
— the things that become visible only when you can see across all providers:

- Provider A gave a different answer than Provider B
- You keep switching from A to B for this type of task
- The model behind Provider A silently changed and its quality shifted
- You've done this exact workflow 4 times across 3 tools — it should be automated
- Provider B would have been faster and cheaper for this task kind

If a single CLI can already surface the information, Trinity should not
duplicate it.

---

## What Trinity Uniquely Solves

These are problems that **require multi-provider observation** and cannot be
solved by any individual CLI, no matter how good it gets:

### 1. Constitution Extraction Through Council

> "Were the answers actually different? Which was better? Why?"

When a task matters, you want more than one opinion. Trinity runs the same
prompt through multiple providers, has each peer-review the others' answers
anonymously, and synthesizes a verdict — all without the user manually
copy-pasting between terminals.

But the real product: each Council run produces `(prompt, response_A,
response_B, peer_review, your_judgment)`. That's RLHF data harvested from your
own work. Trinity uses this pairwise judgment to extract a scalar taste
function that learns to score any response against your constitution.

The provider comparison is the cover story. The taste extraction is the moat.

**No single provider can do this.** Each provider only sees its own output. Only
you know which answers actually match your taste.

### 2. Behavioral Routing Intelligence

> "You tried this in Claude and switched to Codex. That's the 4th time."

Trinity watches transcript histories across all tools. When it detects a
pattern — repeated switches, abandoned sessions, tasks that always end up in a
particular provider — it learns which tool is actually best for each task shape.

**No single provider tracks your cross-tool behavior.**

### 3. Silent Model Drift Detection

> "Claude's coding quality on your repo dropped this week vs last week."

Providers silently update models, change routing, and adjust behavior. Trinity
tracks exact model IDs, CLI versions, and outcome signals over time. When the
same task kind starts producing worse results from a previously-strong
provider, Trinity surfaces it.

**No single provider will tell you its own model got worse.**

### 4. Workflow Repetition Detection

> "You've done this research → code → verify loop 5 times. Want a Shortcut?"

Trinity sees the full arc of a task across sessions and providers. When it
detects a repeated multi-step pattern, it suggests automating it with a macOS
Shortcut or a Cowork workflow.

**No single provider sees the task across its own session boundary, let alone
across other tools.**

### 5. Cost & Time Comparison

> "Gemini solved this research task in 12 seconds. Claude took 48 seconds for
> comparable quality."

Trinity records latency and token usage per provider per task kind. Over time,
it builds a picture of which provider is fastest and cheapest for each class of
work.

**No single provider benchmarks itself against competitors.**

---

## What Trinity Is NOT

- **Not a CLI wrapper.** Trinity does not replace `claude`, `gemini`, or
  `codex`. It does not own the terminal session.
- **Not an orchestrator.** The `run` command (Thinker/Worker/Verifier loop)
  is a prototype, not the product. Council is the high-value path.
- **Not a server.** No `localhost:8080`. No WebSocket. No database. Files only.
- **Not an always-on daemon.** The watcher runs on schedule or on demand, then
  exits. It costs zero resources when idle.

---

## Current Feature Audit

### ✅ Inside the Pattern (Keep & Strengthen)

| Feature | Why It Fits |
|---------|------------|
| **Transcript ingestion** (4 providers) | Core observation layer — reads what CLIs produce |
| **Session feature extraction** | Compact derived signals, not raw transcripts |
| **Council with peer review** | Cross-provider comparison — the flagship capability |
| **Task & action lifecycle** | Durable file-backed state, no database |
| **Watcher (watch-once / watch-loop)** | Async event detection from file changes |
| **macOS Shortcuts dispatch** | Native automation bridge, no server |
| **Static portal page** | Bookmarkable, no backend, Shortcuts-driven |
| **Notifications** | Lightweight signal delivery, native OS integration |
| **Prompt bundles** | Reusable task packaging for council and routing |
| **Workflow suggestion detection** | Surfacing automation opportunities from behavior |

### ⚠️ Outside the Pattern (Reconsider or Deprecate)

| Feature | Problem |
|---------|---------|
| **`run` command** (Thinker/Worker/Verifier loop) | This IS a UX layer — it runs providers in a multi-turn loop, competing with what Claude Code and Codex already do natively. The user should just use their CLI directly. |
| **`recommend` command** (simple text output) | Too thin to be useful — prints one sentence. The real value is the watcher surfacing recommendations asynchronously. |
| **Scoreboard as runtime system** | `update_provider_score()` is called during every provider invocation in `run_task()`, doing file I/O on every turn. Scoring should happen during watcher analysis, not during interactive use. |
| **`prompts.py` role instructions** | Thinker/Worker/Verifier role prompts are part of the `run` command's orchestration layer. If `run` is deprecated, these go with it. |
| **`coordinator.py` heuristic routing** | Only used by `run`. Council and watcher don't use the Thinker/Worker/Verifier coordinator at all. |

### 🔴 Missing But Should Exist

| Feature | Why It Matters |
|---------|---------------|
| **Model drift detection** | Track `(provider, model_id, task_kind) → outcome_score` over time. Alert when a previously-strong combination degrades. Only possible with multi-session history. |
| **Session cost aggregation** | Sum token costs per task, per provider, per week. Show "Claude cost you $4.20 on coding this week, Codex cost $1.80 for similar quality." |
| **Cross-provider task completion tracking** | Did the user finish the task? Did they abandon it and reopen in another tool? This is the strongest routing signal and it's currently untracked. |
| **"What would X have said?" post-hoc review** | After a task completes in one provider, cheaply ask another to review the output. This is a lightweight council that costs one extra call, not three. |
| **Weekly digest notification** | A periodic summary: best provider per task kind this week, total sessions, total cost, drift alerts, workflow suggestions. Surfaced as a single Notification or static page. |
| **Automatic council trigger on disagreement** | When the watcher sees the same task attempted in two providers with different outcomes, automatically escalate to a full council. |
| **Shortcut installer** | Generate a downloadable `.shortcut` file so the user doesn't have to manually create the Trinity Dispatch shortcut. |

---

## GTM Strategy

### Target User

**Power users who already use 2+ AI coding CLIs daily.** They:
- Have Claude Code, Codex, and/or Gemini CLI installed
- Switch between tools based on gut feeling
- Don't have data on which tool is actually better for what
- Lose time re-trying tasks in a second tool when the first fails
- Can install a Python package and run a terminal command

### Positioning

> "Your AI tools don't talk to each other. Trinity watches all of them and
> tells you things none of them can."

### Launch: Council-First

The blog post writes itself:

> "I ran 50 of my favorite prompts through 4 AI coding tools. I had them peer-
> review each other anonymously. The rankings surprised me. Here's the data —
> run it on your own prompts."

The social version of the same launch is even stronger:

> "I ran my real prompts through multiple AI tools. Trinity learned which
> models actually win on my work. Here are my radar chart, my battle cards,
> and my taste profile. Run it on your own prompts."

That **is** the product. Ship Council first. The watcher and digest are the
scaffolding.

**Why this order:**

1. **Council is generative.** It produces a new artifact (cross-provider verdict)
   that didn't exist before. Watcher and digest are diagnostic.

2. **Council extracts constitutional data.** Every run feeds pairwise judgment
   into the taste function. This is the actual moat.

3. **Council is the proof.** k-NN advisory shows 38.7% reroute recall from
   behavioral signal (heuristic: 0%). That gap is everything. Lead with it.

4. **Council creates social objects.** Radar charts, battle cards, weekly
   reports, and taste profiles are far more viral than workflow automation.

**Phase A — Constitution Extraction (Launch)**

1. User installs: `pip install -e .`
2. User creates a bundle: `trinity-local bundle-create "Design the auth system"`
3. User runs council: `trinity-local council-start --bundle <id> --members gemini codex --primary-provider claude`
4. Trinity queries each provider, runs peer review, synthesizes a verdict
5. User opens the review page, sees (prompt, 4 responses, peer feedback, ranking)
6. User indicates which answer they prefer — this feeds the constitution learner
7. Trinity turns that choice into:
   - a council result artifact
   - a winner history
   - a future radar/taste-profile signal

**Every Council run produces RLHF data.**

**Phase B — Autonomous Suggestion (Week 2+)**

Once you have 10+ Council runs, the watcher learns your taste:

1. Watcher detects a new session in Claude
2. Watcher runs `(prompt, response)` through the learned constitution scorer
3. If confidence is low, suggests running a Council: "I'm not sure about this one"
4. If confidence is high, routes proactively: "Gemini usually handles this better"

**Gradually earns trust as the constitution matures.**

**Phase C — Silent Observation (Week 1 onward, parallel)**

The watcher runs continuously (or on-demand):

1. Scans session histories across all providers
2. Detects switches, abandoned sessions, repeated patterns
3. Surfaces: cost comparison, silent model drift, workflow automation opportunities
4. Portal and digest are always available

**Scaffolding, not headline.**

### Distribution

1. **GitHub repo** — `pip install` from source
2. **Homebrew formula** — `brew install trinity-local` (future)
3. **Word of mouth** — the multi-CLI power user community is small and tight
4. **Blog post** — "I spent a month tracking which AI coding tool is actually
   best for what. Here's the data." (uses Trinity's own output as the content)

### Success Metrics

**Product Proof (Already Achieved)**

- **k-NN advisory reroute recall: 38.7%** (heuristic: 0%)
- **Needs-council precision: 98.4%** (heuristic: 60%)
- **Top-2 provider accuracy: 99.5%**
- **NN agreement on high-confidence suggestions: 96.6%**

These metrics prove the core claim: behavioral signal embedded in hidden states
beats keyword routing by an infinite margin (0% → 38.7% is undefined
improvement). The TRINITY paper validates that this generalizes to multi-turn
orchestration. We don't need multi-turn to prove the constitution exists; we
already have it.

**User Metrics (Tracking)**

- Weekly active users running `watch-once` or `watch-loop`
- Number of council runs per user per week
- Constitution maturity: `switch_after_acted_rate` (how often the ranker's
  suggestion is followed by a later switch)
- User retention at 30 days (still running the watcher)

**Social Metrics (Future)**

- Radar generation rate
- Battle card generation rate
- Repeat council rate
- Taste profile stability
- Export/share intent proxy for council and profile artifacts

### Telemetry Model

Public benchmarking should use an **opt-in summary-sharing model**, not raw
transcript upload:

- consent during install
- editable later from Launchpad settings
- `launchpad_view` event on Launchpad open
- `elo_snapshot` upload only when Elo changed or gone stale
- no raw prompts, outputs, file paths, or repo contents by default

See [telemetry-spec.md](telemetry-spec.md) for the event schema and upload
cadence.

## Product Priorities

Ranked by usefulness and takeoff potential:

1. **One-click Council**
2. **Watcher-triggered Council**
3. **Post-council preference learning**
4. **Personal model radar chart**
5. **Council battle cards**
6. **AI taste profile**
7. **Best-provider recommendation before the user switches**
8. **Weekly model report**
9. **Council-to-worker handoff**
10. **Workflow suggestion**

Council is the first win. Radar is the breakout object. Watcher is how the
system compounds.

---

## Simplicity Principles

1. **One file = one entity.** Tasks, actions, bundles, and outcomes are each a
   single JSON file. No joins. No foreign keys. No schema migrations.

2. **Append-only logs for history.** JSONL files for runs, launches, and
   council outcomes. Never rewrite history.

3. **Static HTML for UI.** The portal page is regenerated from file state.
   No React. No build step. No WebSocket. Open in any browser.

4. **Shortcuts for dispatch.** `shortcuts://` URLs bridge static HTML to local
   command execution. One Shortcut handles all actions.

5. **Notifications for urgency.** macOS native notifications for time-sensitive
   signals. Everything else can wait for the portal.

6. **CLI for power users.** Every operation is a `trinity-local <subcommand>`.
   No configuration UI. No setup wizard.

7. **Zero dependencies.** Python stdlib only. No pip install surprises.

---

## Roadmap to the TRINITY Paper

[The TRINITY paper](https://arxiv.org/html/2512.04695v1) (Sakana AI, 2025)
demonstrates that a 0.6B SLM + 10K-parameter linear head can coordinate
multiple LLMs with state-of-the-art results (86.2% on LiveCodeBench), beating
every individual model in the pool. Trinity Local's architecture is a natural
stepping stone toward this.

### What the Paper Does

| Component | TRINITY Paper | Trinity Local (Today) |
|-----------|--------------|----------------------|
| **Coordinator** | Qwen3-0.6B SLM + 10K linear head | `_guess_task_kind()` keyword matching |
| **Hidden states** | Penultimate-token embedding from SLM | None — prompt text features only |
| **Role assignment** | Learned per-turn (T/W/V logits) | Fixed sequence or heuristic |
| **Agent selection** | Learned per-turn (L agent logits) | `config.json` preference lists |
| **Training** | sep-CMA-ES (evolutionary, ~20K params) | No training — heuristic rules |
| **Transcript** | Full multi-turn context fed back | Council only; watcher is observation-only |
| **Evaluation** | Binary terminal reward (pass/fail) | `OutcomeSignals` (completed, errors, etc.) |

### The Gap: What We Need to Build

The paper's key insight is **you don't need a smart coordinator — you need a
small model whose hidden states are rich enough for a tiny head to make good
routing decisions.** The coordinator's generated text is thrown away; only the
hidden-state → logit mapping matters.

This maps cleanly to trinity-local's architecture:

```
TRINITY Paper                    Trinity Local Equivalent
─────────────                    ─────────────────────────
User query                   →   Prompt text from transcript ingestion
SLM hidden state h(s)        →   MLX model embedding (local, free)
Linear head fθ(h)            →   10K-param routing head (new)
Agent logits (L agents)      →   Provider selection (claude/gemini/codex/mlx)
Role logits (3 roles)        →   Council mode selection (route/council/review)
sep-CMA-ES training          →   Offline optimization from watcher corpus
Binary reward R(τ)           →   Task completion signal from watch_runtime
```

### Three-Stage Progression

**Stage 1: Heuristic (Today)**

The current `HeuristicCoordinator` uses keyword matching and config-driven
preferences. This is sufficient for the watcher's recommendation system and
for the council's provider selection. No ML required.

**Stage 2: Embedding-Based Router (Near-Term)**

Replace keyword matching with **MLX embeddings**. Run the local Qwen3-0.6B (or
any small MLX model) to produce a hidden-state vector for each incoming prompt.
Train a small linear head (scikit-learn or raw numpy) on the existing corpus
of `SessionFeatures` + `OutcomeSignals` to predict:

- Best provider for this prompt shape
- Whether to route directly or escalate to council
- Expected completion probability per provider

This is **local, free, and fast** — the MLX model runs in <100ms on Apple
Silicon and produces a 1024-dim vector. The head is <10K params.

Training data comes from the watcher's existing corpus:
- **Positive signal:** User completed the task in this provider
- **Negative signal:** User abandoned and switched to another provider
- **Council signal:** Council peer review ranked provider A > provider B

No external API calls needed for training. No labeled dataset needed — the
watcher generates weak labels continuously.

**Stage 3: Constitution as Licensable Artifact (Long-Term)**

Once you have learned your constitution (via Stage 2 + continuous Council runs),
you can export it and let others instantiate their own constitution using your
compiler.

The API surface is minimal:

```
POST /compile
  body: { pairs: [{prompt, a, b, winner, reasoning}, ...] }
  returns: { constitution_id, scalar_endpoint }

POST /score
  body: { prompt, response, constitution_id }
  returns: { score, percentile }
```

That's the whole product. Two endpoints.

- **`/compile`** ingests your taste data (from Council runs, watcher signals,
  any labeled pairwise judgments) and trains a small linear head.
- **`/score`** judges any (prompt, response) pair against a learned constitution.

Everything else — routing, Council orchestration, agent orchestration — is
built on top of `/score` by other people. You don't orchestrate agents. The
constitution is what you ship.

This is why you can stay local and free forever. You license the constitution,
not the coordinator.

**Why not multi-turn coordinator?** The paper trains on a fixed eval set
(LiveCodeBench). You have a continuous behavioral signal, which is strictly
more valuable. A learned ranker refreshed on 1,000+ examples is plausibly better
than a fixed SLM. Don't chase the paper's sophistication until `switch_after_acted_rate`
stops improving on its own.

### What We Can Reuse from the Paper

1. **Tri-role protocol** — We already have Thinker/Worker/Verifier. The paper
   validates that this role decomposition is genuinely useful (removing it
   hurts performance by 6+ points).

2. **Hidden-state separability** — The paper shows that SLM hidden states are
   nearly perfectly linearly separable by task type. This means even a
   tiny linear head works. We can verify this locally with t-SNE on MLX
   embeddings of our own prompts.

3. **sep-CMA-ES** — The paper provides a complete optimization recipe that
   works under tight budget constraints (1.5K–40K evaluations for 10K params).
   Our corpus of ~100–1000 session features is in this range.

4. **Penultimate token trick** — Use the second-to-last token's hidden state,
   not the final EOS token. The paper shows this matters significantly.

### What We Should NOT Copy

1. **Running the coordinator as a UX loop.** The paper's coordinator runs
   providers in a multi-turn conversation. In our architecture, the CLIs own
   the conversation. The coordinator should run **offline during watcher
   analysis**, not inline during the user's session.

2. **Full SLM text generation.** The paper discards the coordinator's generated
   text entirely. We should too — we only need the hidden state vector. This
   means we can use `mlx_lm` in embedding-only mode, skipping generation
   entirely and running 10x faster.

3. **Closed-source model pool.** The paper uses GPT-5, Gemini 2.5 Pro, and
   Claude 4 Sonnet. We should keep our pool flexible — the local routing
   decision should work with whatever CLIs the user has installed.

---

## Trinity and the Broader Pattern

This architecture is isomorphic to earlier work on spatial taste and pattern
selection (Kintsugi / IPCo):

| Layer | Trinity (Coding Taste) | IPCo (Spatial Taste) |
|-------|------------------------|----------------------|
| **Observation** | Watcher scans transcripts | Usage telemetry of pattern books |
| **Pairwise judgment** | Council forces cross-provider comparison | Pattern book peer review (curator selection) |
| **Constitution extraction** | k-NN learns routing from (prompt, response) pairs | SLM learns plan selection from (site, pattern) pairs |
| **Taste licensing** | `/score` endpoint judges code | Design system judges spatial instantiations |

The pattern: **give away the artifact (transcripts/patterns), license the
constitution that learned to evaluate artifacts.**

This is why Trinity can stay free. The moat is the taste function, not the
router or the digest. The constitution is what scales to other coding domains,
other users, and eventually other modalities.

Den Outdoors is not Trinity's precedent because their plan selection is best.
Den is the precedent because their selection function over plans is isomorphic
to what Trinity learns — you're borrowing their constitution until you have
enough pairwise data to formalize your own.
