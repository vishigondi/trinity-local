"""Tests for the install.sh CLI-wrapper rewrite that wires
launcher_path_resolver.sh into the Trinity binary.

End state: `~/.local/bin/trinity-local` is a small bash script that
calls `~/.local/bin/trinity-path-resolver.sh` to find the source dir,
then exec's Python with the right PYTHONPATH. The resolver probes
Chrome Web Store extension dirs first (auto-update path), falling
back to ~/.trinity/code/ then the legacy skill location.

This means the moment Chrome auto-updates the extension, the next
`trinity-local` invocation picks up new Python — zero user action.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
INSTALL_SH = REPO_ROOT / "scripts" / "install.sh"


@pytest.fixture(scope="module")
def install_script() -> str:
    return INSTALL_SH.read_text()


class TestInstallScriptCopiesResolver:
    def test_install_copies_resolver_to_bin_dir(self, install_script):
        """install.sh must copy the resolver to ~/.local/bin/ so the
        wrappers can find it via a stable path. Leaving it in the
        skill dir creates a chicken-and-egg lookup."""
        assert "trinity-path-resolver.sh" in install_script, (
            "install.sh must drop the resolver alongside the wrappers — "
            "the wrappers depend on a stable resolver path."
        )
        # cp from the source location to the bin dir.
        assert re.search(
            r"cp\s+\"?\$RESOLVER_SRC\"?\s+\"?\$RESOLVER_DST\"?",
            install_script,
        ), "install.sh must `cp` the resolver to the bin dir, not symlink."

    def test_resolver_marked_executable(self, install_script):
        """The resolver is invoked directly — must be chmod +x in
        install.sh or it can't run."""
        assert re.search(
            r"chmod\s+\+x\s+\"?\$RESOLVER_DST\"?",
            install_script,
        ), "install.sh must chmod +x the resolver after copying."


class TestTrinityLocalWrapper:
    def test_wrapper_calls_resolver(self, install_script):
        """The trinity-local wrapper must call the resolver to find
        the source dir. Drift here = the wrapper goes back to the
        old static-path approach and Chrome auto-update breaks."""
        # The wrapper heredoc should reference the resolver.
        # Find the trinity-local wrapper heredoc (between WRAPPER_EOF markers).
        match = re.search(
            r"trinity-local\"?\s*<<WRAPPER_EOF\s*(.+?)\nWRAPPER_EOF",
            install_script,
            re.DOTALL,
        )
        assert match, (
            "install.sh must have a `cat > .../trinity-local <<WRAPPER_EOF` "
            "heredoc — the resolver-aware wrapper."
        )
        wrapper_body = match.group(1)
        assert "RESOLVER" in wrapper_body, (
            "trinity-local wrapper must invoke the resolver — it doesn't."
        )
        # The wrapper should pipe the resolver's stdout into SOURCE_DIR.
        assert "SOURCE_DIR" in wrapper_body
        # And it must exec python with that SOURCE_DIR as PYTHONPATH.
        assert "PYTHONPATH=" in wrapper_body
        assert "trinity_local.main" in wrapper_body

    def test_wrapper_fails_loud_when_no_source(self, install_script):
        """When the resolver returns nothing, the wrapper must print
        a clear error AND a re-install command. Silently exec'ing
        python with a broken PYTHONPATH would be much worse."""
        match = re.search(
            r"trinity-local\"?\s*<<WRAPPER_EOF\s*(.+?)\nWRAPPER_EOF",
            install_script,
            re.DOTALL,
        )
        assert match
        wrapper_body = match.group(1)
        # The wrapper should error out when resolver fails (||).
        assert "exit 1" in wrapper_body or "exit \\$?" in wrapper_body
        # And mention re-install.
        assert "Re-install" in wrapper_body, (
            "Resolver failure should hand the user the curl|bash re-install "
            "command so they can recover."
        )


class TestCaptureHostWrapper:
    def test_capture_host_wrapper_also_uses_resolver(self, install_script):
        """The capture-host wrapper must use the same resolver as the
        main CLI — otherwise Chrome auto-update updates the CLI but
        the Native Messaging host stays stale."""
        match = re.search(
            r"trinity-local-capture-host\"?\s*<<CAPTURE_EOF\s*(.+?)\nCAPTURE_EOF",
            install_script,
            re.DOTALL,
        )
        assert match, (
            "install.sh must write the capture-host wrapper via a "
            "CAPTURE_EOF heredoc."
        )
        body = match.group(1)
        # Same resolver path resolution pattern.
        assert "RESOLVER" in body or "trinity-path-resolver" in body, (
            "capture-host wrapper must use the resolver too — drift here "
            "means CLI auto-updates but Native Messaging stays stale."
        )
        assert "SOURCE_DIR" in body
        assert "capture_host.py" in body


class TestLegacyFallbackBranch:
    """If launcher_path_resolver.sh isn't in the cloned repo (partial
    install / future repo reshuffle), install.sh must still write
    working wrappers via the legacy direct-path approach. The Chrome
    auto-update story degrades but Trinity keeps working."""

    def test_fallback_branch_exists(self, install_script):
        """install.sh has an explicit if/else around resolver
        presence so partial installs don't write broken wrappers."""
        # Look for the resolver-presence guard.
        assert re.search(
            r"if\s+\[\[\s+-n\s+\"\$RESOLVER_DST\"\s+\]\]",
            install_script,
        ), (
            "install.sh must gate wrapper choice on resolver presence "
            "and have a legacy-fallback branch — partial installs would "
            "otherwise leave the user with broken wrappers."
        )

    def test_fallback_uses_legacy_static_path(self, install_script):
        """The fallback branch falls back to the previous wrapper
        shape — TRINITY_SKILL_DIR env var pointing at the skill repo."""
        # Find the legacy heredoc.
        assert "LEGACY_EOF" in install_script, (
            "install.sh must define a legacy wrapper heredoc as fallback."
        )
