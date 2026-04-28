from __future__ import annotations

import json
from pathlib import Path
import re

from .council_schema import (
    CouncilAggregateRanking,
    CouncilMemberResult,
    CouncilOutcome,
    CouncilPeerReview,
    LaunchEvent,
    PromptBundle,
)
from .scoreboard import state_dir
from .utils import now_iso, stable_id

# Aliases for backward compatibility within this module
_now_iso = now_iso
_stable_id = stable_id


def prompt_bundles_dir() -> Path:
    path = state_dir() / "prompt_bundles"
    path.mkdir(parents=True, exist_ok=True)
    return path


def council_runs_path() -> Path:
    return state_dir() / "council_runs.jsonl"


def launch_events_path() -> Path:
    return state_dir() / "launch_events.jsonl"


def council_outcomes_dir() -> Path:
    path = state_dir() / "council_outcomes"
    path.mkdir(parents=True, exist_ok=True)
    return path


def create_prompt_bundle(
    *,
    task_cluster_id: str,
    task_text: str,
    context_excerpt: str = "",
    goal: str = "",
    comparison_instructions: str = "",
    origin_session_id: str | None = None,
    origin_provider: str | None = None,
    metadata: dict | None = None,
) -> PromptBundle:
    bundle_id = _stable_id(
        "bundle",
        task_cluster_id,
        task_text[:400],
        goal[:200],
        origin_session_id or "",
    )
    return PromptBundle(
        bundle_id=bundle_id,
        task_cluster_id=task_cluster_id,
        origin_session_id=origin_session_id,
        origin_provider=origin_provider,
        task_text=task_text.strip(),
        context_excerpt=context_excerpt.strip(),
        goal=goal.strip(),
        comparison_instructions=comparison_instructions.strip(),
        created_at=_now_iso(),
        metadata=metadata or {},
    )


def save_prompt_bundle(bundle: PromptBundle) -> Path:
    path = prompt_bundles_dir() / f"{bundle.bundle_id}.json"
    path.write_text(json.dumps(bundle.to_dict(), indent=2))
    return path


def load_prompt_bundle(path_or_bundle_id: str) -> PromptBundle:
    path = Path(path_or_bundle_id)
    if not path.exists():
        path = prompt_bundles_dir() / f"{path_or_bundle_id}.json"
    raw = json.loads(path.read_text())
    return PromptBundle(**raw)


def create_launch_event(
    *,
    bundle: PromptBundle,
    mode: str,
    source_provider: str | None,
    target_provider: str | None,
    target_model: str | None = None,
    handoff_reason: str | None = None,
    source_session_id: str | None = None,
    target_session_id: str | None = None,
    metadata: dict | None = None,
) -> LaunchEvent:
    launch_id = _stable_id(
        "launch",
        bundle.bundle_id,
        mode,
        source_provider or "",
        target_provider or "",
        target_model or "",
        _now_iso(),
    )
    return LaunchEvent(
        launch_id=launch_id,
        bundle_id=bundle.bundle_id,
        task_cluster_id=bundle.task_cluster_id,
        mode=mode,
        source_provider=source_provider,
        target_provider=target_provider,
        target_model=target_model,
        launched_at=_now_iso(),
        handoff_reason=handoff_reason,
        source_session_id=source_session_id,
        target_session_id=target_session_id,
        metadata=metadata or {},
    )


def append_launch_event(event: LaunchEvent) -> None:
    with launch_events_path().open("a") as handle:
        handle.write(json.dumps(event.to_dict()) + "\n")


def render_member_prompt(bundle: PromptBundle) -> str:
    sections = [
        "You are one member of a multi-model council.",
        f"Task:\n{bundle.task_text}",
    ]
    if bundle.goal:
        sections.append(f"Goal:\n{bundle.goal}")
    if bundle.context_excerpt:
        sections.append(f"Context:\n{bundle.context_excerpt}")
    if bundle.comparison_instructions:
        sections.append(f"Instructions:\n{bundle.comparison_instructions}")
    sections.append(
        "Respond directly to the task. Do not mention the council. Be concise but complete."
    )
    return "\n\n".join(sections)


