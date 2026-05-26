"""One-shot tool to add `class: ...` YAML frontmatter to every doc in the repo.

Run once to bootstrap Gap C (per docs/architectural-gaps.md):

    .venv/bin/python scripts/add_doc_class_frontmatter.py

Idempotent — already-classified files are skipped. The doc classification
declares each md file's purpose so future maintenance (sweeps, linter checks,
test classes) can allocate effort by class.

Doc classes:
  - live: must match current state (loud-fail on drift)
  - aspirational: forward-looking; drift expected; needs verify-against footers
  - historical: timestamped snapshot; do not edit
  - reference: auto-generated or build-artifact; classify but don't edit

After running, `tests/test_doc_class_frontmatter.py` validates every
classifiable doc carries valid frontmatter.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


# Classification by relative path. Anything not in this dict is SKIPPED
# (not all md files should have doc-class frontmatter — SKILL.md and
# .github templates use frontmatter for their own purposes).
CLASSIFICATIONS: dict[str, str] = {
    # ── Repo root ──
    "README.md": "live",
    "claude.md": "live",
    "AGENTS.md": "live",
    "CHANGELOG.md": "live",
    "CONTRIBUTING.md": "live",
    "DESIGN.md": "live",
    "CODE_OF_CONDUCT.md": "live",
    "SECURITY.md": "live",
    # ── docs/ active references ──
    "docs/architecture.md": "live",
    "docs/INSTALL-skill.md": "live",
    "docs/INSTALL-pip.md": "live",
    "docs/INSTALL-extension.md": "live",
    "docs/install-deep.md": "live",
    "docs/launch.md": "live",
    "docs/launch-package.md": "live",
    "docs/LAUNCH_CHECKLIST.md": "live",
    "docs/lens.md": "live",
    "docs/teams.md": "live",
    "docs/MCP_REGISTRY_SUBMISSIONS.md": "live",
    "docs/MIGRATION.md": "live",
    "docs/PREFERENCE_CORPUS_SPEC.md": "live",
    "docs/REPO_PUBLIC_RUNBOOK.md": "live",
    "docs/spec-v1.md": "live",
    "docs/three-tier-architecture.md": "live",
    # training-data.md was retired 2026-05-11 (the trained-coordinator
    # Phase 9 path was sunset; v1.5 ships routing via context
    # engineering instead). The doc's first paragraph carries that
    # sunset notice. Marked historical to match the content; left
    # outside docs/historical/ because incoming docs still cross-link
    # to docs/training-data.md and breaking those links isn't worth
    # the relocation. Same precedent as v2-loop-constitution.md /
    # PUBLIC_READINESS_PLAN.md / simplification_log.md.
    "docs/training-data.md": "historical",
    "docs/historical/trust-mode.md": "historical",
    "docs/SITE_README.md": "live",
    # ── Other tracked user-facing READMEs ──
    "browser-extension/README.md": "live",
    # ── docs/launch-day/ ──
    "docs/launch-day/README.md": "live",
    "docs/launch-day/00_leaderboard.md": "live",
    "docs/launch-day/01_tweet_thread.md": "live",
    "docs/launch-day/02_show_hn_post.md": "live",
    "docs/launch-day/03_hn_objection_faq.md": "live",
    "docs/launch-day/05_comparison_table.md": "live",
    "docs/launch-day/06_founder_narrative.md": "live",
    "docs/launch-day/07_pricing_faq.md": "live",
    "docs/launch-day/08_twitter_bio.md": "live",
    "docs/launch-day/09_linkedin_post.md": "live",
    "docs/launch-day/10_hn_faq_full.md": "live",
    # ── Aspirational (forward-looking; drift expected) ──
    "docs/spec-v1.5.md": "aspirational",
    "docs/spec-v1.6.md": "aspirational",
    "docs/cross-platform-spec.md": "aspirational",
    "docs/launcher-patterns.md": "aspirational",
    "docs/sweep-patterns.md": "aspirational",
    "docs/architectural-gaps.md": "aspirational",
    "docs/design-frame.md": "aspirational",
    "docs/founder-essay-draft.md": "aspirational",
    "docs/product-spec.md": "aspirational",
    "docs/scale-plan.md": "aspirational",
    "docs/telemetry-spec.md": "aspirational",
    "docs/frontend-architecture.md": "aspirational",
    # ── Historical (snapshots; do not edit) ──
    "docs/spec-v2.md": "historical",
    "docs/v2-loop-constitution.md": "historical",
    # docs/historical/ — created 2026-05-22 in v1.7.5 cleanup pass
    # (Phase 4 cut claude.md 918 → 183 lines; these 3 carry the
    # relocated principles / retirement-log / brand-evolution sections).
    "docs/historical/principles.md": "historical",
    "docs/historical/retirement-log.md": "historical",
    "docs/historical/brand-evolution.md": "historical",
    "docs/PUBLIC_READINESS_PLAN.md": "historical",
    "docs/simplification_log.md": "historical",
}


FRONTMATTER_PATTERN = re.compile(r"^---\n(.*?\n)?---\n", re.DOTALL)


def add_frontmatter(path: Path, doc_class: str) -> str:
    """Return the file text with frontmatter prepended (or merged if existing).

    Idempotent: if `class: X` already in frontmatter, leaves the file
    unchanged. If frontmatter exists without `class:`, inserts it. If
    no frontmatter, prepends a new block.
    """
    text = path.read_text(encoding="utf-8")
    existing = FRONTMATTER_PATTERN.match(text)

    if existing:
        front = existing.group(1) or ""
        if re.search(r"^class:\s*\w+\s*$", front, re.MULTILINE):
            return text  # already classified
        # Merge class into existing frontmatter
        new_front = front.rstrip() + f"\nclass: {doc_class}\n"
        return text.replace(existing.group(0), f"---\n{new_front}---\n", 1)

    # Prepend new frontmatter block
    new_block = f"---\nclass: {doc_class}\n---\n\n"
    return new_block + text


def main() -> int:
    changed = 0
    skipped = 0
    classified = 0
    for rel_path, doc_class in CLASSIFICATIONS.items():
        path = REPO / rel_path
        if not path.exists():
            print(f"[skip — missing] {rel_path}", file=sys.stderr)
            skipped += 1
            continue
        new_text = add_frontmatter(path, doc_class)
        if new_text != path.read_text(encoding="utf-8"):
            path.write_text(new_text, encoding="utf-8")
            print(f"[classified {doc_class}] {rel_path}")
            changed += 1
        else:
            print(f"[already classified] {rel_path}")
        classified += 1

    print()
    print(f"Total classifiable docs: {len(CLASSIFICATIONS)}")
    print(f"  changed:    {changed}")
    print(f"  unchanged:  {classified - changed}")
    print(f"  missing:    {skipped}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
