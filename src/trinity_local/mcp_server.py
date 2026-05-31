"""MCP server exposing Trinity's canonical 4 tools + v1.5 trio + provider-loop tool.

Public tools, in lifecycle order:
  - route(task, harness, available_models, budget, latency)
      "Which model should I use?" — heuristic + k-NN, no model calls.
  - run_council(task, members, mode, sequence, responses)
      "Run the task across multiple models." — N+1 model calls.
      When `responses` is provided, skips member dispatch and goes straight
      to chairman synthesis (one model call). This is the structured
      verdict path: agreed_claims, disagreed_claims, winner, routing_lesson.
  - get_persona()
      "Return the user's /me document." — chairman context for any harness.
  - get_council_status(council_run_id)
      "Poll an in-flight or completed council." — for harnesses without fs access.

v1.5 trio: ask / get_picks / mark_pick_wrong.
In-protocol provider loop: import_provider_memory.

Plus MCP Resources (v2 substrate, 2026-05-26) for read-only context:
~/.trinity/memories/*, ~/.trinity/scoreboard/* exposed as
trinity:// URIs that the harness lists at session handshake.

Note: record_outcome retired 2026-05-21. CLI council-rate followed
on 2026-05-22 (task #134 — full rating retirement). Chairman's pick
(routing_label.winner) is the entire supervision signal now;
refinement prompts on the council page carry the "what user wanted
differently" signal inline.

handoff MCP tool retired 2026-05-26 alongside the CLI verb (0 usage
events in 163 launch_events on the dogfooder's machine; deprioritized
as primary demo earlier in the same session; spec v2 makes the lens-via-
MCP-Resources path the primary cross-provider continuity surface).

Internal helpers (get_status, get_elo, get_recent_councils, watch_once)
remain importable for the launchpad but are not exposed via MCP.
"""
from __future__ import annotations

import json
import threading
from typing import Any

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import ErrorData, Resource, Tool
from pydantic import AnyUrl

from .config import load_config
from .ranker import RoutingContext, build_default_ranker, predict_strongest_chairman, chairman_pick_reason

server = Server("trinity-local")


