from __future__ import annotations

import html
import json
from pathlib import Path
from urllib.parse import quote

from .adapters import check_all_adapters
from .council_runtime import load_prompt_bundle
from .council_status import council_status_dir
from .daemon_manager import daemon_status
from .dispatch_registry import make_dispatch_action
from .global_benchmarks import get_global_benchmarks
from .shortcuts_integration import DEFAULT_SHORTCUT_NAME, make_shortcut_invocation
from .state_paths import council_outcomes_dir, review_pages_dir
from .telemetry import build_elo_snapshot, launchpad_telemetry_state

EXAMPLE_PROMPTS = [
    "Write a launch announcement for Trinity Local",
    "Research this company: [company name]",
    "Draft a product specification",
    "Plan an onboarding email sequence",
    "Debug this error: [error message]",
    "Explain this concept",
    "Write a technical blog post outline",
    "Create a project proposal",
]

COUNCIL_LOADING_MESSAGES = [
    "Reticulating splines...",
    "Generating witty dialog...",
    "Tokenizing real life...",
    "Convincing AI not to turn evil...",
    "Computing chance of success...",
    "Optimizing the optimizer...",
    "Keeping all the 1's and removing all the 0's...",
    "Pushing pixels...",
]


def _esc(value: str | None) -> str:
    return html.escape(value or "")


def _truncate(text: str, length: int = 88) -> str:
    if len(text) <= length:
        return text
    return text[:length].rstrip() + "…"


def _load_recent_councils(limit: int = 10) -> list[dict[str, str | None]]:
    items: list[dict[str, str | None]] = []
    for path in council_outcomes_dir().glob("*.json"):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        bundle_id = raw.get("bundle_id")
        prompt = "[Council prompt unavailable]"
        if bundle_id:
            try:
                bundle = load_prompt_bundle(bundle_id)
                prompt = bundle.task_text.strip() or prompt
            except Exception:
                pass
        council_id = raw.get("council_run_id") or path.stem
        items.append(
            {
                "council_id": council_id,
                "bundle_id": bundle_id,
                "title": _truncate(prompt),
                "winner_provider": raw.get("winner_provider"),
                "created_at": raw.get("created_at"),
                "review_page_path": str((review_pages_dir() / f"{council_id}.html").resolve()),
            }
        )
    items.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return items[:limit]


def _normalize_council_query(text: str) -> str:
    return " ".join(text.split()).strip().lower()


def _load_council_query_suggestions(limit: int = 8) -> list[str]:
    ranked: dict[str, dict[str, object]] = {}
    for path in council_outcomes_dir().glob("*.json"):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        bundle_id = raw.get("bundle_id")
        if not bundle_id:
            continue
        try:
            bundle = load_prompt_bundle(bundle_id)
        except Exception:
            continue
        prompt = (bundle.task_text or "").strip()
        if len(prompt) < 8:
            continue
        key = _normalize_council_query(prompt)
        if not key:
            continue
        created_at = str(raw.get("created_at") or bundle.created_at or "")
        entry = ranked.setdefault(
            key,
            {"prompt": prompt, "count": 0, "latest": created_at},
        )
        entry["count"] = int(entry.get("count", 0)) + 1
        if created_at >= str(entry.get("latest") or ""):
            entry["latest"] = created_at
            entry["prompt"] = prompt

    ordered = sorted(
        ranked.values(),
        key=lambda item: (int(item["count"]), str(item["latest"]), str(item["prompt"]).lower()),
        reverse=True,
    )
    suggestions = [str(item["prompt"]) for item in ordered[:limit]]

    existing = {_normalize_council_query(item) for item in suggestions}
    for prompt in EXAMPLE_PROMPTS:
        key = _normalize_council_query(prompt)
        if key in existing:
            continue
        suggestions.append(prompt)
        existing.add(key)
        if len(suggestions) >= limit:
            break
    return suggestions[:limit]


