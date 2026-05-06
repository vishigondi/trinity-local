"""MLX backend for nomic-embed-text-v1.5.

Uses sentence-transformers with PyTorch for inference.
Apple Silicon acceleration via MPS when available.

Model: nomic-ai/nomic-embed-text-v1.5 (137M params, 8192 token context)
Supports Matryoshka dimensions: 768, 512, 256, 128, 64
"""
from __future__ import annotations

import math
from pathlib import Path

from ..state_paths import models_dir

MODEL_ID = "nomic-ai/nomic-embed-text-v1.5"
MODEL_DIR_NAME = "nomic-embed-text-v1.5"
MAX_TOKENS = 8192
DEFAULT_DIM = 768

# Nomic task prefixes — if the caller already prepended one, don't double-prefix.
NOMIC_PREFIXES = ("search_document:", "search_query:", "clustering:", "classification:")


def _ensure_nomic_prefix(text: str) -> str:
    stripped = text.lstrip()
    for prefix in NOMIC_PREFIXES:
        if stripped.startswith(prefix):
            return text
    return f"search_document: {text}"

def model_path() -> Path:
    return models_dir() / MODEL_DIR_NAME


def download_model(*, force: bool = False) -> str:
    """Download/verify the model. Returns status message."""
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError:
        return "sentence-transformers not installed. Run: pip install trinity-local[mlx]"

    try:
        # SentenceTransformer handles caching/downloading automatically
        _ = SentenceTransformer(MODEL_ID, trust_remote_code=True)
        return f"Model ready: {MODEL_ID}"
    except Exception as exc:
        return f"Download failed: {exc}"


def _l2_normalize(vector: list[float]) -> list[float]:
    norm = math.sqrt(sum(v * v for v in vector))
    if norm > 0:
        return [v / norm for v in vector]
    return vector


class MlxEmbedder:
    """Embedder using sentence-transformers + nomic-embed-text-v1.5.

    Despite the module name, this uses PyTorch (with MPS on Apple Silicon)
    rather than raw MLX, because the nomic architecture requires trust_remote_code
    and einops for correct inference.
    """

    def __init__(self):
        self._model = None
        self._loaded = False
        self.model_path = model_path()

    def is_ready(self) -> bool:
        """Check if sentence-transformers is importable.

        Note: This is a simple check. The actual embed() call may still fail at runtime
        (network issues, missing model, permissions, etc.). The embeddings module handles
        these failures gracefully by falling back to TF-IDF.

        This function is kept for observability (model_status()) but is NOT used for
        critical decisions.
        """
        try:
            __import__("sentence_transformers")
            return True
        except ImportError:
            return False

    def _load(self) -> None:
        if self._loaded:
            return

        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(MODEL_ID, trust_remote_code=True)
        self._loaded = True

    def embed(self, text: str, *, dim: int = DEFAULT_DIM) -> list[float]:
        """Embed a single text. Uses Matryoshka truncation to `dim`.

        If the caller already prepended a Nomic task prefix (search_query:,
        search_document:, clustering:, classification:), it's preserved.
        Otherwise we default to search_document: for legacy callers.
        """
        self._load()
        prefixed = _ensure_nomic_prefix(text)
        vector = self._model.encode(prefixed).tolist()
        truncated = vector[:dim]
        return _l2_normalize(truncated)

    def embed_batch(self, texts: list[str], *, dim: int = DEFAULT_DIM, batch_size: int = 64) -> list[list[float]]:
        """Embed multiple texts in batches. ~10-50× faster than serial embed().

        Chunks inputs into groups of `batch_size` BEFORE calling model.encode
        — sentence-transformers tokenizes the entire input list upfront, so
        passing 1000 long texts in one call would balloon memory even with
        batch_size=64 honored for inference. We instead loop, calling encode
        with at most `batch_size` texts per call. This bounds peak memory at
        roughly batch_size * max_seq_len * hidden_dim regardless of total N.
        """
        self._load()
        if not texts:
            return []
        out: list[list[float]] = []
        for start in range(0, len(texts), batch_size):
            chunk = texts[start:start + batch_size]
            prefixed = [_ensure_nomic_prefix(t) for t in chunk]
            vectors = self._model.encode(prefixed, batch_size=batch_size)
            out.extend(_l2_normalize(v[:dim].tolist()) for v in vectors)
        return out
