"""Compute the user's personal routing table on demand.

Two entry points:

  aggregate_routing_table(councils)
      Pure aggregation — given a list of {task_type, routing_label, user_winner}
      dicts, compute per-task-type means + winners. User verdicts are the
      ground truth signal: when present they dominate the chairman's per-
      provider `provider_scores` via a fixed weighting (see USER_VERDICT_WEIGHT).

  compute_personal_routing_table()
      Walk every rated council outcome on disk and aggregate. Called from
      the launchpad render and from chairman_picker. No file is written;
      the council_outcomes/ directory IS the source of truth, divergence
      becomes structurally impossible. Cached in-process by directory mtime.

The table shape:
    {
      "computed_at": iso,
      "councils_aggregated": int,
      "by_task_type": {
          "<task_type>": {
              "<provider>": {"overall": float, "n": int},
              ...
          },
          ...
      },
      "best_per_task_type": {"<task_type>": "<provider>", ...}
    }
"""
from __future__ import annotations

import statistics
from typing import Any, Iterable

from .council_runtime import load_council_outcome
from .state_paths import council_outcomes_dir
from .utils import now_iso


# User verdicts ARE the ground truth — they're what `record_outcome` was
# called "the most important tool" for in claude.md. When a council has a
# user_winner, we blend its contribution as:
#
#   effective_overall = USER_VERDICT_WEIGHT * (10 if winner else 0)
#                     + (1 - USER_VERDICT_WEIGHT) * chairman_overall
#
# At weight 0.7: a user-picked codex with chairman_overall 6.0 contributes
# 7.0 + 1.8 = 8.8 (much stronger than the chairman's 6.0); a user-rejected
# claude with chairman_overall 8.0 contributes 0 + 2.4 = 2.4 (close to a
# vote against). When NO user_winner exists, weight collapses to chairman
# scores unchanged — backward compatible.
USER_VERDICT_WEIGHT = 0.7
USER_WINNER_SCORE = 10.0  # the "ceiling" overall chairman scores are scaled against


def _blend_with_verdict(chairman_overall: float, is_user_winner: bool | None) -> float:
    """Effective contribution for a single (council, provider) cell.

    `is_user_winner` is None when this council had no user verdict at all
    — chairman score passes through unchanged (backward compat).
    """
    if is_user_winner is None:
        return chairman_overall
    target = USER_WINNER_SCORE if is_user_winner else 0.0
    return USER_VERDICT_WEIGHT * target + (1.0 - USER_VERDICT_WEIGHT) * chairman_overall


