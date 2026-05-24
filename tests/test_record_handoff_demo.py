"""Tests for #120: scripts/record_handoff_demo.sh — the asciinema
record helper for the 60-second handoff demo.

Doesn't actually run asciinema (that needs a TTY and a real CLI
session). Locks down the script shape + the documentation contract
so the file doesn't drift out of sync with the launch-arc surfaces
that reference it.
"""
from __future__ import annotations

import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts" / "record_handoff_demo.sh"
DEMO_DIR = REPO_ROOT / "docs" / "demo"
DEMO_README = DEMO_DIR / "README.md"


class TestScriptShape:
    def test_script_exists_and_is_executable(self):
        assert SCRIPT.exists(), "record_handoff_demo.sh missing"
        assert os.access(SCRIPT, os.X_OK), (
            "record_handoff_demo.sh not executable — chmod +x missing"
        )

    def test_script_has_safe_bash_pragmas(self):
        """`set -euo pipefail` is non-negotiable for scripts that pipe
        external CLI output and parse it. Without it, an asciinema
        failure mid-record silently produces a 0-byte cast file."""
        text = SCRIPT.read_text(encoding="utf-8")
        assert "set -euo pipefail" in text

    def test_script_validates_asciinema_installation(self):
        """The script must check for asciinema before invoking it.
        Cross-platform install hint must be present so a Linux user
        doesn't get a bare 'command not found'."""
        text = SCRIPT.read_text(encoding="utf-8")
        assert "command -v asciinema" in text
        # Cross-platform hints — covers the three install paths
        for hint in ("brew install asciinema", "pip install asciinema"):
            assert hint in text, f"Missing install hint: {hint!r}"

    def test_script_validates_trinity_local_on_path(self):
        """Without trinity-local on PATH, handoff can't fire. The
        check must surface a hint pointing at install.sh."""
        text = SCRIPT.read_text(encoding="utf-8")
        assert "command -v trinity-local" in text
        assert "install.sh" in text

    def test_script_writes_to_canonical_cast_path(self):
        """The launch-day embed surfaces (README hero, launch.md) point
        at docs/demo/handoff_60s.cast. The recorder must write there
        (not a temp dir, not a user-chosen path) so the embed
        instructions stay consistent."""
        text = SCRIPT.read_text(encoding="utf-8")
        assert "docs/demo/handoff_60s.cast" in text or \
               "${DEMO_DIR}/handoff_60s.cast" in text

    def test_script_warns_on_thin_prompt_index(self):
        """If the prompt index is empty (cold install), handoff falls
        back to a 'no recent turns' message. The recorder must warn
        so the user doesn't ship a demo with no continuity evidence."""
        text = SCRIPT.read_text(encoding="utf-8")
        assert "prompt_count" in text
        assert "thin context" in text.lower() or "no recent turns" in text.lower()


class TestDemoDirReadme:
    def test_readme_exists(self):
        assert DEMO_README.exists(), "docs/demo/README.md missing"

    def test_readme_has_doc_class_frontmatter(self):
        """All docs in user-facing docs/ must declare a class per the
        frontmatter contract (task #123). live = canonical, ratified."""
        text = DEMO_README.read_text(encoding="utf-8")
        assert text.startswith("---\nclass: live\n---\n")

    def test_readme_explains_asciinema_over_mp4_choice(self):
        """The asciinema-over-MP4 decision is load-bearing for the
        embed surface choice. README must justify it so a future
        contributor doesn't 'modernize' to MP4 and break GitHub
        README rendering."""
        text = DEMO_README.read_text(encoding="utf-8")
        assert "asciinema" in text.lower()
        assert "mp4" in text.lower()
        # Click-to-copy is the killer differentiator vs MP4
        assert "click-to-copy" in text.lower() or "copy commands" in text.lower()

    def test_readme_points_at_record_helper(self):
        text = DEMO_README.read_text(encoding="utf-8")
        assert "scripts/record_handoff_demo.sh" in text

    def test_readme_documents_upload_and_embed_steps(self):
        """The "host it" + "embed it" components of #120 need explicit
        instructions; recording without an upload+embed step doesn't
        close the gate."""
        text = DEMO_README.read_text(encoding="utf-8")
        assert "asciinema upload" in text
        assert "README" in text  # the embed surface
