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


class TestShortcutStatus:
    """Tick #73 — launchpad surfaces the macOS Shortcut registration
    status. Banner renders only when applicable AND missing; on Linux
    or unknown-check states the banner stays hidden."""

    def test_non_macos_returns_not_applicable(self, monkeypatch):
        """On Linux/Windows, the Shortcut isn't applicable — the banner
        must NOT show. Returns applicable=False so the v-if hides."""
        monkeypatch.setattr("sys.platform", "linux")
        from trinity_local.launchpad_data import _shortcut_status
        result = _shortcut_status()
        assert result == {"ok": True, "applicable": False}

    def test_macos_shortcut_installed_returns_ok(self, monkeypatch):
        monkeypatch.setattr("sys.platform", "darwin")
        import trinity_local.shortcut_setup as setup
        monkeypatch.setattr(setup, "_shortcut_installed", lambda *_a, **_kw: True)
        from trinity_local.launchpad_data import _shortcut_status
        result = _shortcut_status()
        assert result["ok"] is True
        assert result["applicable"] is True

    def test_macos_shortcut_missing_returns_not_ok(self, monkeypatch):
        """The banner-triggering case — applicable AND not ok."""
        monkeypatch.setattr("sys.platform", "darwin")
        import trinity_local.shortcut_setup as setup
        monkeypatch.setattr(setup, "_shortcut_installed", lambda *_a, **_kw: False)
        from trinity_local.launchpad_data import _shortcut_status
        result = _shortcut_status()
        assert result["ok"] is False
        assert result["applicable"] is True
        assert "name" in result  # banner uses the configured Shortcut name

    def test_page_data_contains_shortcut_status(self, isolated_home, tmp_path):
        from trinity_local.launchpad_data import build_page_data
        data = build_page_data(
            live_review_path=tmp_path / "live_council.html",
            recent_councils=[],
        )
        assert "shortcutStatus" in data
        assert "ok" in data["shortcutStatus"]
        assert "applicable" in data["shortcutStatus"]

    def test_launchpad_html_contains_banner_template(self, isolated_home):
        """Per meta-principle #14: every shipped feature gets a smoke
        regression guard within one tick. The banner only renders at
        runtime when pageData.shortcutStatus.applicable && !ok — but
        the template DOM exists in source regardless of runtime state.
        Catches a future refactor that drops the banner element."""
        from trinity_local.launchpad_page import render_launchpad_html
        html = render_launchpad_html()
        # The v-if guard that gates banner visibility
        assert "pageData.shortcutStatus" in html
        assert "shortcutStatus.applicable" in html
        # The remediation copy points users at the right CLI command
        assert "trinity-local shortcut-install" in html
        # The marketing-load-bearing phrase that explains the cost
        assert "moat stays empty" in html

    def test_launchpad_html_contains_lens_rebuild_chip(self, isolated_home):
        """Tick #76 — lens card gets a rebuild chip when lens exists.
        Closes the forward-arc gap "See a rejected lens → rebuild
        lens.md link." Same shape as Surface 18's rebuild chips for
        picks/core in the memory viewer."""
        from trinity_local.launchpad_page import render_launchpad_html
        html = render_launchpad_html()
        # The chip-firing handler + flash key
        assert "copyText('trinity-local lens-build', 'lens-rebuild')" in html
        # The v-if guard so the chip stays hidden in the empty-state
        # (where the bare command is shown in a code block instead)
        assert "v-if=\"tasteLenses\"" in html
        # The flash-on-copy text — pinning the rebuild action's
        # confirmation cycle (same 2400ms reset as copyHealthCommand)
        assert "copiedKey === 'lens-rebuild'" in html
