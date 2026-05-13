from __future__ import annotations

import html
import json
from pathlib import Path

from .adapters import check_all_adapters
from .categories import (
    DEFAULT_CATEGORY_FOR_UNKNOWN_TASK_KIND,
    category_keys as _category_keys,
    category_labels as _category_labels,
    task_kind_to_category as _task_kind_to_category,
)
from .config import load_config
from .council_runtime import load_prompt_bundle
from .council_status import load_council_status
from .dispatch_registry import make_dispatch_action
from .global_benchmarks import get_global_benchmarks, get_reference_evals_meta
from .shortcuts_integration import DEFAULT_SHORTCUT_NAME, make_shortcut_invocation
from .state_paths import council_outcomes_dir, council_status_dir, review_pages_dir
from .telemetry import build_elo_snapshot, launchpad_telemetry_state
from .utils import now_iso

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


# Centroid-similarity threshold for the picks↔topology bridge. A pick
# is considered to map onto a topology basin only when their nomic
# centroids share ≥ this cosine similarity. Empirical: 0.5 was too
# lax (oranges mapped to apples), 0.8 too strict (real matches dropped).
# Single source of truth — the JS helper in memory_viewer.py reads
# this same value via render-time injection, so the launchpad-side
# Python match and the in-viewer JS match can't drift.
BASIN_SIM_THRESHOLD = 0.65


def _esc(value: str | None) -> str:
    return html.escape(value or "")


def _strip_thread_context(text: str) -> str:
    """When the prompt was built by thread_context.build_threaded_prompt, the
    actual user question lives after a "Current user message:\n" marker. The
    preceding block is prior-assistant context that humans don't want as the
    card title. Strip it for display.
    """
    marker = "Current user message:\n"
    idx = text.find(marker)
    if idx >= 0:
        return text[idx + len(marker):].strip()
    return text


def _truncate(text: str, length: int = 88) -> str:
    """Truncate at the nearest word boundary so titles don't end mid-word
    like "or p…" or "the output a…". Falls back to hard cut only if the
    text contains no spaces in the budget window (rare, single long token).
    """
    text = _strip_thread_context(text)
    if len(text) <= length:
        return text
    cut = text[:length]
    last_space = cut.rfind(" ")
    if last_space >= length // 2:
        cut = cut[:last_space]
    return cut.rstrip(" ,.;:!?-—") + "…"


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
                # task_type pulled from the latest round's routing_label.
                # Used to render cross-links from each recent card to the
                # matching picks.json / routing.json viewer entries.
                "task_type": None,
            },
        )
        thread["segment_count"] += 1
        # Keep the latest task_type — if a chain mid-rounds shifts type
        # (rare), the most recent round's label is most relevant.
        routing_label = raw.get("routing_label") or {}
        if isinstance(routing_label, dict) and routing_label.get("task_type"):
            thread["task_type"] = routing_label["task_type"]
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
                "task_type": thread.get("task_type"),
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
    polish_auto_enable = make_shortcut_invocation(
        dispatch=make_dispatch_action(
            "run_command",
            args={"command": "trinity-local polish-auto-enable"},
            metadata={"kind": "polish_auto_enable"},
        ),
        shortcut_name=DEFAULT_SHORTCUT_NAME,
    )
    polish_auto_disable = make_shortcut_invocation(
        dispatch=make_dispatch_action(
            "run_command",
            args={"command": "trinity-local polish-auto-disable"},
            metadata={"kind": "polish_auto_disable"},
        ),
        shortcut_name=DEFAULT_SHORTCUT_NAME,
    )
    return {
        "enable": enable.url,
        "disable": disable.url,
        "reset": reset.url,
        "autoChainEnable": auto_chain_enable.url,
        "autoChainDisable": auto_chain_disable.url,
        "polishAutoEnable": polish_auto_enable.url,
        "polishAutoDisable": polish_auto_disable.url,
    }


