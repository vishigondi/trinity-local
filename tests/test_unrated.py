"""Tests for the `unrated` CLI — Pillar 4 funnel-widening (tick #93).

Walks council_outcomes/*.json, filters to ones missing
metadata.user_verdict.user_winner, sorts newest first. The user
runs it, sees the backlog with prompt previews + chairman picks,
copy-pastes the rate command for the ones they want to rate.
"""
from __future__ import annotations

import argparse
import io
import json
from contextlib import redirect_stdout
from pathlib import Path

import pytest


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
    (tmp_path / "council_outcomes").mkdir(parents=True, exist_ok=True)
    (tmp_path / "prompt_bundles").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _write_outcome(home: Path, council_id: str, *, with_verdict: bool,
                   created_at: str, prompt: str, chairman_pick: str = "claude") -> None:
    bundle_id = f"bundle_{council_id}"
    metadata: dict = {"task_text": prompt}
    if with_verdict:
        metadata["user_verdict"] = {"user_winner": chairman_pick}
    outcome = {
        "council_run_id": council_id,
        "bundle_id": bundle_id,
        "created_at": created_at,
        "metadata": metadata,
        "routing_label": {"winner": chairman_pick},
    }
    (home / "council_outcomes" / f"{council_id}.json").write_text(
        json.dumps(outcome), encoding="utf-8"
    )
    bundle = {"bundle_id": bundle_id, "task_text": prompt}
    (home / "prompt_bundles" / f"{bundle_id}.json").write_text(
        json.dumps(bundle), encoding="utf-8"
    )


def _run_unrated(**overrides) -> str:
    from trinity_local.commands.unrated import handle_unrated
    defaults = {"limit": 10, "as_json": False}
    defaults.update(overrides)
    ns = argparse.Namespace(**defaults)
    buf = io.StringIO()
    with redirect_stdout(buf):
        handle_unrated(ns)
    return buf.getvalue()


class TestUnratedCommand:
    def test_empty_install_message(self, isolated_home):
        # No outcomes directory contents
        out = _run_unrated()
        assert "No council outcomes" in out

    def test_all_rated_says_moat_full(self, isolated_home):
        _write_outcome(isolated_home, "council_a", with_verdict=True,
                       created_at="2026-05-13T10:00:00+00:00",
                       prompt="rated thing")
        out = _run_unrated()
        assert "moat is full" in out.lower()

    def test_lists_unrated_newest_first(self, isolated_home):
        _write_outcome(isolated_home, "council_old", with_verdict=False,
                       created_at="2026-05-10T00:00:00+00:00",
                       prompt="old question")
        _write_outcome(isolated_home, "council_new", with_verdict=False,
                       created_at="2026-05-13T12:00:00+00:00",
                       prompt="new question")
        out = _run_unrated()
        # Newest must appear before oldest in output (sort discipline)
        new_idx = out.find("council_new")
        old_idx = out.find("council_old")
        assert new_idx > 0 and old_idx > 0
        assert new_idx < old_idx, (
            f"newest should sort first; got new at {new_idx}, old at {old_idx}\n"
            f"output:\n{out}"
        )

    def test_chairman_pick_shown(self, isolated_home):
        _write_outcome(isolated_home, "council_a", with_verdict=False,
                       created_at="2026-05-13T00:00:00+00:00",
                       prompt="a question", chairman_pick="codex")
        out = _run_unrated()
        assert "codex" in out

    def test_rate_hint_includes_correct_command(self, isolated_home):
        """The point of the command is to give the user the next move.
        That next move is `trinity-local council-rate ...` — pinned."""
        _write_outcome(isolated_home, "council_a", with_verdict=False,
                       created_at="2026-05-13T00:00:00+00:00",
                       prompt="any question")
        out = _run_unrated()
        assert "trinity-local council-rate" in out

    def test_json_output_includes_counts(self, isolated_home):
        _write_outcome(isolated_home, "council_a", with_verdict=True,
                       created_at="2026-05-13T00:00:00+00:00", prompt="rated")
        _write_outcome(isolated_home, "council_b", with_verdict=False,
                       created_at="2026-05-13T00:00:00+00:00", prompt="unrated")
        out = _run_unrated(as_json=True)
        data = json.loads(out)
        assert data["total"] == 2
        assert data["rated"] == 1
        assert data["unrated_count"] == 1
        assert len(data["rows"]) == 1
        assert data["rows"][0]["council_id"] == "council_b"

    def test_long_prompt_gets_truncated(self, isolated_home):
        long_prompt = "very long question " * 30  # ~570 chars
        _write_outcome(isolated_home, "council_a", with_verdict=False,
                       created_at="2026-05-13T00:00:00+00:00", prompt=long_prompt)
        out = _run_unrated()
        # Truncation marker present
        assert "…" in out
        # Long prompt not present in full
        assert long_prompt not in out