def render_primary_council_prompt(
    bundle: PromptBundle,
    members: list[CouncilMemberResult],
    peer_reviews: list[CouncilPeerReview] | None = None,
) -> str:
    member_sections = []
    for index, member in enumerate(members, start=1):
        member_sections.append(
            "\n".join(
                [
                    f"[Member {index}] provider={member.provider} model={member.model or 'unknown'}",
                    member.output_text.strip() or "(no output)",
                ]
            )
        )
    review_sections = []
    for review in peer_reviews or []:
        review_sections.append(
            "\n".join(
                [
                    f"[Peer Review] reviewer={review.reviewer_provider} model={review.reviewer_model or 'unknown'}",
                    review.review_text.strip() or "(no review output)",
                ]
            )
        )
    sections = [
        "You are the primary council synthesizer.",
        f"Original task:\n{bundle.task_text}",
    ]
    if bundle.goal:
        sections.append(f"Goal:\n{bundle.goal}")
    if bundle.context_excerpt:
        sections.append(f"Context:\n{bundle.context_excerpt}")
    if bundle.comparison_instructions:
        sections.append(f"Comparison instructions:\n{bundle.comparison_instructions}")
    sections.append("Council member outputs:\n" + "\n\n".join(member_sections))
    if review_sections:
        sections.append("Peer reviews:\n" + "\n\n".join(review_sections))
    sections.append(
        "Return a synthesis with these sections exactly:\n"
        "1. Agreement\n"
        "2. Differences\n"
        "3. Best Answer\n"
        "4. Winner\n"
        "5. Follow-up Needed"
    )
    return "\n\n".join(sections)


def render_peer_review_prompt(
    bundle: PromptBundle,
    *,
    reviewer_label: str,
    own_label: str,
    anonymized_members: list[tuple[str, CouncilMemberResult]],
) -> str:
    response_sections = []
    for label, member in anonymized_members:
        body = member.output_text.strip() or "(no output)"
        response_sections.append(f"{label}\n{body}")
    sections = [
        "You are reviewing anonymized council responses for the same task.",
        f"Task:\n{bundle.task_text}",
    ]
    if bundle.goal:
        sections.append(f"Goal:\n{bundle.goal}")
    if bundle.context_excerpt:
        sections.append(f"Context:\n{bundle.context_excerpt}")
    if bundle.comparison_instructions:
        sections.append(f"Comparison instructions:\n{bundle.comparison_instructions}")
    sections.append(
        f"You are {reviewer_label}. Your own answer is {own_label}. Judge the responses fairly and do not reveal provider names."
    )
    sections.append("Responses:\n" + "\n\n".join(response_sections))
    sections.append(
        "Return exactly these sections:\n"
        "Agreement\n"
        "Strengths\n"
        "Weaknesses\n"
        "FINAL RANKING\n\n"
        "In FINAL RANKING, rank only the response labels from best to worst, one per line, like:\n"
        "1. Response B\n"
        "2. Response A\n"
        "3. Response C"
    )
    return "\n\n".join(sections)


def create_council_outcome(
    *,
    bundle: PromptBundle,
    primary_provider: str,
    member_results: list[CouncilMemberResult],
    peer_reviews: list[CouncilPeerReview] | None = None,
    aggregate_ranking: CouncilAggregateRanking | None = None,
    primary_model: str | None = None,
    primary_session_id: str | None = None,
    agreement_score: float | None = None,
    winner_provider: str | None = None,
    winner_model: str | None = None,
    needs_followup: bool | None = None,
    differences: list[str] | None = None,
    synthesis_output: str | None = None,
    metadata: dict | None = None,
) -> CouncilOutcome:
    synthesis_prompt = render_primary_council_prompt(bundle, member_results, peer_reviews)
    council_run_id = _stable_id(
        "council",
        bundle.bundle_id,
        primary_provider,
        primary_model or "",
        _now_iso(),
    )
    return CouncilOutcome(
        council_run_id=council_run_id,
        bundle_id=bundle.bundle_id,
        task_cluster_id=bundle.task_cluster_id,
        primary_provider=primary_provider,
        primary_model=primary_model,
        primary_session_id=primary_session_id,
        agreement_score=agreement_score,
        winner_provider=winner_provider,
        winner_model=winner_model,
        needs_followup=needs_followup,
        differences=differences or [],
        member_results=member_results,
        peer_reviews=peer_reviews or [],
        aggregate_ranking=aggregate_ranking,
        synthesis_prompt=synthesis_prompt,
        synthesis_output=synthesis_output,
        created_at=_now_iso(),
        metadata=metadata or {},
    )


def append_council_outcome(outcome: CouncilOutcome) -> None:
    with council_runs_path().open("a") as handle:
        handle.write(json.dumps(outcome.to_dict()) + "\n")


def save_council_outcome(outcome: CouncilOutcome) -> Path:
    path = council_outcomes_dir() / f"{outcome.council_run_id}.json"
    path.write_text(json.dumps(outcome.to_dict(), indent=2))
    append_council_outcome(outcome)
    return path


