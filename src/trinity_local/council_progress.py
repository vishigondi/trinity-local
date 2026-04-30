"""Compatibility wrappers for older council progress imports.

Council run-state now lives in the unified council status files. This module
keeps older imports working while the remaining callers are migrated.
"""
from __future__ import annotations

from .council_status import (
    finalize_council_run_state,
    init_council_run_state,
    start_member_progress,
    update_member_failure,
    update_member_progress,
    update_synthesis_progress,
)
from .state_paths import council_status_dir as council_progress_dir
from .state_paths import council_status_js_path as council_progress_js_path
from .state_paths import council_status_json_path as council_progress_json_path


def init_council_progress(council_id: str, member_providers: list[str]):
    return init_council_run_state(
        council_id,
        task_text="Council",
        bundle_id=council_id,
        council_id=council_id,
        members=member_providers,
        metadata={"kind": "council"},
    )


def cleanup_progress(_council_id: str) -> None:
    """Progress is now part of the unified council status file and is retained."""
    return None


def finalize_council_progress(council_id: str) -> None:
    finalize_council_run_state(council_id, status="completed")


__all__ = [
    "cleanup_progress",
    "council_progress_dir",
    "council_progress_js_path",
    "council_progress_json_path",
    "finalize_council_progress",
    "init_council_progress",
    "init_council_run_state",
    "start_member_progress",
    "update_member_failure",
    "update_member_progress",
    "update_synthesis_progress",
]
