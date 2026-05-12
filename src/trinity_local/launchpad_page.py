from __future__ import annotations

from pathlib import Path

from .council_review import write_live_council_page
from .launchpad_data import _load_recent_councils, build_page_data, build_recent_cards_html
from .launchpad_install import install_launchpad_shortcuts, write_launchpad_app
from .launchpad_template import render_launchpad_html as _render_template
from .state_paths import portal_pages_dir

__all__ = [
    "render_launchpad_html",
    "write_portal_html",
    "write_launchpad_app",
    "install_launchpad_shortcuts",
]


def render_launchpad_html(*, title: str = "Trinity · Own your memories") -> str:
    # CLI's portal-html is the canonical place to refresh the live page;
    # force=True overwrites whatever's on disk with the current source.
    # MCP-side calls leave force=False so a stale long-running server can't
    # clobber the fresh template a previous portal-html wrote.
    live_review_path = write_live_council_page(force=True).resolve()
    recent_councils = _load_recent_councils(limit=8)
    page_data = build_page_data(
        live_review_path=live_review_path,
        recent_councils=recent_councils,
    )
    recent_cards = build_recent_cards_html(recent_councils)
    return _render_template(page_data=page_data, recent_cards=recent_cards, title=title)


def write_portal_html(*, title: str = "Trinity · Own your memories") -> Path:
    path = portal_pages_dir() / "launchpad.html"
    path.write_text(render_launchpad_html(title=title), encoding="utf-8")
    return path
