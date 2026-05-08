"""Tests for me-card PNG export.

Per council_35b2ae198a65b349: the card is the F3 mitigation artifact.
These tests pin that the card renders deterministic-shape output regardless
of whether lens data exists yet (fresh install case) and that the empty
state still produces a valid PNG instead of crashing.
"""

from __future__ import annotations


class TestCardData:
    def test_collect_returns_empty_when_no_lenses(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        from trinity_local.me_card import collect_card_data
        data = collect_card_data()
        assert data.lens_pole_a is None
        assert data.lens_pole_b is None

    def test_collect_picks_lens_with_most_basins(self, tmp_path, monkeypatch):
        # When multiple lenses exist, the strongest = most cross-domain reach
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        from trinity_local.me.basins import me_dir
        from trinity_local.me.pair_mining import LensPair, save_lenses
        narrow = LensPair(
            pole_a="A", pole_b="B", failure_a="x", failure_b="y",
            basins_spanned=["b00", "b01"], verdict="accepted",
        )
        wide = LensPair(
            pole_a="WIDE_A", pole_b="WIDE_B", failure_a="x", failure_b="y",
            basins_spanned=["b00", "b01", "b02", "b03"], verdict="accepted",
        )
        save_lenses([narrow, wide], [])
        from trinity_local.me_card import collect_card_data
        data = collect_card_data()
        assert data.lens_pole_a == "WIDE_A"
        assert data.lens_pole_b == "WIDE_B"


class TestRenderShape:
    def test_render_with_real_lens_produces_valid_png(self):
        from trinity_local.me_card import CardLensData, render_me_card
        data = CardLensData(
            lens_pole_a="leading proxy signal",
            lens_pole_b="official lagging metric",
            failure_a="paranoid pattern-matching",
            failure_b="consensus follower",
            orderings=[("a", "b"), ("c", "d")],
        )
        png = render_me_card(data)
        # PNG signature
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        # 1200×630 produces roughly tens-of-KB at this complexity; sanity check
        assert 5_000 < len(png) < 200_000

    def test_render_empty_state_still_produces_valid_png(self):
        # Fresh install — no lenses yet. Card should still render with
        # the "Run trinity-local me-build" CTA, NOT crash.
        from trinity_local.me_card import CardLensData, render_me_card
        data = CardLensData()  # all fields None / empty
        png = render_me_card(data)
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        assert len(png) > 1000

    def test_render_handles_long_pole_text(self):
        # Wrap logic must not crash on 200-char poles
        from trinity_local.me_card import CardLensData, render_me_card
        long_pole = "x " * 50  # 100 words
        data = CardLensData(
            lens_pole_a=long_pole,
            lens_pole_b="b",
            failure_a="x", failure_b="y",
        )
        png = render_me_card(data)
        assert png[:8] == b"\x89PNG\r\n\x1a\n"


class TestWordWrap:
    def test_short_text_returns_single_line(self):
        # Internal helper: greedy word-wrap. Validate boundary behavior so
        # any future font change doesn't silently break the layout.
        from trinity_local.me_card import _wrap, _load_font
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (100, 100))
        draw = ImageDraw.Draw(img)
        font = _load_font("regular", 20)
        out = _wrap("hello", font, 1000, draw)
        assert out == ["hello"]

    def test_handles_empty_string(self):
        from trinity_local.me_card import _wrap, _load_font
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (100, 100))
        draw = ImageDraw.Draw(img)
        font = _load_font("regular", 20)
        assert _wrap("", font, 1000, draw) == []
