"""End-to-end driver for the 3-stage lens-discovery pipeline.

Stage 1 → Stage 2 prompt (caller fires it via council member call)
Stage 3 prompt (caller fires it via 3-member council)
Stage 4 → save lenses.json + orderings.json + render to memories/lens.md.

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
    save_decisions,
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
    save_rejections,
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


def stage1_basins(*, k: int = 20, seed: int = 42) -> list[Basin]:
    """Cluster PromptNodes into basins. Pure numpy, no LLM."""
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
    `reason` fields so chairman drift is auditable across rebuilds.
    """
    raw_signals = parse_rejections(raw_output, basins)
    kept, rejected = validate_signals(raw_signals, pair_index)
    save_rejections(kept)
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
    decisions = parse_decisions(raw_output, basins)
    save_decisions(decisions)
    return decisions


def stage3_pair_mining_prompt(decisions: list[Decision]) -> str:
    return render_pair_mining_prompt(decisions)


def stage3_parse(raw_output: str) -> list[LensPair]:
    return parse_pair_mining_output(raw_output)


def stage4_post_filter(pairs: list[LensPair], decisions: list[Decision]) -> tuple[list[LensPair], list[LensPair]]:
    """Apply basin post-filter, then split by verdict."""
    filtered = basin_post_filter(pairs, decisions)
    accepted, orderings = split_by_verdict(filtered)
    save_lenses(accepted, orderings)
    return accepted, orderings


def render_me_markdown(
    accepted: list[LensPair],
    orderings: list[LensPair],
    rejections: list[RejectionSignal] | None = None,
) -> str:
    """Render lens artifacts as the lens-document markdown (written by
    the caller to ~/.trinity/memories/lens.md — function name retained
    for back-compat with the pre-task-#91 me.md path) so the chairman
    context loader picks them up. This replaces the old single-virtue-
    list shape with paired tensions.

    Rejections (Stage 0 turn-pair gaps) get a section too — they're
    behavioral evidence the chairman should see when scoring future
    council members against the user's actual choices.
    """
    lines: list[str] = ["# Lens", "", "## Lenses (paired tensions)", ""]
    if not accepted:
        lines.append("(No paired tensions found yet — run lens-build with more decisions.)")
    for i, p in enumerate(accepted, 1):
        lines.append(f"### {i}. {p.pole_a} ↔ {p.pole_b}")
        lines.append(f"- Pure-{p.pole_a} fails as: **{p.failure_a or 'unspecified'}**")
        lines.append(f"- Pure-{p.pole_b} fails as: **{p.failure_b or 'unspecified'}**")
        lines.append(f"- Tension evidence spans basins: {', '.join(p.basins_spanned) or '(none)'}")
        lines.append("")
    if orderings:
        lines.append("## Orderings (preferences without dual regret)")
        lines.append("")
        for p in orderings:
            lines.append(f"- {p.pole_a} > {p.pole_b}")
        lines.append("")
    if rejections:
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
    return "\n".join(lines)
