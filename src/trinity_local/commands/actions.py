"""Handlers for action-suggest, action-council, action-list, action-notify, action-complete."""
from __future__ import annotations

import json

from ..action_runtime import (
    create_council_start_action, create_recommendation_action,
    list_actions, load_action, mark_action_status,
    notify_action, save_action,
)
from ..council_runtime import load_prompt_bundle
from ..task_runtime import load_task_record
from ..shortcuts_integration import DEFAULT_SHORTCUT_NAME


def register(subparsers):
    sp = subparsers.add_parser("action-suggest", help="Create a pending recommendation action from a task")
    sp.add_argument("--task", required=True)
    sp.add_argument("--bundle", default=None)
    sp.add_argument("--notify", action="store_true")
    sp.set_defaults(handler=handle_action_suggest)

    cp = subparsers.add_parser("action-council", help="Create a no-prompt Start Council action for a task")
    cp.add_argument("--task", required=True)
    cp.add_argument("--bundle", required=True)
    cp.add_argument("--members", nargs="+", required=True)
    cp.add_argument("--primary-provider", required=True)
    cp.add_argument("--cwd", default=".")
    cp.add_argument("--notify", action="store_true")
    cp.set_defaults(handler=handle_action_council)

    lp = subparsers.add_parser("action-list", help="List saved actions")
    lp.add_argument("--status", default=None, choices=["pending", "running", "completed", "dismissed"])
    lp.set_defaults(handler=handle_action_list)

    np = subparsers.add_parser("action-notify", help="Send a local notification for an action")
    np.add_argument("--action", required=True)
    np.set_defaults(handler=handle_action_notify)

    xp = subparsers.add_parser("action-complete", help="Mark an action complete or dismissed")
    xp.add_argument("--action", required=True)
    xp.add_argument("--status", required=True, choices=["running", "completed", "dismissed"])
    xp.set_defaults(handler=handle_action_complete)


def handle_action_suggest(args):
    task = load_task_record(args.task)
    bundle_id = load_prompt_bundle(args.bundle).bundle_id if args.bundle else None
    command_hint = None
    if bundle_id and task.recommendation and task.recommendation.recommended_mode == "council":
        command_hint = f"trinity-local council-start --bundle {bundle_id} --members gemini codex --primary-provider claude --cwd ."
    action = create_recommendation_action(task=task, bundle_id=bundle_id, command_hint=command_hint)
    path = save_action(action)
    if args.notify:
        notify_action(action)
    print(json.dumps({"action": action.to_dict(), "path": str(path)}, indent=2))


def handle_action_council(args):
    task = load_task_record(args.task)
    bundle = load_prompt_bundle(args.bundle)
    action = create_council_start_action(
        task=task, bundle_id=bundle.bundle_id,
        members=args.members, primary_provider=args.primary_provider, cwd=args.cwd,
    )
    path = save_action(action)
    if args.notify:
        notify_action(action)
    print(json.dumps({"action": action.to_dict(), "path": str(path)}, indent=2))


def handle_action_list(args):
    actions = [a.to_dict() for a in list_actions(status=args.status)]
    print(json.dumps(actions, indent=2))


def handle_action_notify(args):
    action = load_action(args.action)
    notify_action(action)
    print(json.dumps(action.to_dict(), indent=2))


def handle_action_complete(args):
    action = load_action(args.action)
    action = mark_action_status(action, args.status)
    path = save_action(action)
    print(json.dumps({"action": action.to_dict(), "path": str(path)}, indent=2))
