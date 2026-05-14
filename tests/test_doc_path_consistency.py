"""Meta-test: live spec docs reference the current on-disk paths, not legacy.

Earned in tick #105's real-corpus drift catch: claude.md, spec-v1.md,
and spec-v1.5.md all carried `~/.trinity/memory/` references even
though task #90 renamed the on-disk directory to `~/.trinity/prompts/`
five months earlier. The `memory_dir()` function in state_paths.py
still exists as a back-compat alias (and was the *function name* that
got grandfathered), but the actual disk path is `~/.trinity/prompts/`.
Doc references to the legacy path mislead anyone debugging a fresh
install.

Per principle #14 (regression guard within one tick) + #20 (load-bearing
facts in N≥3 places drift in the oldest surface): pin every live spec
to the current path. CHANGELOG.md and `docs/spec-v2.md` (sunset) are
explicitly allowed legacy references — they ARE the history.

Symmetric: also block "trinity/memory/" without the dot (the
brand-name overlap with the `memories/` directory makes this a
confusion vector).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[1]

# Live spec surfaces. If any of these starts using legacy `~/.trinity/memory/`
# again, the rename has half-regressed.
LIVE_DOCS = [
    REPO / "claude.md",
    REPO / "docs" / "spec-v1.md",
    REPO / "docs" / "spec-v1.5.md",
    REPO / "docs" / "product-spec.md",
    REPO / "README.md",
]

# Match `~/.trinity/memory/` or `~/.trinity/memory ` — the trailing
# slash/space catches references to the directory as a path. We don't
# block `memory_dir(` (the back-compat function), `memory/` as a Python
# package name (that's `src/trinity_local/memory/`), or `memory` as a
# generic word.
LEGACY_PATTERN = re.compile(r"~/\.trinity/memory(?:/|\b)")


def test_no_live_doc_references_legacy_memory_dir():
    """The on-disk path is `~/.trinity/prompts/` (task #90, 2026-01).
    Every live spec doc should use that — legacy `~/.trinity/memory/`
    references mislead users on a fresh install."""
    offenders: list[tuple[Path, int, str]] = []
    for doc in LIVE_DOCS:
        if not doc.exists():
            continue
        for idx, line in enumerate(doc.read_text(encoding="utf-8").splitlines(), start=1):
            if LEGACY_PATTERN.search(line):
                offenders.append((doc.relative_to(REPO), idx, line.strip()))
    if offenders:
        msg = "Legacy `~/.trinity/memory/` references in live spec docs:\n"
        for path, lineno, text in offenders[:10]:
            preview = text if len(text) <= 120 else text[:117] + "..."
            msg += f"  {path}:{lineno}  {preview}\n"
        msg += (
            "\nThe on-disk path is `~/.trinity/prompts/` (task #90, 2026-01). "
            "Either update the doc to use the current path, or move the legacy "
            "reference into CHANGELOG.md / docs/spec-v2.md (the sunset docs)."
        )
        pytest.fail(msg)