@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    return [
        Tool(
            name="route",
            description=(
                "DEPRECATED — prefer `ask(mode='route')`, which returns the same routing "
                "decision (#213 Q4 surface-collapse). Kept for back-compat.\n\n"
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
                "WHEN TO CALL THIS: before asking the user to pick between options that aren't "
                "user-personal preferences. Default to `ask` for product/architectural questions "
                "where the answer is 'which option is RIGHT' (Trinity routes to the model whose "
                "past wins on similar questions are strongest, applies the user's lens). Reserve "
                "AskUserQuestion / interactive prompts for genuinely personal choices (taste, "
                "priorities, scope).\n\n"
                "WHAT IT DOES: Trinity routes via kNN over the user's past prompts (which model "
                "has historically won for similar questions), dispatches one call to the best "
                "provider, and returns a concise structured answer.\n\n"
                "Returns: {answer, routed_to, trust_score (0..1), latency_ms, optional runner_up, "
                "optional escalate_hint='run_council' when trust is low and you should consider "
                "calling `run_council` for parallel perspectives instead}.\n\n"
                "Cost: ~$0.01–0.05 typical for one model call. Latency 3–30s dominated by "
                "the dispatched provider's response time (Trinity overhead is <1s). Single "
                "dispatched call, no flagship planning, no multi-model fan-out. If you genuinely "
                "need disagreement-vs-agreement structure, use `run_council` instead.\n\n"
                "MODE: default `mode='answer'` dispatches one call and returns the answer. "
                "`mode='route'` returns ONLY the routing decision "
                "{mode, primary, challenger, confidence, reason, fallback} with NO model call — "
                "use it to decide which provider to use before you call anything. (This subsumes "
                "the standalone `route` tool, which is kept for back-compat.)"
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The user's question or task"},
                    "mode": {
                        "type": "string",
                        "enum": ["answer", "route"],
                        "default": "answer",
                        "description": "`answer` (default): dispatch one call, return the answer. `route`: return the routing decision only, no model call.",
                    },
                    "available_providers": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Provider names allowed to route to (default: all enabled in config)",
                    },
                    "top_k": {"type": "integer", "default": 5, "description": "How many past prompts to retrieve for the vote (answer mode)"},
                    "budget": {"type": "string", "enum": ["low", "normal", "high"], "default": "normal", "description": "route mode: cost preference"},
                    "latency": {"type": "string", "enum": ["fast", "normal", "patient"], "default": "normal", "description": "route mode: latency preference"},
                    "current_provider": {"type": "string", "description": "route mode: provider currently in use (optional)"},
                    "harness": {"type": "string", "description": "route mode: calling harness name (optional)"},
                },
                "required": ["query"],
            },
        ),
        Tool(
            name="run_council",
            description=(
                "WHEN TO CALL THIS: before committing to an architectural / public-API / "
                "data-schema decision where two senior engineers could reasonably disagree, OR "
                "when the user explicitly asks for a council or second opinion, OR when route() "
                "returned mode='council', OR when you'd otherwise present a multi-option choice "
                "to the user but the choice is product/architectural (not user-personal "
                "preference). Skip for trivial bugs, syntax lookups, mechanical refactors, "
                "information retrieval — wasted on questions with one right answer.\n\n"
                "WHAT IT DOES: launches a multi-provider comparison (claude / codex / antigravity "
                "by default). Supports parallel mode (default; members run simultaneously) and "
                "chain mode (sequential refinement, each model refines the prior). The chairman "
                "synthesizes via the user's lens.md and returns agreed_claims, disagreed_claims "
                "with why_matters, winner, runner_up, routing_lesson. Returns the council_run_id "
                "and the path to the live review page; the council runs asynchronously.\n\n"
                "HORIZON WEIGHTING (#139): the chairman receives a query-horizon classification "
                "(tactical / strategic / philosophical) computed from the task text, and weights "
                "lens cards tagged with the matching horizon heavier in synthesis. This means a "
                "strategic question pulls strategic-tagged lens tensions to the front of the "
                "winner-picking reasoning. The routing_lesson Trinity returns reflects which "
                "lens tags were load-bearing in the verdict.\n\n"
                "When `responses` is provided (pre-supplied member outputs), skips member "
                "dispatch and goes straight to chairman synthesis — one model call instead of "
                "N+1. Use when you ALREADY HAVE multiple model outputs and just want the "
                "structured verdict.\n\n"
                "Cost: 3 member calls + 1 chairman call (~30s-2min). Anthropic's advisor-tool "
                "pattern is intra-provider (Sonnet→Opus, all Claude); `run_council` is "
                "cross-provider (claude/codex/antigravity) — different value prop, both can "
                "coexist."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "task": {"type": "string"},
                    "goal": {"type": "string", "default": "Find the strongest answer."},
                    "members": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Provider names (e.g. ['claude', 'antigravity', 'codex']). Omit to use the default 3-member lineup.",
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
                            "and runs chairman synthesis only (structured verdict)."
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
        # record_outcome retired 2026-05-21 per user direction "we are
        # sunsetting user ratings. Full retirement including MCP." The
        # chairman's pick (routing_label.winner) is the supervision
        # signal that feeds compute_personal_routing_table() now (commit
        # bb817b6). Refinement prompts on the council page carry the
        # "what user wanted differently" signal. CLI `council-rate`
        # was retired one day later on 2026-05-22 (task #134) — full
        # rating retirement, no power-user override remained.
        # Registry entry: src/trinity_local/retired_names.py.
        Tool(
            name="get_persona",
            description=(
                "Return the user's lens — paired tensions distilled by a chairman call over "
                "the user's prompt history across providers (lives at `~/.trinity/memories/lens.md`). "
                "Pull this once at session start and use it as latent context to tailor responses, "
                "terseness, vocabulary, and standing decisions to THIS user. Empty string when not "
                "built — run `trinity-local lens-build` to (re)build, or `trinity-local dream` for "
                "the full memory-rebuild pass.\n\n"
                "Abstract-lens cards may carry a horizon suffix tag `[tactical]` / `[strategic]` / "
                "`[philosophical]` (task #139). Tactical = response-shape preference (format, length, "
                "what to include); strategic = quarter-scale trajectory choices; philosophical = "
                "year-scale identity / framing. When the user's query reads as a particular horizon, "
                "weight matching lens cards heavier than non-matching ones — that's the lens "
                "prioritization the local chairman does too. Untagged cards default to tactical."
            ),
            inputSchema={"type": "object", "properties": {}},
        ),
        Tool(
            name="get_picks",
            description=(
                "Return the user's extracted routing patterns from "
                "`~/.trinity/scoreboard/picks.json` — the cortex layer's "
                "consolidated knowledge across past councils. Per-basin: which "
                "provider wins, why, failure modes per loser, successful prompt "
                "templates, and a system-computed trust_score (6 components, "
                "weighted geometric mean). Pull this when planning a complex "
                "task — it tells you which provider this user prefers for THIS "
                "kind of question and why. Empty when no consolidation has run "
                "yet (`trinity-local consolidate`). Filter to a specific basin "
                "with the `basin_id` parameter; omit for the full map. v1.5."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "basin_id": {
                        "type": "string",
                        "description": "Optional. Return only the rule for this basin (task_type).",
                    },
                    "min_trust": {
                        "type": "number",
                        "default": 0.0,
                        "description": "Filter to rules with trust_score >= this value (0..1).",
                    },
                },
            },
        ),
        Tool(
            name="mark_pick_wrong",
            description=(
                "User veto on a cortex routing rule. Each call increments the "
                "rule's `override_count`; effective_trust = raw_trust × 0.5^count. "
                "Two clicks quarter the trust; three drops most rules out of "
                "routing entirely. Persists across consolidations — a fresh "
                "extraction can't erase the user's signal. Call when the user "
                "says something like \"that cortex rule for system_design is "
                "wrong\" or when you observe the rule producing bad routing "
                "decisions enough times. Use `reset=true` to clear the count "
                "(user changed their mind, or a later extraction got it right). "
                "Spec-v1.5 Week 5."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "basin_id": {
                        "type": "string",
                        "description": "The basin / task_type whose rule should be marked wrong.",
                    },
                    "reason": {
                        "type": "string",
                        "description": "Optional one-line reason — surfaced in the response payload for the calling agent's context.",
                    },
                    "reset": {
                        "type": "boolean",
                        "default": False,
                        "description": "Reset override_count to 0 instead of incrementing. For when the user changes their mind.",
                    },
                },
                "required": ["basin_id"],
            },
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
        Tool(
            name="import_provider_memory",
            description=(
                "Pipe lens tensions OR rejection signals you (the agent) "
                "extracted from your conversation history with this user "
                "directly into Trinity's local state — no terminal, no "
                "copy-paste. The agent IS a provider with the user's "
                "history on its side, so this is the same loop as "
                "`trinity-local eval-prompt → eval-import` but closes "
                "inside the harness.\n\n"
                "USE WHEN: the user asks you to 'save my preferences to "
                "Trinity', 'update my lens with what you've learned', or "
                "you (the agent) recognize you've accumulated useful "
                "rejection signals worth persisting.\n\n"
                "SHAPE: pass `kind='eval'` with a `payload` matching the "
                "schema in docs/evals-from-provider.md (rejections: "
                "[{type, model_quote, user_substitute, why_signal, "
                "confidence}, ...]). Pass `kind='lens'` with the schema "
                "in docs/lens-from-provider.md (tensions: [{pole_a, "
                "pole_b, failure_a, failure_b, horizon, evidence, "
                "confidence, why_matters}, ...]).\n\n"
                "Returns a structured summary: count of new vs duplicate "
                "vs malformed items, the on-disk path written. Same "
                "dedup rules as the CLI verbs — same payload twice is "
                "a no-op.\n\n"
                "Cross-provider attribution: when `provider` is set, it "
                "overrides any source_provider in the payload (useful "
                "when you want to attribute to yourself explicitly)."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "enum": ["lens", "eval"],
                        "description": "Which memory artifact to ingest.",
                    },
                    "payload": {
                        "type": "object",
                        "description": (
                            "The JSON payload, matching the schema for "
                            "the chosen kind. See "
                            "docs/lens-from-provider.md or "
                            "docs/evals-from-provider.md."
                        ),
                    },
                    "provider": {
                        "type": "string",
                        "description": (
                            "Override the source_provider attribution "
                            "(optional). When omitted, falls back to "
                            "payload.source_provider or 'unknown'."
                        ),
                    },
                    "dry_run": {
                        "type": "boolean",
                        "default": False,
                        "description": "Parse + return the merge plan without writing.",
                    },
                },
                "required": ["kind", "payload"],
            },
        ),
    ]


