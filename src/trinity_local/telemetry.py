from __future__ import annotations

import hashlib
import json
import os
import secrets
from dataclasses import asdict, dataclass, fields
from pathlib import Path
from typing import Any

from .council_feedback import latest_feedback_by_council
from .state_paths import council_outcomes_dir, telemetry_settings_dir
from .utils import now_iso


TELEMETRY_VERSION = 1

# ─── Disclosed-payload contract (#231 — provably no-PII) ────────────────
#
# Telemetry is default-ON to close the feedback loop, but the *guarantee*
# is that only categorical labels leave the machine — never prompt text,
# lens tensions, or user_substitute strings. These frozensets ARE that
# contract, enforced structurally (build_outbound_event_payload allowlists
# against DISCLOSED_EVENT_PARAMS; tests assert the elo snapshot's keys stay
# within the ELO sets). Growing an outbound field means adding it here
# first — and that addition is reviewable in one place.

# The only categorical params any outbound GA4 event may carry. The one
# live emitter (council_runner → "council_complete") passes exactly these.
DISCLOSED_EVENT_PARAMS = frozenset({"task_type", "winner", "member_count", "mode"})

# Top-level keys the elo snapshot (provider win-rates) may expose to the
# wire / the browser. All categorical or numeric — no free text.
DISCLOSED_ELO_KEYS = frozenset(
    {"version", "window", "council_count", "providers", "matchups"}
)

# Per-provider stat keys inside snapshot["providers"][slug]. Numeric only.
DISCLOSED_ELO_PROVIDER_KEYS = frozenset(
    {"elo", "wins", "total_games", "win_rate", "consistency"}
)


def build_outbound_event_payload(
    event_name: str, params: dict[str, Any]
) -> dict[str, Any]:
    """Construct the GA4 event envelope, dropping every param outside the
    disclosed categorical allowlist (#231a).

    This is the single chokepoint every outbound council event passes
    through. A caller that accidentally hands us ``prompt`` / ``lens`` /
    ``user_substitute`` (or any other un-disclosed key) gets it SILENTLY
    DROPPED here — so a coding mistake upstream can't leak free text onto
    the wire. Returns the GA4 ``{"events": [{"name", "params"}]}`` shape
    (caller adds ``client_id``).
    """
    safe = {k: params[k] for k in DISCLOSED_EVENT_PARAMS if k in params}
    return {"events": [{"name": event_name, "params": safe}]}


@dataclass
class TelemetrySettings:
    # Default ON since 2026-05-27 per docs/CUT-CANDIDATES.md Category C +
    # user direction. Categorical routing labels + install/usage events
    # only — never prompt content. Disable with `trinity-local telemetry-disable`.
    sharing_enabled: bool = True
    share_usage_events: bool = True
    share_elo_summaries: bool = True
    share_install_id: str = ""
    endpoint: str | None = None
    consented_at: str | None = None
    last_view_upload_at: str | None = None
    last_elo_upload_at: str | None = None
    last_elo_hash: str | None = None
    last_upload_status: str | None = None
    # auto_chain_enabled / max_chain_rounds / polish_auto_iterate retired
    # 2026-05-17 — auto-iterate is now a per-council click via the
    # council-page button, not a global setting.
    # When True, council_runner shells out `open <review_path>` after
    # writing the final unified council page. macOS only — silently
    # no-ops elsewhere. Off by default (some users don't want a browser
    # tab on every council).
    auto_open_council: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return {k: v for k, v in payload.items() if v not in ("", None, [], {})}


def telemetry_settings_path() -> Path:
    return telemetry_settings_dir() / "telemetry.json"


# Google Analytics 4 Measurement Protocol endpoint. Trinity sends
# categorical routing labels + install/usage events here when the user
# has opted in (default ON since 2026-05-27 per docs/CUT-CANDIDATES.md
# Category C — vishigondi GA4 property 539262453). NO prompt content,
# NO lens text — only the categorical labels documented in CLAUDE.md
# "Architectural commitments" #2.
GA4_ENDPOINT = "https://www.google-analytics.com/mp/collect"
GA4_PROPERTY_ID = "539262453"  # vishigondi/trinity-local GA4 property


