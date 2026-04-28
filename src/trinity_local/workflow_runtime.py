from __future__ import annotations

from pathlib import Path

from .council_runtime import create_prompt_bundle, save_prompt_bundle
from .notifications import open_path
from .task_runtime import ensure_task_record, save_sync_record, save_task_record
from .task_schema import TaskRecommendation


def create_workflow_task(
    *,
    source_task,
    prompt_path: str,
    target_provider: str = "cowork",
):
    prompt_file = Path(prompt_path).expanduser().resolve()
    prompt_text = prompt_file.read_text(encoding="utf-8")
    bundle = create_prompt_bundle(
        task_cluster_id=f"workflow-{source_task.task_id[:16]}",
        task_text=prompt_text,
        goal=f"Use {target_provider} to design a Shortcut or workflow artifact for the parent task.",
        comparison_instructions="Prefer a concrete, installable local workflow with minimal setup friction.",
        origin_session_id=source_task.source_session_id,
        origin_provider="trinity",
        metadata={
            "parent_task_id": source_task.task_id,
            "target_provider": target_provider,
            "prompt_path": str(prompt_file),
        },
    )
    bundle_path = save_prompt_bundle(bundle)
    task = ensure_task_record(
        bundle=bundle,
        title=f"Create Shortcut: {source_task.title[:90]}",
        status="workflow_ready",
        recommendation=TaskRecommendation(
            recommended_provider=target_provider,
            recommended_mode="workflow_create",
            reason=f"{target_provider.capitalize()} should draft the Shortcut or workflow artifact.",
            confidence=0.66,
        ),
        tags=["workflow_upgrade"],
        metadata={
            "parent_task_id": source_task.task_id,
            "target_provider": target_provider,
            "prompt_path": str(prompt_file),
            "bundle_path": str(bundle_path),
        },
    )
    task_path = save_task_record(task)
    sync_path = save_sync_record(task)
    return task, task_path, sync_path, bundle_path


def open_workflow_prompt(prompt_path: str) -> bool:
    return open_path(prompt_path)
