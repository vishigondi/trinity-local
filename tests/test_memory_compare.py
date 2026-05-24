"""Tests for #142 memory-compare Mode 1 (lexical comparison)."""
from __future__ import annotations

import pytest

from trinity_local.memory_compare import compare_memories
from trinity_local.memory_compare.metrics import (
    Claim,
    find_overlaps,
    jaccard_pair,
    specificity,
    tokenize,
)
from trinity_local.memory_compare.parse_claude_memory import parse_claude_memory
from trinity_local.memory_compare.parse_lens import parse_lens


SYNTHETIC_LENS = """# /me

## Recurring topics
- engineering — code quality and architecture decisions

## Vocabulary the user uses
- "ship it" — release readiness mode

## Implicit rejections (the moat)
### Don't add abstraction for hypothetical needs
Model frame: "We should add an interface here for future extensibility."
User substituted: "Three similar lines is better than a premature abstraction."
Why this matters: premature abstraction creates cognitive overhead with no payoff.

### Trust internal callers
Model frame: "Let me validate the input here."
User substituted: "It's an internal helper, don't double-check."
Why this matters: validation at internal boundaries is noise, not safety.

## Cross-domain analogies
- software ↔ construction: front-load design

## Abstract lenses
- infrastructure over interface [strategic]
- locked corpus over forward theory [philosophical]
- concrete examples beat prose explanations [tactical]
"""


SYNTHETIC_CLAUDE_MEMORY_INDEX = """- [Premature abstractions](abstraction.md) — premature abstraction creates cognitive overhead with no payoff
- [Build commands](build.md) — uses pnpm not npm
- [Architecture notes](arch.md) — prefer composition over inheritance
"""


SYNTHETIC_TOPIC_FILE = """---
name: Premature abstractions
description: Three similar lines beats a premature abstraction.
---
The user has rejected several refactor proposals where the abstraction
would have served only one caller. See examples in PR #41, #58, #72.
"""


@pytest.fixture
def claude_memory_root(tmp_path):
    """Build a synthetic Auto-Dream memory tree at tmp_path."""
    root = tmp_path / "claude_memory"
    root.mkdir()
    (root / "MEMORY.md").write_text(SYNTHETIC_CLAUDE_MEMORY_INDEX, encoding="utf-8")
    (root / "abstraction.md").write_text(SYNTHETIC_TOPIC_FILE, encoding="utf-8")
    (root / "build.md").write_text(
        "---\ndescription: Use pnpm install for dependency management.\n---\nBody.\n",
        encoding="utf-8",
    )
    (root / "arch.md").write_text(
        "---\ndescription: Composition over inheritance for new modules.\n---\nBody.\n",
        encoding="utf-8",
    )
    return root


class TestTokenize:
    def test_lowercase_and_punct_stripped(self):
        tokens = tokenize("Infrastructure over Interface!")
        assert tokens == frozenset({"infrastructure", "over", "interface"})

    def test_stopwords_removed(self):
        tokens = tokenize("This is the test of the system")
        # the/is/of dropped as stopwords; "system" / "test" survive
        assert "system" in tokens
        assert "test" in tokens
        assert "the" not in tokens
        assert "is" not in tokens

    def test_single_char_tokens_dropped(self):
        tokens = tokenize("a b c d")
        assert tokens == frozenset()

    def test_trinity_jargon_dropped(self):
        """Trinity / Claude / lens / memory are extremely high-frequency
        in both systems' outputs — they smear Jaccard without indicating
        real alignment. Dropped as domain stopwords."""
        tokens = tokenize("Trinity lens captures the user memory")
        assert "trinity" not in tokens
        assert "lens" not in tokens
        assert "memory" not in tokens
        assert "captures" in tokens  # real signal kept


class TestJaccardPair:
    def test_identical_text_score_1(self):
        a = Claim.from_text("trinity", "infrastructure over interface")
        b = Claim.from_text("claude", "infrastructure over interface")
        assert jaccard_pair(a, b) == 1.0

    def test_no_overlap_score_0(self):
        a = Claim.from_text("trinity", "ship now")
        b = Claim.from_text("claude", "polish forever")
        assert jaccard_pair(a, b) == 0.0

    def test_partial_overlap_proportional(self):
        a = Claim.from_text("trinity", "premature abstraction creates overhead")
        b = Claim.from_text("claude", "premature abstraction wastes time")
        score = jaccard_pair(a, b)
        # tokens overlap: {premature, abstraction}; union ≈ 5; score ≈ 0.4
        assert 0.3 < score < 0.5

    def test_empty_tokens_score_0(self):
        a = Claim.from_text("trinity", "")
        b = Claim.from_text("claude", "")
        assert jaccard_pair(a, b) == 0.0


