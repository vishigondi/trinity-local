"""Read/write/list/archive moves from `~/.trinity/moves/`.

Each move lives at `~/.trinity/moves/<slug>/SKILL.md`. Demoted moves
land at `~/.trinity/moves/archive/<slug>/SKILL.md` with their
`trinity_demoted_at` + `trinity_demoted_by_tier` fields populated.

All functions are stateless — they read/write the disk every call.
The Trinity-side of the contract is the dataclass + frontmatter
serialization; the on-disk file is the source of truth.
"""
from __future__ import annotations

from pathlib import Path

from .frontmatter import assemble_document, load_frontmatter, split_document
from .schemas import Move


def _slug_dir(slug: str, *, archived: bool = False) -> Path:
    """Resolve `~/.trinity/moves/<slug>/` or `.../archive/<slug>/`."""
    from .. import state_paths as _sp
    base = _sp.moves_archive_dir() if archived else _sp.moves_dir()
    return base / slug


def _skill_md_path(slug: str, *, archived: bool = False) -> Path:
    return _slug_dir(slug, archived=archived) / "SKILL.md"


def read_move(slug: str, *, archived: bool = False) -> Move:
    """Load a move from `~/.trinity/moves/<slug>/SKILL.md`.

    Raises FileNotFoundError when the move doesn't exist; ValueError
    when the SKILL.md is missing required frontmatter (name +
    description per the agentskills.io spec).
    """
    path = _skill_md_path(slug, archived=archived)
    if not path.exists():
        raise FileNotFoundError(f"Move not found: {path}")
    text = path.read_text(encoding="utf-8")
    fm_text, body = split_document(text)
    if fm_text is None:
        raise ValueError(
            f"Move SKILL.md at {path} missing YAML frontmatter "
            "(must start with `---\\n...`). The SKILL.md spec requires "
            "name + description frontmatter; Trinity adds extension "
            "fields on top."
        )
    fm = load_frontmatter(fm_text)
    return Move.from_frontmatter(fm, body=body)


def write_move(move: Move, *, archived: bool = False) -> Path:
    """Persist a move to `~/.trinity/moves/<slug>/SKILL.md`.

    Returns the on-disk path. Creates the parent directory if needed.
    Caller controls the slug via Move.name (slugified — kebab-case
    enforced).
    """
    slug = _slugify(move.name)
    target = _skill_md_path(slug, archived=archived)
    target.parent.mkdir(parents=True, exist_ok=True)
    text = assemble_document(move.to_frontmatter(), move.body)
    target.write_text(text, encoding="utf-8")
    return target


def list_moves(*, archived: bool = False) -> list[Move]:
    """Enumerate all moves in `~/.trinity/moves/` (or `.../archive/`).

    Cold install: returns []. Subdirectories without a SKILL.md are
    skipped silently — the spec is one SKILL.md per slug-directory.
    """
    from .. import state_paths as _sp
    base = _sp.moves_archive_dir() if archived else _sp.moves_dir()
    if not base.exists():
        return []
    out: list[Move] = []
    for slug_dir in sorted(base.iterdir()):
        # Skip the `archive` subdirectory when listing active moves.
        if not archived and slug_dir.name == "archive":
            continue
        if not slug_dir.is_dir():
            continue
        skill_md = slug_dir / "SKILL.md"
        if not skill_md.exists():
            continue
        try:
            out.append(read_move(slug_dir.name, archived=archived))
        except (FileNotFoundError, ValueError):
            # Tolerate hand-edited / partial moves — list_moves should
            # never crash on a single bad file.
            continue
    return out


def archive_move(slug: str, *, tier: str, reason: str, when: str | None = None) -> Path:
    """Demote an active move into `~/.trinity/moves/archive/<slug>/`.

    Sets `trinity_demoted_at` (caller-supplied or auto-generated ISO)
    and `trinity_demoted_by_tier` (T1 / T2 / T3 / T4) in the move's
    frontmatter. Appends the `reason` to the move's body so users
    inspecting the archive entry can see why it was demoted.

    The active move directory is removed after the archive write is
    confirmed; if anything in the write path fails, the active move is
    left in place (no partial state).
    """
    from datetime import datetime, timezone
    import shutil
    move = read_move(slug, archived=False)
    move.trinity_demoted_at = when or datetime.now(timezone.utc).isoformat(timespec="seconds")
    move.trinity_demoted_by_tier = tier
    move.body = (
        (move.body.rstrip() + "\n\n" if move.body.strip() else "")
        + f"---\n\n## Demoted at {move.trinity_demoted_at} by {tier}\n\n{reason}\n"
    )
    archive_path = write_move(move, archived=True)
    # Remove the active dir AFTER the archive copy is safely on disk
    active_dir = _slug_dir(slug, archived=False)
    if active_dir.exists():
        shutil.rmtree(active_dir)
    return archive_path


def _slugify(name: str) -> str:
    """Convert a move name into a filesystem-safe kebab-case slug.

    SKILL.md spec doesn't constrain the name's shape, but Trinity stores
    moves under `~/.trinity/moves/<slug>/` so we need a stable filename-
    friendly mapping. Lowercase + replace non-alphanumerics with '-',
    collapse runs of '-', strip leading/trailing.
    """
    import re
    s = name.lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = re.sub(r"-+", "-", s).strip("-")
    return s or "untitled"
