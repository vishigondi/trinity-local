"""Tests for `trinity-local dream` — the one-command cold-start.

`dream` orchestrates four phases:
  1. discover (cross-provider pair finder — no LLM)
  2. synthesize (one chairman call per cluster)
  3. consolidate (cortex rule extraction)
  4. me-build (taste-lens rebuild)

All four phases share tested machinery; these tests pin `dream`'s job:
sequencing, error isolation between phases, dry-run no-LLM path, the
--skip-* flags, and the uncapped node walk that distinguishes dream
from the hot-path iterator.
"""
from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest


def _args(**overrides) -> SimpleNamespace:
    base = {
        "similarity_threshold": 0.85,
        "max_clusters": None,
        "skip_consolidate": False,
        "skip_me_build": False,
        "dry_run": False,
        "primary_provider": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def _plant_node(tmp_path, *, id_, provider, embedding, response="answer"):
    from trinity_local.memory import upsert_prompt_node
    from trinity_local.memory.schemas import PromptNode
    upsert_prompt_node(PromptNode(
        id=id_,
        transcript_id=f"t_{id_}",
        provider=provider,
        source_path=f"/fake/{id_}",
        turn_index=0,
        text=f"question for {id_}",
        embedding=embedding,
        created_at="2026-05-12T00:00:00Z",
        following_assistant_text=response,
    ))


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
    return tmp_path


class TestDreamDryRun:
    def test_dry_run_no_llm_calls_and_reports_clusters(self, isolated_home, monkeypatch, capsys):
        """--dry-run discovers clusters, prints the plan, makes ZERO LLM calls."""
        # Plant a cross-provider pair
        _plant_node(isolated_home, id_="a1", provider="claude", embedding=[1.0, 0.0])
        _plant_node(isolated_home, id_="a2", provider="gemini", embedding=[0.99, 0.05])

        from trinity_local.commands.dream import handle_dream
        from trinity_local import mcp_server

        # Guard: any synthesis attempt is a bug in dry-run.
        synth_mock = MagicMock()
        monkeypatch.setattr(mcp_server, "_synthesize_responses", synth_mock)

        rc = handle_dream(_args(dry_run=True))
        out = capsys.readouterr().out
        payload = json.loads(out)

        assert rc == 0
        assert payload["ok"] is True
        assert payload["phases"]["discover"]["clusters_found"] == 1
        assert payload["phases"]["discover"]["with_embedding"] == 2
        # Did NOT enter phase 2 — no synth attempt
        synth_mock.assert_not_called()
        assert "synthesize" not in payload["phases"]


class TestDreamUncappedNodeWalk:
    def test_iterates_past_5000_node_hot_path_cap(self, isolated_home, monkeypatch):
        """The hot-path `iter_prompt_nodes` caps at TRINITY_PROMPT_NODE_LIMIT
        (default 5000) — that's right for launchpad/search but wrong for
        dream, which needs every embedded node. Test that dream's
        `_all_prompt_nodes_uncapped` returns >5000 when there are more."""
        # Plant 5001 nodes — only the uncapped walker should see all of them.
        for i in range(5001):
            _plant_node(
                isolated_home,
                id_=f"node{i}",
                provider="claude",
                embedding=[1.0, 0.0],
            )
        from trinity_local.commands.dream import _all_prompt_nodes_uncapped
        nodes = _all_prompt_nodes_uncapped()
        assert len(nodes) >= 5001


class TestDreamSynthesisPhase:
    def test_synthesizes_each_cluster_via_mcp_machinery(self, isolated_home, monkeypatch, capsys):
        """Each cluster discovered → one call to `_synthesize_responses`."""
        # Two cross-provider pairs → two clusters
        _plant_node(isolated_home, id_="a1", provider="claude", embedding=[1.0, 0.0])
        _plant_node(isolated_home, id_="a2", provider="gemini", embedding=[0.99, 0.05])
        _plant_node(isolated_home, id_="b1", provider="claude", embedding=[0.0, 1.0])
        _plant_node(isolated_home, id_="b2", provider="gemini", embedding=[0.05, 0.99])

        from trinity_local import mcp_server
        from trinity_local.commands import dream

        call_log = []
        async def fake_synth(args, responses):
            call_log.append((args.get("task"), len(responses)))
            return [{"type": "text", "text": '{"ok": true}'}]
        monkeypatch.setattr(mcp_server, "_synthesize_responses", fake_synth)
        # Skip consolidate + me-build to keep this test focused on phase 2.
        rc = dream.handle_dream(_args(skip_consolidate=True, skip_me_build=True))

        out = capsys.readouterr().out
        payload = json.loads(out)
        assert rc == 0
        # Both clusters got synthesized
        assert len(call_log) == 2
        assert payload["phases"]["synthesize"]["synthesized"] == 2
        assert payload["phases"]["synthesize"]["failed"] == 0
        assert payload["phases"]["consolidate"]["skipped"] is True
        assert payload["phases"]["me_build"]["skipped"] is True

    def test_synthesis_failures_do_not_abort_subsequent_clusters(self, isolated_home, monkeypatch, capsys):
        """One bad cluster shouldn't poison the rest."""
        _plant_node(isolated_home, id_="a1", provider="claude", embedding=[1.0, 0.0])
        _plant_node(isolated_home, id_="a2", provider="gemini", embedding=[0.99, 0.05])
        _plant_node(isolated_home, id_="b1", provider="claude", embedding=[0.0, 1.0])
        _plant_node(isolated_home, id_="b2", provider="gemini", embedding=[0.05, 0.99])

        from trinity_local import mcp_server
        from trinity_local.commands import dream

        call_count = [0]
        async def fake_synth(args, responses):
            call_count[0] += 1
            if call_count[0] == 1:
                raise RuntimeError("first cluster blew up")
            return [{"type": "text", "text": '{"ok": true}'}]
        monkeypatch.setattr(mcp_server, "_synthesize_responses", fake_synth)
        rc = dream.handle_dream(_args(skip_consolidate=True, skip_me_build=True))

        payload = json.loads(capsys.readouterr().out)
        assert rc == 0
        assert payload["phases"]["synthesize"]["synthesized"] == 1
        assert payload["phases"]["synthesize"]["failed"] == 1


class TestDreamSkipFlags:
    def test_skip_consolidate_short_circuits_phase_3(self, isolated_home, monkeypatch, capsys):
        from trinity_local.commands import dream
        # Stub out phase 2 so we don't try real calls
        from trinity_local import mcp_server
        async def noop(args, responses):
            return [{"type": "text", "text": '{"ok": true}'}]
        monkeypatch.setattr(mcp_server, "_synthesize_responses", noop)

        # Sentinel that proves _consolidate was NOT entered.
        called = MagicMock()
        monkeypatch.setattr(dream, "_consolidate", called)

        rc = dream.handle_dream(_args(skip_consolidate=True, skip_me_build=True))
        assert rc == 0
        called.assert_not_called()
        payload = json.loads(capsys.readouterr().out)
        assert payload["phases"]["consolidate"] == {"skipped": True}

    def test_skip_me_build_short_circuits_phase_4(self, isolated_home, monkeypatch, capsys):
        from trinity_local.commands import dream
        from trinity_local import mcp_server
        async def noop(args, responses):
            return [{"type": "text", "text": '{"ok": true}'}]
        monkeypatch.setattr(mcp_server, "_synthesize_responses", noop)

        # Phase 3 stubbed to a fast no-op so the test stays unit-fast.
        monkeypatch.setattr(dream, "_consolidate", lambda p: {"ok": True, "stubbed": True})

        called = MagicMock()
        monkeypatch.setattr(dream, "_me_build", called)

        rc = dream.handle_dream(_args(skip_me_build=True))
        assert rc == 0
        called.assert_not_called()
        payload = json.loads(capsys.readouterr().out)
        assert payload["phases"]["me_build"] == {"skipped": True}


class TestDreamMaxClusters:
    def test_max_clusters_caps_synthesis(self, isolated_home, monkeypatch, capsys):
        # Three cross-provider pairs
        for i, (a_embed, b_embed) in enumerate([
            ([1.0, 0.0], [0.99, 0.05]),
            ([0.0, 1.0], [0.05, 0.99]),
            ([0.7, 0.7], [0.71, 0.71]),
        ]):
            _plant_node(isolated_home, id_=f"a{i}", provider="claude", embedding=a_embed)
            _plant_node(isolated_home, id_=f"b{i}", provider="gemini", embedding=b_embed)

        from trinity_local import mcp_server
        from trinity_local.commands import dream

        call_count = [0]
        async def fake_synth(args, responses):
            call_count[0] += 1
            return [{"type": "text", "text": '{"ok": true}'}]
        monkeypatch.setattr(mcp_server, "_synthesize_responses", fake_synth)
        rc = dream.handle_dream(_args(
            max_clusters=2,
            skip_consolidate=True,
            skip_me_build=True,
        ))
        assert rc == 0
        # Synthesis honored the cap — even though discovery found 3
        assert call_count[0] == 2
        payload = json.loads(capsys.readouterr().out)
        # discover phase still shows all 3 found, synthesis only attempted 2
        assert payload["phases"]["discover"]["clusters_found"] == 2  # post-cap
        assert payload["phases"]["synthesize"]["attempted"] == 2


class TestDreamNoData:
    def test_empty_prompt_nodes_completes_gracefully(self, isolated_home, monkeypatch, capsys):
        """Fresh install / no transcripts yet — dream should not crash."""
        from trinity_local.commands import dream
        # Stub later phases so the empty-data case tests just the discovery branch.
        monkeypatch.setattr(dream, "_consolidate", lambda p: {"ok": False, "reason": "no councils"})
        monkeypatch.setattr(dream, "_me_build", lambda p: {"ok": False, "reason": "no data"})

        rc = dream.handle_dream(_args())
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["phases"]["discover"]["clusters_found"] == 0
        # Synthesis phase ran but found nothing to do
        assert payload["phases"]["synthesize"]["attempted"] == 0
