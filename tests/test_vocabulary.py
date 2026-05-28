"""Tests for Phase 2.5 vocabulary distillation.

Pure-geometric (+ pure-regex for anchors) scan of the user's prompt
corpus that surfaces three views of distinctive terminology: anchors
(proper-noun recurrence across threads), homonyms (one word, multiple
meanings), synonyms (multiple words, one meaning). Output is markdown at
~/.trinity/memories/vocabulary.md. Read by the chairman as one of the
three thinking core memories.
"""
from __future__ import annotations

import pytest
import numpy as np


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
    return tmp_path


def _plant_node(*, id_, text, embedding):
    from trinity_local.memory import upsert_prompt_node
    from trinity_local.memory.schemas import PromptNode
    upsert_prompt_node(PromptNode(
        id=id_,
        transcript_id=f"t_{id_}",
        provider="claude",
        source_path=f"/fake/{id_}",
        turn_index=0,
        text=text,
        embedding=list(embedding),
        created_at="2026-05-12T00:00:00Z",
        following_assistant_text="",
    ))


class TestTokenize:
    def test_lowercases_and_drops_stopwords(self):
        from trinity_local.vocabulary import _tokenize
        toks = _tokenize("The Task is to refactor the migration script")
        assert "task" in toks
        assert "refactor" in toks
        assert "migration" in toks
        assert "script" in toks
        # Stopwords filtered.
        assert "the" not in toks
        assert "is" not in toks
        assert "to" not in toks

    def test_requires_3_char_minimum(self):
        from trinity_local.vocabulary import _tokenize
        toks = _tokenize("an X two-char ok longer fine")
        assert "two-char" in toks
        assert "longer" in toks
        assert "fine" in toks
        # "an" and "X" too short or stopword.
        assert "an" not in toks


class TestSkipsWhenEmpty:
    def test_skip_when_no_prompts(self, isolated_home):
        from trinity_local.vocabulary import distill_vocabulary
        report = distill_vocabulary()
        assert report["ok"] is False
        assert report.get("skipped") is True

    def test_skip_when_corpus_below_min_freq(self, isolated_home):
        """If every token appears only once, nothing meets the threshold —
        report skipped, don't emit an empty file."""
        from trinity_local.vocabulary import distill_vocabulary
        for i in range(3):
            _plant_node(
                id_=f"p{i}", text=f"unique_word_{i}",
                embedding=np.random.randn(8).tolist(),
            )
        report = distill_vocabulary(min_freq=5)
        assert report["ok"] is False
        assert report.get("skipped") is True


class TestHomonymDetection:
    def test_detects_token_used_in_two_distant_contexts(self, isolated_home):
        """Plant `task` in two semantically distant clusters (5 in one,
        5 in another, far apart in embedding space). Bimodality score
        should be high."""
        # 10 prompts using "task" — first 5 in cluster A, last 5 in cluster B.
        for i in range(5):
            emb = [1.0, 0.0] + [0.0] * 6  # cluster A
            _plant_node(id_=f"a{i}", text=f"task description in domain alpha {i}", embedding=emb)
        for i in range(5):
            emb = [0.0, 1.0] + [0.0] * 6  # cluster B, orthogonal
            _plant_node(id_=f"b{i}", text=f"task progress check in domain beta {i}", embedding=emb)

        from trinity_local.vocabulary import distill_vocabulary
        report = distill_vocabulary(min_freq=5, top_homonyms=10, synonym_threshold=0.99)
        assert report["ok"] is True
        text = (isolated_home / "memories" / "vocabulary.md").read_text()
        # Homonym section must list "task" because its contexts split between
        # two orthogonal centroids.
        assert "task" in text.lower()
        # Bimodality column present.
        assert "bimodality" in text.lower()

    def test_unimodal_token_scores_low(self, isolated_home):
        """A token that always appears in the same context cluster should
        have a low bimodality score (not surface as a homonym)."""
        from trinity_local.vocabulary import (
            _gather_token_contexts, find_homonyms,
        )
        # 8 contexts all very close together → unimodal.
        nodes = []
        for i in range(8):
            from trinity_local.memory.schemas import PromptNode
            jitter = (np.random.randn(8) * 0.01).tolist()
            base = [1.0, 0.0] + [0.0] * 6
            emb = [b + j for b, j in zip(base, jitter)]
            nodes.append(PromptNode(
                id=f"u{i}", transcript_id="x", provider="claude",
                source_path="/x", turn_index=0,
                text=f"unimodal_token always appears together here {i}",
                embedding=emb, created_at="2026-05-12T00:00:00Z",
                following_assistant_text="",
            ))
        contexts = _gather_token_contexts(nodes, min_freq=5)
        homonyms = find_homonyms(contexts, top_n=10)
        for tok, score, _ in homonyms:
            if tok == "unimodal_token":
                assert score < 0.4, f"unimodal token should score < 0.4, got {score:.3f}"


