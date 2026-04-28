from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator
import re

from .action_runtime import (
    create_council_start_action,
    create_recommendation_action,
    create_workflow_suggestion_action,
    find_action,
    notify_action,
    save_action,
)
from .cost_tracker import append_session_cost, compute_session_cost
from .council_runtime import create_prompt_bundle, save_prompt_bundle
from .drift import OutcomeRecord, append_outcome, check_drift
from .feature_extractors import extract_session_features
from .ingest import (
    parse_claude_code_session,
    parse_codex_session,
    parse_cowork_session,
    parse_gemini_cli_session,
)
from .portal_page import write_portal_html
from .ranker import RoutingContext, build_default_ranker
from .scoreboard import state_dir
from .task_runtime import (
    ensure_task_record,
    load_task_record,
    save_sync_record,
    save_task_record,
    tasks_dir,
)
from .task_schema import TaskRecommendation
from .workflow_prompts import write_cowork_shortcut_prompt


@dataclass
class WatchResult:
    scanned: int
    tasks_written: int
    actions_written: int
    portal_path: str | None = None


def _decision_to_recommendation(
    decision, provider: str
) -> tuple[TaskRecommendation, list[str], str]:
    """Convert RoutingDecision to TaskRecommendation + members + primary_provider.

    Maps the unified ranker output back to the format expected by the watcher.
    Primary provider is always the current provider (no autonomous provider switches).
    """
    mode = "council" if decision.needs_council else "recommendation"
    reason = f"{decision.recommended_provider or provider} recommended with {decision.confidence:.0%} confidence."
    if decision.metadata and decision.metadata.get("reason_suffix"):
        reason += " " + decision.metadata["reason_suffix"]

    return (
        TaskRecommendation(
            recommended_provider=decision.recommended_provider or provider,
            recommended_mode=mode,
            reason=reason,
            confidence=decision.confidence,
            evidence=decision.evidence,
        ),
        decision.top_k or [],
        provider,
    )


def watcher_dir() -> Path:
    path = state_dir() / "watcher"
    path.mkdir(parents=True, exist_ok=True)
    return path


def watcher_cursor_path(source: str) -> Path:
    return watcher_dir() / f"{source}_cursor.json"


def _load_cursor(source: str) -> float:
    path = watcher_cursor_path(source)
    if not path.exists():
        return datetime.now(timezone.utc).timestamp() - 900
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return 0.0
    return float(raw.get("last_mtime", 0.0) or 0.0)


def _save_cursor(source: str, mtime: float) -> None:
    watcher_cursor_path(source).write_text(
        json.dumps({"last_mtime": mtime}, indent=2),
        encoding="utf-8",
    )


def _normalize_providers_for_council(providers: list[str]) -> list[str]:
    """Normalize provider list for council: map cowork→claude, dedupe, preserve order."""
    result = []
    seen = set()
    for p in providers:
        normalized = "claude" if p == "cowork" else p
        if normalized not in seen:
            result.append(normalized)
            seen.add(normalized)
    return result


def _source_root(source: str) -> Path:
    home = Path.home()
    if source == "claude":
        return home / ".claude" / "projects"
    if source == "codex":
        return home / ".codex" / "sessions"
    if source == "gemini":
        return home / ".gemini" / "tmp"
    if source == "cowork":
        return home / "Library" / "Application Support" / "Claude" / "local-agent-mode-sessions"
    raise ValueError(f"Unknown source: {source}")


def _iter_recent_paths(source: str, since_mtime: float) -> Iterator[Path]:
    root = _source_root(source)
    if not root.exists():
        return
    if source == "claude":
        paths = root.rglob("*.jsonl")
    elif source == "codex":
        paths = root.rglob("rollout-*.jsonl")
    elif source == "gemini":
        paths = root.rglob("session-*.json")
    else:
        paths = root.rglob("local_*.json")
    recent = []
    for path in paths:
        try:
            mtime = path.stat().st_mtime
        except OSError:
            continue
        if mtime > since_mtime:
            recent.append((mtime, path))
    for _, path in sorted(recent):
        yield path


def _parse_source_path(source: str, path: Path):
    if source == "claude":
        return parse_claude_code_session(path)
    if source == "codex":
        return parse_codex_session(path)
    if source == "gemini":
        project_name = path.parent.parent.name if path.parent.name == "chats" else None
        return parse_gemini_cli_session(path, project_name=project_name)
    if source == "cowork":
        return parse_cowork_session(path)
    raise ValueError(f"Unknown source: {source}")


