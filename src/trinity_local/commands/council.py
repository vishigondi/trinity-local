"""Council command handlers."""
from __future__ import annotations

import json
import os
import re
import shutil
import signal
from pathlib import Path
from types import SimpleNamespace

from ..config import load_config
from ..council_feedback import append_council_feedback
from ..council_review import write_live_council_page, write_unified_council_page
from ..council_runner import run_council
from ..council_runtime import (
    create_prompt_bundle,
    create_council_outcome,
    load_council_outcome,
    load_prompt_bundle,
    render_member_prompt,
    render_primary_council_prompt,
    save_prompt_bundle,
    save_council_outcome,
)
from ..council_status import (
    council_status_json_path,
    init_council_run_state,
    load_council_status,
    write_council_status,
)
from ..action_runtime import create_review_ready_action, save_action
from ..notifications import open_path
from ..refresh import refresh_launchpad
from ..task_runtime import ensure_task_record, load_task_record, save_sync_record, save_task_record
from ..utils import stable_id
from .helpers import load_member_results, read_text_file


def _status_metadata(*, members: list[str], cwd: Path, pid: int | None = None, process_group_id: int | None = None) -> dict[str, object]:
    metadata: dict[str, object] = {
        "kind": "council",
        "members": members,
        "cwd": str(cwd),
    }
    if pid is not None:
        metadata["pid"] = pid
    if process_group_id is not None:
        metadata["process_group_id"] = process_group_id
    return metadata


