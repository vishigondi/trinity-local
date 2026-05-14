"""Corpus-based eval harness (task #122).

Turns the user's own ~/.trinity/ corpus into a replayable eval suite.
Inputs already on disk for any seeded install:
  - ~/.trinity/me/rejections.jsonl     — 44+ labeled (prompt, rejected_response,
                                          rejection_type) triples mined from
                                          turn-pair gaps
  - ~/.trinity/prompts/prompt_nodes.jsonl — 49k+ prompt index for lookup +
                                            basin-aware slicing
  - ~/.trinity/memories/lens.md       — the judge rubric

This module ships the BUILDER first (MVP for task #122). The runner +
scorer ship in follow-up ticks. With the builder alone, the user can
already inspect what their personal eval set looks like and how it
slices across rejection_type × basin — that's the first marketing
artifact for workstream #116.

The wedge is structurally non-refutable: only Trinity has cross-
provider rejection signal. Anthropic can score Claude on Claude
transcripts; only Trinity can score any model against the user's
empirical rejections of every provider's past output.
"""
from __future__ import annotations

from .builder import build_eval_set, load_eval_set, EvalItem, EvalSet, evals_dir

__all__ = ["build_eval_set", "load_eval_set", "EvalItem", "EvalSet", "evals_dir"]
