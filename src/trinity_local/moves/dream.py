"""Phase 6 of `trinity-local dream` — moves substrate update.

Three sub-phases:

  6a. T4 posterior update — read council_outcomes/ produced since the
      last dream run; for each (active move, completed council) pair
      whose basins match, apply the Beta-Binomial update primitive.
      Writes updated alpha/beta back to disk.

  6b. Promotion pass — discover candidate moves from the rejection
      corpus, run each through the full T1 → T2 → T3 gate, persist
      survivors to ~/.trinity/moves/<slug>/. Failed candidates land
      in dream_rejections.jsonl with which tier rejected them.

  6c. Demotion pass — re-evaluate T4 on every active move. Moves
      whose posterior dropped below baseline get archived (move file
      relocates to moves/archive/ with trinity_demoted_at + reason
      populated).

The orchestrator returns a report dict the dream CLI prints. Caller
(commands/dream.py) wires this in as Phase 6.

State: `~/.trinity/moves/_dream_state.json` carries `last_run_at` so
the T4 update only processes councils that landed after the previous
dream cycle.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .gate import (
    T4_posterior,
    run_gate,
    update_posterior_from_council,
)
from .schemas import Move
from . import store


# ─── State cursor (last dream run) ──────────────────────────────────


def _dream_state_path() -> Path:
    """Where the moves dream cursor lives. One JSON file with
    `{last_run_at: <iso>}`."""
    from .. import state_paths as _sp
    return _sp.moves_dir() / "_dream_state.json"


def _load_dream_state() -> dict[str, Any]:
    path = _dream_state_path()
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _save_dream_state(state: dict[str, Any]) -> None:
    path = _dream_state_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ─── Phase 6a: T4 update from completed councils ────────────────────


def _iter_council_outcomes_since(since_iso: str | None) -> list[dict[str, Any]]:
    """Read ~/.trinity/council_outcomes/*.json produced since the last
    dream run. Returns parsed JSON dicts. Tolerant of malformed files
    (skipped with a logged warning per file). Sort order: oldest first
    so alpha/beta updates apply in chronological order — gives a more
    accurate posterior than a randomly-ordered batch.
    """
    from .. import state_paths as _sp
    outcomes_dir = _sp.council_outcomes_dir() if hasattr(_sp, "council_outcomes_dir") else (_sp.trinity_home() / "council_outcomes")
    if not outcomes_dir.exists():
        return []
    out: list[dict[str, Any]] = []
    since_dt: datetime | None = None
    if since_iso:
        try:
            since_dt = datetime.fromisoformat(since_iso.replace("Z", "+00:00"))
        except ValueError:
            since_dt = None
    for path in sorted(outcomes_dir.glob("council_*.json"), key=lambda p: p.stat().st_mtime):
        if since_dt is not None:
            mtime = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
            if mtime <= since_dt:
                continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        out.append(data)
    return out


def _extract_winning_response_text(outcome: dict[str, Any]) -> str:
    """Pull the chairman's chosen response text from a council outcome.

    Returns empty string when the outcome doesn't carry a clear winner.
    The Bayesian update treats empty text as "no signal" (Jaccard
    against empty = 0 → beta increment), which is correct: a council
    with no clear winner shouldn't increment alpha for any move.
    """
    routing = outcome.get("routing_label") or {}
    winner = (routing.get("winner") or "").strip().lower()
    if not winner:
        return ""
    # member_results is a list of {provider, output_text, ...}; find the
    # one whose provider matches the winner
    for member in outcome.get("member_results") or []:
        if str(member.get("provider", "")).lower() == winner:
            return str(member.get("output_text") or "")
    return ""


def _extract_basin_id(outcome: dict[str, Any]) -> str | None:
    """Resolve the task's basin id for an outcome.

    Strategy: prefer the chairman's task_type → basin map if available;
    fall back to the outcome's basin_id field if present; finally None
    (the move's basin filter will skip moves whose basin doesn't match).
    """
    routing = outcome.get("routing_label") or {}
    # Some outcomes carry basin_id directly; others encode it as task_type
    basin = (
        outcome.get("basin_id")
        or routing.get("basin_id")
        or routing.get("task_basin")
    )
    return str(basin) if basin else None


def update_t4_from_recent_councils(*, since_iso: str | None = None) -> dict[str, Any]:
    """Apply Beta-Binomial updates to all active moves based on council
    outcomes since `since_iso` (or all-time when None — cold install).

    Returns a report dict: `{councils_processed, moves_updated,
    alpha_increments, beta_increments, skipped_no_winner,
    skipped_no_basin}`.

    Implementation note: the loop is O(active_moves × councils). For
    the corpus sizes Trinity targets (≤ ~50 active moves × ≤ 100
    councils/dream cycle) this is ~5000 Jaccard ops, all stdlib +
    sub-second.
    """
    active_moves = store.list_moves(archived=False)
    outcomes = _iter_council_outcomes_since(since_iso)
    report = {
        "councils_processed": 0,
        "moves_updated": 0,
        "alpha_increments": 0,
        "beta_increments": 0,
        "skipped_no_winner": 0,
        "skipped_no_basin": 0,
    }
    if not active_moves or not outcomes:
        return report
    # Track which moves got at least one update so we know which to persist
    touched: set[str] = set()
    for outcome in outcomes:
        report["councils_processed"] += 1
        winner_text = _extract_winning_response_text(outcome)
        if not winner_text:
            report["skipped_no_winner"] += 1
            continue
        basin_id = _extract_basin_id(outcome)
        if not basin_id:
            report["skipped_no_basin"] += 1
            continue
        for move in active_moves:
            _, action = update_posterior_from_council(
                move,
                winning_response_text=winner_text,
                council_basin_id=basin_id,
            )
            if action == "alpha_incremented":
                report["alpha_increments"] += 1
                touched.add(move.name)
            elif action == "beta_incremented":
                report["beta_increments"] += 1
                touched.add(move.name)
    # Persist touched moves
    for move in active_moves:
        if move.name in touched:
            store.write_move(move)
    report["moves_updated"] = len(touched)
    return report


# ─── Phase 6b: Discovery + promotion ────────────────────────────────


@dataclass
class _CandidateGroup:
    """A cluster of rejections that share basin + type → suggests a
    recurring pattern → propose a candidate move."""
    basin_id: str
    rejection_type: str
    members: list[dict[str, Any]]


def discover_candidates(
    rejection_corpus: list[dict[str, Any]],
    *,
    min_group_size: int = 3,
) -> list[Move]:
    """Group rejections by (basin, type); for each group with ≥
    `min_group_size` members, propose a candidate move.

    Discovery heuristic (V1 — intentionally simple):
      - Move's description: derived from the rejection type + the
        first user_substitute exemplar
      - Move's body: concatenation of distinct user_substitute texts
        from the group (caps at 5 to keep the move readable)
      - trinity_promoted_from: the rejection IDs in the group
      - trinity_basin_id: the group's basin

    This is the candidate-generation surface. Future iterations can
    swap in a chairman call that synthesizes a richer move body from
    the rejection patterns; the gate evaluates the candidate either
    way. Today's heuristic is good enough to generate signal-bearing
    candidates the gate can validate.

    Returns candidates in deterministic order (sorted by basin id,
    then by rejection type) so the same input rejection corpus always
    produces the same candidate sequence.
    """
    if not rejection_corpus:
        return []
    # Group by (basin, type)
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in rejection_corpus:
        basin = str(r.get("basin") or "").strip()
        rtype = str(r.get("type") or "").strip()
        if not basin or not rtype:
            continue
        groups.setdefault((basin, rtype), []).append(r)

    candidates: list[Move] = []
    for (basin, rtype), members in sorted(groups.items()):
        if len(members) < min_group_size:
            continue
        # First user_substitute as the description seed
        first_sub = next(
            (str(m.get("user_substitute") or "").strip() for m in members if m.get("user_substitute")),
            "",
        )
        if not first_sub:
            continue
        # Dedupe user_substitute texts; cap at 5 for body readability
        seen: set[str] = set()
        body_examples: list[str] = []
        for m in members:
            sub = str(m.get("user_substitute") or "").strip()
            if sub and sub not in seen:
                seen.add(sub)
                body_examples.append(sub)
            if len(body_examples) >= 5:
                break
        slug_base = rtype.lower().replace("_", "-")
        name = f"{slug_base}-pattern-{basin}"
        description = (
            f"When the model produces a response that triggers a "
            f"{rtype} rejection in basin {basin}, prefer the user's "
            f"observed substitute shape. Example: {first_sub[:200]}"
        )
        body = (
            f"This move was discovered from {len(members)} {rtype} "
            f"rejections in basin {basin}. The user's accepted "
            f"substitutes share this shape:\n\n"
            + "\n\n---\n\n".join(f"> {s[:500]}" for s in body_examples)
        )
        candidate = Move(
            name=name,
            description=description,
            body=body,
            trinity_basin_id=basin,
            trinity_promoted_from=[str(m.get("id") or "") for m in members if m.get("id")],
        )
        candidates.append(candidate)
    return candidates


def _log_dream_rejection(
    candidate: Move,
    tier_results: list[Any],
    *,
    why: str,
) -> None:
    """Append a rejected candidate to dream_rejections.jsonl. The
    log lets users inspect "what did dream propose that the gate
    declined, and which tier rejected it?" — debugging surface for
    the gate's behavior."""
    from .. import state_paths as _sp
    path = _sp.trinity_home() / "dream_rejections.jsonl"
    record = {
        "candidate_name": candidate.name,
        "candidate_basin": candidate.trinity_basin_id,
        "rejected_at": _now_iso(),
        "why_rejected": why,
        "promoted_from": list(candidate.trinity_promoted_from or []),
        "tier_results": [
            {
                "tier": r.tier,
                "passed": r.passed,
                "score": r.score,
                "threshold": r.threshold,
                "reason": r.reason,
            }
            for r in tier_results
        ],
    }
    try:
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, separators=(",", ":")) + "\n")
    except OSError:
        # Logging failure shouldn't crash the dream pass
        pass


def run_promotion_pass(
    candidates: list[Move],
    *,
    accepted_patterns_for_basin: dict[str, list[str]] | None = None,
    basin_centroids: dict[str, list[float]] | None = None,
    rejection_corpus: list[dict[str, Any]] | None = None,
    chairman_provider_config: Any | None = None,
    lens_text: str = "",
) -> dict[str, Any]:
    """Run each candidate through the full T1 → T2 → T3 gate. Survivors
    get persisted to ~/.trinity/moves/<slug>/. Failed candidates are
    logged to dream_rejections.jsonl with which tier rejected them.

    Returns: `{candidates_evaluated, promoted, rejected,
    rejected_by_tier: {T1, T2, T3}}`.

    Promotion side-effects:
      - trinity_promoted_at is set to now
      - trinity_eval_baseline is set to the T3 score (first promotion)
      - The Move is written to disk via store.write_move

    Tier inputs:
      - accepted_patterns_for_basin[basin]: list[str] of accepted-
        pattern texts (typically `user_substitute` from same-basin
        rejections — the things the user accepted that we're checking
        the candidate against)
      - basin_centroids[basin]: list[float] embedding from topics.json
      - rejection_corpus: full corpus passed to T3 (filtered per-move
        by basin inside T3)
    """
    accepted_patterns_for_basin = accepted_patterns_for_basin or {}
    basin_centroids = basin_centroids or {}
    rejection_corpus = rejection_corpus or []
    report = {
        "candidates_evaluated": len(candidates),
        "promoted": 0,
        "rejected": 0,
        "rejected_by_tier": {"T1": 0, "T2": 0, "T3": 0},
    }
    for candidate in candidates:
        basin = candidate.trinity_basin_id or ""
        patterns = accepted_patterns_for_basin.get(basin, [])
        centroid = basin_centroids.get(basin)
        tier_results = run_gate(
            candidate,
            accepted_patterns=patterns,
            basin_centroid=centroid,
            rejection_corpus=rejection_corpus,
            chairman_provider_config=chairman_provider_config,
            lens_text=lens_text,
            baseline=None,  # first promotion — T3 sets the baseline
        )
        # Pass iff every tier that ran passed
        all_passed = all(r.passed for r in tier_results)
        last_tier_run = tier_results[-1].tier if tier_results else None
        if not all_passed:
            failing_tier = next((r.tier for r in tier_results if not r.passed), "?")
            report["rejected"] += 1
            report["rejected_by_tier"][failing_tier] = (
                report["rejected_by_tier"].get(failing_tier, 0) + 1
            )
            _log_dream_rejection(
                candidate,
                tier_results,
                why=f"failed at {failing_tier}",
            )
            continue
        # All tiers passed → promote. Set promoted_at + baseline.
        candidate.trinity_promoted_at = _now_iso()
        # If T3 ran and set a baseline, capture it on the move
        if last_tier_run == "T3":
            t3 = tier_results[-1]
            candidate.trinity_t3_chairman_score = t3.score
            candidate.trinity_eval_baseline = t3.threshold
        store.write_move(candidate)
        report["promoted"] += 1
    return report


# ─── Phase 6c: Demotion pass ─────────────────────────────────────────


def run_demotion_pass() -> dict[str, Any]:
    """Re-evaluate T4 on every active move. Moves whose posterior
    fails T4 (vs their trinity_eval_baseline or the 0.5 fallback)
    get demoted to ~/.trinity/moves/archive/<slug>/ with their
    trinity_demoted_by_tier + trinity_demoted_at populated.

    Returns: `{active_moves_evaluated, demoted, by_tier: {T4: N}}`.

    Note: only T4 demotion ships in this pass. T1/T2/T3 re-eval can
    be added later; T4 is the cheap-to-check signal that triggers
    "this move is no longer earning its keep" in production.
    """
    active_moves = store.list_moves(archived=False)
    report = {
        "active_moves_evaluated": len(active_moves),
        "demoted": 0,
        "by_tier": {"T4": 0},
    }
    for move in active_moves:
        t4 = T4_posterior(move)
        if not t4.passed:
            store.archive_move(
                store._slugify(move.name),
                tier="T4",
                reason=t4.reason,
            )
            report["demoted"] += 1
            report["by_tier"]["T4"] += 1
    return report


# ─── Orchestrator ────────────────────────────────────────────────────


def phase_6_moves_pass(
    *,
    chairman_provider_config: Any | None = None,
    lens_text: str = "",
    rejection_corpus: list[dict[str, Any]] | None = None,
    basin_centroids: dict[str, list[float]] | None = None,
    skip_promotion: bool = False,
    skip_demotion: bool = False,
) -> dict[str, Any]:
    """Run the full moves pass for one dream cycle.

    Order matters:
      6a. T4 update from new councils → posterior values reflect
          latest data before the demotion pass uses them
      6b. Promotion pass — fresh candidates from latest rejection
          corpus → through the full gate
      6c. Demotion pass — re-eval T4 on active moves (now including
          any just-promoted in 6b)

    Returns a flat report dict the dream CLI can append into its
    overall report under `phases.moves`.
    """
    report: dict[str, Any] = {}
    state = _load_dream_state()
    last_run = state.get("last_run_at")

    # 6a: T4 update from recent councils
    report["t4_update"] = update_t4_from_recent_councils(since_iso=last_run)

    # 6b: Promotion pass
    if skip_promotion:
        report["promotion"] = {"skipped": True}
    else:
        rejection_corpus = rejection_corpus or _load_rejection_corpus()
        candidates = discover_candidates(rejection_corpus)
        # Build accepted_patterns_for_basin from the corpus itself —
        # user_substitute texts are the "accepted patterns" of each basin
        accepted_patterns_for_basin = _accepted_patterns_by_basin(rejection_corpus)
        # basin_centroids: caller provides (from topics.json); we don't
        # re-read topics.json here to keep this module independent of
        # the lens-build pipeline.
        report["promotion"] = run_promotion_pass(
            candidates,
            accepted_patterns_for_basin=accepted_patterns_for_basin,
            basin_centroids=basin_centroids or {},
            rejection_corpus=rejection_corpus,
            chairman_provider_config=chairman_provider_config,
            lens_text=lens_text,
        )

    # 6c: Demotion pass (after promotion so newly-promoted moves are
    # evaluated; they pass trivially under min_executions guard)
    if skip_demotion:
        report["demotion"] = {"skipped": True}
    else:
        report["demotion"] = run_demotion_pass()

    # Update cursor for next dream cycle
    state["last_run_at"] = _now_iso()
    _save_dream_state(state)
    return report


def _load_rejection_corpus() -> list[dict[str, Any]]:
    """Read ~/.trinity/me/rejections.jsonl. Returns [] if missing
    or malformed. Per-line JSON.
    """
    from .. import state_paths as _sp
    path = _sp.trinity_home() / "me" / "rejections.jsonl"
    if not path.exists():
        return []
    out: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        return []
    return out


def _accepted_patterns_by_basin(corpus: list[dict[str, Any]]) -> dict[str, list[str]]:
    """Group accepted patterns (user_substitute texts) by basin id.

    Returns a dict suitable for run_promotion_pass()'s
    accepted_patterns_for_basin arg: `{basin_id: [text, text, ...]}`.

    The accepted pattern IS the user's substitute — it's what they
    showed they accept (by typing it) in that basin. Candidates whose
    pattern doesn't lexically resemble these substitutes are filtered
    by T1.
    """
    out: dict[str, list[str]] = {}
    for r in corpus:
        basin = str(r.get("basin") or "").strip()
        sub = str(r.get("user_substitute") or "").strip()
        if basin and sub:
            out.setdefault(basin, []).append(sub)
    return out
