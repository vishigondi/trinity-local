"""Tests for the moves substrate — Phase B of the v2 arc (task #167).

The substrate is the foundation tasks #168-#172 build on. These tests
pin the contract:
  - Move dataclass round-trips through frontmatter (load → write → load
    yields the same Move)
  - Bayesian helpers update alpha/beta atomically + posterior matches
  - store.read_move / write_move / list_moves / archive_move work
    end-to-end on isolated TRINITY_HOME
  - Cold install (no moves directory yet) doesn't crash list_moves()
  - SKILL.md frontmatter parser handles the YAML subset Trinity uses
    (scalars, inline lists, multiline | block scalars, quoted strings)
  - gate.py scaffolding has the four tier functions + run_gate
    dispatcher in place (with NotImplementedError stubs — bodies land
    in #168-#170; the wiring contract is what this test pins)
"""
from __future__ import annotations

import pytest


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    """Isolate ~/.trinity/ for tests so the writes don't pollute the
    real install + concurrent tests don't fight."""
    monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
    return tmp_path


# ─── Frontmatter parser ────────────────────────────────────────────


class TestFrontmatterParser:
    """The custom YAML subset Trinity ships with — keeps runtime deps
    at 3 (Pillow / mcp / numpy). Adding PyYAML for the SKILL.md subset
    was the wrong tradeoff (see frontmatter.py docstring)."""

    def test_split_document_no_frontmatter(self):
        from trinity_local.moves.frontmatter import split_document
        fm, body = split_document("just markdown\nno frontmatter\n")
        assert fm is None
        assert body == "just markdown\nno frontmatter\n"

    def test_split_document_simple(self):
        from trinity_local.moves.frontmatter import split_document
        fm, body = split_document("---\nname: foo\n---\nbody here\n")
        assert fm == "name: foo"
        assert body == "body here\n"

    def test_load_scalar_types(self):
        from trinity_local.moves.frontmatter import load_frontmatter
        data = load_frontmatter(
            "name: foo\n"
            "count: 42\n"
            "score: 0.85\n"
            "active: true\n"
            "missing: null\n"
            "quoted: \"with spaces\"\n"
        )
        assert data["name"] == "foo"
        assert data["count"] == 42
        assert data["score"] == 0.85
        assert data["active"] is True
        assert data["missing"] is None
        assert data["quoted"] == "with spaces"

    def test_load_inline_list(self):
        from trinity_local.moves.frontmatter import load_frontmatter
        data = load_frontmatter(
            'tags: ["a", "b", "c"]\n'
            "scores: [0.1, 0.2, 0.3]\n"
            "ids: [\"r_001\", \"r_042\"]\n"
        )
        assert data["tags"] == ["a", "b", "c"]
        assert data["scores"] == [0.1, 0.2, 0.3]
        assert data["ids"] == ["r_001", "r_042"]

    def test_load_multiline_block_scalar(self):
        from trinity_local.moves.frontmatter import load_frontmatter
        data = load_frontmatter(
            "description: |\n"
            "  line one\n"
            "  line two\n"
            "  line three\n"
            "name: foo\n"
        )
        assert data["description"] == "line one\nline two\nline three"
        assert data["name"] == "foo"

    def test_dump_round_trip(self):
        """load → dump → load yields the same dict (for the subset
        Trinity actually uses). This is the strongest guard against
        SKILL.md drift between Trinity reads and Trinity writes."""
        from trinity_local.moves.frontmatter import load_frontmatter, dump_frontmatter
        original = {
            "name": "tighten-after-bullet-list",
            "description": "line one\nline two",
            "trinity_alpha": 8,
            "trinity_beta": 2,
            "trinity_posterior": 0.8,
            "trinity_promoted_from": ["r_001", "r_042"],
            "trinity_demoted_at": None,
        }
        text = dump_frontmatter(original)
        reloaded = load_frontmatter(text)
        assert reloaded == original


# ─── Move dataclass ────────────────────────────────────────────────


