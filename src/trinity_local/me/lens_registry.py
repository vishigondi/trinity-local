"""Lens accumulation registry — the ACCUMULATE layer of the lens redesign.

Turns the lens from *stateless* (every rebuild replaces the surface
tensions) into *accumulating* (a durable registry of tensions; each
rebuild reinforces or extends rather than overwrites). See
``docs/lens-redesign.md`` build-sequence step 1.

Identity is by **embedding cosine** on a tension's probe text — not a
string match on its poles — because the chairman rephrases the same
tension run-to-run. Measured live: a rebuild over an unchanged
49-rejection corpus produced 3 tensions one run, 2 the next, with zero
string overlap but clear semantic rhyme. Cosine identity is what lets
the same tension persist across those rephrasings, which is the whole
point of accretion.

State: ``~/.trinity/me/lens_registry.json`` — one entry per ``tension_id``::

    {tension_id, pole_a, pole_b, failure_a, failure_b, basins_spanned,
     horizon, probe_text, evidence_ids [unioned across rebuilds],
     first_seen, last_confirmed}

Derived at render (NOT stored — a derived field can't drift out of sync
with the evidence, which is the corruption class this session kept
hitting)::

    support_count(t) = len(evidence_ids)
    active(t)        = support_count >= ACTIVE_MIN
                       and (now - last_confirmed) <= RECENCY_DAYS

The registry only ever **unions** evidence and **bumps** last_confirmed
— a fresh extraction can extend a tension but never erase it (the same
append-only guarantee that makes ``mark_pick_wrong`` durable). Decay is
purely via recency: a tension that stops being confirmed goes inactive
after ``RECENCY_DAYS`` even though its support_count is unchanged. There
is nothing to "decay" actively — support and recency are recomputed from
the stored evidence every render.

Probe embeddings are recomputed from ``probe_text`` at reconcile time
rather than cached on disk: there are only a handful of tensions, so the
cost is trivial, and it sidesteps the stale-embedding class entirely
(when the embedding backend changes — TF-IDF ↔ MLX — cached vectors
become incomparable, but a freshly recomputed one is always in the live
space).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ..utils import atomic_write_text, now_iso, stable_id
from .basins import me_dir
from .pair_mining import LensPair, _tension_probe_text

# Cosine threshold for "these two probe texts are the same tension".
# Start at 0.80 per docs/lens-redesign.md risk #2; tune on real rebuild
# cadence. Too high → the same tension splits into duplicates each
# rebuild (no accretion); too low → distinct tensions merge (lost
# resolution). Under the TF-IDF fallback the same threshold is coarser
# (lexical overlap, not semantic) — rephrasings with different words
# won't match, which is acceptable, documented degradation (risk #4).
MATCH_THRESHOLD = 0.80

# A tension is "active" (rendered) once it has at least this much
# distinct evidence. 1 is deliberate: a brand-new user's lens *should*
# surface on the first build (low-confidence is correct, invisible is
# not — cold-start, risk #3). Higher floors belong to a later
# confidence-tiering pass, not the accumulation core.
ACTIVE_MIN = 1

# Recency window (days). A tension not re-confirmed within this many days
# fades to inactive regardless of accumulated support — graceful decay.
RECENCY_DAYS = 90


def registry_path() -> Path:
    """``~/.trinity/me/lens_registry.json`` — the durable tension registry."""
    return me_dir() / "lens_registry.json"


@dataclass
class RegistryEntry:
    """One durable tension. Poles/failures are the *canonical* (first
    registered) phrasing — kept stable across rebuilds so the rendered
    lens doesn't reword itself when the chairman does. Evidence and
    basins accrete; ``last_confirmed`` advances on every match."""

    tension_id: str
    pole_a: str
    pole_b: str
    failure_a: str = ""
    failure_b: str = ""
    basins_spanned: list[str] = field(default_factory=list)
    horizon: str = "tactical"
    probe_text: str = ""
    evidence_ids: list[str] = field(default_factory=list)
    first_seen: str = ""
    last_confirmed: str = ""

    @property
    def support_count(self) -> int:
        return len(self.evidence_ids)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tension_id": self.tension_id,
            "pole_a": self.pole_a,
            "pole_b": self.pole_b,
            "failure_a": self.failure_a,
            "failure_b": self.failure_b,
            "basins_spanned": self.basins_spanned,
            "horizon": self.horizon,
            "probe_text": self.probe_text,
            "evidence_ids": self.evidence_ids,
            "first_seen": self.first_seen,
            "last_confirmed": self.last_confirmed,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RegistryEntry":
        return cls(
            tension_id=d["tension_id"],
            pole_a=d.get("pole_a", ""),
            pole_b=d.get("pole_b", ""),
            failure_a=d.get("failure_a", ""),
            failure_b=d.get("failure_b", ""),
            basins_spanned=list(d.get("basins_spanned", [])),
            horizon=d.get("horizon", "tactical"),
            probe_text=d.get("probe_text", ""),
            evidence_ids=list(d.get("evidence_ids", [])),
            first_seen=d.get("first_seen", ""),
            last_confirmed=d.get("last_confirmed", ""),
        )

    def to_lens_pair(self) -> LensPair:
        """Reconstruct a renderable LensPair from the registry entry, so
        the existing lens.md renderer can stay unchanged — the registry
        carries every field render needs."""
        return LensPair(
            pole_a=self.pole_a,
            pole_b=self.pole_b,
            failure_a=self.failure_a,
            failure_b=self.failure_b,
            basins_spanned=list(self.basins_spanned),
            horizon=self.horizon,
            verdict="accepted",
        )


def _evidence_ids_for(pair: LensPair) -> list[str]:
    """The distinct evidence ids backing a candidate tension: its decision
    ids plus any ids referenced in dual_evidence. Order-stable + deduped."""
    ids: list[str] = list(pair.tension_decisions)
    for vals in (pair.dual_evidence or {}).values():
        if isinstance(vals, list):
            ids.extend(str(v) for v in vals)
    seen: set[str] = set()
    out: list[str] = []
    for i in ids:
        if i and i not in seen:
            seen.add(i)
            out.append(i)
    return out


def load_registry() -> list[RegistryEntry]:
    path = registry_path()
    if not path.exists():
        return []
    try:
        import json

        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    entries = data.get("tensions", []) if isinstance(data, dict) else []
    out: list[RegistryEntry] = []
    for e in entries:
        if isinstance(e, dict) and e.get("tension_id"):
            out.append(RegistryEntry.from_dict(e))
    return out


def save_registry(entries: list[RegistryEntry]) -> Path:
    import json

    path = registry_path()
    payload = {"tensions": [e.to_dict() for e in entries]}
    atomic_write_text(path, json.dumps(payload, indent=2, ensure_ascii=False))
    return path


def _embed_probes(texts: list[str]) -> list[list[float] | None]:
    """Embed probe texts with the live backend. Returns None for any text
    that fails to embed (offline + no fallback) so the caller degrades to
    string matching for that probe rather than crashing the build."""
    from ..embeddings import embed

    out: list[list[float] | None] = []
    for t in texts:
        try:
            out.append(embed(t) if t else None)
        except Exception:
            out.append(None)
    return out


def _best_match(
    cand_emb: list[float] | None,
    cand_probe: str,
    reg_embs: list[list[float] | None],
    registry: list[RegistryEntry],
) -> int | None:
    """Index of the registry entry whose probe is closest to the candidate
    above MATCH_THRESHOLD, or None. Uses embedding cosine when both
    vectors are present and dimension-compatible; otherwise falls back to
    exact probe-text equality (the only string match safe enough to merge
    on — a looser lexical fuzzy-match risks collapsing distinct tensions)."""
    from ..embeddings.backend_tfidf import cosine_similarity

    best_idx: int | None = None
    best_score = MATCH_THRESHOLD
    for idx, (entry, reg_emb) in enumerate(zip(registry, reg_embs)):
        if cand_emb is not None and reg_emb is not None and len(cand_emb) == len(reg_emb):
            score = cosine_similarity(cand_emb, reg_emb)
            if score >= best_score:
                best_score = score
                best_idx = idx
        elif cand_probe and entry.probe_text == cand_probe:
            return idx
    return best_idx


def reconcile(candidates: list[LensPair], *, now: str | None = None) -> list[RegistryEntry]:
    """Stage 4.5 — match this rebuild's accepted candidates against the
    durable registry by cosine identity, accrue their evidence, and bump
    recency. New tensions register fresh. Deterministic; no LLM.

    Canonical phrasing is *first-registered-wins*: a matched candidate's
    own poles/failures are discarded in favor of the registry's, so the
    rendered lens stays stable when the chairman rewords an unchanged
    tension. Only evidence ids, spanned basins, and last_confirmed change
    on a match.

    Returns the full updated registry (persisted as a side effect)."""
    ts = now or now_iso()
    registry = load_registry()
    reg_embs = _embed_probes([e.probe_text for e in registry])

    for cand in candidates:
        probe = _tension_probe_text(cand)
        cand_emb = _embed_probes([probe])[0]
        evidence = _evidence_ids_for(cand)
        match_idx = _best_match(cand_emb, probe, reg_embs, registry)

        if match_idx is not None:
            entry = registry[match_idx]
            merged = list(entry.evidence_ids)
            seen = set(merged)
            for e in evidence:
                if e not in seen:
                    seen.add(e)
                    merged.append(e)
            entry.evidence_ids = merged
            for b in cand.basins_spanned:
                if b not in entry.basins_spanned:
                    entry.basins_spanned.append(b)
            entry.last_confirmed = ts
        else:
            tid = stable_id("tension", cand.pole_a, cand.pole_b)
            registry.append(
                RegistryEntry(
                    tension_id=tid,
                    pole_a=cand.pole_a,
                    pole_b=cand.pole_b,
                    failure_a=cand.failure_a,
                    failure_b=cand.failure_b,
                    basins_spanned=list(cand.basins_spanned),
                    horizon=cand.horizon,
                    probe_text=probe,
                    evidence_ids=evidence,
                    first_seen=ts,
                    last_confirmed=ts,
                )
            )
            # Keep the parallel embedding list aligned so a second
            # candidate this run can match the just-registered tension.
            reg_embs.append(cand_emb)

    save_registry(registry)
    return registry


def _parse_iso(ts: str) -> datetime | None:
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def is_active(entry: RegistryEntry, *, now: str | None = None) -> bool:
    if entry.support_count < ACTIVE_MIN:
        return False
    confirmed = _parse_iso(entry.last_confirmed)
    if confirmed is None:
        return False
    now_dt = _parse_iso(now or now_iso()) or datetime.now(timezone.utc)
    return (now_dt - confirmed).days <= RECENCY_DAYS


def active_tensions_sorted(*, now: str | None = None) -> list[RegistryEntry]:
    """The render view: active tensions, highest-support first (the MBTI
    'function stack' insight — dominant tensions lead, the chairman
    weights them heaviest). Ties broken by recency. Inactive tensions
    stay in the registry (revivable) but aren't rendered."""
    active = [e for e in load_registry() if is_active(e, now=now)]
    active.sort(key=lambda e: (e.support_count, e.last_confirmed), reverse=True)
    return active
