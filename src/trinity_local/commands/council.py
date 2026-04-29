"""Handlers for council-prompt, council-outcome, council-html, council-run, council-start commands."""
from __future__ import annotations

import json
from pathlib import Path

from ..config import load_config
from ..council_status import write_council_status
from ..council_feedback import append_council_feedback
from ..council_review import review_pages_dir, write_review_html
from ..council_runner import run_council
from ..council_runtime import (
    aggregate_peer_rankings,
    create_prompt_bundle,
    create_council_outcome,
    load_council_outcome,
    load_prompt_bundle,
    render_member_prompt,
    render_peer_review_prompt,
    render_primary_council_prompt,
    save_prompt_bundle,
    save_council_outcome,
)
from ..council_schema import CouncilMemberResult
from ..action_runtime import create_review_ready_action, notify_action, save_action
from ..notifications import notify, open_path
from ..task_runtime import ensure_task_record, load_task_record, save_sync_record, save_task_record
from ..utils import stable_id
from .helpers import load_member_results, load_peer_reviews, read_text_file


def register(subparsers):
    prompt_parser = subparsers.add_parser("council-prompt", help="Render a council member or primary prompt")
    prompt_parser.add_argument("--bundle", required=True, help="Bundle id or path")
    prompt_parser.add_argument("--kind", required=True, choices=["member", "primary", "peer-review"])
    prompt_parser.add_argument("--members-json", default=None, help="JSON file with member results for primary prompt")
    prompt_parser.add_argument("--reviewer-provider", default=None, help="Reviewer provider for peer-review prompt rendering")
    prompt_parser.set_defaults(handler=handle_council_prompt)

    outcome_parser = subparsers.add_parser("council-outcome", help="Create and save a council outcome")
    outcome_parser.add_argument("--bundle", required=True, help="Bundle id or path")
    outcome_parser.add_argument("--primary-provider", required=True)
    outcome_parser.add_argument("--primary-model", default=None)
    outcome_parser.add_argument("--primary-session-id", default=None)
    outcome_parser.add_argument("--members-json", required=True, help="JSON file with council member results")
    outcome_parser.add_argument("--agreement-score", type=float, default=None)
    outcome_parser.add_argument("--winner-provider", default=None)
    outcome_parser.add_argument("--winner-model", default=None)
    outcome_parser.add_argument("--needs-followup", choices=["true", "false"], default=None)
    outcome_parser.add_argument("--difference", action="append", default=[], help="Repeatable difference bullet")
    outcome_parser.add_argument("--synthesis-output-file", default=None)
    outcome_parser.add_argument("--peer-reviews-json", default=None, help="JSON file with council peer reviews")
    outcome_parser.set_defaults(handler=handle_council_outcome)

    html_parser = subparsers.add_parser("council-html", help="Generate a local HTML review page")
    html_parser.add_argument("--bundle", required=True, help="Bundle id or path")
    html_parser.add_argument("--outcome", default=None, help="Council outcome id or path")
    html_parser.set_defaults(handler=handle_council_html)

    council_run_parser = subparsers.add_parser("council-run", help="Launch member providers and synthesize a council result")
    council_run_parser.add_argument("--bundle", required=True, help="Bundle id or path")
    council_run_parser.add_argument("--members", nargs="+", required=True, help="Member providers to query")
    council_run_parser.add_argument("--primary-provider", required=True, help="Provider that synthesizes the council outcome")
    council_run_parser.add_argument("--cwd", default=".", help="Working directory for provider runs")
    council_run_parser.add_argument(
        "--member-model-override",
        action="append",
        default=[],
        help="Repeatable provider=model override for council members",
    )
    council_run_parser.add_argument("--primary-model-override", default=None)
    council_run_parser.add_argument(
        "--without-peer-review",
        action="store_true",
        help="Skip anonymized stage-2 peer review before synthesis",
    )
    council_run_parser.set_defaults(handler=handle_council_run)

    council_start_parser = subparsers.add_parser("council-start", help="Create/update task, run council, and optionally open the review page")
    council_start_parser.add_argument("--bundle", required=True, help="Bundle id or path")
    council_start_parser.add_argument("--members", nargs="+", required=True, help="Member providers to query")
    council_start_parser.add_argument("--primary-provider", required=True)
    council_start_parser.add_argument("--cwd", default=".", help="Working directory for provider runs")
    council_start_parser.add_argument("--status-token", default=None, help="Launchpad status token for same-tab council tracking")
    council_start_parser.add_argument("--open-browser", action="store_true")
    council_start_parser.add_argument("--notify", action="store_true")
    council_start_parser.add_argument("--without-peer-review", action="store_true")
    council_start_parser.set_defaults(handler=handle_council_start)

    council_launch_parser = subparsers.add_parser(
        "council-launch",
        help="Create a prompt bundle from task text, run council, and open the result",
    )
    council_launch_parser.add_argument("--task", required=True, help="Task text to compare across providers")
    council_launch_parser.add_argument("--goal", default="Find the strongest answer.")
    council_launch_parser.add_argument("--instructions", default="Prefer the strongest answer for the user's current task.")
    council_launch_parser.add_argument("--context-file", default=None)
    council_launch_parser.add_argument("--project-hint", default="")
    council_launch_parser.add_argument("--members", nargs="+", default=["claude", "gemini", "codex"])
    council_launch_parser.add_argument("--primary-provider", default="claude")
    council_launch_parser.add_argument("--cwd", default=".")
    council_launch_parser.add_argument("--status-token", default=None)
    council_launch_parser.add_argument("--open-browser", action="store_true")
    council_launch_parser.add_argument("--notify", action="store_true")
    council_launch_parser.add_argument("--without-peer-review", action="store_true")
    council_launch_parser.set_defaults(handler=handle_council_launch)

    council_rate_parser = subparsers.add_parser(
        "council-rate",
        help="Record a user's preferred provider for a council result",
    )
    council_rate_parser.add_argument("--council", required=True)
    council_rate_parser.add_argument("--provider", required=True)
    council_rate_parser.add_argument("--answer-label", default=None)
    council_rate_parser.set_defaults(handler=handle_council_rate)


