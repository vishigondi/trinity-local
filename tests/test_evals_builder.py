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
    # #209: the unified ledger (preference_acts.jsonl) is the sole store.
    # Seed it via the canonical from_rejection adapter (trigger=model_miss)
    # so eval-build's iter_preference_acts(model_miss) sees these.
    from trinity_local.me.preference_acts import (
        from_rejection,
        preference_acts_path,
        save_preference_acts,
    )
    from trinity_local.me.turn_pairs import RejectionSignal

    acts = []
    for e in entries:
        sig = RejectionSignal(
            id=e.get("id", ""),
            type=e.get("type", "REFRAME"),
            model_quote=e.get("model_quote", ""),
            user_substitute=e.get("user_substitute", ""),
            why_signal=e.get("why_signal", ""),
            prompt_id=e.get("prompt_id"),
            basin=e.get("basin"),
            next_user_turn=e.get("next_user_turn", ""),
        )
        acts.append(from_rejection(sig))
    save_preference_acts(acts, allow_shrink=True)
    return preference_acts_path()


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
        with pytest.raises(FileNotFoundError, match="No preference-act ledger"):
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
        # #209: the builder reads the unified ledger; malformed-line skipping
        # is the ledger loader's job (load_preference_acts). Write malformed
        # ledger lines + one valid model_miss act → only the valid one survives.
        from trinity_local.me.preference_acts import preference_acts_path
        p = preference_acts_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("\n".join([
            "not json",
            json.dumps({"id": "r1", "trigger": "model_miss", "privileged": "u",
                        "sacrificed": "m", "kind": "REFRAME"}),
            "",
            json.dumps({"id": "r2", "trigger": "model_miss"}),  # missing privileged/sacrificed — skip
            json.dumps({"id": "", "trigger": "model_miss", "privileged": "u",
                        "sacrificed": "m"}),  # blank id — skip
        ]) + "\n", encoding="utf-8")
        from trinity_local.evals.builder import build_eval_set
        eval_set = build_eval_set()
        # Only r1 survives the structural-field check.
        assert len(eval_set.items) == 1
        assert eval_set.items[0].source_id == "r1"

    def test_limit_caps_items(self, home):
        # Distinct content per row — the unified reader content-dedups, so
        # identical (type, quote, substitute) rows would (correctly) collapse.
        _write_rejections(home, [
            {"id": f"r{i}", "type": "REFRAME", "model_quote": f"m{i}", "user_substitute": f"u{i}", "prompt_id": None}
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
        # r2 must be DISTINCT content (not just a distinct id) — the unified
        # reader content-dedups, so a duplicate-content row wouldn't grow the set.
        _write_rejections(home, [
            {"id": "r1", "type": "REFRAME", "model_quote": "m", "user_substitute": "u", "prompt_id": None},
            {"id": "r2", "type": "REFRAME", "model_quote": "m2", "user_substitute": "u2", "prompt_id": None},
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


class TestEvalBuildReScoreNudge:
    """After rebuilding an eval set, the CLI should nudge the user to
    re-score against the new set when prior runs exist (otherwise the
    leaderboard silently goes out of sync). Names the providers with
    prior results and emits copy-paste-ready commands per provider."""

    def _write_result(self, eval_id: str, target: str) -> None:
        from trinity_local.evals.builder import results_dir
        rd = results_dir()
        rd.mkdir(parents=True, exist_ok=True)
        path = rd / f"eval_{eval_id}__model_{target}__20260101T000000.json"
        path.write_text(json.dumps({
            "eval_id": eval_id, "target_provider": target,
            "items_completed": 5, "items": [],
            "aggregate_score": 0.5, "by_rejection_type": {},
        }))

    def test_targets_with_results_returns_distinct_providers(self, home):
        from trinity_local.commands.eval import _targets_with_results
        self._write_result("set_a", "claude")
        self._write_result("set_a", "codex")
        self._write_result("set_b", "claude")  # duplicate target
        assert _targets_with_results() == {"claude", "codex"}

    def test_targets_with_results_excludes_named_eval_id(self, home):
        """The nudge is about RE-scoring — exclude prior runs against
        the same set we just rebuilt."""
        from trinity_local.commands.eval import _targets_with_results
        self._write_result("set_a", "claude")
        self._write_result("set_b", "codex")
        # Pretend we just rebuilt set_a. Claude's set_a run shouldn't
        # count toward "needs re-scoring."
        targets = _targets_with_results(exclude_eval_id="set_a")
        assert targets == {"codex"}

    def test_targets_with_results_handles_missing_dir(self, home):
        from trinity_local.commands.eval import _targets_with_results
        # No results dir yet → empty set, not crash
        assert _targets_with_results() == set()

    def test_nudge_renders_per_target_eval_run_commands(self, home, capsys):
        """End-to-end smoke: after a rebuild with prior results, output
        contains one `eval-run --target X --eval-id Y` line per
        prior-scored provider."""
        from trinity_local.commands.eval import handle_eval_build
        from argparse import Namespace

        # Plant the ledger + prior runs against ANOTHER eval set
        _write_rejections(home, [{
            "id": "r_001", "type": "REFRAME",
            "model_quote": "long explanation",
            "user_substitute": "just the answer",
            "why_signal": "wants direct answers",
            "prompt_id": "pn_1", "basin": "b00", "next_user_turn": "",
        }])
        self._write_result("eval_OLD_set", "claude")
        self._write_result("eval_OLD_set", "codex")

        # Build args; argparse defaults via Namespace mimic
        args = Namespace(source="rejections", limit=None, eval_id=None)
        handle_eval_build(args)
        out = capsys.readouterr().out
        assert "already scored against prior eval sets" in out
        # Per-target commands surfaced
        assert "eval-run --target claude --eval-id" in out
        assert "eval-run --target codex --eval-id" in out


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


class TestPreferenceActAdapterContract:
    """Pin the RejectionSignal -> from_rejection -> PreferenceAct ->
    EvalItem adapter chain that Stage-2 eval-build now sources through.

    Every other test in this file writes rejections.jsonl as raw JSON,
    so a field-swap inside from_rejection (e.g. transposing privileged
    vs sacrificed, or mapping the wrong attribute onto kind) would stay
    green because the assertions never seed through the dataclass with
    all fields distinct. This test seeds via save_rejections([
    RejectionSignal(...)]) -- the real producer path -- with values
    that are pairwise distinct and asserts the resulting eval item's
    rejection_type / user_substitute / prompt_id equal the seeded
    RejectionSignal's type / user_substitute / prompt_id. A swap in the
    adapter (e.g. privileged=model_quote) then fails here.
    """

    def test_from_rejection_field_mapping_survives_to_eval_item(self, home):
        from trinity_local.evals.builder import build_eval_set

        # Pairwise-distinct field values so any transposition is visible.
        _write_rejections(home, [{
            "id": "r_adapter",
            "type": "REFRAME",
            "model_quote": "MODEL_QUOTE_TEXT",
            "user_substitute": "USER_SUBSTITUTE_TEXT",
            "why_signal": "WHY_SIGNAL_TEXT",
            "prompt_id": "PROMPT_ID_TEXT",
            "basin": "b07",
            "next_user_turn": "NEXT_USER_TURN_TEXT",
        }])

        eval_set = build_eval_set()
        assert len(eval_set.items) == 1
        item = eval_set.items[0]
        # type -> kind -> rejection_type
        assert item.rejection_type == "REFRAME"
        # user_substitute -> privileged -> user_substitute (NOT model_quote)
        assert item.user_substitute == "USER_SUBSTITUTE_TEXT"
        assert item.rejected_response == "MODEL_QUOTE_TEXT"
        # prompt_id passes through unchanged
        assert item.prompt_id == "PROMPT_ID_TEXT"
        assert item.source_id == "r_adapter"
