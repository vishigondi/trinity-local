from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass
from urllib.parse import quote

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


def build_shortcut_url(shortcut_name: str, input_text: str) -> str:
    name = quote(shortcut_name, safe="")
    text = quote(input_text, safe="")
    return f"shortcuts://run-shortcut?name={name}&input=text&text={text}"


def build_dispatch_payload(dispatch: DispatchAction) -> str:
    return json.dumps(dispatch.to_dict(), separators=(",", ":"), ensure_ascii=True)


def make_shortcut_invocation(
    *,
    dispatch: DispatchAction,
    shortcut_name: str = DEFAULT_SHORTCUT_NAME,
) -> ShortcutInvocation:
    input_text = build_dispatch_payload(dispatch)
    return ShortcutInvocation(
        shortcut_name=shortcut_name,
        input_text=input_text,
        url=build_shortcut_url(shortcut_name, input_text),
    )


def run_shortcut(invocation: ShortcutInvocation) -> bool:
    if shutil.which("shortcuts"):
        completed = subprocess.run(
            ["shortcuts", "run", invocation.shortcut_name, "--input-path", "/dev/stdin"],
            input=invocation.input_text,
            capture_output=True,
            text=True,
            check=False,
        )
        return completed.returncode == 0
    if shutil.which("open"):
        completed = subprocess.run(["open", invocation.url], capture_output=True, text=True, check=False)
        return completed.returncode == 0
    return False
