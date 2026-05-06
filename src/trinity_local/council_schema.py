from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class PromptBundle:
    bundle_id: str
    task_cluster_id: str
    origin_session_id: str | None = None
    origin_provider: str | None = None
    task_text: str = ""
    context_excerpt: str = ""
    goal: str = ""
    comparison_instructions: str = ""
    created_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v not in (None, "", {}, [])}


@dataclass
class LaunchEvent:
    launch_id: str
    bundle_id: str
    task_cluster_id: str
    mode: str
    source_provider: str | None = None
    target_provider: str | None = None
    target_model: str | None = None
    launched_at: str = ""
    handoff_reason: str | None = None
    source_session_id: str | None = None
    target_session_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v not in (None, "", {}, [])}


@dataclass
class CouncilMemberResult:
    provider: str
    model: str | None = None
    session_id: str | None = None
    output_text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v not in (None, "", {}, [])}


@dataclass
class CouncilChainStep:
    """One step of a chain-mode council (sequential refinement / relay race).

    Each step takes the prior steps' outputs as context and produces a refined
    answer. The last step's output (or the chairman synthesis over the chain)
    is treated as the final answer.
    """
    step_index: int
    model_provider: str
    model_name: str | None = None
    input_text: str = ""
    output_text: str = ""
    latency_seconds: float | None = None
    cost_estimate_usd: float | None = None
    started_at: str = ""
    completed_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "step_index": self.step_index,
            "model_provider": self.model_provider,
            "input_text": self.input_text,
            "output_text": self.output_text,
        }
        for key in ("model_name", "started_at", "completed_at"):
            value = getattr(self, key)
            if value not in (None, ""):
                payload[key] = value
        if self.latency_seconds is not None:
            payload["latency_seconds"] = self.latency_seconds
        if self.cost_estimate_usd is not None:
            payload["cost_estimate_usd"] = self.cost_estimate_usd
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> CouncilChainStep:
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in raw.items() if k in known})


@dataclass
class CouncilRoutingLabel:
    """Machine-parseable verdict from the Chairman synthesis (§8.7).

    This is the supervision signal for the Phase 9 learned controller — every
    valid label is one training example. Schema mirrors the JSON contract
    appended to the chairman prompt.
    """
    winner: str
    confidence: str = "medium"  # "high" | "medium" | "low"
    runner_up: str | None = None
    task_type: str = ""
    task_domain: str = ""
    user_likely_values: list[str] = field(default_factory=list)
    provider_scores: dict[str, dict[str, float]] = field(default_factory=dict)
    routing_lesson: str = ""
    eval_seed: str = ""
    major_failure_mode: str | None = None
    # Verifier-shaped output: the consumer-visible primitive.
    # "models agreed on these claims, disagreed on these, here's why"
    agreed_claims: list[str] = field(default_factory=list)
    disagreed_claims: list[dict[str, object]] = field(default_factory=list)
    # NOTE: `best_stage_models`, `should_be_hard_case`, and `hard_case_reason`
    # were demoted in iter-3 — zero downstream consumers (verified via grep
    # across personal_routing, chairman_picker, council_review, mcp_server,
    # research/). Removing them shrinks the chairman's required JSON shape and
    # the supervision signal Phase 9 trains on. Older outcome JSONs still load
    # cleanly because `from_dict` filters unknown keys.

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "winner": self.winner,
            "confidence": self.confidence,
        }
        for key in (
            "runner_up",
            "task_type",
            "task_domain",
            "routing_lesson",
            "eval_seed",
            "major_failure_mode",
        ):
            value = getattr(self, key)
            if value not in (None, "", {}, []):
                payload[key] = value
        if self.user_likely_values:
            payload["user_likely_values"] = self.user_likely_values
        if self.provider_scores:
            payload["provider_scores"] = self.provider_scores
        if self.agreed_claims:
            payload["agreed_claims"] = self.agreed_claims
        if self.disagreed_claims:
            payload["disagreed_claims"] = self.disagreed_claims
        return payload

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> CouncilRoutingLabel:
        known = {f for f in cls.__dataclass_fields__}
        filtered = {k: v for k, v in raw.items() if k in known}
        # Coerce required fields with sane defaults
        filtered.setdefault("winner", "")
        filtered.setdefault("confidence", "medium")
        return cls(**filtered)


@dataclass
class CouncilOutcome:
    council_run_id: str
    bundle_id: str
    task_cluster_id: str
    primary_provider: str
    primary_model: str | None = None
    primary_session_id: str | None = None
    agreement_score: float | None = None
    winner_provider: str | None = None
    winner_model: str | None = None
    needs_followup: bool | None = None
    differences: list[str] = field(default_factory=list)
    member_results: list[CouncilMemberResult] = field(default_factory=list)
    synthesis_prompt: str | None = None
    synthesis_output: str | None = None
    routing_label: CouncilRoutingLabel | None = None
    # Mode of this council. "parallel" = members run simultaneously, chairman synthesizes.
    # "chain" = sequential refinement; chain_steps populated.
    mode: str = "parallel"
    chain_steps: list[CouncilChainStep] = field(default_factory=list)
    created_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "council_run_id": self.council_run_id,
            "bundle_id": self.bundle_id,
            "task_cluster_id": self.task_cluster_id,
            "primary_provider": self.primary_provider,
            "member_results": [member.to_dict() for member in self.member_results],
            "created_at": self.created_at,
        }
        for key in (
            "primary_model",
            "primary_session_id",
            "agreement_score",
            "winner_provider",
            "winner_model",
            "needs_followup",
            "synthesis_prompt",
            "synthesis_output",
        ):
            value = getattr(self, key)
            if value not in (None, "", {}, []):
                payload[key] = value
        if self.differences:
            payload["differences"] = self.differences
        if self.routing_label is not None:
            payload["routing_label"] = self.routing_label.to_dict()
        if self.mode and self.mode != "parallel":
            payload["mode"] = self.mode
        if self.chain_steps:
            payload["chain_steps"] = [step.to_dict() for step in self.chain_steps]
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload
