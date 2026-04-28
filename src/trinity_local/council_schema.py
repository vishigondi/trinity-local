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
class CouncilPeerReview:
    reviewer_provider: str
    reviewer_model: str | None = None
    reviewer_session_id: str | None = None
    review_prompt: str | None = None
    review_text: str = ""
    ranked_labels: list[str] = field(default_factory=list)
    agreement: str | None = None
    strengths: list[str] = field(default_factory=list)
    weaknesses: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "reviewer_provider": self.reviewer_provider,
            "review_text": self.review_text,
        }
        for key in (
            "reviewer_model",
            "reviewer_session_id",
            "review_prompt",
            "agreement",
        ):
            value = getattr(self, key)
            if value not in (None, "", {}, []):
                payload[key] = value
        if self.ranked_labels:
            payload["ranked_labels"] = self.ranked_labels
        if self.strengths:
            payload["strengths"] = self.strengths
        if self.weaknesses:
            payload["weaknesses"] = self.weaknesses
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload


@dataclass
class CouncilAggregateRanking:
    ordered_labels: list[str] = field(default_factory=list)
    label_scores: dict[str, float] = field(default_factory=dict)
    label_to_provider: dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if self.ordered_labels:
            payload["ordered_labels"] = self.ordered_labels
        if self.label_scores:
            payload["label_scores"] = self.label_scores
        if self.label_to_provider:
            payload["label_to_provider"] = self.label_to_provider
        return payload


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
    peer_reviews: list[CouncilPeerReview] = field(default_factory=list)
    aggregate_ranking: CouncilAggregateRanking | None = None
    synthesis_prompt: str | None = None
    synthesis_output: str | None = None
    created_at: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "council_run_id": self.council_run_id,
            "bundle_id": self.bundle_id,
            "task_cluster_id": self.task_cluster_id,
            "primary_provider": self.primary_provider,
            "member_results": [member.to_dict() for member in self.member_results],
            "peer_reviews": [review.to_dict() for review in self.peer_reviews],
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
        if self.aggregate_ranking is not None:
            payload["aggregate_ranking"] = self.aggregate_ranking.to_dict()
        if self.differences:
            payload["differences"] = self.differences
        if self.metadata:
            payload["metadata"] = self.metadata
        return payload