_lens_kicks_fired = False
_lens_kicks_lock = threading.Lock()


def _maybe_fire_lens_kicks() -> None:
    """Fire the first-lens-build + activity-refresh kicks once per process, on
    the first tool call (where an MCP session is registered so the build can
    sample). Best-effort: never let an auto-kick failure break a tool call."""
    global _lens_kicks_fired
    with _lens_kicks_lock:
        if _lens_kicks_fired:
            return
        _lens_kicks_fired = True
    try:
        from .cold_start import maybe_kick_first_lens_build, maybe_kick_lens_refresh

        # First build owns the cold-start case; refresh owns keep-current. Each
        # internally gates (should_build/should_refresh + the shared lock), so
        # calling both is a cheap no-op once a current lens exists.
        maybe_kick_first_lens_build()
        maybe_kick_lens_refresh()
    except Exception:
        pass
    # Roots: ask the client what filesystem roots it exposes (e.g. the open
    # project), and log them. Best-effort — surfaces what transcript dirs a
    # future ingest could auto-discover; no-op when the client lacks roots.
    try:
        from .mcp_features import discover_roots, mcp_log

        roots = discover_roots()
        if roots:
            mcp_log("info", f"Client exposed {len(roots)} root(s): {', '.join(roots[:5])}")
    except Exception:
        pass


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict | None) -> list[Any]:
    arguments = arguments or {}
    # Register the active MCP server session so providers running in
    # worker threads can find it (via mcp_sampling.request_claude_sample).
    # When Trinity-MCP is loaded inside Claude Desktop and the client
    # advertised sampling capability, the Claude provider routes through
    # sampling instead of `claude -p` subprocess — sidestepping the
    # post-2026-06-15 Agent SDK credit pool. ContextVar set here
    # propagates to the ThreadPoolExecutor workers in council_runner
    # via copy_context().
    from .mcp_features import clear_request_context, set_request_context
    from .mcp_sampling import clear_active_session, set_active_session
    try:
        ctx = server.request_context
        set_active_session(ctx.session)
        # Capture the request id + client-attached progress token so worker-
        # thread log/progress calls (councils run off-thread) attribute
        # themselves to this request. meta is None when the client sent no
        # _meta; progressToken is None when it didn't ask for progress.
        progress_token = getattr(getattr(ctx, "meta", None), "progressToken", None)
        set_request_context(ctx.request_id, progress_token)
    except (AttributeError, LookupError):
        # Defensive: if the SDK version lacks request_context.session,
        # or this is invoked outside a real MCP request (e.g., tests),
        # skip session registration and let sampling auto-decline.
        pass

    # #263 keystone: fire the LLM-making auto-kicks (first lens build +
    # activity-gated refresh) HERE — on the first tool call, with the session
    # registered above — so their Claude stages route through sampling and
    # ride the user's Claude Code subscription instead of burning `claude -p`
    # quota. copy_context() inside the kick snapshots the active session for
    # the build thread (independent of the finally-clear below). Fire-once.
    _maybe_fire_lens_kicks()

    try:
        if name == "ask":
            return await _ask(arguments)
        if name == "get_picks":
            return await _get_picks(arguments)
        if name == "mark_pick_wrong":
            return await _mark_pick_wrong(arguments)
        if name == "route":
            return await _route(arguments)
        if name == "run_council":
            return await _run_council(arguments)
        # `record_outcome` dispatch removed 2026-05-21 (rating UX sunset).
        if name == "get_persona":
            return await _get_persona(arguments)
        if name == "get_council_status":
            return await _get_council_status(arguments)
        if name == "import_provider_memory":
            return await _import_provider_memory(arguments)
        return [ErrorData(code=404, message=f"Tool not found: {name}")]
    except Exception as exc:
        return [ErrorData(code=500, message=f"{type(exc).__name__}: {exc}")]
    finally:
        clear_active_session()
        clear_request_context()


# ─── MCP Resources — read-only context surfaces ────────────────────
#
# Per the v2 substrate spec (docs/PREFERENCE_CORPUS_SPEC.md), Trinity
# exposes the four cognitive memories + the operational scoreboards
# as MCP Resources. Resources are listed at session start so any
# MCP-aware harness sees them without a tool round-trip — the agent
# can read trinity://memories/lens.md before the user even types a
# prompt, and condition every response on the lens.
#
# This is the leverage point for Phase A of the v2 arc: tools are
# pull (the agent decides when to call); resources are push (the
# harness lists them at handshake, agent reads on demand). Same
# data, different cost profile.

