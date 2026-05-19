---
class: live
---

# Personalized Benchmark · YOUR corpus (v1.7 launch leaderboard)

Generated 2026-05-15, judged against the rejection-signal corpus in
`~/.trinity/me/rejections.jsonl` (mined from real Stage 0 turn-pair gaps
in Vishi's prompt history). Each provider was asked to produce a response
to the same prompts the user actually pushed back on; a different model
played judge so no provider grades itself.

## Headline (N=20 vs N=4 — larger sample is more honest)

| target | aggregate | N | judge | notes |
|---|---|---|---|---|
| **codex** | **0.737** | 4/5 | claude | early N=5 run, not yet expanded |
| **claude** | **0.661** | 20/20 | codex | full N=20 run; aggregate dropped from N=4's 0.708 as more axes sampled |
| gemini | (quota exhausted) | 0/10 | — | free-tier Gemini quota depleted during launch window; ~22h reset — re-run via repro command below |

## By rejection axis (claude N=20 — the substantive run)

| axis | n | mean | range | observation |
|---|---|---|---|---|
| COMPRESSION | 8 | **0.504** | 0.12–0.90 | weakness — claude over-engineers when user wanted brevity |
| REDIRECT | 2 | 0.800 | 0.78–0.82 | reliable when answer is multi-part and user follows one thread |
| REFRAME | 9 | 0.740 | 0.08–0.97 | high variance — strong when prompt-shape matches the lens |
| SHARPENING | 1 | 0.930 | — | strong (small sample) |

## By rejection axis (codex N=4 — earlier small run)

| axis | n | mean | range |
|---|---|---|---|
| REDIRECT | 1 | 0.85 | 0.85 |
| REFRAME | 3 | 0.700 | 0.55–0.90 |

## What the launch headline can claim

> **"On Vishi's actual 20-item rejection corpus, Claude scored 0.66
> aggregate — strong on SHARPENING (0.93) and REDIRECT (0.80), but
> weak on COMPRESSION (0.50) where it over-engineers when the user
> wanted brevity. Only Trinity sees the cross-provider rejection data
> needed to build this benchmark."**

The COMPRESSION-weak finding IS the kind of personal-benchmark signal
the launch positioning promised. Specific, actionable, structurally
non-refutable.

## What the numbers mean

Each item: target model is asked to produce a response, judge model scores
how well the target's answer matches *the user's substituted-back framing*
(what the user actually wrote when they redirected/reframed the prior
model). Score 1.0 = matches user's lens perfectly; 0.0 = ignores user's
correction entirely; 0.5 = neutral.

Pre-fix (yesterday): every score came back exactly 0.5 because the judge
picker alphabet-defaulted to a local MLX provider that returned empty
stdout. Caught and fixed in commit `ff6af70` — judge now prefers cloud
chairmen (claude/codex/gemini in priority order).

## Headline for the launch tweet/HN

> "On Vishi's actual N=20 rejection corpus, Claude scored 0.66 aggregate
> — strong on SHARPENING (0.93) and REDIRECT (0.80), but weak on
> COMPRESSION (0.50) where it over-engineers when the user wanted
> brevity. Codex at 0.74 on a smaller N=4 cohort. Only Trinity sees
> the cross-provider rejection data needed to build this benchmark."

## Caveats

- N=4 per provider is thin. The 44-item eval set built from
  rejections.jsonl supports larger samples; the launch run is what
  fit in the credit window today.
- Gemini scored zero items because the test rig's free-tier Gemini
  quota was exhausted during the launch window
  (`TerminalQuotaError: You have exhausted your capacity on this model.
  Your quota will reset after ~22h`). The API itself is healthy — the
  user's subscription credits just ran out. Reproduce after the
  quota resets via:
  `trinity-local eval-run --eval-id eval_d32567a386b9 --target gemini --limit 20`
  This is exactly the kind of subsidy-window pressure the launch
  positioning calls out: build the corpus while credits are cheap;
  the corpus has lifetime value once subscriptions tighten.
- Self-judging risk is mitigated by cross-judge pairs (codex judges
  claude, claude judges codex). Until gemini holds up, only those two
  comparisons are real.

## Reproducing

```bash
# Build the eval suite (or use the existing one)
trinity-local eval-build

# Run against each provider
trinity-local eval-run --eval-id eval_d32567a386b9 --target codex --limit 20
trinity-local eval-run --eval-id eval_d32567a386b9 --target claude --limit 20
trinity-local eval-run --eval-id eval_d32567a386b9 --target gemini --limit 20

# View results
trinity-local eval-show --target codex
trinity-local eval-show --target claude
trinity-local eval-show --target gemini
```

Raw run data:
- `~/.trinity/evals/results/eval_eval_d32567a386b9__model_codex__20260516T024142.json`
- `~/.trinity/evals/results/eval_eval_d32567a386b9__model_claude__20260516T022637.json`