def handle_council_prompt(args):
    bundle = load_prompt_bundle(args.bundle)
    if args.kind == "member":
        print(render_member_prompt(bundle))
        return
    members = load_member_results(args.members_json) if args.members_json else []
    if args.kind == "peer-review":
        if not members:
            raise SystemExit("error: --members-json is required for kind=peer-review")
        anonymized_members = [
            (f"Response {chr(ord('A') + index)}", member)
            for index, member in enumerate(members)
        ]
        reviewer_provider = args.reviewer_provider or members[0].provider
        own_label = next(
            (label for label, member in anonymized_members if member.provider == reviewer_provider),
            anonymized_members[0][0],
        )
        print(
            render_peer_review_prompt(
                bundle,
                reviewer_label=reviewer_provider,
                own_label=own_label,
                anonymized_members=anonymized_members,
            )
        )
        return
    print(render_primary_council_prompt(bundle, members))


def handle_council_outcome(args):
    bundle = load_prompt_bundle(args.bundle)
    members = load_member_results(args.members_json)
    peer_reviews = load_peer_reviews(args.peer_reviews_json) if args.peer_reviews_json else []
    needs_followup = None
    if args.needs_followup == "true":
        needs_followup = True
    elif args.needs_followup == "false":
        needs_followup = False
    aggregate = None
    if peer_reviews:
        label_to_provider = {
            f"Response {chr(ord('A') + index)}": member.provider
            for index, member in enumerate(members)
        }
        aggregate = aggregate_peer_rankings(peer_reviews, label_to_provider)
    outcome = create_council_outcome(
        bundle=bundle,
        primary_provider=args.primary_provider,
        member_results=members,
        peer_reviews=peer_reviews,
        aggregate_ranking=aggregate,
        primary_model=args.primary_model,
        primary_session_id=args.primary_session_id,
        agreement_score=args.agreement_score,
        winner_provider=args.winner_provider,
        winner_model=args.winner_model,
        needs_followup=needs_followup,
        differences=args.difference,
        synthesis_output=read_text_file(args.synthesis_output_file) if args.synthesis_output_file else None,
        metadata={"member_count": len(members)},
    )
    path = save_council_outcome(outcome)
    print(json.dumps({"outcome": outcome.to_dict(), "path": str(path)}, indent=2))


def handle_council_html(args):
    bundle = load_prompt_bundle(args.bundle)
    outcome = load_council_outcome(args.outcome) if args.outcome else None
    path = write_review_html(bundle, outcome)
    print(json.dumps({"path": str(path)}, indent=2))


