"""Unit tests for memory_viewer's HTML rendering surface.

The viewer renders client-side from inlined JSON, so most behavior is
covered by Surface 14a/14b/16/17 in the browser smoke. These unit
tests guard the *template strings* themselves — a renamed CLI command
or a dropped CSS class would otherwise only surface in the browser
gate, which can be slow to attribute.

Same shape as test_memory_health.py: per-feature class, each test names
the contract being defended.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
    (tmp_path / "memories").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _render():
    from trinity_local.memory_viewer import render_memory_viewer_html
    return render_memory_viewer_html()


class TestPickVetoChip:
    """Tick #26 — one-click veto from the picks Reader. The chip
    template lives client-side in renderPicksReader; if the CLI name
    changes or the chip class is dropped, the JS template silently
    breaks the action arc."""

    def test_pick_veto_class_present(self, isolated_home):
        html = _render()
        # CSS class must be defined (otherwise the chip renders unstyled)
        assert ".pick-veto" in html, ".pick-veto CSS class missing — chip will be unstyled"
        # JS must construct the button with that class
        assert '"pick-veto"' in html, "renderPicksReader doesn't construct a .pick-veto button"

    def test_pick_veto_copies_cortex_override(self, isolated_home):
        html = _render()
        # The chip's clipboard payload is the cortex-override CLI. If
        # the CLI is renamed, this guard catches the JS template drift
        # before Surface 17 in the browser run does.
        assert "trinity-local cortex-override --basin " in html, (
            "pick-veto chip no longer copies cortex-override — template drift"
        )

    def test_pick_actions_wrapper_present(self, isolated_home):
        html = _render()
        # The xlink + veto sit in a .pick-actions flex row. Without
        # the wrapper they'd stack vertically and break the visual
        # contract documented in DESIGN.md.
        assert ".pick-actions" in html, ".pick-actions wrapper class missing"
        assert '"pick-actions"' in html, "renderPicksReader doesn't create the .pick-actions row"


class TestViewerRebuildChip:
    """Tick #27 — persistent rebuild chip in viewer header. Always-on
    counterpart to the staleness chip — fires per-file even when
    _memory_health() reports no issues. The CSS class + per-file
    CLI mapping are template strings that drift silently if
    suggestionFor() is edited without updating the chip wiring."""

    def test_rebuild_chip_class_defined(self, isolated_home):
        html = _render()
        # Both CSS rule and JS construction must reference the class.
        assert ".viewer-rebuild-chip" in html, ".viewer-rebuild-chip CSS missing"
        assert '"viewer-rebuild-chip"' in html, (
            "renderHeader doesn't construct a .viewer-rebuild-chip button"
        )

    def test_rebuild_command_template_uses_suggestion_helper(self, isolated_home):
        html = _render()
        # The chip text is built as "trinity-local " + suggestionFor(file.name).
        # We verify the prefix template AND the helper exists with the
        # expected per-file mapping (one assertion per memory keeps the
        # guard granular).
        assert '"trinity-local " + suggestionFor(file.name)' in html, (
            "rebuild chip no longer threads suggestionFor() — per-file mapping broken"
        )
        # suggestionFor itself must keep the canonical CLI names. If a
        # CLI is renamed, both this guard and Surface 18 catch it.
        for marker in (
            '"lens.md" || name === "topics.json") return "lens-build"',
            '"picks.json") return "consolidate"',
            '"core.md") return "distill"',
        ):
            assert marker in html, f"suggestionFor mapping drifted: {marker}"

    def test_chip_lives_in_header(self, isolated_home):
        html = _render()
        # Sanity check the chip is wired inside renderHeader (so it shows
        # for every file), not inside a single Reader. If it slips into
        # one Reader, the markdown views (lens.md, core.md) lose it.
        header_idx = html.find("function renderHeader(file)")
        chip_idx = html.find('"viewer-rebuild-chip"')
        assert header_idx > 0 and chip_idx > header_idx, (
            "viewer-rebuild-chip is not constructed inside renderHeader — "
            "markdown views won't render it"
        )


class TestPicksReaderCrossLinks:
    """Picks Reader → routing Reader cross-link (tick #10/16 shipped this).
    Guards the click-through path that closes 'see the pick → see the
    evidence the pick was built on'."""

    def test_routing_xlink_template_present(self, isolated_home):
        html = _render()
        # Each pick card has a "View routing scores →" cross-link that
        # carries the basinId into routing.json's task-focus deep link.
        assert "View routing scores" in html, "picks card lost the routing cross-link"
        assert "memory.html?file=routing.json&task=" in html, (
            "routing xlink template drifted from ?task= deep-link contract"
        )

    def test_pick_xlink_class_styled(self, isolated_home):
        html = _render()
        assert ".pick-xlink" in html, "pick-xlink CSS missing"