def _daemon_launchpad_state() -> dict[str, object]:
    success, message = daemon_status()
    normalized = message.lower()
    return {
        "success": success,
        "message": message,
        "running": "running" in normalized and "not running" not in normalized,
        "installed": "not installed" not in normalized,
    }


def _provider_install_help(provider: str) -> tuple[str, str]:
    if provider == "claude":
        return ("Claude Code", "npm install -g @anthropic-ai/claude-code")
    if provider == "codex":
        return ("Codex CLI", "npm install -g @openai/codex && codex --login")
    if provider == "gemini":
        return ("Gemini CLI", "npm install -g @google/gemini-cli && gemini")
    if provider == "cowork":
        return ("Cowork / Claude Desktop", "Install Claude Desktop, then open Local Agent Mode once.")
    pretty = provider.replace("_", " ").title()
    return (pretty, f"Install {pretty} and rerun Trinity.")


def _provider_health_data() -> dict[str, object]:
    statuses = check_all_adapters()
    providers: list[dict[str, object]] = []
    missing_count = 0
    for status in statuses:
        label, install_command = _provider_install_help(status.provider)
        detail_parts: list[str] = []
        if status.version:
            detail_parts.append(status.version)
        if status.transcript_count:
            detail_parts.append(f"{status.transcript_count} transcripts")
        elif status.installed:
            detail_parts.append("No transcripts yet")
        if status.error and not status.installed:
            detail_parts.append(status.error)
        providers.append(
            {
                "provider": status.provider,
                "label": label,
                "installed": status.installed,
                "detail": " · ".join(detail_parts),
                "installCommand": install_command,
            }
        )
        if not status.installed:
            missing_count += 1
    return {
        "providers": providers,
        "missingCount": missing_count,
        "hasMissing": missing_count > 0,
        "footerNote": "After installing, open a new terminal and run `trinity-local status`. Trinity will pick up newly installed providers automatically.",
    }


def _active_launchpad_operation() -> dict[str, object] | None:
    candidates: list[dict[str, object]] = []
    for path in council_status_dir().glob("council_status_*.json"):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if raw.get("status") != "running":
            continue
        metadata = dict(raw.get("metadata") or {})
        kind = metadata.get("kind") or "council"
        candidates.append(
            {
                "statusToken": raw.get("status_token") or path.stem.replace("council_status_", "", 1),
                "kind": kind,
                "status": raw.get("status") or "running",
                "label": raw.get("task_text") or ("Scan recent transcripts once" if kind == "ingest" else "Council"),
                "memberOrder": list(metadata.get("members") or list((raw.get("members") or {}).keys()) or ["claude", "gemini", "codex"]),
                "members": dict(raw.get("members") or {}),
                "activeProvider": raw.get("active_provider"),
                "activeProviders": list(raw.get("active_providers") or []),
                "synthesis": dict(raw.get("synthesis") or {}),
                "reviewPath": raw.get("review_path") or "",
                "error": raw.get("error") or "",
                "updatedAt": raw.get("updated_at") or "",
            }
        )
    if not candidates:
        return None
    candidates.sort(key=lambda item: str(item.get("updatedAt") or ""), reverse=True)
    return candidates[0]


def _elo_chart_data(snapshot: dict) -> dict:
    providers = snapshot.get("providers", {})
    labels = [provider.title() for provider in providers.keys()]
    values = [provider_data.get("elo", 1500) for provider_data in providers.values()]
    return {
        "labels": labels,
        "datasets": [
            {
                "label": "Your Trinity rating",
                "data": values,
                "backgroundColor": "rgba(37, 88, 71, 0.18)",
                "borderColor": "#255847",
                "borderWidth": 2,
                "borderRadius": 10,
            }
        ],
    }


