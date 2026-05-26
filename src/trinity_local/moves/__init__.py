"""Trinity moves substrate — the procedural layer of the v2 hierarchy.

Internal vocab: **moves** (atomic procedural memory). External format:
SKILL.md (per agentskills.io). Trinity adds extension frontmatter fields
(trinity_alpha, trinity_posterior, trinity_promoted_from, etc.) that the
SKILL.md spec explicitly allows.

Public API:
  - schemas.Move           — the dataclass with MACLA-lifted Bayesian
                              tracking + provenance + tier scores
  - store.read_move(slug)  — load a move from ~/.trinity/moves/<slug>/SKILL.md
  - store.write_move(m)    — persist a move to disk
  - store.list_moves()     — enumerate active (non-archived) moves
  - store.archive_move(slug, tier, reason) — demote a move into archive/
  - gate.{T1,T2,T3,T4}     — the four-tier Bayesian gate (scaffolding;
                              T1+T2 filled by #168, T3 by #169, T4 by #170)

See docs/PREFERENCE_CORPUS_SPEC.md for the schema + the wedge
("Why T4 is the wedge no one else has").
"""
from __future__ import annotations

from .schemas import Move
from . import store, gate

__all__ = ["Move", "store", "gate"]