def register(subparsers):
    prompt_parser = subparsers.add_parser("council-prompt", help="Render a council member or primary prompt")
    prompt_parser.add_argument("--bundle", required=True, help="Bundle id or path")
    prompt_parser.add_argument("--kind", required=True, choices=["member", "primary"])
    prompt_parser.add_argument("--members-json", default=None, help="JSON file with member results for primary prompt")
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
    outcome_parser.set_defaults(handler=handle_council_outcome)

    council_run_parser = subparsers.add_parser("council-run", help="Launch member providers and synthesize a council result")
    council_run_parser.add_argument("--bundle", required=True, help="Bundle id or path")
    council_run_parser.add_argument("--members", nargs="+", required=True, help="Member providers to query")
    council_run_parser.add_argument(
        "--primary-provider",
        default=None,
        help="Chairman/synthesizer provider. If omitted, auto-selected as the strongest predicted model for the task.",
    )
    council_run_parser.add_argument("--cwd", default=".", help="Working directory for provider runs")
    council_run_parser.add_argument(
        "--member-model-override",
        action="append",
        default=[],
        help="Repeatable provider=model override for council members",
    )
    council_run_parser.add_argument("--primary-model-override", default=None)
    council_run_parser.set_defaults(handler=handle_council_run)

    council_start_parser = subparsers.add_parser("council-start", help="Create/update task, run council, and optionally open the review page")
    council_start_parser.add_argument("--bundle", required=True, help="Bundle id or path")
    council_start_parser.add_argument("--members", nargs="+", required=True, help="Member providers to query")
    council_start_parser.add_argument(
        "--primary-provider",
        default=None,
        help="Chairman/synthesizer provider. If omitted, auto-selected as the strongest predicted model for the task.",
    )
    council_start_parser.add_argument("--cwd", default=".", help="Working directory for provider runs")
    council_start_parser.add_argument("--status-token", default=None, help="Launchpad status token for same-tab council tracking")
    council_start_parser.add_argument("--open-browser", action="store_true")
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
    # Default = enabled subset of canonical providers, not hardcoded 3-up.
    # Codex-only / claude-only / gemini-only users no longer fire a broken
    # 3-column council (persona audit P89). User can still pass --members
    # claude gemini codex to force the full lineup.
    from ..config import default_council_members
    council_launch_parser.add_argument("--members", nargs="+", default=default_council_members())
    council_launch_parser.add_argument(
        "--primary-provider",
        default=None,
        help="Chairman/synthesizer provider. If omitted, auto-selected as the strongest predicted model for the task.",
    )
    council_launch_parser.add_argument("--cwd", default=".")
    council_launch_parser.add_argument("--status-token", default=None)
    council_launch_parser.add_argument("--open-browser", action="store_true")
    council_launch_parser.set_defaults(handler=handle_council_launch)

    council_rate_parser = subparsers.add_parser(
        "council-rate",
        help="Record a user's preferred provider for a council result",
    )
    council_rate_parser.add_argument("--council", required=True)
    council_rate_parser.add_argument("--provider", required=True)
    council_rate_parser.add_argument("--answer-label", default=None)
    council_rate_parser.set_defaults(handler=handle_council_rate)

    council_stop_parser = subparsers.add_parser(
        "council-stop",
        help="Stop a running council launched from the launchpad",
    )
    council_stop_parser.add_argument("--status-token", required=True)
    council_stop_parser.set_defaults(handler=handle_council_stop)

    council_share_parser = subparsers.add_parser(
        "council-share",
        help="Render a council outcome as a 1200×630 PNG share card (privacy-safe — no user prompts inlined)",
    )
    council_share_parser.add_argument("--council", required=True, help="Council ID")
    council_share_parser.add_argument(
        "--out", default=None,
        help="Output PNG path. Defaults to ~/.trinity/share/council_<id8>.png.",
    )
    council_share_parser.add_argument(
        "--open", dest="open_after", action="store_true",
        help="Open the produced PNG with the OS default handler.",
    )
    council_share_parser.set_defaults(handler=handle_council_share)

    # Single unified iteration command. Replaces the prior trio of
    # council-continue / council-refine / council-auto-chain — they all
    # called the same engine (run_consensus_round / auto_chain_council)
    # with one flag varied. One command keyed by (rounds, prompt) collapses
    # the surface without losing any behavior:
    #   council-iterate --rounds 1               → former "continue"
    #   council-iterate --rounds 1 --prompt P    → former "refine"
    #   council-iterate --rounds N               → former "auto-chain"
    council_iterate_parser = subparsers.add_parser(
        "council-iterate",
        help="Iterate an existing council. With --prompt, run one round under that "
             "directive. Without --prompt, auto-iterate up to --rounds, stopping when "
             "the chairman declares convergence (agreed_claims rich, disagreed_claims "
             "empty, confidence high).",
    )
    council_iterate_parser.add_argument("--council", required=True, help="Parent council_run_id")
    council_iterate_parser.add_argument(
        "--rounds", type=int, default=3,
        help="Max rounds when auto-iterating; ignored when --prompt is set (always 1 round).",
    )
    council_iterate_parser.add_argument(
        "--prompt", default=None,
        help="New user directive. If set, runs one round under this directive instead of auto-iterating.",
    )
    council_iterate_parser.add_argument("--cwd", default=".")
    council_iterate_parser.add_argument(
        "--status-token", default=None,
        help="Reuse this status token so iteration rounds overwrite the same live page.",
    )
    council_iterate_parser.add_argument("--open-browser", action="store_true")
    council_iterate_parser.set_defaults(handler=handle_council_iterate)


def handle_council_prompt(args):
    bundle = load_prompt_bundle(args.bundle)
    if args.kind == "member":
        print(render_member_prompt(bundle))
        return
    members = load_member_results(args.members_json) if args.members_json else []
    print(render_primary_council_prompt(bundle, members))


