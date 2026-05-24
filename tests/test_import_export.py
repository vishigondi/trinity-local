"""Tests for #148 — trinity-local import-export bulk Takeout import.

Detection-side tests use small synthetic files (no real ingest runs).
The actual parsers (parse_chatgpt_export / parse_claude_ai_export /
parse_gemini_takeout_html) are exercised by their own dedicated test
suites; this file locks down the auto-detect + dry-run + CLI shape.
"""
from __future__ import annotations

import argparse
import json

import pytest

from trinity_local.commands import import_export


@pytest.fixture
def export_root(tmp_path):
    return tmp_path / "exports"


def _write_chatgpt_conversations(path):
    """Synthetic ChatGPT export — first conversation has `mapping` key."""
    path.write_text(json.dumps([
        {
            "id": "conv1",
            "title": "test",
            "mapping": {"root": {"id": "root"}},
        }
    ]), encoding="utf-8")


def _write_claude_ai_conversations(path):
    """Synthetic Claude.ai export — first conversation has `chat_messages` key."""
    path.write_text(json.dumps([
        {
            "uuid": "conv1",
            "name": "test",
            "chat_messages": [],
        }
    ]), encoding="utf-8")


def _write_gemini_takeout_html(path):
    """Minimal stub — file existence + name is what _detect_single_file checks."""
    path.write_text("<html><body>fake takeout</body></html>", encoding="utf-8")


class TestDetectSingleFile:
    def test_chatgpt_conversations_json_detected(self, tmp_path):
        p = tmp_path / "conversations.json"
        _write_chatgpt_conversations(p)
        assert import_export._detect_single_file(p) == "chatgpt"

    def test_claude_ai_conversations_json_detected(self, tmp_path):
        p = tmp_path / "conversations.json"
        _write_claude_ai_conversations(p)
        assert import_export._detect_single_file(p) == "claude_ai"

    def test_gemini_takeout_html_detected_at_root(self, tmp_path):
        p = tmp_path / "MyActivity.html"
        _write_gemini_takeout_html(p)
        assert import_export._detect_single_file(p) == "gemini_takeout"

    def test_unknown_file_returns_none(self, tmp_path):
        p = tmp_path / "random.json"
        p.write_text('{"foo": "bar"}', encoding="utf-8")
        assert import_export._detect_single_file(p) is None

    def test_conversations_json_without_known_keys_returns_none(self, tmp_path):
        """A file named conversations.json that has neither `mapping` nor
        `chat_messages` shouldn't be classified — it's not a real export."""
        p = tmp_path / "conversations.json"
        p.write_text(json.dumps([{"foo": "bar"}]), encoding="utf-8")
        assert import_export._detect_single_file(p) is None


class TestDetectExports:
    def test_directory_with_chatgpt_export(self, export_root):
        export_root.mkdir(parents=True)
        _write_chatgpt_conversations(export_root / "conversations.json")
        results = import_export.detect_exports(export_root)
        assert len(results) == 1
        assert results[0]["source"] == "chatgpt"
        assert results[0]["path"].endswith("conversations.json")

    def test_directory_with_multiple_exports(self, export_root):
        """A user may have downloaded both ChatGPT and Claude.ai exports
        and dropped them in one directory. All detected."""
        (export_root / "chatgpt").mkdir(parents=True)
        (export_root / "claude").mkdir(parents=True)
        _write_chatgpt_conversations(export_root / "chatgpt" / "conversations.json")
        _write_claude_ai_conversations(export_root / "claude" / "conversations.json")

        results = import_export.detect_exports(export_root)
        sources = sorted(r["source"] for r in results)
        assert sources == ["chatgpt", "claude_ai"]

    def test_gemini_takeout_nested_path(self, export_root):
        """Real Gemini Takeout layout: Takeout/My Activity/Gemini Apps/MyActivity.html"""
        nested = export_root / "Takeout" / "My Activity" / "Gemini Apps"
        nested.mkdir(parents=True)
        _write_gemini_takeout_html(nested / "MyActivity.html")

        results = import_export.detect_exports(export_root)
        assert len(results) == 1
        assert results[0]["source"] == "gemini_takeout"

    def test_empty_directory_returns_empty(self, export_root):
        export_root.mkdir(parents=True)
        assert import_export.detect_exports(export_root) == []

    def test_skips_common_noise_dirs(self, export_root):
        """node_modules, .venv, __pycache__ etc. shouldn't be probed even
        if they happen to contain a conversations.json."""
        for noise in ("node_modules", ".venv", "__pycache__"):
            d = export_root / noise
            d.mkdir(parents=True)
            _write_chatgpt_conversations(d / "conversations.json")

        # No real exports → detect returns empty (the synthetic
        # conversations.json files in noise dirs are skipped)
        results = import_export.detect_exports(export_root)
        assert results == []