def aggregate_routing_table(councils: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Group routing labels by task_type and compute per-provider mean overall.

    Each item should have:
        - routing_label: dict (with provider_scores + task_type)
        - task_type: str (fallback when label lacks task_type)
        - user_winner: str | None (the provider the user picked via
          record_outcome; weighted heavily — see USER_VERDICT_WEIGHT)
    """
    by_task: dict[str, dict[str, list[float]]] = {}
    materialised = list(councils)
    for c in materialised:
        label = c.get("routing_label") or {}
        task_type = label.get("task_type") or c.get("task_type") or "general"
        scores = label.get("provider_scores") or {}
        user_winner = c.get("user_winner") or None
        for provider, sub in scores.items():
            overall = sub.get("overall") if isinstance(sub, dict) else None
            if overall is None:
                continue
            is_winner: bool | None = None
            if user_winner is not None:
                is_winner = provider == user_winner
            effective = _blend_with_verdict(float(overall), is_winner)
            by_task.setdefault(task_type, {}).setdefault(provider, []).append(effective)

    by_task_type: dict[str, dict[str, dict[str, float]]] = {}
    best_per_task_type: dict[str, str] = {}
    for task_type, providers in by_task.items():
        provider_summary: dict[str, dict[str, float]] = {}
        best_provider: str | None = None
        best_mean = float("-inf")
        for provider, overalls in providers.items():
            mean_overall = statistics.fmean(overalls) if overalls else 0.0
            provider_summary[provider] = {
                "overall": round(mean_overall, 3),
                "n": len(overalls),
            }
            if mean_overall > best_mean:
                best_mean = mean_overall
                best_provider = provider
        by_task_type[task_type] = provider_summary
        if best_provider:
            best_per_task_type[task_type] = best_provider

    return {
        "computed_at": now_iso(),
        "councils_aggregated": len(materialised),
        "by_task_type": by_task_type,
        "best_per_task_type": best_per_task_type,
    }


def _scan_outcomes() -> tuple[list[dict[str, Any]], bool]:
    """Walk council_outcomes/, return (records, all_clean).

    `all_clean` is False when ANY outcome JSON failed to parse — partial
    scans are returned but the caller (compute_personal_routing_table)
    will not promote them to the in-process cache, so a later complete
    scan supersedes them. Without this, a transient half-written outcome
    file could permanently poison the cached aggregate.
    """
    outcomes_dir = council_outcomes_dir()
    records: list[dict[str, Any]] = []
    if not outcomes_dir.exists():
        return records, True
    all_clean = True
    for outcome_path in sorted(outcomes_dir.glob("*.json")):
        council_id = outcome_path.stem
        try:
            outcome = load_council_outcome(council_id)
        except Exception:
            all_clean = False
            continue
        label = outcome.routing_label
        if label is None:
            continue
        try:
            label_dict = label.to_dict()
        except Exception:
            try:
                label_dict = dict(vars(label))
            except Exception:
                all_clean = False
                continue
        task_type = (outcome.metadata or {}).get("task_type")
        # Pull the user's verdict if it was recorded. Lives under
        # outcome.metadata.user_verdict.user_winner — written by
        # record_outcome / commands/council_rate.
        user_verdict = (outcome.metadata or {}).get("user_verdict") or {}
        user_winner = user_verdict.get("user_winner") if isinstance(user_verdict, dict) else None
        records.append({
            "council_run_id": council_id,
            "task_type": task_type,
            "routing_label": label_dict,
            "user_winner": user_winner,
        })
    return records, all_clean


def _iter_rated_councils() -> Iterable[dict[str, Any]]:
    """Yield {task_type, routing_label} dicts for every council outcome on disk
    that carries a routing_label. Both rated (user verdict in
    council_feedback.jsonl) and unrated (replay-history) outcomes contribute,
    so the personal routing table reflects ALL evidence the user has
    accumulated. The chairman's `provider_scores` is a useful signal even
    without a user verdict — and replay-history is the cron-scheduled feed
    that fills the table; gating it behind manual rating starved the table.
    """
    records, _ = _scan_outcomes()
    yield from records


_CACHE: dict[str, Any] | None = None
_CACHE_KEY: tuple[float, int] | None = None


def _outcomes_signature() -> tuple:
    """Per-file (name, mtime_ns, size) tuple for cache invalidation.

    Naive `(latest_mtime, count)` collides when an existing outcome is edited
    in place with the same byte length and a same-second mtime — the cache
    keeps a stale aggregate. Per-file fingerprint catches in-place edits at
    nanosecond resolution and any size change.

    Sorted, hashed-via-tuple-equality. ~18 bytes/file × ~thousands of files =
    cheap; vastly cheaper than re-parsing every JSON when nothing changed.
    """
    outcomes_dir = council_outcomes_dir()
    if not outcomes_dir.exists():
        return ()
    rows: list[tuple[str, int, int]] = []
    for p in sorted(outcomes_dir.glob("*.json")):
        try:
            st = p.stat()
        except OSError:
            continue
        rows.append((p.name, st.st_mtime_ns, st.st_size))
    return tuple(rows)


def compute_personal_routing_table() -> dict[str, Any]:
    """Walk rated council outcomes and aggregate. Cached on outcomes-dir mtime.

    The launchpad and chairman_picker both call this; with the cache, the
    walk is paid once per process per outcomes-dir change. No state file —
    the council_outcomes/ directory is canonical, can't drift from itself.

    A scan that hit ANY unreadable outcome (partial write, corrupt JSON) is
    returned but NOT promoted to the cache — so the next call after the
    transient finishes gets a clean recompute, not a frozen partial result.
    """
    global _CACHE, _CACHE_KEY
    signature = _outcomes_signature()
    if _CACHE is not None and _CACHE_KEY == signature:
        return _CACHE
    records, all_clean = _scan_outcomes()
    table = aggregate_routing_table(iter(records))
    if all_clean:
        _CACHE = table
        _CACHE_KEY = signature
    return table


def invalidate_cache() -> None:
    """Force the next compute_personal_routing_table call to re-walk disk."""
    global _CACHE, _CACHE_KEY
    _CACHE = None
    _CACHE_KEY = None
