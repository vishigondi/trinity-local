"""Verdict-capture stats on the launchpad — gates the moat thesis.

Trinity's "personal ledger of cross-model preferences" only exists for
councils the user actually rates. Tick #69's data audit found 3 of 19
outcomes carried verdicts (16%) on the dev install; surfacing that on
the launchpad is how the user notices the gap (task #110).

These tests exercise the pure aggregator (_verdict_stats) against
synthetic outcomes in an isolated TRINITY_HOME, and the build_page_data
plumbing that ships it to the template.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
    (tmp_path / "council_outcomes").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _write_outcome(home: Path, council_id: str, *, with_verdict: bool) -> Path:
    """Synthesize a minimal council_outcome JSON in the isolated home."""
    metadata: dict = {}
    if with_verdict:
        metadata["user_verdict"] = {"user_winner": "claude"}
    payload = {
        "council_run_id": council_id,
        "bundle_id": f"bundle_{council_id}",
        "metadata": metadata,
    }
    path = home / "council_outcomes" / f"{council_id}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class TestVerdictStats:
    """_verdict_stats walks council_outcomes/*.json and counts how many
    carry metadata.user_verdict.user_winner."""

    def test_empty_install_returns_zero(self, isolated_home):
        from trinity_local.launchpad_data import _verdict_stats
        stats = _verdict_stats()
        assert stats == {"total": 0, "rated": 0, "rate": 0.0}

    def test_counts_rated_vs_unrated(self, isolated_home):
        _write_outcome(isolated_home, "council_a", with_verdict=True)
        _write_outcome(isolated_home, "council_b", with_verdict=False)
        _write_outcome(isolated_home, "council_c", with_verdict=False)
        from trinity_local.launchpad_data import _verdict_stats
        stats = _verdict_stats()
        assert stats["total"] == 3
        assert stats["rated"] == 1
        assert stats["rate"] == pytest.approx(1 / 3)

    def test_unparseable_outcomes_skipped_silently(self, isolated_home):
        """A corrupt JSON file in the outcomes dir must not break the
        whole launchpad render — the count just excludes that file."""
        _write_outcome(isolated_home, "council_good", with_verdict=True)
        bad = isolated_home / "council_outcomes" / "council_bad.json"
        bad.write_text("{not valid json", encoding="utf-8")
        from trinity_local.launchpad_data import _verdict_stats
        stats = _verdict_stats()
        assert stats["total"] == 1  # good only
        assert stats["rated"] == 1


class TestPageDataVerdictStats:
    """Plumbing test: build_page_data exposes verdictStats so the launchpad
    template can render the "N of M rated" eyebrow without re-walking outcomes."""

    def test_page_data_contains_verdict_stats(self, isolated_home, tmp_path):
        from trinity_local.launchpad_data import build_page_data
        _write_outcome(isolated_home, "council_a", with_verdict=True)
        _write_outcome(isolated_home, "council_b", with_verdict=False)
        data = build_page_data(
            live_review_path=tmp_path / "live_council.html",
            recent_councils=[],
        )
        assert "verdictStats" in data
        assert data["verdictStats"]["total"] == 2
        assert data["verdictStats"]["rated"] == 1

    def test_cold_install_has_zero_filled_stats(self, isolated_home, tmp_path):
        """No outcomes → stats present with zeros, not missing — frontend
        v-if guards on rate < 0.5 + total >= 5 stay simple."""
        from trinity_local.launchpad_data import build_page_data
        data = build_page_data(
            live_review_path=tmp_path / "live_council.html",
            recent_councils=[],
        )
        assert data["verdictStats"] == {"total": 0, "rated": 0, "rate": 0.0}
