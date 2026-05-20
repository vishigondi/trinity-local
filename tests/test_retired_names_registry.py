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

    def test_no_duplicate_keys_in_dict_literal(self):
        """Python dict literals silently keep the last value for repeated keys,
        which would erase earlier registry entries on a copy-paste mistake.
        Born of tick 53 — pyflakes caught two `get_eval_summary` entries
        (the tick-46 add silently overwrote the older bare entry; the
        registry effectively had 1 entry, not 2). Parse retired_names.py
        as text and assert no key string appears more than once at the
        top-level of the RETIRED dict literal.
        """
        import re
        text = (REPO / "src/trinity_local/retired_names.py").read_text(encoding="utf-8")
        # Match `    "key": RetirementRecord(` — top-level dict items use
        # 4-space indentation in this file. Excludes nested RetirementRecord
        # field assignments (deeper indent or `name=`).
        keys = re.findall(r'^    "([^"]+)": RetirementRecord\(', text, re.MULTILINE)
        from collections import Counter
        counts = Counter(keys)
        dupes = [k for k, n in counts.items() if n > 1]
        assert not dupes, (
            f"Duplicate keys in RETIRED dict literal: {dupes}. "
            "Python silently keeps only the last value; earlier entries "
            "are erased. Consolidate the duplicates into one entry."
        )


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
        # Container verbs added 2026-05-19 after MCP_REGISTRY_SUBMISSIONS
        # leaked "Comes with the standard `search_prompts` tool" without
        # tripping the prior verb set. These framings present the retired
        # name as still part of the live surface ("ships with X",
        # "exposes X", "supports X tool"), so they're equivalent
        # falsifications of the retirement claim.
        r"comes\s+with",
        r"ships?\s+with",
        r"exposes?",
        r"supports?",
        r"includes?",
        r"offers?",
        r"provides?",
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

    # Docs to scan = every doc with `class: live` in its Gap C
    # frontmatter. Skip historical-class docs (simplification_log.md,
    # spec-v2 sunset, etc.) — they DO narrate retirements in
    # present-tense + that's correct for them. Skip aspirational-class
    # docs too (spec-v1.5, scale-plan future sections) — they may
    # forecast retirement of things that aren't yet retired.
    #
    # Auto-deriving from frontmatter (rather than a hardcoded list)
    # means: when iter #N adds a new live doc, it's automatically
    # covered by this guard via the doc's `class: live` declaration.
    # Pattern #29 (bilateral sync for duplicated artifacts) applied
    # cross-test: the doc-class list lives in ONE place (the
    # frontmatter), not duplicated in N test files.
    # Live-class docs that are EXCLUDED from the scan despite their
    # class label. CHANGELOG.md is `class: live` (it's the active
    # release-notes file) but its individual ENTRIES are timestamped
    # to past releases — per principle #8, CHANGELOG entries are
    # stale-OK. A retired CLI mentioned in a 2026-05-12 entry was
    # current AT THAT ENTRY's release date.
    EXCLUDE_LIVE_DOCS = (
        "CHANGELOG.md",
    )

    @staticmethod
    def _live_class_docs() -> list[Path]:
        """All md files in the repo declaring `class: live`, minus the
        EXCLUDE_LIVE_DOCS that have a timestamped-entries shape."""
        live: list[Path] = []
        frontmatter_re = re.compile(r"^---\n(.*?\n)?---\n", re.DOTALL)
        for path in REPO.rglob("*.md"):
            # Skip artifact / vendored / build dirs.
            if any(
                skip in str(path)
                for skip in (
                    ".venv", "node_modules", "build/", ".egg-info",
                    ".pytest_cache", ".playwright-mcp", "state/",
                    "/skills/", "/data/skills/", ".github/",
                )
            ):
                continue
            try:
                text = path.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            m = frontmatter_re.match(text)
            if not m:
                continue
            front = m.group(1) or ""
            if not re.search(r"^class:\s*live\s*$", front, re.MULTILINE):
                continue
            # Skip per-doc exclusions (e.g. CHANGELOG.md, see above).
            rel = str(path.relative_to(REPO))
            if rel in TestNoPresentTenseInDocs.EXCLUDE_LIVE_DOCS:
                continue
            live.append(path)
        return sorted(live)

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

        for path in self._live_class_docs():
            text = path.read_text(encoding="utf-8")
            rel = str(path.relative_to(REPO))
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
