"""Cold-start auto-scan of local CLI transcripts on first MCP spawn.

The wow flow needs personalization on the first council, not a week
later. The four local-CLI parsers (Claude Code, Codex, Antigravity,
Cowork) all read from on-disk dirs the user already has — so the
moment Trinity's MCP child starts under a brand-new install, we can
auto-detect "no corpus + at least one CLI source present" and kick a
background scan. The server keeps serving tool calls immediately;
tool responses surface a `cold_start_scan` hint so the agent can tell
the user "I'm ingesting your CLI history…" while the scan runs.

Privacy invariant: same data path as the retired `seed-from-taste-terminal`
(replaced by `import-export` 2026-05-27). Only walks transcript dirs
the user already owns on this machine. No exports, no network, no
opt-in dialog. Same `incremental_ingest`
pipeline so dedup / cursors / parser fallthrough behavior is shared.

Disable for tests + CI with ``TRINITY_AUTOSCAN_DISABLED=1``; the
conftest autouse fixture sets it so tests never scan the developer's
real ``~/.claude/``.
"""
from __future__ import annotations

import json
import os
import threading
import time
from pathlib import Path

from .state_paths import state_dir
from .utils import now_iso


COLD_START_SOURCES = ("claude", "codex", "gemini", "cowork")
DEFAULT_SCAN_DEADLINE_S = 300.0
HINT_FRESH_WINDOW_S = 600.0  # surface "scan complete" for 10 min after finish


def cold_start_state_path() -> Path:
    return state_dir() / "cold_start_scan.json"


def _autoscan_disabled() -> bool:
    return os.environ.get("TRINITY_AUTOSCAN_DISABLED", "").strip() not in ("", "0", "false", "False")


def detect_available_sources() -> list[str]:
    """Return the subset of local-CLI sources whose dirs exist on this
    machine. Empty dir counts as absent — a user who installed Claude
    Code but never ran it shouldn't trigger an empty cold-start scan."""
    from .watch_runtime import _iter_recent_paths, _source_root

    available: list[str] = []
    for source in COLD_START_SOURCES:
        try:
            root = _source_root(source)
        except ValueError:
            continue
        if not root.exists():
            continue
        # At least one matching transcript file present.
        if any(True for _ in _iter_recent_paths(source, 0.0)):
            available.append(source)
    return available


def _corpus_is_empty() -> bool:
    """True when no PromptNodes are on disk. Read directly from the
    JSONL file path to avoid pulling the full module + cache layer on
    the cold-start hot path."""
    from .state_paths import prompts_dir

    path = prompts_dir() / "prompt_nodes.jsonl"
    if not path.exists():
        return True
    try:
        return path.stat().st_size == 0
    except OSError:
        return True


def is_cold_start() -> bool:
    """Cold-start trigger: empty corpus AND no prior scan state AND at
    least one local CLI source present AND not disabled by env."""
    if _autoscan_disabled():
        return False
    if cold_start_state_path().exists():
        return False
    if not _corpus_is_empty():
        return False
    return bool(detect_available_sources())


def read_state() -> dict | None:
    path = cold_start_state_path()
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _write_state(state: dict) -> None:
    from .utils import atomic_write_text
    atomic_write_text(cold_start_state_path(), json.dumps(state, indent=2))


def _run_scan(sources: list[str], deadline_s: float, start_iso: str) -> None:
    """The thread body. Runs the scan, rewrites the state file with the
    result. Wrapped in broad try/except: a parser blow-up in any source
    cannot leave the state file at status=in_progress forever (would
    block future cold-start triggers).

    The initial in_progress state file is written synchronously by
    ``kick_cold_start_scan`` BEFORE this thread starts, so the
    cross-process race (two MCP servers calling is_cold_start()
    simultaneously) closes via the existence-check on the state file.
    """
    from .incremental_ingest import ingest_recent

    started = time.monotonic()
    error: str | None = None
    added = 0
    scanned = 0
    try:
        result = ingest_recent(sources=sources, deadline_s=deadline_s)
        added = result.added
        scanned = result.scanned
    except Exception as exc:
        error = f"{type(exc).__name__}: {exc}"

    _write_state({
        "status": "failed" if error else "complete",
        "started_at": start_iso,
        "finished_at": now_iso(),
        "sources_detected": list(sources),
        "added": added,
        "scanned": scanned,
        "deadline_s": deadline_s,
        "duration_s": round(time.monotonic() - started, 2),
        "error": error,
    })


