"""Tests for the embeddings package."""
from __future__ import annotations

import json
import os
from pathlib import Path

from trinity_local.embeddings.backend_tfidf import embed_tfidf, cosine_similarity
from trinity_local.embeddings.cache import (
    _text_key,
    get_cached,
    put_cached,
    clear_cache,
    cache_stats,
    _cache_path,
    _load_index,
)


class TestTextKey:
    def test_deterministic(self):
        assert _text_key("hello", 512) == _text_key("hello", 512)

    def test_different_dims(self):
        assert _text_key("hello", 512) != _text_key("hello", 256)

    def test_different_texts(self):
        assert _text_key("hello", 512) != _text_key("world", 512)


class TestTfidfBackend:
    def test_embed_returns_vector(self):
        vec = embed_tfidf("write a sorting function")
        assert isinstance(vec, list)
        assert len(vec) == 256  # default dim

    def test_embed_custom_dim(self):
        vec = embed_tfidf("write a sorting function", dim=128)
        assert len(vec) == 128

    def test_embed_normalized(self):
        import math
        vec = embed_tfidf("write a sorting function for the list")
        norm = math.sqrt(sum(v * v for v in vec))
        if norm > 0:
            assert abs(norm - 1.0) < 0.01

    def test_similar_texts_higher_sim(self):
        vec_a = embed_tfidf("write a sorting function")
        vec_b = embed_tfidf("write a sorting algorithm")
        vec_c = embed_tfidf("deploy kubernetes cluster")
        sim_ab = cosine_similarity(vec_a, vec_b)
        sim_ac = cosine_similarity(vec_a, vec_c)
        assert sim_ab > sim_ac, f"Similar texts should be closer: {sim_ab} vs {sim_ac}"

    def test_empty_text(self):
        vec = embed_tfidf("")
        assert all(v == 0.0 for v in vec)


class TestCache:
    def test_miss_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        # Reset cache state
        import trinity_local.embeddings.cache as cache_mod
        cache_mod._index = None
        assert get_cached("nonexistent text") is None

    def test_put_and_get(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        import trinity_local.embeddings.cache as cache_mod
        cache_mod._index = None
        vector = [0.1, 0.2, 0.3]
        put_cached("test text", vector, dim=3)
        result = get_cached("test text", dim=3)
        assert result == vector

    def test_clear(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        import trinity_local.embeddings.cache as cache_mod
        cache_mod._index = None
        put_cached("text1", [1.0], dim=1)
        count = clear_cache()
        assert count == 1
        assert get_cached("text1", dim=1) is None

    def test_stats(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        import trinity_local.embeddings.cache as cache_mod
        cache_mod._index = None
        put_cached("text1", [1.0, 2.0], dim=2)
        stats = cache_stats()
        assert stats["entries"] == 1
        assert stats["size_bytes"] > 0

    def test_persistence(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        import trinity_local.embeddings.cache as cache_mod
        cache_mod._index = None
        put_cached("persistent", [0.5], dim=1)
        # Reset in-memory index to force reload from disk
        cache_mod._index = None
        result = get_cached("persistent", dim=1)
        assert result == [0.5]


class TestPublicAPI:
    def test_get_backend_without_mlx(self):
        from trinity_local import embeddings
        # Should be either "mlx" or "tfidf" depending on env
        assert embeddings.get_backend() in ("mlx", "tfidf")

    def test_embed_returns_vector(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        import trinity_local.embeddings.cache as cache_mod
        cache_mod._index = None
        from trinity_local import embeddings
        vec = embeddings.embed("test embedding text")
        assert isinstance(vec, list)
        assert len(vec) > 0

    def test_similarity_symmetric(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        import trinity_local.embeddings.cache as cache_mod
        cache_mod._index = None
        from trinity_local import embeddings
        sim_ab = embeddings.similarity("hello world", "hello there")
        sim_ba = embeddings.similarity("hello there", "hello world")
        assert abs(sim_ab - sim_ba) < 0.001

    def test_model_status(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        import trinity_local.embeddings.cache as cache_mod
        cache_mod._index = None
        from trinity_local import embeddings
        status = embeddings.model_status()
        assert "backend" in status
        assert "cache_entries" in status

    def test_tfidf_fallback_respects_requested_dim(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        import trinity_local.embeddings.cache as cache_mod
        cache_mod._index = None
        from trinity_local import embeddings

        monkeypatch.setattr(embeddings, "_mlx_backend", None)
        vec = embeddings.embed("fallback vector", dim=512)

        assert len(vec) == 512
        assert get_cached("fallback vector", dim=512) == vec
