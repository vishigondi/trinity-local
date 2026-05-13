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


class TestTopicLaunchChip:
    """Tick #28 — launch-council chip on topic graph node detail panels.
    Closes the topology action arc per the forward arc bullet 'click
    a basin → launch a council on this topic'."""

    def test_launch_chip_class_defined(self, isolated_home):
        html = _render()
        assert ".topics-launch-chip" in html, ".topics-launch-chip CSS missing"
        assert '"topics-launch-chip"' in html, (
            "showDetail doesn't construct a .topics-launch-chip button"
        )

    def test_launch_chip_uses_council_launch_cli(self, isolated_home):
        html = _render()
        # If the CLI is renamed (council-launch → run_council or similar),
        # the chip silently copies a broken command.
        assert "'trinity-local council-launch --task \"'" in html, (
            "launch chip no longer copies trinity-local council-launch --task — template drift"
        )

    def test_launch_chip_escapes_shell_metas(self, isolated_home):
        html = _render()
        # The escape chain must handle backslash + dquote + backtick +
        # dollar — anything less can break a bash paste with user
        # prompts that contain code-fence or variable expansion.
        # We check the regex literals are present in the rendered JS.
        # Each replace produces JS source `/<x>/g` after Python escape.
        assert ".replace(/\\\\/g," in html, "missing backslash escape"
        assert '.replace(/"/g,' in html, "missing double-quote escape"
        assert ".replace(/`/g," in html, "missing backtick escape"
        assert ".replace(/\\$/g," in html, "missing dollar escape"


class TestRepReplayChip:
    """Tick #29 — per-representative replay chip. Finer-grained than the
    basin-level launch chip (uses any rep's headline as the seed, not
    just the closest-to-centroid). The escape logic is now shared via
    escapeBashArg — DRY guard ensures the basin chip and rep chip stay
    in sync as the escape rules evolve."""

    def test_replay_chip_class_defined(self, isolated_home):
        html = _render()
        assert ".topics-rep-replay" in html, ".topics-rep-replay CSS missing"
        assert '"topics-rep-replay"' in html, (
            "renderThreadRep doesn't construct a .topics-rep-replay button"
        )

    def test_replay_chip_stops_propagation(self, isolated_home):
        html = _render()
        # Without stopPropagation, clicking the chip would also toggle the
        # surrounding li's expand state — bad UX, especially on multi-turn
        # threads. Guard the wiring.
        assert "event.stopPropagation()" in html, (
            "rep replay chip click handler missing stopPropagation — "
            "expand toggle will fire when the user only meant to copy"
        )

    def test_replay_chip_uses_shared_escape_helper(self, isolated_home):
        html = _render()
        # The basin chip + rep chip both wrap the seed in escapeBashArg
        # so they share one source of truth for shell metacharacter
        # escaping. If a refactor breaks this, the chips can drift on
        # whether `$` gets escaped or not — silently breaking one path.
        assert "function escapeBashArg" in html, "shared escapeBashArg helper missing"
        assert "escapeBashArg(seedText)" in html, (
            "basin-level launch chip no longer threads escapeBashArg — DRY broken"
        )
        assert "escapeBashArg(replaySeed)" in html, (
            "per-rep replay chip no longer threads escapeBashArg"
        )


class TestTopicToPickCrossLink:
    """Tick #30 — topology → picks cross-link. picks.json `.basin_id` is
    actually the task_type label (schema-naming quirk), so this bridge
    matches via cosine similarity between `pick.basin_centroid` and each
    topology basin's `centroid`. Closes the forward-arc cross-memory
    navigation gap 'see a basin, jump to its pick'."""

    def test_pick_xlink_class_defined(self, isolated_home):
        html = _render()
        assert ".topics-pick-xlink" in html, ".topics-pick-xlink CSS missing"
        assert '"topics-pick-xlink"' in html, (
            "showDetail doesn't construct a .topics-pick-xlink anchor"
        )

    def test_reverse_map_uses_centroid_cosine(self, isolated_home):
        html = _render()
        # The bridge MUST match by centroid, not by pick.basin_id —
        # picks.basin_id is the task_type label, not the topology id.
        # If a future refactor drops centroid matching, picks will
        # orphan from topology again.
        assert "basinToPickTask" in html, "basin→pick map missing"
        assert "pick.basin_centroid" in html, (
            "reverse map no longer reads pick.basin_centroid — centroid "
            "matching is the only way to bridge picks → topology since "
            "pick.basin_id is the task_type label not the topology id"
        )
        # Threshold is a magic number — guard that some threshold is
        # being applied (without it the closest basin wins even when
        # similarity is near zero, producing nonsense links).
        assert "SIM_THRESHOLD" in html, (
            "no similarity threshold gate — every pick will link to its "
            "argmax basin regardless of how unrelated they are"
        )

    def test_xlink_targets_picks_reader_with_task_param(self, isolated_home):
        html = _render()
        # Link must go to picks.json viewer with the ?task= deep-link
        # so the picks Reader scrolls to + highlights the right card.
        assert 'memory.html?file=picks.json&task=" + encodeURIComponent(pickTask)' in html, (
            "topic→pick xlink doesn't target the picks Reader's ?task= deep-link"
        )

    def test_malformed_picks_doesnt_crash_topology(self, isolated_home):
        # The try/except around JSON.parse is load-bearing — without it,
        # a corrupt picks.json would take down the topology view entirely.
        html = _render()
        assert "JSON.parse(picksRaw)" in html, "picks parse step missing"
        assert "catch (_)" in html, "missing graceful-degradation try/catch around picks parse"


class TestPickBasinNodeStyling:
    """Tick #31 — visual marker on topology basin nodes that have
    crystallized into routing rules. Complements the in-panel chip
    from tick #30 so the user sees the routing-rule basins at a
    glance without having to click each node."""

    def test_pick_basin_class_defined(self, isolated_home):
        html = _render()
        # CSS rule with both .node.pick-basin and a hover variant — the
        # styling must layer on top of the existing .node base so the
        # circle fill (hsl gradient) still reads.
        assert ".topics-graph-svg .node.pick-basin" in html, (
            "pick-basin CSS rule missing — pick-bearing nodes won't visually differ"
        )
        assert ".topics-graph-svg .node.pick-basin:hover" in html, (
            "pick-basin :hover variant missing — hover state will fall back to base"
        )

    def test_node_class_keyed_on_pick_map(self, isolated_home):
        html = _render()
        # The node-class lookup must read from basinToPickTask (the
        # centroid-matched map built tick #30) — if it reads from
        # any other source (e.g. matching basin.id to pick-key
        # directly) the visual encoding will silently mis-mark nodes.
        assert "basinToPickTask.has(d.id)" in html, (
            "node class lookup doesn't query basinToPickTask — visual marker "
            "will drift from the in-panel chip"
        )

    def test_tooltip_surfaces_routing_rule(self, isolated_home):
        html = _render()
        # The native SVG <title> tooltip should surface the routing rule
        # on hover for pick-bearing basins — passive discovery without
        # having to click the node.
        assert "basinToPickTask.get(d.id)" in html, "tooltip doesn't read the pick map"
        assert "Routing rule:" in html, "tooltip text drift — missing routing-rule label"


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
