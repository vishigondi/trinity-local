"""#212 cold-start aha: cold_open_tension() surfaces ONE surprising true
tension the instant the lens has signal — the differentiated wow, before the
user learns a verb. Surfaced on the launchpad hero, `status`, and MCP."""
from __future__ import annotations

import pytest


@pytest.mark.usefixtures("patch_trinity_home")
class TestColdOpenTension:
    def test_none_on_cold_install(self):
        from trinity_local.cold_start import cold_open_tension
        assert cold_open_tension() is None

    def test_surfaces_top_registry_tension(self):
        from trinity_local.cold_start import cold_open_tension
        from trinity_local.me.lens_registry import RegistryEntry, save_registry
        from trinity_local.utils import now_iso

        ts = now_iso()
        save_registry([
            RegistryEntry(
                tension_id="t1", pole_a="ship velocity", pole_b="polish",
                evidence_ids=["e1", "e2", "e3", "e4"],  # support 4 ≥ LOW_CONFIDENCE
                first_seen=ts, last_confirmed=ts,
            ),
            RegistryEntry(
                tension_id="t2", pole_a="depth", pole_b="speed",
                evidence_ids=["x1"], first_seen=ts, last_confirmed=ts,
            ),
        ])
        line = cold_open_tension()
        assert line is not None
        # Highest-support tension leads (ship velocity / polish, support 4).
        assert "ship velocity" in line and "polish" in line
        assert "4 of your decisions" in line  # provenance shown for n>=3
        assert "depth" not in line  # only ONE tension surfaced


@pytest.mark.usefixtures("patch_trinity_home")
class TestColdOpenLaunchpad:
    def test_page_data_carries_cold_open(self):
        from trinity_local.launchpad_data import _cold_open_for_launchpad
        from trinity_local.me.lens_registry import RegistryEntry, save_registry
        from trinity_local.utils import now_iso

        ts = now_iso()
        save_registry([RegistryEntry(
            tension_id="t1", pole_a="A", pole_b="B",
            evidence_ids=["e1"], first_seen=ts, last_confirmed=ts,
        )])
        assert _cold_open_for_launchpad() is not None

    def test_hero_renders_cold_open_binding(self):
        from trinity_local.launchpad_template import render_launchpad_html
        html = render_launchpad_html(page_data={}, recent_cards="")
        assert "pageData.coldOpen" in html
        assert "cold-open" in html
