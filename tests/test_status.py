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

    def test_status_json_output(self, tmp_path, capsys):
        """Test status --json produces valid JSON."""
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
                        "trinity_local.commands.status.list_actions"
                    ) as mock_actions:
                        mock_actions.return_value = []
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

    def test_status_human_output(self, tmp_path, capsys):
        """Test status with human-readable output."""
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
                        "trinity_local.commands.status.list_actions"
                    ) as mock_actions:
                        mock_actions.return_value = []
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
        assert "trinity-local lens-build" in out

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