def _settings_links() -> dict[str, str]:
    enable = make_shortcut_invocation(
        dispatch=make_dispatch_action(
            "run_command",
            args={"command": "trinity-local telemetry-enable"},
            metadata={"kind": "telemetry_enable"},
        ),
        shortcut_name=DEFAULT_SHORTCUT_NAME,
    )
    disable = make_shortcut_invocation(
        dispatch=make_dispatch_action(
            "run_command",
            args={"command": "trinity-local telemetry-disable"},
            metadata={"kind": "telemetry_disable"},
        ),
        shortcut_name=DEFAULT_SHORTCUT_NAME,
    )
    reset = make_shortcut_invocation(
        dispatch=make_dispatch_action(
            "run_command",
            args={"command": "trinity-local telemetry-reset-id"},
            metadata={"kind": "telemetry_reset"},
        ),
        shortcut_name=DEFAULT_SHORTCUT_NAME,
    )
    auto_ingest_enable = make_shortcut_invocation(
        dispatch=make_dispatch_action(
            "run_command",
            args={"command": "trinity-local auto-ingest-enable"},
            metadata={"kind": "auto_ingest_enable"},
        ),
        shortcut_name=DEFAULT_SHORTCUT_NAME,
    )
    auto_ingest_disable = make_shortcut_invocation(
        dispatch=make_dispatch_action(
            "run_command",
            args={"command": "trinity-local auto-ingest-disable"},
            metadata={"kind": "auto_ingest_disable"},
        ),
        shortcut_name=DEFAULT_SHORTCUT_NAME,
    )
    return {
        "enable": enable.url,
        "disable": disable.url,
        "reset": reset.url,
        "autoIngestEnable": auto_ingest_enable.url,
        "autoIngestDisable": auto_ingest_disable.url,
    }


def build_page_data(
    *,
    launchpad_path: Path,
    live_review_path: Path,
    recent_councils: list[dict[str, str | None]],
) -> dict:
    telemetry = launchpad_telemetry_state()
    elo_snapshot = build_elo_snapshot()
    chart_data = _elo_chart_data(elo_snapshot)
    council_suggestions = _load_council_query_suggestions(limit=8)
    settings_links = _settings_links()
    global_benchmarks = get_global_benchmarks()
    daemon_state = _daemon_launchpad_state()
    provider_health = _provider_health_data()
    active_operation = _active_launchpad_operation()
    benchmark_providers = list(next(iter(global_benchmarks.values()))["models"].keys()) if global_benchmarks else []
    return {
        "shortcutName": DEFAULT_SHORTCUT_NAME,
        "councilSuggestions": council_suggestions,
        "defaultGoal": "Find the strongest answer.",
        "defaultMembers": ["claude", "gemini", "codex"],
        "defaultIngestSources": ["cowork", "claude", "gemini", "codex"],
        "defaultPrimaryProvider": "claude",
        "recentCouncils": recent_councils,
        "telemetry": telemetry,
        "settingsLinks": settings_links,
        "daemon": daemon_state,
        "providerHealth": provider_health,
        "eloChart": chart_data,
        "globalBenchmarks": global_benchmarks,
        "benchmarkProviders": benchmark_providers,
        "launchpadUrl": f"file://{launchpad_path}",
        "liveReviewUrl": f"file://{live_review_path}",
        "activeOperation": active_operation,
        "statusScriptBaseUrl": "file://" + quote(str(council_status_dir().resolve())),
        "councilLoadingMessages": COUNCIL_LOADING_MESSAGES,
    }


def build_recent_cards_html(recent_councils: list[dict[str, str | None]]) -> str:
    return "".join(
        f"""
        <div style="display: flex; flex-direction: column; gap: 12px;">
          <a href="file://{_esc(item['review_page_path'])}" style="text-decoration: none; cursor: pointer;" class="council-card-link">
            <article class="card council-card">
              <div class="eyebrow">Council</div>
              <h3 class="council-title">{_esc(str(item['title']))}</h3>
              <p class="meta">{_esc((item.get('winner_provider') or 'No winner yet').replace('_', ' ').title())} · {_esc(item.get('created_at') or 'unknown')}</p>
            </article>
          </a>
        </div>
        """
        for item in recent_councils
        if item.get('review_page_path')
    ) or '<p class="meta">No councils yet. Launch one above to get started.</p>'
