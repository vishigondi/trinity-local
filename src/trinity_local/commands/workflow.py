"""Handler for workflow-create."""
from __future__ import annotations

import json

from ..notifications import open_path as _open_path
from ..task_runtime import load_task_record
from ..workflow_runtime import create_workflow_task, open_workflow_prompt


def register(subparsers):
    wp = subparsers.add_parser("workflow-create", help="Create a routed workflow-upgrade task from a suggestion prompt")
    wp.add_argument("--task", required=True)
    wp.add_argument("--prompt-path", required=True)
    wp.add_argument("--target-provider", default="cowork")
    wp.add_argument("--open-prompt", action="store_true")
    wp.set_defaults(handler=handle_workflow_create)


def handle_workflow_create(args):
    source_task = load_task_record(args.task)
    workflow_task, task_path, sync_path, bundle_path = create_workflow_task(
        source_task=source_task,
        prompt_path=args.prompt_path,
        target_provider=args.target_provider,
    )
    opened = open_workflow_prompt(args.prompt_path) if args.open_prompt else False
    print(json.dumps({
        "workflow_task": workflow_task.to_dict(),
        "task_path": str(task_path),
        "sync_path": str(sync_path),
        "bundle_path": str(bundle_path),
        "opened_prompt": opened,
    }, indent=2))