class TestMoveDataclass:
    def test_defaults_are_uninformative_prior(self):
        """Day-1 Move with no execution history: alpha=1, beta=1,
        posterior=0.5. The Beta-Binomial uninformative prior."""
        from trinity_local.moves.schemas import Move
        m = Move(name="foo", description="bar")
        assert m.trinity_alpha == 1
        assert m.trinity_beta == 1
        assert m.posterior == 0.5
        assert m.trinity_execution_count == 0
        assert m.is_active is False  # no promoted_at yet
        assert m.is_archived is False

    def test_posterior_after_successes(self):
        from trinity_local.moves.schemas import Move
        m = Move(name="foo", description="bar")
        for _ in range(7):
            m.record_success()
        m.record_failure()
        # alpha=1+7=8, beta=1+1=2 → posterior = 8/10 = 0.8
        assert m.trinity_alpha == 8
        assert m.trinity_beta == 2
        assert m.posterior == pytest.approx(0.8)
        assert m.trinity_execution_count == 8

    def test_is_active_requires_promoted_not_demoted(self):
        from trinity_local.moves.schemas import Move
        m = Move(name="foo", description="bar")
        assert m.is_active is False
        m.trinity_promoted_at = "2026-05-26T12:00:00+00:00"
        assert m.is_active is True
        m.trinity_demoted_at = "2026-05-27T12:00:00+00:00"
        assert m.is_active is False
        assert m.is_archived is True

    def test_frontmatter_round_trip(self):
        """Move → frontmatter dict → Move yields equivalent state. The
        load-bearing serialization invariant."""
        from trinity_local.moves.schemas import Move
        original = Move(
            name="tighten-after-bullet-list",
            description="When the model returns 5+ bullets, compress.",
            trinity_promoted_from=["r_001", "r_042"],
            trinity_basin_id="b03",
            trinity_promoted_at="2026-05-23T14:22:00+00:00",
            trinity_alpha=8,
            trinity_beta=2,
            trinity_execution_count=8,
            trinity_t3_chairman_score=0.84,
            trinity_eval_baseline=0.79,
            trinity_success_contexts=["b03", "b07"],
            trinity_generalizability_score=0.6,
            trinity_lens_tensions_addressed=2,
            body="The actual move's procedure here.",
        )
        fm = original.to_frontmatter()
        reloaded = Move.from_frontmatter(fm, body=original.body)
        assert reloaded == original

    def test_from_frontmatter_tolerant_of_missing_optional_fields(self):
        """A fresh move from `dream` provides only name + description +
        trinity_promoted_from + trinity_basin_id. Everything else gets
        defaults. Without this tolerance, dream couldn't propose
        candidates without redundantly filling in alpha=1, beta=1, etc."""
        from trinity_local.moves.schemas import Move
        minimal = {
            "name": "fresh-from-dream",
            "description": "candidate",
            "trinity_promoted_from": ["r_001"],
            "trinity_basin_id": "b00",
        }
        m = Move.from_frontmatter(minimal)
        assert m.trinity_alpha == 1
        assert m.trinity_beta == 1
        assert m.body == ""

    def test_from_frontmatter_rejects_missing_required(self):
        """SKILL.md spec requires name + description. Either missing →
        error. Critical because the SKILL.md loader in other tools
        (Claude Code etc.) errors the same way; we shouldn't be more
        permissive than the spec."""
        from trinity_local.moves.schemas import Move
        with pytest.raises(ValueError, match="missing required SKILL.md fields"):
            Move.from_frontmatter({"name": "foo"})
        with pytest.raises(ValueError, match="missing required SKILL.md fields"):
            Move.from_frontmatter({"description": "bar"})

    def test_from_frontmatter_ignores_extra_fields(self):
        """Other tools (Cursor, Cline) may add their own custom
        frontmatter fields. SKILL.md spec allows this. Trinity must
        ignore them, not crash."""
        from trinity_local.moves.schemas import Move
        m = Move.from_frontmatter({
            "name": "foo",
            "description": "bar",
            "cursor_pinned": True,
            "cline_priority": 5,
        })
        assert m.name == "foo"


# ─── Store (read/write/list/archive) ────────────────────────────────


