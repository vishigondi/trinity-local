"""Lens-discovery pipeline for `trinity-local lens-build`.

Implements the 3-stage Option C pipeline ratified by council
council_70eaf228d7753074:

- basins.py: numpy k-means topology over PromptNode embeddings (Stage 1)
- decisions.py: chairman-driven decision extraction (Stage 2)
- pair_mining.py: 3-member council + verifier contract + basin
  post-filter that makes topology evidence load-bearing (Stages 3+4)

Drift instrument was explicitly rejected as topic-shift-not-value-shift
metaphor; centroids stay around only as basin tags for the post-filter.
"""

from __future__ import annotations
