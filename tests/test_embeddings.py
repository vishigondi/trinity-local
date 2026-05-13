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


class TestIsFiniteEmbedding:
    """is_finite_embedding is the single source of truth for the NaN/Inf
    filter. Five consumers (me/depth, me/basins, me_builder, cross_provider_pairs,
    vocabulary) all call it before any matmul or k-means. Each shape below
    must return the same answer the consumers were inlining for years."""

    def test_finite_floats_pass(self):
        from trinity_local.embeddings import is_finite_embedding
        assert is_finite_embedding([0.1, -0.2, 3.14, 0.0])

    def test_empty_rejected(self):
        from trinity_local.embeddings import is_finite_embedding
        assert not is_finite_embedding([])
        assert not is_finite_embedding(None)

    def test_nan_rejected(self):
        from trinity_local.embeddings import is_finite_embedding
        assert not is_finite_embedding([1.0, float("nan"), 0.5])

    def test_inf_rejected(self):
        from trinity_local.embeddings import is_finite_embedding
        assert not is_finite_embedding([1.0, float("inf"), 0.5])
        assert not is_finite_embedding([1.0, float("-inf"), 0.5])


class TestWriteBoundaryNaNGate:
    """Per meta-principle #3 (filter at the boundary, not the consumer):
    non-finite vectors must never enter the cache and must never be
    returned by embed()/embed_batch(). MLX has been observed emitting
    NaN under memory pressure or quantization edges — without these
    gates a single bad vector poisons every downstream cosine matmul,
    and the cache makes the poisoning permanent across runs."""

    def test_put_cached_refuses_nan(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        import trinity_local.embeddings.cache as cache_mod
        cache_mod._index = None
        bad = [1.0, float("nan"), 0.5] + [0.0] * 765
        cache_mod.put_cached("nan-text", bad, dim=768)
        assert cache_mod.get_cached("nan-text", dim=768) is None

    def test_put_cached_refuses_inf(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        import trinity_local.embeddings.cache as cache_mod
        cache_mod._index = None
        bad = [1.0, float("inf"), 0.5] + [0.0] * 765
        cache_mod.put_cached("inf-text", bad, dim=768)
        assert cache_mod.get_cached("inf-text", dim=768) is None

    def test_put_cached_accepts_finite(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        import trinity_local.embeddings.cache as cache_mod
        cache_mod._index = None
        good = [0.1] * 768
        cache_mod.put_cached("good-text", good, dim=768)
        assert cache_mod.get_cached("good-text", dim=768) == good

    def test_embed_sanitizes_nan_from_backend(self, tmp_path, monkeypatch):
        """When the MLX backend produces a non-finite vector, embed()
        falls back to TF-IDF instead of returning the poison."""
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        import trinity_local.embeddings.cache as cache_mod
        cache_mod._index = None
        from trinity_local import embeddings

        class _BadBackend:
            def embed(self, text, *, dim=768):
                return [1.0, float("nan"), 0.5] + [0.0] * (dim - 3)

        monkeypatch.setattr(embeddings, "_mlx_backend", _BadBackend())
        vec = embeddings.embed("sanitize me", dim=768)
        assert len(vec) == 768
        assert all(v == v for v in vec)  # no NaN
        assert all(v not in (float("inf"), float("-inf")) for v in vec)

    def test_embed_batch_sanitizes_nan_from_backend(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        import trinity_local.embeddings.cache as cache_mod
        cache_mod._index = None
        from trinity_local import embeddings

        class _BadBackend:
            def embed_batch(self, texts, *, dim=768, batch_size=64):
                # One bad, one good. Test that the bad index is replaced
                # via TF-IDF while the good one passes through.
                good = [0.1] * dim
                bad = [1.0, float("nan"), 0.5] + [0.0] * (dim - 3)
                return [bad if i == 0 else good for i in range(len(texts))]

        monkeypatch.setattr(embeddings, "_mlx_backend", _BadBackend())
        out = embeddings.embed_batch(["nan-text", "ok-text"], dim=768)
        assert len(out) == 2
        assert all(v == v for v in out[0])  # NaN replaced with TF-IDF
        assert all(v == v for v in out[1])