class TestStore:
    def test_cold_install_list_returns_empty(self, isolated_home):
        """First-run state: ~/.trinity/moves/ doesn't exist yet.
        list_moves must return [] without crashing."""
        from trinity_local.moves.store import list_moves
        assert list_moves() == []
        assert list_moves(archived=True) == []

    def test_write_then_read_round_trip(self, isolated_home):
        from trinity_local.moves.schemas import Move
        from trinity_local.moves.store import read_move, write_move
        original = Move(
            name="research-then-tighten",
            description="Sequence research + compression",
            trinity_basin_id="b03",
            trinity_alpha=4,
            trinity_beta=1,
            trinity_execution_count=4,
            body="The procedure here.\n\nMore body text.",
        )
        path = write_move(original)
        assert path.exists()
        assert path.name == "SKILL.md"
        assert path.parent.name == "research-then-tighten"
        reloaded = read_move("research-then-tighten")
        assert reloaded == original

    def test_list_returns_written_moves(self, isolated_home):
        from trinity_local.moves.schemas import Move
        from trinity_local.moves.store import list_moves, write_move
        write_move(Move(name="move-a", description="A"))
        write_move(Move(name="move-b", description="B"))
        write_move(Move(name="move-c", description="C"))
        moves = list_moves()
        names = sorted(m.name for m in moves)
        assert names == ["move-a", "move-b", "move-c"]

    def test_archive_removes_from_active_list(self, isolated_home):
        """archive_move() demotes a move to the archive dir AND removes
        it from the active list. Demotion is observable via list_moves."""
        from trinity_local.moves.schemas import Move
        from trinity_local.moves.store import (
            archive_move,
            list_moves,
            write_move,
        )
        write_move(Move(
            name="drifty-move",
            description="A move that will drift",
            trinity_promoted_at="2026-05-20T00:00:00+00:00",
            body="original procedure",
        ))
        # Active list shows it
        assert [m.name for m in list_moves()] == ["drifty-move"]
        # Demote
        archive_move(
            "drifty-move",
            tier="T3",
            reason="Chairman score dropped below baseline 3 cycles in a row",
        )
        # Active list is now empty; archive has the entry
        assert list_moves() == []
        archived = list_moves(archived=True)
        assert [m.name for m in archived] == ["drifty-move"]
        demoted = archived[0]
        assert demoted.trinity_demoted_by_tier == "T3"
        assert demoted.trinity_demoted_at is not None
        # The demotion reason landed in the body for debuggability
        assert "Chairman score dropped" in demoted.body
        assert "Demoted at" in demoted.body

    def test_active_list_excludes_archive_subdirectory(self, isolated_home):
        """The archive/ subdir under moves/ must not show up in
        list_moves() as a candidate move. Without this, every archived
        slug would re-appear in the active enumeration after demotion."""
        from trinity_local.moves.schemas import Move
        from trinity_local.moves.store import (
            archive_move,
            list_moves,
            write_move,
        )
        write_move(Move(
            name="will-be-demoted",
            description="X",
            trinity_promoted_at="2026-05-26T00:00:00+00:00",
        ))
        archive_move("will-be-demoted", tier="T1", reason="lexical drift")
        # The archive/ directory now exists. list_moves() must NOT
        # surface it as if it were a move slug.
        assert list_moves() == []

    def test_read_missing_move_raises(self, isolated_home):
        from trinity_local.moves.store import read_move
        with pytest.raises(FileNotFoundError):
            read_move("does-not-exist")

    def test_slug_handles_special_chars(self, isolated_home):
        """A move named 'Tighten After Bullet List!' should land at
        ~/.trinity/moves/tighten-after-bullet-list/ — kebab-cased,
        special chars dropped."""
        from trinity_local.moves.schemas import Move
        from trinity_local.moves.store import write_move
        path = write_move(Move(
            name="Tighten After Bullet List!",
            description="X",
        ))
        assert path.parent.name == "tighten-after-bullet-list"


# ─── Gate scaffolding ──────────────────────────────────────────────


class TestGateScaffolding:
    """The four-tier Bayesian gate. T1+T2 shipped #168. T3 lands #169,
    T4 lands #170. The scaffolding contract is what this class pins."""

    def test_all_four_tier_functions_exist(self):
        from trinity_local.moves import gate
        assert callable(gate.T1_lexical)
        assert callable(gate.T2_embedding)
        assert callable(gate.T3_chairman)
        assert callable(gate.T4_posterior)
        assert callable(gate.run_gate)

    def test_t3_t4_raise_not_implemented_until_filled_in(self):
        """T1+T2 are implemented (#168). T3 + T4 still raise
        NotImplementedError pointing at their task numbers — that's the
        wiring contract for the followup tasks."""
        from trinity_local.moves import gate
        from trinity_local.moves.schemas import Move
        m = Move(name="foo", description="bar")
        with pytest.raises(NotImplementedError, match="task #169"):
            gate.T3_chairman(m, rejection_corpus=[])
        with pytest.raises(NotImplementedError, match="task #170"):
            gate.T4_posterior(m)

    def test_tier_result_shape(self):
        """The TierResult dataclass exposes tier / passed / score /
        threshold / reason. Logging surfaces (dream_rejections.jsonl
        per #174) read these field names directly."""
        from trinity_local.moves.gate import TierResult
        r = TierResult(
            tier="T1",
            passed=True,
            score=0.85,
            threshold=0.3,
            reason="Jaccard 0.85 against 5 accepted patterns",
        )
        assert r.tier == "T1"
        assert r.passed is True
        assert r.score == 0.85
        assert r.threshold == 0.3
        assert "Jaccard" in r.reason


