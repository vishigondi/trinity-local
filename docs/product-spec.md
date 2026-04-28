# Trinity Local — Product Spec & GTM Strategy

## The One-Liner

Trinity is a **local observation layer** that watches your AI coding sessions
across providers and surfaces cross-provider insights that no single tool can
see — without running servers, databases, or its own UX.

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

### 1. Cross-Provider Comparison (Council)

> "Were the answers actually different? Which was better? Why?"

When a task matters, you want more than one opinion. Trinity runs the same
prompt through multiple providers, has each peer-review the others' answers
anonymously, and synthesizes a verdict — all without the user manually
copy-pasting between terminals.

**No single provider can do this.** Each provider only sees its own output.

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

### Launch Sequence

**Phase A — Silent Observer (Week 1-2)**

Ship the watcher and digest only. Zero disruption to the user's existing
workflow.

1. User installs: `pip install -e .`
2. User runs: `trinity-local watch-once --notify`
3. Trinity scans their Claude, Codex, Gemini, and Cowork session histories
4. Trinity surfaces: "You used Claude for 12 coding tasks and Codex for 3.
   Codex had 0 errors. Claude had 4. Consider trying Codex for your next
   coding task."
5. User bookmarks the portal page

**No behavior change required.** Trinity just watches and reports.

**Phase B — On-Demand Council (Week 3-4)**

When the user has a task that matters, they can ask Trinity to compare:

1. User creates a bundle: `trinity-local bundle-create "Design the auth system"`
2. User runs council: `trinity-local council-start --bundle <id> --members gemini codex --primary-provider claude`
3. Trinity queries each provider, runs peer review, synthesizes
4. User opens the review page and reads the comparison

**Only invoked when the user explicitly wants a second opinion.**

**Phase C — Autonomous Suggestions (Week 5+)**

The watcher starts making proactive suggestions:

1. Watcher detects a new session in Claude Code
2. Watcher creates a task with a recommendation: "Codex may be better for this"
3. User sees the notification or portal card
4. User clicks to run a council or switch tools

**Gradually earns trust through accuracy.**

### Distribution

1. **GitHub repo** — `pip install` from source
2. **Homebrew formula** — `brew install trinity-local` (future)
3. **Word of mouth** — the multi-CLI power user community is small and tight
4. **Blog post** — "I spent a month tracking which AI coding tool is actually
   best for what. Here's the data." (uses Trinity's own output as the content)

### Success Metrics

- Weekly active users running `watch-once` or `watch-loop`
- Number of council runs per user per week
- Percentage of watcher suggestions the user acts on
- User retention at 30 days (still running the watcher)

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

**Stage 3: Learned Multi-Turn Coordinator (Long-Term)**

The full TRINITY architecture: a coordinator SLM that sees the full transcript
context and selects both agent and role per turn. This requires:

1. **Multi-turn council with transcript feedback** — the coordinator sees prior
   turns and decides the next step (already partially built in council_runner)
2. **sep-CMA-ES optimizer** — offline evolutionary search over the head
   parameters using the watcher's corpus as the evaluation set
3. **Singular value fine-tuning** — adapt a subset of the SLM's layers to
   improve hidden-state separability for routing

This is the end state, but it's not needed until Stage 2 has enough data to
show that routing quality matters.

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
