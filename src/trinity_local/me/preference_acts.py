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

from dataclasses import dataclass, fields
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


def to_rejection(a: "PreferenceAct"):
    """PreferenceAct (model_miss) → RejectionSignal — the inverse of
    ``from_rejection``. Lets lens-build's delta-extraction (#210) reload the
    previously-extracted rejections from the ledger and merge new ones into
    them without re-running Stage 0 over the whole corpus. Lossless for
    model_miss acts (id is content-stable, so a re-extraction collapses onto
    the same row). Imported lazily to avoid a turn_pairs↔preference_acts
    import cycle."""
    from .turn_pairs import RejectionSignal

    return RejectionSignal(
        id=a.id,
        type=a.kind,
        model_quote=a.sacrificed,
        user_substitute=a.privileged,
        why_signal=a.why,
        prompt_id=a.prompt_id,
        basin=a.basin,
        next_user_turn=a.context,
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
    """The unified read layer: every preference act, model-miss and
    self-expressed, as one stream. Order: model_miss first, then
    self_expressed.

    EXTRACT-unification Stage 4b (legacy retirement): reads the unified
    ledger (``preference_acts.jsonl``) as the SOLE store. The legacy
    rejections.jsonl + decisions.jsonl stores were retired here — every
    writer (Stage 0/2 lens-build, eval-import) now writes only the ledger,
    so there's nothing left to merge. Pure read."""
    acts = load_preference_acts()
    acts.sort(key=lambda a: 0 if a.trigger == MODEL_MISS else 1)
    return acts


def preference_acts_path():
    """``~/.trinity/me/preference_acts.jsonl`` — the unified ledger
    (EXTRACT-unification Stage 3). The single serialization of every
    preference act, refreshed by lens-build / lens-resync. Today a
    canonical export (the read path still unions the legacy stores via
    iter_preference_acts); the storage migration retires
    rejections.jsonl + decisions.jsonl in its favor once every reader has
    moved to it."""
    from .basins import me_dir

    return me_dir() / "preference_acts.jsonl"


def save_preference_acts(acts: list[PreferenceAct], *, allow_shrink: bool = False):
    """Write the unified ledger atomically (one JSON object per line).

    Carries the #194 clobber guard, because this ledger is on its way to
    becoming the source of truth: refuse to overwrite a populated ledger
    with a cliff-drop (empty when >= _CLOBBER_MIN_EXISTING rows exist, or
    below _CLOBBER_MIN_FRACTION of the existing count) — almost always a
    transient empty build, not a real shrink. The live ledger is
    preserved and the would-be result is stashed to a `.degenerate`
    sidecar. `allow_shrink=True` is the escape hatch for a genuine
    shrink. The callers (lens-build / lens-resync) wrap this best-effort,
    so a raised guard preserves the ledger and the build continues on the
    legacy stores."""
    import json

    from ..utils import atomic_write_text
    from .turn_pairs import (
        _CLOBBER_MIN_EXISTING,
        _CLOBBER_MIN_FRACTION,
        DegenerateExtractionError,
    )

    path = preference_acts_path()
    existing = 0
    if path.exists():
        try:
            existing = sum(
                1 for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()
            )
        except OSError:
            existing = 0
    floor = max(1, int(existing * _CLOBBER_MIN_FRACTION))
    if not allow_shrink and existing >= _CLOBBER_MIN_EXISTING and len(acts) < floor:
        sidecar = path.parent / (path.name + ".degenerate")
        try:
            sidecar.write_text(
                "\n".join(json.dumps(a.to_dict()) for a in acts) + ("\n" if acts else ""),
                encoding="utf-8",
            )
        except OSError:
            pass
        raise DegenerateExtractionError(
            f"Refusing to overwrite {existing} preference acts with "
            f"{len(acts)} (cliff-drop below {floor}). Live ledger preserved; "
            f"degenerate result written to {sidecar.name}. Pass "
            f"allow_shrink=True only if the corpus genuinely shrank."
        )
    body = "\n".join(json.dumps(a.to_dict()) for a in acts)
    atomic_write_text(path, body + "\n" if body else "")
    return path


def append_preference_acts(acts: list[PreferenceAct]) -> None:
    """Append acts to the ledger (append-only, mirroring the legacy
    rejections.jsonl writer). Used by provider-import (`eval-import` /
    `import_provider_memory`) for incremental adds; lens-build / lens-resync
    use ``save_preference_acts`` (full rewrite). Append never shrinks, so it
    needs no clobber guard — the caller is responsible for id-dedup."""
    import json

    if not acts:
        return
    path = preference_acts_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for a in acts:
            fh.write(json.dumps(a.to_dict()) + "\n")


def load_preference_acts() -> list[PreferenceAct]:
    """Read the unified ledger back. Tolerant: skips malformed /
    under-specified lines. (Distinct from iter_preference_acts, which
    unions the legacy stores — this reads the exported file directly,
    e.g. for `lens-acts` introspection and the eventual read-path flip.)"""
    import json

    path = preference_acts_path()
    if not path.exists():
        return []
    out: list[PreferenceAct] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except ValueError:
            continue
        if not (
            isinstance(d, dict)
            and d.get("id")
            and d.get("trigger")
            and d.get("privileged")
            and d.get("sacrificed")
        ):
            continue
        # Defense in depth: even past the guard, a record could be missing
        # a required dataclass field (partial write, external import) and
        # blow up from_dict's positional construction. Skip it, don't crash
        # the whole load.
        try:
            out.append(PreferenceAct.from_dict(d))
        except (TypeError, KeyError):
            continue
    return out
