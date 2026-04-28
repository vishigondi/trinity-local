"""Handler for the review command — post-hoc review (Council-lite)."""
from __future__ import annotations

import json
import subprocess
import sys

from ..config import load_config
from ..notifications import notify
from ..review import render_review_html, run_review, save_review
from ..task_runtime import load_task_record


def register(subparsers):
    parser = subparsers.add_parser("review", help="Run a post-hoc review of a completed task")
    parser.add_argument("--task", required=True, help="Task ID to review")
    parser.add_argument("--reviewer", required=True, help="Provider to use as reviewer (e.g. gemini, codex)")
    parser.add_argument("--cwd", default=".", help="Working directory for the reviewer")
    parser.add_argument("--notify", dest="do_notify", action="store_true", help="Send macOS notification")
    parser.add_argument("--open-browser", action="store_true", help="Open review in browser")
    parser.set_defaults(handler=handle_review)


def handle_review(args):
    # Load the task to get the output
    from ..task_runtime import tasks_dir
    task_path = tasks_dir() / f"{args.task}.json"
    if not task_path.exists():
        # Try loading directly
        task = load_task_record(args.task)
    else:
        task = load_task_record(str(task_path))

    task_text = task.task_text or task.title or ""
    # Get the final output from metadata or task text
    output_text = task.metadata.get("final_text", "") if task.metadata else ""
    if not output_text:
        output_text = task_text  # Fallback — review the task description itself

    if not task_text:
        print(json.dumps({"error": "Task has no text to review"}))
        sys.exit(1)

    # Load config to get the reviewer command
    try:
        config = load_config(args.config if hasattr(args, "config") else None)
        provider_config = config.providers.get(args.reviewer)
        if provider_config:
            reviewer_command = list(provider_config.command)
        else:
            # Default CLI commands
            defaults = {
                "claude": ["claude", "-p"],
                "gemini": ["gemini"],
                "codex": ["codex", "--quiet"],
            }
            reviewer_command = defaults.get(args.reviewer, [args.reviewer])
    except FileNotFoundError:
        defaults = {
            "claude": ["claude", "-p"],
            "gemini": ["gemini"],
            "codex": ["codex", "--quiet"],
        }
        reviewer_command = defaults.get(args.reviewer, [args.reviewer])

    print(f"Running post-hoc review with {args.reviewer}...")
    result = run_review(
        task_id=task.task_id,
        task_text=task_text,
        output_text=output_text,
        original_provider=task.source_provider or "unknown",
        reviewer_provider=args.reviewer,
        reviewer_command=reviewer_command,
        cwd=args.cwd,
    )

    review_path = save_review(result)
    html_path = render_review_html(result)

    output = {
        "review_id": result.review_id,
        "task_id": result.task_id,
        "reviewer": result.reviewer_provider,
        "verdict": result.verdict,
        "issues_count": len(result.issues),
        "suggestions_count": len(result.suggestions),
        "elapsed_seconds": result.elapsed_seconds,
        "review_path": str(review_path),
        "html_path": str(html_path),
    }
    print(json.dumps(output, indent=2))

    if args.do_notify:
        summary = f"Review by {result.reviewer_provider}: {result.verdict or 'done'}"
        if result.issues:
            summary += f" ({len(result.issues)} issues)"
        notify(title="Trinity Post-Hoc Review", message=summary)

    if args.open_browser:
        subprocess.run(["open", str(html_path)], check=False)
