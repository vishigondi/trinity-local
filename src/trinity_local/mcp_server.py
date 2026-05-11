"""MCP server exposing Trinity's canonical 6 tools.

Public tools, in lifecycle order:
  - route(task, harness, available_models, budget, latency)
      "Which model should I use?" — heuristic + k-NN, no model calls.
  - run_council(task, members, mode, sequence, responses)
      "Run the task across multiple models." — N+1 model calls.
      When `responses` is provided, skips member dispatch and goes straight
      to chairman synthesis (one model call). This is the verifier-shaped
      verdict path: agreed_claims, disagreed_claims, winner, routing_lesson.
  - record_outcome(council_run_id, user_winner, accepted, edited, ...)
      "Trinity, here's what actually happened." — closes the supervision loop.
  - search_prompts(query, top_k)
      "Find similar past prompts worth replaying." — memory search.
  - get_persona()
      "Return the user's /me document." — chairman context for any harness.
  - get_council_status(council_run_id)
      "Poll an in-flight or completed council." — for harnesses without fs access.

Internal helpers (get_status, get_elo, get_recent_councils, watch_once)
remain importable for the launchpad but are not exposed via MCP.
"""
from __future__ import annotations

import json
import sys
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import ErrorData, Tool

from .config import load_config
from .ranker import RoutingContext, build_default_ranker, predict_strongest_chairman, chairman_pick_reason

server = Server("trinity-local")