class TestSynonymDetection:
    def test_detects_near_identical_context_pairs(self, isolated_home):
        """Plant `delete` and `remove` always in the same embedding context —
        they should surface as a synonym candidate."""
        # 6 prompts using "delete" all sit in cluster A.
        for i in range(6):
            emb = [1.0, 0.0] + [0.0] * 6
            _plant_node(id_=f"d{i}", text=f"delete the obsolete record {i}", embedding=emb)
        # 6 prompts using "remove" also in cluster A — synonyms.
        for i in range(6):
            emb = [1.0, 0.0] + [0.0] * 6
            _plant_node(id_=f"r{i}", text=f"remove the obsolete record {i}", embedding=emb)

        from trinity_local.vocabulary import distill_vocabulary
        report = distill_vocabulary(min_freq=5, synonym_threshold=0.85)
        assert report["ok"] is True
        text = (isolated_home / "memories" / "vocabulary.md").read_text()
        # Synonym table should pair delete and remove.
        assert "delete" in text.lower() and "remove" in text.lower()
        assert "synonym" in text.lower()


class TestAnchorDetection:
    def test_surfaces_phrase_recurring_across_threads(self, isolated_home):
        """Plant "Trinity Local" across 4 distinct transcripts. The anchor
        section must list it because thread recurrence ≥ default min (3)."""
        from trinity_local.memory import upsert_prompt_node
        from trinity_local.memory.schemas import PromptNode

        for i in range(4):
            upsert_prompt_node(PromptNode(
                id=f"anc_{i}",
                transcript_id=f"thread_{i}",  # distinct threads
                provider="claude",
                source_path=f"/fake/{i}",
                turn_index=0,
                text=f"Working on Trinity Local for council {i}.",
                embedding=[1.0, 0.0] + [0.0] * 6,
                created_at="2026-05-12T00:00:00Z",
                following_assistant_text="",
            ))

        from trinity_local.vocabulary import distill_vocabulary
        report = distill_vocabulary(min_freq=5, anchor_min_threads=3)
        assert report["ok"] is True
        assert report.get("anchors_emitted", 0) >= 1
        text = (isolated_home / "memories" / "vocabulary.md").read_text()
        assert "Trinity Local" in text
        assert "anchors" in text.lower()

    def test_single_thread_recurrence_does_not_anchor(self, isolated_home):
        """If "Trinity Local" only appears in ONE thread (even 5 times), it
        must NOT be surfaced as an anchor — recurrence across threads is
        the load-bearing signal."""
        from trinity_local.memory import upsert_prompt_node
        from trinity_local.memory.schemas import PromptNode

        # 5 turns, all same transcript_id
        for i in range(5):
            upsert_prompt_node(PromptNode(
                id=f"single_{i}",
                transcript_id="one_thread",
                provider="claude",
                source_path="/fake",
                turn_index=i,
                text=f"Trinity Local task step {i}.",
                embedding=[1.0, 0.0] + [0.0] * 6,
                created_at="2026-05-12T00:00:00Z",
                following_assistant_text="",
            ))

        from trinity_local.vocabulary import find_anchors
        from trinity_local.memory.store import iter_prompt_nodes
        nodes = list(iter_prompt_nodes(limit=None))
        anchors = find_anchors(nodes, min_threads=3, top_n=10)
        # "Trinity Local" appears 5 times but in 1 thread — under the gate.
        assert not any(phrase == "Trinity Local" for phrase, *_ in anchors)

    def test_strips_sentence_start_capital(self):
        """"The Task" should not anchor — first word is a stopword that
        happens to start a sentence."""
        from trinity_local.vocabulary import _extract_proper_phrases
        phrases = _extract_proper_phrases("The Task is hard. When something happens.")
        # "Task" alone is fine (after stripping "The"), but "The Task" should not.
        assert not any(p.startswith("The ") for p in phrases)
        # "When something" starts with stopword — should be filtered entirely
        # (no capital word after "When").
        assert "When" not in phrases


class _StubNode:
    """Minimal node for find_anchors unit tests — it reads .text +
    .transcript_id via getattr, so a namespace is enough."""
    def __init__(self, text, transcript_id):
        self.text = text
        self.transcript_id = transcript_id


