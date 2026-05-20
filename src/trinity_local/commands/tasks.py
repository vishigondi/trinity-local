"""Importable utility — task / bundle / launch-event handlers (CLIs retired pre-launch).

The standalone `trinity-local bundle-create / launch-create /
task-create / task-show / task-sync` CLIs were retired in the
pre-launch simplification (council scope folded these flows inline).
Tests still import `handle_*` for handler-level coverage; main.py
doesn't register this module into the CLI surface.
"""
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
