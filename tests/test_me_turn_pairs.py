"""Tests for Stage 0 turn-pair gap extraction.

Council `council_e7560934cb1f1d72` ratified Option A (one batch chairman
call) ONLY because it ships with deterministic post-validators that
catch chairman skim/miscategorization. These tests pin the validators —
without them, Option A is just plausible JSON, not real signal.
"""

from __future__ import annotations

from trinity_local.me.turn_pairs import RejectionSignal


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
        # ids are content hashes now (not the chairman's r_1/r_2 sequence),
        # so assert on count + types, and that every id is a globally-stable
        # r_<hash> (the BOGUS-type row is dropped).
        assert len(sigs) == 2
        assert all(s.type in {"REFRAME", "COMPRESSION"} for s in sigs)
        assert all(s.id.startswith("r_") and len(s.id) > 5 for s in sigs)

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
    def _sig(self, sig_type: str, prompt_id: str = "p1") -> RejectionSignal:
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


class TestStage0BatchFailureGuard:
    """#203: a per-batch chairman failure (timeout returncode==-1, or empty
    stdout) must be detected so the loop aborts instead of accumulating a
    silently-partial corpus that slips past the #194 clobber guard."""

    def _result(self, stdout, returncode):
        from trinity_local.providers import ProviderResult
        return ProviderResult(provider="claude", stdout=stdout, stderr="", returncode=returncode)

    def test_timeout_sentinel_is_a_failure(self):
        from trinity_local.me_builder import _stage0_batch_failed
        assert _stage0_batch_failed(self._result("", -1)) is True

    def test_empty_stdout_is_a_failure(self):
        from trinity_local.me_builder import _stage0_batch_failed
        assert _stage0_batch_failed(self._result("", 0)) is True
        assert _stage0_batch_failed(self._result("   \n  ", 0)) is True

    def test_real_output_is_not_a_failure(self):
        from trinity_local.me_builder import _stage0_batch_failed
        assert _stage0_batch_failed(self._result('[{"type":"REFRAME"}]', 0)) is False


class TestStage0LowEffortExtractor:
    """Stage 0/2 extraction is mechanical → must run at LOW effort
    regardless of the provider's configured level, so the chairman call
    returns under the 8-min per-call timeout (a 40-pair batch at high
    effort timed out on real data; #203 caught it, this prevents it)."""

    def test_extractor_config_forces_low_effort(self):
        import dataclasses
        from trinity_local.config import ProviderConfig
        # Mirror the me_builder construction: replace(effort="low").
        chairman_config = ProviderConfig(
            name="claude", type="cli", enabled=True, label="Claude",
            command=["claude", "-p"], args=[], task_types={"general"},
            model="claude-opus-4-8", effort="high",
        )
        extract_config = dataclasses.replace(chairman_config, effort="low")
        assert extract_config.effort == "low"
        assert chairman_config.effort == "high"  # original unchanged (frozen)
        # And the low-effort flag is what the claude CLI command will inject.
        from trinity_local.providers import _effective_effort
        assert _effective_effort(extract_config) == "low"

    def test_batch_size_is_small_enough_for_timeout(self):
        from trinity_local.me_builder import _STAGE0_BATCH_SIZE
        # Smaller batches keep per-call generation under the timeout.
        assert _STAGE0_BATCH_SIZE <= 20


class TestCorpusFingerprintSkip:
    """#1 skip-if-unchanged: an unchanged corpus → same fingerprint → the
    next build short-circuits with zero model calls."""

    def test_fingerprint_stable_for_same_corpus(self, patch_trinity_home):
        from trinity_local.memory import upsert_prompt_node
        from trinity_local.memory.schemas import PromptNode
        from trinity_local.me_builder import _corpus_fingerprint
        for i in range(3):
            upsert_prompt_node(PromptNode(
                id=f"p{i}", transcript_id="t", provider="claude", source_path="/x",
                turn_index=i, text=f"prompt {i}", embedding=[0.0]*8,
                created_at="2026-05-12T00:00:00Z", following_assistant_text="",
            ))
        fp1 = _corpus_fingerprint()
        fp2 = _corpus_fingerprint()
        assert fp1 == fp2 and ":" in fp1  # deterministic, "count:hash" shape

    def test_fingerprint_changes_when_corpus_grows(self, patch_trinity_home):
        from trinity_local.memory import upsert_prompt_node
        from trinity_local.memory.schemas import PromptNode
        from trinity_local.me_builder import _corpus_fingerprint
        def add(i):
            upsert_prompt_node(PromptNode(
                id=f"p{i}", transcript_id="t", provider="claude", source_path="/x",
                turn_index=i, text=f"prompt {i}", embedding=[0.0]*8,
                created_at="2026-05-12T00:00:00Z", following_assistant_text="",
            ))
        add(0); add(1)
        before = _corpus_fingerprint()
        add(2)
        assert _corpus_fingerprint() != before  # new prompt → new fingerprint


class TestStage0ConcurrencyCap:
    def test_concurrency_cap_is_bounded(self):
        from trinity_local.me_builder import _STAGE0_MAX_CONCURRENCY
        # Capped so we don't spawn a swarm of claude subprocesses.
        assert 1 <= _STAGE0_MAX_CONCURRENCY <= 8
