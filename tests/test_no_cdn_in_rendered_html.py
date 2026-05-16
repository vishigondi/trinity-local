"""Persona audit P06 + Theme K #1 regression guard: rendered HTML pages
must reference no third-party CDN. The privacy claim ("never leaves
your machine") is structural; one stray `unpkg.com` import voids it.

Failing this test means someone added a `<script src="https://...">`
or `import ... from 'https://...'` line; replace with a vendored
file under src/trinity_local/data/vendor/ + reference via
./vendor/<name>.
"""
from __future__ import annotations

import re

import pytest


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
    return tmp_path


_CDN_DOMAINS = (
    "unpkg.com",
    "jsdelivr.net",
    "cdnjs.cloudflare.com",
    "esm.sh",
    "skypack.dev",
)


def _assert_no_cdn(html: str, page_name: str) -> None:
    """Surface the offending hit so the test failure points at the regress."""
    for domain in _CDN_DOMAINS:
        hits = [
            line for line in html.splitlines()
            if domain in line and not line.strip().startswith("//")
        ]
        assert not hits, (
            f"{page_name} loads {domain} — re-vendored a CDN reference. "
            f"First hit: {hits[0].strip()[:120]}"
        )


class TestNoCdnReferences:
    def test_launchpad_html(self, isolated_home):
        from trinity_local.launchpad_page import write_portal_html
        path = write_portal_html()
        _assert_no_cdn(path.read_text(), "launchpad.html")

    def test_memory_viewer_html(self, isolated_home):
        from trinity_local.memory_viewer import render_memory_viewer_html
        html = render_memory_viewer_html()
        _assert_no_cdn(html, "memory.html")

    def test_council_review_module_constants(self):
        """Direct check on the module string — catches regress even
        before render. The PETITE_VUE_MODULE constant must point to a
        local path, not a CDN URL."""
        from trinity_local import council_review, launchpad_template

        for module, name in (
            (council_review, "council_review"),
            (launchpad_template, "launchpad_template"),
        ):
            ptv = getattr(module, "PETITE_VUE_MODULE", "")
            for domain in _CDN_DOMAINS:
                assert domain not in ptv, (
                    f"{name}.PETITE_VUE_MODULE references {domain} — must be ./vendor/"
                )


class TestVendorFilesPublished:
    """When refresh_launchpad runs, ~/.trinity/portal_pages/vendor/ gets
    every file declared in vendor.VENDORED_FILES."""

    def test_refresh_publishes_all_files(self, isolated_home):
        from trinity_local.refresh import refresh_launchpad
        from trinity_local.vendor import VENDORED_FILES
        from trinity_local.state_paths import portal_pages_dir

        refresh_launchpad()
        vendor_dir = portal_pages_dir() / "vendor"
        for name in VENDORED_FILES:
            assert (vendor_dir / name).exists(), (
                f"vendor file {name} not published — refresh_launchpad lost the wiring"
            )

    def test_publish_is_idempotent_on_unchanged(self, isolated_home):
        from trinity_local.refresh import refresh_launchpad
        from trinity_local.vendor import publish_vendor_files
        from trinity_local.state_paths import portal_pages_dir
        import time

        refresh_launchpad()
        # Capture mtimes after first publish
        vendor_dir = portal_pages_dir() / "vendor"
        mtimes_before = {p.name: p.stat().st_mtime for p in vendor_dir.iterdir()}
        time.sleep(0.05)
        written = publish_vendor_files(portal_pages_dir())
        assert written == [], "second publish wrote files despite content match"
        mtimes_after = {p.name: p.stat().st_mtime for p in vendor_dir.iterdir()}
        for name in mtimes_before:
            assert mtimes_before[name] == mtimes_after[name], (
                f"vendor/{name} rewritten on idempotent re-publish"
            )


class TestRefreshVendorScript:
    """The maintainer-side refresh script must exist and cover every
    file in VENDORED_FILES. If someone adds a new vendored dep without
    extending the script, future-me hits the "TODO: write the refresh
    script" trap the v1.7 audit already closed once.

    Earned 2026-05-16: vendor.py's docstring referenced
    `scripts/refresh-vendor.sh (TODO)` for weeks with no script on
    disk. The fix WAS to write the script — this guard prevents the
    docstring from lying again.
    """

    def test_refresh_script_exists_and_is_executable(self):
        from pathlib import Path

        repo = Path(__file__).resolve().parent.parent
        script = repo / "scripts" / "refresh-vendor.sh"
        assert script.exists(), (
            "scripts/refresh-vendor.sh missing — vendor.py's docstring "
            "promises it. Either restore the script or update the "
            "docstring to point at the new recipe."
        )
        assert script.stat().st_mode & 0o111, (
            "scripts/refresh-vendor.sh exists but isn't executable. "
            "`chmod +x scripts/refresh-vendor.sh` to fix."
        )

    def test_refresh_script_covers_all_vendored_files(self):
        from pathlib import Path
        from trinity_local.vendor import VENDORED_FILES

        repo = Path(__file__).resolve().parent.parent
        script_text = (repo / "scripts" / "refresh-vendor.sh").read_text()
        for name in VENDORED_FILES:
            assert name in script_text, (
                f"refresh-vendor.sh doesn't pin a URL for {name!r}. "
                f"Add a `\"{name} https://...\"` line to the URLS array "
                f"so `bash scripts/refresh-vendor.sh` actually refreshes "
                f"every file ``VENDORED_FILES`` declares."
            )
