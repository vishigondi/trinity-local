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
        # The chip's CLI payload is the cortex-override invocation. If
        # the CLI is renamed, this guard catches the JS template drift
        # before Surface 17 in the browser run does.
        assert "trinity-local cortex-override --basin " in html, (
            "pick-veto chip no longer references cortex-override — template drift"
        )

    def test_pick_veto_gives_visible_click_feedback(self, isolated_home):
        """100-persona audit P63: the veto chip used to copy silently
        — clicked, copied, no visible feedback. Pass B (commit 0555a25)
        retired the macOS Shortcut dispatch path; memory.html renders
        via file:// and can't reach the Chrome extension's Native
        Messaging host directly, so clipboard + paste is the safe path.
        The chip text must flip on click so the user sees the click
        landed. Guard against (a) regression to silent copy and (b)
        re-introduction of the dead shortcuts:// URL fire."""
        html = _render()
        # Click must write the CLI to the clipboard
        assert "navigator.clipboard" in html, (
            "pick-veto no longer writes to clipboard — silent click regression"
        )
        # Click must flip the button text for visible feedback
        assert "✓ Copied" in html, (
            "pick-veto chip no longer shows visible click feedback — "
            "regressed to silent-copy state per persona audit P63"
        )
        # Dead shortcuts:// URL fire must NOT come back — Pass B retired it
        assert "shortcuts://run-shortcut" not in html, (
            "pick-veto re-introduced retired macOS Shortcut URL fire — "
            "Pass B (commit 0555a25) made Chrome extension the only "
            "live dispatch path"
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

    def test_rebuild_chip_copy_matches_launchpad_chips(self, isolated_home):
        """Tick #79 — the memory viewer rebuild chip must use the same
        '↻ Rebuild' copy as the launchpad lens-rebuild (tick #76) and
        cortex-rebuild (tick #77) chips. Principle #11: shared UI
        primitives stay consistent across surfaces. Catches a regression
        that would drift the memory viewer chip back to bare 'Rebuild'."""
        html = _render()
        # Initial label
        assert '"↻ Rebuild"' in html, (
            "viewer-rebuild-chip should use unified '↻ Rebuild' copy"
        )
        # Reset-after-flash label (also has to match)
        assert "textContent = \"↻ Rebuild\"" in html, (
            "the post-flash reset still uses bare 'Rebuild' — text drifts to "
            "inconsistent on second click"
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
            '"lens.md" || name === "topics.json") return "lens"',
            '"picks.json") return "consolidate"',
            # core.md was previously suggested via `distill`; flipped to
            # `dream` 2026-05-18 (iter #11) when distill CLI was hidden
            # but the rebuild chip was still emitting a now-dead command.
            '"core.md") return "dream"',
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
        assert "'trinity-local council --task \"'" in html, (
            "launch chip no longer copies trinity-local council --task — template drift"
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

    def test_threshold_single_sourced_from_python(self, isolated_home):
        """Tick #35 — JS-side SIM_THRESHOLD must match the Python-side
        BASIN_SIM_THRESHOLD that the launchpad chip renderer uses. If
        the two drift, the launchpad and the viewer will disagree on
        whether a task has a topology match."""
        import re
        from trinity_local.launchpad_data import BASIN_SIM_THRESHOLD
        html = _render()
        m = re.search(r"const SIM_THRESHOLD = ([0-9.]+)\s*;", html)
        assert m, "SIM_THRESHOLD assignment not found in rendered JS"
        injected = float(m.group(1))
        assert injected == BASIN_SIM_THRESHOLD, (
            f"JS SIM_THRESHOLD={injected} drifted from Python "
            f"BASIN_SIM_THRESHOLD={BASIN_SIM_THRESHOLD} — they MUST "
            f"agree or launchpad/viewer chips will mis-link"
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
        # Logic now lives in loadCrossMemoryMaps (shared by both Readers).
        html = _render()
        assert "function loadCrossMemoryMaps" in html, "shared cross-memory loader missing"
        assert 'JSON.parse(raw)' in html, "picks parse step missing in shared loader"
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


class TestPicksToTopologyCrossLink:
    """Tick #32 — picks → topology cross-link. Completes the
    bidirectional bridge tick #30 opened. Each pick card now renders
    'View in topology →' targeting topics.html?basin=<id>, and the
    topology view auto-opens the matching basin via the ?basin=
    deep-link param."""

    def test_shared_centroid_match_helper_extracted(self, isolated_home):
        # The centroid match logic was duplicated potential — extracted
        # into matchBasinsToPicks so both Reader directions can't drift.
        html = _render()
        assert "function matchBasinsToPicks" in html, (
            "shared centroid-match helper missing — picks Reader + topology view "
            "will compute the match independently and drift"
        )
        # Returns BOTH directions so each Reader can grab the one it needs.
        assert "basinIdToTask" in html, "shared helper doesn't expose basinIdToTask"
        assert "taskToBasinId" in html, "shared helper doesn't expose taskToBasinId"

    def test_picks_reader_renders_topology_xlink(self, isolated_home):
        html = _render()
        # The xlink template targets topics.json with ?basin=<id>. If
        # the URL contract changes, the deep-link handler in topology
        # view stops opening the right basin.
        assert "View in topology" in html, "topology xlink label missing"
        assert 'memory.html?file=topics.json&basin=" + encodeURIComponent(topologyBasinId)' in html, (
            "topology xlink template drifted from ?basin= deep-link contract"
        )

    def test_topology_view_handles_basin_deep_link(self, isolated_home):
        html = _render()
        # The handler must read ?basin from URL and call showDetail on
        # the matching node. Without it, the picks Reader's xlink lands
        # on a graph with no panel open — confusing UX.
        assert 'params.get("basin")' in html, "topology view doesn't read ?basin= from URL"
        assert "nodes.find(n => n.id === focusBasin)" in html, (
            "topology view's basin deep-link doesn't lookup the matching node"
        )
        # The handler should also call highlightNeighborhood so the
        # selected basin's local neighborhood pops out — same UX as a
        # manual click on the node.
        assert "highlightNeighborhood(match.id)" in html, (
            "?basin= deep-link doesn't highlight neighborhood — selected "
            "basin will be visually indistinguishable from siblings"
        )


class TestRoutingToTopologyCrossLink:
    """Tick #33 — routing → topology cross-link via task_type → pick →
    centroid → basin. Routing doesn't carry centroids itself; the
    bridge piggybacks on the shared taskToBasinId map that tick #32
    already computes from picks.basin_centroid."""

    def test_chip_class_defined(self, isolated_home):
        html = _render()
        assert ".routing-topology-chip" in html, ".routing-topology-chip CSS missing"
        assert '"routing-topology-chip"' in html, (
            "renderRoutingReader doesn't construct a .routing-topology-chip anchor"
        )

    def test_chip_reuses_shared_task_basin_map(self, isolated_home):
        html = _render()
        # The chip must read from the same taskToBasinId Map that
        # tick #32's picks Reader uses. If a future refactor splits
        # the two sides, the picks→topology and routing→topology
        # links could disagree on whether a task has a basin match.
        assert "routingTaskToBasinId" in html, (
            "renderRoutingReader doesn't pull from loadCrossMemoryMaps"
        )
        assert "loadCrossMemoryMaps()" in html, (
            "shared cross-memory loader not called from routing Reader"
        )

    def test_chip_targets_topology_with_basin_param(self, isolated_home):
        html = _render()
        # The href must use the same ?basin= deep-link contract the
        # topology view handles (tick #32). If they diverge, the
        # click lands but the panel doesn't open.
        assert 'memory.html?file=topics.json&basin=" + encodeURIComponent(topoBasinId)' in html, (
            "routing→topology xlink template drifted from ?basin= deep-link"
        )


class TestChairmanBasinLabelFallback:
    """Tick #49 — viewer prefers `basin.label` (chairman-derived) over
    representative-headline truncation over top_terms. Older topics.json
    files written before the labeler stage have no .label and fall
    through the chain. Guards the fallback ordering so a future
    refactor can't silently change which signal wins."""

    def test_labelFor_prefers_chairman_label(self, isolated_home):
        html = _render()
        # Branch order matters: label first, then reps[0], then top_terms.
        assert "if (b.label)" in html, (
            "labelFor must check b.label FIRST so chairman semantics win "
            "over heuristic truncation of representative text"
        )

    def test_tooltipFor_prefers_chairman_label(self, isolated_home):
        html = _render()
        # Same guard for the SVG <title> tooltip.
        assert "tooltipFor" in html, "tooltipFor helper missing"
        # The label-first branch in tooltipFor is right above the legacy chain.
        idx = html.find("function tooltipFor")
        assert idx > 0
        nearby = html[idx:idx + 400]
        assert "b.label" in nearby, "tooltipFor doesn't read b.label"

    def test_basin_dataclass_carries_label_fields(self, isolated_home):
        """Round-trip: Basin → to_dict → JSON → load_basins → Basin
        must preserve the chairman fields (label / intent_type / language)."""
        from trinity_local.me.basins import Basin, save_basins, load_basins
        b = Basin(
            id="b00",
            size=10,
            top_terms=["one", "two"],
            centroid=[0.1, 0.2],
            prompt_ids=["p1"],
            thread_count=3,
            label="Brainstorming for short-form social media",
            intent_type="creative",
            language="en",
        )
        save_basins([b])
        loaded = load_basins()
        assert len(loaded) == 1
        assert loaded[0].label == "Brainstorming for short-form social media"
        assert loaded[0].intent_type == "creative"
        assert loaded[0].language == "en"


class TestStaleBasinBanner:
    """Tick #40 — ?basin=<id> deep-link gracefully handles a stale
    reference (basin no longer in topology, e.g. lens-build was
    re-run with different cluster count). Shows a warm-warning
    banner with a rebuild chip; without this, the link landed
    silently with no panel open and no feedback to the user."""

    def test_stale_basin_branch_present(self, isolated_home):
        html = _render()
        # The else-branch of the focusBasin handler must surface a
        # not-found banner. Guard the marker so a future refactor
        # doesn't silently drop the user-feedback path.
        assert 'not in the current topology' in html, (
            "stale-basin banner copy missing — ?basin= mismatches will "
            "land silently with no user feedback"
        )
        # The rebuild chip should copy the lens-build CLI when clicked.
        assert "trinity-local lens" in html, (
            "stale-basin banner doesn't surface the rebuild CLI chip"
        )

    def test_stale_basin_reuses_health_banner_classes(self, isolated_home):
        # Reuses the .viewer-health-banner + .viewer-health-cmd classes
        # so the stale notice looks identical to the picks Reader's
        # "not yet" banner. Same shape, same color, same affordances —
        # one CSS rule covers both surfaces.
        html = _render()
        # The handler constructs the banner using the same classes;
        # if either constructor drifts, the stale notice would render
        # unstyled.
        idx_handler = html.find("not in the current topology")
        assert idx_handler > 0, "stale-basin handler not present in JS"
        # Find the nearest preceding viewer-health-banner construction —
        # confirms the stale path uses the same DOM shape.
        nearby = html[max(0, idx_handler - 800):idx_handler]
        assert '"viewer-health-banner"' in nearby, (
            "stale-basin banner not built with .viewer-health-banner class — "
            "visual drift from the picks Reader's matching banner"
        )


class TestBasinHoverTitleHelper:
    """Tick #39 — JS-side basinHoverTitle helper mirrors the Python
    _topology_basin_labels + Vue basinHoverLabel. Renders 'Basin
    <id> — <terms>' when topics.json carries top_terms, otherwise
    falls back to 'Open basin <id> in the topology graph'. Used by
    the picks→topology xlink (tick #32) and routing→topology chip
    (tick #33) so all four launchpad/viewer chips agree on hover."""

    def test_helper_function_defined(self, isolated_home):
        html = _render()
        assert "function basinHoverTitle" in html, (
            "basinHoverTitle helper missing — viewer chips will fall back "
            "to opaque 'Open basin <id>' tooltips"
        )

    def test_basinLabels_attached_to_cross_memory_maps(self, isolated_home):
        html = _render()
        # loadCrossMemoryMaps must expose basinLabels alongside the
        # task↔basin maps so both Reader views get a consistent
        # source of truth.
        assert "maps.basinLabels = basinLabels" in html, (
            "loadCrossMemoryMaps doesn't attach basinLabels — viewer "
            "chips can't access the basin → top-terms map"
        )

    def test_picks_xlink_uses_basinHoverTitle(self, isolated_home):
        html = _render()
        assert "basinHoverTitle(topologyBasinId, basinLabels)" in html, (
            "picks card 'View in topology →' xlink no longer threads "
            "basinHoverTitle — hover text reverts to opaque"
        )

    def test_routing_chip_uses_basinHoverTitle(self, isolated_home):
        html = _render()
        assert "basinHoverTitle(topoBasinId, routingBasinLabels)" in html, (
            "routing-table → topology chip no longer threads "
            "basinHoverTitle"
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
