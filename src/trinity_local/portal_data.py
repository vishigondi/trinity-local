from __future__ import annotations

import html
import json
from pathlib import Path
from urllib.parse import quote

from .adapters import check_all_adapters
from .config import load_config
from .council_runtime import load_prompt_bundle
from .council_status import load_council_status
from .dispatch_registry import make_dispatch_action
from .global_benchmarks import get_global_benchmarks, get_reference_evals_meta
from .shortcuts_integration import DEFAULT_SHORTCUT_NAME, make_shortcut_invocation
from .state_paths import council_outcomes_dir, council_status_dir, review_pages_dir
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
    """Group council outcomes into threads (one card per chain_root_id).

    A "thread" here is the sequence of refine/continue/auto-chain rounds
    rooted at one initial question. The card title comes from the root
    round's prompt, the meta line shows the LATEST round's winner and
    timestamp, and the link points at `live_council.html?thread_id=<root>`
    so opening the card reveals every round on one scrollable page.
    """
    threads: dict[str, dict] = {}
    for path in council_outcomes_dir().glob("council_*.json"):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        council_id = raw.get("council_run_id") or path.stem
        metadata = raw.get("metadata") or {}
        bundle_id = raw.get("bundle_id")
        # bundle_id is the canonical chain root identifier — it's allocated
        # at launch time and stays stable across all rounds in a chain. The
        # thread manifest, pending registration, and ?thread_id= URLs all
        # key off it. Falling back to council_id only matters for very old
        # outcomes that predate the manifest writer.
        chain_root_id = metadata.get("chain_root_id") or bundle_id or council_id
        round_number = int(metadata.get("round_number") or 1)
        created_at = str(raw.get("created_at") or "")
        bundle_id = raw.get("bundle_id")

        thread = threads.setdefault(
            chain_root_id,
            {
                "chain_root_id": chain_root_id,
                "segment_count": 0,
                "root_bundle_id": None,
                "root_title": None,
                "latest_winner": None,
                "latest_created_at": "",
            },
        )
        thread["segment_count"] += 1
        # Earliest round = round_number 1 (or smallest round_number) carries
        # the original prompt for the title.
        if round_number == 1 or thread["root_bundle_id"] is None:
            thread["root_bundle_id"] = bundle_id
            thread["root_council_id"] = council_id
        # Latest round drives meta line.
        if created_at >= thread["latest_created_at"]:
            thread["latest_created_at"] = created_at
            thread["latest_winner"] = raw.get("winner_provider")

    items: list[dict[str, str | None]] = []
    for thread in threads.values():
        prompt = "[Council prompt unavailable]"
        if thread["root_bundle_id"]:
            try:
                bundle = load_prompt_bundle(thread["root_bundle_id"])
                prompt = bundle.task_text.strip() or prompt
            except Exception:
                pass
        items.append(
            {
                "council_id": thread.get("root_council_id") or thread["chain_root_id"],
                "chain_root_id": thread["chain_root_id"],
                "bundle_id": thread["root_bundle_id"],
                "title": _truncate(prompt),
                "winner_provider": thread["latest_winner"],
                "created_at": thread["latest_created_at"],
                "segment_count": thread["segment_count"],
                "review_page_path": str(
                    (review_pages_dir() / "live_council.html").resolve()
                ),
            }
        )
    items.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return items[:limit]


def _normalize_council_query(text: str) -> str:
    return " ".join(text.split()).strip().lower()


def _load_council_query_suggestions_fallback(limit: int = 8) -> list[str]:
    """Strings-only fallback when memory.search_prompt_nodes returns nothing.

    Pulls from past council outcomes + hard-coded EXAMPLE_PROMPTS. Same shape
    as before the autofill rewire so empty memory still shows useful suggestions.
    """
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


