"""Parse Claude Auto-Dream MEMORY.md + topic files into Claim list.

Auto-Dream emits plain markdown (no JSON schema). MEMORY.md is the
project-scoped index, capped ~200 lines per claudefa.st mechanics doc.
Topic files (debugging.md, conventions.md, etc.) are linked from
MEMORY.md and contain longer prose with optional YAML frontmatter
carrying ``description:`` — the curated one-line summary.

Two claim sources extracted:
1. MEMORY.md bullet line text after the em-dash "—" (the one-line
   hook per entry, the highest-signal short summary).
2. Each linked topic file's frontmatter ``description`` field when
   present. Falls back to the first non-blank body line otherwise.

Topic file body paragraphs are deliberately NOT extracted as separate
claims — they're prose, too long for Jaccard, and double-count what
the description already captures.
"""
from __future__ import annotations

import re
from pathlib import Path

# MEMORY.md bullet format: `- [Title](file.md) — one-line description`
# OR plain bullet: `- one-line claim text`
_BULLET_LINKED = re.compile(
    r"^-\s+\[(?P<title>[^\]]+)\]\((?P<file>[^)]+)\)\s+[—-]\s+(?P<desc>.+?)\s*$",
    re.MULTILINE,
)
_BULLET_PLAIN = re.compile(r"^-\s+(?P<text>.+?)\s*$", re.MULTILINE)

# YAML frontmatter — capture between leading `---` markers.
_FRONTMATTER = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.DOTALL)
_FRONTMATTER_DESC = re.compile(
    r"^description:\s*(.+?)\s*$", re.MULTILINE,
)


def parse_claude_memory(memory_root: Path) -> list[str]:
    """Extract a flat list of claim strings from an Auto-Dream tree.

    ``memory_root`` points at the directory containing MEMORY.md (e.g.
    ``~/.claude/projects/<project>/memory/``). Returns one string per
    claim — MEMORY.md descriptions first, then unique topic-file
    descriptions that didn't already appear in MEMORY.md.

    Returns an empty list when MEMORY.md doesn't exist. Robust to
    missing or malformed topic files — skips them silently rather than
    crashing the comparison.
    """
    memory_md = memory_root / "MEMORY.md"
    if not memory_md.exists():
        return []
    try:
        text = memory_md.read_text(encoding="utf-8")
    except OSError:
        return []

    claims: list[str] = []
    seen: set[str] = set()
    topic_paths: list[Path] = []

    for m in _BULLET_LINKED.finditer(text):
        desc = m.group("desc").strip()
        if desc:
            norm = desc.lower()
            if norm not in seen:
                claims.append(desc)
                seen.add(norm)
        file = m.group("file").strip()
        topic_path = memory_root / file
        if topic_path.exists():
            topic_paths.append(topic_path)

    # Plain bullets (no link) — only catch lines not already matched
    # by _BULLET_LINKED. We track matched spans by checking whether the
    # plain-bullet text starts with `[` (which means linked-format).
    for m in _BULLET_PLAIN.finditer(text):
        raw = m.group("text").strip()
        if raw.startswith("["):
            continue  # already captured by _BULLET_LINKED
        norm = raw.lower()
        if norm not in seen:
            claims.append(raw)
            seen.add(norm)

    for path in topic_paths:
        desc = _extract_topic_description(path)
        if desc:
            norm = desc.lower()
            if norm not in seen:
                claims.append(desc)
                seen.add(norm)

    return claims


def _extract_topic_description(path: Path) -> str:
    """Return the frontmatter ``description`` field, or first body line."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""

    fm_match = _FRONTMATTER.match(text)
    if fm_match:
        fm = fm_match.group(1)
        desc_match = _FRONTMATTER_DESC.search(fm)
        if desc_match:
            return desc_match.group(1).strip().strip('"').strip("'")
        body_start = fm_match.end()
        body = text[body_start:]
    else:
        body = text

    for line in body.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            return stripped
    return ""