def _default_endpoint() -> str | None:
    """Resolve the telemetry endpoint.

    Lookup order:
      1. `TRINITY_TELEMETRY_ENDPOINT` env (escape hatch for custom collectors)
      2. The GA4 Measurement Protocol endpoint (the default)

    The GA4 path requires `TRINITY_GA4_MEASUREMENT_ID` + `TRINITY_GA4_API_SECRET`
    in env. When either is missing, `_send_event_to_ga4` no-ops silently —
    we never block on telemetry, and we never error out a real CLI flow.
    """
    return os.environ.get("TRINITY_TELEMETRY_ENDPOINT") or GA4_ENDPOINT


def load_telemetry_settings() -> TelemetrySettings:
    path = telemetry_settings_path()
    if not path.exists():
        return TelemetrySettings(endpoint=_default_endpoint())
    raw = json.loads(path.read_text(encoding="utf-8"))
    known_fields = {f.name for f in fields(TelemetrySettings)}
    settings = TelemetrySettings(**{k: v for k, v in raw.items() if k in known_fields})
    if not settings.endpoint:
        settings.endpoint = _default_endpoint()
    return settings


def save_telemetry_settings(settings: TelemetrySettings) -> Path:
    from .utils import atomic_write_text
    path = telemetry_settings_path()
    atomic_write_text(path, json.dumps(settings.to_dict(), indent=2))
    return path


def ensure_share_install_id(settings: TelemetrySettings) -> TelemetrySettings:
    if settings.share_install_id:
        return settings
    settings.share_install_id = f"share_{secrets.token_hex(8)}"
    return settings


def enable_telemetry(
    *,
    endpoint: str | None = None,
    share_usage_events: bool = True,
    share_elo_summaries: bool = True,
) -> TelemetrySettings:
    settings = load_telemetry_settings()
    ensure_share_install_id(settings)
    settings.sharing_enabled = True
    settings.share_usage_events = share_usage_events
    settings.share_elo_summaries = share_elo_summaries
    settings.endpoint = endpoint or settings.endpoint or _default_endpoint()
    settings.consented_at = settings.consented_at or now_iso()
    save_telemetry_settings(settings)
    return settings


def disable_telemetry() -> TelemetrySettings:
    settings = load_telemetry_settings()
    settings.sharing_enabled = False
    save_telemetry_settings(settings)
    return settings


def reset_share_install_id() -> TelemetrySettings:
    settings = load_telemetry_settings()
    settings.share_install_id = f"share_{secrets.token_hex(8)}"
    settings.last_elo_hash = None
    settings.last_view_upload_at = None
    settings.last_elo_upload_at = None
    save_telemetry_settings(settings)
    return settings


def _iter_council_payloads() -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for path in council_outcomes_dir().glob("*.json"):
        try:
            records.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return records


def build_elo_snapshot(window: str = "all_time") -> dict[str, Any]:
    """Build a lightweight local Elo summary from saved councils.

    This is intentionally simple: each recorded council winner gets a head-to-head
    win against the other participants in that council.
    """
    base = 1500.0
    k = 24.0
    ratings: dict[str, float] = {}
    matchups: dict[str, dict[str, int]] = {}
    provider_stats: dict[str, dict[str, int]] = {}
    council_count = 0
    feedback_by_council = latest_feedback_by_council()

    for raw in _iter_council_payloads():
        council_id = raw.get("council_run_id") or ""
        members = [
            item.get("provider")
            for item in raw.get("member_results", [])
            if isinstance(item, dict) and item.get("provider")
        ]
        unique_members = list(dict.fromkeys(members))
        feedback = feedback_by_council.get(council_id, {})
        winner = feedback.get("provider") or raw.get("winner_provider")
        if not winner or winner not in unique_members or len(unique_members) < 2:
            continue
        council_count += 1
        for provider in unique_members:
            ratings.setdefault(provider, base)
            stats = provider_stats.setdefault(provider, {"wins": 0, "total_games": 0})
            stats["total_games"] += 1
        provider_stats[winner]["wins"] += 1

        for loser in unique_members:
            if loser == winner:
                continue
            ratings.setdefault(loser, base)
            expected_winner = 1.0 / (1.0 + 10 ** ((ratings[loser] - ratings[winner]) / 400.0))
            expected_loser = 1.0 - expected_winner
            ratings[winner] += k * (1.0 - expected_winner)
            ratings[loser] += k * (0.0 - expected_loser)

            pair_key = "_vs_".join(sorted((winner, loser)))
            pair = matchups.setdefault(pair_key, {})
            pair[f"{winner}_wins"] = pair.get(f"{winner}_wins", 0) + 1

    providers = {}
    for provider, score in sorted(ratings.items()):
        stats = provider_stats.get(provider, {"wins": 0, "total_games": 0})
        total_games = stats.get("total_games", 0)
        wins = stats.get("wins", 0)
        win_rate = (wins / total_games * 100.0) if total_games else 0.0
        providers[provider] = {
            "elo": int(round(score)),
            "wins": wins,
            "total_games": total_games,
            "win_rate": round(win_rate, 1),
            "consistency": round(win_rate, 1) if total_games else 50.0,
        }

    return {
        "version": TELEMETRY_VERSION,
        "window": window,
        "council_count": council_count,
        "providers": providers,
        "matchups": matchups,
    }