# ─── Gate T1 lexical (#168) ─────────────────────────────────────────


class TestT1Lexical:
    """Word n-gram Jaccard against accepted patterns. Pure stdlib,
    deterministic, no numpy/mlx. Cold-install + empty-input semantics
    are load-bearing — they're what makes the gate usable on day-1
    before any rejection-corpus signal has accumulated."""

    def test_cold_install_passes_vacuously(self):
        """With no accepted patterns to compare against, T1 passes with
        score=1.0. Rationale: cold-install / new-basin case has no
        evidence FOR the candidate, but also no evidence AGAINST. T2
        and T3 do the actual gating; T1 only filters when it has
        signal to work with."""
        from trinity_local.moves.gate import T1_lexical
        from trinity_local.moves.schemas import Move
        m = Move(
            name="foo",
            description="tighten verbose responses into 2-3 sentence summaries",
            body="Drop bullet lists; restate as paragraph.",
        )
        r = T1_lexical(m, accepted_patterns=[])
        assert r.passed is True
        assert r.score == 1.0
        assert "vacuously passes" in r.reason

    def test_passes_when_three_patterns_match(self):
        """The pass criterion is min_matches=3 with Jaccard ≥ 0.3 each.
        Construct a candidate that shares enough n-grams with 3+ patterns."""
        from trinity_local.moves.gate import T1_lexical
        from trinity_local.moves.schemas import Move
        m = Move(
            name="tighten-bullets",
            description="tighten verbose bullet lists into short paragraphs",
            body="",
        )
        # Three patterns sharing tighten/verbose/bullet vocab
        patterns = [
            "tighten verbose bullet lists into short paragraphs please",
            "compress verbose bullet lists into short paragraphs always",
            "tighten verbose bullet lists into short paragraphs nicely",
        ]
        r = T1_lexical(m, accepted_patterns=patterns, threshold=0.3, min_matches=3)
        assert r.passed is True
        assert r.score > 0.3

    def test_fails_when_no_pattern_overlaps(self):
        """Candidate that shares no n-grams with any accepted pattern
        fails T1. Score is 0.0 (max Jaccard across 0-overlap patterns)."""
        from trinity_local.moves.gate import T1_lexical
        from trinity_local.moves.schemas import Move
        m = Move(
            name="totally-unrelated",
            description="convert markdown tables to LaTeX siunitx",
            body="",
        )
        patterns = [
            "tighten verbose bullet lists into short paragraphs",
            "compress redundant prose into single sentences",
            "drop trailing whitespace from each line",
        ]
        r = T1_lexical(m, accepted_patterns=patterns, threshold=0.3, min_matches=3)
        assert r.passed is False
        assert r.score < 0.3

    def test_partial_match_below_min_matches_fails(self):
        """Even with a single 90% match, T1 fails if min_matches isn't
        cleared. The "eerily similar to one outlier" case — Trinity
        wants pattern-class evidence, not one-shot matches."""
        from trinity_local.moves.gate import T1_lexical
        from trinity_local.moves.schemas import Move
        m = Move(
            name="x",
            description="tighten verbose bullet lists into short paragraphs",
            body="",
        )
        patterns = [
            "tighten verbose bullet lists into short paragraphs",  # 100% match
            "completely unrelated text about cats",
            "another unrelated text about weather forecasts",
        ]
        r = T1_lexical(m, accepted_patterns=patterns, threshold=0.3, min_matches=3)
        assert r.passed is False
        # Score still surfaces the one strong match — for debugging
        assert r.score >= 0.9


