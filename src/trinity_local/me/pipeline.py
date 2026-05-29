"""End-to-end driver for the 5-stage lens-discovery pipeline (Stages 0–4).

Stage 0 — turn-pair gap extraction (caller fires it as ONE batch chairman call)
Stage 1 — basin topology (no LLM; numpy k-means)
Stage 2 — decisions (caller fires it via council member call)
Stage 3 — pair mining (caller fires it via 3-member council)
Stage 4 — basin post-filter (deterministic; saves lenses.json + orderings.json
          + renders to memories/lens.md).

The driver is split so the caller (me_builder.build_me_via_council)
controls the LLM dispatches — keeping our "no LLM outside councils"
architectural commitment intact.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .basins import (
    Basin,
    basin_for_prompt,
    compute_basins,
    save_basins,
)
from .decisions import (
    Decision,
    parse_decisions,
    render_extraction_prompt,
)
from .pair_mining import (
    LensPair,
    basin_post_filter,
    parse_pair_mining_output,
    render_pair_mining_prompt,
    save_lenses,
    split_by_verdict,
)
from .turn_pairs import (
    RejectionSignal,
    iter_turn_pairs,
    parse_rejections,
    render_extraction_prompt as render_turn_pair_prompt,
    validate_signals,
)


@dataclass
class PipelineState:
    """Snapshot of intermediate artifacts for inspection / dry-run."""
    basins: list[Basin]
    decisions: list[Decision]
    pairs_raw: list[LensPair]
    pairs_filtered: list[LensPair]
    accepted: list[LensPair]
    orderings: list[LensPair]


def stage1_basins(*, k: int | None = None, seed: int = 42) -> list[Basin]:
    """Cluster PromptNodes into basins. Pure numpy, no LLM.

    k=None → corpus-size-aware basin count (compute_basins.auto_k), so the
    topic map doesn't junk-drawer as history grows (#245)."""
    basins = compute_basins(k=k, seed=seed)
    save_basins(basins)
    return basins


def stage0_turn_pair_prompt(
    pairs: list[dict[str, Any]],
    basins: list[Basin],
) -> str:
    """Render the Option A single-batch chairman prompt for turn-pair gaps."""
    return render_turn_pair_prompt(pairs, basins)


def stage0_parse_and_validate(
    raw_output: str,
    basins: list[Basin],
    pair_index: dict[str, dict[str, Any]],
) -> tuple[list[RejectionSignal], list[dict]]:
    """Parse chairman output, then run deterministic validators.

    Returns (kept_signals, rejected_records). The `rejected` list carries
    `reason` fields so chairman drift is auditable across rebuilds. Pure —
    no disk write; rejections flow in-memory into the unified ledger save
    (legacy rejections.jsonl retired in #209)."""
    raw_signals = parse_rejections(raw_output, basins)
    kept, rejected = validate_signals(raw_signals, pair_index)
    return kept, rejected


def collect_turn_pairs(limit: int = 200) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """Build turn pairs for the Stage 0 batch and an index keyed by prompt_id
    so the post-validators can look up assistant/user/next_user text."""
    pairs: list[dict[str, Any]] = []
    index: dict[str, dict[str, Any]] = {}
    for assistant, user, prompt_id, next_user in iter_turn_pairs(limit=limit):
        pairs.append({
            "prompt_id": prompt_id,
            "assistant_text": assistant,
            "user_text": user,
        })
        index[prompt_id] = {
            "assistant_text": assistant,
            "user_text": user,
            "next_user_text": next_user,
        }
    return pairs, index


def stage2_extraction_prompt(samples: list[dict[str, Any]], basins: list[Basin]) -> str:
    """Render the chairman prompt for decision extraction.

    `samples` items: {prompt_id, text}. Basin tag attached automatically
    via prompt_id lookup.
    """
    enriched = []
    for s in samples:
        prompt_id = s.get("prompt_id")
        enriched.append({
            "prompt_id": prompt_id,
            "text": s.get("text") or "",
            "basin": basin_for_prompt(basins, prompt_id) if prompt_id else None,
        })
    return render_extraction_prompt(enriched, basins)


def stage2_parse(raw_output: str, basins: list[Basin]) -> list[Decision]:
    # Pure parse — no disk write. Decisions flow in-memory into the unified
    # ledger save (legacy decisions.jsonl retired in #209).
    return parse_decisions(raw_output, basins)


def stage3_pair_mining_prompt(decisions: list[Decision]) -> str:
    return render_pair_mining_prompt(decisions)


def stage3_parse(raw_output: str) -> list[LensPair]:
    return parse_pair_mining_output(raw_output)


def _load_basin_centroids() -> dict[str, list[float]]:
    """Read basin centroids from ~/.trinity/memories/topics.json so
    Stage 4's T2 semantic filter can score each tension against each
    basin's geometric center. Returns {} if topics.json is missing or
    malformed — basin_post_filter degrades gracefully (count-only)."""
    import json
    from .. import state_paths as _sp
    path = _sp.memories_dir() / "topics.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: dict[str, list[float]] = {}
    for basin in data.get("basins", []):
        bid = basin.get("id")
        centroid = basin.get("centroid")
        if isinstance(bid, str) and isinstance(centroid, list):
            out[bid] = centroid
    return out