def _guess_task_kind(text: str, provider: str) -> str:
    lowered = text.lower()
    if any(term in lowered for term in ("stock", "research", "compare", "market", "investigate")):
        return "research"
    if any(term in lowered for term in ("debug", "bug", "error", "failing", "traceback")):
        return "debugging"
    if any(term in lowered for term in ("write", "draft", "email", "memo")):
        return "writing"
    if provider == "cowork":
        return "cowork_general"
    if any(term in lowered for term in ("code", "refactor", "repo", "function", "script")):
        return "coding"
    return "general"


def _normalize_prompt_key(text: str) -> str:
    lowered = text.lower()
    lowered = re.sub(r"[^a-z0-9\s]", " ", lowered)
    tokens = [token for token in lowered.split() if len(token) > 2]
    stop = {
        "this",
        "that",
        "with",
        "from",
        "have",
        "need",
        "again",
        "every",
        "open",
        "then",
        "into",
        "using",
        "should",
        "would",
        "could",
        "about",
    }
    filtered = [token for token in tokens if token not in stop]
    return " ".join(filtered[:12]).strip()


def _task_timestamp(task) -> datetime | None:
    stamp = task.updated_at or task.created_at
    if not stamp:
        return None
    try:
        return datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except ValueError:
        return None


def _similar_recent_task_count(*, prompt: str, provider: str, task_kind: str, exclude_task_id: str | None = None) -> int:
    prompt_key = _normalize_prompt_key(prompt)
    if not prompt_key:
        return 0
    cutoff = datetime.now(timezone.utc).timestamp() - (14 * 24 * 60 * 60)
    count = 0
    for path in tasks_dir().glob("*.json"):
        try:
            task = load_task_record(str(path))
        except Exception:
            continue
        if exclude_task_id and task.task_id == exclude_task_id:
            continue
        ts = _task_timestamp(task)
        if ts is None or ts.timestamp() < cutoff:
            continue
        other_text = (task.task_text or task.title or "").strip()
        other_key = _normalize_prompt_key(other_text)
        if not other_key:
            continue
        same_provider = (task.source_provider or provider) == provider
        same_kind = task_kind in task.tags if task.tags else False
        overlap = len(set(prompt_key.split()) & set(other_key.split()))
        if same_provider and same_kind and (other_key == prompt_key or overlap >= 4):
            count += 1
    return count


def _detect_provider_switch(
    features, prompt: str, task_kind: str
) -> tuple[str | None, str | None]:
    """Check if a similar prompt appeared in a different provider recently.

    Uses embedding cosine similarity (if MLX available) for robust matching,
    falling back to word-overlap heuristic otherwise.

    Returns (switched_from_provider, matching_task_id) or (None, None).
    """
    prompt_key = _normalize_prompt_key(prompt)
    if not prompt_key:
        return None, None

    # Check if embeddings are available for stronger matching
    try:
        from . import embeddings as emb
        use_embeddings = emb.is_available()
    except ImportError:
        use_embeddings = False

    cutoff = datetime.now(timezone.utc).timestamp() - 3600  # 60 min window
    for path in tasks_dir().glob("*.json"):
        try:
            task = load_task_record(str(path))
        except Exception:
            continue
        ts = _task_timestamp(task)
        if ts is None or ts.timestamp() < cutoff:
            continue
        other_provider = task.source_provider
        if not other_provider or other_provider == features.provider:
            continue
        other_text = (task.task_text or task.title or "").strip()
        if not other_text:
            continue

        # Embedding-based matching (preferred)
        if use_embeddings:
            sim = emb.similarity(prompt, other_text)
            if sim > 0.7:
                return other_provider, task.task_id
        else:
            # Word-overlap fallback
            other_key = _normalize_prompt_key(other_text)
            if not other_key:
                continue
            overlap = len(set(prompt_key.split()) & set(other_key.split()))
            if other_key == prompt_key or overlap >= 4:
                return other_provider, task.task_id
    return None, None