class TestT1LexicalHelpers:
    """Internal helpers — tokenization + Jaccard + cosine. Pinned
    because the gate's correctness depends on these being deterministic
    + locale-independent."""

    def test_tokenize_strips_punctuation_and_lowercases(self):
        from trinity_local.moves.gate import _tokenize
        assert _tokenize("Hello, World! 123.") == ["hello", "world", "123"]

    def test_tokenize_drops_empty(self):
        from trinity_local.moves.gate import _tokenize
        assert _tokenize("--- ... !!!") == []

    def test_ngrams_short_text_falls_back_to_unigrams(self):
        """A text with fewer than n words returns its unigrams instead
        of an empty set — better than empty for Jaccard semantics."""
        from trinity_local.moves.gate import _word_ngrams
        result = _word_ngrams("hello world", n=3)
        assert result == {"hello", "world"}

    def test_ngrams_normal_case(self):
        from trinity_local.moves.gate import _word_ngrams
        result = _word_ngrams("the quick brown fox jumps", n=3)
        assert result == {"the quick brown", "quick brown fox", "brown fox jumps"}

    def test_jaccard_known_values(self):
        from trinity_local.moves.gate import _jaccard
        assert _jaccard({"a", "b"}, {"a", "b"}) == 1.0
        assert _jaccard({"a", "b"}, {"c", "d"}) == 0.0
        # |∩|=1, |∪|=3, Jaccard = 1/3
        assert abs(_jaccard({"a", "b"}, {"b", "c"}) - 1/3) < 1e-9

    def test_jaccard_empty_returns_zero(self):
        """Both-empty case must not divide by zero. Returns 0.0 (no
        signal extractable from empty sets)."""
        from trinity_local.moves.gate import _jaccard
        assert _jaccard(set(), set()) == 0.0

    def test_cosine_orthogonal_is_zero(self):
        from trinity_local.moves.gate import _cosine
        assert _cosine([1.0, 0.0], [0.0, 1.0]) == 0.0

    def test_cosine_identical_is_one(self):
        from trinity_local.moves.gate import _cosine
        # Within float tolerance
        assert abs(_cosine([1.0, 2.0, 3.0], [1.0, 2.0, 3.0]) - 1.0) < 1e-9

    def test_cosine_dim_mismatch_raises(self):
        from trinity_local.moves.gate import _cosine
        with pytest.raises(ValueError, match="same length"):
            _cosine([1.0, 2.0], [1.0, 2.0, 3.0])

    def test_cosine_zero_vector_is_zero(self):
        """Zero-norm vector returns 0.0 (no signal). The chosen
        semantic — could also raise; 0.0 lets downstream gates fail
        normally instead of crashing."""
        from trinity_local.moves.gate import _cosine
        assert _cosine([0.0, 0.0, 0.0], [1.0, 2.0, 3.0]) == 0.0


# ─── Gate T2 embedding (#168) ───────────────────────────────────────


class TestT2Embedding:
    """Cosine similarity vs basin centroid. Uses the existing
    embeddings backend (MLX when available, TF-IDF fallback). The
    fallback is what makes these tests run deterministically — MLX
    might not be installed in CI."""

    def test_no_centroid_fails_with_actionable_reason(self):
        """When the candidate's claimed basin doesn't exist in
        topics.json yet, T2 fails with a reason that names the fix
        (run dream to rebuild basins)."""
        from trinity_local.moves.gate import T2_embedding
        from trinity_local.moves.schemas import Move
        m = Move(name="x", description="y", trinity_basin_id="b99")
        r = T2_embedding(m, basin_centroid=None)
        assert r.passed is False
        assert r.score == 0.0
        assert "trinity-local dream" in r.reason

    def test_dim_mismatch_fails_with_actionable_reason(self):
        """Pinned: if topics.json was built with a different embedding
        dim (e.g. user swapped backend after a partial install), the
        gate fails loudly instead of crashing."""
        from trinity_local.moves.gate import T2_embedding
        from trinity_local.moves.schemas import Move
        m = Move(name="x", description="y", trinity_basin_id="b00")
        # Wrong-sized centroid — only 5 dims when the backend produces 768
        r = T2_embedding(m, basin_centroid=[0.1, 0.2, 0.3, 0.4, 0.5])
        assert r.passed is False
        assert "dimension mismatch" in r.reason
        assert "re-run dream" in r.reason

    def test_perfect_alignment_passes(self):
        """T2 passes when the candidate embedding aligns with the basin
        centroid. Easiest pin: embed the move's text, use that exact
        vector as the basin centroid — cosine = 1.0."""
        from trinity_local.embeddings import embed
        from trinity_local.moves.gate import T2_embedding, _candidate_text
        from trinity_local.moves.schemas import Move
        m = Move(name="x", description="tighten bullet lists", body="drop verbose")
        # Self-similarity = 1.0
        centroid = embed(_candidate_text(m))
        r = T2_embedding(m, basin_centroid=centroid, threshold=0.7)
        assert r.passed is True
        assert r.score > 0.99  # ≈1.0 modulo any float-drift in cosine math

    def test_dissimilar_fails(self):
        """A negative-aligned centroid (text about an entirely different
        topic) makes cosine drop below threshold. T2 fails."""
        from trinity_local.embeddings import embed
        from trinity_local.moves.gate import T2_embedding
        from trinity_local.moves.schemas import Move
        m = Move(
            name="x",
            description="convert markdown tables to LaTeX siunitx",
            body="",
        )
        # Centroid embedded from a totally different domain
        centroid = embed("recipe for chocolate chip cookies with walnuts")
        r = T2_embedding(m, basin_centroid=centroid, threshold=0.7)
        # The TF-IDF fallback could yield arbitrary scores, but for
        # this clearly disjoint pair we expect to fail.
        assert r.passed is False or r.score < 0.7


