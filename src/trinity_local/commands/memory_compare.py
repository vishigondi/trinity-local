"""``trinity-local memory-compare`` — Trinity lens vs Claude Auto-Dream.

Mode 1 (lexical static comparison) wired up to a CLI. See task #142 and
the design doc whimsical-imagining-firefly.md for the measurement
protocol. Modes 2 and 3 (differential eval, cross-fertilize) are
deferred.

Usage:
  trinity-local memory-compare [--claude-project NAME] [--output PATH]
                               [--top-n N] [--json]

Defaults to scanning ~/.claude/projects/ for an Auto-Dream memory tree
matching the current working directory's project. Writes a markdown
report to ~/.trinity/share/memory_compare_<YYYY-MM-DD>.md and prints
the headline to stdout.
"""
from __future__ import annotations

import json
import os
from pathlib import Path


def register(subparsers):
    p = subparsers.add_parser(
        "memory-compare",
        help="Compare Trinity lens vs Claude Auto-Dream (#142, Mode 1)",
    )
    p.add_argument(
        "--claude-project", default=None,
        help="Project name under ~/.claude/projects/ to compare against. Defaults to the auto-detected project for the current directory.",
    )
    p.add_argument(
        "--claude-memory-path", default=None,
        help="Override path to Claude Auto-Dream memory directory (the one containing MEMORY.md). Bypasses --claude-project auto-detection.",
    )
    p.add_argument(
        "--output", default=None,
        help="Path for the markdown report. Defaults to ~/.trinity/share/memory_compare_<date>.md.",
    )
    p.add_argument(
        "--top-n", type=int, default=5,
        help="How many top-N gaps to surface per side (default 5).",
    )
    p.add_argument(
        "--json", action="store_true",
        help="Emit the full ComparisonReport as JSON to stdout instead of writing a markdown report.",
    )
    p.set_defaults(handler=handle_memory_compare)


def handle_memory_compare(args) -> int:
    from ..memory_compare import compare_memories
    from ..state_paths import share_dir

    claude_root = _resolve_claude_root(args)
    report = compare_memories(
        trinity_lens_text=None,
        claude_memory_root=claude_root,
        top_n=args.top_n,
    )

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
        return 0

    print(report.headline())
    print()
    if claude_root is None:
        print(
            "(Auto-Dream memory directory not found. Pass "
            "--claude-memory-path or --claude-project to specify one.)"
        )
        return 0

    md = _render_markdown(report, claude_root)
    output_path = _resolve_output_path(args, share_dir())
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(md, encoding="utf-8")
    print(f"Wrote {output_path}")
    return 0


def _resolve_claude_root(args) -> Path | None:
    """Find the Auto-Dream memory directory based on CLI args + cwd.

    Precedence:
    1. --claude-memory-path (explicit override)
    2. --claude-project NAME → ~/.claude/projects/NAME/memory/
    3. Auto-detect: convert cwd to Claude's project-key encoding
       (replace / with -) → ~/.claude/projects/<encoded>/memory/
    4. Return None when nothing resolves — caller surfaces a hint.
    """
    if args.claude_memory_path:
        p = Path(args.claude_memory_path).expanduser()
        return p if p.exists() else None
    base = Path.home() / ".claude" / "projects"
    if args.claude_project:
        candidate = base / args.claude_project / "memory"
        return candidate if candidate.exists() else None
    # Claude Code's project-key encoding for `~/.claude/projects/<key>`
    # is just `str(path).replace("/", "-")`. An absolute path like
    # `/Users/foo/x` already starts with `/`, so the encoding yields
    # `-Users-foo-x` — ONE leading dash, not two. The previous
    # implementation prepended `-` unconditionally, producing
    # `--Users-foo-x` and failing to find any real project dir.
    cwd = Path(os.getcwd()).resolve()
    encoded = str(cwd).replace("/", "-")
    candidate = base / encoded / "memory"
    if candidate.exists():
        return candidate
    return None


def _resolve_output_path(args, share_root: Path) -> Path:
    if args.output:
        return Path(args.output).expanduser()
    from datetime import datetime, timezone
    date_stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return share_root / f"memory_compare_{date_stamp}.md"


def _render_markdown(report, claude_root: Path) -> str:
    """Produce the human-readable Mode 1 report."""
    from datetime import datetime, timezone

    now = datetime.now(timezone.utc).replace(microsecond=0)
    lines: list[str] = [
        "# Memory comparison — Trinity lens ↔ Claude Auto-Dream",
        "",
        f"_Generated {now.isoformat()}_",
        f"_Auto-Dream source: `{claude_root}`_",
        "",
        "## Headline",
        "",
        f"> {report.headline()}",
        "",
        "## Coverage",
        "",
        f"- Trinity (`lens.md`): **{report.trinity_count}** principles",
        f"- Claude Auto-Dream: **{report.claude_count}** principles",
        f"- Overlap (token Jaccard ≥ 0.4): **{report.overlap_count}** matched",
        f"- Union-Jaccard: **{round(report.jaccard, 3)}**",
        "",
        "## Specificity",
        "",
        "| System | Mean chars | Median chars | Mean words |",
        "|---|---|---|---|",
    ]
    ts = report.trinity_specificity
    cs = report.claude_specificity
    lines.append(
        f"| Trinity | {ts['mean_chars']} | {ts['median_chars']} | {ts['mean_words']} |"
    )
    lines.append(
        f"| Claude | {cs['mean_chars']} | {cs['median_chars']} | {cs['mean_words']} |"
    )
    lines.append("")
    lines.append(
        "_Higher char count typically means more concrete/observational; "
        "lower means more abstract/structural. Neither is \"better\" — they "
        "encode different layers of taste._"
    )
    lines.append("")

    if report.shared_examples:
        lines.append("## Shared (top overlaps)")
        lines.append("")
        for t_text, c_text in report.shared_examples:
            lines.append(f"- **Trinity:** {t_text}")
            lines.append(f"  **Claude:**  {c_text}")
            lines.append("")

    if report.trinity_only:
        lines.append("## Trinity-only (Claude might be missing)")
        lines.append("")
        for c in report.trinity_only:
            lines.append(f"- {c}")
        lines.append("")

    if report.claude_only:
        lines.append("## Claude-only (Trinity might be missing)")
        lines.append("")
        for c in report.claude_only:
            lines.append(f"- {c}")
        lines.append("")

    lines.append("---")
    lines.append("")
    # The report lives at ~/.trinity/share/ — relative paths into the
    # repo don't resolve. Use the absolute GitHub URL so the link works
    # from anywhere the user opens the markdown.
    lines.append(
        "_Mode 1 lexical comparison only. Modes 2 (differential eval) and "
        "3 (cross-fertilize injection test) are deferred — see "
        "[plan](https://github.com/vishigondi/trinity-local/tree/main/docs/historical/) "
        "for the full measurement protocol._"
    )
    return "\n".join(lines) + "\n"