class TestParseLens:
    def test_extracts_abstract_lenses_and_rejection_whys(self):
        claims = parse_lens(SYNTHETIC_LENS)
        # 3 abstract lenses + 2 rejection whys = 5 total
        assert len(claims) == 5
        assert any("infrastructure over interface" in c for c in claims)
        assert any("premature abstraction" in c.lower() for c in claims)
        assert any("internal boundaries" in c.lower() for c in claims)

    def test_returns_empty_on_empty_input(self):
        assert parse_lens("") == []

    def test_dedupes_identical_text_across_sources(self):
        """If the same statement happens to appear as both an abstract
        lens and a rejection why, it should appear once."""
        lens = """# /me
## Implicit rejections (the moat)
### Title
Model frame: "x"
User substituted: "y"
Why this matters: SAME PRINCIPLE.

## Abstract lenses
- SAME PRINCIPLE [strategic]
"""
        claims = parse_lens(lens)
        # Both surfaces produced "SAME PRINCIPLE" (case-insensitive dedup)
        normalized = [c.lower().strip().rstrip(".") for c in claims]
        assert normalized.count("same principle") == 1


class TestParseClaudeMemory:
    def test_extracts_bullet_descriptions(self, claude_memory_root):
        claims = parse_claude_memory(claude_memory_root)
        # Includes both MEMORY.md bullet descriptions AND topic file
        # frontmatter descriptions (deduped on case-insensitive text).
        assert any("premature abstraction" in c.lower() for c in claims)
        assert any("pnpm" in c.lower() for c in claims)
        assert any("composition" in c.lower() for c in claims)

    def test_missing_file_returns_empty(self, tmp_path):
        # No MEMORY.md in this dir → empty list, not crash
        assert parse_claude_memory(tmp_path) == []

    def test_topic_frontmatter_description_used(self, claude_memory_root):
        claims = parse_claude_memory(claude_memory_root)
        # The "Three similar lines beats a premature abstraction"
        # frontmatter description is distinct from the bullet
        # description and should also be captured.
        assert any("three similar lines" in c.lower() for c in claims)


class TestSpecificity:
    def test_returns_zero_for_empty_list(self):
        result = specificity([])
        assert result["mean_chars"] == 0.0
        assert result["mean_words"] == 0.0

    def test_computes_mean_and_median_chars(self):
        claims = [
            Claim.from_text("trinity", "short"),       # 5
            Claim.from_text("trinity", "medium length"),  # 13
            Claim.from_text("trinity", "this one is the longest of three"),  # 32
        ]
        result = specificity(claims)
        assert result["median_chars"] == 13.0
        assert result["mean_chars"] > 10.0  # roughly (5+13+32)/3 = 16.67


class TestFindOverlaps:
    def test_no_overlaps_returns_empty(self):
        trinity = [Claim.from_text("trinity", "ship velocity matters")]
        claude = [Claim.from_text("claude", "use pnpm for installs")]
        assert find_overlaps(trinity, claude) == []

    def test_finds_clear_match(self):
        trinity = [Claim.from_text("trinity", "premature abstraction creates overhead")]
        claude = [Claim.from_text("claude", "premature abstraction wastes time on hypothetical needs")]
        overlaps = find_overlaps(trinity, claude, threshold=0.2)
        assert len(overlaps) == 1
        t, c, score = overlaps[0]
        assert score > 0.2

    def test_greedy_assignment_each_claim_matches_once(self):
        """If two Trinity claims could both match the same Claude claim,
        only one wins (greedy). Prevents double-counting overlaps."""
        trinity = [
            Claim.from_text("trinity", "premature abstraction is wasteful"),
            Claim.from_text("trinity", "premature abstraction is bad"),
        ]
        claude = [Claim.from_text("claude", "premature abstraction wastes time")]
        overlaps = find_overlaps(trinity, claude, threshold=0.2)
        # Only one match — the Claude claim can't be re-used
        assert len(overlaps) == 1


class TestCompareMemoriesIntegration:
    def test_end_to_end_with_synthetic_inputs(self, claude_memory_root):
        report = compare_memories(
            trinity_lens_text=SYNTHETIC_LENS,
            claude_memory_root=claude_memory_root,
        )
        assert report.trinity_count == 5  # 3 lenses + 2 why-matters
        assert report.claude_count >= 3   # 3 bullets at least
        # "premature abstraction creates cognitive overhead" (Trinity)
        # should overlap with the Claude bullet "premature abstraction
        # creates cognitive overhead with no payoff" — they're near-
        # identical text.
        assert report.overlap_count >= 1
        assert 0.0 <= report.jaccard <= 1.0

    def test_headline_format(self, claude_memory_root):
        report = compare_memories(
            trinity_lens_text=SYNTHETIC_LENS,
            claude_memory_root=claude_memory_root,
        )
        h = report.headline()
        assert "Trinity captured" in h
        assert "Claude Auto-Dream" in h
        assert "overlap" in h
        assert "%" in h

    def test_no_claude_root_returns_trinity_only_report(self):
        report = compare_memories(
            trinity_lens_text=SYNTHETIC_LENS,
            claude_memory_root=None,
        )
        assert report.trinity_count == 5
        assert report.claude_count == 0
        assert report.overlap_count == 0
        assert report.jaccard == 0.0

    def test_to_dict_serializable(self, claude_memory_root):
        report = compare_memories(
            trinity_lens_text=SYNTHETIC_LENS,
            claude_memory_root=claude_memory_root,
        )
        d = report.to_dict()
        # Round-trip through JSON to confirm no non-serializable types
        import json
        roundtripped = json.loads(json.dumps(d))
        assert roundtripped["trinity_count"] == report.trinity_count
        assert "jaccard" in roundtripped
