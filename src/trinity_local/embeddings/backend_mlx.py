"""MLX backend for nomic-embed-text-v1.5.

Uses sentence-transformers with PyTorch for inference.
Apple Silicon acceleration via MPS when available.

Model: nomic-ai/nomic-embed-text-v1.5 (137M params, 8192 token context)
Supports Matryoshka dimensions: 768, 512, 256, 128, 64
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

from ..config import trinity_home

MODEL_ID = "nomic-ai/nomic-embed-text-v1.5"
MODEL_DIR_NAME = "nomic-embed-text-v1.5"
MAX_TOKENS = 8192
DEFAULT_DIM = 512


def models_dir() -> Path:
    path = trinity_home() / "models"
    path.mkdir(parents=True, exist_ok=True)
    return path


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
        """Check if sentence-transformers is importable AND model is cached locally.

        Returns True only if both conditions are met:
        - sentence-transformers package is installed
        - Model files are already cached (not requiring network download)

        In offline environments, this will return False even if the package is installed,
        because SentenceTransformer requires downloading the model on first use.
        """
        try:
            import sentence_transformers
        except ImportError:
            return False

        # Check if model is already cached locally by looking for the model directory
        # The sentence-transformers default cache is at ~/.cache/huggingface/hub/
        try:
            from pathlib import Path
            hf_cache = Path.home() / ".cache" / "huggingface" / "hub"
            # Model is cached if the directory exists and has content
            model_dir = hf_cache / f"models--nomic-ai--nomic-embed-text-v1.5"
            return model_dir.exists() and any(model_dir.iterdir())
        except Exception:
            return False

    def _load(self) -> None:
        if self._loaded:
            return

        from sentence_transformers import SentenceTransformer
        self._model = SentenceTransformer(MODEL_ID, trust_remote_code=True)
        self._loaded = True

    def embed(self, text: str, *, dim: int = DEFAULT_DIM) -> list[float]:
        """Embed a single text. Uses Matryoshka truncation to `dim`."""
        self._load()
        # nomic requires "search_document: " prefix for documents
        prefixed = f"search_document: {text}"
        vector = self._model.encode(prefixed).tolist()
        truncated = vector[:dim]
        return _l2_normalize(truncated)

    def embed_batch(self, texts: list[str], *, dim: int = DEFAULT_DIM, batch_size: int = 32) -> list[list[float]]:
        """Embed multiple texts in batches."""
        self._load()
        prefixed = [f"search_document: {t}" for t in texts]
        vectors = self._model.encode(prefixed, batch_size=batch_size)
        return [_l2_normalize(v[:dim].tolist()) for v in vectors]
