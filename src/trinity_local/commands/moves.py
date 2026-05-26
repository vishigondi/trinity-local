"""trinity-local moves-* — inspect, refresh, and share the moves substrate.

The moves substrate (`~/.trinity/moves/`) is the procedural layer of
Trinity's v2 hierarchy. Each move is one SKILL.md file with extension
frontmatter that tracks Bayesian state (alpha/beta), tier scores
(T1/T2/T3), and provenance (which rejections it was promoted from).

Three verbs ship here:

- `moves-build` — standalone runner for Phase 6 of dream. Lets users
  refresh the promotion + demotion loop without running a full dream
  cycle. Default behavior matches what `dream` does internally.

- `moves-show` — JSON dump of one or all moves. Default: active list,
  newest-first, with posterior + tier scores. `--slug <name>` dumps a
  single move's full SKILL.md. `--archived` includes demoted moves.

- `moves-export` — bundle the active moves directory as a tarball or
  copy-out a flat directory. Lets users share their substrate or back
  it up before a wipe. Archived moves excluded by default; opt in via
  `--include-archived`.

The substrate is portable by construction — SKILL.md is an open format
(agentskills.io). A user can hand the export to another agent harness
and the trinity_* extension fields are tolerated as custom frontmatter.
"""
from __future__ import annotations

import json
import sys
import tarfile
from pathlib import Path

from ..moves import store
from ..moves.schemas import Move
from ..state_paths import moves_archive_dir, moves_dir


def register(subparsers):
    _register_build(subparsers)
    _register_show(subparsers)
    _register_export(subparsers)


# ─── moves-build ─────────────────────────────────────────────────────


def _register_build(subparsers):
    sp = subparsers.add_parser(
        "moves-build",
        help=(
            "Run the moves promotion + demotion loop once. Same logic dream "
            "runs in Phase 6, exposed standalone so you can refresh moves "
            "without re-walking the prompt corpus."
        ),
    )
    sp.add_argument(
        "--primary-provider",
        default=None,
        help="Chairman provider for T3 eval. Defaults to claude.",
    )
    sp.add_argument(
        "--skip-promotion",
        action="store_true",
        help="Skip Phase 6b: discovery + promotion of new candidates.",
    )
    sp.add_argument(
        "--skip-demotion",
        action="store_true",
        help="Skip Phase 6c: re-eval T4 on active moves.",
    )
    sp.set_defaults(handler=handle_build)


def handle_build(args) -> int:
    """Resolve chairman + lens + basin centroids, then delegate to
    ``moves.dream.phase_6_moves_pass``.

    Mirrors the resolution path in ``commands/dream.py::_moves_pass`` —
    keeping the two in sync is the explicit cost of having a standalone
    verb. Refactor only if a third caller appears.
    """
    from ..moves.dream import phase_6_moves_pass

    chairman = _resolve_chairman(getattr(args, "primary_provider", None))
    lens_text = _read_lens_text()
    basin_centroids = _read_basin_centroids()

    report = phase_6_moves_pass(
        chairman_provider_config=chairman,
        lens_text=lens_text,
        basin_centroids=basin_centroids,
        skip_promotion=bool(getattr(args, "skip_promotion", False)),
        skip_demotion=bool(getattr(args, "skip_demotion", False)),
    )
    print(json.dumps({"ok": True, "phase_6_report": report}, indent=2))
    return 0


def _resolve_chairman(primary_provider: str | None):
    from ..config import load_config

    try:
        config = load_config(required=False)
    except Exception:
        return None
    providers = getattr(config, "providers", None) or {}
    name = (primary_provider or "claude").lower()
    return providers.get(name)


def _read_lens_text() -> str:
    from .. import state_paths as _sp

    path = _sp.memories_dir() / "lens.md"
    if not path.exists():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def _read_basin_centroids() -> dict[str, list[float]]:
    from .. import state_paths as _sp

    path = _sp.memories_dir() / "topics.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    out: dict[str, list[float]] = {}
    for basin in data.get("basins", []) or []:
        if "id" in basin and "centroid" in basin:
            out[str(basin["id"])] = list(basin["centroid"])
    return out


# ─── moves-show ──────────────────────────────────────────────────────


def _register_show(subparsers):
    sp = subparsers.add_parser(
        "moves-show",
        help=(
            "Inspect the moves substrate. Default: JSON summary of active "
            "moves with posterior + tier scores. With --slug, dumps one "
            "move's full SKILL.md."
        ),
    )
    sp.add_argument(
        "--slug",
        default=None,
        help="Show one specific move (slug = kebab-case of move name).",
    )
    sp.add_argument(
        "--archived",
        action="store_true",
        help="List archived (demoted) moves instead of active ones.",
    )
    sp.add_argument(
        "--full",
        action="store_true",
        help="Include the body (SKILL.md procedure text) per move. Off by default for tidy output.",
    )
    sp.set_defaults(handler=handle_show)


def handle_show(args) -> int:
    if args.slug:
        return _show_one(args.slug, archived=args.archived)
    return _show_list(archived=args.archived, full=bool(getattr(args, "full", False)))


def _show_one(slug: str, *, archived: bool) -> int:
    try:
        move = store.read_move(slug, archived=archived)
    except FileNotFoundError:
        # Try the other side before giving up — common UX hiccup is
        # remembering the name but not which list it's on.
        try:
            move = store.read_move(slug, archived=not archived)
            archived = not archived
        except FileNotFoundError:
            print(json.dumps({
                "ok": False,
                "error": f"Move not found: {slug}",
                "hint": "Run `trinity-local moves-show` to list active slugs.",
            }, indent=2), file=sys.stderr)
            return 1
    print(json.dumps({
        "ok": True,
        "slug": slug,
        "archived": archived,
        "move": _move_to_dict(move, full=True),
    }, indent=2))
    return 0


