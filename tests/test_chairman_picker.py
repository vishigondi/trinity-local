"""Tests for chairman auto-selection (§ task 32)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from trinity_local.ranker.chairman_picker import (
    chairman_pick_reason,
    predict_strongest_chairman,
)


@pytest.fixture
def home(patch_trinity_home: Path) -> Path:
    return patch_trinity_home


class TestPicker:
    def test_empty_available_returns_empty(self, home: Path):
        assert predict_strongest_chairman("anything", available_providers=[]) == ""

    def test_falls_back_to_global_benchmarks_for_coding(self, home: Path):
        # No personal table; coding task picks the highest-scoring provider
        # in the reference_evals "coding" category.
        # AA Coding Index: codex 59.1, gemini 55.5, claude 52.5.
        pick = predict_strongest_chairman(
            "refactor this function to remove duplication",
            available_providers=["claude", "gemini", "codex"],
        )
        assert pick == "codex"

    def test_falls_back_to_global_benchmarks_for_writing(self, home: Path):
        # writing maps to "intelligence"; Intelligence Index: claude 57.3, codex 53.6, gemini 34.6
        pick = predict_strongest_chairman(
            "write a launch announcement",
            available_providers=["claude", "gemini", "codex"],
        )
        assert pick == "claude"

    def test_falls_back_to_global_for_research_via_intelligence(self, home: Path):
        # research maps to "intelligence"; claude wins (57.3)
        pick = predict_strongest_chairman(
            "research the model router landscape and compare approaches",
            available_providers=["claude", "gemini", "codex"],
        )
        assert pick == "claude"

    def test_excludes_providers_not_in_available_list(self, home: Path):
        # If gemini isn't available, fall back to next-best in coding (codex 53.1 > claude 52.5)
        pick = predict_strongest_chairman(
            "refactor this code",
            available_providers=["claude", "codex"],
        )
        assert pick == "codex"

    def test_default_order_when_global_has_no_match(self, home: Path):
        # Provider not in the global benchmark models — should fall back to first available
        pick = predict_strongest_chairman(
            "anything",
            available_providers=["custom_provider"],
        )
        assert pick == "custom_provider"

    def test_personal_routing_table_overrides_global(self, home: Path, monkeypatch):
        # Personal table says claude wins coding for this user, even though global says gemini
        from trinity_local.ranker import chairman_picker
        monkeypatch.setattr(
            chairman_picker,
            "compute_personal_routing_table",
            lambda: {
                "computed_at": "2026-05-01T00:00:00Z",
                "councils_aggregated": 12,
                "by_task_type": {
                    "coding": {
                        "claude": {"overall": 8.5, "n": 6},
                        "gemini": {"overall": 6.2, "n": 6},
                    },
                },
                "best_per_task_type": {"coding": "claude"},
            },
        )
        pick = predict_strongest_chairman(
            "refactor this function",
            available_providers=["claude", "gemini", "codex"],
        )
        assert pick == "claude"

    def test_personal_routing_skipped_if_winner_unavailable(self, home: Path, monkeypatch):
        # Personal table says claude wins but claude isn't in available — fall to global
        from trinity_local.ranker import chairman_picker
        monkeypatch.setattr(
            chairman_picker,
            "compute_personal_routing_table",
            lambda: {"best_per_task_type": {"coding": "claude"}},
        )
        pick = predict_strongest_chairman(
            "refactor this code",
            available_providers=["gemini", "codex"],
        )
        # AA coding: codex 59.1 > gemini 55.5
        assert pick == "codex"

    def test_corrupt_personal_table_is_ignored(self, home: Path, monkeypatch):
        from trinity_local.ranker import chairman_picker

        def _raise():
            raise ValueError("corrupt")

        monkeypatch.setattr(chairman_picker, "compute_personal_routing_table", _raise)
        pick = predict_strongest_chairman(
            "refactor this code",
            available_providers=["claude", "gemini", "codex"],
        )
        assert pick == "codex"  # falls through to reference_evals coding winner


class TestPickReason:
    def test_reports_personal_source(self, home: Path, monkeypatch):
        from trinity_local.ranker import chairman_picker
        monkeypatch.setattr(
            chairman_picker,
            "compute_personal_routing_table",
            lambda: {"best_per_task_type": {"coding": "claude"}},
        )
        result = chairman_pick_reason(
            "refactor this",
            available_providers=["claude", "gemini"],
        )
        assert result["chairman"] == "claude"
        assert result["source"] == "personal_routing_table"
        assert result["task_kind"] == "coding"

    def test_reports_global_source(self, home: Path):
        # Coding has data in reference_evals.json, so global lookup wins.
        result = chairman_pick_reason(
            "refactor this Python function",
            available_providers=["claude", "gemini", "codex"],
        )
        assert result["chairman"] == "codex"
        assert result["source"] == "global_benchmarks"
        assert result["task_kind"] == "coding"

    def test_reports_default_source_for_unmapped_category(self, home: Path):
        # Writing maps to creative_writing, which has no reference data with
        # external sync dropped. Falls back to default_order.
        result = chairman_pick_reason(
            "write a launch announcement",
            available_providers=["claude", "gemini", "codex"],
        )
        assert result["source"] == "default_order"
        assert result["task_kind"] == "writing"

    def test_reports_default_source_when_no_match(self, home: Path):
        result = chairman_pick_reason(
            "anything",
            available_providers=["custom"],
        )
        assert result["source"] == "default_order"

    def test_reports_none_when_empty_available(self, home: Path):
        result = chairman_pick_reason("anything", available_providers=[])
        assert result["chairman"] == ""
        assert result["source"] == "none"
