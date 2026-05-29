"""#241: the embedder must pin device=cpu by default (TRINITY_EMBED_DEVICE override).

The "MLX" backend is actually sentence-transformers + torch. nomic-embed-v1.5's
trust_remote_code custom ops are MPS-incompatible → per-op CPU fallback, and the
Metal path can WEDGE on a GPU command-buffer recovery: a real backfill dragged
from ~56 nodes/s to ~12 nodes/MIN after an "innocent victim" Metal error and
never recovered. Measured fresh on M1 Ultra: CPU 56 nodes/s + 3s load vs MPS
97/s but 77s load + wedge-fragile. So we pin CPU. This guard stops a refactor
from silently dropping the pin and re-introducing the wedge.
"""
from __future__ import annotations

import sys
import types


def _install_fake_sentence_transformers(monkeypatch, recorder):
    fake = types.ModuleType("sentence_transformers")

    class _FakeST:
        def __init__(self, model_id, **kw):
            recorder["model_id"] = model_id
            recorder["device"] = kw.get("device")
            recorder["trust_remote_code"] = kw.get("trust_remote_code")

    fake.SentenceTransformer = _FakeST  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake)


def test_default_embed_device_is_cpu(monkeypatch):
    monkeypatch.delenv("TRINITY_EMBED_DEVICE", raising=False)
    rec: dict = {}
    _install_fake_sentence_transformers(monkeypatch, rec)
    from trinity_local.embeddings.backend_mlx import MlxEmbedder

    MlxEmbedder()._load()
    assert rec["device"] == "cpu", (
        f"default embed device must be cpu to avoid the MPS Metal-wedge; got {rec.get('device')!r}"
    )
    assert rec["trust_remote_code"] is True


def test_embed_device_env_override_honored(monkeypatch):
    monkeypatch.setenv("TRINITY_EMBED_DEVICE", "mps")
    rec: dict = {}
    _install_fake_sentence_transformers(monkeypatch, rec)
    from trinity_local.embeddings.backend_mlx import MlxEmbedder

    MlxEmbedder()._load()
    assert rec["device"] == "mps", (
        f"TRINITY_EMBED_DEVICE must override the cpu default; got {rec.get('device')!r}"
    )
