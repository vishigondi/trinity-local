"""Regression guard: the MCP-first narrative must stay coherent across
the three load-bearing docs.

Three surfaces, one story:
  - README.md install section: leads with "paste into Claude Code /
    Desktop", does NOT lead with "/trinity" (skill-first phrasing).
  - docs/three-tier-architecture.md: Tier 1 is MCP, NOT "Skill (primary)".
  - CLAUDE.md status block: mentions "MCP-first" pivot.

The 2026-05-19 pivot away from skill-first lands silently if any of
these surfaces drift back. Same shape as the "duplicated facts drift
in the oldest surface" principle (CLAUDE.md principle #20) — pinning
all three forces them to evolve together.
"""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


class TestReadmeInstallSection:
    def test_does_not_lead_with_slash_trinity_skill(self, repo_root):
        """The install section was 'Then type /trinity in Claude Code.
        The skill walks the rest…' — skill-first framing. Pivot 2026-
        05-19: lead with the agent-paste-into path instead. The
        '/trinity' phrasing should not appear in the install section
        as the PRIMARY call-to-action."""
        readme = (repo_root / "README.md").read_text()
        # Find the Install section.
        install_start = readme.find("## Install")
        assert install_start != -1, "README missing Install section"
        # Take the install section through the next ## header.
        next_header = readme.find("\n## ", install_start + 1)
        install_section = readme[install_start:next_header]
        # The deprecated lead phrase.
        assert "Then type `/trinity` in Claude Code. The skill walks the rest" not in install_section, (
            "README Install section must not lead with the skill-first "
            "phrasing. The MCP-first pivot leads with the paste-into-"
            "Claude-Code brief."
        )

    def test_mentions_paste_into_agent_path(self, repo_root):
        """The audience-expansion claim depends on the non-technical
        user seeing 'paste into Claude Code / Desktop' as the easiest
        path. Drift here = the claim silently regresses."""
        readme = (repo_root / "README.md").read_text()
        install_start = readme.find("## Install")
        next_header = readme.find("\n## ", install_start + 1)
        install_section = readme[install_start:next_header]
        # At least one of these must appear — agent-paste-into is the
        # primary entry path.
        assert (
            "paste" in install_section.lower()
            and ("Claude Code" in install_section or "Claude Desktop" in install_section)
        ), (
            "README Install must mention pasting into Claude Code / Desktop "
            "as the primary path."
        )


class TestThreeTierDoc:
    def test_tier_1_is_mcp_not_skill(self, repo_root):
        """The three-tier doc is the architectural source of truth.
        Tier 1 must say MCP, not Skill, as the primary tier."""
        doc = (repo_root / "docs" / "three-tier-architecture.md").read_text()
        # Header line for Tier 1 must mention MCP.
        assert "Tier 1 — MCP" in doc or "Tier 1 - MCP" in doc, (
            "docs/three-tier-architecture.md Tier 1 header must name MCP "
            "as the primary surface (post 2026-05-19 pivot)."
        )
        # Old framing must be gone — the literal "Tier 1 — Skill (primary)"
        # header should not appear.
        assert "Tier 1 — Skill (primary)" not in doc, (
            "Old 'Tier 1 — Skill (primary)' header still present — "
            "the MCP-first pivot didn't fully land in the doc."
        )

    def test_extension_described_as_sidecar(self, repo_root):
        """The Chrome extension is the discovery + capture sidecar, not
        an optional tier-3 afterthought. The framing matters because
        the popup is the non-technical-user entry point."""
        doc = (repo_root / "docs" / "three-tier-architecture.md").read_text()
        # The new framing must call out discovery + capture.
        assert "discovery" in doc.lower(), (
            "three-tier doc must describe the extension as a discovery "
            "surface (the entry point for non-technical users)."
        )
        assert "capture" in doc.lower(), (
            "three-tier doc must describe the extension's browser-capture role."
        )


class TestClaudeMdStatus:
    def test_mentions_mcp_first_pivot(self, repo_root):
        """CLAUDE.md is loaded into every agent session. The status
        block / architecture block must reflect MCP-first; otherwise
        agents reading CLAUDE.md will think skill is still primary."""
        claude_md = (repo_root / "claude.md").read_text()
        # Check the architecture line mentions MCP-first explicitly.
        assert "MCP-first" in claude_md or "MCP server (primary)" in claude_md, (
            "CLAUDE.md must mention MCP-first explicitly so the agent's "
            "loaded-context narrative matches the docs."
        )

    def test_skill_described_as_back_compat_alias(self, repo_root):
        """The skill directory at ~/.claude/skills/trinity/ still
        exists for users who already use it, but the doc must frame
        it as back-compat / alias, not primary. Drift here = new
        users discover the skill and assume it's the recommended path."""
        claude_md = (repo_root / "claude.md").read_text()
        # Look for the framing — either "back-compat" or "alias" near
        # a mention of the skill dir.
        skill_mention_idx = claude_md.find("~/.claude/skills/trinity")
        # The first mention of the skill dir should be near "back-compat"
        # or "alias" (within ~500 chars).
        if skill_mention_idx > 0:
            window = claude_md[max(0, skill_mention_idx - 500):skill_mention_idx + 500]
            assert (
                "back-compat" in window.lower()
                or "alias" in window.lower()
                or "legacy" in window.lower()
            ), (
                "CLAUDE.md's first reference to the skill dir should be "
                "framed as back-compat / alias / legacy — not as the "
                "primary install location."
            )
