from __future__ import annotations

import hashlib
import os
from datetime import datetime, timezone
from pathlib import Path


def now_iso() -> str:
    """Return the current UTC time as an ISO 8601 string with second precision."""
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def stable_id(prefix: str, *parts: str) -> str:
    """Derive a deterministic short ID from a prefix and variable-length key parts."""
    digest = hashlib.sha1("|".join(parts).encode("utf-8")).hexdigest()[:16]
    return f"{prefix}_{digest}"


def atomic_write_text(path: Path, content: str, *, encoding: str = "utf-8") -> None:
    """Write ``content`` to ``path`` atomically via tmp+rename.

    Why: ``path.write_text(content)`` can leave a half-written file on disk
    if the process is killed mid-write (crash, OOM, disk full, signal). The
    consumer then sees an invalid file at the canonical path. Atomic
    rename means readers always see either the old content or the full new
    content — never a partial write.

    Per-process tmp suffix (PID-stamped) avoids cross-process collisions
    where two concurrent writers share the same tmp file. Last-rename
    wins on the target path, but each writer's bytes were complete.

    Promoted to a single helper after Principle #17 audit found the same
    tmp+rename shape inlined in 5 places (cortex.py, cold_start.py,
    capture_host.py, incremental_ingest.py, council_runtime.py).
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    try:
        tmp.write_text(content, encoding=encoding)
        tmp.replace(path)
    finally:
        # If the rename failed, clean up the leftover tmp so the dir
        # doesn't accumulate orphans on repeated failures.
        if tmp.exists():
            try:
                tmp.unlink()
            except OSError:
                pass
