"""User-facing setup guidance helpers."""
from __future__ import annotations

from .adapters import AdapterStatus


def _provider_install_block(status: AdapterStatus) -> list[str]:
    if status.provider == "claude":
        return [
            "Claude Code",
            "  npm install -g @anthropic-ai/claude-code",
        ]
    if status.provider == "codex":
        return [
            "Codex CLI",
            "  npm install -g @openai/codex && codex --login",
        ]
    if status.provider == "antigravity":
        return [
            "Antigravity",
            "  curl -fsSL https://antigravity.google/cli/install.sh | bash && agy",
        ]
    if status.provider == "cowork":
        return [
            "Cowork / Claude Desktop",
            "  Install Claude Desktop, then open Local Agent Mode once.",
        ]
    return [
        status.provider,
        f"  Install the {status.provider} provider and rerun Trinity.",
    ]


def render_missing_provider_guidance(statuses: list[AdapterStatus]) -> str | None:
    """Return a setup block with copy-paste install commands for missing providers."""
    missing = [status for status in statuses if not status.installed]
    if not missing:
        return None

    lines = [
        "📦 Missing providers — copy/paste commands below:",
        "",
    ]
    for status in missing:
        block = _provider_install_block(status)
        lines.append(f"  • {block[0]}")
        lines.append(f"    {block[1]}")
        lines.append("")

    lines.extend(
        [
            "Trinity needs at least 2 providers for cross-provider insights.",
            "After installing, open a new terminal and run:",
            "",
            "  trinity-local status",
            "",
            "Trinity will pick up newly installed providers automatically.",
        ]
    )
    return "\n".join(lines)