def _load_replay_candidates(limit: int = 200) -> list:
    """Memory-backed autofill candidates ranked by replay_value_score.

    Returns a list of dicts with shape:
        {"text": str, "reasons": list[str], "score": float,
         "council_count": int, "winner": str | None, "prompt_id": str}

    Falls back to the string list from _load_council_query_suggestions_fallback
    when the memory index is empty (cold start). Template handles either shape.
    """
    try:
        from .memory import search_prompt_nodes

        results = search_prompt_nodes("", top_k=limit)
    except Exception:
        results = []

    if not results:
        return _load_council_query_suggestions_fallback(limit=8)

    candidates: list[dict] = []
    for hit in results:
        text = (hit.text or "").strip()
        if len(text) < 8:
            continue
        prior = (hit.preceding_assistant_text or "").strip()
        # Truncate prior assistant excerpt for the visible preview; the full
        # text up to the budget is sent through to the council bundle on
        # apply (see thread_context.build_threaded_prompt).
        prior_preview = prior[:240] + ("…" if len(prior) > 240 else "")
        candidates.append({
            "text": text,
            "reasons": list(hit.reasons or []),
            "score": float(hit.score or 0.0),
            "council_count": int(hit.council_count or 0),
            "winner": hit.user_winner or hit.chairman_winner or None,
            "prompt_id": hit.prompt_id or "",
            "priorAssistantText": prior,
            "priorAssistantPreview": prior_preview,
            "transcriptId": hit.transcript_id or "",
            "turnIndex": int(hit.turn_index or 0),
        })
    return candidates


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
        if status.installed:
            continue
        label, install_command = _provider_install_help(status.provider)
        detail_parts: list[str] = []
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
        status_token = path.stem.replace("council_status_", "", 1)
        raw = load_council_status(status_token)
        if raw is None:
            continue
        if raw.get("status") != "running":
            continue
        metadata = dict(raw.get("metadata") or {})
        kind = metadata.get("kind") or "council"
        candidates.append(
            {
                "statusToken": raw.get("status_token") or status_token,
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
    auto_chain_enable = make_shortcut_invocation(
        dispatch=make_dispatch_action(
            "run_command",
            args={"command": "trinity-local auto-chain-enable"},
            metadata={"kind": "auto_chain_enable"},
        ),
        shortcut_name=DEFAULT_SHORTCUT_NAME,
    )
    auto_chain_disable = make_shortcut_invocation(
        dispatch=make_dispatch_action(
            "run_command",
            args={"command": "trinity-local auto-chain-disable"},
            metadata={"kind": "auto_chain_disable"},
        ),
        shortcut_name=DEFAULT_SHORTCUT_NAME,
    )
    return {
        "enable": enable.url,
        "disable": disable.url,
        "reset": reset.url,
        "autoChainEnable": auto_chain_enable.url,
        "autoChainDisable": auto_chain_disable.url,
    }


def _load_personal_routing_table() -> dict | None:
    """Compute the personal routing table on demand from council_outcomes/.

    Returns None when no councils have been rated yet so the launchpad shows
    the empty-state CTA. The single source of truth is the council_outcomes
    directory; aggregation is cached in-process by directory mtime.
    """
    from .personal_routing import compute_personal_routing_table

    try:
        table = compute_personal_routing_table()
    except Exception:
        return None
    if not table.get("by_task_type"):
        return None
    return table


def build_page_data(
    *,
    live_review_path: Path,
    recent_councils: list[dict[str, str | None]],
) -> dict:
    telemetry = launchpad_telemetry_state()
    elo_snapshot = build_elo_snapshot()
    chart_data = _elo_chart_data(elo_snapshot)
    council_suggestions = _load_replay_candidates(limit=200)
    settings_links = _settings_links()
    global_benchmarks = get_global_benchmarks()
    provider_health = _provider_health_data()
    active_operation = _active_launchpad_operation()
    personal_routing = _load_personal_routing_table()
    benchmark_providers = list(next(iter(global_benchmarks.values()))["models"].keys()) if global_benchmarks else []
    # Map provider name -> configured model id, for header annotations on the
    # ratings/benchmarks card. Reads from config.json so it tracks whatever
    # the user is actually running.
    provider_models: dict[str, str] = {}
    try:
        cfg = load_config(required=False)
        for name, provider in cfg.providers.items():
            if provider.model:
                provider_models[name] = provider.model
    except Exception:
        provider_models = {}
    return {
        "shortcutName": DEFAULT_SHORTCUT_NAME,
        "councilSuggestions": council_suggestions,
        "defaultGoal": "Find the strongest answer.",
        "defaultMembers": ["claude", "gemini", "codex"],
        "defaultPrimaryProvider": None,
        "telemetry": telemetry,
        "settingsLinks": settings_links,
        "providerHealth": provider_health,
        "eloChart": chart_data,
        "globalBenchmarks": global_benchmarks,
        "benchmarkProviders": benchmark_providers,
        "providerModels": provider_models,
        "referenceEvalsMeta": get_reference_evals_meta(),
        "liveReviewUrl": f"file://{live_review_path}",
        "activeOperation": active_operation,
        "statusScriptBaseUrl": "file://" + quote(str(council_status_dir().resolve())),
        "councilLoadingMessages": COUNCIL_LOADING_MESSAGES,
        "personalRoutingTable": personal_routing,
        "tasteLenses": _load_taste_lenses(),
    }


def _load_taste_lenses() -> dict | None:
    """Parse ~/.trinity/me.md into shareable taste lenses for the launchpad.

    Returns the structured dict (rejections / vocabulary / abstract_lenses)
    or None when /me hasn't been built yet — the launchpad shows an
    empty-state CTA pointing at `trinity-local me-build`.
    """
    from .me_lenses import parse_taste_lenses

    try:
        lenses = parse_taste_lenses()
    except Exception:
        return None
    if lenses.is_empty:
        return None
    return lenses.to_dict()


def build_recent_cards_html(recent_councils: list[dict[str, str | None]]) -> str:
    def _card(item: dict[str, str | None]) -> str:
        thread_id = item.get("chain_root_id") or item.get("council_id")
        review_path = item.get("review_page_path")
        if not review_path or not thread_id:
            return ""
        href = f"file://{_esc(str(review_path))}?thread_id={_esc(str(thread_id))}"
        winner = (item.get("winner_provider") or "No winner yet").replace("_", " ").title()
        created_at = item.get("created_at") or "unknown"
        seg_count = int(item.get("segment_count") or 1)
        rounds_badge = (
            f' · <span style="opacity: 0.7;">{seg_count} rounds</span>'
            if seg_count > 1
            else ""
        )
        return f"""
        <div style="display: flex; flex-direction: column; gap: 12px;">
          <a href="{href}" style="text-decoration: none; cursor: pointer;" class="council-card-link">
            <article class="card council-card">
              <div class="eyebrow">Thread</div>
              <h3 class="council-title">{_esc(str(item['title']))}</h3>
              <p class="meta">{_esc(winner)} · {_esc(created_at)}{rounds_badge}</p>
            </article>
          </a>
        </div>
        """

    cards = "".join(_card(item) for item in recent_councils)
    return cards or '<p class="meta">No councils yet. Launch one above to get started.</p>'
