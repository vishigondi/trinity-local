from __future__ import annotations

from pathlib import Path


def refresh_launchpad(*, title: str = "Trinity Launchpad", video_url: str | None = None) -> Path:
    from .portal_page import write_portal_html

    return write_portal_html(title=title, video_url=video_url)

