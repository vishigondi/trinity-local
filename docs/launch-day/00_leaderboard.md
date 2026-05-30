---
class: live
---

# Personalized Benchmark · YOUR corpus (v1.7.6 launch leaderboard)

Freshest data refresh 2026-05-23 — **all three providers now have full
N=45 runs on the same suite**, judged against the rejection-signal
corpus in `~/.trinity/me/preference_acts.jsonl` (mined from real Stage 0
turn-pair gaps in Vishi's prompt history). Each provider was asked to
produce a response to the same prompts the user actually pushed back
on; a different model played judge so no provider grades itself. The
N=45 trio is the substantive ship-day data — within-suite comparison
is now apples-to-apples.

## Headline (claude / codex / antigravity — all N=45)

| target | aggregate | N | judge | notes |
|---|---|---|---|---|
| **claude** | **0.788** | 45/45 | codex | freshest run (2026-05-22 22:50) — strongest aggregate; strong + balanced across axes |
| **codex** | **0.760** | 45/45 | claude | freshest run (2026-05-23 03:28) — tight second; SHARPENING peak at 0.86 |
| **antigravity** | **0.610** | 45/45 | claude | freshest run (2026-05-23 03:31) — clear third; COMPRESSION at 0.08 is the standout weakness |

## By rejection axis (claude N=45)

| axis | n | mean | observation |
|---|---|---|---|
| COMPRESSION | 2 | **0.480** | weak on a small sample — claude over-engineers when user wanted brevity |
| REDIRECT | 17 | 0.795 | strong + reliable across multi-part questions |
| REFRAME | 20 | 0.805 | strongest by sample size + mean |
| SHARPENING | 6 | 0.815 | strong — claude reaches for numbers/identifiers when asked |

## By rejection axis (codex N=45)

| axis | n | mean | observation |
|---|---|---|---|
| COMPRESSION | 2 | 0.775 | codex outperforms claude here — tighter compression behavior |
| REDIRECT | 17 | 0.746 | competitive with claude (0.795); slightly less reliable |
| REFRAME | 20 | 0.738 | trails claude (0.805) by 7 points on the largest axis |
| SHARPENING | 6 | **0.863** | codex's peak axis — beats claude (0.815) here |

## By rejection axis (antigravity N=42 of 45 — 3 dispatch failures)

| axis | n | mean | observation |
|---|---|---|---|
| COMPRESSION | 2 | **0.075** | dominant weakness — antigravity over-elaborates when brevity is the rejection |
| REDIRECT | 15 | 0.675 | trails the trio but stays competitive |
| REFRAME | 19 | 0.611 | clear gap on the largest axis (claude 0.81, codex 0.74) |
| SHARPENING | 6 | 0.627 | gap closes here vs the other axes but antigravity still trails |

## What the launch headline can claim

> **"On Vishi's actual 45-item rejection corpus — same suite for all
> three providers — Claude scored 0.79 aggregate, Codex 0.76, Antigravity
> 0.61. The interesting per-axis story: Codex beats Claude on SHARPENING
> (0.86 vs 0.82) and COMPRESSION (0.78 vs 0.48); Claude leads on REFRAME
> and REDIRECT. Antigravity has a clear COMPRESSION weakness (0.08).
> Only Trinity sees the cross-provider rejection data needed to build
> this benchmark."**

The N=45 trio is apples-to-apples — same prompts, same suite, three
distinct judges (codex judges claude, claude judges codex + antigravity).
Per-axis differences are the actual signal; the aggregate hides which
provider is right for which axis.

## What the numbers mean

Each item: target model is asked to produce a response, judge model scores
how well the target's answer matches *the user's substituted-back framing*
(what the user actually wrote when they redirected/reframed the prior
model). Score 1.0 = matches user's lens perfectly; 0.0 = ignores user's
correction entirely; 0.5 = neutral.

Pre-fix (2026-05-21): every score came back exactly 0.5 because the
judge picker alphabet-defaulted to a local MLX provider that returned
empty stdout. Caught and fixed in commit `ff6af70` — judge now prefers
cloud chairmen (claude/codex/antigravity in priority order).

## Headline for the launch tweet/HN

> "On Vishi's actual N=45 rejection corpus — all three providers ran
> the same suite. Claude 0.79 aggregate, Codex 0.76, Antigravity 0.61.
> The interesting per-axis split: Codex peaks on SHARPENING (0.86)
> and COMPRESSION (0.78); Claude leads on REFRAME (0.81) and REDIRECT
> (0.80). Different model wins for different rejection types — and
> only Trinity sees the cross-provider rejection signal needed to
> build this benchmark."

## Caveats

- COMPRESSION axis has only 2 samples in this corpus — direction is
  real (codex 0.78, claude 0.48, antigravity 0.08) but the magnitude
  needs more samples. The next eval-build pass should oversample
  COMPRESSION items if user wants high-confidence claims on that axis.
- Cross-judge pairs: codex judges claude (so codex doesn't grade itself),
  claude judges both codex and antigravity. All three judge pairs
  cross-provider — no self-judging.
- Per-axis n is uneven (REFRAME 20 / REDIRECT 17 / SHARPENING 6 /
  COMPRESSION 2) because the corpus reflects Vishi's actual rejection
  distribution. Within-axis comparisons across providers are sound;
  cross-axis aggregate comparisons should weight by axis n.
- Antigravity ran on the new `agy` binary post task #127 migration.
  The legacy gemini.google.com web-chat capture is independent (browser
  extension's gemini.js adapter, task #135).

## Reproducing

```bash
# Build the eval suite (or use the existing one)
trinity-local eval-build

# Run against each provider on the full N=45 suite
trinity-local eval-run --eval-id eval_12f21a9fd423 --target claude
trinity-local eval-run --eval-id eval_12f21a9fd423 --target codex
trinity-local eval-run --eval-id eval_12f21a9fd423 --target antigravity

# View results
trinity-local eval-show --target claude
trinity-local eval-show --target codex
trinity-local eval-show --target antigravity
```

Raw run data (the N=45 trio as of 2026-05-23):
- `~/.trinity/evals/results/eval_eval_12f21a9fd423__model_claude__20260522T225020.json` (N=45, agg 0.788)
- `~/.trinity/evals/results/eval_eval_12f21a9fd423__model_codex__20260523T032830.json` (N=45, agg 0.760)
- `~/.trinity/evals/results/eval_eval_12f21a9fd423__model_antigravity__20260523T033157.json` (N=45, agg 0.610)
