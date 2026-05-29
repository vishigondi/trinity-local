"""Tests for the status command."""
from __future__ import annotations

import json
from unittest.mock import patch

from trinity_local.commands.status import handle_status


class Args:
    def __init__(self, as_json: bool = False):
        self.as_json = as_json


class TestStatusCommand:
    """Test the status command outputs."""

    def test_status_json_output(self, tmp_path, monkeypatch, capsys):
        """Test status --json produces valid JSON."""
        # Isolate TRINITY_HOME so run_doctor() + signal helpers probe
        # tmp_path instead of the dev machine's real ~/.trinity/. Without
        # this the test took ~4s walking real state (40k+ transcripts);
        # with it the test runs in ~0.3s.
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        with patch("trinity_local.commands.status.state_dir") as mock_state:
            mock_state.return_value = tmp_path
            mock_state_dir = tmp_path / "test"
            mock_state_dir.mkdir()

            with patch("trinity_local.commands.status.tasks_dir") as mock_tasks:
                mock_tasks.return_value = mock_state_dir
                with patch(
                    "trinity_local.commands.status.check_all_adapters"
                ) as mock_adapters:
                    from trinity_local.adapters import AdapterStatus

                    mock_adapters.return_value = [
                        AdapterStatus(
                            provider="claude",
                            cli_name="claude",
                            installed=True,
                            version="1.0",
                            transcript_root=None,
                        )
                    ]
                    with patch(
                        "trinity_local.commands.status.count_actions_by_status"
                    ) as mock_actions:
                        mock_actions.return_value = {}
                        with patch(
                            "trinity_local.commands.status.check_drift"
                        ) as mock_drift:
                            mock_drift.return_value = []

                            args = Args(as_json=True)
                            handle_status(args)

                            captured = capsys.readouterr()
                            output = json.loads(captured.out)
                            assert "trinity_home" in output
                            assert "adapters" in output
                            assert "drift_alerts" in output

    def test_status_human_output(self, tmp_path, monkeypatch, capsys):
        """Test status with human-readable output."""
        # Same TRINITY_HOME isolation as the JSON variant — keeps the
        # test from probing real ~/.trinity/ state.
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        with patch("trinity_local.commands.status.state_dir") as mock_state:
            mock_state.return_value = tmp_path
            mock_state_dir = tmp_path / "test"
            mock_state_dir.mkdir()

            with patch("trinity_local.commands.status.tasks_dir") as mock_tasks:
                mock_tasks.return_value = mock_state_dir
                with patch(
                    "trinity_local.commands.status.check_all_adapters"
                ) as mock_adapters:
                    from trinity_local.adapters import AdapterStatus

                    mock_adapters.return_value = [
                        AdapterStatus(
                            provider="claude",
                            cli_name="claude",
                            installed=True,
                            version="1.0",
                            transcript_root=None,
                        )
                    ]
                    with patch(
                        "trinity_local.commands.status.count_actions_by_status"
                    ) as mock_actions:
                        mock_actions.return_value = {}
                        with patch(
                            "trinity_local.commands.status.check_drift"
                        ) as mock_drift:
                            mock_drift.return_value = []

                            args = Args(as_json=False)
                            handle_status(args)

                            captured = capsys.readouterr()
                            assert "Trinity Local — Status" in captured.out
                            assert "Adapters:" in captured.out


