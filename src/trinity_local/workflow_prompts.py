from __future__ import annotations

from pathlib import Path

from .state_paths import workflow_prompt_dir
from .task_schema import TaskRecord
from .training_schema import SessionFeatures


def render_cowork_shortcut_prompt(*, task: TaskRecord, features: SessionFeatures, workflow_reason: str) -> str:
    source_provider = task.source_provider or features.provider
    cwd = features.cwd or task.metadata.get("cwd") or "."
    task_text = task.task_text or features.first_user_text or task.title
    context = features.final_text or features.planner_text or ""
    return f"""# Cowork Prompt: Create A Shortcut

You are helping the user create a macOS Shortcut or lightweight workflow.

## Goal

Design a Shortcut or small local workflow that reduces repetition for this task pattern.

## Why Trinity Suggested This

{workflow_reason}

## Current Task

{task_text}

## Current App Context

- Source app: {source_provider}
- Working directory: {cwd}
- Current Trinity task id: {task.task_id}

## What To Produce

1. A suggested Shortcut name.
2. The exact user-facing trigger.
3. The list of Shortcut steps.
4. Any AppleScript or shell step needed.
5. The minimal setup instructions.
6. A note on tradeoffs or fragility.

## Constraints

- Prefer Shortcuts first.
- Use AppleScript only where needed.
- Keep it local-first.
- Avoid requiring a persistent server.
- Make the workflow easy for a normal macOS user to install.

## Existing Context

{context or "(no extra context recorded)"}
"""


def write_cowork_shortcut_prompt(*, task: TaskRecord, features: SessionFeatures, workflow_reason: str) -> Path:
    path = workflow_prompt_dir() / f"{task.task_id}_cowork_shortcut.md"
    path.write_text(
        render_cowork_shortcut_prompt(
            task=task,
            features=features,
            workflow_reason=workflow_reason,
        ),
        encoding="utf-8",
    )
    return path