def load_council_outcome(path_or_run_id: str) -> CouncilOutcome:
    path = Path(path_or_run_id)
    if not path.exists():
        path = council_outcomes_dir() / f"{path_or_run_id}.json"
    raw = json.loads(path.read_text())
    members = [CouncilMemberResult(**member) for member in raw.get("member_results", [])]
    raw["member_results"] = members
    raw["peer_reviews"] = [CouncilPeerReview(**review) for review in raw.get("peer_reviews", [])]
    aggregate = raw.get("aggregate_ranking")
    if aggregate:
        raw["aggregate_ranking"] = CouncilAggregateRanking(**aggregate)
    return CouncilOutcome(**raw)


def parse_synthesis_sections(text: str) -> dict[str, str]:
    patterns = {
        "agreement": r"(?:^|\n)(?:1\.\s*Agreement|Agreement)\s*\n(.+?)(?=\n(?:2\.\s*Differences|Differences)\b|\Z)",
        "differences": r"(?:^|\n)(?:2\.\s*Differences|Differences)\s*\n(.+?)(?=\n(?:3\.\s*Best Answer|Best Answer)\b|\Z)",
        "best_answer": r"(?:^|\n)(?:3\.\s*Best Answer|Best Answer)\s*\n(.+?)(?=\n(?:4\.\s*Winner|Winner)\b|\Z)",
        "winner": r"(?:^|\n)(?:4\.\s*Winner|Winner)\s*\n(.+?)(?=\n(?:5\.\s*Follow-up Needed|Follow-up Needed)\b|\Z)",
        "followup": r"(?:^|\n)(?:5\.\s*Follow-up Needed|Follow-up Needed)\s*\n(.+?)\s*$",
    }
    out: dict[str, str] = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, text, flags=re.DOTALL | re.IGNORECASE)
        if match:
            out[key] = match.group(1).strip()
    return out


def parse_peer_review_sections(text: str) -> dict[str, str]:
    patterns = {
        "agreement": r"(?:^|\n)Agreement\s*\n(.+?)(?=\nStrengths\b|\Z)",
        "strengths": r"(?:^|\n)Strengths\s*\n(.+?)(?=\nWeaknesses\b|\Z)",
        "weaknesses": r"(?:^|\n)Weaknesses\s*\n(.+?)(?=\nFINAL RANKING\b|\Z)",
        "ranking": r"(?:^|\n)FINAL RANKING\s*\n(.+?)\s*$",
    }
    out: dict[str, str] = {}
    for key, pattern in patterns.items():
        match = re.search(pattern, text, flags=re.DOTALL | re.IGNORECASE)
        if match:
            out[key] = match.group(1).strip()
    return out


def parse_ranking_labels(ranking_text: str) -> list[str]:
    ranked_labels: list[str] = []
    for line in ranking_text.splitlines():
        clean = line.strip()
        if not clean:
            continue
        clean = re.sub(r"^\d+\.\s*", "", clean)
        clean = re.sub(r"^\-\s*", "", clean)
        if clean.lower().startswith("response "):
            parts = clean.split(None, 1)
            if len(parts) == 2:
                ranked_labels.append(f"Response {parts[1].strip()}")
    return ranked_labels


def parse_bullets(text: str) -> list[str]:
    items: list[str] = []
    for line in text.splitlines():
        clean = line.strip()
        if not clean:
            continue
        clean = re.sub(r"^\d+\.\s*", "", clean)
        clean = re.sub(r"^\-\s*", "", clean)
        if clean:
            items.append(clean)
    return items


def aggregate_peer_rankings(
    peer_reviews: list[CouncilPeerReview],
    label_to_provider: dict[str, str],
) -> CouncilAggregateRanking | None:
    if not peer_reviews:
        return None
    score_totals: dict[str, float] = {label: 0.0 for label in label_to_provider}
    for review in peer_reviews:
        ranking = [label for label in review.ranked_labels if label in score_totals]
        if not ranking:
            continue
        max_points = len(ranking)
        for index, label in enumerate(ranking):
            score_totals[label] += max_points - index
    ordered = sorted(
        score_totals,
        key=lambda label: (-score_totals[label], label_to_provider.get(label, ""), label),
    )
    return CouncilAggregateRanking(
        ordered_labels=[label for label in ordered if score_totals.get(label, 0.0) > 0],
        label_scores={label: score for label, score in score_totals.items() if score > 0},
        label_to_provider=label_to_provider,
    )
