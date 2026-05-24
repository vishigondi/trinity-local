"""Embedding layer for Trinity Local.

Public API:
    embed(text)       → list[float]   (MLX if available, TF-IDF fallback)
    embed_batch(texts) → list[list[float]]  (batched, 10-50× faster on MLX)
    similarity(a, b)  → float         (cosine similarity)
    is_available()    → bool          (True if MLX backend loaded)
    get_backend()     → str           ("mlx" | "tfidf")

This package is imported by both the product path (watch_runtime) and
the research path (research/ranking). It owns model loading and inference.

The persistent embedding cache (`~/.trinity/cache/embeddings.jsonl`) was
retired 2026-05-17 in the pre-launch simplification pass. With the
embedding-powered search hot-path already removed (Tier 1 #4), the only
remaining consumers are the offline rebuild commands (`dream`,
`lens-build`, `vocabulary`, `consolidate`); each pass re-encodes its
own corpus, which costs ~2 min on a 50k-prompt corpus but saves a
persistent state file, an unbounded growth gotcha, and two CLI surfaces
(`cache-stats`, `cache-clear`). Re-introduce an in-memory cache here
if power-user perf complaints surface post-launch.
"""
from __future__ import annotations

from .backend_tfidf import embed_tfidf, cosine_similarity

# Try to load MLX backend
# Optimistically create the embedder; runtime failures fall back to TF-IDF
_mlx_backend = None
_backend_name = "tfidf"

# Test-speed escape hatch: TRINITY_DISABLE_MLX=1 forces the TF-IDF
# fallback path without ever importing backend_mlx. Mirrors what users
# without the `[mlx]` extras experience — same fallback code path that
# ships in default pip installs. Used by tests that pin the CLI
# contract but don't need real semantic embeddings (subprocess-spawned
# tests where monkeypatching the parent process can't reach the child).
import os as _os
if _os.environ.get("TRINITY_DISABLE_MLX") != "1":
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

    MLX may fail at runtime (network issues, model not cached, permission errors).
    Any failure falls back gracefully to TF-IDF, ensuring offline availability.

    Non-finite vectors (NaN/Inf) are replaced with TF-IDF for the same
    text before being returned. MLX can occasionally emit non-finite
    components under memory pressure or quantization edge cases; the
    sanitization gate at this boundary means downstream matmuls (basins
    k-means, depth_score cosine, etc.) never see them.

    If the caller pre-prepended a Nomic task prefix (search_query:, search_document:,
    clustering:, classification:), it is preserved. Otherwise the MLX backend
    auto-prepends search_document: for backwards compatibility.
    """
    vector = None
    if _mlx_backend is not None:
        try:
            vector = _mlx_backend.embed(text, dim=dim)
        except Exception:
            vector = None

    if vector is None or not is_finite_embedding(vector):
        vector = embed_tfidf(text, dim=dim)

    return vector


def embed_batch(texts: list[str], *, dim: int = DEFAULT_DIM, batch_size: int = 64) -> list[list[float]]:
    """Batch-embed multiple texts. 10-50× faster than serial embed() on MLX.

    Falls back to per-text tfidf if MLX unavailable. Non-finite vectors
    are sanitized inline (meta-principle #3: filter at the boundary).
    """
    if not texts:
        return []

    new_vectors: list[list[float]] | None = None
    if _mlx_backend is not None:
        try:
            new_vectors = _mlx_backend.embed_batch(texts, dim=dim, batch_size=batch_size)
        except Exception:
            new_vectors = None

    if new_vectors is None:
        return [embed_tfidf(t, dim=dim) for t in texts]

    # Replace any non-finite vectors with TF-IDF fallback for that
    # specific text. MLX can emit NaN/Inf under memory pressure or
    # quantization edge cases; sanitizing here means downstream
    # matmuls (basins, depth, vocabulary, cross_provider) never see
    # them. Meta-principle #3: filter at the boundary.
    for i, vec in enumerate(new_vectors):
        if not is_finite_embedding(vec):
            new_vectors[i] = embed_tfidf(texts[i], dim=dim)
    return new_vectors


def similarity(text_a: str, text_b: str, *, dim: int = DEFAULT_DIM) -> float:
    """Cosine similarity between two texts."""
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


class EmbedderNotReadyError(RuntimeError):
    """Raised by ``require_embedder_ready`` when the nomic-embed
    weights aren't in the local HF cache. CLI handlers catch this
    and surface an actionable message + exit cleanly — much better
    than letting the user discover the ~600 MB requirement mid-command.

    The exception message is already user-readable so handlers can
    print it directly.
    """


def require_embedder_ready() -> None:
    """Cheap filesystem probe — fails fast if the embedder model isn't
    downloaded. Call BEFORE starting any heavy CLI work (lens-build,
    dream, vocabulary) so the user gets a clear "download required"
    signal instead of a multi-minute CLI startup followed by an
    HF_HUB_OFFLINE error mid-call.

    Same source-of-truth as the launchpad's "Build deeper memory"
    card (launchpad_data._embedder_status). The check is a single
    directory probe — no torch / transformers import, no network call.
    """
    from pathlib import Path

    # Probe the canonical HF cache layout. SentenceTransformer caches
    # models under ~/.cache/huggingface/hub/models--<org>--<name>/snapshots/<hash>/.
    hf_cache = Path.home() / ".cache" / "huggingface" / "hub"
    model_cache_dir = hf_cache / "models--nomic-ai--nomic-embed-text-v1.5"
    if model_cache_dir.exists():
        snapshots = model_cache_dir / "snapshots"
        if snapshots.exists():
            for snapshot in snapshots.iterdir():
                if snapshot.is_dir() and any(snapshot.iterdir()):
                    return  # at least one populated snapshot → ready

    # Also check whether sentence-transformers libs are present —
    # without those, even after the model download the embedder won't
    # work, so the error message must mention pip install too.
    try:
        __import__("sentence_transformers")
        libs_present = True
    except ImportError:
        libs_present = False

    fallback = "huggingface-cli download nomic-ai/nomic-embed-text-v1.5"
    if libs_present:
        # Preferred: Trinity verb (wraps huggingface-cli download with
        # in-product messaging + idempotency). Falls back to the raw
        # huggingface-cli command for users who don't have trinity-local
        # on PATH yet (mid-install).
        command = "trinity-local download-embedder"
        download_block = (
            f"Download once with:\n"
            f"  {command}\n"
            f"(or directly: {fallback})\n\n"
        )
    else:
        command = (
            "pip install 'trinity-local[mlx]' && "
            "trinity-local download-embedder"
        )
        download_block = (
            f"Install the MLX extras + download the model with:\n"
            f"  {command}\n"
            f"(under the hood: {fallback})\n\n"
        )

    raise EmbedderNotReadyError(
        f"Trinity's embedding model (nomic-embed-text-v1.5, ~600 MB) isn't"
        f"in your HuggingFace cache. This command needs it for topic "
        f"basins / lens-build / vocabulary distillation.\n\n"
        f"{download_block}"
        f"Then re-run this command. The model lands at "
        f"~/.cache/huggingface/hub/ and never re-downloads."
    )


def model_status() -> dict:
    """Return model status."""
    return {
        "backend": get_backend(),
        "mlx_available": is_available(),
        "model_path": str(_mlx_backend.model_path) if _mlx_backend else None,
        "model_ready": _mlx_backend.is_ready() if _mlx_backend else False,
    }