def _workflow_reason(features, prompt: str, task_kind: str, task_id: str | None = None) -> str | None:
    lowered = prompt.lower()
    if any(term in lowered for term in ("again", "every time", "repeatedly", "repeat", "shortcut", "automate", "workflow")):
        return "This task looks repetitive or explicitly automation-oriented. Trinity can prepare a Shortcut brief for Cowork."
    repeat_count = _similar_recent_task_count(
        prompt=prompt,
        provider=features.provider,
        task_kind=task_kind,
        exclude_task_id=task_id,
    )
    if repeat_count >= 2:
        return f"Trinity has seen this workflow pattern {repeat_count + 1} times recently. It may be worth turning it into a Shortcut or local automation."
    if repeat_count >= 1 and features.provider == "cowork" and task_kind in {"research", "cowork_general"} and features.did_use_web:
        return "This Cowork research pattern has repeated and may benefit from a Shortcut or lightweight automation."
    return None


def watch_once(*, sources: list[str], notify: bool = False) -> WatchResult:
    # --- Adapter validation at startup ---
    validated_sources: list[str] = []
    for source in sources:
        root = _source_root(source)
        if not root.exists():
            if notify:
                from .notifications import notify as _notify
                _notify(
                    title="Trinity Watcher",
                    message=f"Skipping {source}: transcript directory not found at {root}",
                )
            continue
        validated_sources.append(source)

    scanned = 0
    tasks_written = 0
    actions_written = 0
    for source in validated_sources:
        last_mtime = _load_cursor(source)
        max_mtime = last_mtime
        for path in _iter_recent_paths(source, last_mtime):
            scanned += 1
            try:
                max_mtime = max(max_mtime, path.stat().st_mtime)
            except OSError:
                pass
            session = _parse_source_path(source, path)
            if session is None:
                continue
            features = extract_session_features(session)
            if features.extra.get("is_automated") or features.extra.get("is_low_signal_prompt"):
                continue
            prompt = (features.first_user_text or "").strip()
            if not prompt:
                continue

            # --- Cost and outcome tracking (2.3, 2.5) ---
            task_kind_guess = _guess_task_kind(prompt, features.provider)
            cost = compute_session_cost(features, task_kind=task_kind_guess)
            append_session_cost(cost)
            outcome_rec = OutcomeRecord(
                provider=features.provider,
                model_id=features.model.normalized_model_id,
                task_kind=task_kind_guess,
                completed=bool(features.outcome.completed),
                error_count=features.outcome.tool_errors_total or 0,
                session_seconds=features.outcome.session_seconds,
                timestamp=features.started_at or features.ended_at or "",
            )
            append_outcome(outcome_rec)

            # --- Switching detection (3.1) ---
            switched_from, switch_task_id = _detect_provider_switch(
                features, prompt, task_kind_guess
            )
            force_council = False
            if switched_from:
                outcome_rec = OutcomeRecord(
                    provider=switched_from,
                    model_id=None,
                    task_kind=task_kind_guess,
                    completed=False,
                    error_count=0,
                    session_seconds=None,
                    timestamp=features.started_at or features.ended_at or "",
                )
                append_outcome(outcome_rec)
                # Auto-trigger council: the user switched providers, so a
                # cross-provider comparison is the most valuable action.
                force_council = True

                # Track "later switched" for the original task's advisory
                if switch_task_id:
                    try:
                        from .knn_analytics import mark_suggestion_outcome
                        from .task_runtime import load_task_record as _load_task
                        # Resolve task_id → session_id: the advisory log is
                        # keyed by session_id, not task_id.
                        _switch_task = _load_task(switch_task_id)
                        _switch_session_id = _switch_task.source_session_id or switch_task_id
                        # The original session switched away = suggestion was not
                        # good enough, user abandoned and moved providers
                        mark_suggestion_outcome(
                            _switch_session_id,
                            acted_on=False,
                            later_switched=True,
                            switch_target=features.provider,
                        )
                    except Exception:
                        pass  # Analytics must never break the watcher

            # Use unified ranker interface (heuristic + k-NN with fallback)
            task_kind = task_kind_guess
            routing_ctx = RoutingContext(
                task_text=prompt,
                task_kind=task_kind,
                current_provider=features.provider,
                session_id=session.session_id,
                task_id=None,
                cwd=features.cwd,
                source=source,
                switched_from_provider=switched_from,
                switched_from_task_id=switch_task_id,
                has_web=features.did_use_web,
                has_tools=features.did_use_tools,
                has_edits=features.did_make_edits,
                message_count=features.turn_count,
            )
            ranker = build_default_ranker()
            decision = ranker.advise(routing_ctx)
            if decision.recommended_provider is None:
                continue
            recommendation, members, primary_provider = _decision_to_recommendation(
                decision, features.provider
            )
            bundle = create_prompt_bundle(
                task_cluster_id=session.session_id[:16] if not features.project_hint else f"{features.project_hint}-{session.session_id[:8]}",
                task_text=prompt,
                context_excerpt=features.final_text or "",
                goal=f"Handle this {task_kind} task with the best provider.",
                comparison_instructions="Prefer the strongest answer for the user's current task.",
                origin_session_id=session.session_id,
                origin_provider=features.provider,
                metadata={"cwd": features.cwd or "", "source_path": session.source_path},
            )
            save_prompt_bundle(bundle)
            task = ensure_task_record(
                bundle=bundle,
                title=prompt.splitlines()[0][:120],
                status="suggested",
                recommendation=recommendation,
                tags=[task_kind],
                metadata={"cwd": features.cwd or ".", "source_path": session.source_path},
            )
            # --- Explicit switch linkage (Fix 3) ---
            if switched_from:
                task.switched_from_provider = switched_from
                if switch_task_id:
                    task.switched_from_task_id = switch_task_id
            save_task_record(task)
            save_sync_record(task)
            tasks_written += 1
            workflow_reason = _workflow_reason(features, prompt, task_kind, task.task_id)
            if workflow_reason and find_action(task_id=task.task_id, kind="workflow_suggestion") is None:
                workflow_prompt_path = write_cowork_shortcut_prompt(
                    task=task,
                    features=features,
                    workflow_reason=workflow_reason,
                )
                workflow_action = create_workflow_suggestion_action(
                    task=task,
                    prompt_path=str(workflow_prompt_path),
                    workflow_reason=workflow_reason,
                )
                save_action(workflow_action)
                actions_written += 1
                if notify:
                    notify_action(workflow_action)
            action = None
            if (force_council or recommendation.recommended_mode == "council") and members:
                if find_action(task_id=task.task_id, kind="start_council") is None:
                    action = create_council_start_action(
                        task=task,
                        bundle_id=bundle.bundle_id,
                        members=members,
                        primary_provider=primary_provider,
                        cwd=features.cwd or ".",
                    )
            else:
                if find_action(task_id=task.task_id, kind="recommendation") is None:
                    action = create_recommendation_action(
                        task=task,
                        bundle_id=bundle.bundle_id,
                    )
            if action is not None:
                save_action(action)
                actions_written += 1
                if notify:
                    notify_action(action)
        _save_cursor(source, max_mtime)

    # --- Drift check (runs once per watch_once pass) ---
    if notify:
        from .notifications import notify as _notify
        alerts = check_drift()
        for alert in alerts:
            _notify(title="Trinity Drift Alert", message=alert.message)

    portal_path = str(write_portal_html())
    return WatchResult(
        scanned=scanned,
        tasks_written=tasks_written,
        actions_written=actions_written,
        portal_path=portal_path,
    )


