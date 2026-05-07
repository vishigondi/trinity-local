"""Tests for Stage 0 turn-pair gap extraction.

Council `council_e7560934cb1f1d72` ratified Option A (one batch chairman
call) ONLY because it ships with deterministic post-validators that
catch chairman skim/miscategorization. These tests pin the validators —
without them, Option A is just plausible JSON, not real signal.
"""

from __future__ import annotations


class TestRejectionParser:
    def test_valid_signal_types_are_the_four_spec_types(self):
        from trinity_local.me.turn_pairs import VALID_SIGNAL_TYPES
        assert VALID_SIGNAL_TYPES == {"REFRAME", "COMPRESSION", "REDIRECT", "SHARPENING"}

    def test_parse_rejections_skips_unknown_signal_types(self):
        from trinity_local.me.turn_pairs import parse_rejections

        raw = (
            '{"id":"r_1","type":"REFRAME","model_quote":"x","user_substitute":"y","why_signal":"a","prompt_id":"p1"}\n'
            '{"id":"r_2","type":"BOGUS","model_quote":"x","user_substitute":"y","why_signal":"a","prompt_id":"p1"}\n'
            '{"id":"r_3","type":"COMPRESSION","model_quote":"x","user_substitute":"y","why_signal":"a","prompt_id":"p1"}\n'
        )
        sigs = parse_rejections(raw, basins=[])
        assert {s.id for s in sigs} == {"r_1", "r_3"}
        assert all(s.type in {"REFRAME", "COMPRESSION"} for s in sigs)

    def test_parse_rejections_re_tags_basin_from_prompt_id(self):
        # Same trick as Stage 2 — chairman's basin field isn't trusted;
        # we re-attach from the ground-truth basin lookup.
        from trinity_local.me.basins import Basin
        from trinity_local.me.turn_pairs import parse_rejections

        basins = [
            Basin(id="b00", size=1, top_terms=[], centroid=[0.0], prompt_ids=["real_p1"]),
        ]
        raw = '{"id":"r_1","type":"REFRAME","model_quote":"x","user_substitute":"y","why_signal":"a","prompt_id":"real_p1","basin":"b99"}'
        sigs = parse_rejections(raw, basins)
        assert sigs[0].basin == "b00"


class TestValidators:
    def _sig(self, sig_type: str, prompt_id: str = "p1") -> "RejectionSignal":
        from trinity_local.me.turn_pairs import RejectionSignal
        return RejectionSignal(
            id="r_1",
            type=sig_type,
            model_quote="quote",
            user_substitute="substitute",
            why_signal="delta",
            prompt_id=prompt_id,
            basin=None,
        )

    def test_compression_keeps_when_user_text_is_short(self):
        from trinity_local.me.turn_pairs import validate_signals
        index = {"p1": {
            "assistant_text": " ".join(["word"] * 100),  # 100 words
            "user_text": " ".join(["a"] * 5),            # 5 words → ratio 1/20
            "next_user_text": "",
        }}
        kept, rejected = validate_signals([self._sig("COMPRESSION")], index)
        assert len(kept) == 1
        assert not rejected

    def test_compression_drops_when_user_text_too_long(self):
        from trinity_local.me.turn_pairs import validate_signals
        index = {"p1": {
            "assistant_text": " ".join(["word"] * 100),
            "user_text": " ".join(["a"] * 50),  # ratio 1/2 — well above 1/10
            "next_user_text": "",
        }}
        kept, rejected = validate_signals([self._sig("COMPRESSION")], index)
        assert not kept
        assert "ratio" in rejected[0]["reason"]

    def test_redirect_keeps_when_model_is_multi_part_numbered(self):
        from trinity_local.me.turn_pairs import validate_signals
        index = {"p1": {
            "assistant_text": "1. First option\n2. Second option\n3. Third option",
            "user_text": "I'll go with the first",
            "next_user_text": "",
        }}
        kept, _ = validate_signals([self._sig("REDIRECT")], index)
        assert len(kept) == 1

    def test_redirect_keeps_when_model_is_bulleted(self):
        from trinity_local.me.turn_pairs import validate_signals
        index = {"p1": {
            "assistant_text": "- First\n- Second\n- Third",
            "user_text": "first one",
            "next_user_text": "",
        }}
        kept, _ = validate_signals([self._sig("REDIRECT")], index)
        assert len(kept) == 1

    def test_redirect_drops_single_thread_answer(self):
        from trinity_local.me.turn_pairs import validate_signals
        index = {"p1": {
            "assistant_text": "Just one short answer.",
            "user_text": "ok",
            "next_user_text": "",
        }}
        kept, rejected = validate_signals([self._sig("REDIRECT")], index)
        assert not kept
        assert "multi-part" in rejected[0]["reason"]

    def test_sharpening_keeps_when_keywords_overlap(self):
        from trinity_local.me.turn_pairs import validate_signals
        index = {"p1": {
            "assistant_text": "structural advantages emerge from compounding decisions",
            "user_text": "structural inevitability via compounding",
            "next_user_text": "",
        }}
        kept, _ = validate_signals([self._sig("SHARPENING")], index)
        assert len(kept) == 1

    def test_sharpening_drops_when_user_pivots_away(self):
        from trinity_local.me.turn_pairs import validate_signals
        index = {"p1": {
            "assistant_text": "consider the macroeconomic context",
            "user_text": "what about the technical implementation",
            "next_user_text": "",
        }}
        kept, rejected = validate_signals([self._sig("SHARPENING")], index)
        assert not kept
        assert "overlap" in rejected[0]["reason"]

    def test_reframe_keeps_when_substituted_frame_persists_into_next_turn(self):
        from trinity_local.me.turn_pairs import validate_signals
        index = {"p1": {
            "assistant_text": "talk about distribution channels for marketing",
            "user_text": "what about the manufacturing supply chain",
            "next_user_text": "and the manufacturing capacity over time",
        }}
        kept, _ = validate_signals([self._sig("REFRAME")], index)
        assert len(kept) == 1

    def test_reframe_drops_when_user_returns_to_model_frame(self):
        # User pivoted but next turn returned to model's original frame —
        # not a real reframe per spec (substituted frame must persist).
        from trinity_local.me.turn_pairs import validate_signals
        index = {"p1": {
            "assistant_text": "talk about distribution channels for marketing",
            "user_text": "what about manufacturing capacity",
            "next_user_text": "right, back to distribution channels then for marketing",
        }}
        kept, rejected = validate_signals([self._sig("REFRAME")], index)
        assert not kept
        assert "did not persist" in rejected[0]["reason"]

    def test_reframe_lenient_when_no_next_turn_data(self):
        # Without next-turn data, we can't confirm persistence; be lenient
        # rather than dropping signal that might be real.
        from trinity_local.me.turn_pairs import validate_signals
        index = {"p1": {
            "assistant_text": "model frame",
            "user_text": "user reframe",
            "next_user_text": "",
        }}
        kept, _ = validate_signals([self._sig("REFRAME")], index)
        assert len(kept) == 1