class TestCliHandler:
    def _args(self, **overrides):
        defaults = dict(
            path=None, source=None, dry_run=True,
            limit=None, batch_size=64, dim=768,
            progress=False,
        )
        defaults.update(overrides)
        return argparse.Namespace(**defaults)

    def test_missing_path_exits_with_error_json(self, tmp_path, capsys):
        with pytest.raises(SystemExit) as exc:
            import_export.handle_import_export(self._args(path=str(tmp_path / "missing")))
        assert exc.value.code == 1
        out = capsys.readouterr().out
        payload = json.loads(out)
        assert payload["ok"] is False
        assert "path not found" in payload["error"]

    def test_no_exports_detected_exits_with_hint(self, tmp_path, capsys):
        # Empty directory, no detection
        (tmp_path / "empty").mkdir()
        with pytest.raises(SystemExit) as exc:
            import_export.handle_import_export(self._args(path=str(tmp_path / "empty")))
        assert exc.value.code == 1
        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is False
        assert "no exports detected" in payload["error"]
        # Hint must mention the expected shapes so user knows what to try
        assert "conversations.json" in payload["hint"]
        assert "Takeout" in payload["hint"]

    def test_dry_run_reports_detected_without_ingesting(self, tmp_path, capsys):
        export_dir = tmp_path / "ex"
        export_dir.mkdir()
        _write_chatgpt_conversations(export_dir / "conversations.json")

        import_export.handle_import_export(self._args(path=str(export_dir), dry_run=True))
        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is True
        assert payload["mode"] == "dry-run"
        assert len(payload["detected"]) == 1
        assert payload["detected"][0]["source"] == "chatgpt"

    def test_force_source_bypasses_detection(self, tmp_path, capsys):
        """--source overrides auto-detect. Useful when probe heuristics
        get it wrong (e.g., renamed file)."""
        export_dir = tmp_path / "ex"
        export_dir.mkdir()
        renamed = export_dir / "my_chatgpt_dump.json"
        _write_chatgpt_conversations(renamed)

        import_export.handle_import_export(
            self._args(path=str(renamed), source="chatgpt", dry_run=True)
        )
        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is True
        assert payload["detected"][0]["source"] == "chatgpt"
        assert "forced" in payload["detected"][0]["hint"]


def test_cli_registration_lists_import_export_subcommand():
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    import_export.register(subparsers)
    args = parser.parse_args(["import-export", "/tmp/example", "--dry-run"])
    assert args.command == "import-export"
    assert args.path == "/tmp/example"
    assert args.dry_run is True


class TestActionAllowlist:
    """#148 launchpad UI surface (slice 2 of #148): capture-host action
    dispatch entries so the launchpad's file-picker button fires
    `import-export` via Native Messaging.

    Same guard shape as test_memory_health's test_dream_in_action_allowlist
    — without the allowlist entry the dispatch silently no-ops.
    """

    def test_import_export_in_allowlist(self):
        from trinity_local.capture_host import ACTION_ALLOWLIST
        assert "import-export" in ACTION_ALLOWLIST
        entry = ACTION_ALLOWLIST["import-export"]
        assert entry[0] == "import-export"
        # path is required so the dispatch can't fire blind
        arg_spec = entry[1]
        required_args = [name for name, _, required in arg_spec if required]
        assert "path" in required_args

    def test_import_export_dry_run_in_allowlist(self):
        """Detection-only variant — same CLI, --dry-run as a constant
        flag so payload can't escalate to full ingest by omitting it."""
        from trinity_local.capture_host import ACTION_ALLOWLIST
        assert "import-export-dry-run" in ACTION_ALLOWLIST
        entry = ACTION_ALLOWLIST["import-export-dry-run"]
        assert entry[0] == "import-export"
        # Constant flags include --dry-run — that's host-controlled,
        # not payload-influenced (the security property).
        constant_flags = entry[2] if len(entry) == 3 else []
        assert "--dry-run" in constant_flags

    def test_launchpad_renders_import_card_with_dispatch_wiring(self):
        """#148 UI slice: the launchpad import-export card must render
        with the paste-path input, Probe/Import buttons, and both
        extensionAction kinds wired (dry-run + full). The Vue state
        machine must include importPath / importStatus / importProbeResult.
        Same guard pattern as memory-health's button test."""
        from trinity_local.launchpad_template import render_launchpad_html

        html = render_launchpad_html(page_data={}, recent_cards="")
        # Card header + intro copy
        assert "Bulk import (#148)" in html, "card eyebrow missing"
        assert "Import old Claude / ChatGPT / Gemini exports" in html, "h2 missing"
        # Paste-path input
        assert 'v-model="importPath"' in html, "path input missing"
        # Both action buttons
        assert '@click="probeImportPath"' in html, "Probe handler missing"
        assert '@click="confirmImport"' in html, "Import handler missing"
        # Both extensionAction kinds — dry-run for probe + full for confirm
        assert "kind: 'import-export-dry-run'" in html, "dry-run kind missing"
        assert "kind: 'import-export'" in html, "full-import kind missing"
        # Vue state machine fields
        assert "importPath:" in html, "importPath state field missing"
        assert "importStatus:" in html, "importStatus state field missing"
        assert "importProbeResult:" in html, "importProbeResult state field missing"
        # Path is passed through the dispatch payload — required for the
        # capture-host action allowlist to receive a real value.
        assert "path: this.importPath" in html, "path payload not threaded"

    def test_path_flag_alias_works(self, tmp_path, capsys):
        """The launchpad action dispatcher invokes the CLI via
        --flag VALUE pairs, so --path must work as an alias for the
        positional path argument."""
        import argparse
        export_dir = tmp_path / "ex"
        export_dir.mkdir()
        _write_chatgpt_conversations(export_dir / "conversations.json")

        ns = argparse.Namespace(
            path=None,  # positional unset
            path_flag=str(export_dir),
            source=None,
            dry_run=True,
            limit=None,
            batch_size=64,
            dim=768,
        )
        import_export.handle_import_export(ns)
        payload = json.loads(capsys.readouterr().out)
        assert payload["ok"] is True
        assert payload["mode"] == "dry-run"
