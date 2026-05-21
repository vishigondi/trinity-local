"""Compute the user's personal routing table on demand.

Two entry points:

  aggregate_routing_table(councils)
      Pure aggregation — given a list of {task_type, routing_label,
      chairman_winner} dicts, count chairman wins per provider per
      task_type. The chairman's pick IS the supervision signal (per
      the 2026-05-21 prime directive and commit bb817b6); user_winner
      verdicts are no longer blended in because the MCP record_outcome
      tool was retired alongside the rest of the rating UX.

  compute_personal_routing_table()
      Walk every council outcome on disk and aggregate. Called from
      the launchpad render and from chairman_picker. No file is written;
      the council_outcomes/ directory IS the source of truth, divergence
      becomes structurally impossible. Cached in-process by directory mtime.

The table shape:
    {
      "computed_at": iso,
      "councils_aggregated": int,
      "by_task_type": {
          "<task_type>": {
              "<provider>": {"overall": float, "n": int, "wins": int},
              ...
          },
          ...
      },
      "best_per_task_type": {"<task_type>": "<provider>", ...},
      "wins_per_task_type": {"<task_type>": {"<provider>": int, ...}, ...},
    }
"""
from __future__ import annotations

import statistics
from typing import Any, Iterable

from .council_runtime import load_council_outcome
from .state_paths import council_outcomes_dir
from .utils import now_iso


# Per the prime directive (2026-05-21): "Run any hard question through
# Claude, Codex, and Gemini in parallel. The chairman synthesizes through
# your taste lens and picks the answer YOU would have picked, not the
# generic one." The chairman's `winner` field IS the signal — counted as
# wins per provider per task_type. We do not blend with user verdicts:
# the user_winner UX was sunset 2026-05-21 ("asking the user to pick is
# one more task on them, they don't want to do"). Refinement prompts on
# each council are the supervision signal now.


def aggregate_routing_table(councils: Iterable[dict[str, Any]]) -> dict[str, Any]:
    """Group routing labels by task_type and count chairman wins per provider.

    Each item should have:
        - routing_label: dict (with provider_scores + task_type + winner)
        - task_type: str (fallback when label lacks task_type)
        - chairman_winner: str | None (the provider the chairman picked)
        - user_winner: ignored — sunset 2026-05-21

    Two derived stats per (task_type, provider):
        - wins: count of councils where chairman picked this provider
        - overall: mean of chairman.provider_scores[provider].overall
                   (kept for the per-cell numeric bars in the table)

    `best_per_task_type[task_type]` is the provider with the most chairman
    wins (ties broken by mean overall). This is "chairman picked codex
    4 of 5 times for code-refactor" — the prime directive made visible.
    """
    by_task_scores: dict[str, dict[str, list[float]]] = {}
    by_task_wins: dict[str, dict[str, int]] = {}
    materialised = list(councils)
    for c in materialised:
        label = c.get("routing_label") or {}
        task_type = label.get("task_type") or c.get("task_type") or "general"
        scores = label.get("provider_scores") or {}
        # Chairman's explicit pick — load-bearing for the prime directive.
        # Falls back to the routing_label.winner (canonical) then
        # outcome-level winner_provider supplied by the caller.
        chairman_winner = (
            label.get("winner")
            or c.get("chairman_winner")
            or c.get("winner_provider")
        )
        for provider, sub in scores.items():
            overall = sub.get("overall") if isinstance(sub, dict) else None
            if overall is None:
                continue
            by_task_scores.setdefault(task_type, {}).setdefault(provider, []).append(float(overall))
        if chairman_winner:
            by_task_wins.setdefault(task_type, {})[chairman_winner] = (
                by_task_wins.get(task_type, {}).get(chairman_winner, 0) + 1
            )

    by_task_type: dict[str, dict[str, dict[str, float]]] = {}
    best_per_task_type: dict[str, str] = {}
    wins_per_task_type: dict[str, dict[str, int]] = {}
    for task_type, providers in by_task_scores.items():
        provider_summary: dict[str, dict[str, float]] = {}
        wins_here = by_task_wins.get(task_type, {})
        for provider, overalls in providers.items():
            mean_overall = statistics.fmean(overalls) if overalls else 0.0
            provider_summary[provider] = {
                "overall": round(mean_overall, 3),
                "n": len(overalls),
                "wins": wins_here.get(provider, 0),
            }
        by_task_type[task_type] = provider_summary
        wins_per_task_type[task_type] = dict(wins_here)
        # Best = most chairman wins, tie-broken by mean overall.
        if wins_here:
            best_provider = max(
                wins_here.items(),
                key=lambda kv: (kv[1], provider_summary.get(kv[0], {}).get("overall", 0)),
            )[0]
            best_per_task_type[task_type] = best_provider
        else:
            # No chairman winner recorded for any council in this task
            # type — fall back to highest mean overall so the column
            # isn't empty for historical data missing the winner field.
            best_provider = max(
                provider_summary.items(),
                key=lambda kv: kv[1].get("overall", 0),
                default=(None, {}),
            )[0]
            if best_provider:
                best_per_task_type[task_type] = best_provider

    return {
        "computed_at": now_iso(),
        "councils_aggregated": len(materialised),
        "by_task_type": by_task_type,
        "best_per_task_type": best_per_task_type,
        # Per-task-type chairman wins; the launchpad table can render
        # "chairman picked codex 4/5" using this.
        "wins_per_task_type": wins_per_task_type,
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
        # The chairman's pick IS the supervision signal per the prime
        # directive (2026-05-21). user_winner was sunset alongside the
        # rest of the rating UX — refinement prompts on each council are
        # the post-pivot signal path.
        chairman_winner = (
            (label_dict or {}).get("winner")
            or outcome.winner_provider
        )
        records.append({
            "council_run_id": council_id,
            "task_type": task_type,
            "routing_label": label_dict,
            "chairman_winner": chairman_winner,
            "winner_provider": outcome.winner_provider,
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


def freeze_routing_to_disk() -> dict[str, Any]:
    """Write the current routing table to `~/.trinity/scoreboard/routing.json`.

    The table is otherwise lazy-computed on every call from
    `council_outcomes/`. Freezing lets the chairman context loader, Phase 5
    distill, and any external reader see the empirical-memory entry without
    re-walking the outcomes dir each time.

    Returns the table that was written (same shape as
    compute_personal_routing_table). Skips writing if the table is empty.
    """
    import json
    from .state_paths import routing_path

    table = compute_personal_routing_table()
    # `table` is always a dict with metadata keys (computed_at,
    # councils_aggregated) even when no councils have been rated. The real
    # "is there routing signal" check is whether the per-task-type bucket
    # has entries.
    if not table.get("by_task_type"):
        return table
    from .utils import atomic_write_text
    atomic_write_text(routing_path(), json.dumps(table, indent=2, sort_keys=True))
    return table
