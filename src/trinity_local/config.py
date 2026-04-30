from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ProviderConfig:
    name: str
    type: str
    enabled: bool
    label: str
    command: list[str]
    args: list[str]
    roles: set[str]
    task_kinds: set[str]
    model: str | None = None


@dataclass(frozen=True)
class AppConfig:
    max_turns: int
    default_task_kind: str
    notifications: bool
    providers: dict[str, ProviderConfig]
    role_preferences: dict[str, list[str]]
    task_preferences: dict[str, list[str]]


def project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def trinity_home() -> Path:
    """Return the Trinity state directory.

    Defaults to ``~/.trinity/``. Override with ``TRINITY_HOME`` env var.
    The directory is created on first access.
    """
    env = os.environ.get("TRINITY_HOME")
    if env:
        path = Path(env).expanduser().resolve()
    else:
        path = Path.home() / ".trinity"
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_path(explicit: str | None = None) -> Path:
    if explicit:
        return Path(explicit).expanduser().resolve()
    return project_root() / "config.json"


def load_config(explicit: str | None = None, *, required: bool = True) -> AppConfig:
    """Load configuration from disk.

    Args:
        explicit: explicit path to config.json; uses project_root()/config.json if None.
        required: if True (default), raises FileNotFoundError when the config
            file is missing.  When False, returns a minimal empty config instead
            — useful for read-only CLI commands that only inspect state.
    """
    path = config_path(explicit)
    if not path.exists():
        if not required:
            return _empty_config()
        raise FileNotFoundError(
            f"Missing config file at {path}. Copy config.example.json to config.json first."
        )

    raw = json.loads(path.read_text())
    providers: dict[str, ProviderConfig] = {}
    for name, provider in raw["providers"].items():
        providers[name] = ProviderConfig(
            name=name,
            type=provider["type"],
            enabled=provider.get("enabled", True),
            label=provider.get("label", name),
            command=list(provider["command"]),
            args=list(provider.get("args", [])),
            roles=set(provider.get("roles", [])),
            task_kinds=set(provider.get("task_kinds", [])),
            model=provider.get("model"),
        )

    return AppConfig(
        max_turns=int(raw.get("max_turns", 4)),
        default_task_kind=raw.get("default_task_kind", "general"),
        notifications=bool(raw.get("notifications", True)),
        providers=providers,
        role_preferences={
            key: list(value) for key, value in raw.get("role_preferences", {}).items()
        },
        task_preferences={
            key: list(value) for key, value in raw.get("task_preferences", {}).items()
        },
    )


def _empty_config() -> AppConfig:
    """Return a minimal config with no providers — used when config is optional."""
    return AppConfig(
        max_turns=4,
        default_task_kind="general",
        notifications=False,
        providers={},
        role_preferences={},
        task_preferences={},
    )
