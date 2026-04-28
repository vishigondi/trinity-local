"""Tests for the status command."""
from __future__ import annotations

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from trinity_local.commands.status import handle_status
from trinity_local.cost_tracker import CostSummary, SessionCost


class Args:
    """Mock args object."""

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
                            "trinity_local.commands.status.load_cost_log"
                        ) as mock_costs:
                            mock_costs.return_value = []
                            with patch(
                                "trinity_local.commands.status.summarize_costs"
                            ) as mock_summary:
                                mock_summary.return_value = {}
                                with patch(
                                    "trinity_local.commands.status.check_drift"
                                ) as mock_drift:
                                    mock_drift.return_value = []

                                    args = Args(as_json=True)
                                    handle_status(args)

                                    captured = capsys.readouterr()
                                    # Should produce valid JSON
                                    output = json.loads(captured.out)
                                    assert "trinity_home" in output
                                    assert "cost_by_provider" in output

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
                            "trinity_local.commands.status.load_cost_log"
                        ) as mock_costs:
                            mock_costs.return_value = []
                            with patch(
                                "trinity_local.commands.status.summarize_costs"
                            ) as mock_summary:
                                mock_summary.return_value = {}
                                with patch(
                                    "trinity_local.commands.status.check_drift"
                                ) as mock_drift:
                                    mock_drift.return_value = []

                                    args = Args(as_json=False)
                                    handle_status(args)

                                    captured = capsys.readouterr()
                                    assert "Trinity Local — Status" in captured.out
                                    assert "Adapters:" in captured.out

    def test_status_with_cost_summary(self, tmp_path, capsys):
        """Test status correctly handles CostSummary objects."""
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
                            "trinity_local.commands.status.load_cost_log"
                        ) as mock_costs:
                            cost = SessionCost(
                                session_id="test",
                                provider="claude",
                                model_id="claude-sonnet",
                                input_tokens=100,
                                output_tokens=50,
                                cached_tokens=0,
                                input_cost_usd=0.0005,
                                output_cost_usd=0.0005,
                                total_cost_usd=0.001,
                                task_kind="testing",
                            )
                            mock_costs.return_value = [cost]
                            with patch(
                                "trinity_local.commands.status.summarize_costs"
                            ) as mock_summary:
                                # Simulate what summarize_costs returns
                                summary = CostSummary(provider="claude")
                                summary.total_cost_usd = 0.001
                                summary.sessions = 1
                                mock_summary.return_value = {"claude": summary}
                                with patch(
                                    "trinity_local.commands.status.check_drift"
                                ) as mock_drift:
                                    mock_drift.return_value = []

                                    # Test JSON output
                                    args = Args(as_json=True)
                                    handle_status(args)
                                    captured = capsys.readouterr()
                                    output = json.loads(captured.out)
                                    assert (
                                        output["cost_by_provider"]["claude"] == 0.001
                                    )

                                    # Test human output
                                    args = Args(as_json=False)
                                    handle_status(args)
                                    captured = capsys.readouterr()
                                    assert "claude: $0.0010" in captured.out
