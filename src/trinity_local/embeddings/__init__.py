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

from .cache import get_cached, put_cached, clear_cache
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


def embed(text: str, *, dim: int = 512) -> list[float]:
    """Embed text into a dense vector.

    Uses MLX (nomic-embed-text-v1.5) if available, TF-IDF stub otherwise.
    Results are cached by text hash.

    MLX may fail at runtime (network issues, model not cached, permission errors).
    Any failure falls back gracefully to TF-IDF, ensuring offline availability.
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

    if vector is None:
        vector = embed_tfidf(text)

    put_cached(text, vector, dim=dim)
    return vector


def similarity(text_a: str, text_b: str, *, dim: int = 512) -> float:
    """Cosine similarity between two texts. Cached per-text."""
    vec_a = embed(text_a, dim=dim)
    vec_b = embed(text_b, dim=dim)
    return cosine_similarity(vec_a, vec_b)


def setup_model(*, force: bool = False) -> str:
    """Download the MLX model. Returns status message."""
    try:
        from .backend_mlx import MlxEmbedder, download_model
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
