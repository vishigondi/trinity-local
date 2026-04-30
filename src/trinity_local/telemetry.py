from __future__ import annotations

import hashlib
import json
import os
import secrets
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .council_feedback import latest_feedback_by_council
from .council_runtime import council_outcomes_dir
from .state_paths import state_dir, telemetry_settings_dir, analytics_dir
from .utils import now_iso


TELEMETRY_VERSION = 1


@dataclass
class TelemetrySettings:
    sharing_enabled: bool = False
    share_usage_events: bool = False
    share_elo_summaries: bool = False
    share_install_id: str = ""
    endpoint: str | None = None
    consented_at: str | None = None
    last_view_upload_at: str | None = None
    last_elo_upload_at: str | None = None
    last_elo_hash: str | None = None
    last_upload_status: str | None = None
    auto_ingest_transcript: bool = False

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return {k: v for k, v in payload.items() if v not in ("", None, [], {})}


def telemetry_settings_path() -> Path:
    return telemetry_settings_dir() / "telemetry.json"


def telemetry_events_path() -> Path:
    path = analytics_dir() / "telemetry_events.jsonl"
    return path


def _default_endpoint() -> str | None:
    return os.environ.get("TRINITY_TELEMETRY_ENDPOINT")


def load_telemetry_settings() -> TelemetrySettings:
    path = telemetry_settings_path()
    if not path.exists():
        return TelemetrySettings(endpoint=_default_endpoint())
    raw = json.loads(path.read_text(encoding="utf-8"))
    settings = TelemetrySettings(**raw)
    if not settings.endpoint:
        settings.endpoint = _default_endpoint()
    return settings


def save_telemetry_settings(settings: TelemetrySettings) -> Path:
    path = telemetry_settings_path()
    path.write_text(json.dumps(settings.to_dict(), indent=2), encoding="utf-8")
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


def append_telemetry_event(event: dict[str, Any]) -> None:
    with telemetry_events_path().open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(event) + "\n")


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


def launchpad_telemetry_state() -> dict[str, Any]:
    settings = load_telemetry_settings()
    if settings.sharing_enabled:
        ensure_share_install_id(settings)
    snapshot = build_elo_snapshot()
    return {
        "settings": settings.to_dict(),
        "snapshot": snapshot,
        "snapshot_hash": elo_snapshot_hash(snapshot),
        "view_event": build_launchpad_view_event(settings=settings),
        "elo_event": build_elo_snapshot_event(settings=settings),
    }
