"""Stage 2 — decision extraction (one chairman call).

Walk MMR-sampled chunks, ask the chairman to surface every
decision-shaped utterance with structured tags. Output is
`~/.trinity/me/decisions.jsonl` — one JSON line per decision.

Schema:
{
  "id": "d_001",
  "privileged": "<what got optimized for>",
  "sacrificed": "<what got traded away>",
  "valence": "satisfaction|regret|unresolved|correction|cost",
  "basin": "<basin id from stage 1>",
  "verbatim": "<≤25 word excerpt from user turn>",
  "prompt_id": "<originating PromptNode id>"
}

Why valence has 5 values, not 3: literal regret quotes are rare; real
lens evidence often shows up as a correction ("ok that's wrong, do X
instead") or a stated cost ("this approach gives up Y"). Council
council_c63fa273bdc2ed21 ratified expanding the enum so the three
tests don't reject real lenses for lacking explicit regret.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .basins import Basin, basin_for_prompt, me_dir


VALID_VALENCES = {"satisfaction", "regret", "unresolved", "correction", "cost"}


@dataclass
class Decision:
    id: str
    privileged: str
    sacrificed: str
    valence: str
    basin: str | None
    verbatim: str
    prompt_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "privileged": self.privileged,
            "sacrificed": self.sacrificed,
            "valence": self.valence,
            "basin": self.basin,
            "verbatim": self.verbatim,
            "prompt_id": self.prompt_id,
        }


def decisions_path() -> Path:
    return me_dir() / "decisions.jsonl"


def render_extraction_prompt(samples: list[dict], basins: list[Basin]) -> str:
    """Render the chairman prompt for stage 2.

    `samples` is a list of `{prompt_id, text, basin}` dicts (basin tag is
    a hint for the chairman to surface basin-id in its output, but the
    actual ground-truth basin is re-attached deterministically after
    parsing — chairman output is not trusted for the post-filter step).
    """
    basin_summary = "\n".join(
        f"  {b.id}: {', '.join(b.top_terms) or '(no distinctive terms)'} ({b.size} prompts)"
        for b in basins[:20]
    )
    chunks = []
    for i, s in enumerate(samples):
        prompt_id = s.get("prompt_id") or f"sample_{i}"
        basin = s.get("basin") or "?"
        text = (s.get("text") or "").strip().replace("\n", " ")
        if len(text) > 600:
            text = text[:600] + "…"
        chunks.append(f"[{prompt_id} · basin={basin}] {text}")
    chunk_block = "\n\n".join(chunks)

    return f"""You are extracting decision-shaped utterances from a user's prompt history.
A "decision" is any moment where the user CHOSE, DECLINED, REGRETTED,
RATIONALIZED, or COURSE-CORRECTED. Walk the chunks below and surface every
decision you find. Skip neutral or purely informational prompts.

CRITICAL: When labelling `privileged` and `sacrificed`, abstract one level
ABOVE the literal phrases in the verbatim. The downstream pair-miner needs
poles that recur across domains, not labels tied to one decision.

  Verbatim: "let's just pay 2% to the buyer agent and close fast"
  ❌ literal: privileged="lower buyer-agent fee", sacrificed="agent goodwill"
  ✓ abstract: privileged="momentum to close", sacrificed="relational reciprocity"

  Verbatim: "intelligence is infrastructure, not interface"
  ❌ literal: privileged="infrastructure", sacrificed="interface"
  ✓ abstract: privileged="capability hidden in structure", sacrificed="capability surfaced as features"

  Verbatim: "use the punnett square always, not the ratio"
  ❌ literal: privileged="punnett square", sacrificed="ratio"
  ✓ abstract: privileged="generative mechanism shown", sacrificed="derived shortcut"

If you can't abstract a decision (it's too domain-specific to generalize),
skip it rather than emit a literal label.

For each decision, emit ONE JSON line in this exact schema:

{{"id": "d_001", "privileged": "<what was optimized for>", "sacrificed": "<what was traded away>", "valence": "satisfaction|regret|unresolved|correction|cost", "basin": "<basin id from list below>", "verbatim": "<≤25 word excerpt from the chunk>", "prompt_id": "<the [id] from the chunk header>"}}

Valence guide:
- satisfaction: explicit endorsement of the trade
- regret: explicit regret over the trade
- unresolved: ambivalent or still-deliberating
- correction: course-correction ("no, do X instead")
- cost: stated trade-off cost ("this gives up Y")

Use correction or cost when the user shows lens evidence without literal
regret words — both count as valid evidence for pair mining.

Basins from the user's corpus (id : top terms · size):
{basin_summary}

Hard cap: emit at most 80 decisions. Prefer high-signal ones (clear pole,
explicit trade-off) over weak ones. Skip chunks with no decision shape.

Output format: ONE JSON object per line, NO commentary, NO markdown
fences, NO blank lines. Each line must parse as JSON.

CHUNKS:

{chunk_block}
"""


def parse_decisions(raw: str, basins: list[Basin]) -> list[Decision]:
    """Parse chairman output into Decision objects.

    Tolerates: trailing/leading text, partial markdown fences, malformed
    lines (skipped not crashed). Re-tags basin from prompt_id ground
    truth so a chairman that ignores basin tags can't poison the
    stage 4 post-filter.
    """
    decisions: list[Decision] = []
    next_auto_id = 1
    seen_ids: set[str] = set()

    text = raw.strip()
    # Strip markdown fences if the model wrapped output despite the prompt.
    if text.startswith("```"):
        text = re.sub(r"^```\w*\n?", "", text)
        text = re.sub(r"\n?```\s*$", "", text)
    for line in text.splitlines():
        line = line.strip()
        if not line or not line.startswith("{"):
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        privileged = (obj.get("privileged") or "").strip()
        sacrificed = (obj.get("sacrificed") or "").strip()
        verbatim = (obj.get("verbatim") or "").strip()
        if not privileged or not sacrificed or not verbatim:
            continue
        valence = (obj.get("valence") or "").strip().lower()
        if valence not in VALID_VALENCES:
            continue
        prompt_id = (obj.get("prompt_id") or "").strip() or None
        # Ground-truth re-tag: don't trust chairman's basin field — look up
        # by prompt_id against the topology. This is what makes basin
        # tags load-bearing despite chairman drift.
        basin_id = basin_for_prompt(basins, prompt_id) if prompt_id else None
        if basin_id is None:
            basin_id = (obj.get("basin") or "").strip() or None

        d_id = (obj.get("id") or "").strip()
        if not d_id or d_id in seen_ids:
            d_id = f"d_{next_auto_id:03d}"
            while d_id in seen_ids:
                next_auto_id += 1
                d_id = f"d_{next_auto_id:03d}"
        seen_ids.add(d_id)
        next_auto_id += 1

        decisions.append(Decision(
            id=d_id,
            privileged=privileged,
            sacrificed=sacrificed,
            valence=valence,
            basin=basin_id,
            verbatim=verbatim,
            prompt_id=prompt_id,
        ))
    return decisions


def save_decisions(decisions: list[Decision]) -> Path:
    path = decisions_path()
    with path.open("w") as f:
        for d in decisions:
            f.write(json.dumps(d.to_dict()) + "\n")
    return path


def load_decisions() -> list[Decision]:
    path = decisions_path()
    if not path.exists():
        return []
    decisions: list[Decision] = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
            decisions.append(Decision(**obj))
        except (json.JSONDecodeError, TypeError):
            continue
    return decisions