@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    return [
        Tool(
            name="route",
            description=(
                "Recommend a routing decision for a task: which model to use, whether to "
                "run a council, and how confident the recommendation is. Cheap and fast "
                "(no model calls). Call this BEFORE choosing a model. Use when you need "
                "to decide between providers, or when uncertainty about the right model "
                "for a task is the actual problem."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "task": {"type": "string", "description": "The user's prompt or task description"},
                    "harness": {"type": "string", "description": "Calling harness name (e.g. 'claude_code', 'codex')"},
                    "available_models": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Provider names available to this caller",
                    },
                    "budget": {"type": "string", "enum": ["low", "normal", "high"], "default": "normal"},
                    "latency": {"type": "string", "enum": ["fast", "normal", "patient"], "default": "normal"},
                    "current_provider": {"type": "string", "description": "Provider currently being used (optional)"},
                },
                "required": ["task"],
            },
        ),
        Tool(
            name="ask",
            description=(
                "Ask a single question and get one routed answer. Trinity routes via kNN over "
                "the user's past prompts (which model has historically won for similar questions), "
                "dispatches one call to the best provider, and returns a concise structured answer. "
                "Use for 90% of consults — quick second opinion, cross-provider check, dodging a "
                "rate limit on your own subscription.\n\n"
                "Returns: {answer, routed_to, trust_score (0..1), latency_ms, optional runner_up, "
                "optional escalate_hint='compare' when trust is low and you should consider calling "
                "`run_council` for parallel perspectives instead}.\n\n"
                "Cost: ~$0.01–0.05 typical, <2s. Single dispatched call, no flagship planning, "
                "no multi-model fan-out. If you genuinely need disagreement-vs-agreement structure, "
                "use `run_council` instead."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The user's question or task"},
                    "available_providers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Provider names allowed to route to (default: all enabled in config)",
                    },
                    "thread_id": {
                        "type": "string",
                        "description": "Optional. Carries context across related calls (working memory).",
                    },
                    "top_k": {"type": "integer", "default": 5, "description": "How many past prompts to retrieve for the vote"},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="run_council",
            description=(
                "Launch a multi-provider comparison for the user's task. Use when the user "
                "asks for a second opinion or a council, or when route() returned mode='council'. "
                "Supports parallel mode (default; members run simultaneously) and chain mode "
                "(sequential refinement, each model refines the prior). Returns the council_run_id "
                "and the path to the live review page; the council runs asynchronously.\n\n"
                "When `responses` is provided (pre-supplied member outputs), skips member dispatch "
                "and goes straight to chairman synthesis — one model call instead of N+1. This is "
                "the verifier-shaped verdict path. Use when you ALREADY HAVE multiple model outputs "
                "and just want the structured verdict (agreed_claims, disagreed_claims, winner, "
                "routing_lesson, eval_seed)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "task": {"type": "string"},
                    "goal": {"type": "string", "default": "Find the strongest answer."},
                    "members": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Provider names (e.g. ['claude', 'gemini', 'codex']). Omit to use the default 3-member lineup.",
                    },
                    "mode": {"type": "string", "enum": ["parallel", "chain"], "default": "parallel"},
                    "sequence": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "For mode='chain': the ordered provider sequence. Defaults to members.",
                    },
                    "primary_provider": {"type": "string", "description": "Chairman/synthesizer. Auto-selected if omitted."},
                    "responses": {
                        "type": "array",
                        "description": (
                            "Pre-supplied member outputs. When present, skips member dispatch "
                            "and runs chairman synthesis only (verifier-shaped verdict)."
                        ),
                        "items": {
                            "type": "object",
                            "properties": {
                                "provider": {"type": "string"},
                                "content": {"type": "string"},
                                "model": {"type": "string"},
                            },
                            "required": ["provider", "content"],
                        },
                    },
                    "wait_seconds": {
                        "type": "number",
                        "default": 0,
                        "description": (
                            "If > 0, block up to this many seconds waiting for the council to "
                            "finish; if it completes in time, the outcome (winner, agreed/disagreed "
                            "claims, routing_lesson) is returned inline. Otherwise returns the "
                            "council_run_id immediately and the caller polls get_council_status. "
                            "Useful when the council is likely cached or fast — saves a round trip. "
                            "Ignored when `responses` is provided (synthesis is always inline)."
                        ),
                    },
                },
                "required": ["task"],
            },
        ),
        Tool(
            name="record_outcome",
            description=(
                "Closes the supervision loop. After the user has acted on a council's output, "
                "report what actually happened: which provider was selected, whether the user "
                "accepted/edited it, cost, latency. THIS IS THE MOST IMPORTANT TOOL — without "
                "it, Trinity is just a switchboard. "
                "If the user abandoned the council without picking a winner (e.g. a member "
                "hung or the user lost interest), pass `accepted=false` and omit `user_winner`. "
                "Abandonment is a valid signal."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "council_run_id": {"type": "string"},
                    "user_winner": {"type": "string", "description": "Provider the user actually picked. Omit when abandoned."},
                    "accepted": {"type": "boolean"},
                    "edited": {"type": "boolean"},
                    "tests_passed": {"type": "boolean"},
                    "cost_usd": {"type": "number"},
                    "latency_sec": {"type": "number"},
                    "answer_label": {"type": "string", "description": "Optional UI label for the chosen answer"},
                    "abandonment_reason": {"type": "string", "description": "Optional: why the user didn't pick a winner (e.g. 'codex hung', 'lost interest')"},
                },
                "required": ["council_run_id"],
            },
        ),
        Tool(
            name="search_prompts",
            description=(
                "Find past prompts worth replaying. Ranks by substring/token overlap with the "
                "query plus replay-value heuristics (recency, theme tags, prior council count, "
                "user-override signal). No embedding model is loaded — this is a fast, "
                "deterministic keyword + recency match across the user's full AI history "
                "(Claude Code, Codex, Gemini, ChatGPT, Claude.ai). Use when the user starts "
                "typing and you want to suggest replay candidates."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "top_k": {"type": "integer", "default": 8},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="get_persona",
            description=(
                "Return the user's /me profile — a markdown doc built by a chairman call over "
                "sampled prompt history (the user's actual conversations across providers). Pull "
                "this once at session start and use it as latent context to tailor responses, "
                "terseness, vocabulary, and standing decisions to THIS user. Empty string when not "
                "built — run `trinity-local me-build` to (re)build."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="get_council_status",
            description=(
                "Poll an in-flight or completed council by `council_run_id` (returned from "
                "run_council). Returns: status (running/completed/failed/canceled), per-member "
                "progress, chairman synthesis state, elapsed seconds, and the final outcome "
                "summary (winner, agreed/disagreed claims, routing_lesson) when complete. "
                "Use this to wait on async councils without filesystem access."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "council_run_id": {"type": "string"},
                },
                "required": ["council_run_id"],
            },
        ),
    ]


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict | None) -> list[Any]:
    arguments = arguments or {}
    try:
        if name == "ask":
            return await _ask(arguments)
        if name == "route":
            return await _route(arguments)
        if name == "run_council":
            return await _run_council(arguments)
        if name == "record_outcome":
            return await _record_outcome(arguments)
        if name == "search_prompts":
            return await _search_prompts(arguments)
        if name == "get_persona":
            return await _get_persona(arguments)
        if name == "get_council_status":
            return await _get_council_status(arguments)
        return [ErrorData(code=404, message=f"Tool not found: {name}")]
    except Exception as exc:
        return [ErrorData(code=500, message=f"{type(exc).__name__}: {exc}")]


def _text(payload: dict | str) -> dict:
    """Wrap a JSON-serializable result as an MCP text response."""
    body = payload if isinstance(payload, str) else json.dumps(payload, indent=2, default=str)
    return {"type": "text", "text": body}