# ─── Gate dispatcher with real T1/T2 ────────────────────────────────


class TestRunGateWithT1T2:
    """run_gate now actually executes T1+T2 (T3 raises). Verify the
    short-circuit behavior — T2 doesn't run when T1 fails, and T3
    raises only on candidates that survived T1+T2."""

    def test_t1_failure_short_circuits(self):
        """T1 fails → T2 + T3 don't run. Returned list contains only
        the T1 result."""
        from trinity_local.moves.gate import run_gate
        from trinity_local.moves.schemas import Move
        m = Move(name="x", description="completely unrelated text", body="")
        # Patterns that share no n-grams — T1 fails
        patterns = ["one two three four five", "six seven eight nine ten"]
        results = run_gate(m, accepted_patterns=patterns, basin_centroid=None)
        assert len(results) == 1
        assert results[0].tier == "T1"
        assert results[0].passed is False

    def test_t1_pass_t2_fail_short_circuits_before_t3(self):
        """T1 passes (cold-install vacuous pass) but T2 fails (no
        centroid) → T3 doesn't run, so the NotImplementedError doesn't
        surface."""
        from trinity_local.moves.gate import run_gate
        from trinity_local.moves.schemas import Move
        m = Move(name="x", description="some text", body="")
        results = run_gate(m, accepted_patterns=[], basin_centroid=None)
        assert len(results) == 2
        assert results[0].tier == "T1" and results[0].passed is True
        assert results[1].tier == "T2" and results[1].passed is False

    def test_t1_t2_pass_then_t3_raises(self):
        """When T1+T2 both pass, T3 runs — and currently raises
        NotImplementedError (pending #169). This pins the wiring:
        the followup task lands as a drop-in replacement for T3.
        Once #169 ships, this test will assert the new T3 behavior."""
        from trinity_local.embeddings import embed
        from trinity_local.moves.gate import _candidate_text, run_gate
        from trinity_local.moves.schemas import Move
        m = Move(name="x", description="tighten bullet lists", body="drop verbose")
        # Self-similar centroid so T2 passes deterministically
        centroid = embed(_candidate_text(m))
        with pytest.raises(NotImplementedError, match="task #169"):
            run_gate(
                m,
                accepted_patterns=[],
                basin_centroid=centroid,
                rejection_corpus=[{"id": "r_001"}],
            )


# ─── State paths ───────────────────────────────────────────────────


class TestStatePaths:
    def test_moves_dir_creates_under_trinity_home(self, isolated_home):
        from trinity_local.state_paths import moves_dir
        path = moves_dir()
        assert path == isolated_home / "moves"
        assert path.exists()
        assert path.is_dir()

    def test_moves_archive_dir_under_moves_dir(self, isolated_home):
        from trinity_local.state_paths import moves_archive_dir, moves_dir
        archive = moves_archive_dir()
        assert archive == moves_dir() / "archive"
        assert archive.exists()
