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
    # Minimum council sample size before declaring a "best" per task_type.
    # Live trigger 2026-05-25: 89% of the user's 246 task_types had their
    # winner declared from n=1 council ("X wins task_type Y based on a
    # single sample"). That's noise, not signal. The chairman_picker
    # already sigmoid-blends low-n personal data with global benchmarks
    # via _blended_pick (reads by_task_type directly, not
    # best_per_task_type), so suppressing low-n entries here is purely
    # a display correctness fix — doesn't affect routing decisions.
    MIN_BEST_SAMPLES = 3
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
        # Total councils for this task_type — sample-size gate for the
        # "best" claim. We sum wins (chairman picks) when present, else
        # fall back to summing council counts from provider_summary.
        total_n = sum(wins_here.values()) if wins_here else sum(
            int(s.get("n", 0)) for s in provider_summary.values()
        )
        if total_n < MIN_BEST_SAMPLES:
            continue  # don't claim a best — let the consumer (or
            # chairman_picker's sigmoid blend) handle low-n explicitly.
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
        # How many members actually produced a real answer (>= 200 chars).
        # A council where only one member responded substantively isn't a
        # real contest — its "winner" won by default, not on quality. The
        # value proof (#236) filters on this so the headline measures
        # answer quality, not dispatch reliability (a third of the captured
        # ledger predates the dispatch fixes and has empty/echoed members).
        substantive_members = sum(
            1 for m in (outcome.member_results or [])
            if len((getattr(m, "output_text", "") or "").strip()) >= _SUBSTANTIVE_MIN_CHARS
        )
        records.append({
            "council_run_id": council_id,
            "task_type": task_type,
            "routing_label": label_dict,
            "chairman_winner": chairman_winner,
            "winner_provider": outcome.winner_provider,
            "primary_provider": outcome.primary_provider,
            "substantive_members": substantive_members,
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


# A member output below this many chars is empty/echoed/a one-liner, not a
# real answer. Used to tell a genuine 3-way contest from a council where only
# one model responded (the rest of the captured ledger predates dispatch fixes).
_SUBSTANTIVE_MIN_CHARS = 200

# Below this many real contests the aggregate isn't worth a headline — the
# confidence-honesty rule (n<3 suppress) generalized to the proof surface.
_VALUE_PROOF_MIN_COUNCILS = 10

# A coarse category family needs at least this many real contests AND a
# win-margin this large before we'll name a leader — otherwise it's noise
# (the per-task-type grain is 400+ near-unique chairman labels; coarsening to
# the head token gives families like product_* → "product", strategic_* →
# "strategic" that carry real signal).
_WEDGE_MIN_CONTESTS = 8
_WEDGE_MIN_MARGIN = 3


def _is_real_contest(record: dict[str, Any]) -> bool:
    """A council is a real contest when >= 2 members gave a substantive
    answer. Records predating the substantive_members field default to True
    (assume real) so synthetic/legacy records aren't silently dropped."""
    return record.get("substantive_members", 2) >= 2


def council_value_proof() -> dict[str, Any]:
    """The council-first value proof, computed from the council_outcomes/
    ledger — no new eval, no model calls (#236).

    The painkiller, in one stat: a single-provider user gets their default
    model's answer every time. Trinity's chairman, having heard all three
    labs, picks a DIFFERENT model than the user's default a large fraction
    of the time — meaning that fraction of the time the default would have
    been the worse answer. We also surface the per-lab win split (provider
    names canonicalized at the load boundary so web-capture brand names —
    chatgpt/claude_ai/gemini — fold into codex/claude/antigravity).

    Restricted to REAL contests (>= 2 members gave a substantive answer) so
    the number measures answer quality, not dispatch reliability — a third of
    the captured ledger predates the dispatch fixes and has empty/echoed
    members whose "winner" won by default. (Empirically the filter doesn't
    move the headline — 56% before and after — but it makes the claim
    defensible.)

    Returns `{"ready": False, ...}` below the headline threshold so callers
    can stay quiet on a thin ledger rather than tout a noisy number.
    """
    from .council_schema import normalize_provider_slug

    all_records, _ = _scan_outcomes()
    total = len(all_records)
    records = [r for r in all_records if _is_real_contest(r)]
    n = len(records)
    if n < _VALUE_PROOF_MIN_COUNCILS:
        return {"ready": False, "n": n, "total": total,
                "min_councils": _VALUE_PROOF_MIN_COUNCILS}

    win_counts: dict[str, int] = {}
    changed = 0
    comparable = 0  # real contests where both winner and default are known
    for r in records:
        winner = normalize_provider_slug(r.get("chairman_winner") or r.get("winner_provider") or "")
        default = normalize_provider_slug(r.get("primary_provider") or "")
        if winner:
            win_counts[winner] = win_counts.get(winner, 0) + 1
        if winner and default:
            comparable += 1
            if winner != default:
                changed += 1

    changed_pct = round(100 * changed / comparable) if comparable else 0
    win_split = {
        p: {"count": c, "pct": round(100 * c / n)}
        for p, c in sorted(win_counts.items(), key=lambda kv: -kv[1])
    }
    return {
        "ready": True,
        "n": n,
        "total": total,
        "real_contests": n,
        "changed_pick": changed,
        "comparable": comparable,
        "changed_pct": changed_pct,
        "win_split": win_split,
    }


def council_category_wedge() -> list[dict[str, Any]]:
    """The asymmetric wedge, per category: which lab wins which KIND of
    question (#236). Different labs genuinely specialize — Claude wins
    deliberation (strategy/architecture/hardware), GPT wins generation
    (product/creative/vendor) — and a single-provider user can't see it.

    Coarsens the 400+ near-unique chairman task_type labels to their head
    token (product_recommendation/product_research → "product"), restricts to
    REAL contests, and names a leader only where the family clears both a
    volume floor and a win-margin floor (else noise). Sorted by volume.
    Empty list on a thin ledger.
    """
    import collections

    from .council_schema import normalize_provider_slug

    all_records, _ = _scan_outcomes()
    fam: dict[str, collections.Counter] = collections.defaultdict(collections.Counter)
    for r in all_records:
        if not _is_real_contest(r):
            continue
        winner = normalize_provider_slug(r.get("chairman_winner") or r.get("winner_provider") or "")
        # The chairman's task_type lives on the routing_label (551/551 populated);
        # the metadata-sourced record field is mostly empty.
        label = r.get("routing_label") or {}
        task_type = (label.get("task_type") or r.get("task_type") or "").lower()
        if not winner or not task_type:
            continue
        fam[task_type.split("_")[0]][winner] += 1

    wedge: list[dict[str, Any]] = []
    for family, counts in fam.items():
        n = sum(counts.values())
        if n < _WEDGE_MIN_CONTESTS:
            continue
        ranked = counts.most_common()
        leader, lead_n = ranked[0]
        runner_n = ranked[1][1] if len(ranked) > 1 else 0
        if lead_n - runner_n < _WEDGE_MIN_MARGIN:
            continue  # contested — don't crown a leader
        wedge.append({
            "family": family,
            "leader": leader,
            "n": n,
            "lead_count": lead_n,
            "margin": lead_n - runner_n,
        })
    wedge.sort(key=lambda w: -w["n"])
    return wedge


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
