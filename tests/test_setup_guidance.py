from __future__ import annotations

from trinity_local.adapters import AdapterStatus
from trinity_local.setup_guidance import render_missing_provider_guidance


def test_render_missing_provider_guidance_includes_copy_paste_commands():
    guidance = render_missing_provider_guidance(
        [
            AdapterStatus(provider="claude", cli_name="claude", installed=False),
            AdapterStatus(provider="codex", cli_name="codex", installed=False),
            AdapterStatus(provider="gemini", cli_name="gemini", installed=False),
            AdapterStatus(provider="cowork", cli_name="claude-desktop", installed=False),
        ]
    )

    assert guidance is not None
    assert "npm install -g @anthropic-ai/claude-code" in guidance
    assert "npm install -g @openai/codex && codex --login" in guidance
    assert "npm install -g @google/gemini-cli && gemini" in guidance
    assert "Install Claude Desktop, then open Local Agent Mode once." in guidance
    assert "Trinity will pick up newly installed providers automatically." in guidance


def test_render_missing_provider_guidance_returns_none_when_everything_is_installed():
    guidance = render_missing_provider_guidance(
        [
            AdapterStatus(provider="claude", cli_name="claude", installed=True),
            AdapterStatus(provider="codex", cli_name="codex", installed=True),
        ]
    )

    assert guidance is None