def _load_personal_routing_table() -> dict | None:
    """Compute the personal routing table on demand from council_outcomes/.

    Returns None when no councils have been rated yet so the launchpad shows
    the empty-state CTA. The single source of truth is the council_outcomes
    directory; aggregation is cached in-process by directory mtime.

    Augments the table with a ``cold_start`` block per task_type so the
    launchpad can render "X% personalized" badges that match the chairman
    picker's actual sigmoid weighting (task #40).
    """
    from .personal_routing import compute_personal_routing_table
    from .ranker.chairman_picker import sigmoid_alpha

    try:
        table = compute_personal_routing_table()
    except Exception:
        return None
    by_task = table.get("by_task_type") or {}
    if not by_task:
        return None

    cold_start: dict[str, dict] = {}
    for task_type, providers in by_task.items():
        n_personal = 0
        for sub in providers.values():
            if isinstance(sub, dict):
                n_personal = max(n_personal, int(sub.get("n", 0) or 0))
        alpha = sigmoid_alpha(n_personal)
        cold_start[task_type] = {
            "n_personal": n_personal,
            "alpha": round(alpha, 3),
            "personalization_pct": int(round(alpha * 100)),
        }
    table = dict(table)
    table["cold_start"] = cold_start
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
        # Server-injected canonical map so the launchpad's per-category bar
        # chart aggregates ALL personal routing entries (not just the six
        # task_types an out-of-sync hardcoded JS map happened to know about).
        "taskKindToCategory": _task_kind_to_category(),
        "defaultCategoryForUnknownTaskKind": DEFAULT_CATEGORY_FOR_UNKNOWN_TASK_KIND,
        # The personal chart's X-axis uses the LMArena-aligned CATEGORY_REGISTRY
        # keys (overall / coding / hard_prompts / ...). Reference evals use a
        # different category scheme (intelligence/coding/agentic from
        # ArtificialAnalysis); aligning the two sides one day is v1.1+ work.
        "personalChartCategoryKeys": _category_keys(),
        "personalChartCategoryLabels": _category_labels(),
        "providerModels": provider_models,
        "referenceEvalsMeta": get_reference_evals_meta(),
        # Relative URLs so the launchpad works under both file:// (double-click
        # the HTML) and http://localhost:PORT (when serving ~/.trinity via
        # `python -m http.server`). The launchpad lives at
        # /portal_pages/launchpad.html; live_council is at /review_pages/...
        "liveReviewUrl": "../review_pages/live_council.html",
        "activeOperation": active_operation,
        "statusScriptBaseUrl": "./status",
        "councilLoadingMessages": COUNCIL_LOADING_MESSAGES,
        "personalRoutingTable": personal_routing,
        "cortexRules": _load_cortex_rules(),
        "tasteLenses": _load_taste_lenses(),
        "coreStatus": _core_status(),
        # Aggregate "what's stale, what should I do" — only surfaces when
        # one of the four signals (core staleness / picks overrides /
        # audit disagreement / pre-thread-aware topology) fires.
        "memoryHealth": _memory_health(),
        # Just the count — actual cards are server-rendered into the body
        # via build_recent_cards_html. The hero h1 no longer branches on
        # this (promise wins the H1 in idle state); kept exposed in case
        # other sections want a first-run greeting affordance.
        "recentCouncilsCount": len(recent_councils),
        # Timestamp baked at render time — shown in the footer so cache
        # staleness is diagnosable at a glance. If the user sees an old
        # stamp after pip upgrade or fix-deploy, they need to hard-reload.
        "regeneratedAt": now_iso(),
    }


