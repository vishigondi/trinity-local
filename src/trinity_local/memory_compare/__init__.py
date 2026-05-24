"""Trinity lens ↔ Claude Auto-Dream comparison harness (#142).

Three measurement modes (per docs plan whimsical-imagining-firefly.md):
- Mode 1 — Static comparison (this slice). Lexical Jaccard + coverage
  + specificity over parsed claim lists. Cheap, ships first.
- Mode 2 — Differential evaluation (deferred). Reuses eval-run with
  --memory-source {trinity|claude|both|none} to score each memory's
  contribution against rejections.jsonl ground truth.
- Mode 3 — Cross-fertilize prompt-injection test (deferred). For each
  asymmetric-gap claim, build a synthetic prompt and judge whose
  memory wins. Generates the architectural-improvement candidate list.

The public surface for Mode 1: ``compare_memories(trinity_lens_text,
claude_memory_root)`` returning a ``ComparisonReport``.
"""
from __future__ import annotations

from .metrics import Claim, ComparisonReport, compare_memories

__all__ = ["Claim", "ComparisonReport", "compare_memories"]
