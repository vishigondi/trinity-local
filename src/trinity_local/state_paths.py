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
    # Directory name kept as portal_pages/ for on-disk back-compat with existing
    # ~/.trinity/ installs; Python module names and function callers have moved
    # to "launchpad_*" but the served path string lives in user filesystems and
    # is regenerable anyway, so we don't migrate it.
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


# --- Paths migrated from individual modules (Phase 0) ---


def tasks_dir() -> Path:
    """Durable todo records — one JSON file per pending action (council
    launches, review-ready handoffs). Lives at `~/.trinity/todos/` to
    disambiguate from `task_type` (the classifier label, NOT a stored
    record). Pre-launch directory rename: if a legacy
    `~/.trinity/tasks/` exists from an earlier dev install, move it to
    `todos/` once."""
    path = state_dir() / "todos"
    legacy = state_dir() / "tasks"
    if not path.exists() and legacy.exists():
        try:
            legacy.rename(path)
        except OSError:
            pass
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
    """Raw prompt index — the INPUT to dream. Holds PromptNode / TurnWindow
    JSONL + cursors.

    Renamed `memory/` → `prompts/` to match the brand axis: prompts (raw,
    yours, the INPUT) vs memories (plural, what dream creates, the OUTPUT).
    The two differed by one letter, which was a confusion grenade.

    Back-compat function name kept so existing imports work; on disk the
    files live under ~/.trinity/prompts/. Migration is one-time + idempotent:
    if the legacy ~/.trinity/memory/ exists and the new ~/.trinity/prompts/
    does not, the whole directory is renamed.
    """
    path = state_dir() / "prompts"
    legacy = state_dir() / "memory"
    if not path.exists() and legacy.exists():
        try:
            legacy.rename(path)
        except OSError:
            # Cross-device or permission edge — leave legacy in place,
            # create the new path empty so writes go forward. The
            # raw_prompts_dir() consumer is structured-write-only, so a
            # split state still functions — readers cap from the new path.
            pass
    path.mkdir(parents=True, exist_ok=True)
    return path


def prompts_dir() -> Path:
    """Brand-aligned alias for memory_dir(). New code should call this;
    existing imports of memory_dir() keep working."""
    return memory_dir()


def memories_dir() -> Path:
    """The five durable memory types dream creates (lens, picks, routing,
    topics, vocabulary). See claude.md Glossary → "core memories".

    Migration: any pre-existing files at legacy paths
    (`~/.trinity/cortex/routing_patterns.json`, `~/.trinity/me.md`,
    `~/.trinity/me/basins.json`) are moved here on first access. The
    underlying file content schemas are unchanged — only the filenames
    align with the brand axis.
    """
    path = state_dir() / "memories"
    path.mkdir(parents=True, exist_ok=True)
    _migrate_legacy_memory_paths(path)
    return path


def _migrate_legacy_memory_paths(memories: Path) -> None:
    """One-time best-effort move of legacy memory files into ~/.trinity/memories/.

    Idempotent: if the new path already exists, the legacy file is left alone
    (the legacy file is the on-disk source of truth only until the new path
    is written; after migration the new path wins).
    """
    legacy_map = [
        (state_dir() / "cortex" / "routing_patterns.json", memories / "picks.json"),
        (state_dir() / "me.md", memories / "lens.md"),
        (state_dir() / "me" / "basins.json", memories / "topics.json"),
    ]
    for legacy, new in legacy_map:
        if new.exists() or not legacy.exists():
            continue
        try:
            legacy.rename(new)
        except OSError:
            # Cross-device move or transient permission issue — copy + leave
            # legacy in place so we never lose data.
            try:
                new.write_bytes(legacy.read_bytes())
            except OSError:
                pass


def picks_path() -> Path:
    """`picks.json` — your model picks per topic with reasoning.
    Procedural memory. Written by `consolidate`, read by `ask` + chairman."""
    return memories_dir() / "picks.json"


def lens_path() -> Path:
    """`lens.md` — paired tensions you'd reject vs accept.
    Value memory. Written by `lens-build` (formerly `me-build`)."""
    return memories_dir() / "lens.md"


def topics_path() -> Path:
    """`topics.json` — k-means clusters of subjects you ask about.
    Semantic memory. Written by lens-build Stage 1."""
    return memories_dir() / "topics.json"


def routing_path() -> Path:
    """`routing.json` — per-category provider track record (numbers).
    Empirical memory. Computed on demand from council_outcomes/, written
    on dream Phase 4 for the chairman context loader."""
    return memories_dir() / "routing.json"


def vocabulary_path() -> Path:
    """`vocabulary.md` — bimodality detection on YOUR terminology.
    Language memory. Written by dream Phase 2.5."""
    return memories_dir() / "vocabulary.md"


def core_path() -> Path:
    """`core.md` — singular paragraph distillation subsuming the five
    plural core memories. Identity. Read FIRST by the chairman on every
    council; falls through to specific memory files only on demand.
    Written by dream Phase 5."""
    return state_dir() / "core.md"


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
    """Back-compat alias: returns the new picks.json path. Existing callers
    that import this function keep working; new code should call picks_path()
    directly. The migration into ~/.trinity/memories/ runs automatically
    on first call to memories_dir()."""
    return picks_path()


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