def handle_council_outcome(args):
    bundle = load_prompt_bundle(args.bundle)
    members = load_member_results(args.members_json)
    needs_followup = None
    if args.needs_followup == "true":
        needs_followup = True
    elif args.needs_followup == "false":
        needs_followup = False
    outcome = create_council_outcome(
        bundle=bundle,
        primary_provider=args.primary_provider,
        member_results=members,
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


def handle_council_run(args):
    config = load_config(args.config)
    bundle = load_prompt_bundle(args.bundle)
    overrides: dict[str, str] = {}
    for item in args.member_model_override:
        if "=" not in item:
            raise SystemExit("error: --member-model-override must look like provider=model")
        provider_name, model_name = item.split("=", 1)
        overrides[provider_name.strip()] = model_name.strip()
    primary_provider = args.primary_provider
    if not primary_provider:
        from ..ranker import predict_strongest_chairman

        primary_provider = predict_strongest_chairman(
            bundle.task_text,
            available_providers=list(args.members),
        )
    result = run_council(
        config=config,
        bundle=bundle,
        member_providers=args.members,
        primary_provider=primary_provider,
        cwd=Path(args.cwd).expanduser().resolve(),
        member_model_overrides=overrides,
        primary_model_override=args.primary_model_override,
        run_state_token=bundle.bundle_id,
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
    if not args.primary_provider:
        from ..ranker import predict_strongest_chairman

        args.primary_provider = predict_strongest_chairman(
            bundle.task_text,
            available_providers=list(args.members),
        )
    process_id = os.getpid()
    process_group_id = os.getpgid(0)
    status_metadata = _status_metadata(
        members=list(args.members),
        cwd=cwd,
        pid=process_id,
        process_group_id=process_group_id,
    )
    completed_metadata = _status_metadata(members=list(args.members), cwd=cwd)
    task = ensure_task_record(
        bundle=bundle,
        status="running",
        tags=["council"],
        metadata={"cwd": str(cwd)},
    )
    task_path = save_task_record(task)
    sync_path = save_sync_record(task)
    original_sigterm = signal.getsignal(signal.SIGTERM)
    original_sigint = signal.getsignal(signal.SIGINT)

    def _mark_canceled(message: str) -> None:
        task.status = "canceled"
        save_task_record(task)
        save_sync_record(task)
        if status_token:
            write_council_status(
                status_token,
                status="canceled",
                task_text=bundle.task_text,
                bundle_id=bundle.bundle_id,
                council_id=bundle.bundle_id,
                error=message,
                metadata=status_metadata,
            )
        refresh_launchpad()

    def _termination_handler(signum, _frame):  # type: ignore[no-untyped-def]
        sig_name = signal.Signals(signum).name
        _mark_canceled(f"Council stopped ({sig_name}).")
        raise SystemExit(143)

    signal.signal(signal.SIGTERM, _termination_handler)
    signal.signal(signal.SIGINT, _termination_handler)
    if status_token:
        init_council_run_state(
            status_token,
            task_text=bundle.task_text,
            bundle_id=bundle.bundle_id,
            council_id=bundle.bundle_id,
            members=list(args.members),
            metadata=status_metadata,
            runner_pid=process_id,
            runner_pgid=process_group_id,
        )
        refresh_launchpad()
    # Skip the "Council running" start notification by default. The live
    # council page already opens to a "Council running" status view with
    # streaming member responses — a system notification on top of that
    # is redundant and uses Script Editor's generic icon (no Trinity
    # branding) plus a "Show" button that opens an unhelpful preview pane.
    # Completion notifications still fire because they tell you something
    # the page can't (the run finished while you weren't looking).
    try:
        result = run_council(
            config=config,
            bundle=bundle,
            member_providers=args.members,
            primary_provider=args.primary_provider,
            cwd=cwd,
            run_state_token=status_token or bundle.bundle_id,
            # Honor chain mode end-to-end. Without these, the runner ignored
            # the caller's intent and dispatched parallel — silent drift
            # between the reported mode and the actual execution.
            mode=getattr(args, "mode", "parallel") or "parallel",
            sequence=getattr(args, "sequence", None),
        )
    except Exception as exc:
        if status_token:
            write_council_status(
                status_token,
                status="failed",
                task_text=bundle.task_text,
                bundle_id=bundle.bundle_id,
                error=str(exc),
                metadata=status_metadata,
            )
        refresh_launchpad()
        raise
    finally:
        signal.signal(signal.SIGTERM, original_sigterm)
        signal.signal(signal.SIGINT, original_sigint)
    final_task = load_task_record(str(result.task_path)) if result.task_path else task
    review_action = create_review_ready_action(
        task=final_task,
        command_hint=f"trinity-local open-review --task {final_task.task_id}",
    )
    review_action_path = save_action(review_action)
    if status_token and load_council_status(status_token) is None:
        write_council_status(
            status_token,
            status="completed",
            task_text=bundle.task_text,
            bundle_id=bundle.bundle_id,
            council_id=result.outcome.council_run_id,
            review_path=str(result.review_path),
            metadata=completed_metadata,
        )
    refresh_launchpad()

    # Auto-chain: if user opted in, kick off consensus rounds until convergence
    # OR max_chain_rounds. Chairman chairs the convergence call (chairman_says_converged).
    auto_chain_summary: list[dict] | None = None
    final_review_path = result.review_path
    final_outcome = result.outcome
    try:
        from ..telemetry import load_telemetry_settings
        from ..council_runner import auto_chain_council
        from ..council_runtime import chairman_says_converged

        settings = load_telemetry_settings()
        # Two paths fire auto-chain:
        #   (a) global `auto_chain_enabled` — auto-iterate every council
        #   (b) targeted `polish_auto_iterate` — only when the task is
        #       polish-shaped (make-this-better / tighten / etc.). Default
        #       OFF; lets the user opt into iteration without blanket-
        #       firing it on architecture or debugging questions.
        from ..task_types import is_polish_task
        should_auto_chain = bool(settings.auto_chain_enabled) or (
            bool(settings.polish_auto_iterate) and is_polish_task(bundle.task_text)
        )
        if should_auto_chain:
            chain_results = auto_chain_council(
                config=config,
                initial_outcome=result.outcome,
                max_rounds=int(settings.max_chain_rounds or 3),
                cwd=cwd,
                # Reuse the original status token (or bundle id as token) so
                # auto-chain rounds keep updating the same live launchpad page.
                run_state_token=status_token or bundle.bundle_id,
            )
            auto_chain_summary = []
            for r in chain_results:
                lbl = r.outcome.routing_label
                auto_chain_summary.append({
                    "round_number": r.outcome.metadata.get("round_number"),
                    "council_run_id": r.outcome.council_run_id,
                    "review_path": str(r.review_path),
                    "winner": lbl.winner if lbl else None,
                    "converged": chairman_says_converged(lbl),
                })
            if chain_results:
                final_review_path = chain_results[-1].review_path
                final_outcome = chain_results[-1].outcome
                refresh_launchpad()
    except Exception as exc:
        # Auto-chain failure must not crash the original council run.
        auto_chain_summary = [{"error": f"{type(exc).__name__}: {exc}"}]

    opened = open_path(final_review_path) if args.open_browser else False
    payload = {
        "task_path": str(result.task_path or task_path),
        "sync_path": str(result.sync_path or sync_path),
        "review_path": str(final_review_path),
        "review_action_path": str(review_action_path),
        "opened": opened,
        "council_run_id": final_outcome.council_run_id,
    }
    if auto_chain_summary is not None:
        payload["auto_chain"] = auto_chain_summary
    print(json.dumps(payload, indent=2))


def handle_council_launch(args):
    status_token = getattr(args, "status_token", None)
    metadata = {
        "launch_source": "launchpad",
        "members": list(args.members),
    }
    if status_token:
        metadata["status_token"] = status_token
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
    if status_token:
        write_live_council_page()
    launch_args = SimpleNamespace(
        config=args.config,
        bundle=bundle.bundle_id,
        members=args.members,
        primary_provider=args.primary_provider,
        cwd=args.cwd,
        status_token=status_token,
        open_browser=args.open_browser,
        # Thread chain-mode params through to run_council. Before this fix,
        # handle_council_start dropped them and silently ran parallel even
        # when the caller (MCP `run_council(mode='chain')`) reported chain.
        mode=getattr(args, "mode", "parallel"),
        sequence=getattr(args, "sequence", None),
    )
    handle_council_start(launch_args)


def handle_council_rate(args):
    record = append_council_feedback(
        council_id=args.council,
        provider=args.provider,
        answer_label=args.answer_label,
    )
    outcome = load_council_outcome(args.council)
    bundle = load_prompt_bundle(outcome.bundle_id)

    # Persist the user's verdict to the outcome JSON so the live council page
    # rehydrates the "Preferred" badge on reload. The MCP record_outcome tool
    # writes the same shape; without this the launchpad's one-click rating
    # was a feedback-log-only no-op as far as the UI was concerned (clicking
    # a winner showed a green pill, reloading lost it). Discovered during
    # the Surface 6 click-test: outcome.selected_provider stayed None across
    # 21 council_feedback entries.
    outcome.metadata.setdefault("user_verdict", {})
    outcome.metadata["user_verdict"].update({
        "user_winner": args.provider,
        "accepted": True,
        "abandoned": False,
    })
    if args.answer_label:
        outcome.metadata["user_verdict"]["answer_label"] = args.answer_label
    from ..council_runtime import save_council_outcome  # local import; keeps top of file unchanged
    save_council_outcome(outcome)

    # Propagate the user's verdict to the originating PromptNode so the
    # personal routing table compounds. The MCP record_outcome tool does this
    # too — keeping the launchpad's one-click flow in sync makes every
    # rated council a labeled training row regardless of which surface fired
    # the rating.
    propagated_to_prompt_node = False
    metadata = outcome.metadata or {}
    prompt_node_id = metadata.get("prompt_node_id")
    if prompt_node_id:
        try:
            from ..memory import record_council_outcome as _record_to_prompt_node

            chairman_winner = None
            label = outcome.routing_label
            if label is not None:
                chairman_winner = getattr(label, "winner", None)
            propagated_to_prompt_node = _record_to_prompt_node(
                prompt_node_id=prompt_node_id,
                council_run_id=outcome.council_run_id,
                chairman_winner=chairman_winner,
                user_winner=args.provider,
            )
        except Exception:
            propagated_to_prompt_node = False

    # The personal routing table is computed on demand from rated outcomes;
    # this rate event will appear there automatically the next time the
    # launchpad renders or chairman_picker runs. Surface the current count
    # for the CLI response so the caller can confirm the table is non-empty.
    try:
        from ..personal_routing import compute_personal_routing_table, invalidate_cache

        invalidate_cache()
        councils_aggregated = compute_personal_routing_table().get("councils_aggregated", 0)
    except Exception:
        councils_aggregated = None

    review_path = write_unified_council_page(bundle, outcome)
    portal_path = refresh_launchpad()
    print(json.dumps({
        "feedback": record,
        "portal_path": str(portal_path),
        "review_path": str(review_path),
        "propagated_to_prompt_node": propagated_to_prompt_node,
        "prompt_node_id": prompt_node_id,
        "personal_routing_table_councils": councils_aggregated,
    }, indent=2))


def handle_council_stop(args):
    status_token = args.status_token
    status_path = council_status_json_path(status_token)
    if not status_path.exists():
        print(json.dumps({"stopped": False, "reason": "status_not_found", "status_token": status_token}, indent=2))
        return

    raw = json.loads(status_path.read_text(encoding="utf-8"))
    metadata = dict(raw.get("metadata") or {})
    task_text = raw.get("task_text")
    bundle_id = raw.get("bundle_id")
    council_id = raw.get("council_id")
    pid = raw.get("runner_pid") or metadata.get("pid")
    pgid = raw.get("runner_pgid") or metadata.get("process_group_id")

    write_council_status(
        status_token,
        status="canceled",
        task_text=task_text,
        bundle_id=bundle_id,
        council_id=council_id,
        error="Council stopped by user.",
        metadata=metadata,
    )
    refresh_launchpad()

    killed = False
    kill_error = None
    try:
        if pgid:
            os.killpg(int(pgid), signal.SIGTERM)
            killed = True
        elif pid:
            os.kill(int(pid), signal.SIGTERM)
            killed = True
    except OSError as exc:
        kill_error = str(exc)
        if "No such process" in kill_error:
            killed = True

    print(
        json.dumps(
            {
                "stopped": killed,
                "status_token": status_token,
                "pid": pid,
                "process_group_id": pgid,
                "error": kill_error,
            },
            indent=2,
        )
    )


def handle_council_share(args):
    """Render a council outcome as a 1200×630 PNG share card.

    Rewritten 2026-05-17 (iteration 5 of the share-workflow audit).
    Prior implementation copied write_unified_council_page's redirect
    HTML (379 bytes pointing at a relative `live_council.html?...` path)
    to Desktop — which was useless to any recipient because the
    relative path resolved only on the author's filesystem.

    New shape: PNG card matching eval_card + me_card. Three share
    surfaces, one visual language. Privacy-safe by construction —
    only the chairman-extracted agreed_claims / disagreed_claims /
    winner cross to the card. The user's verbatim prompt + members'
    full response text never touch the artifact, AND the prompt no
    longer leaks into the output filename (former bug).
    """
    from ..council_card import collect_card_data_from_outcome, render_council_card
    from ..state_paths import state_dir

    outcome = load_council_outcome(args.council)
    # Strip the "council_" prefix when slicing the id for the filename —
    # the prior code used outcome.council_run_id[:8] which (since the
    # id starts with literal "council_") produced filenames like
    # "trinity-council-council_-..." with a useless prefix.
    id_short = outcome.council_run_id.removeprefix("council_")[:8] or "anon"

    card_data = collect_card_data_from_outcome(outcome)
    png_bytes = render_council_card(card_data)

    out = (Path(args.out) if args.out
           else state_dir() / "share" / f"council_{id_short}.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(png_bytes)

    opened = False
    if args.open_after:
        opened = open_path(out)

    print(json.dumps({
        "ok": True,
        "path": str(out),
        "bytes": len(png_bytes),
        "council_id": outcome.council_run_id,
        "winner": card_data.winner,
        "members": list(card_data.members),
        "agreed_claims_count": len(card_data.agreed_claims),
        "disagreed_claim_present": card_data.disagreed_claim is not None,
        "opened": opened,
    }, indent=2))


# ---------------------------------------------------------------------------
# Consensus-iteration chain handlers
# ---------------------------------------------------------------------------


def _print_round_summary(result, round_label: str) -> None:
    outcome = result.outcome
    label = outcome.routing_label
    summary = {
        "round": round_label,
        "council_run_id": outcome.council_run_id,
        "review_path": str(result.review_path),
        "primary_provider": outcome.primary_provider,
        "winner_provider": outcome.winner_provider,
        "parent_council_id": outcome.metadata.get("parent_council_id"),
        "round_number": outcome.metadata.get("round_number"),
    }
    if label is not None:
        summary["winner"] = label.winner
        summary["confidence"] = label.confidence
        summary["agreed_claims"] = len(label.agreed_claims)
        summary["disagreed_claims"] = len(label.disagreed_claims)
        from ..council_runtime import chairman_says_converged
        summary["converged"] = chairman_says_converged(label)
    print(json.dumps(summary, indent=2))


def handle_council_iterate(args):
    """Unified iteration: rounds + optional --prompt directive. Replaces the
    prior trio of continue/refine/auto-chain handlers; they were all variants
    of the same `run_consensus_round` / `auto_chain_council` engine."""
    from ..council_runner import auto_chain_council, run_consensus_round

    config = load_config(args.config)
    parent = load_council_outcome(args.council)
    cwd = Path(args.cwd).expanduser().resolve()
    status_token = getattr(args, "status_token", None)

    # When the user asks for a single round (with or without --prompt), they
    # want a forced continuation — the launchpad's "continue" button must
    # work even when the parent already converged. Skip auto_chain_council's
    # convergence gate; run exactly one round.
    if args.prompt or args.rounds == 1:
        result = run_consensus_round(
            config=config,
            parent_outcome=parent,
            user_refinement=args.prompt,
            cwd=cwd,
            run_state_token=status_token,
        )
        if args.open_browser:
            open_path(result.review_path)
        _print_round_summary(result, round_label="refine" if args.prompt else "continue")
        return

    # rounds > 1, no prompt → auto-iterate, stop on convergence.
    results = auto_chain_council(
        config=config,
        initial_outcome=parent,
        max_rounds=args.rounds,
        cwd=cwd,
        run_state_token=status_token,
    )
    if results and args.open_browser:
        open_path(results[-1].review_path)

    # Per-round summary
    rounds = []
    for i, r in enumerate(results):
        outcome = r.outcome
        label = outcome.routing_label
        rounds.append({
            "round_number": outcome.metadata.get("round_number"),
            "council_run_id": outcome.council_run_id,
            "review_path": str(r.review_path),
            "winner": label.winner if label else None,
            "confidence": label.confidence if label else None,
            "agreed_claims": len(label.agreed_claims) if label else 0,
            "disagreed_claims": len(label.disagreed_claims) if label else 0,
        })

    from ..council_runtime import chairman_says_converged
    final = results[-1].outcome if results else parent
    print(json.dumps({
        "ok": True,
        "initial_council_run_id": parent.council_run_id,
        "rounds_run": len(results),
        "max_rounds": args.rounds,
        "converged": chairman_says_converged(final.routing_label),
        "final_council_run_id": final.council_run_id,
        "rounds": rounds,
    }, indent=2))
