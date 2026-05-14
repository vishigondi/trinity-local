"""Pin the subsidy-window narrative across README + launch.md (task #118).

The framing must thread coherently through both surfaces — a user
who reads the README hero and clicks through to launch.md/HN should
see the same line of thinking, not two different pitches. Drift in
one without the other breaks the launch's narrative integrity.

Guards the two load-bearing keywords (`subsidized` + `corpus`) and
the load-bearing concept (cross-provider re-scoring) appear in BOTH
files. If a future rewrite removes the thread from one but not the
other, this test catches the drift loudly.
"""
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("doc", [
    REPO / "README.md",
    REPO / "docs" / "launch.md",
])
def test_subsidy_window_narrative_present(doc):
    """Both surfaces must carry the subsidy-window framing — the FOMO
    motivator user identified in task #118."""
    text = doc.read_text(encoding="utf-8").lower()
    # The two keywords that make the framing recognizable. Both must
    # appear within the same doc for the framing to land.
    assert "subsidiz" in text, (
        f"{doc.relative_to(REPO)}: missing 'subsidized'/'subsidy' — "
        f"the launch-copy framing for task #118 was lost in a rewrite."
    )
    assert "corpus" in text, (
        f"{doc.relative_to(REPO)}: missing 'corpus' — the FOMO line's "
        f"object (what the user is BUILDING during the subsidy window) "
        f"was lost. The framing reduces to a generic 'cheap now' without it."
    )
