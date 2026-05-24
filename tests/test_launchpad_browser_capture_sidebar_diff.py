"""Tests for the sidebar-sync diff on the launchpad's browser-capture
card. Parity with the status CLI's Captures: section (50e7610).

Same data source for all three surfaces:
- status CLI Captures: section
- in-provider auto-sync pill (browser-extension/sync-pill.js)
- launchpad browser-capture card (this file's tests)

All call `capture_host._query_sync_status` so they never drift apart.
"""
from __future__ import annotations

import pytest


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
    return tmp_path


def _make_capture(home, provider, count, sidebar_ids=None):
    """Create N capture files for provider; optionally pin a sidebar."""
    import json

    conv_dir = home / "conversations" / provider
    conv_dir.mkdir(parents=True)
    for i in range(count):
        conv_id = f"conv_{provider}_{i}"
        (conv_dir / f"{conv_id}.json").write_text("{}", encoding="utf-8")
    if sidebar_ids is not None:
        sidebar = {"sidebar": {"items": [{"id": cid} for cid in sidebar_ids]}}
        (conv_dir / "_sidebar.json").write_text(json.dumps(sidebar), encoding="utf-8")


class TestBrowserCaptureSidebarDiff:
    def test_provider_with_no_sidebar_lacks_diff_fields(self, isolated_home):
        """If the extension hasn't snapshotted a sidebar yet (cold install
        or older extension version), the row should still render with
        count + count_24h but NO sidebar_count / missing_count fields.
        Template's v-if guards on those keys so absence is fine."""
        _make_capture(isolated_home, "claude", count=5)
        from trinity_local.launchpad_data import _browser_capture

        result = _browser_capture()
        assert result["has_data"] is True
        claude_row = next(r for r in result["providers"] if r["provider"] == "claude")
        # Diff fields absent — extension never wrote _sidebar.json
        assert claude_row.get("sidebar_count", 0) == 0 or "sidebar_count" not in claude_row
        assert claude_row.get("missing_count", 0) == 0 or "missing_count" not in claude_row

    def test_provider_fully_synced_has_zero_missing(self, isolated_home):
        """When on-disk captures match sidebar 1:1, missing_count is 0
        — template hides the unsynced suffix (silent-when-zero)."""
        _make_capture(
            isolated_home, "chatgpt", count=3,
            sidebar_ids=["conv_chatgpt_0", "conv_chatgpt_1", "conv_chatgpt_2"],
        )
        from trinity_local.launchpad_data import _browser_capture

        result = _browser_capture()
        chatgpt_row = next(r for r in result["providers"] if r["provider"] == "chatgpt")
        assert chatgpt_row["sidebar_count"] == 3
        assert chatgpt_row["missing_count"] == 0

    def test_provider_with_missing_threads_surfaces_count(self, isolated_home):
        """The load-bearing case: 3 captures on disk, sidebar lists 5 →
        missing_count = 2. Template renders "2 unsynced" suffix."""
        _make_capture(
            isolated_home, "gemini", count=3,
            sidebar_ids=[
                "conv_gemini_0", "conv_gemini_1", "conv_gemini_2",
                "conv_extra_in_sidebar", "conv_other_missing",
            ],
        )
        from trinity_local.launchpad_data import _browser_capture

        result = _browser_capture()
        gemini_row = next(r for r in result["providers"] if r["provider"] == "gemini")
        assert gemini_row["sidebar_count"] == 5
        assert gemini_row["missing_count"] == 2

    def test_sidebar_diff_failure_does_not_break_browser_capture(self, isolated_home, monkeypatch):
        """Per analytics-never-crash: a bug in _query_sync_status must
        not propagate out of _browser_capture. The row renders without
        the sidebar fields; rest of the surface stays intact."""
        _make_capture(isolated_home, "claude", count=2)

        def explode(payload):
            raise RuntimeError("simulated sidebar lookup bug")

        from trinity_local import capture_host as capture_mod
        monkeypatch.setattr(capture_mod, "_query_sync_status", explode)

        from trinity_local.launchpad_data import _browser_capture

        # Must not raise
        result = _browser_capture()
        assert result["has_data"] is True
        claude_row = next(r for r in result["providers"] if r["provider"] == "claude")
        # Sidebar fields absent (the try/except swallowed the error)
        assert "sidebar_count" not in claude_row
        assert "missing_count" not in claude_row