def elo_snapshot_hash(snapshot: dict[str, Any]) -> str:
    payload = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    return "sha1:" + hashlib.sha1(payload.encode("utf-8")).hexdigest()


def build_launchpad_view_event(
    *,
    settings: TelemetrySettings | None = None,
    app_version: str = "0.1.0",
) -> dict[str, Any]:
    settings = settings or load_telemetry_settings()
    if settings.sharing_enabled:
        ensure_share_install_id(settings)
    return {
        "event": "launchpad_view",
        "version": TELEMETRY_VERSION,
        "share_install_id": settings.share_install_id or "",
        "app_version": app_version,
        "timestamp": now_iso(),
        "surface": "launchpad",
        "council_count_bucket": _bucket_council_count(build_elo_snapshot()["council_count"]),
        "provider_count": len(build_elo_snapshot()["providers"]),
    }


def build_elo_snapshot_event(
    *,
    settings: TelemetrySettings | None = None,
    app_version: str = "0.1.0",
) -> dict[str, Any]:
    settings = settings or load_telemetry_settings()
    if settings.sharing_enabled:
        ensure_share_install_id(settings)
    snapshot = build_elo_snapshot()
    return {
        "event": "elo_snapshot",
        "version": TELEMETRY_VERSION,
        "share_install_id": settings.share_install_id or "",
        "app_version": app_version,
        "timestamp": now_iso(),
        **snapshot,
    }


def _bucket_council_count(value: int) -> str:
    if value <= 0:
        return "0"
    if value < 10:
        return "1-9"
    if value < 50:
        return "10-49"
    return "50+"


def _browser_send_enabled() -> bool:
    """Whether the browser launchpad is allowed to POST telemetry (#231c).

    Gated on the SAME credential guarantee as the Python path: a custom
    collector endpoint, or GA4 measurement creds. Absent both, the Python
    `_send_event_to_ga4` no-ops — so the browser MUST no-op too, or it
    becomes a bypass that sends events the CLI suppressed. We enforce that
    by withholding `endpoint` from pageData (see `launchpad_telemetry_state`),
    which short-circuits the browser's `maybeSendTelemetry()`.
    """
    if os.environ.get("TRINITY_TELEMETRY_ENDPOINT", "").strip():
        return True
    return _ga4_credentials() is not None


def _browser_endpoint() -> str | None:
    """The endpoint string the browser POSTs to, or None when sends aren't
    credential-enabled. A custom collector is used verbatim; GA4 needs its
    measurement_id + api_secret in the query string (the browser has no
    other channel to authenticate)."""
    custom = os.environ.get("TRINITY_TELEMETRY_ENDPOINT", "").strip()
    if custom:
        return custom
    creds = _ga4_credentials()
    if creds is None:
        return None
    measurement_id, api_secret = creds
    return f"{GA4_ENDPOINT}?measurement_id={measurement_id}&api_secret={api_secret}"


def launchpad_telemetry_state() -> dict[str, Any]:
    settings = load_telemetry_settings()
    if settings.sharing_enabled:
        ensure_share_install_id(settings)
    snapshot = build_elo_snapshot()
    # Close the browser-bypass (#231c): only expose a usable `endpoint` when
    # sends are credential-enabled. Without it, the browser's
    # maybeSendTelemetry() returns early — it can't transmit what the Python
    # path would suppress. The default GA4 collect URL (no creds) is NOT a
    # usable endpoint and must never reach pageData.
    settings_dict = settings.to_dict()
    browser_endpoint = _browser_endpoint()
    if browser_endpoint:
        settings_dict["endpoint"] = browser_endpoint
    else:
        settings_dict.pop("endpoint", None)
    return {
        "settings": settings_dict,
        "snapshot": snapshot,
        "snapshot_hash": elo_snapshot_hash(snapshot),
        "view_event": build_launchpad_view_event(settings=settings),
        "elo_event": build_elo_snapshot_event(settings=settings),
    }


