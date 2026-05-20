"""Gap C — Doc-class frontmatter linter.

Every classifiable doc must carry a YAML frontmatter block declaring
its class:

    ---
    class: live | aspirational | historical | reference
    ---

The classification is enforced via this test + bootstrapped by
`scripts/add_doc_class_frontmatter.py` (which carries the canonical
list of CLASSIFIABLE_DOCS).

Why not all md files? Some carry frontmatter for OTHER reasons:
  - skills/**/SKILL.md uses YAML for Claude Code skill metadata
  - .github/ISSUE_TEMPLATE/*.md uses YAML for GitHub issue templates
  - state/, build/, .pytest_cache/, .playwright-mcp/ are runtime artifacts

The CLASSIFIABLE_DOCS list mirrors `scripts/add_doc_class_frontmatter.py:CLASSIFICATIONS`.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[1]
VALID_CLASSES = {"live", "aspirational", "historical", "reference"}

# Paths that MUST carry doc-class frontmatter. Mirrors
# scripts/add_doc_class_frontmatter.py:CLASSIFICATIONS — when a new
# doc lands, add it to both.
CLASSIFIABLE_DOCS: list[str] = [
    # ── Repo root ──
    "README.md",
    "claude.md",
    "AGENTS.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "DESIGN.md",
    "CODE_OF_CONDUCT.md",
    "SECURITY.md",
    # ── docs/ ──
    "docs/architecture.md",
    "docs/INSTALL-skill.md",
    "docs/INSTALL-pip.md",
    "docs/INSTALL-extension.md",
    "docs/install-deep.md",
    "docs/launch.md",
    "docs/launch-package.md",
    "docs/LAUNCH_CHECKLIST.md",
    "docs/lens.md",
    "docs/teams.md",
    "docs/MCP_REGISTRY_SUBMISSIONS.md",
    "docs/MIGRATION.md",
    "docs/PREFERENCE_CORPUS_SPEC.md",
    "docs/REPO_PUBLIC_RUNBOOK.md",
    "docs/spec-v1.md",
    "docs/three-tier-architecture.md",
    "docs/training-data.md",
    "docs/TRUST-MODE.md",
    # ── docs/launch-day/ ──
    "docs/launch-day/README.md",
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
    # ── Aspirational ──
    "docs/spec-v1.5.md",
    "docs/spec-v1.6.md",
    "docs/cross-platform-spec.md",
    "docs/launcher-patterns.md",
    "docs/sweep-patterns.md",
    "docs/architectural-gaps.md",
    "docs/design-frame.md",
    "docs/founder-essay-draft.md",
    "docs/product-spec.md",
    "docs/scale-plan.md",
    "docs/telemetry-spec.md",
    "docs/frontend-architecture.md",
    # ── Historical ──
    "docs/spec-v2.md",
    "docs/v2-loop-constitution.md",
    "docs/PUBLIC_READINESS_PLAN.md",
    "docs/simplification_log.md",
]


FRONTMATTER_PATTERN = re.compile(r"^---\n(.*?\n)?---\n", re.DOTALL)
CLASS_LINE_PATTERN = re.compile(r"^class:\s*(\w+)\s*$", re.MULTILINE)


def _extract_class(text: str) -> str | None:
    """Return the declared class from frontmatter, or None if missing."""
    m = FRONTMATTER_PATTERN.match(text)
    if not m:
        return None
    front = m.group(1) or ""
    cm = CLASS_LINE_PATTERN.search(front)
    return cm.group(1) if cm else None


class TestDocClassFrontmatter:
    """Every classifiable doc carries valid frontmatter + valid class.

    This converts the implicit "this doc is load-bearing for launch / this
    one is historical roadmap / this one is forward-looking spec" knowledge
    into a queryable declaration. Future sweeps allocate effort by class;
    future linter extensions can validate class-specific invariants (e.g.,
    \"historical docs are read-only\", \"aspirational docs need verify-against
    footers\").
    """

    @pytest.mark.parametrize("rel_path", CLASSIFIABLE_DOCS)
    def test_doc_has_frontmatter(self, rel_path: str):
        path = REPO / rel_path
        assert path.exists(), f"Doc {rel_path} listed as classifiable but missing"
        text = path.read_text(encoding="utf-8")
        match = FRONTMATTER_PATTERN.match(text)
        assert match, (
            f"{rel_path}: no YAML frontmatter block. Every classifiable "
            "doc must declare its class. Run "
            "`python scripts/add_doc_class_frontmatter.py` to bootstrap."
        )

    @pytest.mark.parametrize("rel_path", CLASSIFIABLE_DOCS)
    def test_doc_class_is_valid(self, rel_path: str):
        path = REPO / rel_path
        text = path.read_text(encoding="utf-8")
        doc_class = _extract_class(text)
        assert doc_class is not None, (
            f"{rel_path}: frontmatter exists but no `class: X` line. "
            "Add `class: live | aspirational | historical | reference`."
        )
        assert doc_class in VALID_CLASSES, (
            f"{rel_path}: invalid class {doc_class!r}. "
            f"Must be one of {sorted(VALID_CLASSES)}."
        )

    def test_classifiable_docs_list_in_sync_with_bootstrap_script(self):
        """The list here and the CLASSIFICATIONS dict in
        scripts/add_doc_class_frontmatter.py must agree, so a new doc
        gets classified consistently across the two surfaces."""
        script_text = (REPO / "scripts" / "add_doc_class_frontmatter.py").read_text(
            encoding="utf-8"
        )
        script_paths = set(
            re.findall(r'"([^"]+\.md)":\s*"\w+"', script_text)
        )
        test_paths = set(CLASSIFIABLE_DOCS)
        missing_from_test = script_paths - test_paths
        missing_from_script = test_paths - script_paths
        assert not missing_from_test and not missing_from_script, (
            f"CLASSIFIABLE_DOCS in test_doc_class_frontmatter.py and "
            f"CLASSIFICATIONS in scripts/add_doc_class_frontmatter.py drift:\n"
            f"  in script, not in test: {sorted(missing_from_test)}\n"
            f"  in test, not in script: {sorted(missing_from_script)}"
        )
