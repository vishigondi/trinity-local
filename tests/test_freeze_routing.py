"""Tests for `freeze_routing_to_disk` — the writer that materializes the
on-demand personal routing table into `~/.trinity/memories/routing.json`.

Phase 5 distill reads routing.json as one of the five plural core memories;
without a writer the file is always empty and the empirical-memory entry
is silently dropped from the distillation prompt. This suite pins that the
writer produces a valid file, skips when empty, and respects the cache.
"""
from __future__ import annotations

import json

import pytest


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
    return tmp_path


def _seed_outcome(home, *, council_id: str, task_type: str, winner: str):
    """Plant a council outcome JSON that the routing-table walker will pick up."""
    outcomes = home / "council_outcomes"
    outcomes.mkdir(parents=True, exist_ok=True)
    (outcomes / f"council_{council_id}.json").write_text(json.dumps({
        "council_run_id": f"council_{council_id}",
        "bundle_id": f"bundle_{council_id}",
        "task_cluster_id": "c",
        "primary_provider": winner,
        "created_at": "2026-05-12T00:00:00",
        "routing_label": {
            "task_type": task_type,
            "winner": winner,
            # aggregate_routing_table expects per-provider dicts with an
            # `overall` key (the scan ignores raw floats).
            "provider_scores": {
                winner: {"overall": 0.9, "accuracy": 0.9, "fit_to_user": 0.9},
                "other": {"overall": 0.4, "accuracy": 0.5, "fit_to_user": 0.3},
            },
        },
        "metadata": {
            "user_verdict": {"user_winner": winner},
        },
    }))


class TestFreezeRouting:
    def test_writes_routing_json_when_outcomes_exist(self, isolated_home):
        from trinity_local.personal_routing import freeze_routing_to_disk, invalidate_cache
        from trinity_local.state_paths import routing_path

        _seed_outcome(isolated_home, council_id="a1", task_type="system_design", winner="codex")
        _seed_outcome(isolated_home, council_id="a2", task_type="system_design", winner="codex")
        invalidate_cache()

        table = freeze_routing_to_disk()
        assert table, "routing table must be non-empty when outcomes exist"
        assert routing_path().exists()
        on_disk = json.loads(routing_path().read_text())
        assert on_disk == table, "file content must match returned table"

    def test_skip_write_when_empty(self, isolated_home):
        """No outcomes on disk → `by_task_type` is empty → no file written.
        (The returned dict still has metadata keys like `computed_at`, but
        without routing signal we'd just be writing a useless file the
        chairman would have to skip.)"""
        from trinity_local.personal_routing import freeze_routing_to_disk, invalidate_cache
        from trinity_local.state_paths import routing_path

        invalidate_cache()
        table = freeze_routing_to_disk()
        assert table.get("by_task_type", {}) == {}
        # Empty file is worse than no file — chairman/distill would emit
        # an empty "ROUTING" header. Skip the write entirely.
        assert not routing_path().exists()

    def test_distill_reads_frozen_routing(self, isolated_home):
        """End-to-end pinning: after freeze, the distill prompt composer
        includes the ROUTING section because the file is now on disk."""
        from trinity_local.personal_routing import freeze_routing_to_disk, invalidate_cache
        from trinity_local.distill import build_distill_prompt
        from trinity_local.state_paths import lens_path

        # Seed both a lens (so distill doesn't short-circuit on no-memories)
        # and outcomes (so routing freezes non-empty).
        lens_path().write_text("# Lens\n→ leverage over ownership.", encoding="utf-8")
        _seed_outcome(isolated_home, council_id="r1", task_type="code_refactor", winner="codex")
        _seed_outcome(isolated_home, council_id="r2", task_type="code_refactor", winner="codex")
        invalidate_cache()
        freeze_routing_to_disk()

        prompt = build_distill_prompt()
        assert "ROUTING" in prompt
        assert "code_refactor" in prompt or "codex" in prompt
