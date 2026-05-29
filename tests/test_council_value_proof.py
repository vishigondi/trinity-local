"""#236: surface the council value proof from the existing council_outcomes/.

The council-first painkiller in one stat: how often the chairman picked a
DIFFERENT model than the user's default (i.e. how often a single-provider
habit would have shipped the worse answer), plus the per-lab win split.
No new eval, no model calls — pure aggregation over the outcomes ledger.

These guard the math + the confidence threshold + the load-boundary provider
canonicalization (web-capture brand names fold into the canonical slugs), and
that the launchpad/status surfaces self-hide on a thin ledger.
"""
from __future__ import annotations

import trinity_local.personal_routing as pr


def _records(*triples):
    # (chairman_winner, primary_provider) pairs → scan-record dicts.
    return [
        {"chairman_winner": w, "winner_provider": w, "primary_provider": p}
        for w, p in triples
    ]


def test_changed_pick_and_split(monkeypatch):
    # 3 of 4 councils picked a non-default model; default is always claude.
    recs = _records(
        ("codex", "claude"),
        ("antigravity", "claude"),
        ("claude", "claude"),       # default won — NOT a changed pick
        ("codex", "claude"),
    ) * 5  # 20 councils, clears the n>=10 threshold
    monkeypatch.setattr(pr, "_scan_outcomes", lambda: (recs, True))
    vp = pr.council_value_proof()
    assert vp["ready"] is True
    assert vp["n"] == 20
    assert vp["comparable"] == 20
    # 3 of every 4 changed → 75%
    assert vp["changed_pct"] == 75
    # codex 10/20=50%, claude 5/20=25%, antigravity 5/20=25%
    assert vp["win_split"]["codex"]["pct"] == 50
    assert vp["win_split"]["claude"]["count"] == 5


def test_thin_ledger_not_ready(monkeypatch):
    monkeypatch.setattr(pr, "_scan_outcomes", lambda: (_records(("codex", "claude")), True))
    vp = pr.council_value_proof()
    assert vp["ready"] is False
    assert vp["n"] == 1


def test_provider_names_canonicalized_at_boundary(monkeypatch):
    # Web-capture brand names must fold into the canonical slugs so the split
    # is per-LAB, not chatgpt-vs-codex double-counted (the v1.7.62 bug class).
    recs = _records(
        ("chatgpt", "claude"),     # → codex
        ("gpt", "claude"),         # → codex
        ("claude_ai", "codex"),    # winner→claude, default→codex (changed)
        ("gemini", "claude"),      # → antigravity
    ) * 5
    monkeypatch.setattr(pr, "_scan_outcomes", lambda: (recs, True))
    vp = pr.council_value_proof()
    assert set(vp["win_split"]) <= {"codex", "claude", "antigravity"}, (
        "brand names must canonicalize; got " + repr(list(vp["win_split"]))
    )
    assert vp["win_split"]["codex"]["count"] == 10  # chatgpt + gpt


def test_launchpad_helper_brands_and_hides(monkeypatch):
    from trinity_local import launchpad_data as ld

    # Ready → brand-mapped wins.
    recs = _records(("codex", "claude"), ("claude", "claude")) * 6
    monkeypatch.setattr(pr, "_scan_outcomes", lambda: (recs, True))
    card = ld._council_value_for_launchpad()
    assert card is not None
    labels = [w["label"] for w in card["wins"]]
    assert "GPT" in labels and "Claude" in labels
    assert "codex" not in labels  # slugs never leak to the UI

    # Thin ledger → None so the card self-hides.
    monkeypatch.setattr(pr, "_scan_outcomes", lambda: ([], True))
    assert ld._council_value_for_launchpad() is None