def stage4_post_filter(pairs: list[LensPair], decisions: list[Decision]) -> tuple[list[LensPair], list[LensPair]]:
    """Apply basin post-filter (count + semantic), then split by verdict."""
    basin_centroids = _load_basin_centroids()
    filtered = basin_post_filter(pairs, decisions, basin_centroids=basin_centroids)
    accepted, orderings = split_by_verdict(filtered)
    save_lenses(accepted, orderings)
    return accepted, orderings


def stage4b_surface_conflicts(
    accepted: list[LensPair],
    orderings: list[LensPair],
) -> list:
    """Detect structural contradictions between LensPairs (#141 slice 2).

    Stage 4b runs after Stage 4 splits accepted vs orderings. Looks for
    pairs whose poles are literally swapped (same axis, opposite
    privilege direction) — those are the contradictions today's lens
    silently averages over. Persists results to
    ``~/.trinity/me/conflicts.json``.

    The plan's #3 strategic-direction move: don't smooth contradictions,
    force the meta-judgment. The lens.md renderer + launchpad surfacing
    (slice 3) read from the persisted file so user sees what needs
    resolving.

    Returns the detected Conflict list (empty when the corpus has none
    or when accepted+orderings are empty).
    """
    from .conflicts import detect_conflicts, save_conflicts

    all_pairs = list(accepted) + list(orderings)
    if not all_pairs:
        # Nothing to compare — clear any stale conflicts file so the
        # launchpad doesn't show ghost detections from a prior corpus.
        save_conflicts([])
        return []

    conflicts = detect_conflicts(all_pairs)
    save_conflicts(conflicts)
    return conflicts