def _dispatch_via_config(provider_name: str, prompt: str) -> str:
    """Production dispatch shim used by `ask`. Looks up the named provider in
    config first; if not found, falls through to detected Ollama models
    (provider_name="ollama:<model>"). Errors raise; the MCP handler catches
    them and returns an error response so Claude in the harness knows the
    route failed and can retry / replan.
    """
    from pathlib import Path

    from .config import load_config
    from .providers import make_provider, ProviderError

    config = load_config()
    # config.providers is a dict keyed by name; iterate values for ProviderConfig
    # objects with .enabled and .name attributes.
    for p in config.providers.values():
        if p.name == provider_name and p.enabled:
            provider = make_provider(p)
            result = provider.run(prompt, Path.cwd())
            if result.returncode != 0:
                raise ProviderError(f"{provider_name} exit {result.returncode}: {result.stderr[:200]}")
            return result.stdout

    # Fall through: maybe this is a detected local model, e.g. "ollama:qwen3:32b".
    if provider_name.startswith("ollama:"):
        return _dispatch_to_ollama_model(provider_name, prompt)

    raise ProviderError(f"Provider not configured or not enabled: {provider_name}")


def _dispatch_to_ollama_model(provider_name: str, prompt: str) -> str:
    """Build an ephemeral ProviderConfig for a detected Ollama model and run.
    `provider_name` shape is `ollama:<model_name>` (the LocalModel.provider_name
    stable identifier from local_models.py)."""
    from pathlib import Path
    from .config import ProviderConfig
    from .providers import OllamaProvider, ProviderError

    model = provider_name[len("ollama:"):]
    cfg = ProviderConfig(
        name=provider_name,
        type="ollama",
        enabled=True,
        label=f"Ollama {model}",
        command=["ollama"],
        args=[],
        roles=set(),
        task_kinds=set(),
        model=model,
    )
    provider = OllamaProvider(cfg)
    result = provider.run(prompt, Path.cwd())
    if result.returncode != 0:
        raise ProviderError(f"{provider_name} exit {result.returncode}: {result.stderr[:200]}")
    return result.stdout


def _full_provider_pool() -> list[str]:
    """Build the available-provider pool: enabled config providers + detected
    local Ollama models, with currently-unhealthy providers demoted to the
    end. The Conductor / ask uses this when the caller doesn't pass an
    explicit `available_providers` list.

    Demotion (not exclusion) preserves the option for routing to fall back to
    an unhealthy provider when nothing else fits, while keeping it from being
    the first choice. Unhealthy = recent rate-limit / billing / auth failure
    within the decay window — see dispatch_health.py.
    """
    from .config import load_config
    from .dispatch_health import unhealthy_providers
    from .local_models import detect_local_models

    pool: list[str] = []
    try:
        config = load_config()
        for p in config.providers.values():
            if p.enabled:
                pool.append(p.name)
    except Exception:
        pass
    try:
        for m in detect_local_models():
            pool.append(m.provider_name)
    except Exception:
        pass

    # Demote unhealthy providers to the end (preserve relative order otherwise).
    try:
        unhealthy = unhealthy_providers()
    except Exception:
        unhealthy = set()
    if unhealthy:
        healthy = [p for p in pool if p not in unhealthy]
        sick = [p for p in pool if p in unhealthy]
        pool = healthy + sick

    return pool


async def _ask(args: dict) -> list[Any]:
    """Handle mcp__trinity-local__ask. Routes via kNN + dispatches once.
    See `src/trinity_local/ask.py` for orchestration logic.
    """
    from .ask import run_ask

    query = args.get("query")
    if not query or not isinstance(query, str):
        return [ErrorData(code=400, message="`query` is required and must be a string")]

    available = args.get("available_providers")
    if available is not None and not isinstance(available, list):
        return [ErrorData(code=400, message="`available_providers` must be a list of provider names")]
    # When caller doesn't specify available_providers, default to the full
    # pool (config providers + detected local models). This is what makes
    # ask aware of Ollama / MLX without each call having to declare them.
    if available is None:
        available = _full_provider_pool()

    top_k = int(args.get("top_k", 5))
    # thread_id is accepted but not yet used in week-1 — wired in week-2.
    _thread_id = args.get("thread_id")

    try:
        result = run_ask(
            query,
            dispatch_fn=_dispatch_via_config,
            top_k=top_k,
            available_providers=available,
        )
    except Exception as exc:
        return [ErrorData(code=502, message=f"dispatch_failed: {type(exc).__name__}: {exc}")]

    return [_text(result.to_dict())]


