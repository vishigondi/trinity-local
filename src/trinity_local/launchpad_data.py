from __future__ import annotations

import html
import json
from pathlib import Path

from .adapters import check_all_adapters
from .categories import (
    DEFAULT_CATEGORY_FOR_UNKNOWN_TASK_TYPE,
    category_keys as _category_keys,
    category_labels as _category_labels,
    task_type_to_category as _task_type_to_category,
)
from .config import load_config
from .council_runtime import load_prompt_bundle
from .council_status import load_council_status
from .dispatch_registry import make_dispatch_action
from .global_benchmarks import get_global_benchmarks, get_reference_evals_meta
from .memory.store import iter_prompt_nodes
from .shortcuts_integration import DEFAULT_SHORTCUT_NAME, make_shortcut_invocation
from .state_paths import council_outcomes_dir, council_status_dir, review_pages_dir, trinity_home
from .telemetry import build_elo_snapshot, launchpad_telemetry_state
from .utils import now_iso

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
    """When the prompt was built by the launchpad's JS thread-context wrapper
    (launchpad_template.py applySuggestion), the actual user question lives
    after a "Current user message:\n" marker. The preceding block is
    prior-assistant context that humans don't want as the card title. Strip
    it for display.
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
        # (Phase 3d 2026-05-22: the per-thread "any_rated" flag was
        # stripped here when the launchpad rating UI was retired. The
        # chairman's pick — recorded in routing_label.winner above — is
        # now the supervision signal and never needs a user click.)
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
                # The per-thread "rated" flag was retired Phase 3d
                # (2026-05-22) along with the launchpad rating UI;
                # chairman's winner_provider is the supervision signal.
                "review_page_path": str(
                    (review_pages_dir() / "live_council.html").resolve()
                ),
            }
        )
    items.sort(key=lambda item: item.get("created_at") or "", reverse=True)
    return items[:limit]


def _provider_install_help(provider: str) -> tuple[str, str]:
    # Same install strings as _TIER_INSTALL_HELP below — they're two
    # surfaces of the same fact (the canonical install command per
    # provider). Iter-#39 caught divergent strings (Antigravity here
    # had `&& agy` appended, which auto-launches the CLI after
    # install — surprising in a copy-paste install one-liner). New
    # invariant: these two functions agree byte-for-byte on the
    # install command field. The doc-consistency guard
    # test_launchpad_install_commands_match enforces it.
    if provider == "claude":
        return ("Claude Code", "npm install -g @anthropic-ai/claude-code")
    if provider == "codex":
        return ("Codex CLI", "npm install -g @openai/codex && codex --login")
    if provider == "antigravity":
        return ("Antigravity", "curl -fsSL https://antigravity.google/cli/install.sh | bash")
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


# Tier-card display order for the launchpad — visually distinct from
# config.CANONICAL_COUNCIL_PROVIDERS / registry.CANONICAL_COUNCIL_PROVIDERS
# (which use a chairman-preference order). The launchpad's order here is
# UI-led, not load-bearing for routing. Membership is the same; if either
# the launchpad order OR the canonical order changes, both call sites
# must be checked.
_TIER_PROVIDERS: tuple[str, ...] = ("claude", "codex", "antigravity")

# Provider slug → on-PATH binary name. Most providers use the same string,
# but Antigravity's slug is "antigravity" while its CLI binary is `agy`.
_TIER_PROVIDER_BINARY: dict[str, str] = {
    "claude": "claude",
    "codex": "codex",
    "antigravity": "agy",
}

# Per-provider install commands. The canonical form per provider lives
# here AND in setup_guidance.py + doctor.py — keep all three in sync
# (the iter-#39 fix harmonized them after discovering the launchpad
# taught `curl https://claude.ai/install.sh | bash` while setup_guidance
# + tests both taught `npm install -g @anthropic-ai/claude-code`).
_TIER_INSTALL_HELP: dict[str, tuple[str, str, str]] = {
    # provider -> (display name, install command, value proposition)
    "claude": (
        "Claude Code",
        "npm install -g @anthropic-ai/claude-code",
        "Anchor voice — drives the chairman synthesis by default.",
    ),
    "codex": (
        "Codex CLI",
        "npm install -g @openai/codex && codex --login",
        "Adversarial second voice — surfaces real disagreement.",
    ),
    "antigravity": (
        "Antigravity",
        "curl -fsSL https://antigravity.google/cli/install.sh | bash",
        "Long-context third voice — completes the canonical council.",
    ),
}


def _embedder_status() -> dict[str, object]:
    """Surface the deeper-memory opt-in state on the launchpad.

    The nomic-embed-text-v1.5 weights are ~600 MB. They aren't bundled
    with Trinity — first lens-build / dream / vocabulary call triggers
    a HuggingFace Hub download. The CLAUDE.md status block describes
    this; the user encounters it as a RuntimeError the first time they
    run lens-build, which is jarring.

    Better: surface the state on the launchpad ON FIRST PAINT, with a
    clear "Build deeper memory" CTA showing the exact download
    command. The card is gated on a real signal — only show when the
    user has prompts indexed (so they'd actually benefit). Cold
    install with no prompts shows nothing; user has bigger things to
    do first.

    Returns:
      modelDownloaded:    True if HF cache contains the weights
      promptsIndexed:     True if prompt_nodes.jsonl has content
      mlxAvailable:       True if sentence-transformers is importable
      downloadCommand:    shell command to fetch the model
      show:               True only when prompts are indexed AND model
                          isn't downloaded; everything else hides the
                          card (cold install → nothing to embed yet;
                          everything wired → nothing to do)
    """
    # Model weights live in HuggingFace cache, NOT in ~/.trinity/models/.
    # sentence-transformers writes to the HF cache; backend_mlx.py used
    # to expose a `model_path()` helper that pointed at ~/.trinity/models/
    # but nothing read it, and the helper was retired 2026-05-20 (tick 28).
    # We read the real cache directly here.
    hf_cache = Path.home() / ".cache" / "huggingface" / "hub"
    model_cache_dir = hf_cache / "models--nomic-ai--nomic-embed-text-v1.5"
    model_downloaded = False
    if model_cache_dir.exists():
        # snapshots/<commit-hash>/ holds the weight files. Any non-empty
        # snapshot directory means the model was at least partly fetched.
        snapshots = model_cache_dir / "snapshots"
        if snapshots.exists():
            for snapshot in snapshots.iterdir():
                if snapshot.is_dir() and any(snapshot.iterdir()):
                    model_downloaded = True
                    break

    # Prompts indexed = user has data that would benefit from embeddings.
    # Empty install → no upsell.
    prompt_nodes_file = trinity_home() / "prompts" / "prompt_nodes.jsonl"
    prompts_indexed = (
        prompt_nodes_file.exists()
        and prompt_nodes_file.stat().st_size > 100  # 100 bytes = at least one record
    )

    # mlxAvailable tracks whether the LIBS (sentence-transformers + torch)
    # are importable. Without these, even running the download command
    # won't help — the user needs `pip install trinity-local[mlx]` first.
    try:
        from . import embeddings
        mlx_available = embeddings.is_available()
    except Exception:
        mlx_available = False

    download_command = (
        "huggingface-cli download nomic-ai/nomic-embed-text-v1.5"
        if mlx_available
        else "pip install 'trinity-local[mlx]' && huggingface-cli download nomic-ai/nomic-embed-text-v1.5"
    )

    return {
        "modelDownloaded": model_downloaded,
        "promptsIndexed": prompts_indexed,
        "mlxAvailable": mlx_available,
        "downloadCommand": download_command,
        # Show the card only when we have signal (prompts indexed) AND
        # the model is missing. Avoids nagging cold-install users with
        # zero prompts, and hides the card entirely when everything's
        # already wired.
        "show": prompts_indexed and not model_downloaded,
    }


def _council_tier_status() -> dict[str, object]:
    """The audience-expansion tier card data.

    Pillar of the "works with 1, sells the other two" pitch: shows the
    user where they are on the 1 → 2 → 3 ladder and what the next
    free-tier add unlocks.

    Returned shape:
      tier:           1 | 2 | 3  — number of canonical providers on PATH
      installed:      [provider names that have a binary on PATH]
      missing:        [{provider, label, installCommand, value} for missing]
      headline:       short status line for the card header
      nextStep:       single next provider to pitch, None when tier == 3

    Tier card UI:
      tier 0 → "Install a Claude-compatible CLI to start" (rare; cold install)
      tier 1 → "You have <X>. Add <Y> for a 2nd voice."
      tier 2 → "You have <X> + <Y>. Add <Z> for the full council."
      tier 3 → card hidden (all installed).
    """
    import shutil

    installed: list[str] = []
    missing: list[dict[str, str]] = []
    for provider in _TIER_PROVIDERS:
        # Most provider slugs match their on-PATH binary name 1:1, but
        # Antigravity is "antigravity" with binary `agy`. `_TIER_PROVIDER_BINARY`
        # is the canonical map; shutil.which is what the council runner
        # uses too — same source of truth.
        binary = _TIER_PROVIDER_BINARY.get(provider, provider)
        if shutil.which(binary) is not None:
            installed.append(provider)
        else:
            label, cmd, value = _TIER_INSTALL_HELP[provider]
            missing.append({
                "provider": provider,
                "label": label,
                "installCommand": cmd,
                "value": value,
            })

    tier = len(installed)
    next_step = missing[0] if missing else None

    installed_labels = [_TIER_INSTALL_HELP[p][0] for p in installed]
    if tier == 0:
        headline = "Install a council provider to get started."
    elif tier == 1:
        headline = f"You have {installed_labels[0]}. Add one more for cross-model disagreement."
    elif tier == 2:
        joined = " + ".join(installed_labels)
        headline = f"You have {joined}. One more provider completes the canonical council."
    else:
        headline = "Full canonical council — all three providers installed."

    return {
        "tier": tier,
        "installed": installed,
        "missing": missing,
        "headline": headline,
        "nextStep": next_step,
        # The card renders only when 0 < tier < 3. Tier 0 is rare
        # (truly cold install) — surfacing the message is still
        # useful but uses a different visual treatment. Tier 3
        # hides the card entirely.
        "show": 0 <= tier < 3,
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
                "memberOrder": list(metadata.get("members") or list((raw.get("members") or {}).keys()) or ["claude", "antigravity", "codex"]),
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
    # auto-chain + polish-auto settings links retired 2026-05-17 — the
    # toggles are gone; users click auto-chain on the council review page.
    # Phase 4b — each settings action surfaces its narrow extension-tier
    # `kind` alongside the legacy shortcut URL. The launchpad's dispatcher
    # picks the extension path when wired, falls back to the URL on
    # macOS, surfaces the install banner otherwise.
    return {
        "enable": {"shortcutUrl": enable.url, "extensionKind": "telemetry-enable"},
        "disable": {"shortcutUrl": disable.url, "extensionKind": "telemetry-disable"},
        "reset": {"shortcutUrl": reset.url, "extensionKind": "telemetry-reset-id"},
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
    settings_links = _settings_links()
    global_benchmarks = get_global_benchmarks()
    provider_health = _provider_health_data()
    council_tier = _council_tier_status()
    embedder_status = _embedder_status()
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
        "defaultGoal": "Find the strongest answer.",
        "defaultMembers": __import__("trinity_local.config", fromlist=["default_council_members"]).default_council_members(),
        "defaultPrimaryProvider": None,
        "telemetry": telemetry,
        "settingsLinks": settings_links,
        "providerHealth": provider_health,
        "councilTier": council_tier,
        "embedderStatus": embedder_status,
        "eloChart": chart_data,
        "globalBenchmarks": global_benchmarks,
        "benchmarkProviders": benchmark_providers,
        # Server-injected canonical map so the launchpad's per-category bar
        # chart aggregates ALL personal routing entries (not just the six
        # task_types an out-of-sync hardcoded JS map happened to know about).
        "taskTypeToCategory": _task_type_to_category(),
        "defaultCategoryForUnknownTaskType": DEFAULT_CATEGORY_FOR_UNKNOWN_TASK_TYPE,
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
        # Merge corpus summary (tick #48) — small counts dict so future
        # launchpad surfaces can show "Trinity has captured N tacit-
        # record acts" without re-walking the log. Computed-view-on-
        # demand same as personal_routing_table — no separate state file.
        "mergeLog": _safe_merge_summary(),
        # Map basin_id → "top_term1 · top_term2 · top_term3" — used by
        # the launchpad chip tooltips that deep-link into topology so
        # the user sees what a basin is *about* without having to click.
        # Resolved at page-build time from topics.json; empty {} when
        # no consolidation has run.
        "topologyBasinLabels": _topology_basin_labels(),
        "coreStatus": _core_status(),
        # Aggregate "what's stale, what should I do" — only surfaces when
        # one of the five signals (core staleness / picks overrides /
        # audit disagreement / pre-thread-aware topology / picks cortex-
        # stale) fires. See `_memory_health()` docstring for the
        # canonical list.
        "memoryHealth": _memory_health(),
        # Just the count — actual cards are server-rendered into the body
        # via build_recent_cards_html. The hero h1 no longer branches on
        # this (promise wins the H1 in idle state); kept exposed in case
        # other sections want a first-run greeting affordance.
        "recentCouncilsCount": len(recent_councils),
        # verdictStats removed from pageData 2026-05-21 with the
        # rating UX sunset (commit 8f1fd95). The compute function
        # _verdict_stats() was retired 2026-05-22 alongside its
        # sole remaining consumer doctor._check_verdict_rate.
        # Retired 2026-05-17. The macOS Shortcut dispatcher is gone;
        # _shortcut_status() now always reports applicable=False so the
        # legacy banner stays hidden. Kept on the payload for template
        # backward compat — the JS dispatch reads it and short-circuits.
        "shortcutStatus": _shortcut_status(),
        # Empirical benchmark summary — most-recent eval-run result
        # surfaced on the launchpad so the user sees their personal
        # benchmark numbers without cat'ing JSON. Empty state (CTA)
        # when no runs have completed yet.
        "evalSummary": _eval_summary(),
        # rateLimitSaves removed from pageData 2026-05-21 alongside
        # the rate-action / pending-ratings mechanism retirement. The
        # launchpad never rendered a card for it (the user explicitly
        # asked "remove this" pre-launch); function was orphan.
        # v1.6 Surface 33 — browser-capture activity. Empty state has a
        # CTA (install the extension); populated state shows per-provider
        # counts + last-capture timestamp. Stale (> 24h since last
        # capture, when at least one exists) flips a warning border —
        # the same silent-breakage signal verdict_rate / handoff_ready
        # use elsewhere.
        "browserCapture": _browser_capture(),
        # Phase 4: Chrome extension dispatch ID. Populated when the user has
        # run `trinity-local install-extension --extension-id <ID>` (Phase 2).
        # Read by window.__TRINITY_DISPATCH__ to call chrome.runtime.sendMessage
        # against the right extension. None when not configured — dispatch
        # falls back to the macOS Shortcut path on Mac, or shows the install
        # banner elsewhere.
        "browserExtension": _browser_extension(),
        # Timestamp baked at render time — shown in the footer so cache
        # staleness is diagnosable at a glance. If the user sees an old
        # stamp after pip upgrade or fix-deploy, they need to hard-reload.
        "regeneratedAt": now_iso(),
    }


def _eval_summary() -> dict:
    """Surface the most-recent eval-run result on the launchpad.

    Reads ~/.trinity/evals/results/eval_*__model_*.json. Returns:
      - {has_results: False, ...empty_state_fields}  when no runs yet
      - {has_results: True, target, model, aggregate_score, axes[],
         total_runs, items_completed, items_total, eval_id, ran_at,
         result_path}  when at least one run completed

    Empty state still carries the CTA fields (eval_set_available)
    so the template can render the "you built an eval set, run it
    against gemini" call to action without losing data.

    Per "Analytics never crash": any failure returns the safe
    empty-state shape rather than raising — the launchpad must not
    fall over because an eval result file is malformed.
    """
    from .state_paths import state_dir
    empty = {
        "has_results": False,
        "target": None,
        "model": None,
        "aggregate_score": None,
        "axes": [],
        "total_runs": 0,
        "items_completed": 0,
        "items_total": 0,
        "eval_id": None,
        "ran_at": None,
        "result_path": None,
        # Whether the user has built an eval set — drives whether the
        # empty state CTA points at `eval-build` or `eval-run`.
        "eval_set_available": False,
    }
    # NOTE: hardcoded path on purpose — `evals.builder.evals_dir()` mkdir-
    # creates the directory as a side effect, which would surface an empty
    # `~/.trinity/evals/` on every launchpad render for users who haven't
    # run eval-build yet. Same anti-ghost-dir reason as tick 28's
    # models_dir() sunset. Read-only check: just stat for existence.
    evals_dir = state_dir() / "evals"
    if not evals_dir.is_dir():
        return empty
    eval_set_available = any(evals_dir.glob("eval_*.json"))
    results_dir = evals_dir / "results"
    if not results_dir.is_dir():
        empty["eval_set_available"] = eval_set_available
        return empty
    candidates = sorted(
        results_dir.glob("eval_*__model_*.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        empty["eval_set_available"] = eval_set_available
        return empty
    latest = candidates[0]
    try:
        payload = json.loads(latest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        empty["eval_set_available"] = eval_set_available
        return empty
    # Build the per-axis array for the template, sorted desc by mean.
    by_type = payload.get("by_rejection_type") or {}
    axes = sorted(
        [
            {
                "name": axis,
                "count": stats.get("count", 0),
                "mean": stats.get("mean_score", 0.0),
                "min": stats.get("min_score", 0.0),
                "max": stats.get("max_score", 0.0),
            }
            for axis, stats in by_type.items()
            if isinstance(stats, dict)
        ],
        key=lambda a: a["mean"],
        reverse=True,
    )
    # Multi-target comparison view. When Trinity has results for ≥2
    # providers, the launchpad shows a comparison table — not just
    # the most recent run. A journalist screenshotting the launchpad
    # should see the wedge ("Trinity scores models against YOUR
    # rejections"), which only lands when multiple providers are
    # visible side-by-side.
    #
    # For each unique target_provider, take the MOST RECENT result
    # (mtime descending). Sort the row order by aggregate score
    # descending so the strongest model is first — that's the natural
    # marketing voice ("here's the leaderboard on YOUR corpus").
    by_target: dict[str, dict] = {}
    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        target = data.get("target_provider")
        if not target or target in by_target:
            continue  # keep the most recent (we walked mtime-desc)
        # Judge provider is stored per-item (each item names its
        # judge). Take the first item's judge as the run's judge —
        # the harness uses one judge per run, so any item works.
        items = data.get("items") or []
        judge = None
        for item in items:
            if isinstance(item, dict) and item.get("judge_provider"):
                judge = item["judge_provider"]
                break
        # Per-axis means for the by-axis matrix view + per-axis leader
        # computation below. Keep nested so consumers paying only for
        # the aggregate-leaderboard view skip the parse.
        # Pairs (mean, count) so the leader-suppression rule can check
        # sample size — claims like "codex wins COMPRESSION 0.77" based
        # on n=2 are noise, not signal.
        per_axis = {}
        per_axis_n = {}
        for axis_name, stats in (data.get("by_rejection_type") or {}).items():
            if isinstance(stats, dict) and "mean_score" in stats:
                per_axis[axis_name] = float(stats["mean_score"])
                per_axis_n[axis_name] = int(stats.get("count", 0))
        by_target[target] = {
            "target": target,
            "model": data.get("target_model"),
            "aggregate_score": data.get("aggregate_score"),
            "items_completed": data.get("items_completed", 0),
            "judge": judge,
            "ran_at": data.get("completed_at") or data.get("started_at"),
            "by_axis": per_axis,
            "by_axis_n": per_axis_n,
            # eval_id surfaces mixed-set drift: when the comparison list
            # contains rows from different eval sets the aggregate
            # scores aren't directly comparable. Template uses the
            # mixed_eval_sets flag below to warn the user.
            "eval_id": data.get("eval_id"),
        }
    comparison = sorted(
        by_target.values(),
        key=lambda r: r.get("aggregate_score") or -1.0,
        reverse=True,
    )
    # Mixed-eval-set drift: each provider's most-recent run may target
    # a different eval set (e.g. user rebuilt then re-scored only 2 of
    # 3 providers). Surface a warning when distinct eval_ids appear in
    # the comparison list — scores from different sets aren't
    # directly comparable. CLI mirror: `eval-show --compare` emits the
    # same warning; this brings it to the launchpad.
    distinct_eval_ids = {
        r["eval_id"] for r in comparison if r.get("eval_id")
    }
    mixed_eval_sets = len(distinct_eval_ids) > 1
    # Per-axis leader: for each axis seen across any provider, who
    # scored highest? Surfaces the wedge claim ("X is best for this
    # kind of question") on the launchpad without requiring the user
    # to leave for `trinity-local eval-show --compare --by-axis`.
    #
    # SUPPRESSED when mixed_eval_sets is True: comparing per-axis
    # scores across different eval sets is exactly the operation the
    # mixed-set warning says is invalid. Rendering "claude leads
    # COMPRESSION (0.12)" next to "codex leads COMPRESSION (0.77)"
    # when those came from DIFFERENT 5-item-vs-45-item sets is a
    # misleading head-to-head claim. The banner already surfaces the
    # remedy; better to hide the chips than make a false comparison.
    per_axis_leader: list[dict] = []
    # Minimum samples per provider before declaring a leader on an axis.
    # n=2 is the live trigger — COMPRESSION on the user's eval set had 2
    # items per provider, but mean differences of 0.7 between providers
    # at n=2 are noise, not signal. n=3 is a hard floor; in practice
    # users should be at n=10+ before a per-axis claim is publishable.
    MIN_AXIS_SAMPLES = 3
    if not mixed_eval_sets:
        axes_seen: set[str] = set()
        for row in comparison:
            axes_seen.update((row.get("by_axis") or {}).keys())
        for axis in sorted(axes_seen):
            scored = [
                (r["target"], r["by_axis"][axis], (r.get("by_axis_n") or {}).get(axis, 0))
                for r in comparison
                if axis in (r.get("by_axis") or {})
            ]
            if not scored:
                continue
            # Sample-size guard: if ANY contender on this axis is below
            # the floor, suppress the claim — leader-by-noise is worse
            # than no leader.
            if any(n < MIN_AXIS_SAMPLES for _, _, n in scored):
                continue
            leader_target, leader_score, _ = max(scored, key=lambda kv: kv[1])
            per_axis_leader.append({
                "axis": axis,
                "target": leader_target,
                "score": leader_score,
            })

    return {
        "has_results": True,
        "target": payload.get("target_provider"),
        "model": payload.get("target_model"),
        "aggregate_score": payload.get("aggregate_score"),
        "axes": axes,
        "total_runs": len(candidates),
        "items_completed": payload.get("items_completed", 0),
        "items_total": payload.get("items_total", 0),
        "eval_id": payload.get("eval_id"),
        "ran_at": payload.get("completed_at") or payload.get("started_at"),
        "result_path": str(latest.relative_to(state_dir())),
        "eval_set_available": eval_set_available,
        # Multi-target comparison: list of {target, model,
        # aggregate_score, items_completed, judge, ran_at, by_axis},
        # sorted by aggregate desc. Always at least 1 entry (the latest
        # run). Template uses this when len(comparison) >= 2 to render
        # a leaderboard view alongside the per-axis bars.
        "comparison": comparison,
        # Per-axis leader chips. List of {axis, target, score} sorted
        # by axis name. Template renders chips above the leaderboard
        # when len >= 1, surfacing the wedge claim ("X is best at
        # COMPRESSION") without requiring the user to leave for
        # `trinity-local eval-show --compare --by-axis`.
        "per_axis_leader": per_axis_leader,
        # True when the comparison list contains rows from ≥2 distinct
        # eval sets. Template surfaces a warning banner so a user
        # rebuilding-without-rescoring-all-providers sees the drift.
        "mixed_eval_sets": mixed_eval_sets,
    }


# _rate_limit_saves() retired 2026-05-21 alongside the
# rate-action / pending-ratings mechanism retirement. Function was
# computed every launchpad render and shipped to pageData["rateLimitSaves"]
# but the Vue template never read it (user said "remove this" pre-launch).
# Pure orphan; removed from both call site and definition. Registry:
# src/trinity_local/retired_names.py.


def _humanize_ago(seconds: int | None) -> str:
    """Friendly relative-time string for the launchpad UI."""
    if seconds is None or seconds < 0:
        return ""
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    if seconds < 86400:
        return f"{seconds // 3600}h"
    return f"{seconds // 86400}d"


def _browser_capture() -> dict:
    """Surface 33 — "Browser capture · last 24h" launchpad card.

    Per ``docs/spec-v1.6.md`` line 479-497: makes silent capture breakage
    VISIBLE. Walks ``~/.trinity/conversations/<provider>/*.json`` (the
    paths the v1.6 capture host writes to), counts per-provider, finds
    the most-recent mtime. If the extension stops working, the "Last
    capture" timestamp ages; same shape as the verdict_rate /
    handoff_ready / cortex_freshness checks.

    File-shape filtering (provider-conditional):
      - ``<conv_id>.stream.json`` for claude/chatgpt — adapter
        accumulator sidecars to canonical ``<conv_id>.json`` files;
        skipped to avoid double-counting.
      - ``<conv_id>.stream.json`` for gemini — IS the canonical
        output (Google's batchexecute is reply-only; gemini.js writes
        directly to ``.stream.json``). Counted.
      - ``stream-<urlhash>.json`` (any provider) — fallback no-adapter
        writes when no ``__TRINITY_ADAPTERS.<provider>`` exists. Since
        `gemini.js` shipped (commit 441bc28, task #135), all 3 named
        providers have adapters; this fallback path is dormant unless
        a new untracked provider URL gets visited. Always skipped
        (no conv_id, just an opaque url hash; not user-facing).

    Returns:
      - {has_data: False, install_command} when zero capture files
      - {has_data: True, total_captured, providers[], last_capture_iso,
         last_capture_ago_seconds, stale (when last_capture > 24h ago)}
        once captures exist.

    Per "Analytics never crash": any unexpected failure returns the
    empty shape.
    """
    from .state_paths import conversations_dir
    empty = {
        "has_data": False,
        "total_captured": 0,
        "captured_24h": 0,
        "providers": [],
        "last_capture_iso": None,
        "last_capture_ago_seconds": None,
        "stale": False,
        "install_command": "trinity-local install-extension",
    }
    conv_root = conversations_dir()
    if not conv_root.exists():
        return empty
    try:
        import time as _time
        now = _time.time()
        day_ago = now - 86400
        per_provider: dict[str, dict[str, int]] = {}
        latest_mtime: float = 0.0
        total = 0
        total_24h = 0
        for provider_dir in conv_root.iterdir():
            if not provider_dir.is_dir():
                continue
            provider_name = provider_dir.name
            count = 0
            count_24h = 0
            for f in provider_dir.glob("*.json"):
                # `stream-<urlhash>.json` is the raw-fallback orphan
                # (no conv_id) written when no adapter exists. Always
                # skip — not a user-facing conversation.
                if f.name.startswith("stream-"):
                    continue
                # `.stream.json` is provider-conditional: it's a
                # sidecar for claude/chatgpt (skip to avoid double-
                # counting alongside the canonical `<conv_id>.json`),
                # but it IS canonical for gemini (Google's batchexecute
                # is reply-only — gemini.js writes <conv_id>.stream.json
                # as the only output). Shipped 2026-05-22 (441bc28).
                if f.name.endswith(".stream.json") and provider_name != "gemini":
                    continue
                try:
                    mtime = f.stat().st_mtime
                except OSError:
                    continue
                count += 1
                if mtime > day_ago:
                    count_24h += 1
                if mtime > latest_mtime:
                    latest_mtime = mtime
            if count:
                per_provider[provider_name] = {"count": count, "count_24h": count_24h}
                total += count
                total_24h += count_24h
        if total == 0:
            return empty
        ago_seconds = int(now - latest_mtime) if latest_mtime else None
        last_iso = None
        if latest_mtime:
            from datetime import datetime, timezone
            last_iso = datetime.fromtimestamp(latest_mtime, tz=timezone.utc).isoformat()
        # Sidebar-sync diff per provider: surfaces "you have N unsynced
        # threads" signal the status CLI already shows. Same data source
        # (_query_sync_status) so launchpad + status + in-provider pill
        # all read from one place. Skipped for providers with 0 captures
        # (nothing to diff against — _query_sync_status returns the
        # provider doesn't exist, which is a different state).
        from .capture_host import _query_sync_status
        provider_rows = []
        for p, v in per_provider.items():
            row = {"provider": p, "count": v["count"], "count_24h": v["count_24h"]}
            try:
                sync = _query_sync_status({"provider": p})
                if sync.get("ok"):
                    row["sidebar_count"] = sync.get("sidebar_count", 0)
                    row["missing_count"] = sync.get("missing_count", 0)
            except Exception:
                # Per analytics-never-crash: sidebar lookup failure
                # silently drops the missing-count signal for that
                # provider; the launchpad still renders the row.
                pass
            provider_rows.append(row)
        return {
            "has_data": True,
            "total_captured": total,
            "captured_24h": total_24h,
            "providers": sorted(
                provider_rows,
                key=lambda r: r["count"],
                reverse=True,
            ),
            "last_capture_iso": last_iso,
            "last_capture_ago_seconds": ago_seconds,
            "last_capture_ago_human": _humanize_ago(ago_seconds),
            # > 24h is the silent-breakage signal — capture host should
            # fire at least once a day on any active install. The
            # launchpad shows a warning border when this flips True.
            "stale": ago_seconds is not None and ago_seconds > 86400,
            "install_command": "trinity-local install-extension",
        }
    except Exception:
        return empty


def _browser_extension() -> dict:
    """Read the persisted Chrome extension ID written by install-extension.

    The file:// launchpad calls chrome.runtime.sendMessage(<extensionId>, ...)
    to dispatch button clicks. Without the ID, tier-1 dispatch is dead
    silent — there's no way to discover the ID from JS alone (the user
    has to load the unpacked extension manually, copy the 32-char ID, and
    feed it to `trinity-local install-extension --extension-id <ID>`).

    Returns `{"extensionId": str|None, "configured": bool}`. The launchpad's
    dispatch script gates on `configured`: if False, skip the extension
    probe and go straight to shortcut/install-prompt.
    """
    try:
        from . import state_paths as _sp
        settings_path = _sp.telemetry_settings_dir() / "extension.json"
        if not settings_path.exists():
            return {"extensionId": None, "configured": False}
        import json as _json
        data = _json.loads(settings_path.read_text())
        ext_id = data.get("extension_id")
        if isinstance(ext_id, str) and ext_id:
            return {"extensionId": ext_id, "configured": True}
        return {"extensionId": None, "configured": False}
    except Exception:
        return {"extensionId": None, "configured": False}


def dispatch_readiness() -> dict:
    """Snapshot of whether the Chrome extension dispatch path is wired up.

    Read by `trinity-local portal-html --open-browser` so the CLI can print
    a precise hint when the extension isn't configured. Same data the
    file:// launchpad surfaces in its banner. macOS Shortcut tier retired
    2026-05-17; the legacy fields (`shortcut_applicable`/`shortcut_installed`)
    are kept on the return dict as always-False so callers that read them
    don't crash.

    Returns:
        {
            "extension_configured": bool,
            "host_on_path": bool,
            "shortcut_applicable": False,  # retired; always False
            "shortcut_installed": False,   # retired; always False
            "ready": bool,                 # extension is wired
            "recommended_action": str|None,  # one-line hint, None when ready
        }
    """
    import shutil
    ext = _browser_extension()
    host_on_path = bool(shutil.which("trinity-local-capture-host"))
    ready = ext["configured"] and host_on_path

    recommendation: str | None = None
    if not ready:
        if ext["configured"] and not host_on_path:
            recommendation = (
                "Extension ID is configured but `trinity-local-capture-host` is "
                "not on PATH. Reinstall: `pip install -e .` (or `pip install "
                "trinity-local`) so the console script lands."
            )
        else:
            recommendation = (
                "No dispatch path active. Install the browser extension "
                "(chrome://extensions → Load unpacked → browser-extension/), "
                "then run `trinity-local install-extension --extension-id <ID>`."
            )

    return {
        "extension_configured": ext["configured"],
        "host_on_path": host_on_path,
        "shortcut_applicable": False,
        "shortcut_installed": False,
        "ready": ready,
        "recommended_action": recommendation,
    }


def _shortcut_status() -> dict:
    """Retired 2026-05-17 with the macOS Shortcut dispatcher kill, then
    deeper-cleaned in Pass B (commit 0555a25) when `canUseShortcut()`
    and the JS Tier-2 branch went away. Kept as a stable empty payload
    so `page_data["shortcutStatus"]` doesn't KeyError in any consumer.
    Always reports `applicable: False`; the launchpad banner stays
    hidden, and the JS dispatch path never tries the Shortcut tier
    because that branch no longer exists in launchpad_runtime.js.
    """
    return {"ok": True, "applicable": False}




def _core_status() -> dict:
    """Report the freshness of ~/.trinity/core.md vs the three thinking
    memories it actually distills (lens.md, topics.json, vocabulary.md
    per `distill.py`). picks + routing are scoreboards, NOT inputs to
    core.md — listing them here was a v1.7-collapse leak that fired
    false 'stale' warnings whenever a user rated a council. The
    launchpad surfaces this as a one-line hint so users notice when a
    fresh `distill` would help.

    Returns one of three states:
    - `{"state": "missing"}`  → core.md never built; lens/topics/... exist
    - `{"state": "stale"}`    → one or more source memories are newer
    - `{"state": "fresh"}`    → core.md is the newest of the bunch
    - `{"state": "empty"}`    → no memories present yet (cold install)
    """
    from .state_paths import (
        core_path, lens_path, topics_path, vocabulary_path,
    )
    core = core_path()
    # Must match `distill.py`'s source list — picks/routing are
    # scoreboards, not cognitive memory.
    sources = [lens_path(), topics_path(), vocabulary_path()]
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
    """Aggregate the nine staleness signals the launchpad surfaces:
      - core.md staleness (vs the three thinking memories) via _core_status
      - picks override_count > 0 (user-marked rules to demote)
      - picks audit_status == "disagreed" (chairman-audit caught drift)
      - topics.json prompt_ids round-trip integrity (legacy pre-thread-aware)
      - picks.json cortex freshness: councils newer than last consolidate
        (Pillar 3 drift surfacing — `ask` routes on stale rules until
        re-consolidate; doctor.py `_check_cortex_freshness` mirrors this)
      - lens.md pending user edits (#140 slice 3): live diff between
        current lens.md and the post-last-build snapshot. Surfaced so
        the user knows their hand-edits will be picked up by the next
        lens-build (closes the lens-edit-as-signal loop).
      - lenses.json same-horizon conflicts (#141 slice 3): Stage 4b
        detected pairs that privilege opposite poles of the same axis
        at the same horizon — real contradictions worth a meta-judgment
        rather than silent averaging.
      - extension capture-drift (#147): code-patch patterns where a
        provider's streaming endpoint regex no longer matches. Gives
        the "Repair extension" button a trigger so the user knows
        WHEN to click.
      - extension auth-cookie-stale (#150): user-action pattern where
        the provider's auth cookie expired. Hint points at manual
        login refresh (council dispatch wouldn't help — fix is
        browser-side).

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
    total = 9
    # 1. core.md freshness
    core = _core_status()
    state = core.get("state")
    if state == "stale":
        src = core.get("stale_source", "a source memory")
        issues.append({
            "name": "core.md",
            "status": "stale",
            "hint": f"{src} is newer than the distillation.",
            # --only-distill is the fast path: ~20s on a real install vs
            # ~5-15min for the full 5-phase dream. core.md is just the
            # distillation of the three upstream memories; if those are
            # current (which they usually are when only core.md is stale),
            # Phase 5 alone fixes it.
            "command": "trinity-local dream --only-distill",
            "href": None,
        })
    elif state == "missing":
        # Missing → no upstream memories may exist yet either. Safer to
        # run the full pipeline so the user gets a complete first-run.
        # --only-distill would write a thin core.md from empty inputs.
        issues.append({
            "name": "core.md",
            "status": "missing",
            "hint": "The singular core memory has not been compiled.",
            "command": "trinity-local dream",
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

    # 5. picks.json cortex freshness — councils newer than the last
    #    consolidate mean `ask` is routing on stale rules. Doctor's
    #    _check_cortex_freshness reports the same shape from the CLI
    #    side; this is the launchpad-facing surface so the user sees it
    #    without having to run `doctor`. Pillar 3 (drift surfacing)
    #    + Pillar 4 (supervision-signal moat — stale picks waste the
    #    verdict signal that just came in).
    try:
        from .state_paths import picks_path, council_outcomes_dir
        picks_p = picks_path()
        if picks_p.exists():
            picks_data = json.loads(picks_p.read_text(encoding="utf-8"))
            consolidated_ats: list[str] = []
            for entry in picks_data.values() if isinstance(picks_data, dict) else []:
                if isinstance(entry, dict):
                    ts = entry.get("consolidated_at")
                    if isinstance(ts, str):
                        consolidated_ats.append(ts)
            if consolidated_ats:
                freshest = max(consolidated_ats)
                outcomes_p = council_outcomes_dir()
                newer = 0
                for path in outcomes_p.glob("council_*.json") if outcomes_p.is_dir() else []:
                    try:
                        outcome = json.loads(path.read_text(encoding="utf-8"))
                    except (OSError, json.JSONDecodeError):
                        continue
                    created = outcome.get("created_at") or ""
                    if isinstance(created, str) and created > freshest:
                        newer += 1
                if newer > 0:
                    issues.append({
                        "name": "picks.json",
                        "status": "cortex-stale",
                        "hint": f"{newer} council(s) newer than the last consolidate — `ask` routes on stale rules.",
                        "command": "trinity-local consolidate",
                        "href": None,
                    })
    except Exception:
        pass  # cortex freshness check must never break launchpad

    # 6. lens.md pending edits — #140 slice 3. Live diff between current
    # lens.md and snapshot baseline. Not a "staleness" issue per se but
    # surfaced through the same channel: action-needed signal that
    # lens-build is the way to commit the user's edits into the corpus.
    try:
        from .me.lens_edits import pending_lens_edits_count

        pending = pending_lens_edits_count()
        if pending > 0:
            issues.append({
                "name": "lens.md",
                "status": "edits-pending",
                "hint": f"{pending} hand-edit(s) will be picked up by the next lens-build (weight=3.0, strongest signal).",
                "command": "trinity-local lens-build",
                "href": None,
            })
    except Exception:
        pass  # capture pipeline must not break launchpad rendering

    # 7. lenses.json same-horizon conflicts — #141 slice 3. Stage 4b
    # detected structural contradictions. Surfaced only when same-
    # horizon (real contradiction, not multi-resolution preference);
    # cross-horizon notes stay in lens.md but don't fire as launchpad
    # signal — #139 already handles them via lens weighting.
    try:
        from .me.conflicts import count_active_conflicts

        n_active = count_active_conflicts()
        if n_active > 0:
            issues.append({
                "name": "lenses.json",
                "status": "contradictions",
                "hint": f"{n_active} same-horizon contradiction(s) detected. See lens.md → ⚠ Tensions in tension.",
                "command": None,
                "href": "../portal_pages/memory.html?file=lens.md",
            })
    except Exception:
        pass  # detection must not break launchpad rendering

    # 8 + 9. Extension-repair patterns — #147/#150. The status CLI
    # already surfaces these; bringing them to the launchpad closes
    # the parity gap. Two signal kinds:
    #   - stale-auth-cookie (user-action): hint points at manual
    #     refresh; no auto-dispatch (login is on the user's side).
    #   - provider-extended-silence (code-patch): hint points at the
    #     auto-repair flow which the "Repair extension" button on this
    #     same card fires. Surfacing this signal gives that button a
    #     trigger — without it, the user doesn't know WHEN to click.
    try:
        from .commands.extension_repair import detect_failure_patterns, diagnose

        patterns = detect_failure_patterns(diagnose())
        code_patches = [p for p in patterns if p.get("fix_kind") == "code-patch"]
        user_actions = [p for p in patterns if p.get("fix_kind") == "user-action"]
        if code_patches:
            providers = ", ".join(p["provider"] for p in code_patches)
            issues.append({
                "name": "extension",
                "status": "capture-drift",
                "hint": (
                    f"{len(code_patches)} provider(s) with code-patch "
                    f"pattern ({providers}). Click 'Repair extension' "
                    f"above to dispatch the self-healing council "
                    f"(no HAR needed)."
                ),
                "command": "trinity-local extension repair --auto",
                "href": None,
            })
        if user_actions:
            providers = ", ".join(p["provider"] for p in user_actions)
            issues.append({
                "name": "extension",
                "status": "auth-cookie-stale",
                "hint": (
                    f"{len(user_actions)} provider(s) with stale auth "
                    f"({providers}). Log out + log back in to refresh — "
                    f"council dispatch wouldn't help (fix is browser-side)."
                ),
                "command": None,
                "href": None,
            })
    except Exception:
        pass  # extension diagnostic must not break launchpad rendering

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


def _load_decisions_by_id() -> dict:
    """Read `~/.trinity/me/decisions.jsonl` into a `{id: decision}` map.

    Each decision carries the privileged/sacrificed pair + verbatim
    quote that justified one lens claim. Returns {} when the file
    doesn't exist (cold install, lens-build never ran). Resilient to
    malformed lines — skips them rather than aborting the whole load.

    Surfaced on the launchpad lens card so every claim's
    `tension_decisions` IDs render as clickable backrefs to their
    source rejection pair. Traceability per principle #22 (empty
    callbacks swallow dispatch failures) + the README's "if it can't
    show its work, it doesn't get to claim the thought."
    """
    from .state_paths import trinity_home
    path = trinity_home() / "me" / "decisions.jsonl"
    if not path.exists():
        return {}
    out: dict = {}
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            did = d.get("id")
            if did:
                out[str(did)] = d
    except OSError:
        return {}
    return out


def _load_taste_lenses() -> dict | None:
    """Surface taste lenses for the launchpad.

    Prefers the new 5-stage pipeline output (`me/lenses.json`,
    `me/orderings.json`) which carries pole_a / pole_b / failure
    modes / spanned basins. Falls back to the legacy single-virtue
    parse when the pipeline hasn't run yet.

    Returns None when neither source has data — the launchpad shows
    an empty-state CTA pointing at `trinity-local lens-build`.
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
    # Traceability: load decisions.jsonl into a {id: {...}} map so the
    # launchpad lens card can render `tension_decisions` IDs as clickable
    # backrefs to the source rejection pairs that justify each lens claim.
    # Principle: "if it can't show its work, it doesn't get to claim the
    # thought." Schema per src/trinity_local/me/decisions.py — each
    # decision has id, privileged, sacrificed, valence, basin, verbatim,
    # prompt_id. Verbatim is the user's actual words from that moment.
    out["decisionsById"] = _load_decisions_by_id()
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


# In-process cache for topics.json — invalidated on (path, mtime) change.
# A single launchpad render calls into the helpers below 4× (cortex card,
# recent-card builder, both topology-helper consumers); without this we
# parse the file 4×. (path, mtime) key — not mtime alone — so test
# fixtures in different isolated_home dirs that happen to share the
# same second-level mtime don't leak cached basins across each other.
_TOPICS_BASINS_CACHE: tuple[str, float, list[dict]] | None = None


def _load_topics_basins() -> list[dict]:
    """Read topics.json once per (path, file-version); return basin list.

    Both `_topology_basin_labels` and `_task_to_topology_basin` need
    the same parsed payload — sharing keeps a single launchpad render
    from re-parsing the file 4×. Returns [] on any error so callers
    keep their existing graceful-degradation paths.
    """
    global _TOPICS_BASINS_CACHE
    try:
        from .state_paths import topics_path
        topics_p = topics_path()
        if not topics_p.exists():
            _TOPICS_BASINS_CACHE = None
            return []
        path_key = str(topics_p)
        mtime = topics_p.stat().st_mtime
        if (
            _TOPICS_BASINS_CACHE
            and _TOPICS_BASINS_CACHE[0] == path_key
            and _TOPICS_BASINS_CACHE[1] == mtime
        ):
            return _TOPICS_BASINS_CACHE[2]
        topics = json.loads(topics_p.read_text(encoding="utf-8"))
    except Exception:
        return []
    basins = topics.get("basins") or []
    _TOPICS_BASINS_CACHE = (path_key, mtime, basins)
    return basins


def _topology_basin_labels() -> dict[str, str]:
    """Return {basin_id: "term1 · term2 · term3"} from topics.json.

    Used by launchpad chips that deep-link to topology basins — the
    basin id "b03" alone is opaque, so the hover tooltip surfaces the
    basin's top TF-IDF terms. Same data the topology graph node label
    already shows, just made available to the launchpad's Vue chips.

    Returns {} when topics.json is missing or unparseable so chips
    keep working with their fallback "Open basin <id>" tooltip.
    """
    out: dict[str, str] = {}
    for b in _load_topics_basins():
        bid = b.get("id")
        if not bid:
            continue
        terms = b.get("top_terms") or []
        if terms:
            # Top-3 is enough for a hover tooltip; the full list lives
            # in the basin detail panel. Plain " · " separator matches
            # the topology view's label style.
            out[str(bid)] = " · ".join(str(t) for t in terms[:3])
    return out


def _safe_merge_summary() -> dict:
    """Return summarize_merges() output, falling back to a zero-filled
    dict if the import fails (cold install / circular dep). Keeps
    page_data shape stable across cold + warm installs."""
    try:
        from .merges import summarize_merges
        return summarize_merges()
    except Exception:
        return {
            "total": 0,
            "by_type": {},
            "by_signal_type": {},
            "first_ts": None,
            "last_ts": None,
        }


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
    except Exception:
        return {}
    try:
        patterns = load_routing_patterns()
    except Exception:
        patterns = None
    if not patterns:
        return {}
    basins = _load_topics_basins()
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
        # data-title powers the launchpad's client-side title search.
        # Lowercased once here so the JS substring match doesn't
        # recompute per keystroke. The per-card cross-memory chips
        # (→ pick / → routing / → topology / → share PNG) and the
        # "Unrated" badge were sunset 2026-05-21 along with the rest
        # of the user-rating UX. The card is now: title, winner, date.
        title_lower = str(item.get("title") or "").lower()
        return f"""
        <div class="council-card-wrapper" data-title="{_esc(title_lower)}" style="display: flex; flex-direction: column; gap: 8px;">
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