# ─── GA4 Measurement Protocol ───────────────────────────────────────────
#
# Trinity sends categorical routing labels + install/usage events to GA4
# property 539262453 when the user has opted in. This is the only outbound
# data Trinity emits. Per CLAUDE.md "Architectural commitments" #2:
# NO prompt content, NO lens text, NO user_substitute strings — only the
# categorical labels (task_type, winner, provider_scores keys).
#
# Implementation:
#   - Fire-and-forget via a daemon thread so the CLI flow never blocks.
#   - Silent no-op when measurement_id + api_secret env vars are missing
#     (lets contributors run Trinity without GA4 credentials).
#   - Best-effort: HTTP failures are swallowed; telemetry must never
#     fail-open into a user-visible error.

def _ga4_credentials() -> tuple[str, str] | None:
    """Return (measurement_id, api_secret) when both env vars are set,
    else None (causes silent no-op).

    Measurement ID format is `G-XXXXXXXXXX` (not the numeric property
    ID — different field in GA4 admin). API secret is created at
    Admin → Data Streams → Web → Measurement Protocol API secrets.
    """
    measurement_id = os.environ.get("TRINITY_GA4_MEASUREMENT_ID", "").strip()
    api_secret = os.environ.get("TRINITY_GA4_API_SECRET", "").strip()
    if not measurement_id or not api_secret:
        return None
    return measurement_id, api_secret


def _send_event_to_ga4(
    event_name: str,
    params: dict[str, Any],
    *,
    settings: TelemetrySettings | None = None,
    blocking: bool = False,
) -> bool:
    """Fire-and-forget GA4 Measurement Protocol POST.

    Returns True when the event was queued for send, False when it
    was suppressed (telemetry disabled / no credentials / load error).
    The actual HTTP call runs in a background daemon thread so the
    caller never waits — set ``blocking=True`` only in tests.

    Args:
      event_name: GA4 event name (e.g. "council_complete"). Must match
        GA4's naming rules: snake_case, ≤40 chars.
      params: Categorical event params only. Keys snake_case ≤40 chars.
        Values must be primitives (str/int/float/bool). NO prompt content,
        NO lens text — only routing labels per CLAUDE.md commitment #2.
      settings: Optional TelemetrySettings; loads from disk when None.
      blocking: When True, run the POST inline (test-only).
    """
    settings = settings or load_telemetry_settings()
    if not settings.sharing_enabled or not settings.share_usage_events:
        return False
    creds = _ga4_credentials()
    if creds is None:
        return False
    measurement_id, api_secret = creds

    # GA4 requires a stable client_id — reuse share_install_id when present.
    if not settings.share_install_id:
        settings = ensure_share_install_id(settings)
        save_telemetry_settings(settings)

    # Enforce the disclosed-param allowlist at the wire boundary (#231a) —
    # NOT a bare dict(params) — so an upstream caller can't leak free text.
    payload = {
        "client_id": settings.share_install_id,
        **build_outbound_event_payload(event_name, params),
    }
    body = json.dumps(payload).encode("utf-8")
    url = f"{GA4_ENDPOINT}?measurement_id={measurement_id}&api_secret={api_secret}"

    def _post() -> None:
        import urllib.error
        import urllib.request
        try:
            req = urllib.request.Request(
                url,
                data=body,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                resp.read()
        except (urllib.error.URLError, OSError, TimeoutError):
            # Telemetry must never error out a real flow. Drop the event.
            pass

    if blocking:
        _post()
    else:
        import threading
        threading.Thread(target=_post, daemon=True).start()
    return True


def record_event(event_name: str, **params: Any) -> bool:
    """Public entry point — top-level callers invoke this.

    Wraps `_send_event_to_ga4` with the live settings load. Returns
    True when fired, False when suppressed (opt-out, no creds, etc.).

    Example:
        record_event(
            "council_complete",
            task_type="design",
            winner="claude",
            member_count=3,
        )

    Keep params categorical — task_type, winner, provider, harness,
    council_count_bucket. NEVER pass prompt text, lens content, or
    user_substitute strings.
    """
    return _send_event_to_ga4(event_name, params)
