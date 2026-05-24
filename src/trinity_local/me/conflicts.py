"""Stage 4b — active conflict surfacing (#141, plan Extension #3).

After Stage 4 splits LensPairs into accepted vs. orderings, the same
extracted pairs can still encode *structural contradictions* — pair A
privileges X over Y in one basin, pair B privileges Y over X in
another. Today the lens silently averages over these, leading to
chairman context that "smooths" rather than forcing the meta-judgment.

This module detects those contradictions deterministically and persists
them as a separate `~/.trinity/me/conflicts.json` file so:

- The lens.md renderer can surface a "⚠ Tensions in tension" section
- The launchpad can count them as a health/awareness signal
- A future user-facing meta-judgment UI can pull from one source

Detection (v1, deterministic): two pairs conflict when their poles are
literally swapped (case-insensitive, whitespace-normalized). Example:
  Pair A: pole_a="infrastructure", pole_b="interface"
  Pair B: pole_a="interface",      pole_b="infrastructure"
→ Conflict. Same axis, opposite privilege direction.

When a conflict's two pairs share horizon (e.g. both `strategic`), the
conflict is a REAL contradiction worth resolving. When horizons differ,
it's likely a META-PATTERN ("tactical privileges X but strategic
privileges Y" — that's not contradiction, that's a feature of
multi-resolution preferences and #139 already handles weighting).

V2 will use embedding similarity to catch semantic conflicts where
poles are phrased differently — deferred. Documented in CLAUDE.md
Future #B as part of the per-basin judgment-dimension work.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .basins import me_dir
from .pair_mining import LensPair


def conflicts_path() -> Path:
    """`~/.trinity/me/conflicts.json` — Stage 4b output."""
    return me_dir() / "conflicts.json"


def _pair_id(pair: LensPair) -> str:
    """Stable identifier for a LensPair derived from its poles.

    LensPair has no native id field — pairs are identified positionally
    in lenses.json. We derive a hash so conflicts can reference pairs
    without depending on list ordering (which changes across builds).
    """
    import hashlib

    src = f"{pair.pole_a.strip().lower()}|{pair.pole_b.strip().lower()}"
    return f"p_{hashlib.sha1(src.encode('utf-8')).hexdigest()[:12]}"


@dataclass
class Conflict:
    """A detected contradiction between two LensPairs.

    ``horizon_match`` is True when both pairs share the same horizon —
    that's the case worth user attention. False when horizons differ
    (e.g. tactical vs strategic) — surface as note, not as alarm:
    multi-resolution preferences are NOT contradictions.
    """
    pair_a_id: str
    pair_b_id: str
    pole_a_axis: str          # the "A pole" of the conflict — what one pair privileges
    pole_b_axis: str          # the "B pole" of the conflict — what the other privileges
    horizon_a: str
    horizon_b: str
    horizon_match: bool
    basins_a: list[str] = field(default_factory=list)
    basins_b: list[str] = field(default_factory=list)
    why_conflicting: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "pair_a_id": self.pair_a_id,
            "pair_b_id": self.pair_b_id,
            "pole_a_axis": self.pole_a_axis,
            "pole_b_axis": self.pole_b_axis,
            "horizon_a": self.horizon_a,
            "horizon_b": self.horizon_b,
            "horizon_match": self.horizon_match,
            "basins_a": self.basins_a,
            "basins_b": self.basins_b,
            "why_conflicting": self.why_conflicting,
        }


def detect_conflicts(pairs: list[LensPair]) -> list[Conflict]:
    """Stage 4b: scan accepted + orderings pairs for swapped-poles.

    Detection is deterministic and literal — two pairs conflict iff
    after case-insensitive normalization, pair A's pole_a equals pair
    B's pole_b AND pair A's pole_b equals pair B's pole_a. Same axis,
    flipped privilege direction.

    Self-comparison and duplicate-pair pairings are skipped. Order is
    canonicalized (alphabetic by pair_id) so the same conflict doesn't
    surface twice from different scan orders.
    """
    by_id: dict[str, LensPair] = {}
    for p in pairs:
        pid = _pair_id(p)
        # If two pairs hash to the same id (genuinely identical poles),
        # keep the first — they're not in conflict with themselves.
        if pid in by_id:
            continue
        by_id[pid] = p

    seen_keys: set[tuple[str, str]] = set()
    conflicts: list[Conflict] = []
    ids = list(by_id.keys())
    for i, a_id in enumerate(ids):
        for b_id in ids[i + 1:]:
            a = by_id[a_id]
            b = by_id[b_id]
            if _is_swapped_poles(a, b):
                key = tuple(sorted((a_id, b_id)))
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                horizon_match = (a.horizon == b.horizon)
                why = _explain_conflict(a, b, horizon_match)
                conflicts.append(
                    Conflict(
                        pair_a_id=a_id,
                        pair_b_id=b_id,
                        pole_a_axis=a.pole_a.strip(),
                        pole_b_axis=a.pole_b.strip(),
                        horizon_a=a.horizon,
                        horizon_b=b.horizon,
                        horizon_match=horizon_match,
                        basins_a=list(a.basins_spanned),
                        basins_b=list(b.basins_spanned),
                        why_conflicting=why,
                    )
                )
    return conflicts


def _is_swapped_poles(a: LensPair, b: LensPair) -> bool:
    """True iff pair A's poles are exactly pair B's poles, swapped.

    Case + whitespace normalized. Returns False on self-comparison
    (same pair, same poles — not a conflict).
    """
    a_pa = a.pole_a.strip().lower()
    a_pb = a.pole_b.strip().lower()
    b_pa = b.pole_a.strip().lower()
    b_pb = b.pole_b.strip().lower()
    if a_pa == b_pa and a_pb == b_pb:
        return False  # identical, not swapped
    return a_pa == b_pb and a_pb == b_pa


def _explain_conflict(a: LensPair, b: LensPair, horizon_match: bool) -> str:
    """Short prose explanation for the lens.md renderer."""
    if horizon_match:
        return (
            f"Both pairs are {a.horizon}-horizon but privilege opposite poles "
            f"of the same axis ('{a.pole_a}' vs '{a.pole_b}'). Resolving "
            f"this requires a meta-judgment about which basin's evidence "
            f"is more load-bearing."
        )
    return (
        f"Different horizons ({a.horizon} vs {b.horizon}) privilege opposite "
        f"poles. This is likely multi-resolution preference, not contradiction "
        f"— #139 weighting handles it without forcing a choice."
    )


def save_conflicts(conflicts: list[Conflict]) -> Path:
    """Write conflicts to `~/.trinity/me/conflicts.json` as an array.

    Overwrites any existing file (conflicts are recomputed from
    scratch each build; old detections don't accumulate as JSONL).
    """
    path = conflicts_path()
    path.write_text(
        json.dumps([c.to_dict() for c in conflicts], indent=2),
        encoding="utf-8",
    )
    return path


def load_conflicts() -> list[Conflict]:
    """Read conflicts.json into Conflict objects. Empty list on missing/empty."""
    path = conflicts_path()
    if not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if not isinstance(raw, list):
        return []
    out: list[Conflict] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        out.append(
            Conflict(
                pair_a_id=entry.get("pair_a_id", ""),
                pair_b_id=entry.get("pair_b_id", ""),
                pole_a_axis=entry.get("pole_a_axis", ""),
                pole_b_axis=entry.get("pole_b_axis", ""),
                horizon_a=entry.get("horizon_a", "tactical"),
                horizon_b=entry.get("horizon_b", "tactical"),
                horizon_match=bool(entry.get("horizon_match", False)),
                basins_a=list(entry.get("basins_a") or []),
                basins_b=list(entry.get("basins_b") or []),
                why_conflicting=entry.get("why_conflicting", ""),
            )
        )
    return out


def count_active_conflicts() -> int:
    """How many same-horizon conflicts exist (the launchpad-surfacing count).

    Different-horizon conflicts are not surfaced as alarms — they're
    multi-resolution preferences which #139 already handles.
    """
    return sum(1 for c in load_conflicts() if c.horizon_match)