def _show_list(*, archived: bool, full: bool) -> int:
    moves = store.list_moves(archived=archived)
    moves = _sort_newest_first(moves)
    print(json.dumps({
        "ok": True,
        "archived": archived,
        "count": len(moves),
        "moves": [_move_to_dict(m, full=full) for m in moves],
    }, indent=2))
    return 0


def _sort_newest_first(moves: list[Move]) -> list[Move]:
    """Sort active moves by promoted_at desc; archived by demoted_at desc.

    Falls back to name when timestamps are missing (shouldn't happen on
    a healthy substrate but cheap to guard).
    """
    def key(m: Move):
        ts = m.trinity_demoted_at or m.trinity_promoted_at or ""
        return (ts, m.name)
    return sorted(moves, key=key, reverse=True)


def _move_to_dict(move: Move, *, full: bool) -> dict:
    """Render a Move for CLI JSON output.

    Trims the on-disk frontmatter dict to what humans/agents care about
    when scanning a list: name, description, Bayesian state, tier
    scores, basin. Hides empty fields. Body included only when full=True.
    """
    out: dict = {
        "name": move.name,
        "description": move.description,
        "basin": move.trinity_basin_id,
        "promoted_at": move.trinity_promoted_at,
        "alpha": move.trinity_alpha,
        "beta": move.trinity_beta,
        "executions": move.trinity_execution_count,
        "posterior": round(move.posterior, 4),
    }
    if move.trinity_demoted_at:
        out["demoted_at"] = move.trinity_demoted_at
        out["demoted_by_tier"] = move.trinity_demoted_by_tier
    for k in (
        "trinity_t1_lexical_score",
        "trinity_t2_embedding_score",
        "trinity_t3_chairman_score",
        "trinity_eval_baseline",
    ):
        v = getattr(move, k)
        if v is not None:
            out[k[len("trinity_"):]] = v
    if move.trinity_promoted_from:
        out["promoted_from"] = move.trinity_promoted_from
    if full:
        out["body"] = move.body
    return out


# ─── moves-export ────────────────────────────────────────────────────


def _register_export(subparsers):
    sp = subparsers.add_parser(
        "moves-export",
        help=(
            "Bundle the moves substrate into a tarball or directory for "
            "sharing/backup. SKILL.md is an open format — recipients can "
            "drop the bundle into their own ~/.trinity/moves/."
        ),
    )
    sp.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Output path. Defaults to ~/.trinity/share/moves-export.tar.gz.",
    )
    sp.add_argument(
        "--format",
        choices=["tar.gz", "dir"],
        default="tar.gz",
        help="Bundle format. tar.gz produces one file; dir copies into a flat directory.",
    )
    sp.add_argument(
        "--include-archived",
        action="store_true",
        help="Include demoted moves (under archive/). Off by default — most users want only their active substrate.",
    )
    sp.set_defaults(handler=handle_export)


def handle_export(args) -> int:
    from ..state_paths import share_dir

    # moves_dir() always exists (state_paths creates it on access), so
    # "cold install" and "empty substrate" collapse to the same case.
    sources = _collect_sources(include_archived=bool(getattr(args, "include_archived", False)))
    if not sources:
        print(json.dumps({
            "ok": False,
            "error": "Nothing to export — no active moves found.",
            "hint": "Run `trinity-local moves-build` (or `trinity-local dream`) to populate the substrate. Use --include-archived to include demoted moves.",
        }, indent=2), file=sys.stderr)
        return 1

    if args.format == "tar.gz":
        out = args.out or (share_dir() / "moves-export.tar.gz")
        return _write_tarball(out, sources)
    out = args.out or (share_dir() / "moves-export")
    return _write_directory(out, sources)


def _collect_sources(*, include_archived: bool) -> list[tuple[Path, str]]:
    """Walk moves_dir + (optionally) archive_dir; return (abs_path, arcname).

    arcname is the path inside the bundle. We use ``moves/<slug>/SKILL.md``
    for active and ``moves/archive/<slug>/SKILL.md`` for archived so the
    bundle mirrors the on-disk layout under ~/.trinity/.
    """
    out: list[tuple[Path, str]] = []
    base = moves_dir()
    if base.exists():
        for slug_dir in sorted(base.iterdir()):
            if not slug_dir.is_dir():
                continue
            if slug_dir.name == "archive":
                continue
            skill_md = slug_dir / "SKILL.md"
            if skill_md.exists():
                out.append((skill_md, f"moves/{slug_dir.name}/SKILL.md"))
    if include_archived:
        arch = moves_archive_dir()
        if arch.exists():
            for slug_dir in sorted(arch.iterdir()):
                if not slug_dir.is_dir():
                    continue
                skill_md = slug_dir / "SKILL.md"
                if skill_md.exists():
                    out.append((skill_md, f"moves/archive/{slug_dir.name}/SKILL.md"))
    return out


def _write_tarball(out: Path, sources: list[tuple[Path, str]]) -> int:
    out.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(out, "w:gz") as tar:
        for abs_path, arcname in sources:
            tar.add(abs_path, arcname=arcname)
    print(json.dumps({
        "ok": True,
        "format": "tar.gz",
        "path": str(out),
        "count": len(sources),
        "bytes": out.stat().st_size,
    }, indent=2))
    return 0


def _write_directory(out: Path, sources: list[tuple[Path, str]]) -> int:
    out.mkdir(parents=True, exist_ok=True)
    written: list[str] = []
    for abs_path, arcname in sources:
        target = out / arcname
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(abs_path.read_bytes())
        written.append(arcname)
    print(json.dumps({
        "ok": True,
        "format": "dir",
        "path": str(out),
        "count": len(written),
        "files": written,
    }, indent=2))
    return 0