async def _route(args: dict) -> list[Any]:
    task = args["task"]
    # Distinguish absent from explicitly empty. `available_models=[]` is the
    # caller signaling "no providers are available" — we should error rather
    # than silently picking from defaults.
    if "available_models" in args:
        available = args.get("available_models")
        if not isinstance(available, list):
            return [_text({"ok": False, "error": "`available_models` must be a list of provider names"})]
        if not available:
            return [_text({"ok": False, "error": "`available_models` is empty — no providers to route to"})]
    else:
        available = ["claude", "gemini", "codex"]
    current_provider = args.get("current_provider") or available[0]
    budget_pref = (args.get("budget") or "normal").lower()
    latency_pref = (args.get("latency") or "normal").lower()

    from .ranker import prompt_calls_for_council
    from .task_kinds import guess_task_kind

    chairman_pick = chairman_pick_reason(task, available_providers=available)
    task_kind = chairman_pick.get("task_kind") or guess_task_kind(task)

    decision = None
    try:
        ranker = build_default_ranker()
        decision = ranker.advise(RoutingContext(
            task_text=task,
            task_kind=task_kind,
            current_provider=current_provider,
            session_id="mcp_route",
            metadata={"budget": budget_pref, "latency": latency_pref},
        ))
    except Exception:
        decision = None

    # Map RoutingDecision → MCP shape. The ranker exposes `needs_council`
    # (bool) and `top_k` (ordered providers); the spec promises `mode` and
    # `challenger`. Without this mapping, route() would silently return
    # mode="single" for every task — defeating "council on disagreement."
    decision_needs_council = bool(getattr(decision, "needs_council", False))
    decision_top_k = list(getattr(decision, "top_k", []) or [])
    decision_confidence_raw = getattr(decision, "confidence", None)
    decision_evidence = getattr(decision, "evidence", []) or []

    base_mode = "council" if decision_needs_council else "single"
    base_confidence = _confidence_band(decision_confidence_raw)
    if decision_evidence:
        base_reason = "; ".join(decision_evidence[:2])
    else:
        base_reason = f"chairman picked from {chairman_pick.get('source', 'default')}"

    # Latency-aware demotion: when the caller asked for latency='fast', the
    # strongest-on-quality provider (codex+gpt-5.5 xhigh) is the wrong pick —
    # it takes 30s+. Prefer claude/gemini if either is available.
    fast_demoted = False
    primary_pick = chairman_pick.get("chairman") or available[0]
    if latency_pref == "fast" and primary_pick == "codex":
        fast_alt = next((p for p in ("claude", "gemini") if p in available), None)
        if fast_alt:
            primary_pick = fast_alt
            fast_demoted = True

    # Prompt-shape escalation: if the task literally contains "A) ... B) ..."
    # numbered alternatives, "vs.", "which is best", "tradeoffs", etc., the
    # user is asking for a comparison — escalate to mode=council regardless
    # of what task_kind says. Single-answer routing on a multi-candidate
    # prompt under-recommends council and starves the personal routing table.
    council_signals: list[str] = []
    escalate, council_signals = prompt_calls_for_council(task)
    if escalate:
        mode = "council"
        confidence = "high"
        reason = f"prompt shape suggests comparison: {', '.join(council_signals)}"
    else:
        mode = base_mode
        confidence = base_confidence
        reason = base_reason

    # Challenger: ranker top_k[1] when distinct from primary AND in the
    # caller-supplied available_models. Pre-fix, the ranker could return
    # `challenger="codex"` even when `available_models=["claude"]` — useless
    # advice. Always filter through `available`.
    challenger = next(
        (p for p in decision_top_k if p != primary_pick and p in available),
        next((p for p in available if p != primary_pick), None),
    )
    # If only one provider is actually available, force mode="single" — there
    # IS no second opinion to be had, so reporting mode="council" is a lie.
    if len(available) < 2:
        mode = "single"
        challenger = None

    if fast_demoted:
        reason = f"{reason}; latency=fast → demoted codex"

    payload = {
        "mode": mode,
        "primary": primary_pick,
        "challenger": challenger,
        "confidence": confidence,
        "reason": reason,
        "task_kind": task_kind,
        "chairman_source": chairman_pick.get("source", "default_order"),
        "shape_signals": council_signals,
        "budget": budget_pref,
        "latency": latency_pref,
        "should_auto_council": mode == "council",
    }
    return [_text(payload)]


def _confidence_band(raw) -> str:
    """Normalize a 0..1 ranker confidence (or string) into 'high'/'medium'/'low'.

    The MCP `route()` schema declares confidence as a string enum, but
    `RoutingDecision.confidence` is a 0..1 float. Without this normalizer the
    payload leaked floats like 0.72 into the contract.
    """
    if isinstance(raw, str):
        if raw in ("high", "medium", "low"):
            return raw
        return "medium"
    # bool subclasses int — `float(True) == 1.0` would silently coerce a
    # malformed bool confidence into "high". Reject explicitly.
    if isinstance(raw, bool):
        return "medium"
    try:
        f = float(raw) if raw is not None else 0.5
    except (TypeError, ValueError):
        f = 0.5
    if f >= 0.75:
        return "high"
    if f >= 0.55:
        return "medium"
    return "low"


