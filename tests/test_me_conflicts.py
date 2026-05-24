"""Tests for #141 active conflict surfacing (Stage 4b)."""
from __future__ import annotations

import pytest

from trinity_local.me.conflicts import (
    Conflict,
    _is_swapped_poles,
    _pair_id,
    count_active_conflicts,
    detect_conflicts,
    load_conflicts,
    save_conflicts,
)
from trinity_local.me.pair_mining import LensPair


@pytest.fixture
def conflicts_env(tmp_path, monkeypatch):
    monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
    return tmp_path


def _pair(pole_a: str, pole_b: str, horizon: str = "strategic", basins: list[str] | None = None) -> LensPair:
    return LensPair(
        pole_a=pole_a,
        pole_b=pole_b,
        failure_a=f"pure {pole_a}",
        failure_b=f"pure {pole_b}",
        basins_spanned=basins or ["b00", "b01"],
        horizon=horizon,
    )


class TestSwappedPolesDetection:
    def test_swapped_poles_detected(self):
        a = _pair("speed", "safety")
        b = _pair("safety", "speed")
        assert _is_swapped_poles(a, b) is True

    def test_identical_poles_not_conflict(self):
        a = _pair("speed", "safety")
        b = _pair("speed", "safety")
        assert _is_swapped_poles(a, b) is False

    def test_unrelated_poles_not_conflict(self):
        a = _pair("speed", "safety")
        b = _pair("brevity", "depth")
        assert _is_swapped_poles(a, b) is False

    def test_case_insensitive(self):
        a = _pair("Infrastructure", "Interface")
        b = _pair("interface", "INFRASTRUCTURE")
        assert _is_swapped_poles(a, b) is True

    def test_whitespace_normalized(self):
        a = _pair("  infrastructure  ", "interface")
        b = _pair("interface", "infrastructure  ")
        assert _is_swapped_poles(a, b) is True


class TestPairId:
    def test_id_stable_across_calls(self):
        p1 = _pair("infrastructure", "interface")
        p2 = _pair("infrastructure", "interface")
        assert _pair_id(p1) == _pair_id(p2)

    def test_id_starts_with_p_prefix(self):
        assert _pair_id(_pair("a", "b")).startswith("p_")

    def test_swapped_poles_yield_different_ids(self):
        """An (A,B) pair and a (B,A) pair must have different ids — they
        ARE different pairs (privilege direction differs), even if they
        constitute a conflict together."""
        assert _pair_id(_pair("a", "b")) != _pair_id(_pair("b", "a"))


class TestDetectConflicts:
    def test_no_conflicts_in_unrelated_pairs(self):
        pairs = [
            _pair("infrastructure", "interface"),
            _pair("brevity", "completeness"),
            _pair("speed", "safety"),
        ]
        assert detect_conflicts(pairs) == []

    def test_swapped_pair_surfaces_one_conflict(self):
        pairs = [
            _pair("infrastructure", "interface"),
            _pair("interface", "infrastructure"),
        ]
        conflicts = detect_conflicts(pairs)
        assert len(conflicts) == 1
        c = conflicts[0]
        assert c.pole_a_axis == "infrastructure"
        assert c.pole_b_axis == "interface"
        assert c.horizon_match is True

    def test_horizon_mismatch_flagged_correctly(self):
        """Different-horizon conflict is detected but flagged as
        non-alarm (multi-resolution preference)."""
        pairs = [
            _pair("speed", "safety", horizon="tactical"),
            _pair("safety", "speed", horizon="strategic"),
        ]
        conflicts = detect_conflicts(pairs)
        assert len(conflicts) == 1
        assert conflicts[0].horizon_match is False
        assert "not contradiction" in conflicts[0].why_conflicting.lower() or \
               "multi-resolution" in conflicts[0].why_conflicting.lower()

    def test_dedupes_self_comparison(self):
        """A pair compared to itself must NOT surface as a conflict."""
        p = _pair("x", "y")
        assert detect_conflicts([p]) == []

    def test_three_way_does_not_double_count(self):
        """If 3 pairs cluster around the same axis with different
        privilege directions, each unique pair-of-pairs surfaces ONCE,
        never twice from different scan order."""
        pairs = [
            _pair("a", "b"),
            _pair("b", "a"),
            _pair("c", "d"),  # unrelated
        ]
        conflicts = detect_conflicts(pairs)
        assert len(conflicts) == 1


class TestPersistence:
    def test_save_and_load_round_trip(self, conflicts_env):
        pairs = [_pair("a", "b"), _pair("b", "a")]
        original = detect_conflicts(pairs)
        save_conflicts(original)

        loaded = load_conflicts()
        assert len(loaded) == 1
        assert loaded[0].pair_a_id == original[0].pair_a_id
        assert loaded[0].horizon_match == original[0].horizon_match
        assert loaded[0].pole_a_axis == "a"

    def test_load_empty_when_no_file(self, conflicts_env):
        assert load_conflicts() == []

    def test_save_overwrites_not_appends(self, conflicts_env):
        """Conflicts are recomputed from scratch each build, not
        accumulated — the on-disk file is always the latest snapshot."""
        save_conflicts([
            Conflict(
                pair_a_id="p_old1",
                pair_b_id="p_old2",
                pole_a_axis="old",
                pole_b_axis="stale",
                horizon_a="tactical",
                horizon_b="tactical",
                horizon_match=True,
            )
        ])
        save_conflicts([])
        assert load_conflicts() == []


