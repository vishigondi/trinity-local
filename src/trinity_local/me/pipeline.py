"""End-to-end driver for the 3-stage lens-discovery pipeline.

Stage 1 → Stage 2 prompt (caller fires it via council member call)
Stage 3 prompt (caller fires it via 3-member council)
Stage 4 → save lenses.json + orderings.json + render to me.md.

The driver is split so the caller (me_builder.build_me_via_council)
controls the LLM dispatches — keeping our "no LLM outside councils"
architectural commitment intact.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
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


def render_me_markdown(accepted: list[LensPair], orderings: list[LensPair]) -> str:
    """Render lens artifacts as me.md so the chairman context loader
    picks them up. This replaces the old single-virtue-list shape with
    paired tensions."""
    lines: list[str] = ["# /me", "", "## Lenses (paired tensions)", ""]
    if not accepted:
        lines.append("(No paired tensions found yet — run me-build with more decisions.)")
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
    return "\n".join(lines)