def watch_loop(*, sources: list[str], notify: bool = False, interval_seconds: int = 30) -> None:
    """Run watch_once in a loop with graceful shutdown on SIGINT/SIGTERM."""
    import signal
    import threading

    stop_event = threading.Event()

    def _handle_signal(signum, frame):
        stop_event.set()

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    while not stop_event.is_set():
        try:
            watch_once(sources=sources, notify=notify)
        except Exception as exc:
            _log_watch_error(exc, notify=notify)
        stop_event.wait(timeout=interval_seconds)


def _log_watch_error(exc: Exception, *, notify: bool = False) -> None:
    """Best-effort error logging for watch_loop pass failures."""
    import traceback

    error_record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "error": str(exc),
        "type": type(exc).__name__,
        "traceback": traceback.format_exc(),
    }

    try:
        from .config import trinity_home
        error_log = trinity_home() / "analytics" / "watch_errors.jsonl"
        error_log.parent.mkdir(parents=True, exist_ok=True)
        with error_log.open("a", encoding="utf-8") as f:
            f.write(json.dumps(error_record) + "\n")
    except Exception:
        pass  # If we can't even log, don't crash the loop

    if notify:
        try:
            from .notifications import notify as _notify
            _notify(
                title="Trinity Watcher Error",
                message=f"Watch pass failed: {type(exc).__name__}: {exc}",
            )
        except Exception:
            pass
