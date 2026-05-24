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

    def test_resolve_claude_root_uses_explicit_path(self, claude_memory_root, monkeypatch):
        """--claude-memory-path wins over auto-detection."""
        from trinity_local.commands.memory_compare import _resolve_claude_root
        from argparse import Namespace

        ns = Namespace(
            claude_memory_path=str(claude_memory_root),
            claude_project=None,
        )
        assert _resolve_claude_root(ns) == claude_memory_root

    def test_resolve_claude_root_returns_none_when_nothing_exists(self, tmp_path, monkeypatch):
        from trinity_local.commands.memory_compare import _resolve_claude_root
        from argparse import Namespace

        ns = Namespace(
            claude_memory_path=str(tmp_path / "missing"),
            claude_project=None,
        )
        assert _resolve_claude_root(ns) is None

    def test_resolve_claude_root_auto_detect_encodes_cwd_correctly(
        self, tmp_path, monkeypatch
    ):
        """Auto-detect mode: cwd → `~/.claude/projects/<encoded>/memory`.

        Claude Code encodes the project key as `str(path).replace("/", "-")`.
        For an absolute path like `/Users/foo/x` that yields `-Users-foo-x`
        (ONE leading dash from the leading "/"). The first-cut implementation
        prepended `-` unconditionally, producing `--Users-foo-x` and missing
        every real Claude project. Regression: pretend `~/.claude/projects`
        lives under tmp_path, plant the correctly-encoded dir, point cwd
        at a path the encoder will hit, and assert auto-detect lands.
        """
        from trinity_local.commands.memory_compare import _resolve_claude_root
        from argparse import Namespace

        # Stage a fake $HOME so `Path.home() / ".claude/projects/<key>"`
        # lands inside tmp_path. Avoids the bleed into real ~/.claude.
        fake_home = tmp_path / "home"
        fake_home.mkdir()
        monkeypatch.setenv("HOME", str(fake_home))

        # The cwd that the encoder will see — pick a deterministic path
        # under tmp_path so test-host paths don't leak in.
        target_cwd = tmp_path / "some" / "project"
        target_cwd.mkdir(parents=True)
        monkeypatch.chdir(target_cwd)

        encoded = str(target_cwd.resolve()).replace("/", "-")
        project_memory = (
            fake_home / ".claude" / "projects" / encoded / "memory"
        )
        project_memory.mkdir(parents=True)

        ns = Namespace(claude_memory_path=None, claude_project=None)
        resolved = _resolve_claude_root(ns)
        assert resolved == project_memory, (
            f"Auto-detect expected to find {project_memory!s} but got {resolved!s}. "
            "If the bug regresses, you'll see a path with an extra leading dash."
        )

    def test_cli_handler_writes_markdown_report(self, claude_memory_root, tmp_path, monkeypatch, capsys):
        """End-to-end: CLI handler writes a real markdown report and
        prints the headline. The output structure should match what the
        plan's measurement-protocol section specified."""
        from trinity_local.commands.memory_compare import handle_memory_compare
        from argparse import Namespace

        # Isolate TRINITY_HOME so the report doesn't pollute real state
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        out_path = tmp_path / "report.md"
        ns = Namespace(
            claude_memory_path=str(claude_memory_root),
            claude_project=None,
            output=str(out_path),
            top_n=3,
            json=False,
        )
        rc = handle_memory_compare(ns)
        assert rc == 0

        # Markdown report written
        assert out_path.exists()
        report_md = out_path.read_text(encoding="utf-8")
        assert "# Memory comparison" in report_md
        assert "Headline" in report_md
        assert "Coverage" in report_md
        assert "Specificity" in report_md

        # Headline printed to stdout
        captured = capsys.readouterr()
        assert "captured" in captured.out
        assert str(out_path) in captured.out  # "Wrote /path/to/report.md"

    def test_cli_handler_json_mode_omits_markdown_file(self, claude_memory_root, tmp_path, monkeypatch, capsys):
        """--json flag skips disk write, prints serialized report."""
        import json as _json
        from trinity_local.commands.memory_compare import handle_memory_compare
        from argparse import Namespace

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        out_path = tmp_path / "should_not_be_written.md"
        ns = Namespace(
            claude_memory_path=str(claude_memory_root),
            claude_project=None,
            output=str(out_path),
            top_n=5,
            json=True,
        )
        rc = handle_memory_compare(ns)
        assert rc == 0
        assert not out_path.exists()

        captured = capsys.readouterr()
        # stdout is parseable JSON with the expected schema
        parsed = _json.loads(captured.out)
        assert "trinity_count" in parsed
        assert "claude_count" in parsed
        assert "jaccard" in parsed

    def test_cli_handler_no_claude_root_surfaces_hint(self, tmp_path, monkeypatch, capsys):
        """When neither auto-detect nor explicit path resolves, the
        handler must print a hint (not crash, not silently succeed)."""
        from trinity_local.commands.memory_compare import handle_memory_compare
        from argparse import Namespace

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        ns = Namespace(
            claude_memory_path=str(tmp_path / "definitely_missing"),
            claude_project=None,
            output=None,
            top_n=5,
            json=False,
        )
        rc = handle_memory_compare(ns)
        assert rc == 0
        captured = capsys.readouterr()
        assert "Auto-Dream memory directory not found" in captured.out

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
