"""Minimal YAML frontmatter parser tailored to SKILL.md.

Why custom instead of PyYAML: Trinity's runtime-deps invariant is 3
(Pillow, mcp, numpy). Adding PyYAML for a single subset of YAML the
spec exercises is the wrong tradeoff. The SKILL.md frontmatter shape
is tractable:

  - key: scalar              # string / int / float / bool / null
  - key: "quoted string"     # double or single quoted
  - key: [a, b, c]           # inline list (strings only)
  - key:                     # block list:
      - first
      - second
  - key: |                   # multiline block scalar (literal)
      first line
      second line

Edge cases this parser does NOT handle (deliberately — SKILL.md
frontmatter doesn't exercise them):
  - YAML anchors (&foo / *foo)
  - Folded block scalars (>)
  - Nested dicts beyond one level deep
  - Numeric strings (everything that LOOKS like an int gets parsed as int)
  - Comments inside the frontmatter

If a future Trinity surface needs more, swap this for PyYAML — the
public surface is just load_frontmatter() + dump_frontmatter().
"""
from __future__ import annotations

import re
from typing import Any


def split_document(text: str) -> tuple[str | None, str]:
    """Split a SKILL.md-like document into (frontmatter_text, body).

    Returns (None, full_text) when there's no frontmatter. The
    frontmatter, when present, is the content between the leading
    `---\\n` and the next `\\n---\\n` — without the delimiters.
    """
    if not text.startswith("---\n"):
        return None, text
    end = text.find("\n---\n", 4)
    if end < 0:
        # Trailing delimiter at EOF (no body) is also valid
        if text.endswith("\n---"):
            return text[4:-4], ""
        # No closing delimiter — treat as bodyless
        return None, text
    frontmatter = text[4:end]
    body = text[end + 5:]
    return frontmatter, body


def _parse_scalar(token: str) -> Any:
    """Parse a YAML scalar — string / int / float / bool / null.

    Quoted strings keep their quotes stripped. Bare strings stay as
    strings unless they parse cleanly as int/float/bool/null.
    """
    s = token.strip()
    if not s:
        return None
    # null
    if s in ("null", "~"):
        return None
    # bool
    if s == "true":
        return True
    if s == "false":
        return False
    # quoted string
    if (s.startswith('"') and s.endswith('"')) or (s.startswith("'") and s.endswith("'")):
        return s[1:-1]
    # int
    try:
        return int(s)
    except ValueError:
        pass
    # float
    try:
        return float(s)
    except ValueError:
        pass
    # bare string
    return s


def _parse_inline_list(s: str) -> list[Any]:
    """Parse [a, b, "c d", 5] — inline list of scalars."""
    s = s.strip()
    if not (s.startswith("[") and s.endswith("]")):
        raise ValueError(f"not an inline list: {s!r}")
    inner = s[1:-1].strip()
    if not inner:
        return []
    items: list[Any] = []
    # Simple comma-split that respects quoted strings
    buf = ""
    in_quote: str | None = None
    for ch in inner:
        if in_quote:
            buf += ch
            if ch == in_quote:
                in_quote = None
        elif ch in ('"', "'"):
            buf += ch
            in_quote = ch
        elif ch == "," and not in_quote:
            items.append(_parse_scalar(buf))
            buf = ""
        else:
            buf += ch
    if buf.strip():
        items.append(_parse_scalar(buf))
    return items


