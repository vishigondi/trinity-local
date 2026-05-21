"""Tests for the corpus-based eval-set builder (task #122).

Pins the load-bearing schema + extraction behavior. The eval set is
the durable artifact that the runner+scorer consume in follow-up
ticks; if its shape drifts here, every downstream surface breaks.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def home(patch_trinity_home: Path) -> Path:
    return patch_trinity_home


def _write_rejections(home: Path, entries: list[dict]) -> Path:
    rej_path = home / "me" / "rejections.jsonl"
    rej_path.parent.mkdir(parents=True, exist_ok=True)
    with rej_path.open("w", encoding="utf-8") as fh:
        for e in entries:
            fh.write(json.dumps(e) + "\n")
    return rej_path


def _write_prompt_node(home: Path, prompt_id: str, text: str, *, provider: str = "claude") -> None:
    """Drop a minimal PromptNode into the prompts index so the builder
    can look up prompt text by prompt_id."""
    from trinity_local.memory.schemas import PromptNode
    from trinity_local.memory.store import upsert_prompt_node

    upsert_prompt_node(PromptNode(
        id=prompt_id,
        transcript_id=f"t_{prompt_id}",
        provider=provider,
        source_path=f"/fake/{provider}.json",
        turn_index=0,
        text=text,
        embedding=None,
        created_at="2026-05-01T10:00:00",
        timestamp="2026-05-01T10:00:00",
        preceding_assistant_text="",
        following_assistant_text="",
        themes=[],
    ))


class TestBuildEvalSet:
    def test_raises_when_no_rejections_file(self, home):
        from trinity_local.evals.builder import build_eval_set
        with pytest.raises(FileNotFoundError, match="No rejections file"):
            build_eval_set()

    def test_unsupported_source_raises_not_implemented(self, home):
        _write_rejections(home, [])
        from trinity_local.evals.builder import build_eval_set
        with pytest.raises(NotImplementedError, match="cross_provider_pair"):
            build_eval_set(source="cross_provider_pair")

    def test_empty_rejections_yields_empty_set_with_stable_id(self, home):
        _write_rejections(home, [])
        from trinity_local.evals.builder import build_eval_set
        eval_set = build_eval_set()
        assert eval_set.items == []
        assert eval_set.stats["items"] == 0
        # Content-addressed: empty set has a deterministic id.
        assert eval_set.eval_id.startswith("eval_")

    def test_real_shape_item_renders(self, home):
        """The schema the runner will consume."""
        _write_prompt_node(home, "pn_42", "Build a spec for the terminal app.", provider="claude")
        _write_rejections(home, [{
            "id": "r_001",
            "type": "REDIRECT",
            "model_quote": "Here's a full GTM strategy...",
            "user_substitute": "Just write the spec.",
            "why_signal": "User ignored the GTM strategy and asked only for a build spec.",
            "prompt_id": "pn_42",
            "basin": "b03",
            "next_user_turn": "",
        }])
        from trinity_local.evals.builder import build_eval_set
        eval_set = build_eval_set()
        assert len(eval_set.items) == 1
        item = eval_set.items[0]
        # Every consumer-facing field present
        assert item.eval_item_id.startswith("ei_")
        assert item.prompt == "Build a spec for the terminal app."
        assert item.rejection_type == "REDIRECT"
        assert item.rejected_response == "Here's a full GTM strategy..."
        assert item.user_substitute == "Just write the spec."
        assert "User ignored" in item.rubric_signal
        assert item.basin_id == "b03"
        assert item.source == "rejections"
        assert item.source_id == "r_001"
        assert item.prompt_id == "pn_42"
        # Provider attribution flows through from the PromptNode
        assert item.provider_of_rejected_response == "claude"

    def test_missing_prompt_id_falls_back_to_user_substitute(self, home):
        """Corpus churn: rejection mentions a prompt_id that no longer
        resolves. Fall back to user_substitute so the rejection-shape
        signal is preserved rather than silently dropped."""
        _write_rejections(home, [{
            "id": "r_orphan",
            "type": "COMPRESSION",
            "model_quote": "A long lecture...",
            "user_substitute": "tldr please",
            "why_signal": "User wanted shorter.",
            "prompt_id": "pn_does_not_exist",
            "basin": "b00",
        }])
        from trinity_local.evals.builder import build_eval_set
        eval_set = build_eval_set()
        assert len(eval_set.items) == 1
        # prompt falls back to user_substitute when prompt_id can't resolve.
        assert eval_set.items[0].prompt == "tldr please"
        assert eval_set.items[0].provider_of_rejected_response is None

    def test_stats_aggregate_by_type_and_basin(self, home):
        _write_rejections(home, [
            {"id": "r1", "type": "REFRAME", "model_quote": "A", "user_substitute": "B", "prompt_id": None, "basin": "b00"},
            {"id": "r2", "type": "REFRAME", "model_quote": "C", "user_substitute": "D", "prompt_id": None, "basin": "b00"},
            {"id": "r3", "type": "COMPRESSION", "model_quote": "E", "user_substitute": "F", "prompt_id": None, "basin": "b01"},
        ])
        from trinity_local.evals.builder import build_eval_set
        eval_set = build_eval_set()
        # by_type counts each rejection_type
        assert eval_set.stats["by_rejection_type"] == {"REFRAME": 2, "COMPRESSION": 1}
        # by_basin counts each basin (entries with basin)
        assert eval_set.stats["by_basin"] == {"b00": 2, "b01": 1}
        # Sorted descending by count so the dominant axes lead.
        types = list(eval_set.stats["by_rejection_type"].items())
        assert types[0][1] >= types[-1][1]

    def test_skips_malformed_rejection_lines(self, home):
        rej_path = home / "me" / "rejections.jsonl"
        rej_path.parent.mkdir(parents=True, exist_ok=True)
        rej_path.write_text("\n".join([
            "not json",
            json.dumps({"id": "r1", "type": "REFRAME", "model_quote": "ok"}),
            "",
            json.dumps({"id": "r2", "type": "REFRAME"}),  # missing model_quote — skip
            json.dumps({"id": "", "type": "REFRAME", "model_quote": "ok"}),  # blank id — skip
        ]) + "\n", encoding="utf-8")
        from trinity_local.evals.builder import build_eval_set
        eval_set = build_eval_set()
        # Only r1 survives the structural-field check.
        assert len(eval_set.items) == 1
        assert eval_set.items[0].source_id == "r1"

    def test_limit_caps_items(self, home):
        _write_rejections(home, [
            {"id": f"r{i}", "type": "REFRAME", "model_quote": "m", "user_substitute": "u", "prompt_id": None}
            for i in range(10)
        ])
        from trinity_local.evals.builder import build_eval_set
        eval_set = build_eval_set(limit=3)
        assert len(eval_set.items) == 3

    def test_content_addressed_eval_id_is_idempotent(self, home):
        """Same corpus state → same eval_id. This is what makes results
        diffable across runs (and across model releases)."""
        entries = [
            {"id": "r1", "type": "REFRAME", "model_quote": "m", "user_substitute": "u", "prompt_id": None},
            {"id": "r2", "type": "COMPRESSION", "model_quote": "m", "user_substitute": "u", "prompt_id": None},
        ]
        _write_rejections(home, entries)
        from trinity_local.evals.builder import build_eval_set
        a = build_eval_set()
        b = build_eval_set()
        assert a.eval_id == b.eval_id

    def test_eval_id_changes_when_corpus_changes(self, home):
        from trinity_local.evals.builder import build_eval_set
        _write_rejections(home, [
            {"id": "r1", "type": "REFRAME", "model_quote": "m", "user_substitute": "u", "prompt_id": None},
        ])
        first = build_eval_set().eval_id
        _write_rejections(home, [
            {"id": "r1", "type": "REFRAME", "model_quote": "m", "user_substitute": "u", "prompt_id": None},
            {"id": "r2", "type": "REFRAME", "model_quote": "m", "user_substitute": "u", "prompt_id": None},
        ])
        second = build_eval_set().eval_id
        assert first != second


class TestSaveLoadRoundtrip:
    def test_roundtrip_preserves_all_fields(self, home):
        from trinity_local.evals.builder import build_eval_set, save_eval_set, load_eval_set
        _write_prompt_node(home, "pn_1", "prompt text", provider="antigravity")
        _write_rejections(home, [{
            "id": "r1", "type": "SHARPENING",
            "model_quote": "vague",
            "user_substitute": "be specific about X, Y, Z",
            "why_signal": "user wanted precision",
            "prompt_id": "pn_1",
            "basin": "b04",
        }])
        eval_set = build_eval_set()
        path = save_eval_set(eval_set)
        assert path.exists()
        # Load it back, byte-for-byte equivalent on the shape that
        # matters for downstream consumers (runner / scorer).
        reloaded = load_eval_set(eval_set.eval_id)
        assert reloaded is not None
        assert reloaded.eval_id == eval_set.eval_id
        assert reloaded.source == eval_set.source
        assert reloaded.stats == eval_set.stats
        assert len(reloaded.items) == 1
        a, b = reloaded.items[0], eval_set.items[0]
        assert a.to_dict() == b.to_dict()

    def test_load_returns_none_for_unknown_eval_id(self, home):
        from trinity_local.evals.builder import load_eval_set
        assert load_eval_set("eval_does_not_exist") is None


class TestEvalCLIRegistered:
    """The CLI is the user-facing surface for the marketing artifact.
    If it's not registered, the eval set never gets built."""

    def test_eval_build_and_eval_stats_in_parser(self):
        import argparse
        from trinity_local import main as main_module
        parser = main_module.build_parser()
        # Find the SubParsersAction specifically — other actions can
        # also have `choices` (e.g. --scope user|project) but their
        # choices are lists, not the subparser-name dict we want.
        sub_actions = [
            a for a in parser._actions
            if isinstance(a, argparse._SubParsersAction)
        ]
        assert sub_actions, "no subparser action found"
        choices = sub_actions[0].choices  # dict[name -> ArgumentParser]
        assert "eval-build" in choices
        assert "eval-stats" in choices
