"""macOS Shortcut dispatch — retired 2026-05-17.

The Shortcut dispatcher (the `Trinity Dispatch` Shortcut + `~/.trinity/bin/
trinity-dispatch` shell wrapper + `shortcut-install` CLI) was the v1.0
launchpad's macOS-only dispatch path. The Chrome extension's Native
Messaging host (`capture_host.py`) is the cross-platform replacement
and is now the canonical dispatch tier.

This module remains as an inert shim so the renderers
(`council_review.py`, `launchpad_data.py`, `action_runtime.py`)
keep importing without breaking. `make_shortcut_invocation` now returns
empty URLs — the JS dispatch in `launchpad_runtime.js` skips
tier-2-shortcut when the URL is empty and routes everything through the
extension.

Slated for full removal once the consumer-side JS + HTML surgery lands
(template buttons stop building shortcut:// URLs entirely).
"""
from __future__ import annotations

from dataclasses import dataclass

from .dispatch_registry import DispatchAction

DEFAULT_SHORTCUT_NAME = "Trinity Dispatch"


@dataclass
class ShortcutInvocation:
    shortcut_name: str
    input_text: str
    url: str

    def to_dict(self) -> dict[str, str]:
        return {
            "shortcut_name": self.shortcut_name,
            "input_text": self.input_text,
            "url": self.url,
        }


def make_shortcut_invocation(
    *,
    dispatch: DispatchAction,
    shortcut_name: str = DEFAULT_SHORTCUT_NAME,
) -> ShortcutInvocation:
    return ShortcutInvocation(shortcut_name=shortcut_name, input_text="", url="")