async def _synthesize_responses(args: dict, responses: list[dict]) -> list[Any]:
    """Chairman-only synthesis over pre-supplied member responses.

    Equivalent to running a council where members already executed; we skip
    the dispatch and feed the chairman directly. One model call (chairman)
    instead of N+1. Returns the verifier-shaped Routing JSON inline.
    """
    from .council_runtime import (
        create_council_outcome,
        create_prompt_bundle,
        parse_routing_label,
        render_primary_council_prompt,
        save_council_outcome,
        save_prompt_bundle,
    )
    from .council_schema import CouncilMemberResult
    from .providers import make_provider
    from .utils import stable_id

    task = args["task"]
    members = [
        CouncilMemberResult(
            provider=str(r.get("provider", "unknown")),
            model=r.get("model"),
            output_text=str(r.get("content", "")),
            metadata={"source": "mcp_synthesis"},
        )
        for r in responses
    ]

    # Pick the chairman from ENABLED LOCAL providers — not from the
    # caller-supplied response provider labels. The labels can be arbitrary
    # ("answer_a", "external", "judge_v2") and don't have to match a Trinity
    # provider config. Use the labels only for display/scoring; chair from
    # the user's actual provider lineup.
    config = load_config()
    enabled = [
        name for name, p in (config.providers if config else {}).items()
        if p.enabled and p.type in ("cli", "codex")
    ] or ["claude"]
    chairman = args.get("primary_provider") or predict_strongest_chairman(
        task, available_providers=enabled
    )
    chairman_config = config.providers.get(chairman) if chairman in (config.providers if config else {}) else None
    if chairman_config is None or not chairman_config.enabled:
        return [_text({
            "ok": False,
            "error": f"Chairman provider '{chairman}' missing or disabled in Trinity config",
        })]

    bundle = create_prompt_bundle(
        task_cluster_id=stable_id("cluster", "mcp_synthesis", task[:400]),
        task_text=task,
        goal=args.get("goal") or "Synthesize the strongest answer from these responses.",
        origin_provider="mcp_run_council",
    )
    save_prompt_bundle(bundle)

    synthesis_prompt = render_primary_council_prompt(bundle, members)
    primary = make_provider(chairman_config)
    try:
        # cwd is required by the runtime (subprocess.run cwd= can't be None)
        from pathlib import Path
        result = primary.run(synthesis_prompt, cwd=Path.cwd())
    except Exception as exc:
        return [_text({"ok": False, "error": f"Chairman call failed: {exc}"})]

    synthesis_output = result.stdout or result.stderr or ""
    routing_label, parse_error = parse_routing_label(synthesis_output)

    # Surface the chairman's verdict on the outcome itself, not just inside
    # the routing_label. Without `winner_provider`, downstream consumers
    # (record_outcome, personal_routing aggregation) can't tell who won.
    winner_from_label = getattr(routing_label, "winner", None) if routing_label else None
    outcome_metadata: dict = {"mode": "synthesis_only"}
    if parse_error:
        outcome_metadata["routing_label_error"] = parse_error
    outcome = create_council_outcome(
        bundle=bundle,
        primary_provider=chairman,
        member_results=members,
        primary_model=chairman_config.model,
        synthesis_output=synthesis_output,
        synthesis_prompt=synthesis_prompt,
        routing_label=routing_label,
        winner_provider=winner_from_label,
        metadata=outcome_metadata,
    )
    outcome_path = save_council_outcome(outcome)

    payload: dict = {
        "ok": True,
        "council_run_id": outcome.council_run_id,
        "mode": "synthesis_only",
        "synthesis_output": synthesis_output,
        "_local_paths": {"outcome_path": str(outcome_path)},
    }
    if routing_label:
        payload["winner"] = routing_label.winner
        payload["runner_up"] = routing_label.runner_up
        payload["confidence"] = routing_label.confidence
        payload["agreed_claims"] = routing_label.agreed_claims
        payload["disagreed_claims"] = routing_label.disagreed_claims
        payload["routing_lesson"] = routing_label.routing_lesson
        payload["eval_seed"] = routing_label.eval_seed
    elif parse_error:
        payload["routing_label_error"] = parse_error
    return [_text(payload)]