def _core_status() -> dict:
    """Report the freshness of ~/.trinity/core.md vs the five plural
    memories it distills. The launchpad surfaces this as a one-line
    hint so users notice when a fresh `distill` would help.

    Returns one of three states:
    - `{"state": "missing"}`  → core.md never built; lens/picks/... exist
    - `{"state": "stale"}`    → one or more source memories are newer
    - `{"state": "fresh"}`    → core.md is the newest of the bunch
    - `{"state": "empty"}`    → no memories present yet (cold install)
    """
    from .state_paths import (
        core_path, lens_path, picks_path, routing_path,
        topics_path, vocabulary_path,
    )
    core = core_path()
    sources = [
        lens_path(), picks_path(), routing_path(),
        topics_path(), vocabulary_path(),
    ]
    existing_sources = [p for p in sources if p.exists()]
    if not existing_sources:
        return {"state": "empty"}
    if not core.exists():
        return {"state": "missing"}
    try:
        core_mtime = core.stat().st_mtime
    except OSError:
        return {"state": "missing"}
    for src in existing_sources:
        try:
            if src.stat().st_mtime > core_mtime:
                return {"state": "stale", "stale_source": src.name}
        except OSError:
            continue
    return {"state": "fresh"}


def _memory_health() -> dict:
    """Aggregate the four staleness signals the launchpad surfaces:
      - core.md staleness (vs the five plural memories) via _core_status
      - picks override_count > 0 (user-marked rules to demote)
      - picks audit_status == "disagreed" (chairman-audit caught drift)
      - topics.json prompt_ids round-trip integrity (legacy pre-thread-aware)

    Returns:
      {
        "issues": [{name, status, hint}, ...],   # only non-fresh items
        "ok_count": int,                         # memories with no issue
        "total_count": int,                      # all signals inspected
      }

    The launchpad renders the issues row only when issues is non-empty.
    Fresh state → silent → user isn't told "all good!" every launch.
    """
    # Each issue carries:
    #   name    — which memory file
    #   status  — short status badge
    #   hint    — prose hint (no embedded command — pure context)
    #   command — the CLI command the user should run, broken out so the
    #             launchpad can render a click-to-copy chip. None when
    #             the action is "navigate somewhere" rather than "run a CLI".
    #   href    — optional in-app navigation target (e.g. memory.html link)
    issues: list[dict[str, str | None]] = []
    total = 4
    # 1. core.md freshness
    core = _core_status()
    state = core.get("state")
    if state == "stale":
        src = core.get("stale_source", "a source memory")
        issues.append({
            "name": "core.md",
            "status": "stale",
            "hint": f"{src} is newer than the distillation.",
            "command": "trinity-local distill",
            "href": None,
        })
    elif state == "missing":
        issues.append({
            "name": "core.md",
            "status": "missing",
            "hint": "The singular core memory has not been compiled.",
            "command": "trinity-local distill",
            "href": None,
        })

    # 2 + 3. picks.json override + audit signals (cortex layer)
    try:
        picks_payload = _load_cortex_rules()
        if picks_payload:
            rules = picks_payload.get("rules") or []
            overridden = [r for r in rules if r.get("override_count", 0) > 0]
            disagreed = [r for r in rules if r.get("audit_status") == "disagreed"]
            if overridden:
                issues.append({
                    "name": "picks.json",
                    "status": "user-overrides",
                    "hint": f"{len(overridden)} pick(s) marked wrong; re-consolidate to refresh.",
                    "command": "trinity-local consolidate",
                    "href": None,
                })
            if disagreed:
                issues.append({
                    "name": "picks.json",
                    "status": "audit-disagreed",
                    "hint": f"chairman-audit disagreed on {len(disagreed)} pick(s).",
                    "command": None,
                    "href": "../portal_pages/memory.html?file=picks.json",
                })
    except Exception:
        pass  # picks introspection must never break launchpad rendering

    # 4. topics.json — legacy per-turn schema doesn't carry thread_count.
    #    Surfacing as a one-time upgrade prompt; clears on next lens-build.
    try:
        from .state_paths import topics_path
        topics_p = topics_path()
        if topics_p.exists():
            payload = json.loads(topics_p.read_text(encoding="utf-8"))
            basins = payload.get("basins") or []
            has_thread_aware = any(b.get("thread_count", 0) for b in basins)
            if basins and not has_thread_aware:
                issues.append({
                    "name": "topics.json",
                    "status": "pre-thread-aware",
                    "hint": "Topology was computed per-turn (older schema).",
                    "command": "trinity-local lens-build",
                    "href": None,
                })
    except Exception:
        pass

    return {
        "issues": issues,
        "ok_count": max(0, total - len(issues)),
        "total_count": total,
    }


