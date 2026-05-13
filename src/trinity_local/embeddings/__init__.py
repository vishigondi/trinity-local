"""Embedding layer for Trinity Local.

Public API:
    embed(text)       → list[float]   (MLX if available, TF-IDF fallback)
    similarity(a, b)  → float         (cosine similarity, cached)
    is_available()    → bool          (True if MLX backend loaded)
    get_backend()     → str           ("mlx" | "tfidf")

This package is imported by both the product path (watch_runtime) and
the research path (research/ranking). It owns model loading, inference,
and caching. The watcher never calls the model twice for the same text.
"""
from __future__ import annotations

from .cache import get_cached, put_cached
from .backend_tfidf import embed_tfidf, cosine_similarity

# Try to load MLX backend
# Optimistically create the embedder; runtime failures fall back to TF-IDF
_mlx_backend = None
_backend_name = "tfidf"

try:
    from .backend_mlx import MlxEmbedder
    _mlx_backend = MlxEmbedder()
    _backend_name = "mlx"  # Optimistic; embed() will fall back if it fails
except ImportError:
    _mlx_backend = None
except Exception:
    _mlx_backend = None


def is_available() -> bool:
    """True if the MLX backend was successfully imported.

    Note: MLX may still fail at runtime (network, cache issues, permissions).
    The embed() function gracefully falls back to TF-IDF if MLX fails.
    """
    return _mlx_backend is not None


def get_backend() -> str:
    """Return the active backend name: 'mlx' or 'tfidf'."""
    return _backend_name


DEFAULT_DIM = 768


def is_finite_embedding(emb) -> bool:
    """True if `emb` is a non-empty sequence of all-finite floats.

    Single source of truth for the NaN/Inf filter — historically the
    same shape was inlined three different ways in `me/depth.py`,
    `me/basins.py`, and `me_builder.py`, and two other consumers
    (`cross_provider_pairs.py`, `vocabulary._gather_token_contexts`)
    forgot it entirely. A single non-finite row poisons numpy matmuls
    (NaN cells propagate across every other row's distances) and
    silently corrupts cluster centroids; the bug only surfaces when
    real-corpus tests exercise downstream signals. Centralizing the
    check lets every embedding consumer call one function and lets
    the audit grep for one name.

    Returns False for None, empty sequences, and anything containing
    NaN, +inf, or -inf. Cheap inline loop — faster than np conversion
    for the filter step (avoids materializing an array per row).
    """
    if not emb:
        return False
    try:
        for v in emb:
            if v != v or v == float("inf") or v == float("-inf"):
                return False
    except TypeError:
        return False
    return True


def embed(text: str, *, dim: int = DEFAULT_DIM) -> list[float]:
    """Embed text into a dense vector.

    Uses MLX (nomic-embed-text-v1.5) if available, TF-IDF stub otherwise.
    Results are cached by text hash.

    MLX may fail at runtime (network issues, model not cached, permission errors).
    Any failure falls back gracefully to TF-IDF, ensuring offline availability.

    Non-finite vectors (NaN/Inf) are replaced with TF-IDF for the same
    text before being cached or returned. MLX can occasionally emit
    non-finite components under memory pressure or quantization edge
    cases; the sanitization gate at this boundary means downstream
    matmuls (basins k-means, depth_score cosine, etc.) never see them.

    If the caller pre-prepended a Nomic task prefix (search_query:, search_document:,
    clustering:, classification:), it is preserved. Otherwise the MLX backend
    auto-prepends search_document: for backwards compatibility.
    """
    cached = get_cached(text, dim=dim)
    if cached is not None:
        return cached

    # Try MLX first, but fall back to TF-IDF on any error
    vector = None
    if _mlx_backend is not None:
        try:
            vector = _mlx_backend.embed(text, dim=dim)
        except Exception:
            # MLX failed (network, missing model, permissions, etc.)
            # Fall back to TF-IDF
            vector = None

    if vector is None or not is_finite_embedding(vector):
        vector = embed_tfidf(text, dim=dim)

    put_cached(text, vector, dim=dim)
    return vector


def embed_batch(texts: list[str], *, dim: int = DEFAULT_DIM, batch_size: int = 64) -> list[list[float]]:
    """Batch-embed multiple texts. 10-50× faster than serial embed() on MLX.

    Cache-aware: returns cached vectors for known texts, only sends unknown
    texts through the model. Falls back to per-text tfidf if MLX unavailable.
    """
    if not texts:
        return []

    # Cache lookup pass
    cached_results: list[list[float] | None] = [get_cached(t, dim=dim) for t in texts]
    uncached_indices = [i for i, v in enumerate(cached_results) if v is None]
    if not uncached_indices:
        return [v for v in cached_results if v is not None]

    uncached_texts = [texts[i] for i in uncached_indices]
    new_vectors: list[list[float]] | None = None
    if _mlx_backend is not None:
        try:
            new_vectors = _mlx_backend.embed_batch(uncached_texts, dim=dim, batch_size=batch_size)
        except Exception:
            new_vectors = None

    if new_vectors is None:
        new_vectors = [embed_tfidf(t, dim=dim) for t in uncached_texts]
    else:
        # Replace any non-finite vectors with TF-IDF fallback for that
        # specific text. MLX can emit NaN/Inf under memory pressure or
        # quantization edge cases; sanitizing here means downstream
        # matmuls (basins, depth, vocabulary, cross_provider) never see
        # them. Meta-principle #3: filter at the boundary.
        for i, vec in enumerate(new_vectors):
            if not is_finite_embedding(vec):
                new_vectors[i] = embed_tfidf(uncached_texts[i], dim=dim)

    # Stitch results back in order + write to cache
    for idx, vec in zip(uncached_indices, new_vectors):
        cached_results[idx] = vec
        put_cached(texts[idx], vec, dim=dim)
    return [v for v in cached_results if v is not None]


def similarity(text_a: str, text_b: str, *, dim: int = DEFAULT_DIM) -> float:
    """Cosine similarity between two texts. Cached per-text."""
    vec_a = embed(text_a, dim=dim)
    vec_b = embed(text_b, dim=dim)
    return cosine_similarity(vec_a, vec_b)


def setup_model(*, force: bool = False) -> str:
    """Download the MLX model. Returns status message."""
    try:
        from .backend_mlx import download_model
    except ImportError:
        return "MLX dependencies not installed. Run: pip install trinity-local[mlx]"

    return download_model(force=force)


def model_status() -> dict:
    """Return model and cache status."""
    from .cache import cache_stats
    stats = cache_stats()
    return {
        "backend": get_backend(),
        "mlx_available": is_available(),
        "model_path": str(_mlx_backend.model_path) if _mlx_backend else None,
        "model_ready": _mlx_backend.is_ready() if _mlx_backend else False,
        "cache_entries": stats["entries"],
        "cache_size_bytes": stats["size_bytes"],
    }