class TestStage4bWrapper:
    """Slice 2: stage4b_surface_conflicts() — pipeline-level wrapper
    that calls detect_conflicts and persists to disk."""

    def test_empty_inputs_clear_stale_file(self, conflicts_env):
        """When both accepted and orderings are empty, any prior
        conflicts file from an earlier build is cleared — the launchpad
        shouldn't show ghost detections from a stale corpus."""
        from trinity_local.me.pipeline import stage4b_surface_conflicts

        # Seed a stale file
        save_conflicts([
            Conflict(
                pair_a_id="stale", pair_b_id="ghost",
                pole_a_axis="x", pole_b_axis="y",
                horizon_a="strategic", horizon_b="strategic",
                horizon_match=True,
            )
        ])
        assert len(load_conflicts()) == 1  # confirms baseline

        result = stage4b_surface_conflicts([], [])
        assert result == []
        assert load_conflicts() == []  # cleared from disk

    def test_detects_and_persists_in_one_call(self, conflicts_env):
        from trinity_local.me.pipeline import stage4b_surface_conflicts

        accepted = [_pair("speed", "safety")]
        orderings = [_pair("safety", "speed")]
        conflicts = stage4b_surface_conflicts(accepted, orderings)

        assert len(conflicts) == 1
        # And it's on disk
        assert len(load_conflicts()) == 1

    def test_finds_conflicts_within_accepted_only(self, conflicts_env):
        """A conflict can exist purely in the accepted pool — not just
        across the accepted/orderings split."""
        from trinity_local.me.pipeline import stage4b_surface_conflicts

        accepted = [
            _pair("infrastructure", "interface"),
            _pair("interface", "infrastructure"),
        ]
        conflicts = stage4b_surface_conflicts(accepted, [])
        assert len(conflicts) == 1


class TestLensMdRender:
    """Slice 3: lens.md surfaces the ⚠ Tensions in tension section."""

    def test_no_conflicts_no_section(self, conflicts_env):
        from trinity_local.me.pipeline import render_me_markdown

        # No conflicts.json → no Tensions section
        save_conflicts([])
        md = render_me_markdown(
            accepted=[_pair("a", "b")],
            orderings=[],
            rejections=None,
        )
        assert "Tensions in tension" not in md

    def test_same_horizon_renders_with_alarm_header(self, conflicts_env):
        from trinity_local.me.pipeline import render_me_markdown

        save_conflicts([
            Conflict(
                pair_a_id="p_aaa", pair_b_id="p_bbb",
                pole_a_axis="infrastructure", pole_b_axis="interface",
                horizon_a="strategic", horizon_b="strategic",
                horizon_match=True,
                basins_a=["b00"], basins_b=["b01"],
            )
        ])
        md = render_me_markdown(
            accepted=[_pair("infrastructure", "interface")],
            orderings=[],
            rejections=None,
        )
        assert "⚠ Tensions in tension" in md
        assert "infrastructure ↔ interface" in md
        assert "meta-judgment" in md  # the explanatory prose

    def test_cross_horizon_uses_softer_label(self, conflicts_env):
        from trinity_local.me.pipeline import render_me_markdown

        save_conflicts([
            Conflict(
                pair_a_id="p_aaa", pair_b_id="p_bbb",
                pole_a_axis="speed", pole_b_axis="safety",
                horizon_a="tactical", horizon_b="strategic",
                horizon_match=False,
                basins_a=["b00"], basins_b=["b01"],
            )
        ])
        md = render_me_markdown(
            accepted=[_pair("speed", "safety")],
            orderings=[],
            rejections=None,
        )
        assert "Tensions in tension" in md
        # Cross-horizon should be framed as multi-resolution, NOT alarm
        assert "multi-resolution" in md
        assert "not contradiction" in md


class TestLaunchpadHealthSurfacing:
    """Slice 3: launchpad health signal #7 = active contradictions."""

    def test_active_conflicts_surface_as_issue(self, conflicts_env):
        from trinity_local.launchpad_data import _memory_health

        save_conflicts([
            Conflict(
                pair_a_id="p1", pair_b_id="p2",
                pole_a_axis="x", pole_b_axis="y",
                horizon_a="strategic", horizon_b="strategic",
                horizon_match=True,
            )
        ])
        health = _memory_health()
        lens_issues = [i for i in health["issues"] if i["name"] == "lenses.json"]
        assert len(lens_issues) == 1
        assert lens_issues[0]["status"] == "contradictions"
        assert "1" in lens_issues[0]["hint"]
        # Total: 9 signals after the extension-signals add
        assert health["total_count"] == 9

    def test_cross_horizon_only_does_not_surface(self, conflicts_env):
        """Cross-horizon conflicts are NOT real alarms — they're
        multi-resolution preferences. Should not appear as launchpad
        health issue."""
        from trinity_local.launchpad_data import _memory_health

        save_conflicts([
            Conflict(
                pair_a_id="p1", pair_b_id="p2",
                pole_a_axis="x", pole_b_axis="y",
                horizon_a="tactical", horizon_b="strategic",
                horizon_match=False,
            )
        ])
        health = _memory_health()
        lens_issues = [i for i in health["issues"] if i["name"] == "lenses.json"]
        assert lens_issues == []


class TestActiveCount:
    def test_count_only_includes_horizon_match(self, conflicts_env):
        save_conflicts([
            Conflict(
                pair_a_id="a", pair_b_id="b",
                pole_a_axis="x", pole_b_axis="y",
                horizon_a="strategic", horizon_b="strategic",
                horizon_match=True,
            ),
            Conflict(
                pair_a_id="c", pair_b_id="d",
                pole_a_axis="m", pole_b_axis="n",
                horizon_a="tactical", horizon_b="strategic",
                horizon_match=False,  # multi-resolution, NOT alarm
            ),
        ])
        assert count_active_conflicts() == 1

    def test_count_zero_when_no_conflicts(self, conflicts_env):
        assert count_active_conflicts() == 0
