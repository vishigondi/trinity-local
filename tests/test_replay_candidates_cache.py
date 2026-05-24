"""Disk-cache for _load_replay_candidates (portal-html hot path).

The launchpad render previously called search_prompt_nodes("") every
time — walking up to 5000 nodes (~3.5s cold on the real 1GB / 38K-
prompt install). Portal-html is its own process per render, so the
in-process cache in iter_prompt_nodes never carried across renders.

Disk cache keyed by prompt_nodes.jsonl (mtime, size, limit). Renders
after the first hot one are sub-millisecond; ingest invalidates by
mutating the file's mtime/size.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import pytest


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
    return tmp_path


def _seed_prompt_nodes(home: Path, count: int = 3) -> Path:
    """Drop a prompt_nodes.jsonl with `count` minimal valid nodes."""
    from trinity_local.state_paths import prompts_dir
    p = prompts_dir() / "prompt_nodes.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("w", encoding="utf-8") as fh:
        for i in range(count):
            fh.write(json.dumps({
                "id": f"n{i}",
                "transcript_id": f"t{i}",
                "provider": "claude",
                "source_path": f"/fake/{i}",
                "turn_index": 0,
                "text": f"prompt text number {i} long enough",
                "embedding": [0.1] * 8,
                "created_at": "2026-05-24T00:00:00Z",
                "timestamp": "2026-05-24T00:00:00Z",
            }) + "\n")
    return p


class TestReplayCandidatesCache:
    def test_first_call_populates_cache(self, home):
        from trinity_local.launchpad_data import (
            _load_replay_candidates,
            _replay_candidates_cache_path,
        )
        _seed_prompt_nodes(home, count=3)
        cache_file = _replay_candidates_cache_path()
        assert not cache_file.exists()

        result = _load_replay_candidates(limit=10)
        assert isinstance(result, list)
        assert cache_file.exists()
        blob = json.loads(cache_file.read_text(encoding="utf-8"))
        assert "signature" in blob
        assert "candidates" in blob
        assert isinstance(blob["candidates"], list)

    def test_second_call_hits_cache_when_input_unchanged(self, home, monkeypatch):
        """If the cache signature matches, _load_replay_candidates must
        return the cached list WITHOUT re-running search_prompt_nodes."""
        from trinity_local.launchpad_data import _load_replay_candidates
        _seed_prompt_nodes(home, count=3)
        first = _load_replay_candidates(limit=10)

        # Sentinel: monkeypatch the search to raise — proves we don't
        # fall through to it on the cached path.
        from trinity_local import memory
        def boom(*args, **kwargs):
            raise AssertionError("search_prompt_nodes should NOT be called on warm cache")
        monkeypatch.setattr(memory, "search_prompt_nodes", boom)

        second = _load_replay_candidates(limit=10)
        assert second == first

    def test_cache_invalidates_on_file_mutation(self, home, monkeypatch):
        """Add a new prompt → mtime/size change → cache should miss."""
        from trinity_local.launchpad_data import _load_replay_candidates
        path = _seed_prompt_nodes(home, count=3)
        _load_replay_candidates(limit=10)

        # Append a new node so size + mtime both change.
        time.sleep(0.01)  # ensure mtime ticks on coarse-grained FS
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({
                "id": "n_new",
                "transcript_id": "t_new",
                "provider": "claude",
                "source_path": "/fake/new",
                "turn_index": 0,
                "text": "a brand new prompt to bust the cache",
                "embedding": [0.1] * 8,
                "created_at": "2026-05-24T01:00:00Z",
                "timestamp": "2026-05-24T01:00:00Z",
            }) + "\n")
        # Force mtime to be definitely newer (some filesystems have 1s
        # resolution).
        os.utime(path, None)

        # Sentinel proves the cache miss triggered a re-search.
        seen = []
        from trinity_local import memory as _m
        original = _m.search_prompt_nodes
        def watching(*args, **kwargs):
            seen.append(args)
            return original(*args, **kwargs)
        monkeypatch.setattr(_m, "search_prompt_nodes", watching)

        _load_replay_candidates(limit=10)
        assert len(seen) >= 1, "cache should miss when prompt_nodes.jsonl mutates"

    def test_missing_file_skips_cache_path(self, home, monkeypatch):
        """When prompt_nodes.jsonl doesn't exist, cache logic should
        no-op (no signature, no read, no write) — the call should still
        return whatever the fallback path produces."""
        from trinity_local.launchpad_data import (
            _load_replay_candidates,
            _replay_candidates_cache_path,
        )
        # Don't seed any prompt_nodes.jsonl. Expect the fallback list.
        result = _load_replay_candidates(limit=10)
        # Whatever the fallback returns, the call must not create a
        # cache entry for an empty-state run.
        cache = _replay_candidates_cache_path()
        assert not cache.exists()
        assert isinstance(result, list)
