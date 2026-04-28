"""Tests for shared utilities."""
from __future__ import annotations

from trinity_local.utils import now_iso, stable_id


class TestNowIso:
    def test_format(self):
        ts = now_iso()
        assert ts.endswith("+00:00")
        # Should not have microseconds
        assert "." not in ts

    def test_different_calls_monotonic(self):
        ts1 = now_iso()
        ts2 = now_iso()
        assert ts2 >= ts1


class TestStableId:
    def test_deterministic(self):
        id1 = stable_id("task", "hello", "world")
        id2 = stable_id("task", "hello", "world")
        assert id1 == id2

    def test_prefix(self):
        result = stable_id("task", "test")
        assert result.startswith("task_")

    def test_length(self):
        result = stable_id("action", "test")
        # prefix + _ + 16 hex chars
        assert len(result) == len("action_") + 16

    def test_different_inputs_different_ids(self):
        id1 = stable_id("task", "alpha")
        id2 = stable_id("task", "beta")
        assert id1 != id2

    def test_different_prefixes_different_ids(self):
        id1 = stable_id("task", "hello")
        id2 = stable_id("action", "hello")
        assert id1 != id2
