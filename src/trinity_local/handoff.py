"""Cross-provider handoff: continue a conversation in a different model.

The killer-hook mechanism from the launch arc (task #119 / killer_hook
memory). User is mid-conversation with Claude; runs `handoff gemini`;
Gemini receives the prior conversation as context and continues — no
re-context, no copy-paste.

The wedge is structurally non-refutable: only Trinity has the
cross-provider prompt index, so only Trinity can pull "what was just
said" from any provider's transcripts.

Two surfaces:
  - `trinity-local handoff <provider> [--continuation "..."]` CLI
  - `mcp__trinity-local__handoff` MCP tool (agent-callable from
    inside Claude Code, Codex CLI, Gemini CLI)

Both share `run_handoff()` below.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from .config import ProviderConfig
from .memory.store import iter_prompt_nodes
from .memory.schemas import PromptNode
from .providers import ProviderResult, make_provider


# How much of each prior assistant response to include. Trade-off:
# enough to carry the thread, not so much that we blow the receiving
# model's context window with a single handoff. 1500 chars per turn ×
# 3 turns ≈ 4500 chars of assistant text + the user turns themselves.
PER_TURN_CONTEXT_BUDGET_CHARS = 1500

# How many prior (user, assistant) pairs to include by default. Three
# is the sweet spot: enough to establish thread continuity for the
# receiving model, few enough that the handoff prompt isn't dominated
# by stale context.
DEFAULT_TURNS = 3


@dataclass(frozen=True)
class HandoffResult:
    """Returned by `run_handoff`. Carries the continued response plus
    context the agent can surface ('which model just answered? on what
    prior context?')."""
    target_provider: str
    target_model: str | None
    context_turns: int  # how many prior turns we packaged
    source_providers: list[str]  # which providers' turns we pulled from
    response_text: str
    elapsed_seconds: float
    error: str | None = None

    def to_dict(self) -> dict:
        out: dict = {
            "target_provider": self.target_provider,
            "target_model": self.target_model,
            "context_turns": self.context_turns,
            "source_providers": self.source_providers,
            "response_text": self.response_text,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
        }
        if self.error:
            out["error"] = self.error
        return out


def _truncate(text: str, budget: int = PER_TURN_CONTEXT_BUDGET_CHARS) -> str:
    text = (text or "").strip()
    if len(text) <= budget:
        return text
    half = budget // 2
    return f"{text[:half].rstrip()}\n[... truncated ...]\n{text[-half:].lstrip()}"


def _select_recent_turns(num_turns: int) -> list[PromptNode]:
    """Pull the N most-recent prompt nodes across all providers.

    Uses `iter_prompt_nodes` which already returns capped, mtime-cached
    nodes sorted by timestamp. We over-fetch a small buffer to tolerate
    nodes that lack assistant text (skipped from the handoff context).
    """
    over_fetch = max(num_turns * 3, 10)
    nodes = list(iter_prompt_nodes(limit=over_fetch))
    # iter_prompt_nodes already returns most-recent-first; we want
    # chronological for the conversation log so the receiving model
    # sees the actual order.
    usable = [n for n in nodes if (n.text or "").strip()]
    return usable[:num_turns]


# Per-target capability hints: nudge the receiving model to USE the
# integrations it commonly has, since the prior model in the
# conversation almost certainly didn't. The continuity wedge is
# strongest when the new model demonstrably brings capability the
# old one structurally couldn't — Gemini reading Gmail that Claude
# can't see is "wait, how did it know that" magic.
#
# Hints are deliberately soft ("if you have"): Trinity doesn't know
# the target's actual installed tools — that depends on the user's
# harness config. A hard "use Gmail" would be a hallucination prompt
# for users who haven't wired google-workspace MCP yet. The soft form
# triggers tool use when available without inventing it otherwise.
_CAPABILITY_HINTS: dict[str, str] = {
    "gemini": (
        "If you have access to Google Workspace tools (Gmail, Drive, "
        "Calendar) or web search, USE THEM when they'd enrich your "
        "answer with data the prior model couldn't see. The prior "
        "model was a different AI and couldn't read the user's "
        "emails, files, or calendar — you can. That's the entire "
        "point of this handoff: bringing capability to the "
        "conversation, not just another opinion."
    ),
    "claude": (
        "If you have access to filesystem tools, code execution, or "
        "MCP integrations the prior model didn't have, USE THEM. "
        "The point of this handoff isn't another opinion — it's "
        "bringing capability the prior model structurally couldn't."
    ),
    "codex": (
        "If you have access to local code, shell, or filesystem "
        "tools the prior model didn't have, USE THEM. The point "
        "of this handoff isn't another opinion — it's bringing "
        "capability the prior model structurally couldn't."
    ),
}


def build_handoff_prompt(
    nodes: Iterable[PromptNode],
    *,
    continuation: str | None = None,
    target_provider: str | None = None,
) -> tuple[str, list[str]]:
    """Render prior conversation as a "continuing-this-thread" prompt
    for the target model. Returns (prompt_text, source_providers).

    The prompt explicitly tells the receiving model "you're continuing
    a conversation that another AI started" — without that frame the
    model often re-introduces itself and breaks the demo's illusion of
    continuity.

    When `target_provider` is supplied, appends a per-provider
    capability hint that nudges the receiving model to use the
    integrations it commonly has but the prior model didn't. This is
    what makes the cross-provider hero demo (#115/#121) deterministic:
    gemini sees "use Google Workspace if available" and pulls Gmail/
    Calendar into the answer, demonstrating capability not just
    perspective.
    """
    capability_hint = _CAPABILITY_HINTS.get((target_provider or "").lower(), "")
    chunks: list[str] = [
        "You are continuing a conversation the user was having with "
        "another AI model. Pick up exactly where the prior model left "
        "off — don't re-introduce yourself, don't recap, just respond "
        "as if you'd been in the conversation from the start.\n\n",
    ]
    if capability_hint:
        chunks.append(f"{capability_hint}\n\n")
    chunks.append("--- Prior conversation log ---\n")
    source_providers: list[str] = []
    # nodes come in most-recent-first order; flip to chronological for
    # the receiving model.
    node_list = list(nodes)
    node_list.reverse()
    for n in node_list:
        user_text = (n.text or "").strip()
        if not user_text:
            continue
        chunks.append(f"\nUSER: {user_text}\n")
        # Prefer the FOLLOWING assistant text (the response to THIS
        # user turn) over the preceding (which is the context that
        # set up this turn). For handoff, we want the model to see
        # what it's continuing FROM.
        assistant_text = _truncate(n.following_assistant_text or n.preceding_assistant_text or "")
        if assistant_text:
            chunks.append(f"\nASSISTANT ({n.provider}): {assistant_text}\n")
        if n.provider and n.provider not in source_providers:
            source_providers.append(n.provider)
    chunks.append("\n--- End of prior log ---\n\n")
    if continuation:
        chunks.append(f"The user now asks: {continuation.strip()}\n")
    else:
        chunks.append(
            "Continue the conversation. Respond to the user's most "
            "recent message as a natural next turn.\n"
        )
    return "".join(chunks), source_providers


def run_handoff(
    target_provider: str,
    provider_configs: dict[str, ProviderConfig],
    *,
    continuation: str | None = None,
    num_turns: int = DEFAULT_TURNS,
    cwd: Path | None = None,
) -> HandoffResult:
    """Pull recent cross-provider context, dispatch to target, return result.

    Raises KeyError if `target_provider` isn't in provider_configs. The
    caller (CLI or MCP handler) is responsible for translating that
    into a user-facing error.
    """
    if target_provider not in provider_configs:
        return HandoffResult(
            target_provider=target_provider,
            target_model=None,
            context_turns=0,
            source_providers=[],
            response_text="",
            elapsed_seconds=0.0,
            error=(
                f"Unknown provider '{target_provider}'. "
                f"Available: {sorted(provider_configs)}"
            ),
        )
    config = provider_configs[target_provider]
    nodes = _select_recent_turns(num_turns)
    if not nodes:
        return HandoffResult(
            target_provider=target_provider,
            target_model=config.model,
            context_turns=0,
            source_providers=[],
            response_text="",
            elapsed_seconds=0.0,
            error=(
                "No recent prompts found in ~/.trinity/prompts/. "
                "Run `trinity-local seed-from-taste-terminal` first, "
                "or wait for incremental ingest to pick up new transcripts."
            ),
        )
    prompt, source_providers = build_handoff_prompt(
        nodes,
        continuation=continuation,
        target_provider=target_provider,
    )
    provider = make_provider(config)
    cwd = cwd or Path.cwd()
    result: ProviderResult = provider.run(prompt, cwd=cwd)
    error: str | None = None
    if result.returncode != 0:
        error = (
            f"{target_provider} returned exit {result.returncode}: "
            f"{(result.stderr or 'no stderr').strip()[:200]}"
        )
    return HandoffResult(
        target_provider=target_provider,
        target_model=config.model,
        context_turns=len(nodes),
        source_providers=source_providers,
        response_text=result.stdout,
        elapsed_seconds=result.elapsed_seconds,
        error=error,
    )
