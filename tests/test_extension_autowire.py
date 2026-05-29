"""Extension auto-wire: pre-register the native host for the canonical
extension id so the published extension connects with zero further setup.

The mechanism: install.sh pre-wires the host for ONE fixed id
(registry.CANONICAL_EXTENSION_ID). When the user installs the published
extension (same id), the host is already there → "registers itself if
found". A sideloaded build (different id) falls back to --extension-id.
CHROME_WEB_STORE_URL flips the launchpad CTA from sideload to one-click.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[1]


class TestCanonicalIdSingleSourceOfTruth:
    def test_constant_is_valid_chrome_id(self):
        from trinity_local.registry import CANONICAL_EXTENSION_ID
        assert re.fullmatch(r"[a-p]{32}", CANONICAL_EXTENSION_ID), (
            "canonical extension id must be Chrome's 32-char a-p format"
        )

    def test_bash_resolver_default_matches_constant(self):
        """launcher_path_resolver.sh hard-codes the same id as its default
        (bash can't import Python). Drift = the resolver probes a different
        extension dir than the host is wired for. Keep them in lockstep."""
        from trinity_local.registry import CANONICAL_EXTENSION_ID
        resolver = (REPO / "scripts" / "launcher_path_resolver.sh").read_text()
        m = re.search(r'EXTENSION_ID="\$\{1:-([a-p]{32})\}"', resolver)
        assert m, "resolver must define EXTENSION_ID default in the {1:-<id>} form"
        assert m.group(1) == CANONICAL_EXTENSION_ID, (
            f"resolver default {m.group(1)} != registry CANONICAL_EXTENSION_ID "
            f"{CANONICAL_EXTENSION_ID} — update both when the id changes."
        )


class TestInstallShPreWiresHost:
    def test_install_sh_calls_install_extension(self):
        sh = (REPO / "scripts" / "install.sh").read_text()
        assert "install-extension" in sh, (
            "install.sh must pre-wire the capture host (best-effort) so the "
            "published extension connects with no second command."
        )
        # Best-effort: must not hard-fail the install if pre-wiring fails.
        assert re.search(r"install-extension[^\n]*\|\||install-extension.*then", sh) or \
            "could not pre-wire" in sh, (
            "the pre-wire step must be best-effort (browser capture is optional)."
        )


def _chrome_manifest(home: Path) -> Path:
    """Platform-aware native-messaging manifest path (matches install.py)."""
    import sys
    if sys.platform == "darwin":
        return (home / "Library/Application Support/Google/Chrome/"
                "NativeMessagingHosts/local.trinity.capture.json")
    return (home / ".config/google-chrome/NativeMessagingHosts/"
            "local.trinity.capture.json")


class TestInstallExtensionDefaultsToCanonical:
    def test_no_id_defaults_to_canonical_and_writes_manifest(self, tmp_path, monkeypatch):
        import json
        from types import SimpleNamespace

        from trinity_local.commands.install import handle_install_extension
        from trinity_local.registry import CANONICAL_EXTENSION_ID

        # install-extension writes under Path.home(); sandbox it.
        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
        host = tmp_path / "trinity-local-capture-host"
        host.write_text("#!/bin/sh\n")
        rc = handle_install_extension(SimpleNamespace(
            extension_id=None, host_path=str(host), browsers=["chrome"], firefox=False,
        ))
        assert rc in (0, None)
        manifest = _chrome_manifest(tmp_path)
        assert manifest.exists(), "default install-extension must write the host manifest"
        d = json.loads(manifest.read_text())
        assert d["allowed_origins"] == [f"chrome-extension://{CANONICAL_EXTENSION_ID}/"]

    def test_explicit_sideload_id_overrides_canonical(self, tmp_path, monkeypatch):
        import json
        from types import SimpleNamespace

        from trinity_local.commands.install import handle_install_extension

        monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path))
        host = tmp_path / "trinity-local-capture-host"
        host.write_text("#!/bin/sh\n")
        sideload = "abcdefghijklmnopabcdefghijklmnop"
        handle_install_extension(SimpleNamespace(
            extension_id=sideload, host_path=str(host), browsers=["chrome"], firefox=False,
        ))
        d = json.loads(_chrome_manifest(tmp_path).read_text())
        assert d["allowed_origins"] == [f"chrome-extension://{sideload}/"]


@pytest.mark.usefixtures("patch_trinity_home")
class TestWebStoreSwitch:
    def test_browser_extension_exposes_web_store_url(self):
        from trinity_local.launchpad_data import _browser_extension
        from trinity_local.registry import CHROME_WEB_STORE_URL
        ext = _browser_extension()
        assert "webStoreUrl" in ext
        assert ext["webStoreUrl"] == CHROME_WEB_STORE_URL

    def test_launchpad_card_gates_cta_on_web_store_url(self):
        tpl = (REPO / "src/trinity_local/launchpad_template.py").read_text()
        # The card branches on webStoreUrl: "Add to Chrome" when set,
        # sideload docs when empty.
        assert "pageData.browserExtension.webStoreUrl" in tpl
        assert "Add to Chrome" in tpl
