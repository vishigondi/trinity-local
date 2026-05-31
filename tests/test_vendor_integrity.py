"""Vendored-JS supply-chain integrity guard.

The launchpad / memory-viewer / council pages serve 12 vendored JS libraries
from ``src/trinity_local/data/vendor/`` (so the "never leaves your machine"
privacy claim doesn't depend on a CDN being an honest broker at render time).
``scripts/vendor-sha256.txt`` pins the expected SHA-256 of each vendored file.

This guard fails if a committed vendored file's bytes drift from its pinned
hash — catching a tampered/swapped library, or a version bump that updated the
bytes but not the manifest.

On a DELIBERATE bump: edit the URL in ``scripts/refresh-vendor.sh``, re-run it
(``scripts/refresh-vendor.sh --update-manifest`` regenerates the manifest), and
commit the URL + new bytes + new manifest line together so the diff is auditable.
"""
from __future__ import annotations

import hashlib
import pathlib

REPO = pathlib.Path(__file__).resolve().parents[1]
VENDOR = REPO / "src" / "trinity_local" / "data" / "vendor"
MANIFEST = REPO / "scripts" / "vendor-sha256.txt"


def _manifest() -> dict[str, str]:
    out: dict[str, str] = {}
    for line in MANIFEST.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        sha, name = line.split()
        out[name] = sha
    return out


def test_vendored_js_matches_sha256_manifest():
    manifest = _manifest()
    actual = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in VENDOR.glob("*.js")
    }
    assert set(actual) == set(manifest), (
        "vendor/ files vs manifest mismatch: "
        f"only-in-dir={sorted(set(actual) - set(manifest))}, "
        f"only-in-manifest={sorted(set(manifest) - set(actual))}. "
        "Regenerate scripts/vendor-sha256.txt."
    )
    drift = {n: (manifest[n], actual[n]) for n in actual if actual[n] != manifest[n]}
    assert not drift, (
        "Vendored JS bytes drifted from the pinned SHA-256 (tampering, or a "
        f"version bump that didn't update the manifest): {drift}. If intentional, "
        "re-run `scripts/refresh-vendor.sh --update-manifest` and commit the new "
        "bytes + manifest together."
    )