def kick_cold_start_scan(deadline_s: float = DEFAULT_SCAN_DEADLINE_S) -> dict | None:
    """Spawn the cold-start scan in a daemon thread. Returns the initial
    state dict (with status=in_progress), or None when no scan was kicked
    (autoscan disabled, corpus non-empty, prior scan present, or no
    available sources). Caller doesn't wait — the thread runs to deadline
    or completion and rewrites the state file.

    The initial in_progress state file is written SYNCHRONOUSLY before
    the daemon thread starts. This closes the cross-process race where
    two MCP servers (Claude Code + Codex CLI + Cursor + Antigravity all
    spawn on session start) call is_cold_start() simultaneously and
    both see an empty state — only the first to reach this function
    creates the state file; the rest hit the `is_cold_start()`
    state-file-exists short-circuit and return None.
    """
    if not is_cold_start():
        return None
    sources = detect_available_sources()
    if not sources:
        return None

    start_iso = now_iso()
    # Write the in_progress state BEFORE spawning the thread so the
    # second simultaneous caller's is_cold_start() check sees it and
    # bails. Within a single process, threading.Lock would be cheaper
    # but doesn't help across processes; the on-disk state file is
    # the cross-process serialization point.
    _write_state({
        "status": "in_progress",
        "started_at": start_iso,
        "finished_at": None,
        "sources_detected": list(sources),
        "added": 0,
        "scanned": 0,
        "deadline_s": deadline_s,
        "error": None,
    })

    thread = threading.Thread(
        target=_run_scan,
        args=(sources, deadline_s, start_iso),
        name="trinity-cold-start-scan",
        daemon=True,
    )
    thread.start()
    return read_state()


def cold_start_hint() -> dict | None:
    """For MCP tool responses. Returns a compact payload when the scan
    is running OR finished within ``HINT_FRESH_WINDOW_S``. The agent
    surfaces it inline so the user sees "I'm building your memory" without
    a launchpad detour. Returns None when no scan has ever fired (cold-
    start blocked or already-warm install) or when the scan is too old
    to be the agent's news."""
    state = read_state()
    if state is None:
        return None
    status = state.get("status")
    if status == "in_progress":
        return {
            "status": "in_progress",
            "message": (
                f"Trinity is ingesting your local CLI history "
                f"({', '.join(state.get('sources_detected', []))}). "
                f"Responses get more personal as it lands."
            ),
            "added_so_far": state.get("added", 0),
        }
    if status in ("complete", "failed"):
        # Only surface for a short window post-finish.
        finished_at = state.get("finished_at")
        if not finished_at:
            return None
        try:
            from datetime import datetime, timezone
            ts = datetime.fromisoformat(finished_at.replace("Z", "+00:00"))
            age_s = (datetime.now(timezone.utc) - ts).total_seconds()
        except (ValueError, TypeError):
            return None
        if age_s > HINT_FRESH_WINDOW_S:
            return None
        if status == "failed":
            return {
                "status": "failed",
                "message": (
                    "Cold-start ingest of your CLI history hit an error: "
                    f"{state.get('error') or 'unknown'}. "
                    "Run `trinity-local import-export <path>` to retry."
                ),
                "added": state.get("added", 0),
            }
        return {
            "status": "complete",
            "message": (
                f"Trinity finished ingesting {state.get('added', 0)} prompts "
                f"from {', '.join(state.get('sources_detected', []))}. "
                f"Memories will warm up over the next few councils."
            ),
            "added": state.get("added", 0),
        }
    return None


def maybe_kick_cold_start() -> dict | None:
    """Idempotent entry point for the MCP server startup hook. Wraps
    ``kick_cold_start_scan`` so thread-spawn failures cannot crash the
    MCP server."""
    try:
        return kick_cold_start_scan()
    except Exception:
        return None


# ── activity-gated lens refresh (Anthropic Auto-Dream pattern) ─────────
#
# Auto-Dream triggers on "24h elapsed AND 5 sessions" — NOT a wall-clock
# nightly cron. We mirror that: refresh an EXISTING lens when enough time
# has passed AND enough new conversation has accumulated, evaluated at MCP
# connect (a natural "session" event) so it runs inside an authenticated
# session — never a 3am cron with no provider auth, never a surprise spend
# on a quiet day. cold-start handles the FIRST build; this handles the
# keep-current refresh.

