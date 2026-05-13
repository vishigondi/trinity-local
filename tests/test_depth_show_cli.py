"""Tick #53 — `trinity-local depth-show` CLI surfaces the geometric
depth signal so the user can inspect which threads the composite
score flags before any chairman call sees them.

Same shape + same test style as test_merges_log.py's CLI tests.
"""
from __future__ import annotations

import json

import pytest


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
    return tmp_path


def _seed_prompt_nodes(home, items):
    """Write a small prompt_nodes.jsonl the depth helpers can read."""
    from trinity_local.memory.schemas import PromptNode
    from trinity_local.state_paths import memory_dir
    path = memory_dir() / "prompt_nodes.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for it in items:
            node = PromptNode(
                id=it["nid"],
                transcript_id=it["tid"],
                provider="test",
                source_path="test.jsonl",
                turn_index=it.get("turn_index", 0),
                text=it.get("text", ""),
                embedding=it["embedding"],
                created_at="2026-05-13T00:00:00",
            )
            f.write(json.dumps(node.to_dict()) + "\n")


class TestDepthShowCLI:
    def test_cold_install_renders_empty(self, isolated_home, capsys):
        from trinity_local.commands.depth import handle_depth_show

        class Args:
            top = 10
            as_json = False
        handle_depth_show(Args())
        out = capsys.readouterr().out
        assert "No prompt nodes indexed yet" in out, (
            "cold install should print the empty-state hint, not crash"
        )

    def test_json_output_shape(self, isolated_home, capsys):
        # Three threads: two close together, one outlier. Outlier
        # should top the rank.
        _seed_prompt_nodes(isolated_home, [
            {"tid": "t_near_a", "nid": "a", "embedding": [1.0, 0.0, 0.0], "text": "near A"},
            {"tid": "t_near_a", "nid": "a2", "embedding": [0.95, 0.05, 0.0], "text": "near A again", "turn_index": 1},
            {"tid": "t_near_b", "nid": "b", "embedding": [0.9, 0.1, 0.0], "text": "near B"},
            {"tid": "t_near_b", "nid": "b2", "embedding": [0.85, 0.15, 0.0], "text": "near B again", "turn_index": 1},
            {"tid": "t_outlier", "nid": "c", "embedding": [0.0, 0.0, 1.0], "text": "way over here"},
            {"tid": "t_outlier", "nid": "c2", "embedding": [0.0, 0.1, 0.9], "text": "still over here", "turn_index": 1},
        ])
        from trinity_local.commands.depth import handle_depth_show

        class Args:
            top = 10
            as_json = True
        handle_depth_show(Args())
        out = capsys.readouterr().out
        payload = json.loads(out)
        # Schema contract — downstream consumers parse this JSON.
        assert "total_threads" in payload
        assert "rows" in payload
        assert payload["total_threads"] >= 3
        row = payload["rows"][0]
        for key in ("transcript_id", "depth_score", "corpus_distance", "inter_turn_distance", "lid", "turn_count", "first_turn"):
            assert key in row, f"row missing key {key!r}"

    def test_top_argument_truncates(self, isolated_home, capsys):
        _seed_prompt_nodes(isolated_home, [
            {"tid": f"t{i}", "nid": f"n{i}", "embedding": [float(i), 0.0, 0.0]}
            for i in range(5)
        ])
        from trinity_local.commands.depth import handle_depth_show

        class Args:
            top = 2
            as_json = True
        handle_depth_show(Args())
        payload = json.loads(capsys.readouterr().out)
        assert len(payload["rows"]) == 2, f"expected 2 rows, got {len(payload['rows'])}"

    def test_first_turn_used_as_preview(self, isolated_home, capsys):
        """The preview text in the table = the thread's turn_index=0
        prompt. Pin this so a future refactor (e.g., "use longest turn"
        or "use LLM-summarized") trips the test."""
        _seed_prompt_nodes(isolated_home, [
            {"tid": "t1", "nid": "a", "embedding": [1.0, 0.0], "text": "the initiating prompt", "turn_index": 0},
            {"tid": "t1", "nid": "b", "embedding": [0.0, 1.0], "text": "a later follow-up turn", "turn_index": 1},
            {"tid": "t2", "nid": "c", "embedding": [-1.0, 0.0], "text": "another initiating prompt", "turn_index": 0},
        ])
        from trinity_local.commands.depth import handle_depth_show

        class Args:
            top = 10
            as_json = True
        handle_depth_show(Args())
        payload = json.loads(capsys.readouterr().out)
        t1_row = next(r for r in payload["rows"] if r["transcript_id"] == "t1")
        assert "initiating prompt" in t1_row["first_turn"]
        assert "follow-up" not in t1_row["first_turn"], (
            "preview should be turn_index=0, not a later follow-up"
        )

    def test_outlier_thread_tops_the_ranking(self, isolated_home, capsys):
        """The whole point of the depth signal: a thread far from the
        corpus centroid scores higher than threads near it. This is
        the user-facing validation — if it fails the composite isn't
        what we claim."""
        _seed_prompt_nodes(isolated_home, [
            # Three threads near [1, 0, 0]
            {"tid": "t_near_1", "nid": "a", "embedding": [1.0, 0.0, 0.0]},
            {"tid": "t_near_1", "nid": "a2", "embedding": [0.9, 0.1, 0.0], "turn_index": 1},
            {"tid": "t_near_2", "nid": "b", "embedding": [0.95, 0.05, 0.0]},
            {"tid": "t_near_2", "nid": "b2", "embedding": [0.85, 0.15, 0.0], "turn_index": 1},
            {"tid": "t_near_3", "nid": "c", "embedding": [0.9, 0.0, 0.1]},
            {"tid": "t_near_3", "nid": "c2", "embedding": [0.8, 0.1, 0.1], "turn_index": 1},
            # One outlier with movement across orthogonal axes
            {"tid": "t_outlier", "nid": "d", "embedding": [0.0, 1.0, 0.0]},
            {"tid": "t_outlier", "nid": "d2", "embedding": [0.0, 0.0, 1.0], "turn_index": 1},
        ])
        from trinity_local.commands.depth import handle_depth_show

        class Args:
            top = 10
            as_json = True
        handle_depth_show(Args())
        payload = json.loads(capsys.readouterr().out)
        top_id = payload["rows"][0]["transcript_id"]
        assert top_id == "t_outlier", (
            f"outlier should rank #1; got {top_id} (full ranking: "
            f"{[r['transcript_id'] for r in payload['rows']]})"
        )
