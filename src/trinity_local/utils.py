from __future__ import annotations

import hashlib
from datetime import datetime, timezone


def now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string with second precision."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stable_id(prefix: str, *parts: str) -> str:
    """Derive a deterministic short ID from a prefix and variable-length key parts."""
    digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"
