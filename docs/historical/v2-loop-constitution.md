---
class: historical
---

# Trinity v2 — Loop Constitution (spec — substrate removed, preserved as reference)

> **⚠️ Status update (substrate removed):** The Loop Constitution substrate
> (`frame.py` / `run.py` / `verify_web.py` formerly in `src/trinity_local/loop/`)
> has been **removed from the codebase** as pre-launch simplification. The
> mechanic — *execute → verify → cull → re-verify → commit* — will be rebuilt
> leaner inside `plan_and_execute`. **Status 2026-05-22:** the rebuild
> was queued for v1.7 (task #128), slipped, and was formally sunset in
> the post-launch cleanup pass — running v1.5 on real data showed the
> `ask` + `run_council` ceiling didn't bind hard enough to justify
> rebuilding the orchestration layer; the harness owns multi-step.
> Git history preserves the substrate as an architectural reference.
>
> The architecture below stays as **architectural reference** for v1.6 work.
> The productization plan is replaced by [`spec-v1.5.md`](spec-v1.5.md).
> Reopens only if v1.5 hits a quality ceiling that a trained skill-factory
> could break through.
>
> Substrate ratified by `council_5fbf909119830643` (Codex won, high).
> Compression ratified by `council_7a770b8b78b6bd4e` (Codex won, high).
> Held back from v1 launch per `council_f8174af1be1f646d` (Claude won, high).

## Premise

v1 is the *evidence ledger*. v2 is the *skill factory*.

Models are great at generation, bad at compression. (The irony: models are compression.)
The task is to generate skills. Skills are first-class — callable, named, evictable.

The Loop Constitution names seven stages — `invert → plan → execute → verify → cull → commit
→ evict`. That's not seven steps. It's **two loops with state coupling**, the same
architectural principle that, in 2025, beat the largest CoT models on hardest reasoning
benchmarks with 27M parameters and a thousand examples.

> Inversion, cull, and eviction are the wind.

## The double-loop

```
OUTER LOOP (slow, structural — the frame, taste sets it)
    invert + plan = "what's worth building, what would fail"
    │
    ▼  (frame becomes inner-loop rubric)
INNER LOOP (fast, recurring — small operator, many applications)
    execute → verify → cull → re-verify → commit
    │
    ▼  (drift telemetry feeds back)
OUTER LOOP audit
    eviction = re-run outer when model lands or telemetry widens
```

State flows both ways:
- Outer's `inversions` + `eval_seed` → become inner's verify rubric.
- Inner's `cycles_to_converge`, `cull_volume`, `verify_failures` → trigger outer reframe.

The user's question — *"how to get the meta prompt to continuously run"* — answer: it doesn't.
**The inner loop runs many times within ONE outer frame**; outer reframes only on triggers
(model release, drift past threshold, user explicit reframe).

## Outer loop — `trinity-loop frame`

One chairman call. Inputs: `skill_intent` (string). Outputs: `~/.trinity/skills/<id>/frame.json`.

```json
{
  "skill_id": "skill_abc123",
  "intent": "extract pricing from a SaaS landing page",
  "inversions": [
    "Output is a flat blob with no schema",
    "Pricing values include marketing copy ('starting at') instead of numerics",
    "Handles only one tier, drops Enterprise",
    "..."
  ],
  "eval_seed": "A passing attempt returns one JSON object per pricing tier with fields {name, monthly_usd, annual_usd, billed, included_seats, key_features[]}. Tiers are extracted in source order. 'Contact us' tiers report monthly_usd=null. ...",
  "verifier": "autobrowse",
  "model_baseline": {"claude": "claude-opus-4-7", "gemini": "gemini-3.1-pro-preview"},
  "created_at": "2026-05-07T19:24:42+00:00"
}
```

**Hard requirements** (validated post-parse):
- 3 ≤ `len(inversions)` ≤ 7
- `len(eval_seed) ≥ 80` characters
- `verifier ∈ {"autobrowse", "chairman_rubric"}`

Council ratified: keep one-call framing unless validation fails. **Don't split invert+plan into
two stages by default** (claude+codex agreed; gemini dissented). They're two views of the same
act of taste.

## Inner loop — `trinity-loop run`

State machine in pure Python. State persists to `~/.trinity/skills/<id>/state.json`. Resumes
after crash. The CLI process IS the supervisor — no daemon.

```
state.iteration = 0
while iteration < max_iter:
    iteration += 1

    artifact = execute(frame, state.history)        # 1 chairman call
    verify_result = verify(artifact, frame.eval_seed)  # autobrowse OR rubric chairman
    if not verify_result.passed:
        state.history.append(structured_failure_record)
        continue

    cull_proposal = cull(artifact, verify_result)    # 1 chairman call
    pre_hash  = sha256(artifact)
    post_hash = sha256(cull_proposal.artifact)

    if pre_hash != post_hash:                        # HASH-BASED gate (council eval seed)
        state.history.append({stage:"cull", outcome:"mutated", hash_before, hash_after})
        re_verify_result = verify(cull_proposal.artifact, frame.eval_seed)
        if not re_verify_result.passed:
            state.history.append(re_verify_failed)
            continue
        artifact = cull_proposal.artifact

    commit(artifact, frame.eval_seed)                # writes SKILL.md + eval.json + rationale.md
    return graduated
return failed_to_graduate
```

### State coupling — structured history records

Per `council_7a770b8b78b6bd4e` modification: `state.history` carries **structured records, not
raw failure strings**. Each entry:

```python
{
  "iteration": int,
  "stage": "execute" | "verify" | "cull" | "re_verify" | "commit",
  "outcome": "passed" | "failed" | "mutated" | "noop",
  "reasons": [str, ...],
  "artifact_hash_before": "sha256:...",
  "artifact_hash_after": "sha256:...",
  "cull_proposal_id": str | None,
  "timestamp": "ISO8601"
}
```

Next iteration's `execute` prompt pulls structured fields — last 3 failure records by default
— rather than concatenating raw strings.

### Cull → re-verify gate (the load-bearing piece)

Per Codex's winning eval seed for `council_5fbf909119830643`:

> *Without re-verify, the committed artifact is not the one the test proved — silently breaks
> the entire compression contract.*

The gate is **hash-based**, not boolean (`council_7a770b8b78b6bd4e`):

```python
if sha256(pre_cull) != sha256(post_cull):
    re_verify(post_cull_artifact)
```

Cull no-ops (chairman emits "cull this" but returns the same artifact unchanged) skip the
re-verify call — saves a chairman call.

If re-verify fails, the cull is **discarded**, the pre-cull artifact stays valid, and the
iteration is logged as failed. The loop retries with the structured history including this
failure.

## Verification — Browserbase Autobrowse + chairman-rubric

Per `council_5fbf909119830643`: Autobrowse is the verification adapter. Wrapped at
`src/trinity_local/loop/verify_web.py`:

```bash
npx autobrowse --task <skill_id> --env local --iterations 5
```

`--env local` means headed Chrome, no API key, persistent profile. `--env remote` exists for
bot-protected sites; not the cost-basis path.

Output contract is uniform across both verifiers:

```python
{
  "passed": bool,
  "reasons": [str, ...],
  "skill_md_path": str | None,
  "iterations_used": int,
  "summary": str,
}
```

**Graceful degradation**: when Autobrowse isn't installed (most fresh installs), the wrapper
returns `passed=false` with a structured `not_available` reason. Inner loop falls back to
`chairman_rubric` — the chairman judges the artifact against the eval_seed directly.

## Eviction — outer rerun on triggers

No separate `evict.py` module. Eviction = `trinity-loop reframe` re-runs `frame` against
stale skills.

**Triggers (in order of explicit-ness):**
1. **User explicit**: `trinity-loop reframe --skill <id>`.
2. **Model release**: poll `data/model_candidates.json` (the model-candidate registry)
   on supervisor cron tick. Compare current Claude / Gemini / Codex versions to last-known.
   On bump, mark all skills created on the old version as `stale: true`, schedule re-baseline
   batch.
3. **Telemetry threshold** (post-launch): `cycles_to_converge` past N (TBD by data) signals
   the outer rails were wrong. Reframe.

Re-baseline = run verify + cull on each stale skill with the new model. Skills that fail
re-verify get evicted (folder moved to `~/.trinity/skills/_evicted/`).

Per Claude's dissent in `council_5fbf909119830643`: model-release-triggered mass eviction is
non-negotiable. *"When a new model lands, throw out half"* — the user's stated requirement.

## Skill registry — folders, no separate module

Each graduated skill is `~/.trinity/skills/<skill_id>/`:

```
~/.trinity/skills/skill_abc123/
├── frame.json        — outer-loop output
├── state.json        — inner-loop state machine, last good
├── SKILL.md          — the graduated artifact
├── eval.json         — the test that proved it (eval_seed + verify_reasons)
└── rationale.md      — why this skill exists, failure modes warned about
```

The directory IS the registry. No `registry.py` module. Listing skills = `os.listdir`.
Eviction = move folder. Versioning = `meta.json` sidecar with `created_at`,
`created_with_model`, `last_verified_at`.

## What's explicitly out of scope

- **Anthropic Managed Agents integration**: pricing not disclosed; complementary not
  replacement; revisit when stable.
- **Multi-user skill sharing / cross-machine registry**: paid v2.1 feature per
  `council_f8174af1be1f646d` (launch-strategy ratification). v2 ships as local-only.
- **Generic non-web verifiers** beyond chairman-rubric: add when specific verifier classes
  (code execution, prompt eval, dataset benchmark) earn their place.
- **Telemetry-driven outer reframe** (`cycles_to_converge` threshold): gather data first, set
  threshold from real distributions.

## Status

- **v2-alpha substrate shipped (May 7, 2026)**: `loop/frame.py`, `loop/run.py`,
  `loop/verify_web.py`, `loop/cli.py`. 34 tests pinning the parsers, validators, hash gate,
  and state machine. CLI smoke verified: real chairman call returned 7 inversions + 600-char
  eval_seed on "summarize a markdown doc".
- **Held back from v1 launch** per `council_f8174af1be1f646d`: tease v2 as "the next layer"
  in launch narrative; don't headline it as the product. Ship cross-machine skill registry as
  the v2.1 paid feature once OSS launch lands.

## Critical files

Repo paths (relative to repo root):

- `src/trinity_local/loop/` — package (REMOVED pre-launch — see CHANGELOG; this
  doc is the architectural history kept around in case v1.6 wants to study it)
- `CHANGELOG.md` — v2-alpha section
- `claude.md` — Loop Constitution (v2) section

Runtime council outcomes (in the user's own `~/.trinity/council_outcomes/`):

- `council_5fbf909119830643.json` — substrate ratification
- `council_7a770b8b78b6bd4e.json` — compression + structured history + hash gate
- `council_f8174af1be1f646d.json` — held-back-from-launch decision