async def _run_council(args: dict) -> list[Any]:
    # Pre-supplied responses → chairman synthesis only. One model call instead
    # of N+1. Same outcome shape (verifier-shaped Routing JSON), persisted as
    # a CouncilOutcome so subsequent record_outcome calls can attach.
    #
    # Distinguish "absent" from "explicitly empty": passing responses=[] is a
    # caller error (they intended to invoke the synthesis path with N candidates
    # and ended up with zero). Reject loudly rather than silently launching a
    # full provider council on an empty list.
    if "responses" in args:
        responses = args.get("responses")
        if not isinstance(responses, list):
            return [_text({"ok": False, "error": "`responses` must be a list of {provider, content} objects"})]
        if not responses:
            return [_text({"ok": False, "error": "`responses` is empty — pass at least one {provider, content} entry"})]
        # Validate each entry has required fields before any dispatch
        for i, r in enumerate(responses):
            if not isinstance(r, dict) or "content" not in r or "provider" not in r:
                return [_text({"ok": False, "error": f"`responses[{i}]` must contain 'provider' and 'content' fields"})]
        return await _synthesize_responses(args, responses)

    from .commands.council import handle_council_launch
    from types import SimpleNamespace
    import asyncio
    import contextlib
    import io
    import time

    task = args["task"]
    goal = args.get("goal", "Find the strongest answer.")
    members = args.get("members") or ["claude", "gemini", "codex"]
    mode = args.get("mode", "parallel")
    sequence = args.get("sequence")
    primary_provider = args.get("primary_provider")
    wait_seconds = float(args.get("wait_seconds") or 0)

    if mode not in ("parallel", "chain"):
        return [_text({"ok": False, "error": f"unknown mode: {mode}"})]

    launch_args = SimpleNamespace(
        config=None,
        task=task,
        goal=goal,
        instructions="Prefer the strongest answer for the user's current task.",
        context_file=None,
        project_hint="",
        members=members if mode == "parallel" else (sequence or members),
        primary_provider=primary_provider,
        # CRITICAL: thread mode + sequence into launch_args so handle_council_launch
        # can propagate them to handle_council_start → run_council. Without these,
        # MCP `run_council(mode="chain")` was reaching the runner as parallel
        # while the response said "mode": "chain" — the silent-dispatch bug
        # the verification council caught.
        mode=mode,
        sequence=sequence,
        cwd=".",
        status_token=None,
        open_browser=False,
        notify=False,
    )

    # handle_council_launch prints a JSON record with both the council_run_id
    # (what MCP callers need) and several local filesystem paths (launchpad
    # implementation detail). Capture, parse, and project to a clean shape.
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            handle_council_launch(launch_args)
    except SystemExit as exc:
        return [_text({"ok": False, "error": f"council exited: {exc}"})]

    captured = buf.getvalue().strip()
    raw: dict = {}
    if captured:
        try:
            raw = json.loads(captured)
        except json.JSONDecodeError:
            return [_text({"ok": False, "error": "council launch produced unparseable output", "raw": captured})]

    council_run_id = raw.get("council_run_id")
    if not council_run_id:
        return [_text({"ok": False, "error": "council launch did not return a council_run_id", "raw": raw})]

    response: dict = {
        "ok": True,
        "council_run_id": council_run_id,
        "mode": mode,
        # Local filesystem artifacts — useful for the CLI / launchpad, opaque
        # to MCP callers. Nested under `_local_paths` so harnesses can ignore.
        "_local_paths": {
            "task_path": raw.get("task_path"),
            "sync_path": raw.get("sync_path"),
            "review_path": raw.get("review_path"),
            "review_action_path": raw.get("review_action_path"),
        },
    }

    # Optional inline-wait. Polls the status file every 750ms until either
    # the council reports completed/failed/canceled, or the budget expires.
    if wait_seconds > 0:
        from .council_runtime import load_council_outcome
        from .state_paths import council_outcomes_dir

        deadline = time.monotonic() + wait_seconds
        completed_status: dict | None = None
        while time.monotonic() < deadline:
            # Use the same lookup-with-fallback logic as `_get_council_status`:
            # the live status file is keyed by status token (often the
            # bundle_id, not the council_run_id). Without the fallback scan,
            # wait_seconds could time out on a council that already completed.
            status_payload = _lookup_council_status(council_run_id)
            current = (status_payload or {}).get("status")
            if current in ("completed", "failed", "canceled"):
                completed_status = status_payload
                break
            # Belt-and-suspenders: a completed outcome JSON also resolves the
            # wait, even if the live status file lags or never got written.
            outcome_path = council_outcomes_dir() / f"{council_run_id}.json"
            if outcome_path.exists():
                completed_status = status_payload or {"status": "completed"}
                break
            await asyncio.sleep(0.75)

        if completed_status is not None:
            outcome_summary = None
            outcome_path = council_outcomes_dir() / f"{council_run_id}.json"
            if outcome_path.exists():
                try:
                    outcome = load_council_outcome(council_run_id)
                    label = outcome.routing_label
                    outcome_summary = {
                        "winner": outcome.winner_provider,
                        "primary_provider": outcome.primary_provider,
                        "primary_model": outcome.primary_model,
                        "synthesis_output": outcome.synthesis_output,
                        "agreed_claims": list(getattr(label, "agreed_claims", []) or []) if label else [],
                        "disagreed_claims": list(getattr(label, "disagreed_claims", []) or []) if label else [],
                        "routing_lesson": getattr(label, "routing_lesson", "") if label else "",
                        "user_likely_values": list(getattr(label, "user_likely_values", []) or []) if label else [],
                    }
                except Exception:
                    outcome_summary = None
            response["status"] = completed_status.get("status")
            response["outcome"] = outcome_summary
        else:
            response["status"] = "running"
            response["timed_out_after_seconds"] = wait_seconds

    return [_text(response)]