REFRESH_MIN_AGE_H = 24.0          # Auto-Dream's 24h floor
REFRESH_MIN_NEW_PROMPTS = 5       # Auto-Dream's "5 sessions" analog — enough new material
_REFRESH_COOLDOWN_S = 1800.0      # don't re-kick within 30 min (in-flight damping)
# A refresh lock older than this is presumed dead (its owner crashed mid-build
# and never released it). Bounds the cost of a single lost lock to one stale
# window. Comfortably larger than a real delta rebuild + a safety margin.
_REFRESH_LOCK_STALE_S = 3600.0


def lens_refresh_marker_path() -> Path:
    return state_dir() / "lens_refresh.json"


def lens_refresh_lock_path() -> Path:
    return state_dir() / "lens_refresh.lock"


def _hours_since(iso: str | None) -> float | None:
    if not iso or not isinstance(iso, str):
        return None
    import datetime as _dt
    try:
        ts = _dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return None
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=_dt.timezone.utc)
    return (_dt.datetime.now(_dt.timezone.utc) - ts).total_seconds() / 3600.0


def _fingerprint_count(fp: str) -> int:
    """Fingerprints are 'count:sha1'. Pull the leading count, or 0."""
    head = (fp or "").split(":", 1)[0]
    return int(head) if head.isdigit() else 0


