from __future__ import annotations

from pathlib import Path

from .config import trinity_home


# v1 schema lock. Bump only when the on-disk layout changes in a way that
# requires a migration. v2 adds new subdirs (videos/, lens/, models/) without
# renaming existing ones — those land at SCHEMA_VERSION 2. See docs/spec-v1.md
# "Folder layout" and docs/spec-v2.md "Foundations laid in v1."
SCHEMA_VERSION = "1"


def state_dir() -> Path:
    home = trinity_home()
    # Lazily anchor the schema version. Written once; future bumps go through
    # an explicit migration script that updates this file under a transaction.
    _ensure_schema_version(home)
    return home


def _ensure_schema_version(home: Path) -> None:
    schema_path = home / "SCHEMA_VERSION"
    if schema_path.exists():
        return
    try:
        home.mkdir(parents=True, exist_ok=True)
        schema_path.write_text(SCHEMA_VERSION + "\n", encoding="utf-8")
    except OSError:
        pass


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


def outcomes_log_path() -> Path:
    return state_dir() / "outcomes.jsonl"


def research_dir() -> Path:
    path = state_dir() / "research"
    path.mkdir(parents=True, exist_ok=True)
    return path


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


def models_dir() -> Path:
    path = state_dir() / "models"
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


def memory_dir() -> Path:
    path = state_dir() / "memory"
    path.mkdir(parents=True, exist_ok=True)
    return path


def cortex_dir() -> Path:
    """v1.5 cortex layer — extracted routing patterns per basin, model-version
    checkpoints, per-provider failure modes. Written by `trinity-local
    consolidate`; read by `ask` at query time. See `docs/spec-v1.5.md`.
    """
    path = state_dir() / "cortex"
    path.mkdir(parents=True, exist_ok=True)
    return path


def dispatch_outcomes_path() -> Path:
    """JSONL log of `ask` dispatch outcomes — one line per call. Tracks the
    rate-limit-saves metric named in docs/launch-package.md as the day-1
    case-study number. Each line: {ts, query_excerpt, primary, succeeded_on,
    retries, classified_kind}.
    """
    path = analytics_dir() / "dispatch_outcomes.jsonl"
    return path


def cortex_routing_patterns_path() -> Path:
    return cortex_dir() / "routing_patterns.json"


def cortex_model_checkpoints_path() -> Path:
    return cortex_dir() / "model_checkpoints.json"


def prompt_nodes_path() -> Path:
    return memory_dir() / "prompt_nodes.jsonl"


def turn_windows_path() -> Path:
    return memory_dir() / "turn_windows.jsonl"


def ingest_cursors_path() -> Path:
    return memory_dir() / "cursors.json"


def hard_examples_dir() -> Path:
    path = research_dir() / "hard_examples"
    path.mkdir(parents=True, exist_ok=True)
    return path


def replay_examples_dir() -> Path:
    path = research_dir() / "examples"
    path.mkdir(parents=True, exist_ok=True)
    return path