def load_frontmatter(text: str) -> dict[str, Any]:
    """Parse SKILL.md-style YAML frontmatter into a dict.

    Tolerant: unknown line shapes are skipped (with the lossy choice
    documented in the parser comments). For SKILL.md the inputs are
    constrained enough that this hasn't bitten in practice.

    Multiline block scalars (|) are gathered until indentation drops
    back to the parent level. Inline lists ([a, b]) and block lists
    (`-`-prefixed) both yield Python lists.
    """
    lines = text.splitlines()
    out: dict[str, Any] = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        # Skip blank lines + comments
        if not line.strip() or line.lstrip().startswith("#"):
            i += 1
            continue
        # Top-level key:value
        m = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$", line)
        if not m:
            i += 1
            continue
        key, value = m.group(1), m.group(2).strip()
        # Multiline block scalar
        if value == "|":
            body_lines: list[str] = []
            i += 1
            # Determine indent from the first body line
            indent = None
            while i < len(lines):
                ln = lines[i]
                if not ln.strip():
                    # Blank lines inside the block are kept (without indent)
                    body_lines.append("")
                    i += 1
                    continue
                cur_indent = len(ln) - len(ln.lstrip())
                if indent is None:
                    indent = cur_indent
                if cur_indent < indent:
                    break
                body_lines.append(ln[indent:])
                i += 1
            # Strip trailing blank lines for a clean payload
            while body_lines and not body_lines[-1]:
                body_lines.pop()
            out[key] = "\n".join(body_lines)
            continue
        # Block list: `key:` (empty) then `- item` lines
        if value == "":
            # Peek ahead for `- ` lines
            items: list[Any] = []
            j = i + 1
            while j < len(lines):
                ln = lines[j]
                if not ln.strip():
                    j += 1
                    continue
                lm = re.match(r"^(\s+)-\s+(.*)$", ln)
                if not lm:
                    break
                items.append(_parse_scalar(lm.group(2)))
                j += 1
            if items:
                out[key] = items
                i = j
                continue
            # Empty value, no list — store as None
            out[key] = None
            i += 1
            continue
        # Inline list
        if value.startswith("["):
            out[key] = _parse_inline_list(value)
            i += 1
            continue
        # Scalar
        out[key] = _parse_scalar(value)
        i += 1
    return out


def _dump_scalar(value: Any) -> str:
    """Serialize a Python scalar back to YAML."""
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    s = str(value)
    # Quote strings that could be misread as scalars or contain special chars.
    if (
        s in ("null", "true", "false", "~", "")
        or s.lstrip("-").replace(".", "", 1).isdigit()
        or any(ch in s for ch in ":#[]{},&*!|>'\"%@`")
        or s != s.strip()
    ):
        # Quote and escape embedded double quotes
        return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return s


def _dump_list(items: list[Any]) -> str:
    """Serialize a list inline ([a, b, c])."""
    return "[" + ", ".join(_dump_scalar(x) for x in items) + "]"


def _dump_multiline(value: str) -> list[str]:
    """Serialize a multiline string as a `|` block scalar."""
    lines = value.split("\n")
    return ["|"] + [f"  {ln}" for ln in lines]


def dump_frontmatter(data: dict[str, Any]) -> str:
    """Serialize a dict back to YAML frontmatter (NO --- delimiters).

    Round-trips load_frontmatter() output for the SKILL.md subset.
    Preserves key order — callers should pass an ordered dict if order
    matters (Python 3.7+ guarantees dict iteration order).
    """
    out: list[str] = []
    for key, value in data.items():
        if isinstance(value, str) and "\n" in value:
            out.append(f"{key}: |")
            out.extend(f"  {ln}" for ln in value.split("\n"))
        elif isinstance(value, list):
            out.append(f"{key}: {_dump_list(value)}")
        elif isinstance(value, dict):
            # One level of nesting: emit as block-style
            out.append(f"{key}:")
            for nk, nv in value.items():
                if isinstance(nv, list):
                    out.append(f"  {nk}: {_dump_list(nv)}")
                else:
                    out.append(f"  {nk}: {_dump_scalar(nv)}")
        else:
            out.append(f"{key}: {_dump_scalar(value)}")
    return "\n".join(out)


def assemble_document(frontmatter: dict[str, Any], body: str) -> str:
    """Compose `---\\nfrontmatter\\n---\\nbody` for write-back to disk."""
    return f"---\n{dump_frontmatter(frontmatter)}\n---\n{body}"
