# Personalized Benchmark · YOUR corpus (v1.7 launch leaderboard)

Generated 2026-05-15, judged against the rejection-signal corpus in
`~/.trinity/me/rejections.jsonl` (mined from real Stage 0 turn-pair gaps
in Vishi's prompt history). Each provider was asked to produce a response
to the same prompts the user actually pushed back on; a different model
played judge so no provider grades itself.

## Headline

| target | aggregate | judge | items |
|---|---|---|---|
| **codex** | **0.737** | claude | 4/5 |
| **claude** | **0.708** | codex | 4/5 |
| gemini | (API outage) | — | 0/10 |

## By rejection axis

### codex (judge=claude)

| axis | n | mean | range |
|---|---|---|---|
| REDIRECT | 1 | 0.85 | 0.85 |
| REFRAME | 3 | 0.700 | 0.55–0.90 |

### claude (judge=codex)

| axis | n | mean | range |
|---|---|---|---|
| REDIRECT | 1 | 0.78 | 0.78 |
| REFRAME | 3 | 0.683 | 0.25–0.92 |

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

> "On Vishi's actual prompt corpus, Codex scored 0.74 and Claude scored
> 0.71 — judged by the OTHER model against the rejection-signal pattern
> only Trinity captures. Only Trinity sees the cross-provider rejection
> data needed to build this benchmark."

## Caveats

- N=4 per provider is thin. The 44-item eval set built from
  rejections.jsonl supports larger samples; the launch run is what
  fit in the credit window today.
- Gemini scored zero items because its CLI errored on every dispatch
  attempt during the launch window (`Error when talking to Gemini API`).
  Reproduce after the API recovers via:
  `trinity-local eval-run --eval-id eval_d32567a386b9 --target gemini --limit 20`
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
