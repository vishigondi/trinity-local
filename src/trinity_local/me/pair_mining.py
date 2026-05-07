"""Stage 3 — pair mining via 3-member council + verifier contract.
Stage 4 — deterministic basin post-filter.

Three members propose pair candidates from `decisions.jsonl`. The
chairman applies the three tests as a JSON contract:
- TENSION: decisions in BOTH directions (A privileged sacrificing B,
  AND B privileged sacrificing A).
- DUAL EVIDENCE: regret/correction/cost on BOTH poles (any of the
  expanded valence values per council_c63fa273bdc2ed21).
- FAILURE-MODE LEGIBILITY: a named failure for pure-A and pure-B
  (paralysis / hedonism / theater / sterility / ...).

Verdict per pair: accepted | preserve_as_ordering | dropped.

Stage 4 applies a deterministic post-filter on top: any pair whose
tension evidence sits entirely in ONE basin gets demoted to
preserve_as_ordering. Council council_70eaf228d7753074 ratified this
as the load-bearing piece — without it, basin tags are dead code.

Output:
- `~/.trinity/me/lenses.json` — accepted pairs (4–8 expected)
- `~/.trinity/me/orderings.json` — preserve_as_ordering pairs
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .basins import me_dir
from .decisions import Decision


@dataclass
class LensPair:
    pole_a: str
    pole_b: str
    failure_a: str
    failure_b: str
    tension_decisions: list[str] = field(default_factory=list)
    dual_evidence: dict[str, list[str]] = field(default_factory=dict)
    basins_spanned: list[str] = field(default_factory=list)
    verdict: str = "accepted"

    def to_dict(self) -> dict[str, Any]:
        return {
            "pole_a": self.pole_a,
            "pole_b": self.pole_b,
            "failure_a": self.failure_a,
            "failure_b": self.failure_b,
            "tension_decisions": self.tension_decisions,
            "dual_evidence": self.dual_evidence,
            "basins_spanned": self.basins_spanned,
            "verdict": self.verdict,
        }


def lenses_path() -> Path:
    return me_dir() / "lenses.json"


def orderings_path() -> Path:
    return me_dir() / "orderings.json"


def render_pair_mining_prompt(decisions: list[Decision]) -> str:
    """Build the chairman + members prompt for Stage 3.

    Members propose candidate pairs; chairman applies the three tests
    and returns a JSON array of verdicts.
    """
    decision_lines = []
    for d in decisions[:120]:  # cap to keep prompt sane
        decision_lines.append(json.dumps({
            "id": d.id,
            "privileged": d.privileged,
            "sacrificed": d.sacrificed,
            "valence": d.valence,
            "basin": d.basin,
            "verbatim": d.verbatim,
        }))
    decisions_block = "\n".join(decision_lines)

    return f"""You are mining lens-pairs from a user's decisions.

A LENS is a tension between two value poles (A, B) where:
1. TENSION — decisions privilege A at B's cost AND vice versa (both directions).
2. DUAL EVIDENCE — regret/correction/cost shows up on BOTH poles
   (the user has stated downsides of over-indexing on each pole).
3. FAILURE-MODE LEGIBILITY — a named failure mode for pure-A AND pure-B
   (e.g., paralysis, hedonism, theater, sterility, performance, avoidance).

If only ONE direction has evidence, it's a virtue or an ordering, not a lens.
If failure-modes are unnameable on either pole, it's a virtue, not a lens.

CRITICAL: ABSTRACT THE POLES. Each pole must be a STRUCTURAL pattern that
recurs across multiple domains, not a literal phrase from one decision.

BAD pole names (too literal, single domain — REJECT these):
  ❌ "speed/momentum to close"           → too specific to a real-estate deal
  ❌ "lower buyer-agent fee"             → one transaction
  ❌ "frigate setup over usb mount"      → one home automation task
  ❌ "settle the prior determination"    → too narrow

GOOD pole names (structural, span 3+ domains):
  ✓ "infrastructure over interface"          (architecture, software, smart-home)
  ✓ "locked corpus over forward theory"      (genetics, geopolitics, tax, SEO)
  ✓ "temporal trajectory over present snapshot"  (materials, real-estate, tax)
  ✓ "full-stack control over component excellence" (manufacturing, kit business, travel)
  ✓ "generative grammar over selected instance"    (floor-plans, genetics, philosophy)
  ✓ "codified rule over aesthetic judgment"        (genetics, design, manifestos)

THE TEST: would two strangers reading this lens converge on the same answer
in a domain you've never discussed? If a pole only fits one topical area, it's
a preference, not a lens. Name the structural move that ties decisions across
DIFFERENT basins together.

Cross-basin requirement: your tension_decisions for any "accepted" pair must
draw from AT LEAST 2 distinct basin ids (b00..bNN in the decisions below).
Pairs whose evidence sits in one basin are topic preferences — emit them as
"preserve_as_ordering" instead of "accepted".

Propose 6–12 candidate pairs from the decisions below. For each pair, return
a verdict object — JSON array, one element per pair, schema below:

{{
  "pole_a": "<short noun phrase, the optimized-for axis>",
  "pole_b": "<short noun phrase, the traded-away axis>",
  "failure_a": "<one-word or short phrase named failure of pure-A>",
  "failure_b": "<one-word or short phrase named failure of pure-B>",
  "tension_decisions": ["<decision_id where A privileged>", "<decision_id where B privileged>", ...],
  "dual_evidence": {{
    "pole_a": ["<decision_id with regret/correction/cost on A>", ...],
    "pole_b": ["<decision_id with regret/correction/cost on B>", ...]
  }},
  "verdict": "accepted | preserve_as_ordering | dropped"
}}

VERDICT GUIDE:
- accepted: passes all three tests
- preserve_as_ordering: stable preference (A always over B) but no
  dual evidence — useful as a lookup, not a lens
- dropped: neither tension nor dual evidence; a virtue or noise

Output: ONE JSON array. NO commentary outside the array. NO markdown fences.

DECISIONS:

{decisions_block}
"""


def parse_pair_mining_output(raw: str) -> list[LensPair]:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    # Find the outermost JSON array
    start = text.find("[")
    end = text.rfind("]")
    if start < 0 or end < 0 or end <= start:
        return []
    try:
        items = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return []
    if not isinstance(items, list):
        return []

    pairs: list[LensPair] = []
    for obj in items:
        if not isinstance(obj, dict):
            continue
        pole_a = (obj.get("pole_a") or "").strip()
        pole_b = (obj.get("pole_b") or "").strip()
        if not pole_a or not pole_b or pole_a == pole_b:
            continue
        verdict = (obj.get("verdict") or "accepted").strip().lower()
        if verdict not in {"accepted", "preserve_as_ordering", "dropped"}:
            verdict = "accepted"
        tension = obj.get("tension_decisions") or []
        if not isinstance(tension, list):
            tension = []
        dual = obj.get("dual_evidence") or {}
        if not isinstance(dual, dict):
            dual = {}
        pairs.append(LensPair(
            pole_a=pole_a,
            pole_b=pole_b,
            failure_a=(obj.get("failure_a") or "").strip(),
            failure_b=(obj.get("failure_b") or "").strip(),
            tension_decisions=[str(t) for t in tension if isinstance(t, (str, int))],
            dual_evidence={
                "pole_a": [str(t) for t in (dual.get("pole_a") or []) if isinstance(t, (str, int))],
                "pole_b": [str(t) for t in (dual.get("pole_b") or []) if isinstance(t, (str, int))],
            },
            basins_spanned=[],  # filled by basin_post_filter
            verdict=verdict,
        ))
    return pairs


_MIN_BASINS_FOR_LENS = 3
"""Spec threshold: TASTE_WIKI_SCHEMA.md mandates ≥3 domains supporting
each lens. Trinity's basins are functionally equivalent to taste-terminal's
domains (k-means topological clusters over PromptNode embeddings). Anything
under 3 basins is a topic-bound preference — keep as ordering, not lens."""


def basin_post_filter(pairs: list[LensPair], decisions: list[Decision]) -> list[LensPair]:
    """Stage 4: drop tension evidence that doesn't span enough basins.

    Per spec (TASTE_WIKI_SCHEMA.md): "Minimum 3 domains supporting an
    entry." Tension that sits in <3 basins is a domain-local virtue or
    a stable preference, not a lens that two strangers would converge
    on across unrelated topics.

    Verdicts:
    - accepted: ≥3 basins
    - preserve_as_ordering: 1–2 basins (topic-local)
    - dropped: 0 basins (chairman emitted IDs that don't anchor)
    """
    decision_basin = {d.id: d.basin for d in decisions}
    filtered: list[LensPair] = []
    for pair in pairs:
        basins = {
            decision_basin.get(d_id)
            for d_id in pair.tension_decisions
            if decision_basin.get(d_id)
        }
        basins.discard(None)
        pair.basins_spanned = sorted(b for b in basins if b)
        if pair.verdict != "accepted":
            filtered.append(pair)
            continue
        if len(pair.basins_spanned) >= _MIN_BASINS_FOR_LENS:
            filtered.append(pair)
        elif len(pair.basins_spanned) >= 1:
            pair.verdict = "preserve_as_ordering"
            filtered.append(pair)
        else:
            pair.verdict = "dropped"
            filtered.append(pair)
    return filtered


def split_by_verdict(pairs: list[LensPair]) -> tuple[list[LensPair], list[LensPair]]:
    """Split pairs into (accepted, orderings). Dropped pairs filtered out."""
    accepted = [p for p in pairs if p.verdict == "accepted"]
    orderings = [p for p in pairs if p.verdict == "preserve_as_ordering"]
    return accepted, orderings


def save_lenses(accepted: list[LensPair], orderings: list[LensPair]) -> tuple[Path, Path]:
    lp = lenses_path()
    op = orderings_path()
    lp.write_text(json.dumps({"lenses": [p.to_dict() for p in accepted]}, indent=2))
    op.write_text(json.dumps({"orderings": [p.to_dict() for p in orderings]}, indent=2))
    return lp, op


def load_lenses() -> list[LensPair]:
    path = lenses_path()
    if not path.exists():
        return []
    return [LensPair(**p) for p in json.loads(path.read_text()).get("lenses", [])]


def load_orderings() -> list[LensPair]:
    path = orderings_path()
    if not path.exists():
        return []
    return [LensPair(**p) for p in json.loads(path.read_text()).get("orderings", [])]
