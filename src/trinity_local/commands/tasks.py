"""Handlers for bundle-create, launch-create, task-create, task-show, task-sync."""
from __future__ import annotations

import hashlib
import json

from ..council_runtime import (
    append_launch_event, create_launch_event,
    create_prompt_bundle, load_prompt_bundle, save_prompt_bundle,
)
from ..task_runtime import (
    ensure_task_record, load_task_record,
    make_sync_record, save_sync_record, save_task_record,
)
from ..task_schema import TaskRecommendation
from .helpers import read_text_file


def _derive_task_cluster_id(task_text: str, project_hint: str = "") -> str:
    digest = hashlib.sha1(f"{project_hint}|{task_text}".encode("utf-8")).hexdigest()
    return digest[:16]


def register(subparsers):
    bp = subparsers.add_parser("bundle-create", help="Create and save a prompt bundle")
    bp.add_argument("task", help="Task text for the bundle")
    bp.add_argument("--project-hint", default="")
    bp.add_argument("--context-file", default=None)
    bp.add_argument("--goal", default="")
    bp.add_argument("--instructions", default="")
    bp.add_argument("--origin-session-id", default=None)
    bp.add_argument("--origin-provider", default=None)
    bp.set_defaults(handler=handle_bundle_create)

    lp = subparsers.add_parser("launch-create", help="Record a launch event")
    lp.add_argument("--bundle", required=True)
    lp.add_argument("--mode", required=True, choices=["route", "handoff", "council"])
    lp.add_argument("--source-provider", default=None)
    lp.add_argument("--target-provider", default=None)
    lp.add_argument("--target-model", default=None)
    lp.add_argument("--handoff-reason", default=None)
    lp.add_argument("--source-session-id", default=None)
    lp.add_argument("--target-session-id", default=None)
    lp.set_defaults(handler=handle_launch_create)

    tp = subparsers.add_parser("task-create", help="Create or update a durable task record")
    tp.add_argument("--bundle", required=True)
    tp.add_argument("--status", default="suggested")
    tp.add_argument("--title", default=None)
    tp.add_argument("--recommended-provider", default=None)
    tp.add_argument("--recommended-mode", default=None)
    tp.add_argument("--reason", default=None)
    tp.add_argument("--confidence", type=float, default=None)
    tp.add_argument("--tag", action="append", default=[])
    tp.set_defaults(handler=handle_task_create)

    tsp = subparsers.add_parser("task-show", help="Show a saved task record")
    tsp.add_argument("--task", required=True)
    tsp.set_defaults(handler=handle_task_show)

    tsyncp = subparsers.add_parser("task-sync", help="Write a sync-safe task payload")
    tsyncp.add_argument("--task", required=True)
    tsyncp.set_defaults(handler=handle_task_sync)


def handle_bundle_create(args):
    bundle = create_prompt_bundle(
        task_cluster_id=_derive_task_cluster_id(args.task, args.project_hint),
        task_text=args.task,
        context_excerpt=read_text_file(args.context_file),
        goal=args.goal,
        comparison_instructions=args.instructions,
        origin_session_id=args.origin_session_id,
        origin_provider=args.origin_provider,
        metadata={"project_hint": args.project_hint} if args.project_hint else {},
    )
    path = save_prompt_bundle(bundle)
    print(json.dumps({"bundle": bundle.to_dict(), "path": str(path)}, indent=2))


def handle_launch_create(args):
    bundle = load_prompt_bundle(args.bundle)
    event = create_launch_event(
        bundle=bundle, mode=args.mode,
        source_provider=args.source_provider,
        target_provider=args.target_provider,
        target_model=args.target_model,
        handoff_reason=args.handoff_reason,
        source_session_id=args.source_session_id,
        target_session_id=args.target_session_id,
    )
    append_launch_event(event)
    print(json.dumps(event.to_dict(), indent=2))


def handle_task_create(args):
    bundle = load_prompt_bundle(args.bundle)
    recommendation = None
    if any(v is not None for v in (
        args.recommended_provider, args.recommended_mode, args.reason, args.confidence,
    )):
        recommendation = TaskRecommendation(
            recommended_provider=args.recommended_provider,
            recommended_mode=args.recommended_mode,
            reason=args.reason, confidence=args.confidence,
        )
    task = ensure_task_record(
        bundle=bundle, title=args.title, status=args.status,
        recommendation=recommendation, tags=args.tag,
    )
    path = save_task_record(task)
    sync_path = save_sync_record(task)
    print(json.dumps({"task": task.to_dict(), "path": str(path), "sync_path": str(sync_path)}, indent=2))


def handle_task_show(args):
    task = load_task_record(args.task)
    print(json.dumps(task.to_dict(), indent=2))


def handle_task_sync(args):
    task = load_task_record(args.task)
    payload = make_sync_record(task)
    path = save_sync_record(task)
    print(json.dumps({"sync": payload.to_dict(), "path": str(path)}, indent=2))