# Static resource catalog. Each entry maps a trinity:// URI to a
# (label, mime_type, path_func) tuple. path_func is a no-arg callable
# that returns the on-disk Path — lazy so tests can override
# TRINITY_HOME and the resource list reflects the new location.
def _resource_catalog() -> list[tuple[str, str, str, str, Any]]:
    """Return the canonical list of MCP Resources Trinity exposes.

    Each tuple: (uri, name, description, mime_type, path_func).

    The four cognitive memories (core / lens / topics / vocabulary)
    map to the lens hierarchy chairman reads top-down. The two
    scoreboards (picks / routing) are read-only operational data
    surfaced for agents that want to see "what Trinity routes to
    today" without firing the route() tool.

    AGENTS.md was originally on this catalog but dropped 2026-05-26
    after user pushback: AGENTS.md is project-scoped by convention
    (agents read `./AGENTS.md` in the user's repo, not at home), and
    every harness that reads AGENTS.md also reads MCP Resources —
    so generating a user-home AGENTS.md was ceremonial. The lens flows
    via trinity://memories/lens.md instead; users who want a
    project-local AGENTS.md can write one that references that URI.
    """
    from . import state_paths as _sp
    memories = _sp.memories_dir()
    scoreboard = _sp.scoreboard_dir()
    return [
        (
            "trinity://memories/core.md",
            "Trinity Core Memory",
            "Your one-paragraph manifesto — chairman reads this first to ground every council in your voice.",
            "text/markdown",
            lambda: memories / "core.md",
        ),
        (
            "trinity://memories/lens.md",
            "Trinity Lens",
            "Paired tensions you reject vs accept. The chairman conditions synthesis on these. The load-bearing personalization layer.",
            "text/markdown",
            lambda: memories / "lens.md",
        ),
        (
            "trinity://memories/topics.json",
            "Trinity Topics (Basins)",
            "Subject basins extracted from your corpus — semantic clusters with TF-IDF labels and lens-evidence maps.",
            "application/json",
            lambda: memories / "topics.json",
        ),
        (
            "trinity://memories/vocabulary.md",
            "Trinity Vocabulary",
            "Your anchors, homonyms, and overloaded terms. What 'X' means to you, not to the model's training distribution.",
            "text/markdown",
            lambda: memories / "vocabulary.md",
        ),
        (
            "trinity://scoreboard/picks.json",
            "Trinity Picks (Cortex Routing Rules)",
            "Extracted routing rules per task basin — what model wins on which kind of question, derived from your council history.",
            "application/json",
            lambda: scoreboard / "picks.json",
        ),
        (
            "trinity://scoreboard/routing.json",
            "Trinity Personal Routing Table",
            "Per-task-type provider track record — aggregated from chairman picks across all your councils.",
            "application/json",
            lambda: scoreboard / "routing.json",
        ),
    ]


@server.list_resources()
async def handle_list_resources() -> list[Resource]:
    """Advertise Trinity's readable resources to the harness.

    All resources are exposed unconditionally — even when their files
    don't exist yet (cold install). read_resource() returns a stub
    explaining how to populate them rather than 404'ing, so the
    agent sees "AGENTS.md not yet generated — run trinity-local
    dream" and can offer that action to the user.
    """
    return [
        Resource(
            uri=AnyUrl(uri),
            name=name,
            description=description,
            mimeType=mime,
        )
        for (uri, name, description, mime, _path_func) in _resource_catalog()
    ]


@server.read_resource()
async def handle_read_resource(uri: AnyUrl) -> str:
    """Return the contents of a trinity:// resource.

    Cold-install behavior: when the underlying file doesn't exist,
    return a stub message explaining how to populate it. This is
    actionable feedback (agent knows what to suggest) and avoids
    the dead-resource 404 path that would surface as a generic
    error in the harness's UI.
    """
    uri_str = str(uri)
    catalog = {entry[0]: entry for entry in _resource_catalog()}
    if uri_str not in catalog:
        raise ValueError(f"Unknown Trinity resource: {uri_str}")
    _, name, _, _, path_func = catalog[uri_str]
    path = path_func()
    if not path.exists():
        # Stub response per cold-install path: tell the agent what
        # the resource WILL contain + how to populate it. Strictly
        # better than 404 — the agent surfaces a concrete next-step
        # to the user instead of a vague error.
        return (
            f"# {name}\n\n"
            f"_(empty — this file does not exist yet)_\n\n"
            f"Trinity hasn't generated this resource yet. To populate it:\n\n"
            f"```bash\n"
            f"trinity-local dream\n"
            f"```\n\n"
            f"Dream reads your existing corpus and writes the four cognitive "
            f"memories (`core.md`, `lens.md`, `topics.json`, `vocabulary.md`) "
            f"plus the AGENTS.md lens-derived guidance. After dream finishes, "
            f"re-read this resource and it will be populated.\n\n"
            f"Resource URI: `{uri_str}`\n"
            f"On-disk path: `{path}`\n"
        )
    return path.read_text(encoding="utf-8")


# ─── MCP Prompts — Trinity's verbs as native slash-prompts ──────────
#
# Registering these handlers makes the host advertise the `prompts`
# capability, so `/council`, `/lens`, `/ask` show up in the harness's
# slash menu. Each prompt expands to a user-role message that tells the
# agent which Trinity tool to call — discovery for users who'd never read
# a tool docstring. The arg becomes the task/query text.

_PROMPT_CATALOG = [
    {
        "name": "council",
        "description": "Compare a hard question across Claude, GPT, and Gemini "
        "and synthesize the answer your taste would pick.",
        "arg": ("task", "The question or task to run the council on.", True),
        "tool": "run_council",
        "render": lambda task: (
            f"Run a Trinity council on this, then report the chairman's verdict "
            f"with the agreed_claims and disagreed_claims:\n\n{task}\n\n"
            f"Use the `mcp__trinity-local__run_council` tool."
        ),
    },
    {
        "name": "ask",
        "description": "Route one question to the single best provider for it "
        "(cheap — one call, chairman-blessed).",
        "arg": ("query", "The question to route.", True),
        "tool": "ask",
        "render": lambda query: (
            f"Route this question to the best provider for it and answer:\n\n{query}\n\n"
            f"Use the `mcp__trinity-local__ask` tool."
        ),
    },
    {
        "name": "lens",
        "description": "Read the user's taste lens so you can tailor this "
        "session's answers to how they decide.",
        "arg": ("focus", "Optional: what to focus the lens read on.", False),
        "tool": "get_persona",
        "render": lambda focus: (
            "Read the user's Trinity taste lens via the "
            "`mcp__trinity-local__get_persona` tool and condition your answers "
            "on it for the rest of this session."
            + (f" Focus especially on: {focus}." if focus else "")
        ),
    },
]