class TestActionableSignals:
    """Status surfaces action-takeable signals from the launchpad
    feature set (#140 lens edits, #141 conflicts, #150 capture-drift)
    so CLI-only users see them without opening the launchpad. Section
    silently hidden when all signal counts are zero."""

    def test_signals_section_hidden_when_all_zero(self, tmp_path, monkeypatch, capsys):
        """Steady-green install: no signals section at all. Keeps the
        common case terse."""
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))

        # Stub the three signal sources to all-zero responses
        from trinity_local.me import lens_edits as le_mod
        from trinity_local.me import conflicts as conflicts_mod
        from trinity_local.commands import extension_repair as repair_mod

        monkeypatch.setattr(le_mod, "pending_lens_edits_count", lambda: 0)
        monkeypatch.setattr(conflicts_mod, "count_active_conflicts", lambda: 0)
        monkeypatch.setattr(repair_mod, "detect_failure_patterns", lambda diag: [])

        args = Args(as_json=False)
        handle_status(args)
        out = capsys.readouterr().out
        assert "Signals:" not in out, (
            "Signals section must be silent when all signal counts are zero"
        )

    def test_lens_edits_pending_surfaces_signal(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        from trinity_local.me import lens_edits as le_mod
        from trinity_local.me import conflicts as conflicts_mod
        from trinity_local.commands import extension_repair as repair_mod

        monkeypatch.setattr(le_mod, "pending_lens_edits_count", lambda: 3)
        monkeypatch.setattr(conflicts_mod, "count_active_conflicts", lambda: 0)
        monkeypatch.setattr(repair_mod, "detect_failure_patterns", lambda diag: [])

        args = Args(as_json=False)
        handle_status(args)
        out = capsys.readouterr().out
        assert "Signals:" in out
        assert "lens.md edits" in out
        assert "3 pending" in out
        assert "trinity-local lens" in out

    def test_conflicts_surface_with_lens_md_pointer(self, tmp_path, monkeypatch, capsys):
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        from trinity_local.me import lens_edits as le_mod
        from trinity_local.me import conflicts as conflicts_mod
        from trinity_local.commands import extension_repair as repair_mod

        monkeypatch.setattr(le_mod, "pending_lens_edits_count", lambda: 0)
        monkeypatch.setattr(conflicts_mod, "count_active_conflicts", lambda: 2)
        monkeypatch.setattr(repair_mod, "detect_failure_patterns", lambda diag: [])

        args = Args(as_json=False)
        handle_status(args)
        out = capsys.readouterr().out
        assert "lens contradictions" in out
        assert "2 same-horizon" in out
        assert "Tensions in tension" in out

    def test_code_patch_pattern_surfaces_with_auto_repair_hint(self, tmp_path, monkeypatch, capsys):
        """The #150 code-patch pattern points at the auto-repair flow.
        User-action patterns get a separate signal line — they need
        manual cookie refresh, not a council dispatch."""
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        from trinity_local.me import lens_edits as le_mod
        from trinity_local.me import conflicts as conflicts_mod
        from trinity_local.commands import extension_repair as repair_mod

        monkeypatch.setattr(le_mod, "pending_lens_edits_count", lambda: 0)
        monkeypatch.setattr(conflicts_mod, "count_active_conflicts", lambda: 0)
        monkeypatch.setattr(repair_mod, "detect_failure_patterns", lambda diag: [
            {"fix_kind": "code-patch", "provider": "gemini", "pattern": "provider-extended-silence"},
            {"fix_kind": "user-action", "provider": "claude", "pattern": "stale-auth-cookie"},
        ])

        args = Args(as_json=False)
        handle_status(args)
        out = capsys.readouterr().out
        assert "capture drift" in out
        assert "1 code-patch" in out
        assert "extension repair --auto" in out
        assert "auth-cookie stale" in out
        assert "refresh login" in out

    def test_browser_captures_section_silent_on_cold_install(
        self, tmp_path, monkeypatch, capsys
    ):
        """No conversations/ directories exist (cold install) →
        Captures section silent. Keeps a clean fresh install from
        rendering an empty/zero-noise block."""
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        from trinity_local.commands import extension_repair as repair_mod

        # Stub the diagnose() result with no providers existing
        monkeypatch.setattr(
            repair_mod, "diagnose",
            lambda: {"providers": {
                "claude":  {"exists": False, "captures": 0, "hours_since_last": None},
                "chatgpt": {"exists": False, "captures": 0, "hours_since_last": None},
                "gemini":  {"exists": False, "captures": 0, "hours_since_last": None},
            }},
        )

        args = Args(as_json=False)
        handle_status(args)
        out = capsys.readouterr().out
        assert "Captures:" not in out, (
            "Captures section must stay silent when no extension data exists"
        )

    def test_browser_captures_section_renders_with_per_provider_rows(
        self, tmp_path, monkeypatch, capsys
    ):
        """When the extension is active, status shows per-provider
        counts + hours-since-last with the same shape as the launchpad
        browser-capture card."""
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        from trinity_local.commands import extension_repair as repair_mod

        monkeypatch.setattr(
            repair_mod, "diagnose",
            lambda: {"providers": {
                "claude":  {"exists": True, "captures": 50, "hours_since_last": 1.5,
                            "last_capture": "2026-05-24T00:00:00"},
                "chatgpt": {"exists": True, "captures": 12, "hours_since_last": 8.0,
                            "last_capture": "2026-05-23T18:00:00"},
                "gemini":  {"exists": True, "captures": 200, "hours_since_last": 0.2,
                            "last_capture": "2026-05-24T01:50:00"},
            }},
        )

        args = Args(as_json=False)
        handle_status(args)
        out = capsys.readouterr().out
        assert "Captures:" in out
        # Total across the 3 providers
        assert "262" in out
        # Per-provider rows present
        for slug in ("claude", "chatgpt", "gemini"):
            assert slug in out
        # Last-capture time surfaced
        assert "1.5h ago" in out
        assert "0.2h ago" in out

    def test_browser_captures_directory_exists_but_empty(
        self, tmp_path, monkeypatch, capsys
    ):
        """If a provider's directory exists but has zero files (extension
        installed, never captured anything yet for that provider),
        surface the "installed but no captures yet" hint so the user
        knows to check for capture failures."""
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        from trinity_local.commands import extension_repair as repair_mod

        monkeypatch.setattr(
            repair_mod, "diagnose",
            lambda: {"providers": {
                "claude":  {"exists": True, "captures": 5, "hours_since_last": 1.0},
                "chatgpt": {"exists": True, "captures": 0, "hours_since_last": None},
                "gemini":  {"exists": False, "captures": 0, "hours_since_last": None},
            }},
        )

        args = Args(as_json=False)
        handle_status(args)
        out = capsys.readouterr().out
        # chatgpt → installed but no captures yet
        assert "extension installed but no captures yet" in out
        # gemini → never captured (directory missing)
        assert "not yet captured" in out

    def test_captures_show_missing_from_sidebar_when_unsynced(
        self, tmp_path, monkeypatch, capsys
    ):
        """When a provider has captures but the sidebar shows more
        threads than the on-disk count (real production signal we
        observed: chatgpt 37 files, sidebar 38, 1 missing), the
        Captures: line must show the missing count so the user knows
        to run auto-sync. Same data source as the in-provider sync pill."""
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        from trinity_local.commands import extension_repair as repair_mod
        from trinity_local import capture_host as capture_mod

        monkeypatch.setattr(
            repair_mod, "diagnose",
            lambda: {"providers": {
                "claude":  {"exists": True, "captures": 30, "hours_since_last": 1.0},
                "chatgpt": {"exists": True, "captures": 37, "hours_since_last": 2.5},
                "gemini":  {"exists": True, "captures": 100, "hours_since_last": 0.5},
            }},
        )

        def fake_sync(payload):
            slug = payload.get("provider")
            # claude fully synced (0 missing); chatgpt has 5 missing;
            # gemini fully synced
            if slug == "chatgpt":
                return {"ok": True, "sidebar_count": 42, "on_disk_count": 37, "missing_count": 5}
            return {"ok": True, "sidebar_count": 30, "on_disk_count": 30, "missing_count": 0}

        monkeypatch.setattr(capture_mod, "_query_sync_status", fake_sync)

        args = Args(as_json=False)
        handle_status(args)
        out = capsys.readouterr().out
        # chatgpt: missing-from-sidebar suffix present
        assert "5 missing from sidebar" in out
        # claude + gemini: NO missing suffix (would be visual noise)
        # We check by reading the claude line; missing suffix absent
        for line in out.splitlines():
            if line.strip().startswith("✅ claude "):
                assert "missing from sidebar" not in line, (
                    "claude was fully synced — no missing-suffix should appear"
                )
            if line.strip().startswith("✅ gemini "):
                assert "missing from sidebar" not in line

    def test_signals_in_json_output_when_active(self, tmp_path, monkeypatch, capsys):
        """JSON output must include the same signals the human output
        renders — scripts/agents parsing JSON otherwise have no
        visibility into the action-takeable items.

        The `signals` key is always present (empty list when nothing
        fires), so callers can `len(status["signals"])` without an
        existence branch."""
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        from trinity_local.me import lens_edits as le_mod
        from trinity_local.me import conflicts as conflicts_mod
        from trinity_local.commands import extension_repair as repair_mod

        monkeypatch.setattr(le_mod, "pending_lens_edits_count", lambda: 7)
        monkeypatch.setattr(conflicts_mod, "count_active_conflicts", lambda: 1)
        monkeypatch.setattr(repair_mod, "detect_failure_patterns", lambda d: [
            {"fix_kind": "code-patch", "provider": "gemini"},
        ])
        monkeypatch.setattr(repair_mod, "diagnose", lambda: {"providers": {}})

        args = Args(as_json=True)
        handle_status(args)
        payload = json.loads(capsys.readouterr().out)

        assert "signals" in payload
        kinds = [s["kind"] for s in payload["signals"]]
        assert "lens_edits_pending" in kinds
        assert "lens_contradictions" in kinds
        assert "capture_drift" in kinds

        # Per-signal payload carries count + fix_command
        edits = next(s for s in payload["signals"] if s["kind"] == "lens_edits_pending")
        assert edits["count"] == 7
        assert edits["fix_command"] == "trinity-local lens"

    def test_signals_empty_list_when_steady_green_in_json(
        self, tmp_path, monkeypatch, capsys,
    ):
        """The empty case is `signals: []`, not absent. Scripts must be
        able to `len(...)` without `if "signals" in payload` branch."""
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        from trinity_local.me import lens_edits as le_mod
        from trinity_local.me import conflicts as conflicts_mod
        from trinity_local.commands import extension_repair as repair_mod

        monkeypatch.setattr(le_mod, "pending_lens_edits_count", lambda: 0)
        monkeypatch.setattr(conflicts_mod, "count_active_conflicts", lambda: 0)
        monkeypatch.setattr(repair_mod, "detect_failure_patterns", lambda d: [])
        monkeypatch.setattr(repair_mod, "diagnose", lambda: {"providers": {}})

        args = Args(as_json=True)
        handle_status(args)
        payload = json.loads(capsys.readouterr().out)
        assert payload["signals"] == []

    def test_captures_in_json_when_extension_active(
        self, tmp_path, monkeypatch, capsys,
    ):
        """Browser-extension captures surface via JSON `captures` key
        when at least one provider directory exists. Absent (not empty)
        when no extension data has ever been captured — same shape as
        human surface's silent-when-cold."""
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        from trinity_local.commands import extension_repair as repair_mod

        monkeypatch.setattr(
            repair_mod, "diagnose",
            lambda: {"providers": {
                "claude":  {"exists": True, "captures": 12, "hours_since_last": 0.5},
                "chatgpt": {"exists": True, "captures": 5, "hours_since_last": 3.0},
                "gemini":  {"exists": True, "captures": 100, "hours_since_last": 0.1},
            }},
        )

        args = Args(as_json=True)
        handle_status(args)
        payload = json.loads(capsys.readouterr().out)
        assert "captures" in payload
        assert payload["captures"]["total"] == 117
        assert "claude" in payload["captures"]["by_provider"]
        assert payload["captures"]["by_provider"]["claude"]["captures"] == 12

    def test_captures_absent_in_json_when_no_extension_data(
        self, tmp_path, monkeypatch, capsys,
    ):
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        from trinity_local.commands import extension_repair as repair_mod

        monkeypatch.setattr(
            repair_mod, "diagnose",
            lambda: {"providers": {
                "claude":  {"exists": False, "captures": 0, "hours_since_last": None},
                "chatgpt": {"exists": False, "captures": 0, "hours_since_last": None},
                "gemini":  {"exists": False, "captures": 0, "hours_since_last": None},
            }},
        )

        args = Args(as_json=True)
        handle_status(args)
        payload = json.loads(capsys.readouterr().out)
        # Captures key intentionally absent (not empty dict) to keep
        # cold-install JSON terse — same as human side staying silent.
        assert "captures" not in payload

    def test_signal_block_failure_does_not_break_status(self, tmp_path, monkeypatch, capsys):
        """Each signal helper is wrapped in try/except — a bug in one
        must not break the whole status command. Steady-state diagnostic
        must always render."""
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        from trinity_local.me import lens_edits as le_mod

        def explode():
            raise RuntimeError("simulated lens_edits bug")
        monkeypatch.setattr(le_mod, "pending_lens_edits_count", explode)

        args = Args(as_json=False)
        handle_status(args)  # must not raise
        out = capsys.readouterr().out
        # Status still renders end-to-end
        assert "Trinity Local — Status" in out
        assert "State:" in out