def _load_cortex_rules() -> dict | None:
    """Surface the v1.5 cortex routing patterns for the launchpad.

    Returns a compact dict the template can render as the "what Trinity
    has learned about you" headline card — the visible artifact of the
    consolidation pass (`trinity-local consolidate`). Sorted by trust
    score desc so the highest-confidence rules render first.

    Returns None when no consolidation has run yet — the launchpad shows
    an empty-state CTA pointing at `trinity-local consolidate`.
    """
    try:
        from .cortex import effective_trust, load_routing_patterns, TRUST_KNN_FALLBACK, TRUST_USE_RULE
    except Exception:
        return None
    patterns = load_routing_patterns()
    if not patterns:
        return None
    # Compact view for the template — only the fields the launchpad card needs.
    rules = []
    for basin_id, p in patterns.items():
        rules.append({
            "basin_id": basin_id,
            "primary": p.routing_rule.primary,
            "challenger": p.routing_rule.challenger,
            "reason": p.routing_rule.reason,
            # Surface BOTH the raw trust (data quality) and the effective
            # trust (after user-veto penalty). The launchpad sorts on
            # effective so overridden rules sink; the band label reflects
            # effective too so a heavily-overridden 0.9-quality rule reads
            # as "kNN fallback" not "use rule alone".
            "trust_score": round(effective_trust(p), 3),
            "raw_trust_score": round(p.trust_score.value, 3),
            "trust_band": p.trust_score.interpretation,
            "n_episodes": p.n_episodes,
            "winner_share": round(p.winner_distribution.get(p.routing_rule.primary, 0.0), 3),
            "audit_status": getattr(p, "audit_status", "unaudited"),
            "bimodal_flag": getattr(p, "bimodal_flag", False),
            "override_count": getattr(p, "override_count", 0),
            # First few council_run_ids the rule was extracted from. Capped
            # at 5 (the full set is in council_outcomes/ — only need a peek
            # for the launchpad evidence chips). Empty list when the
            # consolidator didn't record IDs (older patterns).
            "evidence": (getattr(p, "evidence", None) or [])[:5],
        })
    # Highest trust first — that's what the user wants to see at the top.
    rules.sort(key=lambda r: r["trust_score"], reverse=True)
    # Annotate each rule with the topology basin it bridges to (centroid
    # cosine ≥ BASIN_SIM_THRESHOLD). When present, the cortex card row
    # renders a → topology chip so the user can jump from "the rule" to
    # "the prompts the rule was extracted from" in one click. Reuses the
    # same matching map as the recent-card chip + the routing-table chip
    # so all three surfaces agree.
    task_to_basin = _task_to_topology_basin()
    for r in rules:
        bid = task_to_basin.get(str(r["basin_id"]))
        if bid:
            r["topology_basin"] = bid
    return {
        "rules": rules,
        "total_basins": len(rules),
        "trust_use_rule": TRUST_USE_RULE,
        "trust_knn_fallback": TRUST_KNN_FALLBACK,
    }


