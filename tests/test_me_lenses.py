"""Tests for me_lenses parser — the launchpad's pair-wise lens cards depend on it."""
from __future__ import annotations

from trinity_local.me_lenses import parse_taste_lenses


SAMPLE_ME = """# /me

## Recurring topics
- Some topic.

## Vocabulary the user uses
- "disaggregated prefill" — splitting prefill from decode — turn [28], [33].
- "context loader" — the program that prefills your data into the KV cache — [40].

## Implicit rejections (the moat)

### Skip the curated list, point at the source
Model frame: "you mean GPQA Diamond. Here's the consolidated picture from current benchmarks."
User substituted: "Measuring the performance of our models on real-world tasks | OpenAI"
Why this matters: trust the locked corpus, not the assistant's tabulation.

### Don't lecture math, audit it
Model frame: "49/51 — the paper is clean."
User substituted: "Section 3.7 still uses the stationary-mean formula."
Why this matters: surface-level pass-rate is not consistency.

## Cross-domain analogies
- AI prefill ↔ identity / cookies: prefill the user's data once.

## Abstract lenses
- Source over synthesis — link the primary doc instead of the curated table.
- Second-level impacts — first-order read is the table stakes, the move is downstream.
"""


class TestParseTasteLenses:
    def test_extracts_rejections_with_titles_and_pairs(self):
        lenses = parse_taste_lenses(SAMPLE_ME)
        assert len(lenses.rejections) == 2
        first = lenses.rejections[0]
        assert first.title == "Skip the curated list, point at the source"
        assert first.model_frame.startswith("you mean GPQA Diamond")
        assert first.user_substituted.startswith("Measuring the performance")
        assert first.why_matters == "trust the locked corpus, not the assistant's tabulation"

    def test_extracts_vocabulary_phrase_and_meaning(self):
        lenses = parse_taste_lenses(SAMPLE_ME)
        phrases = [v.phrase for v in lenses.vocabulary]
        assert "disaggregated prefill" in phrases
        assert "context loader" in phrases
        # Turn references are stripped from the meaning
        prefill = next(v for v in lenses.vocabulary if v.phrase == "disaggregated prefill")
        assert "turn" not in prefill.meaning.lower()
        assert "decode" in prefill.meaning

    def test_extracts_abstract_lenses(self):
        lenses = parse_taste_lenses(SAMPLE_ME)
        assert len(lenses.abstract_lenses) == 2
        statements = [l.statement for l in lenses.abstract_lenses]
        assert any("Source over synthesis" in s for s in statements)
        assert any("Second-level impacts" in s for s in statements)

    def test_share_text_is_paste_ready(self):
        lenses = parse_taste_lenses(SAMPLE_ME)
        share = lenses.rejections[0].to_share_text()
        # All four labeled rows present.
        assert "Skip the curated list" in share
        assert "Model said:" in share
        assert "What I substituted:" in share
        assert "Why this matters:" in share
        # Verbatim quotes preserved (without the wrapping double-quotes).
        assert "GPQA Diamond" in share

    def test_empty_me_returns_empty_lenses(self):
        lenses = parse_taste_lenses("")
        assert lenses.is_empty
        assert lenses.rejections == []
        assert lenses.vocabulary == []
        assert lenses.abstract_lenses == []

    def test_to_dict_includes_per_card_and_section_share_text(self):
        lenses = parse_taste_lenses(SAMPLE_ME)
        out = lenses.to_dict()
        # Each rejection card carries its own share_text for the launchpad copy button.
        assert "share_text" in out["rejections"][0]
        # Vocabulary + abstract-lenses each have a "copy all" payload.
        assert "Vocabulary I keep using" in out["vocabulary_share_text"]
        assert "abstract lenses" in out["abstract_lenses_share_text"].lower()

    def test_malformed_rejection_card_skipped_not_crashed(self):
        # Card missing one of the three labeled rows should be skipped, not poison.
        broken = SAMPLE_ME.replace("Why this matters: trust the locked corpus, not the assistant's tabulation.\n", "")
        lenses = parse_taste_lenses(broken)
        # The well-formed second rejection should still parse.
        titles = [r.title for r in lenses.rejections]
        assert "Don't lecture math, audit it" in titles
