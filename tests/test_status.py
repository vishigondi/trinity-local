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
