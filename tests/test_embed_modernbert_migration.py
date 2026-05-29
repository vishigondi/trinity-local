"""#244: the embedder is modernbert-embed-base on a REAL MLX backend.

Pins the migration off nomic-embed-text-v1.5 (custom nomic_bert arch — MLX-
unsupported, torch-MPS-wedging) onto nomic-ai/modernbert-embed-base (standard
ModernBERT arch: real MLX on Apple via backend_mlx_native, torch elsewhere; 8192
ctx, Matryoshka, Apache-2.0). Guards: (a) both backends point at modernbert so a
machine's vectors are model-consistent; (b) the retired v1.5 id can't silently
return; (c) the native backend exposes the embed interface + is preferred.
"""
from __future__ import annotations


def test_mlx_native_backend_uses_modernbert():
    from trinity_local.embeddings.backend_mlx_native import MLX_MODEL_ID
    assert MLX_MODEL_ID == "nomic-ai/modernbert-embed-base"


def test_torch_fallback_also_uses_modernbert():
    # The torch/sentence-transformers fallback must use the SAME model so
    # vectors are model-consistent regardless of runtime.
    from trinity_local.embeddings.backend_mlx import MODEL_ID
    assert MODEL_ID == "nomic-ai/modernbert-embed-base"


def test_retired_v15_model_id_absent_from_both_backends():
    import trinity_local.embeddings.backend_mlx as t
    import trinity_local.embeddings.backend_mlx_native as m
    assert "nomic-embed-text-v1.5" not in t.MODEL_ID
    assert "nomic-embed-text-v1.5" not in m.MLX_MODEL_ID


def test_native_backend_has_embed_interface():
    from trinity_local.embeddings.backend_mlx_native import MlxNativeEmbedder
    # methods exist (don't instantiate — that loads MLX); interface parity
    # with the torch backend + the embed_batch/embed contract __init__ relies on.
    for name in ("embed", "embed_batch"):
        assert callable(getattr(MlxNativeEmbedder, name, None)), f"missing {name}"


def test_env_override_for_torch_model(monkeypatch):
    # TRINITY_EMBED_MODEL lets a power user pin a different model on the torch path.
    monkeypatch.setenv("TRINITY_EMBED_MODEL", "some-other/model")
    import importlib
    import trinity_local.embeddings.backend_mlx as t
    importlib.reload(t)
    assert t.MODEL_ID == "some-other/model"
    monkeypatch.delenv("TRINITY_EMBED_MODEL", raising=False)
    importlib.reload(t)
    assert t.MODEL_ID == "nomic-ai/modernbert-embed-base"
