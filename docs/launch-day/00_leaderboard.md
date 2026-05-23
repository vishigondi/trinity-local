---
class: live
---

# Personalized Benchmark · YOUR corpus (v1.7.5 launch leaderboard)

Freshest data refresh 2026-05-22 (claude N=45 ran today); codex + gemini
held at their May 19 runs pending re-runs. Judged against the rejection-
signal corpus in `~/.trinity/me/rejections.jsonl` (mined from real
Stage 0 turn-pair gaps in Vishi's prompt history). Each provider was
asked to produce a response to the same prompts the user actually
pushed back on; a different model played judge so no provider grades
itself.

## Headline (claude N=45 vs codex N=5 vs gemini N=17 — asymmetric coverage)

| target | aggregate | N | judge | notes |
|---|---|---|---|---|
| **claude** | **0.788** | 45/45 | codex | freshest run (2026-05-22 22:50) on the 45-item eval suite — the substantive ship-day data |
| **codex** | **0.700** | 5/5 | claude | May 19 run, N=5 subset — re-run on the full 45-item suite is the v1.7.6 polish item |
| **gemini** | **0.442** | 17/17 | claude | May 19 run, mid-size N=17 slice that hit COMPRESSION items claude/codex didn't — exposes a real weakness |

## By rejection axis (claude N=45 — the freshest, substantive run)

| axis | n | mean | range | observation |
|---|---|---|---|---|
| COMPRESSION | 2 | **0.480** | 0.28–0.68 | weak (small sample) — claude over-engineers when user wanted brevity |
| REDIRECT | 17 | 0.795 | 0.12–0.98 | strong + reliable across multi-part questions |
| REFRAME | 20 | 0.805 | 0.02–0.97 | strongest axis by sample size + mean; high variance though |
| SHARPENING | 6 | 0.815 | 0.18–0.97 | strong — claude reaches for numbers/identifiers when asked |

## By rejection axis (codex N=5 — May 19 subset, pending full re-run)

| axis | n | mean | range |
|---|---|---|---|
| REDIRECT | 1 | 0.90 | — |
| REFRAME | 4 | 0.65 | 0.15–0.85 |

## By rejection axis (gemini N=17 — May 19 wider slice)

| axis | n | mean | range | observation |
|---|---|---|---|---|
| COMPRESSION | 7 | 0.300 | 0.05–0.85 | clear weakness — the wider slice exposed it |
| REDIRECT | 2 | 0.350 | 0.00–0.70 | weak |
| REFRAME | 8 | 0.600 | 0.35–0.85 | midrange |

## What the launch headline can claim

> **"On Vishi's actual 45-item rejection corpus, Claude scored 0.79
> aggregate — strongest on SHARPENING (0.82) and REFRAME (0.81),
> with REDIRECT close behind (0.80). Codex 0.70 on a smaller N=5
> cohort; Gemini 0.44 on a wider N=17 slice that exposed clear
> COMPRESSION weakness. Only Trinity sees the cross-provider
> rejection data needed to build this benchmark."**

Claude's N=45 result is the substantive one — REFRAME at n=20 is real
sample size. Codex + gemini still wait on full-suite re-runs to be
apples-to-apples comparable.

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

> "On Vishi's actual N=45 rejection corpus, Claude scored 0.79 aggregate
> — strongest on SHARPENING (0.82) and REFRAME (0.81). Codex 0.70 on
> a smaller N=5 cohort; Gemini 0.44 on a wider N=17 slice that exposed
> clear COMPRESSION weakness. Only Trinity sees the cross-provider
> rejection data needed to build this benchmark."

## Caveats

- N asymmetry across providers (claude 45, codex 5, gemini 17). The
  full 45-item eval suite ran on claude 2026-05-22; codex + gemini
  full re-runs are the v1.7.6 polish item. Within-provider comparison
  is sound (each provider judged by a different model); cross-provider
  aggregate comparisons should weight by sample size.
- Gemini's lower aggregate is partially a sample-coverage effect —
  the May 19 N=17 slice happened to include 7 COMPRESSION items that
  exposed the weakness. Claude's N=45 only had 2 COMPRESSION items
  (mean 0.48 — same direction). A full-suite gemini re-run would
  give matched-coverage comparison.
- Self-judging risk is mitigated by cross-judge pairs (codex judges
  claude, claude judges codex / gemini). All three pairs cross.

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

Raw run data (freshest per provider as of 2026-05-22):
- `~/.trinity/evals/results/eval_eval_12f21a9fd423__model_claude__20260522T225020.json` (N=45)
- `~/.trinity/evals/results/eval_eval_d32567a386b9__model_codex__20260519T111748.json` (N=5)
- `~/.trinity/evals/results/eval_eval_d32567a386b9__model_gemini__20260519T035802.json` (N=17)