def _load_taste_lenses() -> dict | None:
    """Surface taste lenses for the launchpad.

    Prefers the new 3-stage pipeline output (`me/lenses.json`,
    `me/orderings.json`) which carries pole_a / pole_b / failure
    modes / spanned basins. Falls back to the legacy single-virtue
    parse when the pipeline hasn't run yet.

    Returns None when neither source has data — the launchpad shows
    an empty-state CTA pointing at `trinity-local me-build`.
    """
    from .me.pair_mining import load_lenses, load_orderings
    from .me_lenses import parse_taste_lenses

    paired = [p.to_dict() for p in load_lenses()]
    orderings = [p.to_dict() for p in load_orderings()]

    legacy = None
    try:
        lenses = parse_taste_lenses()
        if not lenses.is_empty:
            legacy = lenses.to_dict()
    except Exception:
        legacy = None

    if not paired and not orderings and not legacy:
        return None

    out: dict = legacy.copy() if legacy else {
        "rejections": [],
        "vocabulary": [],
        "abstract_lenses": [],
        "rejections_share_text": "",
        "vocabulary_share_text": "",
        "abstract_lenses_share_text": "",
        "combined_share_text": "",
    }
    out["paired_lenses"] = paired
    out["orderings"] = orderings
    if paired:
        # Build a combined share text from the paired form — preferred
        # over the single-virtue legacy text once the pipeline ships.
        lines = ["My lenses (paired tensions Trinity surfaced):", ""]
        for p in paired:
            lines.append(f"→ {p['pole_a']} ↔ {p['pole_b']}")
            if p.get("failure_a") and p.get("failure_b"):
                lines.append(f"   pure-{p['pole_a']} fails as {p['failure_a']}; pure-{p['pole_b']} fails as {p['failure_b']}")
        lines.append("")
        lines.append("(via trinity-local)")
        out["combined_share_text"] = "\n".join(lines)
    return out


