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
    task_types: set[str]
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
            task_types=set(provider.get("task_types", [])),
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


# Canonical 3-provider lineup for parallel councils, in display order.
# Codex-only / claude-only / gemini-only users (persona audit P89) had
# broken 3-column councils because 9 sites hardcoded this list as a
# default; the helper below picks the enabled subset so a single-
# provider user gets a clean single-call instead of failed 3-of-3.
CANONICAL_COUNCIL_PROVIDERS: tuple[str, ...] = ("claude", "gemini", "codex")


def default_council_members(explicit: str | None = None) -> list[str]:
    """Return the canonical 3-provider council lineup filtered to whatever
    the user has actually enabled in config.json. Preserves canonical order.

    When config can't be loaded (cold install, malformed file) OR no
    cloud providers are enabled, returns the full canonical list — the
    caller's existing "Provider missing or disabled" error path is the
    right thing to surface.

    Use this as the default whenever a CLI / MCP / launchpad surface
    would otherwise hardcode ``["claude", "gemini", "codex"]``. Honors
    user override (--members on CLI, members= on MCP) unchanged.
    """
    try:
        config = load_config(explicit, required=False)
    except Exception:
        return list(CANONICAL_COUNCIL_PROVIDERS)
    enabled = {
        name for name, p in config.providers.items()
        if getattr(p, "enabled", True) and name in CANONICAL_COUNCIL_PROVIDERS
    }
    if not enabled:
        return list(CANONICAL_COUNCIL_PROVIDERS)
    return [name for name in CANONICAL_COUNCIL_PROVIDERS if name in enabled]
