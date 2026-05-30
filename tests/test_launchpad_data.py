

class TestTimelineForLaunchpad:
    """#252 'Your timeline' — life-chapters surfaced chronologically, dev/
    agent-ops chapters filtered, thin chapters dropped."""

    def _chapter(self, label, start, end, prompts):
        from types import SimpleNamespace
        return SimpleNamespace(
            label=label, start_month=start, end_month=end,
            months=1, total_prompts=prompts,
        )

    def test_filters_dev_sorts_chronologically(self, monkeypatch):
        import trinity_local.launchpad_data as ld
        chapters = [
            self._chapter("loop, run", "2026-05", "2026-05", 1363),   # dev → drop
            self._chapter("home, smart", "2025-07", "2025-07", 420),
            self._chapter("property, lots", "2025-05", "2026-03", 771),
            self._chapter("noise", "2024-01", "2024-01", 30),          # thin → drop
        ]
        monkeypatch.setattr(ld, "detect_chapters", lambda: chapters, raising=False)
        import trinity_local.me.chapters as ch
        monkeypatch.setattr(ch, "detect_chapters", lambda: chapters)

        rows = ld._timeline_for_launchpad()
        labels = [r["label"] for r in rows]
        assert "Loop, Run" not in labels      # dev chapter filtered
        assert all("noise" != r["label"].lower() for r in rows)  # thin dropped
        assert labels == ["Property, Lots", "Home, Smart"]  # chronological by start
        # range collapses single-month chapters.
        home = next(r for r in rows if r["label"] == "Home, Smart")
        assert home["range"] == "2025-07"
        prop = next(r for r in rows if r["label"] == "Property, Lots")
        assert prop["range"] == "2025-05 → 2026-03"

    def test_empty_on_no_chapters(self, monkeypatch):
        import trinity_local.launchpad_data as ld
        import trinity_local.me.chapters as ch
        monkeypatch.setattr(ch, "detect_chapters", lambda: [])
        assert ld._timeline_for_launchpad() == []


def test_timeline_card_binding_in_template():
    """#252 — the launchpad template carries the timeline card binding so the
    page-data field actually renders (browser-verified; this pins it)."""
    from trinity_local.launchpad_template import render_launchpad_html
    html = render_launchpad_html(page_data={}, recent_cards="")
    assert "pageData.timeline" in html
    assert "Your timeline" in html