@server.list_prompts()
async def handle_list_prompts() -> list[Any]:
    """Advertise Trinity's verbs as MCP prompts (slash-menu entries)."""
    from mcp.types import Prompt, PromptArgument

    prompts = []
    for spec in _PROMPT_CATALOG:
        arg_name, arg_desc, arg_required = spec["arg"]
        prompts.append(
            Prompt(
                name=spec["name"],
                description=spec["description"],
                arguments=[
                    PromptArgument(
                        name=arg_name, description=arg_desc, required=arg_required
                    )
                ],
            )
        )
    return prompts


@server.get_prompt()
async def handle_get_prompt(name: str, arguments: dict | None) -> Any:
    """Expand a Trinity prompt into a user-role message that routes the agent
    to the matching Trinity tool."""
    from mcp.types import GetPromptResult, PromptMessage, TextContent

    arguments = arguments or {}
    spec = next((s for s in _PROMPT_CATALOG if s["name"] == name), None)
    if spec is None:
        raise ValueError(f"Unknown Trinity prompt: {name}")
    arg_name = spec["arg"][0]
    text = spec["render"](arguments.get(arg_name, "") or "")
    return GetPromptResult(
        description=spec["description"],
        messages=[
            PromptMessage(role="user", content=TextContent(type="text", text=text))
        ],
    )


@server.set_logging_level()
async def handle_set_logging_level(level: Any) -> None:
    """Honor the client's logging/setLevel request — filters mcp_log emissions
    to the requested minimum level for the rest of the connection."""
    from .mcp_features import set_min_log_level

    set_min_log_level(str(level))


def _text(payload: dict | str) -> dict:
    """Wrap a JSON-serializable result as an MCP text response.

    Two optional hints get injected into dict payloads so agents can
    surface them inline:

    * ``cold_start`` — "Trinity is ingesting your CLI history…" when
      the first-run auto-scan is running or just finished.
    * ``extension_status`` — "Chrome extension not configured — install
      it for browser capture + auto-update." when the user installed
      via curl|bash and never wired the extension. Closes the cross-
      bootstrap loop from the agent side (the launchpad and install.sh
      already surface this; agents calling MCP tools see it too).

    Strings pass through unchanged — hints only attach to structured
    responses where the agent can pluck a field.
    """
    if isinstance(payload, dict):
        if "cold_start" not in payload:
            try:
                from .cold_start import cold_start_hint

                hint = cold_start_hint()
                if hint is not None:
                    payload = dict(payload)
                    payload["cold_start"] = hint
            except Exception:
                pass
        # #212 cold-start aha: once the lens has signal, surface ONE surprising
        # true tension so the agent can open with "here's one thing I've
        # learned about how you decide" — the differentiated wow, before the
        # user has learned a verb. Self-omits on a cold install (None).
        if "lens_cold_open" not in payload:
            try:
                from .cold_start import cold_open_tension

                co = cold_open_tension()
                if co:
                    payload = dict(payload)
                    payload["lens_cold_open"] = co
            except Exception:
                pass
        if "extension_status" not in payload:
            try:
                hint = _extension_status_hint()
                if hint is not None:
                    payload = dict(payload)
                    payload["extension_status"] = hint
            except Exception:
                pass
    body = payload if isinstance(payload, str) else json.dumps(payload, indent=2, default=str)
    return {"type": "text", "text": body}


# Cached at module level so we don't hit the filesystem on every MCP
# response. The extension config is set by `install-extension` and
# doesn't change mid-process — a process-lifetime cache is correct.
# `_NOT_COMPUTED` is the sentinel for "we haven't asked yet." Critical
# detail: `is not object()` would create a FRESH sentinel each call
# and always read as "not computed" — the cache would never hit. Use
# a stable module-level singleton.
_NOT_COMPUTED = object()
_EXTENSION_HINT_CACHED: dict | None | object = _NOT_COMPUTED


def _extension_status_hint() -> dict | None:
    """Return an extension-status hint dict when the Chrome extension
    isn't wired, else None. Cached for the process lifetime.

    Hint shape:
      {
        "configured": False,
        "message": str,           # human-readable, agent surfaces inline
        "install_doc": str,       # URL to the install instructions
      }

    When the extension IS configured, returns None so agents don't
    see a "your extension is fine, by the way" hint on every call.
    """
    global _EXTENSION_HINT_CACHED
    if _EXTENSION_HINT_CACHED is not _NOT_COMPUTED:
        return _EXTENSION_HINT_CACHED  # type: ignore[return-value]

    try:
        from .launchpad_data import dispatch_readiness

        readiness = dispatch_readiness()
    except Exception:
        _EXTENSION_HINT_CACHED = None
        return None

    if readiness.get("extension_configured"):
        _EXTENSION_HINT_CACHED = None
        return None

    _EXTENSION_HINT_CACHED = {
        "configured": False,
        "message": (
            "Chrome extension not wired — install it for browser "
            "capture (claude.ai / chatgpt.com / gemini.google.com) + "
            "Web Store auto-update."
        ),
        "install_doc": "https://github.com/vishigondi/trinity-local/blob/main/docs/INSTALL-extension.md",
    }
    return _EXTENSION_HINT_CACHED


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
        task_types=set(),
        model=model,
    )
    provider = OllamaProvider(cfg)
    result = provider.run(prompt, Path.cwd())
    if result.returncode != 0:
        raise ProviderError(f"{provider_name} exit {result.returncode}: {result.stderr[:200]}")
    return result.stdout