def _format_relative_date(iso: str) -> str:
    # ISO timestamp → friendly relative date for the recent-council cards.
    # "2026-05-08T14:47:53+00:00" -> "May 8" or "Today" or "3 days ago".
    # Falls back to the raw string if parsing fails — better noisy than blank.
    from datetime import datetime, timezone

    if not iso or iso == "unknown":
        return iso or "unknown"
    try:
        dt = datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return iso
    now = datetime.now(timezone.utc) if dt.tzinfo else datetime.now()
    delta = (now - dt).total_seconds()
    if delta < 0:
        return dt.strftime("%b %-d")
    if delta < 3600:
        return "Just now"
    if delta < 86400:
        h = int(delta // 3600)
        return "1 hour ago" if h == 1 else f"{h} hours ago"
    if delta < 86400 * 7:
        d = int(delta // 86400)
        return "Yesterday" if d == 1 else f"{d} days ago"
    return dt.strftime("%b %-d")


def _task_to_topology_basin() -> dict[str, str]:
    """Return {task_type: topology_basin_id} for picks with a centroid
    match into topics.json above BASIN_SIM_THRESHOLD.

    Mirrors the JS helper `matchBasinsToPicks` in memory_viewer.py —
    same logic, same threshold, same first-task-wins rule — so the
    server-rendered launchpad chips agree with the client-rendered
    Reader views. Returns {} on any error (cold install, missing
    topics.json, malformed centroids) so the cards keep rendering.
    """
    try:
        from .cortex import load_routing_patterns
        from .state_paths import topics_path
    except Exception:
        return {}
    try:
        patterns = load_routing_patterns()
    except Exception:
        patterns = None
    if not patterns:
        return {}
    try:
        topics_p = topics_path()
        if not topics_p.exists():
            return {}
        topics = json.loads(topics_p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    basins = topics.get("basins") or []
    if not basins:
        return {}
    # Pre-compute per-basin norm + centroid once.
    import math
    basin_norms = []
    for b in basins:
        c = b.get("centroid") or []
        s = sum(x * x for x in c)
        if not s:
            continue
        basin_norms.append({"centroid": c, "norm": math.sqrt(s), "id": b.get("id")})
    if not basin_norms:
        return {}
    result: dict[str, str] = {}
    claimed: set[str] = set()  # first task wins per basin (mirrors JS)
    for task_type, pattern in patterns.items():
        pc = getattr(pattern, "basin_centroid", None) or []
        if not pc:
            continue
        pc_norm_sq = sum(x * x for x in pc)
        if not pc_norm_sq:
            continue
        pc_norm = math.sqrt(pc_norm_sq)
        best_sim = -1.0
        best_id: str | None = None
        for bn in basin_norms:
            c = bn["centroid"]
            if len(c) != len(pc):
                continue
            dot = sum(a * b for a, b in zip(pc, c))
            sim = dot / (pc_norm * bn["norm"])
            if sim > best_sim:
                best_sim = sim
                best_id = bn["id"]
        if best_id and best_sim >= BASIN_SIM_THRESHOLD and best_id not in claimed:
            result[str(task_type)] = str(best_id)
            claimed.add(best_id)
    return result


def build_recent_cards_html(recent_councils: list[dict[str, str | None]]) -> str:
    # Build the task→topology_basin map once for ALL cards in this
    # render pass (not per-card — load_routing_patterns + topics.json
    # parse would otherwise re-run N times).
    task_to_basin = _task_to_topology_basin()

    def _card(item: dict[str, str | None]) -> str:
        thread_id = item.get("chain_root_id") or item.get("council_id")
        review_path = item.get("review_page_path")
        if not review_path or not thread_id:
            return ""
        # Relative URL so the recent-council card works under both file:// and
        # http://localhost (the launchpad sits at /portal_pages/launchpad.html;
        # the review page is /review_pages/<id>.html — the redirect stub —
        # which forwards to live_council.html with the same query string).
        href = f"../review_pages/{_esc(Path(str(review_path)).name)}?thread_id={_esc(str(thread_id))}"
        winner = (item.get("winner_provider") or "No winner yet").replace("_", " ").title()
        created_at = _format_relative_date(item.get("created_at") or "unknown")
        seg_count = int(item.get("segment_count") or 1)
        rounds_badge = (
            f' · <span style="opacity: 0.7;">{seg_count} rounds</span>'
            if seg_count > 1
            else ""
        )
        # Cross-memory chips: when this council's chairman tagged a
        # task_type, render two ghost links that jump to picks.json
        # and routing.json for that same task. Sits OUTSIDE the main
        # card anchor so clicking a chip doesn't also trigger the
        # full-card navigation to the live council page.
        task_type = item.get("task_type")
        xlinks = ""
        if task_type:
            task = _esc(str(task_type))
            # All three chips share the .cross-memory-chip base from
            # launchpad_template.py — visual treatment lives in one
            # place. --pill modifier gives the round/larger look the
            # recent-card row uses (vs the inline label chip on the
            # cortex card).
            chip_classes = "council-xlink cross-memory-chip cross-memory-chip--label cross-memory-chip--pill"
            chips = [
                f'<a href="../portal_pages/memory.html?file=picks.json&task={task}" '
                f'class="{chip_classes}">→ pick</a>',
                f'<a href="../portal_pages/memory.html?file=routing.json&task={task}" '
                f'class="{chip_classes}">→ routing</a>',
            ]
            # Third chip: → topology, only when this task_type has a
            # centroid match into topics.json (tick #34). Closes the
            # launchpad → topology loop directly so the user doesn't
            # have to bounce through picks first.
            topo_basin = task_to_basin.get(str(task_type))
            if topo_basin:
                basin = _esc(topo_basin)
                chips.append(
                    f'<a href="../portal_pages/memory.html?file=topics.json&basin={basin}" '
                    f'class="{chip_classes}">→ topology</a>'
                )
            xlinks = (
                f'<div class="council-xlinks" style="display: flex; gap: 6px; margin-top: -4px; flex-wrap: wrap;">'
                + "".join(chips)
                + "</div>"
            )
        return f"""
        <div style="display: flex; flex-direction: column; gap: 8px;">
          <a href="{href}" style="text-decoration: none; cursor: pointer;" class="council-card-link">
            <article class="card council-card">
              <div class="eyebrow">Thread</div>
              <h3 class="council-title">{_esc(str(item['title']))}</h3>
              <p class="meta">{_esc(winner)} · {_esc(created_at)}{rounds_badge}</p>
            </article>
          </a>
          {xlinks}
        </div>
        """

    cards = "".join(_card(item) for item in recent_councils)
    return cards or '<p class="meta">No councils yet. Launch one above to get started.</p>'
