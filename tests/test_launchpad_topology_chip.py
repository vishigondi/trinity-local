"""Tick #34 — launchpad recent-card → topology chip.

The card already had → pick and → routing chips (tick #15). The
third chip → topology closes the loop from the launchpad directly,
sparing the bounce through picks. The Python-side centroid match
must agree with the JS-side match in memory_viewer (same threshold,
same first-task-wins rule) — these tests guard the Python half.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
    (tmp_path / "memories").mkdir(parents=True, exist_ok=True)
    (tmp_path / "cortex").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _seed_topics(home: Path, basins: list[dict]) -> None:
    (home / "memories" / "topics.json").write_text(
        json.dumps({"basins": basins}), encoding="utf-8"
    )


def _seed_picks(home: Path, patterns: dict) -> None:
    # cortex.load_routing_patterns reads from picks_path() which today
    # resolves to ~/.trinity/memories/picks.json (the cortex_routing_
    # patterns_path is a back-compat alias).
    (home / "memories" / "picks.json").write_text(
        json.dumps(patterns), encoding="utf-8"
    )


class TestTaskToTopologyBasin:
    """The Python centroid-match helper must agree with the JS half
    (matchBasinsToPicks in memory_viewer.py). Tests pin the contract:
    threshold, first-task-wins, graceful degradation on missing data."""

    def test_cold_install_returns_empty(self, isolated_home):
        from trinity_local.launchpad_data import _task_to_topology_basin
        # No topics.json, no picks → empty map (must NOT raise).
        assert _task_to_topology_basin() == {}

    def test_no_picks_returns_empty(self, isolated_home):
        # Topics exist but no picks → still empty.
        _seed_topics(isolated_home, [
            {"id": "b00", "centroid": [1.0, 0.0, 0.0]},
        ])
        from trinity_local.launchpad_data import _task_to_topology_basin
        assert _task_to_topology_basin() == {}

    def test_match_returns_basin_for_aligned_centroid(self, isolated_home):
        # Pick centroid nearly parallel to b00 → should match.
        _seed_topics(isolated_home, [
            {"id": "b00", "centroid": [1.0, 0.0, 0.0]},
            {"id": "b01", "centroid": [0.0, 1.0, 0.0]},
        ])
        _seed_picks(isolated_home, {
            "coding": _minimal_pattern_payload("coding", centroid=[0.99, 0.1, 0.0]),
        })
        from trinity_local.launchpad_data import _task_to_topology_basin
        result = _task_to_topology_basin()
        assert result == {"coding": "b00"}

    def test_below_threshold_drops_match(self, isolated_home):
        # Pick centroid orthogonal-ish to both basins (cosine < 0.65)
        # → no match returned.
        _seed_topics(isolated_home, [
            {"id": "b00", "centroid": [1.0, 0.0, 0.0]},
            {"id": "b01", "centroid": [0.0, 1.0, 0.0]},
        ])
        _seed_picks(isolated_home, {
            "unrelated": _minimal_pattern_payload(
                "unrelated", centroid=[0.5, 0.5, 0.707]  # cosine ~0.5 to both
            ),
        })
        from trinity_local.launchpad_data import _task_to_topology_basin
        assert _task_to_topology_basin() == {}

    def test_first_task_wins_when_two_match_same_basin(self, isolated_home):
        # Two picks both match b00. First (by insertion order) claims it;
        # second drops. This mirrors the JS rule so the launchpad chips
        # don't disagree with the in-viewer link.
        _seed_topics(isolated_home, [
            {"id": "b00", "centroid": [1.0, 0.0, 0.0]},
        ])
        _seed_picks(isolated_home, {
            "first_task": _minimal_pattern_payload("first_task", centroid=[0.99, 0.0, 0.0]),
            "second_task": _minimal_pattern_payload("second_task", centroid=[0.98, 0.0, 0.0]),
        })
        from trinity_local.launchpad_data import _task_to_topology_basin
        result = _task_to_topology_basin()
        assert "first_task" in result
        assert result["first_task"] == "b00"
        assert "second_task" not in result  # second was claimed-out


class TestCortexCardTopologyAnnotation:
    """Tick #35 — extend the cortex picks card on the launchpad with
    a → topology link per rule when that rule's basin centroid matches
    a topology basin. Annotation happens in _load_cortex_rules so the
    Vue template just reads r.topology_basin."""

    def test_topology_basin_attached_when_match(self, isolated_home, monkeypatch):
        from trinity_local import launchpad_data
        # Stub the centroid matcher so the test doesn't need to
        # populate topics.json — we're testing the annotation, not
        # the math (that's covered above).
        monkeypatch.setattr(
            launchpad_data,
            "_task_to_topology_basin",
            lambda: {"coding": "b07"},
        )
        # Stub load_routing_patterns so _load_cortex_rules has work
        # to annotate without needing a fully-seeded cortex.
        from trinity_local.cortex import RoutingPattern, RoutingRule, TrustScore, FailureModes
        rule = RoutingRule(primary="claude", challenger="gemini", reason="test")
        trust = TrustScore(value=0.7, components={"n_episodes": 1.0})
        pattern = RoutingPattern(
            basin_id="coding",
            consolidated_at="2026-05-13T00:00:00",
            n_episodes=5,
            task_types=["coding"],
            winner_distribution={"claude": 1.0},
            routing_rule=rule,
            trust_score=trust,
            failure_modes=FailureModes(),
            successful_prompts={},
            decay={},
            evidence=[],
            basin_centroid=[0.99, 0.0, 0.0],
        )
        monkeypatch.setattr(
            launchpad_data, "load_routing_patterns", lambda: {"coding": pattern}, raising=False
        )
        # Also monkeypatch the import inside _load_cortex_rules.
        import trinity_local.cortex
        monkeypatch.setattr(
            trinity_local.cortex, "load_routing_patterns", lambda: {"coding": pattern}
        )
        from trinity_local.launchpad_data import _load_cortex_rules
        payload = _load_cortex_rules()
        assert payload is not None, "cortex rules payload is None"
        assert payload["rules"], "no rules in payload"
        coding_rule = next(r for r in payload["rules"] if r["basin_id"] == "coding")
        assert coding_rule.get("topology_basin") == "b07", (
            f"topology_basin not annotated; got {coding_rule.get('topology_basin')!r}"
        )

    def test_topology_basin_absent_when_no_match(self, isolated_home, monkeypatch):
        from trinity_local import launchpad_data
        monkeypatch.setattr(launchpad_data, "_task_to_topology_basin", lambda: {})
        from trinity_local.cortex import RoutingPattern, RoutingRule, TrustScore, FailureModes
        rule = RoutingRule(primary="claude", challenger=None, reason="x")
        trust = TrustScore(value=0.5, components={})
        pattern = RoutingPattern(
            basin_id="unmatched",
            consolidated_at="2026-05-13T00:00:00",
            n_episodes=1,
            task_types=["unmatched"],
            winner_distribution={"claude": 1.0},
            routing_rule=rule,
            trust_score=trust,
            failure_modes=FailureModes(),
            successful_prompts={},
            decay={},
            evidence=[],
            basin_centroid=[0.1, 0.1, 0.0],
        )
        import trinity_local.cortex
        monkeypatch.setattr(
            trinity_local.cortex, "load_routing_patterns", lambda: {"unmatched": pattern}
        )
        from trinity_local.launchpad_data import _load_cortex_rules
        payload = _load_cortex_rules()
        rule_row = payload["rules"][0]
        assert "topology_basin" not in rule_row, (
            f"topology_basin should be absent when no match; got {rule_row.get('topology_basin')!r}"
        )


class TestRecentCardTopologyTooltip:
    """Tick #39 — recent-card → topology chip tooltip now surfaces
    basin top-terms when topics.json carries them. Cold-install
    fallback is 'Open basin <id> in the topology graph'."""

    def test_tooltip_carries_top_terms_when_labels_available(self, isolated_home, monkeypatch):
        monkeypatch.setattr(
            "trinity_local.launchpad_data._task_to_topology_basin",
            lambda: {"coding": "b07"},
        )
        monkeypatch.setattr(
            "trinity_local.launchpad_data._topology_basin_labels",
            lambda: {"b07": "refactor · function · type"},
        )
        from trinity_local.launchpad_data import build_recent_cards_html
        cards = [{
            "council_id": "c001",
            "chain_root_id": "t001",
            "review_page_path": "c001.html",
            "title": "Refactor X?",
            "winner_provider": "claude",
            "created_at": "2026-05-13T10:00:00",
            "segment_count": 1,
            "task_type": "coding",
        }]
        html = build_recent_cards_html(cards)
        # Tooltip should carry the top-terms text. The exact prefix
        # matches the Vue + JS helpers so the wording is consistent
        # across launchpad + viewer.
        assert 'title="Basin b07 — refactor · function · type"' in html, (
            "recent-card → topology chip tooltip missing basin top-terms"
        )

    def test_tooltip_falls_back_when_labels_empty(self, isolated_home, monkeypatch):
        monkeypatch.setattr(
            "trinity_local.launchpad_data._task_to_topology_basin",
            lambda: {"coding": "b07"},
        )
        monkeypatch.setattr(
            "trinity_local.launchpad_data._topology_basin_labels",
            lambda: {},  # no labels → fallback path
        )
        from trinity_local.launchpad_data import build_recent_cards_html
        cards = [{
            "council_id": "c001",
            "chain_root_id": "t001",
            "review_page_path": "c001.html",
            "title": "Refactor X?",
            "winner_provider": "claude",
            "created_at": "2026-05-13T10:00:00",
            "segment_count": 1,
            "task_type": "coding",
        }]
        html = build_recent_cards_html(cards)
        assert 'title="Open basin b07 in the topology graph"' in html, (
            "fallback tooltip path broken — cold install will render no title"
        )


class TestRecentCardTopologyChip:
    """The chip must render only when task_type → basin map has a match.
    Without a match, the recent card shows only → pick + → routing."""

    def test_chip_rendered_when_match_exists(self, isolated_home, monkeypatch):
        # Force _task_to_topology_basin to return a known map; assert
        # the rendered card HTML carries the → topology chip with the
        # right href.
        monkeypatch.setattr(
            "trinity_local.launchpad_data._task_to_topology_basin",
            lambda: {"coding": "b07"},
        )
        from trinity_local.launchpad_data import build_recent_cards_html
        cards = [{
            "council_id": "c001",
            "chain_root_id": "t001",
            "review_page_path": "c001.html",
            "title": "How do I refactor X?",
            "winner_provider": "claude",
            "created_at": "2026-05-13T10:00:00",
            "segment_count": 1,
            "task_type": "coding",
        }]
        html = build_recent_cards_html(cards)
        assert "→ topology" in html, "topology chip missing"
        assert "memory.html?file=topics.json&basin=b07" in html, (
            "topology chip target drifted from ?basin= contract"
        )

    def test_chip_omitted_when_no_match(self, isolated_home, monkeypatch):
        monkeypatch.setattr(
            "trinity_local.launchpad_data._task_to_topology_basin",
            lambda: {},  # no matches at all
        )
        from trinity_local.launchpad_data import build_recent_cards_html
        cards = [{
            "council_id": "c001",
            "chain_root_id": "t001",
            "review_page_path": "c001.html",
            "title": "A council",
            "winner_provider": "claude",
            "created_at": "2026-05-13T10:00:00",
            "segment_count": 1,
            "task_type": "unmapped_task",
        }]
        html = build_recent_cards_html(cards)
        # The other two chips must still render.
        assert "→ pick" in html
        assert "→ routing" in html
        # But not the topology chip.
        assert "→ topology" not in html, (
            "topology chip should NOT render when task has no centroid match"
        )


def _minimal_pattern_payload(task_type: str, *, centroid: list[float]) -> dict:
    """Build a minimal RoutingPattern-shaped dict that load_routing_patterns
    can deserialize. Field names + shapes mirror cortex._pattern_from_dict."""
    return {
        "basin_id": task_type,
        "n_episodes": 5,
        "consolidated_at": "2026-05-13T00:00:00",
        "routing_rule": {
            "primary": "claude",
            "challenger": "gemini",
            "reason": "test fixture",
        },
        "trust_score": {
            "value": 0.7,
            "components": {},
            "computed_by": "system",
        },
        "winner_distribution": {"claude": 1.0},
        "task_types": [task_type],
        "successful_prompts": {},
        "failure_modes": {},
        "evidence": [],
        "basin_centroid": centroid,
        "manifold_dim": 1.0,
        "bimodal_flag": False,
        "audit_status": "unaudited",
        "override_count": 0,
        "decay": {},
    }