def _trigger_incremental_ingest() -> None:
    """Fire-and-forget: scan transcripts newer than the per-source memory
    cursor and append fresh ``PromptNode``s. Runs at the start of ``ask``
    so MCP-driven flows pick up new conversations without a manual
    ``import-export`` rerun (or its retired predecessor seed-from-taste-
    terminal). Bounded at 1s so it cannot dominate user-facing latency;
    errors are swallowed so a parser breakage cannot take down the tool
    surface.
    """
    try:
        from .incremental_ingest import ingest_recent

        ingest_recent(deadline_s=1.0)
    except Exception:
        return


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

    Q4 surface-collapse (#213): `route` merged into `ask` as a mode.
    `mode="route"` returns the routing decision (which model, council-or-not,
    confidence) WITHOUT dispatching a call — the old `route` tool's job. The
    standalone `route` tool stays registered for back-compat (deprecated).
    """
    from .ask import run_ask

    query = args.get("query")
    if not query or not isinstance(query, str):
        return [ErrorData(code=400, message="`query` is required and must be a string")]

    mode = (args.get("mode") or "answer").lower()
    if mode == "route":
        # Delegate to the routing path: query→task, available_providers→
        # available_models; pass the routing hints through unchanged.
        route_args: dict = {"task": query}
        if "available_providers" in args:
            route_args["available_models"] = args.get("available_providers")
        for k in ("harness", "budget", "latency", "current_provider"):
            if args.get(k) is not None:
                route_args[k] = args[k]
        return await _route(route_args)

    _trigger_incremental_ingest()

    available = args.get("available_providers")
    if available is not None and not isinstance(available, list):
        return [ErrorData(code=400, message="`available_providers` must be a list of provider names")]
    # When caller doesn't specify available_providers, default to the full
    # pool (config providers + detected local models). This is what makes
    # ask aware of Ollama / MLX without each call having to declare them.
    if available is None:
        available = _full_provider_pool()

    top_k = int(args.get("top_k", 5))

    try:
        result = run_ask(
            query,
            dispatch_fn=_dispatch_via_config,
            top_k=top_k,
            available_providers=available,
        )
    except Exception as exc:
        # 100-persona audit D7: structured error shape lets the agent
        # auto-retry around rate limits without parsing a free-form
        # string. Detect the failure kind from the exception message
        # so {error_code, recoverable, retry_with} can drive recovery.
        from .dispatch_errors import classify_dispatch_failure
        exc_text = str(exc)
        try:
            failure = classify_dispatch_failure(
                provider=available[0] if available else "unknown",
                returncode=getattr(exc, "returncode", 1),
                stderr=exc_text,
            )
            failure_kind = failure.kind.value
            recoverable = failure.retry_with_other_provider
        except Exception:
            failure_kind = "unknown"
            recoverable = True
        # Suggest the remaining pool minus the failing provider so the
        # agent can immediately retry around it (the rate-limit-dodge
        # wedge in one hop).
        failing_provider = available[0] if available else None
        retry_pool = [p for p in available if p != failing_provider] if available else []
        return [_text({
            "ok": False,
            "error_code": {
                "rate_limited": "RATE_LIMITED",
                "billing_exceeded": "BILLING_EXCEEDED",
                "auth_failed": "AUTH_FAILED",
                "model_not_found": "MODEL_NOT_FOUND",
                "timeout": "TIMEOUT",
            }.get(failure_kind, "DISPATCH_FAILED"),
            "provider": failing_provider,
            "recoverable": bool(recoverable and retry_pool),
            "retry_with": {"available_providers": retry_pool} if retry_pool else None,
            "user_message": (
                f"{failing_provider} {failure_kind.replace('_', ' ')}; "
                f"try {retry_pool[0]} next" if retry_pool else
                f"All providers failed ({failure_kind})"
            ),
            "detail": exc_text[:240],
        })]

    payload = result.to_dict()
    # Make the success/failure shape symmetric: the failure branch above
    # returns {"ok": False, error_code, ...}; the success branch needs
    # ok=True so an agent doing `if response.get("ok"): proceed` works
    # uniformly. Was asymmetric — happy path returned the raw answer
    # dict with no ok key, agent's natural check treated success as
    # failure.
    payload["ok"] = True
    # pending_ratings hint retired 2026-05-21 alongside record_outcome.
    return [_text(payload)]


async def _get_picks(args: dict) -> list[Any]:
    """Handle mcp__trinity-local__get_cortex_rules. Returns the user's
    extracted routing patterns so the calling agent can inspect what
    Trinity has learned about which model wins for which question kind.
    """
    from .cortex import load_routing_patterns

    basin_id = args.get("basin_id")
    if basin_id is not None and not isinstance(basin_id, str):
        return [ErrorData(code=400, message="`basin_id` must be a string when provided")]
    try:
        min_trust = float(args.get("min_trust", 0.0))
    except (TypeError, ValueError):
        return [ErrorData(code=400, message="`min_trust` must be numeric")]

    patterns = load_routing_patterns()
    if not patterns:
        return [_text({"rules": {}, "note": "No cortex consolidation yet. Run `trinity-local consolidate`."})]

    # Strip cortex-internal fields from the MCP response. basin_centroid
    # is a 768-dim embedding vector (~17KB serialized per basin) — only
    # used inside _best_centroid_match for semantic routing; an agent
    # reading get_picks wants the routing rule + failure modes + trust
    # score, not the raw vector. Without this, 9 basins returned ~175KB
    # / 7600 lines of JSON to the agent — far past any sane MCP payload.
    # manifold_dim / bimodal_flag are also internal geometry hints.
    _INTERNAL_FIELDS = ("basin_centroid", "manifold_dim", "bimodal_flag")

    # Filter
    filtered: dict[str, dict] = {}
    for bid, pattern in patterns.items():
        if basin_id is not None and bid != basin_id:
            continue
        if pattern.trust_score.value < min_trust:
            continue
        d = pattern.to_dict()
        for k in _INTERNAL_FIELDS:
            d.pop(k, None)
        filtered[bid] = d

    return [_text({
        "rules": filtered,
        "total_basins": len(patterns),
        "returned": len(filtered),
    })]


async def _mark_pick_wrong(args: dict) -> list[Any]:
    """Handle mcp__trinity-local__mark_cortex_rule_wrong. Increments (or
    resets) the override_count on a basin's rule; effective_trust drops
    by 0.5^count. Persists across consolidations.
    """
    from .cortex import effective_trust, load_routing_patterns, save_routing_patterns

    basin_id = args.get("basin_id")
    if not basin_id or not isinstance(basin_id, str):
        return [ErrorData(code=400, message="`basin_id` is required and must be a string")]
    reset = bool(args.get("reset", False))
    reason = args.get("reason")

    patterns = load_routing_patterns()
    if not patterns:
        return [_text({
            "ok": False,
            "error": "No cortex consolidation yet — run `trinity-local consolidate` first.",
        })]
    if basin_id not in patterns:
        return [_text({
            "ok": False,
            "error": f"basin {basin_id!r} not in cortex",
            "known_basins": sorted(patterns.keys()),
        })]

    pattern = patterns[basin_id]
    prior = pattern.override_count
    action = "reset" if reset else "incremented"
    pattern.override_count = 0 if reset else prior + 1
    save_routing_patterns(patterns)

    # Append a cortex_override row to merges.jsonl (tick #45). Same
    # schema the CLI handler writes — single source of truth on the
    # merge log so MCP and CLI verdicts feed one corpus.
    try:
        from .merges import record_merge
        record_merge({
            "type": "cortex_override",
            "basin_id": basin_id,
            "action": action,
            "prior_count": prior,
            "new_count": pattern.override_count,
            "raw_trust": round(pattern.trust_score.value, 3),
            "reason": reason,
        })
    except Exception:
        pass

    return [_text({
        "ok": True,
        "basin_id": basin_id,
        "action": action,
        "override_count": pattern.override_count,
        "raw_trust": round(pattern.trust_score.value, 3),
        "effective_trust": round(effective_trust(pattern), 3),
        "reason": reason,
    })]


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
        from .config import default_council_members
        available = default_council_members()
    current_provider = args.get("current_provider") or available[0]
    budget_pref = (args.get("budget") or "normal").lower()
    latency_pref = (args.get("latency") or "normal").lower()

    from .ranker import prompt_calls_for_council
    from .task_types import guess_task_type, is_polish_task

    chairman_pick = chairman_pick_reason(task, available_providers=available)
    task_type = chairman_pick.get("task_type") or guess_task_type(task)
    polish = is_polish_task(task)

    decision = None
    try:
        ranker = build_default_ranker()
        decision = ranker.advise(RoutingContext(
            task_text=task,
            task_type=task_type,
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
    # it takes 30s+. Prefer claude/antigravity if either is available.
    fast_demoted = False
    primary_pick = chairman_pick.get("chairman") or available[0]
    if latency_pref == "fast" and primary_pick == "codex":
        fast_alt = next((p for p in ("claude", "antigravity") if p in available), None)
        if fast_alt:
            primary_pick = fast_alt
            fast_demoted = True

    # Prompt-shape escalation: if the task literally contains "A) ... B) ..."
    # numbered alternatives, "vs.", "which is best", "tradeoffs", etc., the
    # user is asking for a comparison — escalate to mode=council regardless
    # of what task_type says. Single-answer routing on a multi-candidate
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
        "task_type": task_type,
        "chairman_source": chairman_pick.get("source", "default_order"),
        "shape_signals": council_signals,
        "budget": budget_pref,
        "latency": latency_pref,
        "should_auto_council": mode == "council",
        # Polish-shape tasks ("make this better", "tighten this", ≤20 words
        # + "shorter"/"simpler"/etc.) benefit from consensus_round iteration
        # — the first pass catches the obvious; the value is in rounds 2-3
        # where each model refines against the others' outputs. Surfaced
        # here so harnesses + the launchpad can OFFER auto-iterate without
        # changing default behavior.
        "auto_iterate_recommended": polish,
    }
    # pending_ratings hint retired 2026-05-21 alongside record_outcome.
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
    instead of N+1. Returns the structured Routing JSON inline.
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
    # (personal_routing aggregation) can't tell who won.
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
    # of N+1. Same outcome shape (structured Routing JSON), persisted as
    # a CouncilOutcome the personal routing table reads from.
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
    from .config import default_council_members
    members = args.get("members") or default_council_members()
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

    # MCP logging + progress (best-effort; no-op without a capable client).
    from .mcp_features import mcp_log, mcp_progress

    mcp_log("info", f"Council {council_run_id} launched ({mode})")
    mcp_progress(0.05, 1.0, message="council dispatched")

    # Optional inline-wait. Polls the status file every 750ms until either
    # the council reports completed/failed/canceled, or the budget expires.
    if wait_seconds > 0:
        from .council_runtime import load_council_outcome
        from .state_paths import council_outcomes_dir

        deadline = time.monotonic() + wait_seconds
        completed_status: dict | None = None
        while time.monotonic() < deadline:
            # Stream progress as a fraction of the wait budget elapsed, so the
            # harness can render a live bar while members deliberate. Monotonic
            # by construction; capped below 1.0 until the council resolves.
            elapsed = wait_seconds - (deadline - time.monotonic())
            mcp_progress(
                min(0.95, 0.05 + 0.9 * (elapsed / wait_seconds)),
                1.0,
                message="council deliberating",
            )
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
            mcp_progress(1.0, 1.0, message="council complete")
            winner = (outcome_summary or {}).get("winner") if outcome_summary else None
            mcp_log(
                "info",
                f"Council {council_run_id} {completed_status.get('status')}"
                + (f" — winner {winner}" if winner else ""),
            )
            # rate_action injection retired 2026-05-21 alongside record_outcome.
        else:
            response["status"] = "running"
            response["timed_out_after_seconds"] = wait_seconds
            mcp_log("warning", f"Council {council_run_id} still running after {wait_seconds}s")

    return [_text(response)]


# _record_outcome handler removed 2026-05-21 per user direction
# "we are sunsetting user ratings. Full retirement including MCP."
# Chairman's pick is the supervision signal (commit bb817b6).
# Registry entry: src/trinity_local/retired_names.py.


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


# _build_rate_action() + _pending_ratings_hint() + _PENDING_HINT_CACHE
# removed 2026-05-21. Per user direction: "Retire the whole mechanism"
# (rate-action hint injection alongside the record_outcome MCP tool).
# The chairman's pick IS the supervision signal — agents don't need
# to be nudged to capture a verdict that's already captured. Pillar 4
# funnel-widener mechanism deferred until a different shape proves out
# (current default: refinement prompts on the council page surface
# "what should the chairman have picked instead" without an agent-side
# tax). Registry: src/trinity_local/retired_names.py.


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

    # Path-safety: council_run_id is joined into a filesystem path below. Reject
    # path separators / traversal so a crafted or buggy id can't read an
    # arbitrary .json outside council_outcomes_dir() (defense-in-depth — the MCP
    # client is trusted-local, but the id should never escape the directory). An
    # unsafe id matches no real council, so we fall through to the "not found".
    _id_path_safe = (
        isinstance(council_run_id, str)
        and "/" not in council_run_id
        and "\\" not in council_run_id
        and ".." not in council_run_id
    )

    # Two storage locations:
    #   - council_outcomes/<id>.json: written ONCE on completion, durable
    #   - portal_pages/status/council_status_<token>.json: updated live during the run
    # `_lookup_council_status` handles both the direct-key and fallback-scan
    # cases; the wait_seconds polling path uses the same helper.
    status_payload: dict | None = (
        _lookup_council_status(council_run_id) if _id_path_safe else None
    )

    outcome_summary: dict | None = None
    outcome_load_error: str | None = None
    outcome_path = council_outcomes_dir() / f"{council_run_id}.json"
    if _id_path_safe and outcome_path.exists():
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
        except Exception as exc:
            # Silent skip would tell the agent "status is completed"
            # but "outcome is null" without explaining why. Most likely
            # cause: outcome JSON half-written by a legacy writer or
            # partially corrupted on disk.
            outcome_summary = None
            outcome_load_error = f"{type(exc).__name__}: {exc}"

    if status_payload is None and outcome_summary is None:
        # The corrupt-outcome-file path needs to carry outcome_load_error
        # too — otherwise the agent sees "unknown" with no signal that
        # an actual file existed but wouldn't parse.
        early_response: dict[str, Any] = {
            "council_run_id": council_run_id,
            "status": "unknown",
            "error": "no live status file or completed outcome found",
        }
        if outcome_load_error is not None:
            early_response["outcome_load_error"] = outcome_load_error
        return [_text(early_response)]

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

    status_response: dict = {
        "council_run_id": council_run_id,
        "status": (status_payload or {}).get("status") or ("completed" if outcome_summary else "unknown"),
        "task_text": (status_payload or {}).get("task_text"),
        "members": members_summary,
        "synthesis_status": ((status_payload or {}).get("synthesis") or {}).get("status"),
        "review_path": (status_payload or {}).get("review_path"),
        "outcome": outcome_summary,
    }
    if outcome_load_error is not None:
        status_response["outcome_load_error"] = outcome_load_error
    return [_text(status_response)]


async def _import_provider_memory(args: dict) -> list[Any]:
    """Pipe lens / eval JSON straight into Trinity's local state.

    The agent reusing this loop INSIDE Claude Code / Codex / Cursor has
    the user's full conversation history on its side — same as the
    provider-side prompt loops (lens-prompt + eval-prompt) but closes
    in-protocol. Dispatch reuses the same dict→signal mapping the
    CLI verbs use, so the dedup / malformed-skip / append-only
    semantics are identical.
    """
    from argparse import Namespace
    import io
    import json as _json
    from contextlib import redirect_stdout

    kind = (args.get("kind") or "").strip().lower()
    if kind not in ("lens", "eval"):
        return [_text({
            "ok": False,
            "error": f"kind must be 'lens' or 'eval' (got {kind!r})",
        })]
    payload = args.get("payload")
    if not isinstance(payload, dict):
        return [_text({
            "ok": False,
            "error": "payload must be an object (matching the lens or eval schema)",
        })]

    # The CLI handlers read raw text from stdin / file. To reuse them
    # without disk I/O, serialize the payload and feed it via the
    # --from-json path. Capture stdout (which carries the JSON summary
    # when as_json=True) into a buffer.
    raw = _json.dumps(payload)
    ns = Namespace(
        path=None,
        from_json=False,
        provider=args.get("provider"),
        dry_run=bool(args.get("dry_run", False)),
        as_json=True,
    )

    if kind == "lens":
        from .commands.lens_import import handle_lens_import as _handler
    else:
        from .commands.eval_import import handle_eval_import as _handler

    # The handlers read sys.stdin when from_json=True. Replace sys.stdin
    # for the duration of the call to feed our serialized payload.
    import sys as _sys
    ns.from_json = True
    saved_stdin = _sys.stdin
    _sys.stdin = io.StringIO(raw)
    buf = io.StringIO()
    rc = None
    try:
        with redirect_stdout(buf):
            rc = _handler(ns)
    finally:
        _sys.stdin = saved_stdin

    out = buf.getvalue().strip()
    try:
        summary = _json.loads(out) if out else {}
    except _json.JSONDecodeError:
        summary = {"ok": rc == 0, "raw_output": out}

    summary["kind"] = kind
    summary["dry_run"] = bool(args.get("dry_run", False))
    if rc not in (None, 0):
        summary["ok"] = False
        summary["exit_code"] = rc
    return [_text(summary)]


async def run_stdio_server():
    # Dev mode: watch source tree for edits and exit on change so the MCP
    # launcher respawns with fresh code. No-op when TRINITY_MCP_WATCH is unset.
    from .mcp_watchdog import start_watchdog_if_enabled

    start_watchdog_if_enabled()

    # First-spawn auto-scan: when corpus is empty AND local CLI transcript
    # dirs (~/.claude, ~/.codex, ~/.gemini, cowork) exist, kick a background
    # ingest so the first council the user fires already has personalization
    # signal. No-op when corpus is populated or no source dirs found.
    from .cold_start import maybe_kick_cold_start

    # The cold-start *scan* is pure ingest (no LLM) — safe to run at startup
    # before any session exists. The two LLM-making kicks (first-build +
    # refresh) are deliberately NOT fired here: they're moved to the first
    # tool call (see `_maybe_fire_lens_kicks` in handle_call_tool) so they run
    # with an active MCP session and route their Claude stages through
    # sampling/createMessage instead of burning `claude -p` quota. Firing them
    # here — before server.run() — means no session is registered yet, so they
    # could never sample (the #263 keystone bug).
    maybe_kick_cold_start()

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            server.create_initialization_options(),
        )


