"""Tests for `trinity-local dream` — the one-command cold-start.

`dream` orchestrates four phases:
  1. discover (cross-provider pair finder — no LLM)
  2. synthesize (one chairman call per cluster)
  3. consolidate (cortex rule extraction)
  4. lens-build (taste-lens rebuild; renamed from `me-build` per Tier 1 #2)

All four phases share tested machinery; these tests pin `dream`'s job:
sequencing, error isolation between phases, dry-run no-LLM path, the
--skip-* flags, and the uncapped node walk that distinguishes dream
from the hot-path iterator.
"""
from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest


@pytest.fixture(autouse=True)
def _bypass_embedder_gate(monkeypatch):
    """Dream's handler gates on the ~600 MB nomic model being present in
    the HF cache (`require_embedder_ready`). These tests stub Phase 1
    discovery + Phase 2 synthesis directly with MagicMock; they never
    touch the real embedder, so the gate is just noise here. CI runs
    without the HF cache and fails-closed otherwise.

    The dedicated gate behavior lives in test_embedder_cli_gate.py;
    this fixture is bypass-only and does not erode that coverage."""
    from trinity_local import embeddings
    monkeypatch.setattr(embeddings, "require_embedder_ready", lambda: None)


def _args(**overrides) -> SimpleNamespace:
    base = {
        "similarity_threshold": 0.85,
        "max_clusters": None,
        "skip_consolidate": False,
        "skip_me_build": False,
        "skip_vocabulary": False,
        "skip_distill": False,
        "only_distill": False,
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
        # ≥6 words to clear the default min_prompt_words filter
        # (filters conversational filler from cross-provider discovery).
        text=f"What is the canonical answer for question identifier {id_}",
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
        _plant_node(isolated_home, id_="a2", provider="antigravity", embedding=[0.99, 0.05])

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
        _plant_node(isolated_home, id_="a2", provider="antigravity", embedding=[0.99, 0.05])
        _plant_node(isolated_home, id_="b1", provider="claude", embedding=[0.0, 1.0])
        _plant_node(isolated_home, id_="b2", provider="antigravity", embedding=[0.05, 0.99])

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
        _plant_node(isolated_home, id_="a2", provider="antigravity", embedding=[0.99, 0.05])
        _plant_node(isolated_home, id_="b1", provider="claude", embedding=[0.0, 1.0])
        _plant_node(isolated_home, id_="b2", provider="antigravity", embedding=[0.05, 0.99])

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
            _plant_node(isolated_home, id_=f"b{i}", provider="antigravity", embedding=b_embed)

        from trinity_local import mcp_server
        from trinity_local.commands import dream
        from trinity_local import embeddings as embeddings_mod

        # Stub the heavy downstream phases so the test only exercises
        # what it actually asserts on (synthesis call count). Was the
        # suite's #1 slowest test at 30s before these patches:
        # - require_embedder_ready: ~22s nomic model cold-load
        # - _vocabulary_scan (Phase 2.5): another real chairman dispatch
        # - _distill (Phase 5): another real chairman dispatch + writes
        # Test only asserts the synthesis_call_count cap — those
        # downstream phases aren't part of the contract being verified.
        monkeypatch.setattr(embeddings_mod, "require_embedder_ready", lambda: None)
        monkeypatch.setattr(dream, "_vocabulary_scan", lambda: {"skipped_in_test": True})
        monkeypatch.setattr(dream, "_distill", lambda provider: {"skipped_in_test": True})

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


class TestDreamOnlyDistill:
    """--only-distill: skip every upstream phase, just refresh core.md.
    Fast path for clearing the 'stale core.md' status warning when the
    upstream memories (lens/topics/vocabulary) are still current."""

    def test_only_distill_skips_discovery_and_all_upstream_phases(self, isolated_home, monkeypatch, capsys):
        from trinity_local.commands import dream

        # If anything other than _distill is called, the test fails.
        # The point of --only-distill is BYPASSING all 5 upstream stubs.
        upstream_called: list[str] = []
        monkeypatch.setattr(dream, "_all_prompt_nodes_uncapped",
                            lambda: upstream_called.append("discover") or [])
        monkeypatch.setattr(dream, "_synthesize_all",
                            lambda *a, **k: upstream_called.append("synthesize") or {})
        monkeypatch.setattr(dream, "_consolidate",
                            lambda p: upstream_called.append("consolidate") or {})
        monkeypatch.setattr(dream, "_me_build",
                            lambda p: upstream_called.append("me_build") or {})
        monkeypatch.setattr(dream, "_vocabulary_scan",
                            lambda: upstream_called.append("vocabulary") or {})

        distill_calls: list[str] = []
        monkeypatch.setattr(dream, "_distill",
                            lambda p: (distill_calls.append(p) or {"ok": True}))

        rc = dream.handle_dream(_args(only_distill=True))
        assert rc == 0
        assert upstream_called == [], (
            f"--only-distill called upstream phases: {upstream_called} "
            "(should bypass ALL of them)"
        )
        assert distill_calls == ["claude"]

    def test_only_distill_honors_primary_provider(self, isolated_home, monkeypatch, capsys):
        from trinity_local.commands import dream
        monkeypatch.setattr(dream, "_all_prompt_nodes_uncapped", lambda: [])

        recorded: list[str] = []
        monkeypatch.setattr(dream, "_distill",
                            lambda p: (recorded.append(p) or {"ok": True}))

        rc = dream.handle_dream(_args(only_distill=True, primary_provider="codex"))
        assert rc == 0
        assert recorded == ["codex"]

    def test_only_distill_plus_skip_distill_errors(self, isolated_home, monkeypatch, capsys):
        """The two flags are mutually exclusive — combined they'd
        produce a no-op. Exit 2 with a clear message instead of
        silently running nothing."""
        from trinity_local.commands import dream
        with pytest.raises(SystemExit) as exc:
            dream.handle_dream(_args(only_distill=True, skip_distill=True))
        assert exc.value.code == 2
        # Message surfaces both flag names so the user knows what to drop
        captured = capsys.readouterr()
        assert "--only-distill" in captured.err
        assert "--skip-distill" in captured.err

    def test_only_distill_payload_includes_mode_flag(self, isolated_home, monkeypatch, capsys):
        """Scripted callers should be able to tell from the JSON that
        an only-distill run happened (vs a full dream that ended
        with just a distill phase)."""
        from trinity_local.commands import dream
        monkeypatch.setattr(dream, "_distill", lambda p: {"ok": True})

        rc = dream.handle_dream(_args(only_distill=True))
        assert rc == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload.get("mode") == "only-distill"
        # No upstream phases recorded in the report
        assert set(payload.get("phases", {}).keys()) == {"distill"}
