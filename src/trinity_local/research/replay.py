"""Offline replay — re-process historical transcripts into training examples.

Walks the same transcript paths as the watcher but instead of creating tasks
and actions, it generates RoutingExample records with weak labels derived from
observed behavior (completion, switching, cost, error counts).

This module reads from provider transcript directories and writes to
~/.trinity/research/examples/.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

from ..config import trinity_home
from ..feature_extractors import extract_session_features
from ..ingest import (
    iter_claude_code_sessions,
    parse_codex_session,
    parse_cowork_session,
    parse_gemini_cli_session,
)
from ..state_paths import research_dir, replay_examples_dir
from ..task_kinds import guess_task_kind
from ..training_schema import (
    ModelDescriptor,
    RoutingExample,
    SessionFeatures,
    TaskLink,
    TranscriptWindow,
)
from ..utils import stable_id


def examples_dir() -> Path:
    """Backward-compat wrapper — delegates to state_paths.replay_examples_dir()."""
    return replay_examples_dir()


@dataclass
class ReplayStats:
    """Summary of a replay run."""
    sessions_scanned: int = 0
    examples_generated: int = 0
    skipped_low_signal: int = 0
    skipped_no_prompt: int = 0
    errors: int = 0


def _weak_label(features: SessionFeatures) -> str:
    """Derive a weak label from observed session behavior.

    Returns one of:
      - good_fit: completed with low errors
      - bad_fit: not completed or high errors
      - needs_council: ambiguous signal
    """
    outcome = features.outcome
    if outcome.completed:
        error_rate = (outcome.tool_errors_total or 0) / max(outcome.tool_calls_total or 1, 1)
        if error_rate < 0.15:
            return "good_fit"
        if error_rate > 0.4:
            return "bad_fit"
        return "needs_council"
    # Not completed
    if (outcome.tool_errors_total or 0) > 3:
        return "bad_fit"
    if (outcome.assistant_turns or 0) < 2:
        return "bad_fit"
    return "needs_council"


def _guess_task_kind(text: str) -> str:
    """Compatibility wrapper around the shared task kind classifier."""
    return guess_task_kind(text)


def _features_to_example(features: SessionFeatures) -> RoutingExample | None:
    """Convert a SessionFeatures into a RoutingExample with weak labels."""
    prompt = (features.first_user_text or "").strip()
    if not prompt:
        return None
    if features.extra.get("is_low_signal_prompt") or features.extra.get("is_automated"):
        return None

    task_kind = _guess_task_kind(prompt)
    label = _weak_label(features)

    window = TranscriptWindow(
        session_id=features.session_id,
        provider=features.provider,
        source_path=features.raw.source_path,
        started_at=features.started_at,
        ended_at=features.ended_at,
        cwd=features.cwd,
        project_hint=features.project_hint,
        first_user_text=prompt[:2000],
        planner_text=(features.planner_text or "")[:1000] or None,
        final_text=(features.final_text or "")[:1000] or None,
        task_kind_hint=task_kind,
        model=features.model,
        tools=features.tools,
        outcome=features.outcome,
    )

    example_id = stable_id("ex", features.session_id, features.provider)

    return RoutingExample(
        example_id=example_id,
        transcript=window,
        chosen_provider=features.provider,
        chosen_model=features.model,
        label=label,
        confidence=None,
        alternatives=[],
        reasons=[],
    )


def _iter_source_sessions(source: str) -> Iterator[tuple[str, object]]:
    """Yield (source, parsed_session) for all sessions of a source."""
    home = Path.home()
    if source == "claude":
        root = home / ".claude" / "projects"
        if root.exists():
            for session in iter_claude_code_sessions(root):
                yield source, session
    elif source == "codex":
        root = home / ".codex" / "sessions"
        if root.exists():
            for path in sorted(root.rglob("rollout-*.jsonl")):
                session = parse_codex_session(path)
                if session:
                    yield source, session
    elif source == "gemini":
        root = home / ".gemini" / "tmp"
        if root.exists():
            for path in sorted(root.rglob("session-*.json")):
                session = parse_gemini_cli_session(path)
                if session:
                    yield source, session
    elif source == "cowork":
        root = home / "Library" / "Application Support" / "Claude" / "local-agent-mode-sessions"
        if root.exists():
            for path in sorted(root.rglob("local_*.json")):
                session = parse_cowork_session(path)
                if session:
                    yield source, session


def replay_source(source: str, *, limit: int | None = None) -> ReplayStats:
    """Replay one source and generate RoutingExamples.

    Returns stats about the replay run. Examples are written to
    ~/.trinity/research/examples/<example_id>.json
    """
    stats = ReplayStats()
    out_dir = examples_dir()

    for _, session in _iter_source_sessions(source):
        if limit and stats.examples_generated >= limit:
            break
        stats.sessions_scanned += 1
        try:
            features = extract_session_features(session)
        except Exception:
            stats.errors += 1
            continue

        if features.extra.get("is_low_signal_prompt") or features.extra.get("is_automated"):
            stats.skipped_low_signal += 1
            continue

        prompt = (features.first_user_text or "").strip()
        if not prompt:
            stats.skipped_no_prompt += 1
            continue

        example = _features_to_example(features)
        if example is None:
            stats.skipped_no_prompt += 1
            continue

        path = out_dir / f"{example.example_id}.json"
        path.write_text(json.dumps(example.to_dict(), indent=2), encoding="utf-8")
        stats.examples_generated += 1

    return stats


def replay_all(*, sources: list[str] | None = None, limit: int | None = None) -> dict[str, ReplayStats]:
    """Replay all sources and return per-source stats."""
    sources = sources or ["claude", "codex", "gemini", "cowork"]
    results: dict[str, ReplayStats] = {}
    for source in sources:
        results[source] = replay_source(source, limit=limit)
    return results


def load_examples() -> list[RoutingExample]:
    """Load all generated examples from disk."""
    examples: list[RoutingExample] = []
    out_dir = examples_dir()
    if not out_dir.exists():
        return examples
    for path in sorted(out_dir.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            # Light reconstruction — we only need the fields for ranking
            examples.append(RoutingExample(
                example_id=raw["example_id"],
                transcript=TranscriptWindow(
                    session_id=raw["transcript"]["session_id"],
                    provider=raw["transcript"]["provider"],
                    source_path=raw["transcript"]["source_path"],
                    started_at=raw["transcript"].get("started_at"),
                    ended_at=raw["transcript"].get("ended_at"),
                    cwd=raw["transcript"].get("cwd"),
                    project_hint=raw["transcript"].get("project_hint"),
                    first_user_text=raw["transcript"].get("first_user_text"),
                    planner_text=raw["transcript"].get("planner_text"),
                    final_text=raw["transcript"].get("final_text"),
                    task_kind_hint=raw["transcript"].get("task_kind_hint"),
                    model=ModelDescriptor(**raw["transcript"].get("model", {"provider": ""})),
                ),
                chosen_provider=raw["chosen_provider"],
                chosen_model=ModelDescriptor(**raw.get("chosen_model", {"provider": ""})),
                label=raw["label"],
                confidence=raw.get("confidence"),
                alternatives=raw.get("alternatives", []),
                reasons=raw.get("reasons", []),
            ))
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
    return examples
