from __future__ import annotations

from pathlib import Path

from .config import trinity_home


def state_dir() -> Path:
    return trinity_home()


def prompt_bundles_dir() -> Path:
    path = state_dir() / "prompt_bundles"
    path.mkdir(parents=True, exist_ok=True)
    return path


def council_outcomes_dir() -> Path:
    path = state_dir() / "council_outcomes"
    path.mkdir(parents=True, exist_ok=True)
    return path


def council_runs_path() -> Path:
    return state_dir() / "council_runs.jsonl"


def launch_events_path() -> Path:
    return state_dir() / "launch_events.jsonl"


def council_feedback_path() -> Path:
    return state_dir() / "council_feedback.jsonl"


def review_pages_dir() -> Path:
    path = state_dir() / "review_pages"
    path.mkdir(parents=True, exist_ok=True)
    return path


def portal_pages_dir() -> Path:
    path = state_dir() / "portal_pages"
    path.mkdir(parents=True, exist_ok=True)
    return path


def council_status_dir() -> Path:
    path = portal_pages_dir() / "status"
    path.mkdir(parents=True, exist_ok=True)
    return path


def council_status_json_path(status_token: str) -> Path:
    return council_status_dir() / f"council_status_{status_token}.json"


def council_status_js_path(status_token: str) -> Path:
    return council_status_dir() / f"council_status_{status_token}.js"


def shortcut_setup_dir() -> Path:
    path = state_dir() / "shortcut_setup"
    path.mkdir(parents=True, exist_ok=True)
    return path


def shortcut_bin_dir() -> Path:
    path = state_dir() / "bin"
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_dir() -> Path:
    path = state_dir() / "cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def embeddings_cache_path() -> Path:
    return cache_dir() / "embeddings.jsonl"


def research_dir() -> Path:
    path = state_dir() / "research"
    path.mkdir(parents=True, exist_ok=True)
    return path


# --- Paths migrated from individual modules (Phase 0) ---


def tasks_dir() -> Path:
    path = state_dir() / "tasks"
    path.mkdir(parents=True, exist_ok=True)
    return path


def task_sync_dir() -> Path:
    path = state_dir() / "task_sync"
    path.mkdir(parents=True, exist_ok=True)
    return path


def actions_dir() -> Path:
    path = state_dir() / "actions"
    path.mkdir(parents=True, exist_ok=True)
    return path


def reviews_dir() -> Path:
    path = state_dir() / "reviews"
    path.mkdir(parents=True, exist_ok=True)
    return path


def digest_pages_dir() -> Path:
    path = state_dir() / "digest_pages"
    path.mkdir(parents=True, exist_ok=True)
    return path


def telemetry_settings_dir() -> Path:
    path = state_dir() / "settings"
    path.mkdir(parents=True, exist_ok=True)
    return path


def analytics_dir() -> Path:
    path = state_dir() / "analytics"
    path.mkdir(parents=True, exist_ok=True)
    return path


def watcher_dir() -> Path:
    path = state_dir() / "watcher"
    path.mkdir(parents=True, exist_ok=True)
    return path


def workflow_prompt_dir() -> Path:
    path = state_dir() / "workflow_prompts"
    path.mkdir(parents=True, exist_ok=True)
    return path


def hard_examples_dir() -> Path:
    path = research_dir() / "hard_examples"
    path.mkdir(parents=True, exist_ok=True)
    return path


def replay_examples_dir() -> Path:
    path = research_dir() / "examples"
    path.mkdir(parents=True, exist_ok=True)
    return path
