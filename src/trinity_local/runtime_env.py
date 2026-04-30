from __future__ import annotations

import os
import sys
from pathlib import Path


def project_venv_root(python_executable: str | None = None) -> Path:
    executable = Path(python_executable or sys.executable)
    return executable.expanduser().parent.parent.resolve()


def project_venv_bin(python_executable: str | None = None) -> Path:
    return project_venv_root(python_executable) / "bin"


def runtime_bin_paths(python_executable: str | None = None) -> list[str]:
    candidates = [
        str(project_venv_bin(python_executable)),
        str((Path.home() / ".local" / "bin").expanduser()),
        "/opt/homebrew/bin",
        "/usr/local/bin",
    ]
    unique: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        if candidate and candidate not in seen:
            seen.add(candidate)
            unique.append(candidate)
    return unique


def runtime_path_prefix(python_executable: str | None = None) -> str:
    return ":".join(runtime_bin_paths(python_executable))


def build_runtime_env(
    env: dict[str, str] | None = None,
    *,
    python_executable: str | None = None,
) -> dict[str, str]:
    merged = dict(os.environ if env is None else env)
    current_path = merged.get("PATH", "")
    parts = runtime_bin_paths(python_executable)
    if current_path:
        parts.append(current_path)
    merged["PATH"] = ":".join(part for part in parts if part)
    return merged
