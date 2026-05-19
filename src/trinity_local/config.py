from __future__ import annotations

import json
import os
import shutil
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
    raw_text: str | None = None
    if path.exists():
        raw_text = path.read_text()
    else:
        # 100-persona audit D1 fix: a fresh wheel install has no
        # `config.json` next to project_root(), so the README's first
        # command (`council-launch --task "hello"`) used to crash with a
        # FileNotFoundError pointing at a site-packages path the user
        # neither owns nor knows about — the tweet-screenshot failure
        # mode. Fall through to the bundled `data/config.example.json`
        # so the hero command works on a clean pip install.
        try:
            from importlib import resources
            raw_text = (
                resources.files("trinity_local")
                .joinpath("data/config.example.json")
                .read_text(encoding="utf-8")
            )
        except (FileNotFoundError, ModuleNotFoundError, AttributeError):
            raw_text = None
        if raw_text is None:
            if not required:
                return _empty_config()
            raise FileNotFoundError(
                f"Missing config file at {path} and no bundled fallback found. "
                "Run `trinity-local install-mcp` to recreate config.json."
            )

    raw = json.loads(raw_text)
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


def installed_council_providers(explicit: str | None = None) -> list[str]:
    """Return the canonical lineup filtered to providers whose CLI binary
    is actually on PATH.

    The audience-expansion claim is "Trinity works with one provider —
    add the other two for richer disagreement signal." Today's default
    lineup ignores binary availability, so a user with only Claude
    installed gets a 3-member council that fails 2 of 3. Pre-filter to
    only the providers whose CLI we can actually invoke; the launchpad
    tip card surfaces the missing ones as a free-tier upsell.

    Fallback: if NO canonical providers have binaries on PATH, return
    the full canonical list. Caller's existing "Provider binary not
    found" error path becomes the diagnostic (the council fails
    clearly with a list of what to install, instead of silently
    rendering an empty council page).
    """
    try:
        config = load_config(explicit, required=False)
    except Exception:
        config = None

    enabled: set[str] = set(CANONICAL_COUNCIL_PROVIDERS)
    if config is not None:
        enabled = {
            name for name, p in config.providers.items()
            if getattr(p, "enabled", True) and name in CANONICAL_COUNCIL_PROVIDERS
        }
        if not enabled:
            enabled = set(CANONICAL_COUNCIL_PROVIDERS)

    available: list[str] = []
    for name in CANONICAL_COUNCIL_PROVIDERS:
        if name not in enabled:
            continue
        provider_config = (
            config.providers.get(name) if config is not None else None
        )
        binary = (
            provider_config.command[0]
            if provider_config and provider_config.command
            else name
        )
        if shutil.which(binary) is not None:
            available.append(name)
    if not available:
        return list(CANONICAL_COUNCIL_PROVIDERS)
    return available


def default_council_members(explicit: str | None = None) -> list[str]:
    """Return the canonical lineup filtered by enable+install status.

    Alias for ``installed_council_providers`` — kept as the public
    name every CLI / MCP / launchpad caller already uses. The PATH
    filter (added 2026-05-19) makes the 1-member council case the
    natural default for users who haven't installed all three CLIs,
    rather than a 3-member council that fails 2 of 3.
    """
    return installed_council_providers(explicit)