def handle_council_run(args):
    config = load_config(args.config)
    bundle = load_prompt_bundle(args.bundle)
    overrides: dict[str, str] = {}
    for item in args.member_model_override:
        if "=" not in item:
            raise SystemExit("error: --member-model-override must look like provider=model")
        provider_name, model_name = item.split("=", 1)
        overrides[provider_name.strip()] = model_name.strip()
    result = run_council(
        config=config,
        bundle=bundle,
        member_providers=args.members,
        primary_provider=args.primary_provider,
        cwd=Path(args.cwd).expanduser().resolve(),
        member_model_overrides=overrides,
        primary_model_override=args.primary_model_override,
        with_peer_review=not args.without_peer_review,
    )
    print(
        json.dumps(
            {
                "outcome": result.outcome.to_dict(),
                "outcome_path": str(result.outcome_path),
                "review_path": str(result.review_path),
                "task_path": str(result.task_path) if result.task_path else None,
                "sync_path": str(result.sync_path) if result.sync_path else None,
                "launches": [launch.to_dict() for launch in result.launches],
            },
            indent=2,
        )
    )


def handle_council_start(args):
    config = load_config(args.config)
    bundle = load_prompt_bundle(args.bundle)
    cwd = Path(args.cwd).expanduser().resolve()
    status_token = getattr(args, "status_token", None)
    task = ensure_task_record(
        bundle=bundle,
        status="running",
        tags=["council"],
        metadata={"cwd": str(cwd)},
    )
    task_path = save_task_record(task)
    sync_path = save_sync_record(task)
    if status_token:
        write_council_status(
            status_token,
            status="running",
            task_text=bundle.task_text,
            bundle_id=bundle.bundle_id,
            metadata={"cwd": str(cwd)},
        )
    if args.notify:
        notify("Trinity council running", f"Starting council for: {task.title}")
    try:
        result = run_council(
            config=config,
            bundle=bundle,
            member_providers=args.members,
            primary_provider=args.primary_provider,
            cwd=cwd,
            with_peer_review=not args.without_peer_review,
        )
    except Exception as exc:
        if status_token:
            write_council_status(
                status_token,
                status="failed",
                task_text=bundle.task_text,
                bundle_id=bundle.bundle_id,
                error=str(exc),
                metadata={"cwd": str(cwd)},
            )
        raise
    final_task = load_task_record(str(result.task_path)) if result.task_path else task
    review_action = create_review_ready_action(
        task=final_task,
        command_hint=f"trinity-local open-review --task {final_task.task_id}",
    )
    review_action_path = save_action(review_action)
    if status_token:
        write_council_status(
            status_token,
            status="completed",
            task_text=bundle.task_text,
            bundle_id=bundle.bundle_id,
            council_id=result.outcome.council_run_id,
            review_path=str(result.review_path),
            metadata={"cwd": str(cwd)},
        )
    if args.notify:
        notify_action(review_action)
    opened = open_path(result.review_path) if args.open_browser else False
    print(
        json.dumps(
            {
                "task_path": str(result.task_path or task_path),
                "sync_path": str(result.sync_path or sync_path),
                "review_path": str(result.review_path),
                "review_action_path": str(review_action_path),
                "opened": opened,
            },
            indent=2,
        )
    )


def handle_council_launch(args):
    status_token = getattr(args, "status_token", None)
    metadata = {"launch_source": "launchpad"}
    if args.project_hint:
        metadata["project_hint"] = args.project_hint
    bundle = create_prompt_bundle(
        task_cluster_id=stable_id("cluster", args.project_hint, args.task[:400]),
        task_text=args.task,
        context_excerpt=read_text_file(args.context_file),
        goal=args.goal,
        comparison_instructions=args.instructions,
        origin_provider="launchpad",
        origin_session_id=status_token,
        metadata=metadata,
    )
    save_prompt_bundle(bundle)
    launch_args = type("CouncilLaunchArgs", (), {
        "config": args.config,
        "bundle": bundle.bundle_id,
        "members": args.members,
        "primary_provider": args.primary_provider,
        "cwd": args.cwd,
        "status_token": status_token,
        "open_browser": args.open_browser,
        "notify": args.notify,
        "without_peer_review": args.without_peer_review,
    })()
    handle_council_start(launch_args)


def handle_council_rate(args):
    record = append_council_feedback(
        council_id=args.council,
        provider=args.provider,
        answer_label=args.answer_label,
    )
    print(json.dumps({"feedback": record}, indent=2))
