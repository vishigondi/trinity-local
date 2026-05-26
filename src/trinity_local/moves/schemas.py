"""Move dataclass — the atomic procedural-memory unit.

External format: SKILL.md (agentskills.io). Trinity adds extension
frontmatter fields the SKILL.md spec explicitly allows. See
docs/PREFERENCE_CORPUS_SPEC.md "Layer 3a: Moves" for the full schema.

Field semantics — lifted from MACLA (S. Forouzandeh, AAMAS 2026):
- alpha/beta: Beta-Binomial conjugate prior. alpha increments on
  chairman-picked applications, beta on chairman-not-picked.
  posterior = alpha / (alpha + beta). Incremental, no rolling window.
- success_contexts / failure_contexts: basins where the move fired
  correctly vs incorrectly. Lets users debug demotion by tier.
- generalizability_score: how broadly the move applies (multi-basin).
  Independent of confidence — a move can be high-confidence in 1 basin
  AND low-generalizability simultaneously.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Move:
    """A promoted move — atomic procedural memory unit.

    Read from + written to ~/.trinity/moves/<slug>/SKILL.md via
    store.read_move() / store.write_move(). The SKILL.md frontmatter
    serializes every field; the body is the move's procedure (markdown).
    """

    # ── SKILL.md spec-required ──
    name: str
    description: str

    # ── Provenance (why this move exists) ──
    trinity_promoted_from: list[str] = field(default_factory=list)
    trinity_basin_id: str | None = None
    trinity_promoted_at: str | None = None  # ISO 8601
    trinity_demoted_at: str | None = None
    trinity_demoted_by_tier: str | None = None  # T1 / T2 / T3 / T4

    # ── Bayesian tracking (MACLA Beta-Binomial conjugate prior) ──
    # Initial state: alpha=1, beta=1 (uninformative prior; posterior=0.5).
    # Every council where this move was active increments one of them.
    trinity_alpha: int = 1
    trinity_beta: int = 1
    trinity_execution_count: int = 0  # = alpha + beta - 2 (excludes initial prior)

    # ── Tier scores from the 4-tier Bayesian gate ──
    # Most recent re-eval values; refreshed every dream cycle.
    trinity_t1_lexical_score: float | None = None
    trinity_t2_embedding_score: float | None = None
    trinity_t3_chairman_score: float | None = None
    trinity_eval_baseline: float | None = None  # personal best on T3

    # ── Contrastive learning (MACLA) ──
    trinity_success_contexts: list[str] = field(default_factory=list)
    trinity_failure_contexts: list[str] = field(default_factory=list)
    trinity_generalizability_score: float | None = None
    trinity_lens_tensions_addressed: int | None = None

    # ── Body — the actual procedure (markdown, post-frontmatter) ──
    body: str = ""

    # ─── Derived properties ──────────────────────────────────────

    @property
    def posterior(self) -> float:
        """Beta-Binomial conjugate posterior: alpha / (alpha + beta).

        With uninformative prior (alpha=beta=1) this starts at 0.5 and
        converges to the true success rate as execution_count grows.
        """
        total = self.trinity_alpha + self.trinity_beta
        return self.trinity_alpha / total if total > 0 else 0.5

    @property
    def is_active(self) -> bool:
        """A move is active iff it was promoted AND not demoted."""
        return self.trinity_promoted_at is not None and self.trinity_demoted_at is None

    @property
    def is_archived(self) -> bool:
        """A move is archived iff it was demoted at some point."""
        return self.trinity_demoted_at is not None

    # ─── Bayesian update helpers ─────────────────────────────────
    # Mutate-in-place for callers that want imperative updates. Pure
    # data; no I/O. Persistence is the caller's job (store.write_move).

    def record_success(self) -> None:
        """The move was applied AND the chairman picked the response
        using it. Increments alpha."""
        self.trinity_alpha += 1
        self.trinity_execution_count += 1

    def record_failure(self) -> None:
        """The move was applied AND the chairman picked a different
        response. Increments beta."""
        self.trinity_beta += 1
        self.trinity_execution_count += 1

    # ─── Serialization ───────────────────────────────────────────

    def to_frontmatter(self) -> dict[str, Any]:
        """Render the dataclass as a SKILL.md frontmatter dict.

        Omits None values + empty lists to keep the on-disk file clean.
        The `posterior` property is computed at read time from alpha/
        beta, so it's not persisted (storing it would let alpha/beta and
        posterior drift apart).
        """
        out: dict[str, Any] = {
            "name": self.name,
            "description": self.description,
        }
        # Provenance — only include fields with actual values
        for k in (
            "trinity_promoted_from",
            "trinity_basin_id",
            "trinity_promoted_at",
            "trinity_demoted_at",
            "trinity_demoted_by_tier",
        ):
            v = getattr(self, k)
            if v not in (None, []):
                out[k] = v
        # Bayesian tracking — always persisted (defaults are
        # meaningful: alpha=1, beta=1 is the prior).
        out["trinity_alpha"] = self.trinity_alpha
        out["trinity_beta"] = self.trinity_beta
        out["trinity_execution_count"] = self.trinity_execution_count
        # Tier scores — only when populated
        for k in (
            "trinity_t1_lexical_score",
            "trinity_t2_embedding_score",
            "trinity_t3_chairman_score",
            "trinity_eval_baseline",
        ):
            v = getattr(self, k)
            if v is not None:
                out[k] = v
        # Contrastive learning — empty lists omitted
        for k in ("trinity_success_contexts", "trinity_failure_contexts"):
            v = getattr(self, k)
            if v:
                out[k] = v
        for k in ("trinity_generalizability_score", "trinity_lens_tensions_addressed"):
            v = getattr(self, k)
            if v is not None:
                out[k] = v
        return out

    @classmethod
    def from_frontmatter(cls, data: dict[str, Any], body: str = "") -> "Move":
        """Construct a Move from a frontmatter dict + body.

        Tolerant of missing optional fields (cold-install: fresh moves
        from dream propose only `name`, `description`, `trinity_basin_id`,
        `trinity_promoted_from`; everything else gets defaults). Tolerant
        of extra fields (other tools may add their own custom frontmatter
        — the SKILL.md spec allows this; Trinity just ignores them).
        """
        # Required
        if "name" not in data or "description" not in data:
            raise ValueError(
                f"Move frontmatter missing required SKILL.md fields "
                f"name + description; got {sorted(data.keys())}"
            )
        return cls(
            name=str(data["name"]),
            description=str(data["description"]),
            trinity_promoted_from=list(data.get("trinity_promoted_from") or []),
            trinity_basin_id=data.get("trinity_basin_id"),
            trinity_promoted_at=data.get("trinity_promoted_at"),
            trinity_demoted_at=data.get("trinity_demoted_at"),
            trinity_demoted_by_tier=data.get("trinity_demoted_by_tier"),
            trinity_alpha=int(data.get("trinity_alpha", 1)),
            trinity_beta=int(data.get("trinity_beta", 1)),
            trinity_execution_count=int(data.get("trinity_execution_count", 0)),
            trinity_t1_lexical_score=data.get("trinity_t1_lexical_score"),
            trinity_t2_embedding_score=data.get("trinity_t2_embedding_score"),
            trinity_t3_chairman_score=data.get("trinity_t3_chairman_score"),
            trinity_eval_baseline=data.get("trinity_eval_baseline"),
            trinity_success_contexts=list(data.get("trinity_success_contexts") or []),
            trinity_failure_contexts=list(data.get("trinity_failure_contexts") or []),
            trinity_generalizability_score=data.get("trinity_generalizability_score"),
            trinity_lens_tensions_addressed=data.get("trinity_lens_tensions_addressed"),
            body=body,
        )
