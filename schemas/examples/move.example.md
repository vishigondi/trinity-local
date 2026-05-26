---
name: tighten verbose bullet lists
description: Collapse multi-bullet lists into a single direct sentence when the user has shown they prefer prose.
trinity_promoted_from:
- r_017
- r_019
- r_021
trinity_basin_id: basin_42
trinity_promoted_at: 2026-05-25T17:42:00+00:00
trinity_alpha: 8
trinity_beta: 2
trinity_execution_count: 8
trinity_t1_lexical_score: 0.42
trinity_t2_embedding_score: 0.81
trinity_t3_chairman_score: 0.78
trinity_eval_baseline: 0.78
trinity_success_contexts:
- basin_42
- basin_47
trinity_failure_contexts: []
trinity_generalizability_score: 0.65
trinity_lens_tensions_addressed: 2
---

## When to apply

User's last turn rejected a bulleted response by re-asking the same question
or by typing a direct prose follow-up. Look for: 3+ bullets in the prior
assistant turn; user's next turn shorter than the assistant's turn / 4;
no "expand" / "more detail" hedges.

## How to apply

Collapse the bullet list into one direct sentence. Lead with the verb. Keep
proper nouns and specific numbers; drop the parallel structure. Reserve
bullets for genuine enumerations the user explicitly requested.
