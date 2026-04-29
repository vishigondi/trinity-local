from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import AppConfig
from .council_progress import (
    cleanup_progress,
    finalize_council_progress,
    init_council_progress,
    update_member_progress,
    update_synthesis_progress,
)
from .council_review import write_unified_council_page
from .council_runtime import (
    aggregate_peer_rankings,
    append_launch_event,
    create_council_outcome,
    create_launch_event,
    parse_bullets,
    parse_peer_review_sections,
    parse_synthesis_sections,
    parse_ranking_labels,
    render_member_prompt,
    render_peer_review_prompt,
    save_council_outcome,
)
from .council_schema import CouncilMemberResult, CouncilOutcome, CouncilPeerReview, LaunchEvent, PromptBundle
from .providers import ProviderError, make_provider
from .task_runtime import save_sync_record, save_task_record, task_from_council


@dataclass
class CouncilRunResult:
    outcome: CouncilOutcome
    outcome_path: Path
    review_path: Path
    launches: list[LaunchEvent]
    task_path: Path | None = None
    sync_path: Path | None = None


def _provider_model(config, override: str | None) -> str | None:
    return override or config.model


def run_council(
    *,
    config: AppConfig,
    bundle: PromptBundle,
    member_providers: list[str],
    primary_provider: str,
    cwd: Path,
    member_model_overrides: dict[str, str] | None = None,
    primary_model_override: str | None = None,
    with_peer_review: bool = True,
) -> CouncilRunResult:
    member_model_overrides = member_model_overrides or {}
    member_results: list[CouncilMemberResult] = []
    peer_reviews: list[CouncilPeerReview] = []
    launches: list[LaunchEvent] = []

    failed_members: list[str] = []
    failed_reviewers: list[str] = []
    member_failures: list[dict[str, object]] = []
    reviewer_failures: list[dict[str, object]] = []

    # Initialize progress tracking
    council_id = bundle.bundle_id
    init_council_progress(council_id, member_providers)

    for provider_name in member_providers:
        provider_config = config.providers.get(provider_name)
        if provider_config is None or not provider_config.enabled:
            failed_members.append(provider_name)
            member_failures.append(
                {
                    "provider": provider_name,
                    "stage": "member",
                    "reason": "provider_missing_or_disabled",
                }
            )
            continue
        prompt = render_member_prompt(bundle)
        provider = make_provider(provider_config)
        try:
            result = provider.run(prompt, cwd)
        except Exception as exc:
            failed_members.append(provider_name)
            member_failures.append(
                {
                    "provider": provider_name,
                    "stage": "member",
                    "reason": "exception",
                    "error": str(exc),
                }
            )
            continue
        if result.returncode != 0 and not (result.stdout or "").strip():
            failed_members.append(provider_name)
            member_failures.append(
                {
                    "provider": provider_name,
                    "stage": "member",
                    "reason": "nonzero_returncode_without_stdout",
                    "returncode": result.returncode,
                    "stderr": result.stderr,
                }
            )
            continue
        member = CouncilMemberResult(
            provider=provider_name,
            model=_provider_model(provider_config, member_model_overrides.get(provider_name)),
            session_id=None,
            output_text=result.stdout or result.stderr,
            metadata={
                "returncode": result.returncode,
                "stderr": result.stderr,
                "stdout": result.stdout,
            },
        )
        member_results.append(member)
        # Update progress tracking
        update_member_progress(council_id, provider_name, result.stdout or result.stderr or "")
        event = create_launch_event(
            bundle=bundle,
            mode="council",
            source_provider=bundle.origin_provider,
            target_provider=provider_name,
            target_model=member.model,
            handoff_reason="council_member",
            source_session_id=bundle.origin_session_id,
            metadata={"bundle_role": "member"},
        )
        append_launch_event(event)
        launches.append(event)

    if not member_results:
        raise ProviderError(
            f"All council members failed: {failed_members}. "
            "Cannot proceed with zero successful responses."
        )

    label_to_provider = {
        f"Response {chr(ord('A') + index)}": member.provider
        for index, member in enumerate(member_results)
    }
    if with_peer_review and len(member_results) >= 2:
        anonymized_members = [
            (f"Response {chr(ord('A') + index)}", member)
            for index, member in enumerate(member_results)
        ]
        for review_index, member in enumerate(member_results):
            reviewer_label = f"Reviewer {chr(ord('A') + review_index)}"
            own_label = anonymized_members[review_index][0]
            review_prompt = render_peer_review_prompt(
                bundle,
                reviewer_label=reviewer_label,
                own_label=own_label,
                anonymized_members=anonymized_members,
            )
            reviewer_provider_name = member.provider
            reviewer_config = config.providers.get(reviewer_provider_name)
            if reviewer_config is None or not reviewer_config.enabled:
                failed_reviewers.append(reviewer_provider_name)
                reviewer_failures.append(
                    {
                        "provider": reviewer_provider_name,
                        "stage": "peer_review",
                        "reason": "provider_missing_or_disabled",
                    }
                )
                continue
            reviewer = make_provider(reviewer_config)
            try:
                review_result = reviewer.run(review_prompt, cwd)
            except Exception as exc:
                failed_reviewers.append(reviewer_provider_name)
                reviewer_failures.append(
                    {
                        "provider": reviewer_provider_name,
                        "stage": "peer_review",
                        "reason": "exception",
                        "error": str(exc),
                    }
                )
                continue
            sections = parse_peer_review_sections(review_result.stdout or review_result.stderr)
            ranked_labels = parse_ranking_labels(sections.get("ranking", ""))
            review = CouncilPeerReview(
                reviewer_provider=reviewer_provider_name,
                reviewer_model=member.model,
                reviewer_session_id=member.session_id,
                review_prompt=review_prompt,
                review_text=review_result.stdout or review_result.stderr,
                ranked_labels=ranked_labels,
                agreement=sections.get("agreement"),
                strengths=parse_bullets(sections.get("strengths", "")),
                weaknesses=parse_bullets(sections.get("weaknesses", "")),
                metadata={
                    "returncode": review_result.returncode,
                    "stderr": review_result.stderr,
                    "stdout": review_result.stdout,
                    "reviewed_labels": [label for label, _ in anonymized_members],
                    "own_label": own_label,
                },
            )
            peer_reviews.append(review)
            event = create_launch_event(
                bundle=bundle,
                mode="council",
                source_provider=reviewer_provider_name,
                target_provider=reviewer_provider_name,
                target_model=member.model,
                handoff_reason="council_peer_review",
                source_session_id=member.session_id,
                metadata={"bundle_role": "peer_review", "reviewer_label": reviewer_label},
            )
            append_launch_event(event)
            launches.append(event)

    aggregate_ranking = aggregate_peer_rankings(peer_reviews, label_to_provider)

    primary_config = config.providers.get(primary_provider)
    if primary_config is None or not primary_config.enabled:
        raise ProviderError(f"Unknown or disabled primary provider: {primary_provider}")
    primary_model = _provider_model(primary_config, primary_model_override)
    primary_prompt = render_member_prompt(bundle) if not member_results else None
    outcome = create_council_outcome(
        bundle=bundle,
        primary_provider=primary_provider,
        member_results=member_results,
        peer_reviews=peer_reviews,
        aggregate_ranking=aggregate_ranking,
        primary_model=primary_model,
        metadata={"cwd": str(cwd)},
    )
    # Reuse the generated synthesis prompt so it is tracked in metadata and on disk.
    primary_prompt = outcome.synthesis_prompt or primary_prompt or ""

    # --- Primary synthesis with failure handling ---
    update_synthesis_progress(council_id, "running")
    synthesis_output = ""
    synthesis_error = None
    sections: dict[str, str] = {}
    synthesis_failure: dict[str, object] | None = None
    primary = make_provider(primary_config)
    try:
        primary_result = primary.run(primary_prompt, cwd)
        synthesis_output = primary_result.stdout or primary_result.stderr or ""
        sections = parse_synthesis_sections(synthesis_output)
    except Exception as exc:
        synthesis_error = str(exc)
        synthesis_failure = {
            "provider": primary_provider,
            "stage": "primary_synthesis",
            "reason": "exception",
            "error": str(exc),
        }
        synthesis_output = ""
    finally:
        update_synthesis_progress(council_id, "done")

    differences = []
    if "differences" in sections:
        differences = [
            line.strip("- ").strip()
            for line in sections["differences"].splitlines()
            if line.strip()
        ]
    winner_provider = None
    if "winner" in sections:
        winner_lower = sections["winner"].lower()
        for provider_name in [*member_providers, primary_provider]:
            if provider_name.lower() in winner_lower:
                winner_provider = provider_name
                break
    needs_followup = None
    if "followup" in sections:
        follow = sections["followup"].lower()
        if "yes" in follow or "true" in follow:
            needs_followup = True
        elif "no" in follow or "false" in follow:
            needs_followup = False

    final_metadata: dict = {
        "cwd": str(cwd),
        "peer_review_count": len(peer_reviews),
        "failed_members": failed_members,
        "failed_reviewers": failed_reviewers,
        "member_failures": member_failures,
        "reviewer_failures": reviewer_failures,
    }
    if synthesis_error:
        final_metadata["synthesis_error"] = synthesis_error
        final_metadata["synthesis_failure"] = synthesis_failure
    else:
        final_metadata["primary_returncode"] = primary_result.returncode
        final_metadata["primary_stderr"] = primary_result.stderr
        final_metadata["parsed_sections"] = sections

    final_outcome = create_council_outcome(
        bundle=bundle,
        primary_provider=primary_provider,
        member_results=member_results,
        peer_reviews=peer_reviews,
        aggregate_ranking=aggregate_ranking,
        primary_model=primary_model,
        agreement_score=None,
        winner_provider=winner_provider,
        winner_model=primary_model if winner_provider == primary_provider else None,
        needs_followup=needs_followup,
        differences=differences,
        synthesis_output=synthesis_output,
        metadata=final_metadata,
    )
    outcome_path = save_council_outcome(final_outcome)
    review_path = write_unified_council_page(bundle, final_outcome)

    # Mark progress as complete and clean up
    finalize_council_progress(council_id)
    cleanup_progress(council_id)

    primary_event = create_launch_event(
        bundle=bundle,
        mode="council",
        source_provider=bundle.origin_provider,
        target_provider=primary_provider,
        target_model=primary_model,
        handoff_reason="council_primary_synthesis",
        source_session_id=bundle.origin_session_id,
        metadata={"bundle_role": "primary"},
    )
    append_launch_event(primary_event)
    launches.append(primary_event)
    task = task_from_council(
        bundle=bundle,
        outcome=final_outcome,
        review_page_path=str(review_path),
        launch_ids=[launch.launch_id for launch in launches],
    )
    task_path = save_task_record(task)
    sync_path = save_sync_record(task)

    return CouncilRunResult(
        outcome=final_outcome,
        outcome_path=outcome_path,
        review_path=review_path,
        launches=launches,
        task_path=task_path,
        sync_path=sync_path,
    )