class TestAnchorPrevalenceCap:
    """#196: a phrase in more than max_thread_fraction of ALL threads is
    boilerplate (Trinity's captured prompt scaffolding recurs in ~75% of
    conversations), not a distinctive anchor — the IDF intuition."""

    def test_ubiquitous_phrase_dropped_as_boilerplate(self):
        # ≥ MIN_THREADS_FOR_PREVALENCE_CAP (20) total threads so the cap is live.
        from trinity_local.vocabulary import find_anchors
        nodes = [_StubNode("Acme dashboard", f"t{i}") for i in range(20)]
        nodes += [_StubNode("Kitchen remodel", f"k{i}") for i in range(8)]
        anchors = find_anchors(nodes, min_threads=3, top_n=10, max_thread_fraction=0.5)
        names = [p for p, *_ in anchors]
        assert "Acme" not in names   # 20/28 = 71% > 50% cap → boilerplate
        assert "Kitchen" in names    # 8/28 = 29% ≤ 50% → kept

    def test_high_cap_keeps_ubiquitous(self):
        # Proves the cap is what drops it: lift the cap, Acme returns.
        from trinity_local.vocabulary import find_anchors
        nodes = [_StubNode("Acme dashboard", f"t{i}") for i in range(20)]
        anchors = find_anchors(nodes, min_threads=3, top_n=10, max_thread_fraction=1.0)
        assert any(p == "Acme" for p, *_ in anchors)

    def test_cap_inactive_below_min_threads(self):
        # Tiny corpus: a phrase in 100% of 4 threads IS the signal, not
        # boilerplate — the cap must not fire below the floor.
        from trinity_local.vocabulary import find_anchors
        nodes = [_StubNode("Acme dashboard", f"t{i}") for i in range(4)]
        anchors = find_anchors(nodes, min_threads=3, top_n=10, max_thread_fraction=0.4)
        assert any(p == "Acme" for p, *_ in anchors)


class TestAnchorThreadAttribution:
    """#196: a node with no transcript_id can't establish cross-thread
    recurrence. The old `transcript_id or node.id` fallback counted each
    such node as its OWN thread, inflating recurrence past the real
    conversation count."""

    def test_missing_transcript_id_does_not_inflate(self):
        from trinity_local.vocabulary import find_anchors
        nodes = [_StubNode("Acme dashboard", None) for _ in range(5)]
        anchors = find_anchors(nodes, min_threads=3, top_n=10, max_thread_fraction=1.0)
        assert not any(p == "Acme" for p, *_ in anchors)


class TestAnchorImperativeBlacklist:
    """#196: imperative / emphasis words that capitalize (sentence start,
    ALL-CAPS emphasis, instruction prose) name no entity and shouldn't
    anchor — the residue left after the prevalence cap."""

    def test_imperative_and_emphasis_caps_not_anchors(self):
        from trinity_local.vocabulary import _extract_proper_phrases
        for w in ("MUST", "Change", "Read", "Fix", "Output", "Every", "One"):
            assert w not in _extract_proper_phrases(f"{w} the thing now"), w
        # Control: a real Title-case entity is untouched.
        assert "Kitchen" in _extract_proper_phrases("Kitchen remodel plan")

    def test_compound_blacklisted_prefix_fully_stripped(self):
        """Review finding #5: stripping only the FIRST blacklisted word let
        compound scaffolding prefixes survive ("For New Users" → "New
        Users"). All leading blacklisted words must be removed."""
        from trinity_local.vocabulary import _extract_proper_phrases
        phrases = _extract_proper_phrases("For New Users the flow matters")
        # "For", "New", "Users" are all blacklisted → nothing capitalized
        # entity-like survives.
        assert not any("New" in p or "Users" in p for p in phrases)
        # A real entity after a compound prefix still survives.
        assert "Kitchen" in _extract_proper_phrases("For New Kitchen design")


class TestVocabularyPath:
    def test_writes_to_memories_vocabulary_md(self, isolated_home):
        from trinity_local.vocabulary import distill_vocabulary
        from trinity_local.state_paths import vocabulary_path

        for i in range(6):
            emb = [1.0, 0.0] + [0.0] * 6
            _plant_node(id_=f"p{i}", text=f"refactor migration script step {i}", embedding=emb)

        report = distill_vocabulary(min_freq=5)
        assert report["ok"] is True
        assert vocabulary_path().exists()
        assert report["path"] == str(vocabulary_path())
