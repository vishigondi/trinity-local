"""Unified preference-act evidence type — Stage 1 of the EXTRACT
unification (docs/lens-redesign.md beauty audit).

The lens pipeline extracts user taste through two passes that are really
one shape:

- **Stage 0 rejections** (`RejectionSignal`): the model offered X, the
  user substituted Y. REFRAME / REDIRECT / COMPRESSION / SHARPENING.
- **Stage 2 decisions** (`Decision`): the user privileged value A over
  value B, with a valence (satisfaction / regret / …).

A rejection *is* a decision — the user privileged their substitute over
the model's offering. Decisions ⊇ rejections; a rejection is the
model-miss-triggered subset. The beautiful form is **one evidence type
with a `trigger` discriminator**:

- `trigger="model_miss"`   ← rejections (model got it wrong, user fixed it)
- `trigger="self_expressed"` ← decisions (user stated a trade-off directly)

This module is the **read/type layer** of the unification (Strangler-Fig
step 1): it introduces `PreferenceAct` + adapters from the two existing
shapes + a unified reader over the two existing on-disk stores. The
writers (Stage 0 → rejections.jsonl, Stage 2 → decisions.jsonl), the
eval harness, and provider-import are all UNCHANGED at this stage — they
keep their current schemas. Later stages merge the extraction pass and
migrate storage. Doing it this way means each stage is independently
shippable and reversible, and the risky storage migration comes last,
after the type is proven on real data.
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Any

# Trigger discriminator values.
MODEL_MISS = "model_miss"
SELF_EXPRESSED = "self_expressed"


@dataclass
class PreferenceAct:
    """One act of the user expressing taste — the union of a rejection and
    a decision. `privileged` is what the user chose; `sacrificed` is what
    was given up. `trigger` says which extraction surfaced it."""

    id: str
    trigger: str  # MODEL_MISS | SELF_EXPRESSED
    privileged: str
    sacrificed: str
    # For model_miss: the rejection type (REFRAME/REDIRECT/COMPRESSION/
    # SHARPENING). For self_expressed: the decision valence (satisfaction/
    # regret/unresolved/correction/cost). One "category of this act" field.
    kind: str = ""
    why: str = ""  # why_signal (rejection) | would_flip_if (decision)
    prompt_id: str | None = None
    basin: str | None = None
    # For model_miss: the user's next turn (REFRAME persistence context).
    # For self_expressed: the verbatim user words from that moment.
    context: str = ""
    source: str = "lens-build"  # provenance; decisions carry transcript/user_logged/lens_edit
    weight: float = 1.0  # pair-mining evidence weight (user_logged decisions = 2.0)

    def to_dict(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "id": self.id,
            "trigger": self.trigger,
            "privileged": self.privileged,
            "sacrificed": self.sacrificed,
        }
        # Filter defaults/empties to keep the serialized line compact, same
        # convention as RejectionSignal/Decision.
        if self.kind:
            out["kind"] = self.kind
        if self.why:
            out["why"] = self.why
        if self.prompt_id:
            out["prompt_id"] = self.prompt_id
        if self.basin:
            out["basin"] = self.basin
        if self.context:
            out["context"] = self.context
        if self.source != "lens-build":
            out["source"] = self.source
        if self.weight != 1.0:
            out["weight"] = self.weight
        return out

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PreferenceAct":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in known})


def from_rejection(r) -> PreferenceAct:
    """RejectionSignal → PreferenceAct. The user substituted their phrasing
    for the model's, so they privileged the substitute over the quote."""
    return PreferenceAct(
        id=r.id,
        trigger=MODEL_MISS,
        privileged=r.user_substitute,
        sacrificed=r.model_quote,
        kind=r.type,
        why=r.why_signal,
        prompt_id=r.prompt_id,
        basin=r.basin,
        context=r.next_user_turn,
        source="lens-build",
    )


def from_decision(d) -> PreferenceAct:
    """Decision → PreferenceAct. The decision already names privileged vs
    sacrificed directly; the valence becomes the `kind`."""
    return PreferenceAct(
        id=d.id,
        trigger=SELF_EXPRESSED,
        privileged=d.privileged,
        sacrificed=d.sacrificed,
        kind=d.valence,
        why=d.would_flip_if,
        prompt_id=d.prompt_id,
        basin=d.basin,
        context=d.verbatim,
        source=d.source,
        weight=d.weight,
    )


def iter_preference_acts() -> list[PreferenceAct]:
    """The unified read layer: every preference act on disk, model-miss and
    self-expressed, as one stream. Reads the two existing stores
    (rejections.jsonl + decisions.jsonl) through the adapters — no new
    on-disk format at this stage. Order: model_miss first, then
    self_expressed, each in file order."""
    from .decisions import load_decisions
    from .turn_pairs import load_rejections

    acts: list[PreferenceAct] = [from_rejection(r) for r in load_rejections()]
    acts.extend(from_decision(d) for d in load_decisions())
    return acts
