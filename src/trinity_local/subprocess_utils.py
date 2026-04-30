from __future__ import annotations

import subprocess
from pathlib import Path
from typing import Any

from .runtime_env import build_runtime_env


def run_with_runtime_env(
    args: list[str],
    *,
    cwd: Path | str | None = None,
    timeout: float | None = None,
    capture_output: bool = True,
    text: bool = True,
    check: bool = False,
    input: str | None = None,
    env: dict[str, str] | None = None,
    python_executable: str | None = None,
) -> subprocess.CompletedProcess[Any]:
    resolved_cwd = str(cwd) if isinstance(cwd, Path) else cwd
    return subprocess.run(
        args,
        cwd=resolved_cwd,
        timeout=timeout,
        capture_output=capture_output,
        text=text,
        check=check,
        input=input,
        env=build_runtime_env(env, python_executable=python_executable),
    )