def render_me_markdown(
    accepted: list[LensPair],
    orderings: list[LensPair],
    rejections: list[RejectionSignal] | None = None,
    tension_support: dict[tuple[str, str], dict[str, Any]] | None = None,
    preference_acts: list | None = None,
    trajectories: list | None = None,
) -> str:
    """Render lens artifacts as the lens-document markdown (written by
    the caller to ~/.trinity/memories/lens.md — function name retained
    for back-compat with the pre-task-#91 me.md path) so the chairman
    context loader picks them up. This replaces the old single-virtue-
    list shape with paired tensions.

    `tension_support` (#198) carries the accumulation signal from the
    lens registry, keyed by (pole_a, pole_b): `support_count`,
    `first_seen`, `last_confirmed`. When present, each tension renders
    how much evidence backs it and how long it has persisted — the
    durability the chairman should weight by. Tensions backed by fewer
    than `LOW_CONFIDENCE_BELOW` decisions are flagged so a thin signal
    isn't stated as if it were settled. Absent (e.g. registry layer
    skipped), tensions render without the line — graceful degradation.

    Rejections (Stage 0 turn-pair gaps) get a section too — they're
    behavioral evidence the chairman should see when scoring future
    council members against the user's actual choices.
    """
    from .lens_registry import LOW_CONFIDENCE_BELOW

    support = tension_support or {}
    lines: list[str] = ["# Lens", "", "## Lenses (paired tensions)", ""]
    if not accepted:
        lines.append("(No paired tensions found yet — run lens-build with more decisions.)")
    for i, p in enumerate(accepted, 1):
        lines.append(f"### {i}. {p.pole_a} ↔ {p.pole_b}")
        lines.append(f"- Pure-{p.pole_a} fails as: **{p.failure_a or 'unspecified'}**")
        lines.append(f"- Pure-{p.pole_b} fails as: **{p.failure_b or 'unspecified'}**")
        lines.append(f"- Tension evidence spans basins: {', '.join(p.basins_spanned) or '(none)'}")
        sig = support.get((p.pole_a, p.pole_b))
        if sig:
            n = sig.get("support_count", 0)
            first = (sig.get("first_seen") or "")[:10]
            last = (sig.get("last_confirmed") or "")[:10]
            stability = f"stable since {first}" if first and first == last else (
                f"first seen {first}, last confirmed {last}" if first or last else ""
            )
            caveat = " _(low confidence — seen in few decisions)_" if n < LOW_CONFIDENCE_BELOW else ""
            support_line = f"- Supported by {n} decision{'s' if n != 1 else ''}"
            if stability:
                support_line += f" · {stability}"
            lines.append(support_line + caveat)
        lines.append("")
    if orderings:
        lines.append("## Orderings (preferences without dual regret)")
        lines.append("")
        for p in orderings:
            lines.append(f"- {p.pole_a} > {p.pole_b}")
        lines.append("")
    # Stage 4b (#141 slice 3): if conflicts.json exists, surface them
    # here. We read from disk rather than thread the conflicts list
    # through the call signature — Stage 4b persisted them just before
    # render_me_markdown runs, so disk IS the source of truth.
    try:
        from .conflicts import load_conflicts

        conflicts = load_conflicts()
    except Exception:
        conflicts = []
    if conflicts:
        lines.append("## ⚠ Tensions in tension")
        lines.append("")
        same_horizon = [c for c in conflicts if c.horizon_match]
        cross_horizon = [c for c in conflicts if not c.horizon_match]
        if same_horizon:
            lines.append(
                "_Same-horizon contradictions — your decisions privilege "
                "opposite poles of the same axis. Resolving requires a "
                "meta-judgment about which basin's evidence is more "
                "load-bearing._"
            )
            lines.append("")
            for c in same_horizon:
                lines.append(
                    f"- **{c.pole_a_axis} ↔ {c.pole_b_axis}** "
                    f"({c.horizon_a}): basins `{', '.join(c.basins_a) or '—'}` "
                    f"vs `{', '.join(c.basins_b) or '—'}`"
                )
            lines.append("")
        if cross_horizon:
            lines.append(
                "_Cross-horizon notes — multi-resolution preference (not "
                "contradiction). #139's lens-weighting handles these._"
            )
            lines.append("")
            for c in cross_horizon:
                lines.append(
                    f"- {c.pole_a_axis} ↔ {c.pole_b_axis} "
                    f"({c.horizon_a} vs {c.horizon_b})"
                )
            lines.append("")
    if preference_acts:
        # EXTRACT-unification Stage 1: render rejections AND decisions as
        # ONE evidence stream — every act of the user expressing taste,
        # discriminated by `trigger`. model_miss = corrections of the
        # model; self_expressed = trade-offs the user stated directly.
        # (When `preference_acts` is absent, the legacy rejections-only
        # section below still renders — back-compat for callers not yet
        # migrated.)
        from collections import defaultdict

        from .preference_acts import MODEL_MISS, SELF_EXPRESSED

        miss = [a for a in preference_acts if a.trigger == MODEL_MISS]
        self_exp = [a for a in preference_acts if a.trigger == SELF_EXPRESSED]
        lines.append("## Preference acts")
        lines.append("")
        lines.append(
            "Every act of you expressing taste — the model-miss corrections "
            "AND the trade-offs you stated directly. The user is the final "
            "authority; weight what the user privileged over what was offered."
        )
        lines.append("")
        if miss:
            groups: dict[str, list] = defaultdict(list)
            for a in miss:
                groups[a.kind].append(a)
            lines.append(f"### Model-miss — you corrected the model ({len(miss)})")
            for kind in ("REFRAME", "COMPRESSION", "REDIRECT", "SHARPENING"):
                items = groups.get(kind, [])
                if not items:
                    continue
                lines.append(f"#### {kind} ({len(items)})")
                for a in items[:5]:  # cap per kind so lens.md stays readable
                    lines.append(f"- model: \"{a.sacrificed[:100]}\"")
                    lines.append(f"  you: \"{a.privileged[:100]}\"")
                    if a.why:
                        lines.append(f"  why: {a.why[:140]}")
                if len(items) > 5:
                    lines.append(f"  _({len(items) - 5} more)_")
            lines.append("")
        if self_exp:
            lines.append(f"### Self-expressed — your stated trade-offs ({len(self_exp)})")
            for a in self_exp[:8]:
                row = f"- **{a.privileged}** > {a.sacrificed}"
                if a.kind:
                    row += f" _({a.kind})_"
                lines.append(row)
                if a.why:
                    lines.append(f"  would flip if: {a.why[:140]}")
            if len(self_exp) > 8:
                lines.append(f"  _({len(self_exp) - 8} more)_")
            lines.append("")
    elif rejections:
        # Group by type so the chairman sees the signal-type distribution.
        from collections import defaultdict
        groups: dict[str, list] = defaultdict(list)
        for sig in rejections:
            groups[sig.type].append(sig)
        lines.append("## Implicit rejections (turn-pair gaps)")
        lines.append("")
        lines.append(
            "Mined from (model_response, user_next_turn) pairs. The user is the "
            "final authority — chairman should weight what the user actually did "
            "next over what the model proposed."
        )
        lines.append("")
        for sig_type in ("REFRAME", "COMPRESSION", "REDIRECT", "SHARPENING"):
            items = groups.get(sig_type, [])
            if not items:
                continue
            lines.append(f"### {sig_type} ({len(items)})")
            for sig in items[:5]:  # cap per type so lens.md stays readable
                lines.append(f"- model: \"{sig.model_quote[:100]}\"")
                lines.append(f"  user: \"{sig.user_substitute[:100]}\"")
                if sig.why_signal:
                    lines.append(f"  why: {sig.why_signal[:140]}")
            if len(items) > 5:
                lines.append(f"  _({len(items) - 5} more)_")
            lines.append("")
    # Trajectory lens (#182): diachronic pulls aggregated across threads.
    # Rendered last so the chairman reads the synchronic acts first, then the
    # sustained arcs they compose into.
    if trajectories:
        from .arc_mining import render_trajectory_lines
        lines.extend(render_trajectory_lines(trajectories))
    return "\n".join(lines)
