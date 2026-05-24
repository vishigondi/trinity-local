"""Capture user edits to ``~/.trinity/memories/lens.md`` as preference signal.

When the user opens lens.md and edits a line by hand, that's the strongest
possible taste signal Trinity can collect — stronger than rejection signal
extracted from transcripts, stronger than chairman-derived would_flip_if.
The user is *actively asserting* taste, not just pushing back on something
the model produced.

This module is the capture side of #140. Mechanism:

1. After every successful ``lens-build``, write a snapshot of lens.md to
   ``~/.trinity/me/lens_snapshot.md``.
2. At the start of the *next* ``lens-build``, diff the current lens.md
   against that snapshot. Any difference = user edit since last build.
3. Persist each line-level delta as one JSON line in
   ``~/.trinity/me/lens_edits.jsonl``: ``{ts, op, before, after, source}``.

The feed-back side (next dream cycle reads the JSONL and weights edits
heavier in Stage 2 corpus) is a separate slice.

Edge cases:
- No snapshot file (cold start, or first-ever lens-build): no edits
  captured — there's nothing to diff against. The post-build write
  establishes the baseline for next time.
- Snapshot identical to current: no edits captured.
- lens.md missing: skip silently (lens-build is what creates it).
"""
from __future__ import annotations

from dataclasses import dataclass
from difflib import unified_diff
from pathlib import Path

from ..utils import now_iso
from .basins import me_dir


def lens_snapshot_path() -> Path:
    """Path to the post-build snapshot of lens.md used for next-build diffs."""
    return me_dir() / "lens_snapshot.md"


def lens_edits_path() -> Path:
    """Append-only log of user edits captured between builds."""
    return me_dir() / "lens_edits.jsonl"


@dataclass
class LensEdit:
    """One line-level delta captured from a user edit to lens.md.

    ``op`` is one of:
    - ``"add"``: a new line appeared (``before`` is empty, ``after`` has it)
    - ``"remove"``: a line was deleted (``before`` has it, ``after`` empty)

    Modifications surface as adjacent ``remove`` + ``add`` pairs; we don't
    try to pair them at capture time — the chairman reading the JSONL can
    see the sequence and infer intent. Avoids brittle pairing heuristics.
    """
    ts: str
    op: str
    before: str
    after: str
    source: str = "user_edit"

    def to_dict(self) -> dict[str, str]:
        return {
            "ts": self.ts,
            "op": self.op,
            "before": self.before,
            "after": self.after,
            "source": self.source,
        }


def _diff_to_edits(old_text: str, new_text: str, ts: str) -> list[LensEdit]:
    """Compute line-level edits between two lens.md snapshots.

    Uses ``difflib.unified_diff`` (stdlib, no deps). Skips header/hunk
    metadata; emits one ``LensEdit`` per +/- line.
    """
    edits: list[LensEdit] = []
    for line in unified_diff(
        old_text.splitlines(),
        new_text.splitlines(),
        lineterm="",
        n=0,
    ):
        if not line or line.startswith(("---", "+++", "@@")):
            continue
        if line.startswith("-"):
            edits.append(LensEdit(ts=ts, op="remove", before=line[1:], after=""))
        elif line.startswith("+"):
            edits.append(LensEdit(ts=ts, op="add", before="", after=line[1:]))
    return edits


def capture_lens_edits(current_lens_text: str | None = None) -> list[LensEdit]:
    """Diff current lens.md against the post-last-build snapshot.

    Pass ``current_lens_text`` to compare against an in-memory version
    (useful for tests / for callers that have already read lens.md).
    Otherwise reads ``memories_dir()/lens.md`` from disk.

    Returns the captured edits (empty list when no snapshot or no diff)
    and appends them to ``lens_edits.jsonl``. Idempotent: re-running
    against the same input produces duplicates, so callers should only
    invoke once per build cycle.
    """
    from ..state_paths import memories_dir

    if current_lens_text is None:
        lens_path = memories_dir() / "lens.md"
        if not lens_path.exists():
            return []
        try:
            current_lens_text = lens_path.read_text(encoding="utf-8")
        except OSError:
            return []

    snapshot = lens_snapshot_path()
    if not snapshot.exists():
        # First-ever build, or snapshot deleted — no baseline to diff
        # against. Establishing the baseline happens in
        # write_lens_snapshot() after lens-build completes.
        return []

    try:
        old_text = snapshot.read_text(encoding="utf-8")
    except OSError:
        return []

    if old_text == current_lens_text:
        return []

    edits = _diff_to_edits(old_text, current_lens_text, ts=now_iso())
    if not edits:
        return []

    _append_edits(edits)
    return edits


def _append_edits(edits: list[LensEdit]) -> None:
    import json

    path = lens_edits_path()
    with path.open("a", encoding="utf-8") as fh:
        for edit in edits:
            fh.write(json.dumps(edit.to_dict()) + "\n")


def write_lens_snapshot(lens_text: str) -> None:
    """Pin the current lens.md as the baseline for next build's diff.

    Called by lens-build after successfully writing lens.md. Any user
    edits between this call and the next lens-build will surface as
    edits in ``capture_lens_edits()``.
    """
    lens_snapshot_path().write_text(lens_text, encoding="utf-8")


def load_recent_edits(limit: int = 50) -> list[LensEdit]:
    """Read back recent edits — used by the feed-back side (Stage 2
    corpus augmentation) and by the launchpad surfacing ("N edits since
    last dream"). Returns most-recent-first."""
    import json

    path = lens_edits_path()
    if not path.exists():
        return []
    edits: list[LensEdit] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            edits.append(
                LensEdit(
                    ts=obj.get("ts", ""),
                    op=obj.get("op", ""),
                    before=obj.get("before", ""),
                    after=obj.get("after", ""),
                    source=obj.get("source", "user_edit"),
                )
            )
    except OSError:
        return []
    edits.reverse()
    return edits[:limit]