def should_refresh_lens() -> tuple[bool, str]:
    """Activity gate: refresh iff a lens exists, ≥REFRESH_MIN_AGE_H since the
    last build, AND ≥REFRESH_MIN_NEW_PROMPTS new prompts have landed. Returns
    (should, human_reason). Pure read — never raises."""
    try:
        from .me_builder import _corpus_fingerprint, _lens_build_state_path, me_path

        if not me_path().exists():
            return False, "no lens yet (cold-start territory, not refresh)"
        sp = _lens_build_state_path()
        if not sp.exists():
            return False, "no build-state to age against"
        try:
            st = json.loads(sp.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return False, "unreadable build state"
        age_h = _hours_since(st.get("built_at"))
        if age_h is None:
            return False, "no built_at timestamp"
        if age_h < REFRESH_MIN_AGE_H:
            return False, f"last build {age_h:.1f}h ago (< {REFRESH_MIN_AGE_H:.0f}h floor)"
        prior_fp = st.get("fingerprint") or ""
        cur_fp = _corpus_fingerprint()
        if cur_fp == prior_fp:
            return False, "corpus unchanged since last build"
        new_prompts = _fingerprint_count(cur_fp) - _fingerprint_count(prior_fp)
        if new_prompts < REFRESH_MIN_NEW_PROMPTS:
            return False, f"only {new_prompts} new prompt(s) (< {REFRESH_MIN_NEW_PROMPTS})"
        return True, f"{new_prompts} new prompts, {age_h:.0f}h since last build"
    except Exception as exc:
        return False, f"gate error: {exc}"


def _recently_kicked() -> bool:
    """True if a refresh was kicked within the cooldown — damps re-kicks on
    repeated connects while one is still in flight."""
    p = lens_refresh_marker_path()
    if not p.exists():
        return False
    try:
        last = _hours_since(json.loads(p.read_text(encoding="utf-8")).get("last_kick_at"))
    except (OSError, ValueError):
        return False
    return last is not None and (last * 3600.0) < _REFRESH_COOLDOWN_S


def _write_refresh_marker(payload: dict) -> None:
    try:
        from .utils import atomic_write_text
        p = lens_refresh_marker_path()
        p.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(p, json.dumps(payload))
    except Exception:
        pass


def _try_claim_refresh_lock() -> bool:
    """Atomic cross-process claim. Returns True iff THIS caller won the right
    to rebuild.

    Why this exists (#234): every CLI harness the user has connected (Claude
    Code + Codex CLI + Cursor + Antigravity) spawns its own MCP child, and
    they all hit `maybe_kick_lens_refresh()` on connect. `should_refresh_lens()`
    and `_recently_kicked()` are both pure reads, so without a lock all four
    children pass the gate in the same instant and each kicks a full chairman-
    driven rebuild — quadruple spend and four writers racing on the same
    ledger. The single-process cooldown marker can't close this: it's written
    AFTER the check, so concurrent racers all read it as absent.

    The lock is an `O_CREAT | O_EXCL` create — the OS guarantees exactly one
    creator even across processes. A lock older than `_REFRESH_LOCK_STALE_S`
    is treated as abandoned (owner crashed mid-build) and reclaimed, so a lost
    lock self-heals after one stale window instead of wedging refresh forever.
    """
    import os as _os

    path = lens_refresh_lock_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        return False

    # Reclaim a stale lock (crashed owner) before attempting the claim.
    try:
        age_s = time.time() - path.stat().st_mtime
        if age_s > _REFRESH_LOCK_STALE_S:
            path.unlink()
    except OSError:
        pass  # missing (fine) or unstattable (let the create attempt decide)

    try:
        fd = _os.open(str(path), _os.O_CREAT | _os.O_EXCL | _os.O_WRONLY, 0o644)
    except FileExistsError:
        return False  # another harness holds the lock — it owns this rebuild
    except OSError:
        return False
    try:
        _os.write(fd, f"{_os.getpid()}|{now_iso()}".encode("utf-8"))
    except OSError:
        pass
    finally:
        _os.close(fd)
    return True


def _release_refresh_lock() -> None:
    try:
        lens_refresh_lock_path().unlink()
    except OSError:
        pass


def maybe_kick_lens_refresh() -> dict | None:
    """If the activity gate is open and no refresh is in flight, background-
    kick a (cheap, delta) lens rebuild. Best-effort: every failure path is
    swallowed so it can't crash or block the MCP server. Returns the kick
    record, or None when skipped.

    #234: the actual in-flight guard is the cross-process lock claimed by
    `_try_claim_refresh_lock()` — only ONE concurrently-connecting harness
    wins it and rebuilds; the rest see the existing lock and bail. The
    `_recently_kicked()` cooldown stays as a cheap pre-filter so the common
    no-op connect doesn't even touch the lockfile."""
    if _autoscan_disabled():
        return None
    try:
        ok, reason = should_refresh_lens()
        if not ok or _recently_kicked():
            return None
        # Atomic check-and-set: only the lock winner proceeds. Closes the
        # TOCTOU window where N harnesses all pass the pure-read gate above
        # in the same instant and each spawns a rebuild.
        if not _try_claim_refresh_lock():
            return None
        _write_refresh_marker({"last_kick_at": now_iso(), "reason": reason, "status": "in_progress"})

        def _run():
            try:
                from .me_builder import build_me_via_lens_pipeline
                _path, summary = build_me_via_lens_pipeline()
                _write_refresh_marker({
                    "last_kick_at": now_iso(), "reason": reason, "status": "done",
                    "finished_at": now_iso(), "summary": summary,
                })
            except Exception as exc:
                _write_refresh_marker({
                    "last_kick_at": now_iso(), "reason": reason, "status": "failed",
                    "finished_at": now_iso(), "error": str(exc)[:200],
                })
            finally:
                _release_refresh_lock()

        threading.Thread(target=_run, daemon=True, name="trinity-lens-refresh").start()
        return {"status": "kicked", "reason": reason}
    except Exception:
        return None


def cold_open_tension() -> str | None:
    """The cold-start *aha* (#212 / Q2): ONE surprising, true thing about how
    the user decides — surfaced the instant their lens has any signal, before
    they've learned a single verb.

    It names the single highest-support decision *axis* from the lens (the
    tension they keep navigating), NOT a fixed winner — the lens models a
    both-defensible tension, so claiming "you always pick X" would overclaim.
    Returns None until a lens/registry tension exists (cold install). Pure
    read, fully best-effort: never raises into a startup/status path."""
    try:
        from .me.lens_registry import LOW_CONFIDENCE_BELOW, active_tensions_sorted

        tensions = active_tensions_sorted()
        if tensions:
            t = tensions[0]
            n = t.support_count
            prov = f" — seen across {n} of your decisions" if n >= LOW_CONFIDENCE_BELOW else ""
            return (
                f"One axis your lens already surfaces: “{t.pole_a}” vs "
                f"“{t.pole_b}” — the tension you keep navigating{prov}."
            )
    except Exception:
        pass
    # Fallback for a pre-registry lens: the first accepted pair.
    try:
        from .me.pair_mining import load_lenses

        pairs = load_lenses()
        if pairs:
            p = pairs[0]
            return (
                f"One axis your lens already surfaces: “{p.pole_a}” vs "
                f"“{p.pole_b}” — the tension you keep navigating."
            )
    except Exception:
        pass
    return None
