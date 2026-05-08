from __future__ import annotations

from pathlib import Path


def refresh_launchpad(*, title: str = "Trinity Launchpad") -> Path:
    from .portal_page import write_portal_html

    _backfill_thread_manifests()
    return write_portal_html(title=title)


def _backfill_thread_manifests() -> int:
    """Safety net for the recurring stale-MCP bug: a long-running MCP server
    can save council outcomes via old code that didn't yet call
    `update_thread_manifest`. Result: `~/.trinity/council_outcomes/*.json`
    exists, but `_thread_<bundle>.js` does not — and the recent-council card
    on the launchpad 404s when clicked.

    Every `portal-html` regen scans for outcomes whose thread manifest is
    missing and writes one. Cheap (one fs stat per outcome); idempotent."""
    from .council_runtime import update_thread_manifest, load_council_outcome
    from .state_paths import council_outcomes_dir

    outcomes_dir = council_outcomes_dir()
    written = 0
    for outcome_path in outcomes_dir.glob("council_*.json"):
        try:
            outcome = load_council_outcome(outcome_path.stem)
        except Exception:
            continue
        chain_root = (outcome.metadata or {}).get("chain_root_id") or outcome.bundle_id
        if not chain_root:
            continue
        if (outcomes_dir / f"_thread_{chain_root}.js").exists():
            continue
        try:
            update_thread_manifest(outcome)
            written += 1
        except Exception:
            continue
    return written