async def _record_outcome(args: dict) -> list[Any]:
    from .council_feedback import append_council_feedback
    from .council_runtime import load_council_outcome, save_council_outcome
    from .memory import record_council_outcome as memory_record_outcome

    council_run_id = args["council_run_id"]
    user_winner = args.get("user_winner")  # optional — abandonment is valid
    abandoned = user_winner is None

    # Sensible default: providing a user_winner means the user accepted that
    # answer; omitting it means the council was abandoned. Caller can still
    # override explicitly. Drops the cognitive load on the common "thumbs-up"
    # call: record_outcome(council_run_id, user_winner="codex") is enough.
    if "accepted" in args:
        accepted = args["accepted"]
    else:
        accepted = not abandoned

    feedback = None
    if not abandoned:
        feedback = append_council_feedback(
            council_id=council_run_id,
            provider=user_winner,
            answer_label=args.get("answer_label"),
        )

    # Update the persisted CouncilOutcome with verdict metadata. Only include
    # fields the caller actually provided — avoid clobbering with None.
    try:
        outcome = load_council_outcome(council_run_id)
    except Exception:
        outcome = None
    if outcome is not None:
        outcome.metadata.setdefault("user_verdict", {})
        verdict = {
            "user_winner": user_winner,
            "accepted": accepted,
            "abandoned": abandoned,
        }
        for optional_key in ("edited", "tests_passed", "cost_usd", "latency_sec", "abandonment_reason"):
            if optional_key in args:
                verdict[optional_key] = args[optional_key]
        outcome.metadata["user_verdict"].update(verdict)
        save_council_outcome(outcome)

        # Propagate to PromptNode if the bundle linked one. For abandonments
        # we still record the chairman_winner (so the personal table reflects
        # what the chairman thought) but no user_winner.
        prompt_node_id = (outcome.metadata or {}).get("prompt_node_id")
        if isinstance(prompt_node_id, str) and prompt_node_id:
            chairman = outcome.routing_label.winner if outcome.routing_label else None
            memory_record_outcome(
                prompt_node_id=prompt_node_id,
                council_run_id=council_run_id,
                chairman_winner=chairman,
                user_winner=user_winner,  # None when abandoned — that's fine
            )

    return [_text({
        "ok": True,
        "feedback": feedback,
        "outcome_updated": outcome is not None,
        "abandoned": abandoned,
    })]


async def _search_prompts(args: dict) -> list[Any]:
    from .memory import search_prompt_nodes

    query = args["query"]
    top_k = int(args.get("top_k") or 8)
    raw_results = search_prompt_nodes(query, top_k=top_k)

    # Confidence + filtering at the API level. Surface tokens like "MCP" or
    # "cursor" can produce 0.5-0.6 prompt_similarity for prompts that are
    # totally off-topic. The harness shouldn't have to filter; we know
    # enough to filter for them.
    sims = [float(r.prompt_similarity or 0.0) for r in raw_results]
    top_sim = max(sims) if sims else 0.0
    if top_sim >= 0.78:
        confidence = "high"
        # Keep everything when the top match is solid — even 0.5 results
        # may have value in this case (related but not duplicate).
        threshold = 0.55
    elif top_sim >= 0.65:
        confidence = "medium"
        threshold = 0.65
    else:
        confidence = "low"
        threshold = 999.0  # drop everything; the query has no good match

    filtered = [r for r in raw_results if float(r.prompt_similarity or 0.0) >= threshold]
    dropped_count = len(raw_results) - len(filtered)

    payload = {
        "query": query,
        "confidence": confidence,
        "top_similarity": round(top_sim, 3),
        "results_filtered_out": dropped_count,
        "guidance": (
            "high → safe to suggest as replay candidates; "
            "medium → results above 0.65 similarity returned; "
            "low → no results meet the relevance bar; do not inject anything as context"
        ),
        "results": [
            {
                "prompt_id": r.prompt_id,
                "text": r.text,
                "score": r.score,
                "prompt_similarity": r.prompt_similarity,
                "reasons": list(r.reasons or []),
                "chairman_winner": r.chairman_winner,
                "user_winner": r.user_winner,
                "council_count": r.council_count,
                "provider": r.provider,
                "timestamp": r.timestamp,
            }
            for r in filtered
        ],
    }
    return [_text(payload)]


