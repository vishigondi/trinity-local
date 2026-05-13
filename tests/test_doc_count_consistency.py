"""Meta-test: load-bearing counts stay in sync across docs.

Principle #20 (duplicated facts drift in the oldest surface)
formalized in tick #89. The pattern surfaced 3× this session — each
time a numeric claim was correct in some surfaces and stale in
others (a stale claim in the OLDEST surface, specifically). The
fix shape: enforce that every place a count is pinned agrees with
every other place, so future-me catches the drift at test time
instead of grep time.

This guard scans the three known duplicate surfaces for the test
count and the smoke-surface count, and asserts they agree
internally. Doesn't enforce a SPECIFIC value — that would require
running pytest first to know what number to expect. Internal
consistency is the regression target; "all stale together" is still
a green test, but a tick that bumps one number without bumping the
others fails loudly.

Per principle #14 (every shipped feature gets a smoke regression
guard within one tick): tick #89 shipped the principle; this ticks
the guard.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[1]
CLAUDE_MD = REPO / "claude.md"
PRODUCT_SPEC = REPO / "docs" / "product-spec.md"


def _extract(path: Path, pattern: str) -> str | None:
    """Return the first regex group match in `path`, or None if not found."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(pattern, text)
    return m.group(1) if m else None


class TestTestCountConsistency:
    """Three known surfaces pin the pytest count. They must agree."""

    def test_three_surfaces_agree(self):
        # Surface A: claude.md Status block — "N tests passing"
        status_count = _extract(
            CLAUDE_MD,
            r"(\d+) tests passing",
        )
        # Surface B: claude.md Verified status — "pytest -q — **N passed**"
        verified_count = _extract(
            CLAUDE_MD,
            r"pytest -q.{0,5}\*\*(\d+) passed\*\*",
        )
        # Surface C: docs/product-spec.md item 11 — "Test suite: N passing"
        spec_count = _extract(
            PRODUCT_SPEC,
            r"Test suite:\s*(\d+) passing",
        )

        # All three must be present (locating-the-marker is itself a guard
        # against someone re-titling a section and breaking the pin point).
        assert status_count, "claude.md Status block lost the 'N tests passing' marker"
        assert verified_count, "claude.md Verified status lost the 'pytest -q — **N passed**' marker"
        assert spec_count, "product-spec.md item 11 lost the 'Test suite: N passing' marker"

        # All three numbers must agree.
        counts = {
            "claude.md status": status_count,
            "claude.md verified": verified_count,
            "product-spec item 11": spec_count,
        }
        unique = set(counts.values())
        assert len(unique) == 1, (
            f"Test count drifted across surfaces: {counts}. "
            f"Principle #20: when you bump the test count, bump it in "
            f"ALL three places in the same commit. Single-source-of-truth "
            f"would be cleaner long-term."
        )


class TestSmokeSurfaceCountConsistency:
    """The smoke-surface count claim appears in claude.md status + the
    product-spec. Same shape; same regression guard."""

    def test_two_surfaces_agree(self):
        status_count = _extract(
            CLAUDE_MD,
            r"(\d+)-surface browser smoke",
        )
        spec_count = _extract(
            PRODUCT_SPEC,
            r"(\d+)-surface browser smoke",
        )
        assert status_count, "claude.md Status block lost the 'N-surface browser smoke' marker"
        assert spec_count, "product-spec.md lost the 'N-surface browser smoke' marker"
        assert status_count == spec_count, (
            f"Smoke-surface count drift: claude.md says {status_count}, "
            f"product-spec says {spec_count}. Per principle #20, pin both "
            f"in the same commit."
        )
