"""Per-harness paste-in snippet generator (#166, Phase A).

The popup's `harness-snippets.js` is the single source of truth for the
per-harness MCP config blocks. These guards pin: all six harnesses present,
the uvx-based command in each, the right config surface (JSON mcpServers vs
Codex's TOML mcp_servers), the target file paths, and that the popup actually
loads + invokes the module. Drift here silently breaks the lowest-friction
install path.
"""
from __future__ import annotations

from pathlib import Path

EXT = Path(__file__).resolve().parent.parent / "browser-extension"


def _snippets_js() -> str:
    return (EXT / "harness-snippets.js").read_text(encoding="utf-8")


class TestHarnessSnippetModule:
    def test_module_file_exists(self):
        assert (EXT / "harness-snippets.js").exists()

    def test_all_six_harness_labels_present(self):
        js = _snippets_js()
        for label in (
            "Claude Code", "Claude Desktop", "Codex CLI",
            "Cursor", "Antigravity", "Cline (VS Code)",
        ):
            assert label in js, f"harness {label!r} missing from snippet module"

    def test_each_harness_id_present(self):
        js = _snippets_js()
        for hid in ("claude-code", "claude-desktop", "codex", "cursor", "antigravity", "cline"):
            assert f'id: "{hid}"' in js, f"harness id {hid!r} missing"

    def test_uvx_command_is_the_recommended_path(self):
        js = _snippets_js()
        # Every harness rides the uvx zero-prereq invocation.
        assert '"command": "uvx"' in js   # JSON harnesses
        assert 'command = "uvx"' in js    # Codex TOML
        assert '"trinity-local", "--mcp"' in js

    def test_json_harnesses_use_mcpservers_key(self):
        assert '"mcpServers"' in _snippets_js()

    def test_codex_uses_toml_mcp_servers_table(self):
        # Codex reads TOML, not JSON — the one harness with a different surface.
        assert "[mcp_servers.trinity-local]" in _snippets_js()

    def test_target_file_paths_present(self):
        js = _snippets_js()
        for path in (
            "~/.claude.json",
            "~/.codex/config.toml",
            "~/.cursor/mcp.json",
            "~/.gemini/settings.json",
        ):
            assert path in js, f"target path {path!r} missing"

    def test_exposes_renderer_and_data_globals(self):
        js = _snippets_js()
        assert "renderHarnessPicker" in js
        assert "TRINITY_HARNESS_SNIPPETS" in js

    def test_module_is_chrome_free(self):
        # The whole point: loads standalone (no extension context), so it
        # must not touch chrome.* — otherwise it can't be the single source
        # of truth nor be browser-tested outside the extension.
        assert "chrome." not in _snippets_js()


class TestPopupWiresThePicker:
    def test_popup_html_loads_the_module_before_popup_js(self):
        html = (EXT / "popup.html").read_text(encoding="utf-8")
        # Match the <script src> tags specifically — "popup.js" also appears
        # in the file's top comment, so a bare .index would mis-order.
        assert 'src="harness-snippets.js"' in html
        assert html.index('src="harness-snippets.js"') < html.index('src="popup.js"')

    def test_popup_js_invokes_the_picker_in_setup_card(self):
        js = (EXT / "popup.js").read_text(encoding="utf-8")
        assert "renderHarnessPicker(body)" in js
