"""Regression: the launchpad lens card must expose decisions.jsonl as
a clickable backref row under each paired lens.

The README pledge: "If it can't show its work, it doesn't get to claim
the thought." Every lens claim's `tension_decisions` IDs (e.g. d_001)
must resolve to the source rejection pair (privileged / sacrificed /
verbatim) that justified the claim — visible inline, hover-revealable
in :title, click-expandable via native <details>.
"""
from __future__ import annotations

import json


def test_load_decisions_by_id_reads_jsonl(tmp_path, monkeypatch):
    from trinity_local import launchpad_data
    from trinity_local import state_paths

    me_dir = tmp_path / "me"
    me_dir.mkdir()
    (me_dir / "decisions.jsonl").write_text(
        json.dumps({"id": "d_001", "privileged": "X", "sacrificed": "Y",
                    "valence": "satisfaction", "basin": "b00",
                    "verbatim": "I'd rather ship X than polish Y",
                    "prompt_id": "p_001"}) + "\n"
        + json.dumps({"id": "d_002", "privileged": "A", "sacrificed": "B",
                      "valence": "unresolved", "basin": "b01",
                      "verbatim": "A is more useful here",
                      "prompt_id": "p_002"}) + "\n"
        + "\n"  # blank line — must skip cleanly
        + "{garbage}\n"  # malformed JSON — must skip cleanly
    )
    monkeypatch.setattr(state_paths, "trinity_home", lambda: tmp_path)

    decisions = launchpad_data._load_decisions_by_id()
    assert set(decisions.keys()) == {"d_001", "d_002"}
    assert decisions["d_001"]["privileged"] == "X"
    assert decisions["d_002"]["verbatim"] == "A is more useful here"


def test_load_decisions_by_id_handles_missing_file(tmp_path, monkeypatch):
    from trinity_local import launchpad_data
    from trinity_local import state_paths

    monkeypatch.setattr(state_paths, "trinity_home", lambda: tmp_path)
    # No me/decisions.jsonl exists.
    assert launchpad_data._load_decisions_by_id() == {}


def test_taste_lenses_payload_includes_decisions_by_id():
    """The page_data["tasteLenses"]["decisionsById"] field must exist
    so the Vue template can render the backref row. Live state — uses
    whatever's actually in the user's ~/.trinity/me/decisions.jsonl."""
    from trinity_local.launchpad_data import _load_taste_lenses

    lenses = _load_taste_lenses()
    if lenses is None:
        # Cold install — no taste lenses yet. The field doesn't exist
        # because the payload itself is None. That's fine.
        return
    assert "decisionsById" in lenses, (
        "tasteLenses payload must carry decisionsById so the lens card "
        "can resolve tension_decisions IDs back to source rejection pairs"
    )
    assert isinstance(lenses["decisionsById"], dict)


def test_lens_card_template_renders_justified_by_row():
    """Structural: the launchpad template must include the 'Justified by'
    backref row that surfaces tension_decisions clickably. Catches a
    refactor that removes the backref feature."""
    from trinity_local.launchpad_template import render_launchpad_html
    html = render_launchpad_html(page_data={}, recent_cards="")
    assert "Justified by" in html, (
        "lens card must include the 'Justified by' label so users see "
        "they can drill into each lens claim's source"
    )
    assert "click to see the work" in html, (
        "label should explicitly invite the user to click — the README "
        "pledge is 'if it can't show its work, it doesn't get to claim "
        "the thought'"
    )
    assert "tasteLenses.decisionsById[did]" in html, (
        "template must lookup decisionsById to resolve the verbatim quote"
    )
    assert "<details" in html, (
        "use native <details> for the expand affordance — zero Vue state needed"
    )


def test_lens_card_shows_verbatim_quote_when_decision_present():
    """The expanded details must surface privileged + sacrificed +
    verbatim. The verbatim is the load-bearing field — the user's own
    words from the moment that justified this lens claim."""
    from trinity_local.launchpad_template import render_launchpad_html
    html = render_launchpad_html(page_data={}, recent_cards="")
    assert "tasteLenses.decisionsById[did].privileged" in html
    assert "tasteLenses.decisionsById[did].sacrificed" in html
    assert "tasteLenses.decisionsById[did].verbatim" in html


def test_lens_card_graceful_when_decision_missing():
    """If a tension_decisions ID isn't in decisionsById (lens stale,
    decisions.jsonl trimmed), the chip must still render and surface
    a useful message — not silently disappear."""
    from trinity_local.launchpad_template import render_launchpad_html
    html = render_launchpad_html(page_data={}, recent_cards="")
    assert "not found in decisions.jsonl" in html, (
        "missing decision must produce a visible 'stale lens' hint, "
        "not just an empty chip — same honesty pattern as the n<3 axis "
        "low-confidence suppression"
    )