async def _get_persona(args: dict) -> list[Any]:
    from .me_builder import load_me, me_path
    from .config import trinity_home

    text = load_me()
    home = trinity_home()
    path = me_path()
    # Symbolic relative path so consumers don't bake user-specific absolutes
    # into their state. The harness can still use `path` if it has fs access.
    try:
        relative_path = "$TRINITY_HOME/" + str(path.relative_to(home))
    except ValueError:
        relative_path = str(path)
    return [_text({
        "path": str(path),
        "trinity_home_relative": relative_path,
        "size_chars": len(text),
        "text": text,
        "available": bool(text),
    })]


def _lookup_council_status(council_run_id: str) -> dict | None:
    """Find the live status file for a council, regardless of which token
    keyed it. Status files live at portal_pages/status/council_status_<token>.json
    and the token is often the bundle_id, not the council_run_id, so a direct
    lookup misses. Falls back to a scan that matches on `council_id`.
    """
    from .council_status import load_council_status
    from .state_paths import council_status_dir

    payload: dict | None = load_council_status(council_run_id)
    if payload is not None:
        return payload
    for path in council_status_dir().glob("council_status_*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if data.get("council_id") == council_run_id:
            return data
    return None


async def _get_council_status(args: dict) -> list[Any]:
    from .council_runtime import load_council_outcome
    from .state_paths import council_outcomes_dir

    council_run_id = args["council_run_id"]

    # Two storage locations:
    #   - council_outcomes/<id>.json: written ONCE on completion, durable
    #   - portal_pages/status/council_status_<token>.json: updated live during the run
    # `_lookup_council_status` handles both the direct-key and fallback-scan
    # cases; the wait_seconds polling path uses the same helper.
    status_payload: dict | None = _lookup_council_status(council_run_id)

    outcome_summary: dict | None = None
    outcome_path = council_outcomes_dir() / f"{council_run_id}.json"
    if outcome_path.exists():
        try:
            outcome = load_council_outcome(council_run_id)
            label = outcome.routing_label
            outcome_summary = {
                "winner": outcome.winner_provider,
                "primary_provider": outcome.primary_provider,
                "primary_model": outcome.primary_model,
                "synthesis_output": outcome.synthesis_output,
                "agreed_claims": list(getattr(label, "agreed_claims", []) or []) if label else [],
                "disagreed_claims": list(getattr(label, "disagreed_claims", []) or []) if label else [],
                "routing_lesson": getattr(label, "routing_lesson", "") if label else "",
                "user_likely_values": list(getattr(label, "user_likely_values", []) or []) if label else [],
                "member_count": len(outcome.member_results),
            }
        except Exception:
            outcome_summary = None

    if status_payload is None and outcome_summary is None:
        return [_text({
            "council_run_id": council_run_id,
            "status": "unknown",
            "error": "no live status file or completed outcome found",
        })]

    # Compress live status to a small per-member summary.
    members_summary: dict | None = None
    if status_payload:
        members = status_payload.get("members") or {}
        members_summary = {
            provider: {
                "status": info.get("status"),
                "model": info.get("model"),
                "response_chars": len(info.get("response_text") or ""),
            }
            for provider, info in members.items()
        }

    return [_text({
        "council_run_id": council_run_id,
        "status": (status_payload or {}).get("status") or ("completed" if outcome_summary else "unknown"),
        "task_text": (status_payload or {}).get("task_text"),
        "members": members_summary,
        "synthesis_status": ((status_payload or {}).get("synthesis") or {}).get("status"),
        "review_path": (status_payload or {}).get("review_path"),
        "outcome": outcome_summary,
    })]


async def run_stdio_server():
    # Dev mode: watch source tree for edits and exit on change so the MCP
    # launcher respawns with fresh code. No-op when TRINITY_MCP_WATCH is unset.
    from .mcp_watchdog import start_watchdog_if_enabled

    start_watchdog_if_enabled()

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )
