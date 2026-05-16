"""Phase 1 doc-consistency guard: every `trinity-local <cmd>` mentioned
in skills/trinity/SKILL.md must resolve in `trinity-local --help`.

The skill IS the spec — if SKILL.md references a CLI command that
doesn't exist, the skill's bash invocation fails silently and the user
sees a generic argparse error instead of the workflow Trinity promises.
This was the council `ff3da1fa84906791`-flagged failure mode for the
skill-primary framing.

Same shape as principle #20 (load-bearing facts duplicated in N≥3
surfaces drift in the oldest one): the README, the skill, and the
launch copy can all reference CLI commands; the skill is now one of
those surfaces and gets its own guard.
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest


SKILL_PATH = Path(__file__).resolve().parents[1] / "skills" / "trinity" / "SKILL.md"


@pytest.fixture(scope="module")
def cli_subcommands() -> set[str]:
    """Pull the full subcommand set from `trinity-local --help`. We grep
    out the positional argument list because argparse prints it in
    curly-braced csv form: `{cmd1,cmd2,cmd3,...}`."""
    result = subprocess.run(
        [sys.executable, "-m", "trinity_local.main", "--help"],
        capture_output=True, text=True, check=False, timeout=15,
    )
    out = result.stdout
    # argparse prints the positional choices on one or more lines like
    # `{action-suggest,action-council,...}` — collect everything inside
    # the first top-level `{...}` block.
    matches = re.findall(r"\{([^{}]+)\}", out)
    if not matches:
        pytest.fail(f"Could not parse subcommands from --help output:\n{out[:500]}")
    # The largest match is the full positional choices.
    longest = max(matches, key=len)
    return set(cmd.strip() for cmd in longest.split(","))


def test_skill_md_exists():
    """SKILL.md is the user-facing contract; this file pins its location."""
    assert SKILL_PATH.exists(), (
        f"skills/trinity/SKILL.md missing at {SKILL_PATH}. The skill IS the spec; "
        f"absent skill = absent v1.0 product surface."
    )


def test_every_trinity_local_invocation_resolves(cli_subcommands):
    """For every `trinity-local <cmd>` shell invocation in SKILL.md,
    `<cmd>` must be a real subcommand the CLI exposes. Catches:
      - command renames that didn't propagate to SKILL.md
      - aspirational commands documented before they exist
      - typos that would make the skill's bash invocation fail
        with a generic argparse error
    """
    content = SKILL_PATH.read_text()
    # Match `trinity-local <subcommand>` inside backticks AND inside
    # the SKILL.md !`...` shell-call syntax. Subcommand follows the
    # word "trinity-local" and a space; capture the first token after.
    # Same-line only — `\s` matches newlines too and would spuriously grab
    # the first token of the NEXT line (e.g. `... trinity-local\nln -s ...`
    # captures `ln`).
    pattern = re.compile(r"trinity-local[ \t]+([a-z][a-z0-9-]*)", re.IGNORECASE)
    referenced = set(m.group(1) for m in pattern.finditer(content))

    # "install" alone isn't a subcommand — drop noise from prose like
    # "the install itself" that argparse can't validate.
    referenced -= {"install"}
    # CLI flags shouldn't be matched but the regex requires lowercase
    # word chars after the space, so flags like --version are skipped.

    assert referenced, (
        "SKILL.md doesn't reference ANY trinity-local subcommand. The "
        "skill MUST drive the CLI; an empty driver isn't a skill, it's "
        "marketing copy."
    )

    missing = referenced - cli_subcommands
    assert not missing, (
        f"SKILL.md references {len(missing)} CLI subcommand(s) that don't "
        f"exist in `trinity-local --help`: {sorted(missing)!r}. Either add "
        f"them to commands/ + register(), or remove the reference from "
        f"SKILL.md. Available subcommands: {sorted(cli_subcommands)[:20]!r}..."
    )


def test_skill_md_documents_three_tier_invariant():
    """The skill's framing carries the brand pitch. If the three-tier
    framing or the tier-equivalence claim drifts out of SKILL.md, the
    launch story loses its mechanic. Pin both as required substrings."""
    content = SKILL_PATH.read_text()
    # The tier names — drift here = framing drift across surfaces
    assert "Tier 1" in content and "Tier 2" in content and "Tier 3" in content
    # Tier-equivalence invariant (NOT bit-identical, NOT "byte-identical")
    # — codex Phase 1 verdict: claiming bit-equality is a credibility bug.
    assert "tier-equivalent" in content.lower() or "tier-equivalence" in content.lower()
    assert "0.9999" in content, (
        "SKILL.md must pin the cosine ≥ 0.9999 invariant per "
        "council_ff3da1fa84906791. The numeric anchor is what makes the "
        "claim falsifiable rather than rhetorical."
    )
