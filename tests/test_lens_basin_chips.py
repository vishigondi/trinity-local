"""Tick #36 — lens card → topology cross-link via basins_spanned.

Each paired lens carries basins_spanned (list of topology basin ids
the tension lives across). The launchpad lens card now renders these
as chip deep-links to the topology view (?basin=<id>), closing the
forward-arc gap "lens card on the launchpad → link to the prompts
that surfaced it" — by linking to the topology basins instead.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
    (tmp_path / "memories").mkdir(parents=True, exist_ok=True)
    return tmp_path


class TestLensBasinChipTemplate:
    """The Vue template must render basins_spanned as deep-link chips
    when present. v-if guards the row so lenses without basins_spanned
    (legacy data) don't render an empty 'Spans' label."""

    def test_template_renders_basins_spanned_row(self, isolated_home):
        from trinity_local.launchpad_template import render_launchpad_html
        # Minimal page_data with a paired lens that has basins_spanned.
        page_data = _minimal_page_data_with_lens(basins_spanned=["b03", "b05", "b12"])
        html = render_launchpad_html(page_data=page_data, recent_cards="")
        # Vue v-for binds in templates render at runtime — we can only
        # assert the template carries the right loop bindings + URL
        # contract. The runtime side is the browser smoke (Surface 27).
        assert "p.basins_spanned" in html, (
            "template doesn't read p.basins_spanned — chips won't render"
        )
        assert "lens-basin-chip" in html, "lens-basin-chip class missing"
        assert "memory.html?file=topics.json&basin=" in html, (
            "template doesn't construct topics.json ?basin= deep-link — "
            "chips will land on the topology page with no basin focused"
        )
        assert "encodeURIComponent(bid)" in html, (
            "basin id not url-encoded — special chars in basin ids would break the link"
        )

    def test_template_v_if_guards_empty_basins(self, isolated_home):
        from trinity_local.launchpad_template import render_launchpad_html
        page_data = _minimal_page_data_with_lens(basins_spanned=[])
        html = render_launchpad_html(page_data=page_data, recent_cards="")
        # The v-if must check both presence AND length so an empty
        # array doesn't render an orphan "Spans" label.
        assert "p.basins_spanned && p.basins_spanned.length" in html, (
            "v-if guard doesn't check .length — empty basins_spanned "
            "will render an orphan 'Spans' label with no chips"
        )


def _minimal_page_data_with_lens(*, basins_spanned: list[str]) -> dict:
    """page_data shape that build_page_data emits, trimmed to what the
    template's lens card branch consumes."""
    return {
        "enabled": False,
        "endpoint": "",
        "anonymous_id": "",
        "autoChainEnabled": False,
        "polishAutoIterate": False,
        "personalRouting": {},
        "globalRouting": {},
        "tasteLenses": {
            "paired_lenses": [{
                "pole_a": "leading proxy",
                "pole_b": "lagging metric",
                "failure_a": "paranoid",
                "failure_b": "consensus follower",
                "basins_spanned": basins_spanned,
                "tension_decisions": [],
                "dual_evidence": {"pole_a": [], "pole_b": []},
                "verdict": "accepted",
            }],
            "orderings": [],
            "rejections": [],
            "vocabulary": [],
            "abstract_lenses": [],
            "rejections_share_text": "",
            "vocabulary_share_text": "",
            "abstract_lenses_share_text": "",
            "combined_share_text": "",
        },
        "cortexRules": None,
        "councilSuggestions": [],
        "councilQuerySuggestions": [],
        "providerHealth": {"providers": []},
        "activeOperation": None,
        "memoryHealth": {"issues": [], "ok_count": 4, "total_count": 4},
        "memoryHealthDigest": "",
        "ratingsHistory": {"labels": [], "datasets": []},
        "personalRoutingEmptyState": {},
        "modelLineup": [],
        "scoreboard": {},
        "providerNames": {},
        "providerLabels": {},
    }
