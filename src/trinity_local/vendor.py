"""Vendored JS dependencies for the launchpad + memory viewer + council
review pages.

100-persona audit P06 fix: prior cuts loaded marked / petite-vue /
chart.js / 9 d3-* modules from unpkg + jsdelivr on every page open.
That contradicted the "never leaves your machine" privacy absolute —
each launchpad render reached out to 13 third-party CDNs, exposing
the user's IP + a browser fingerprint to mirrors that have no business
in the Trinity wedge.

This module publishes the same files locally:

- Bundled into the wheel under ``src/trinity_local/data/vendor/*.js``
  via the package-data declaration in pyproject.toml.
- Copied into ``~/.trinity/portal_pages/vendor/`` on each portal-html
  regen (idempotent, content-hash-skip when up-to-date).
- HTML templates reference ``./vendor/<file>.js`` instead of CDN URLs.

Net result: launchpad + memory viewer + council review all render with
zero outbound network traffic. The privacy claim becomes absolutely
true, not "absolutely true except 13 JS files."

Refreshing the vendored set is a maintenance ritual (when a new d3
version ships): edit + run ``scripts/refresh-vendor.sh``. The script
pins every URL with an explicit version; treat version bumps as
security-sensitive (the rendered HTML is what the user sees offline,
so the bytes have to be auditable). After refresh, re-run
``pytest tests/test_no_cdn_in_rendered_html.py`` — the 5 guards there
re-render launchpad + memory-viewer and check zero unpkg/jsdelivr
references make it into the produced HTML.
"""
from __future__ import annotations

import hashlib
import sys
from importlib import resources
from pathlib import Path


# Canonical list — keep in sync with files actually present under
# src/trinity_local/data/vendor/. A presence check at write time
# surfaces drift between this list and the package_data wildcard.
VENDORED_FILES: tuple[str, ...] = (
    "petite-vue.es.js",
    "chart.umd.min.js",
    "marked.min.js",
    "d3-selection.min.js",
    "d3-dispatch.min.js",
    "d3-timer.min.js",
    "d3-quadtree.min.js",
    "d3-drag.min.js",
    "d3-force.min.js",
    "d3-zoom.min.js",
    "d3-interpolate.min.js",
    "d3-color.min.js",
)


def _read_vendored(name: str) -> bytes | None:
    """Load one vendored file via the package resources API. Returns
    None when the file isn't present (e.g. source layout without the
    data wired up) — caller falls back gracefully."""
    try:
        return resources.files("trinity_local").joinpath(f"data/vendor/{name}").read_bytes()
    except (FileNotFoundError, ModuleNotFoundError, AttributeError):
        return None


def publish_vendor_files(target_dir: Path) -> list[Path]:
    """Copy all vendored JS files into ``target_dir/vendor/``. Idempotent
    via byte-by-byte content compare: re-runs are no-ops when nothing
    changed. Skips missing files silently (graceful degradation for
    source layouts that don't bundle the data — pages will still try
    to load ./vendor/* and 404 cleanly).

    Returns the list of paths actually written this call (zero on
    no-op runs, non-zero on first publish or post-upgrade).
    """
    vendor_dir = target_dir / "vendor"
    vendor_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    for name in VENDORED_FILES:
        payload = _read_vendored(name)
        if payload is None:
            continue
        target = vendor_dir / name
        if target.exists():
            try:
                if hashlib.sha256(target.read_bytes()).digest() == hashlib.sha256(payload).digest():
                    continue
            except OSError:
                pass
        try:
            target.write_bytes(payload)
            written.append(target)
        except OSError as exc:
            print(
                f"warning: failed to publish vendored file {name!r} "
                f"to {target}: {exc.__class__.__name__}: {exc}. "
                f"Launchpad will 404 on ./vendor/{name} — "
                f"check perms on {vendor_dir}.",
                file=sys.stderr,
            )
    return written
