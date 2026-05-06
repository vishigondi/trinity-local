"""Persistent vector cache for embeddings.

Keyed by sha1(text)[:16] + dim. Stored as JSONL at
~/.trinity/cache/embeddings.jsonl. Shared between product and research paths.
"""
from __future__ import annotations

import hashlib
import json

from ..state_paths import embeddings_cache_path


def _cache_path() -> Path:
    return embeddings_cache_path()


def _text_key(text: str, dim: int = 768) -> str:
    """Cache key: hash of text + dimension."""
    h = hashlib.sha1(text.encode("utf-8", errors="replace")).hexdigest()[:16]
    return f"{h}:{dim}"


# In-memory index (loaded lazily)
_index: dict[str, list[float]] | None = None


def _load_index() -> dict[str, list[float]]:
    """Load the full cache index into memory."""
    global _index
    if _index is not None:
        return _index

    _index = {}
    path = _cache_path()
    if not path.exists():
        return _index

    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            key = record["key"]
            vector = record["vector"]
            _index[key] = vector
        except (json.JSONDecodeError, KeyError, TypeError):
            continue

    return _index


def get_cached(text: str, *, dim: int = 768) -> list[float] | None:
    """Look up a cached vector. Returns None on miss."""
    index = _load_index()
    key = _text_key(text, dim)
    return index.get(key)


def put_cached(text: str, vector: list[float], *, dim: int = 768) -> None:
    """Store a vector in the cache."""
    index = _load_index()
    key = _text_key(text, dim)
    if key in index:
        return  # Already cached

    index[key] = vector
    record = {"key": key, "vector": vector}
    with _cache_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def clear_cache() -> int:
    """Clear the cache. Returns number of entries cleared."""
    global _index
    count = len(_index) if _index else 0
    _index = {}
    path = _cache_path()
    if path.exists():
        path.unlink()
    return count


def cache_stats() -> dict:
    """Return cache statistics."""
    index = _load_index()
    path = _cache_path()
    size = path.stat().st_size if path.exists() else 0
    return {
        "entries": len(index),
        "size_bytes": size,
        "path": str(path),
    }
