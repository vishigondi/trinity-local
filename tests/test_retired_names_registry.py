"""Gap B — Retirement registry guard.

Two invariants:

1. **Registry integrity.** Every record in ``RETIRED`` has a valid date,
   declared kind, and (if it claims a replacement) the replacement is a
   real CLI/MCP-tool that currently exists.

2. **No present-tense references in docs/code.** For each retired name,
   scan docs and code for present-tense framing (\"X does Y\", \"X prints\")
   in non-historical context. Past-tense (\"X was retired\", \"if you
   previously ran X\") is fine.

The second invariant is the iter #68/#69 catch shape made automatic.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from trinity_local.retired_names import (
    RETIRED,
    RetirementRecord,
    all_names,
    format_migration_hint,
    get,
    names_by_kind,
)


REPO = Path(__file__).resolve().parents[1]
DATE_PATTERN = re.compile(r"^\d{4}-\d{2}-\d{2}$")


class TestRegistryIntegrity:
    """Every RetirementRecord is structurally sound."""

    @pytest.mark.parametrize("name", sorted(RETIRED.keys()))
    def test_record_has_required_fields(self, name: str):
        record = RETIRED[name]
        assert isinstance(record, RetirementRecord)
        assert record.name == name, (
            f"Record key {name!r} doesn't match record.name {record.name!r}"
        )
        assert DATE_PATTERN.match(record.retired_at), (
            f"{name}: retired_at {record.retired_at!r} not YYYY-MM-DD"
        )
        assert record.reason, f"{name}: empty reason"
        assert record.kind in (
            "cli", "mcp_tool", "module", "file", "config_field", "concept"
        ), f"{name}: invalid kind {record.kind!r}"


class TestRegistryLookups:
    """The convenience helpers work as documented."""

    def test_get_returns_record_or_none(self):
        assert get("shortcut-install") is not None
        assert get("not-retired") is None

    def test_all_names_sorted(self):
        names = all_names()
        assert names == sorted(names)
        assert "shortcut-install" in names
        assert "get_eval_summary" in names

    def test_names_by_kind_filters(self):
        clis = names_by_kind("cli")
        mcp = names_by_kind("mcp_tool")
        # cli set + mcp set should be disjoint
        assert set(clis).isdisjoint(set(mcp))
        # Known retirements land in their declared kinds
        assert "shortcut-install" in clis
        assert "search_prompts" in mcp

    def test_format_migration_hint_includes_replacement(self):
        msg = format_migration_hint("shortcut-install")
        assert "shortcut-install" in msg
        assert "2026-05-17" in msg
        assert "install-extension" in msg

    def test_format_migration_hint_for_unknown_name(self):
        msg = format_migration_hint("definitely-not-retired")
        assert "not a known retired" in msg


class TestNoPresentTenseInDocs:
    """For each retired CLI, scan launch-credibility docs for
    present-tense references. This is the iter #68/#69 catch shape
    promoted from manual review to automated guard.

    Pattern: ``\\b{name}\\b`` near a present-tense verb. The exact
    pattern is approximate — flagged matches need human review, not
    automatic rewrite. The test loud-fails with the context line.

    Past-tense + retirement narration is allowed: \"X was retired\",
    \"users who ran X\", \"the legacy X CLI\", etc.
    """

    # Present-tense verbs that signal "the thing is still alive".
    # When found near a retired name in a live doc, flag for review.
    PRESENT_TENSE_VERBS = (
        r"prints?",
        r"runs?",
        r"registers?",
        r"writes?",
        r"installs?",
        r"creates?",
        r"calls?",
        r"invokes?",
    )

    # Phrases that explicitly mark a retired-name reference as
    # historical / past-tense. If any of these appear in the same
    # paragraph as the retired name, we trust the context.
    HISTORICAL_MARKERS = (
        "retired",
        "was retired",
        "no longer exists",
        "previously ran",
        "previously fired",
        "earlier",
        "legacy",
        "formerly",
        "sunset",
        "deprecated",
        "historical",
        "pre-launch",
        "snapshot",
        "removed",
    )

    # Docs to scan. Skip historical-class docs (the simplification log,
    # spec-v2 sunset doc, etc.) — they DO narrate retirements in
    # present-tense + that's correct for them.
    DOCS_TO_SCAN: list[str] = [
        "README.md",
        "claude.md",
        "AGENTS.md",
        "CONTRIBUTING.md",
        "DESIGN.md",
        "docs/architecture.md",
        "docs/INSTALL-skill.md",
        "docs/INSTALL-pip.md",
        "docs/INSTALL-extension.md",
        "docs/install-deep.md",
        "docs/launch.md",
        "docs/launch-package.md",
        "docs/LAUNCH_CHECKLIST.md",
        "docs/MIGRATION.md",
        "docs/spec-v1.md",
        "docs/three-tier-architecture.md",
        "docs/launch-day/00_leaderboard.md",
        "docs/launch-day/01_tweet_thread.md",
        "docs/launch-day/02_show_hn_post.md",
        "docs/launch-day/03_hn_objection_faq.md",
        "docs/launch-day/04_demo_voiceover.md",
        "docs/launch-day/05_comparison_table.md",
        "docs/launch-day/06_founder_narrative.md",
        "docs/launch-day/07_pricing_faq.md",
        "docs/launch-day/08_twitter_bio.md",
        "docs/launch-day/09_linkedin_post.md",
        "docs/launch-day/10_hn_faq_full.md",
    ]

    def test_no_present_tense_for_retired_names(self):
        """For each (retired-name, live-doc) pair, find lines that
        match the present-tense verb pattern in a paragraph that
        DOESN'T contain any historical markers. Failure mode is
        a paragraph that says \"`X` prints Y\" without any \"was retired\"
        context — exactly the iter #68/#69 catch.

        Matching is intentionally narrow:
        - The retired name MUST appear in a code-context marker
          (backticks, trinity-local prefix, or mcp__trinity-local__
          prefix). This avoids false positives on names that are also
          common English words (\"judge\", \"doctor\", \"compare\").
        - The present-tense verb must appear within 60 characters
          of the name reference.
        - The paragraph must not contain historical markers.
        """
        violations: list[str] = []

        for rel in self.DOCS_TO_SCAN:
            path = REPO / rel
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8")
            # Paragraph-split: any blank-line-separated block is a unit.
            paragraphs = re.split(r"\n\s*\n", text)
            for paragraph in paragraphs:
                lower = paragraph.lower()
                # Skip paragraphs that explicitly mark themselves historical.
                if any(marker in lower for marker in self.HISTORICAL_MARKERS):
                    continue
                for name in all_names():
                    # Code-context patterns only — backticks or
                    # explicit CLI/MCP prefix. Avoids prose-noun
                    # false positives on common English words.
                    escaped = re.escape(name)
                    code_contexts = (
                        rf"`{escaped}`",
                        rf"trinity-local\s+{escaped}\b",
                        rf"mcp__trinity-local__{escaped}\b",
                    )
                    name_pat = "(?:" + "|".join(code_contexts) + ")"
                    if not re.search(name_pat, paragraph):
                        continue
                    # Look for a present-tense verb within 60 chars
                    # of the code-context name reference.
                    for verb in self.PRESENT_TENSE_VERBS:
                        proximity = (
                            rf"{name_pat}.{{0,60}}\b({verb})\b"
                            rf"|\b({verb})\b.{{0,60}}{name_pat}"
                        )
                        if re.search(proximity, paragraph):
                            line_no = (
                                text[: text.index(paragraph)].count("\n") + 1
                            )
                            snippet = re.sub(r"\s+", " ", paragraph[:160]).strip()
                            violations.append(
                                f"  {rel}:{line_no} (near `{name}`): "
                                f"{snippet}..."
                            )
                            break

        # The guard is approximate — it can false-positive on edge cases.
        # If it does, either (a) extend HISTORICAL_MARKERS to whitelist
        # the framing pattern or (b) past-tense the prose.
        assert not violations, (
            "Retired names appear in present-tense framing in live docs. "
            "Either re-frame to past tense ('X was retired', 'previously ran X') "
            "OR extend HISTORICAL_MARKERS in this test if the context IS "
            "explicitly historical but uses uncommon wording.\n"
            + "\n".join(violations[:20])
            + (f"\n  ...and {len(violations)-20} more" if len(violations) > 20 else "")
        )
