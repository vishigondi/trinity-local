"""The `ask` orchestration — single-call routing for v1.5.

`ask` is the cheap default tool Claude Code reaches for. Flow:

  1. Embed-or-substring-search the user query against the hippocampus
     (`memory.search_prompt_nodes`) — top-K similar past prompts of yours.
  2. Vote on provider from the hits using three signals (in priority):
     - council winners that came out of this prompt (chairman_winner)
     - user verdicts on those councils (user_winner)
     - which provider the user originally asked this prompt (PromptNode.provider)
  3. Compute trust_score from agreement strength + sample size + recency proxy.
  4. Dispatch (callback) to the chosen provider; concise structured return.

Week-1 scope per docs/spec-v1.5.md. Cortex-layer routing rules land in Week 2;
this is the kNN-only hippocampus path. Cortex rules will plug in here as a
*prior* over the vote, not a replacement.

`dispatch_fn` is intentionally an injected callable so tests can run end-to-end
without spawning real provider CLIs. Production wires `providers.make_provider(...)`
through.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from .memory import search_prompt_nodes


# trust_score weights — sum to 1.0. Tunable in Week 2 after the human-calibration gate.
_W_AGREEMENT = 0.55
_W_SAMPLE = 0.30
_W_RECENCY = 0.15

# Below this trust score the response should include an escalate_hint=compare so
# Claude in the harness can choose to call `compare` instead of trusting the ask.
ESCALATE_HINT_THRESHOLD = 0.55


@dataclass
class AskDecision:
    """Routing decision plus the evidence that produced it. Pre-dispatch."""

    routed_to: str
    trust_score: float
    runner_up: str | None
    vote_counts: dict[str, int]
    evidence_prompt_ids: list[str] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> dict:
        out = {
            "routed_to": self.routed_to,
            "trust_score": round(self.trust_score, 3),
            "vote_counts": self.vote_counts,
            "evidence_prompt_ids": self.evidence_prompt_ids[:5],
        }
        if self.runner_up:
            out["runner_up"] = self.runner_up
        if self.reason:
            out["reason"] = self.reason
        return out


@dataclass
class AskResult:
    """Final tool return — what Claude in the harness gets back."""

    answer: str
    routed_to: str
    trust_score: float
    runner_up: str | None
    escalate_hint: str | None  # e.g. "compare" when trust is low
    latency_ms: int
    decision: AskDecision

    def to_dict(self) -> dict:
        # Token-economy: keep this compact. Claude's context window is the cost.
        out = {
            "answer": self.answer,
            "routed_to": self.routed_to,
            "trust_score": round(self.trust_score, 3),
            "latency_ms": self.latency_ms,
        }
        if self.runner_up:
            out["runner_up"] = self.runner_up
        if self.escalate_hint:
            out["escalate_hint"] = self.escalate_hint
        return out


def decide_route(
    query: str,
    *,
    top_k: int = 5,
    available_providers: list[str] | None = None,
) -> AskDecision:
    """Pure decision logic — no dispatch. Useful for dry-run / inspection."""
    hits = search_prompt_nodes(query, top_k=top_k)
    return _decide_from_hits(hits, available_providers=available_providers)


def _decide_from_hits(
    hits: list,
    *,
    available_providers: list[str] | None,
) -> AskDecision:
    if not hits:
        return AskDecision(
            routed_to=(available_providers or ["claude"])[0],
            trust_score=0.0,
            runner_up=None,
            vote_counts={},
            evidence_prompt_ids=[],
            reason="no_history",
        )

    votes: dict[str, float] = {}
    evidence: list[str] = []
    for hit in hits:
        # Each signal carries 1.0 if present. The same hit can vote multiple
        # times via different signals (chairman + user verdict + origin).
        winner_signals = [
            (hit.user_winner, 1.5),     # strongest signal — user actively picked
            (hit.chairman_winner, 1.0),
        ]
        for provider, weight in winner_signals:
            if provider:
                votes[provider] = votes.get(provider, 0.0) + weight
                if hit.prompt_id not in evidence:
                    evidence.append(hit.prompt_id)
        # Fallback: prompt-origin provider (where the user actually sent the
        # prompt in the past). Weak signal — they may have just defaulted to
        # whatever was open — but better than nothing.
        # PromptNode field not exposed on SearchResult directly; skip in v1.

    if available_providers:
        votes = {p: v for p, v in votes.items() if p in available_providers}

    if not votes:
        return AskDecision(
            routed_to=(available_providers or ["claude"])[0],
            trust_score=0.0,
            runner_up=None,
            vote_counts={},
            evidence_prompt_ids=[h.prompt_id for h in hits[:5]],
            reason="hits_found_but_no_winner_signal",
        )

    ranked = sorted(votes.items(), key=lambda kv: kv[1], reverse=True)
    primary = ranked[0][0]
    runner_up = ranked[1][0] if len(ranked) > 1 else None
    trust = _compute_trust(votes, n_hits=len(hits))

    return AskDecision(
        routed_to=primary,
        trust_score=trust,
        runner_up=runner_up,
        vote_counts={p: int(v) for p, v in votes.items()},
        evidence_prompt_ids=evidence,
        reason=f"voted from {len(hits)} similar past prompts",
    )


def _compute_trust(votes: dict[str, float], n_hits: int) -> float:
    """4-component trust score will land in Week 2 alongside cortex rules.
    Week-1 stub uses 3 components (agreement, sample, recency-proxy=1.0) plus
    a hard floor: with fewer than 2 hits, trust caps at 0.5 regardless of
    agreement. One data point isn't enough signal to recommend without
    escalation. This makes the single-hit case explicitly low-trust so the
    `escalate_hint=compare` fires correctly.
    """
    total = sum(votes.values()) or 1.0
    top = max(votes.values())
    agreement = top / total  # 0..1 — winner's share of the vote

    # Sample size: 5 hits is "fully informed"; fewer hits dilute trust.
    sample_size = min(1.0, n_hits / 5.0)

    # Recency proxy is a placeholder in week 1 — kNN already biases toward
    # recent because search_prompt_nodes weights by recency. Plug full
    # recency-stability metric in week 2 when cortex consolidation ships.
    recency = 1.0

    raw = _W_AGREEMENT * agreement + _W_SAMPLE * sample_size + _W_RECENCY * recency

    # Hard floor: single-hit evidence caps at 0.5. Two hits in agreement is
    # the minimum bar for "confident enough to ship without escalation."
    if n_hits < 2:
        return min(raw, 0.5)
    return raw


def run_ask(
    query: str,
    *,
    dispatch_fn: Callable[[str, str], str],
    top_k: int = 5,
    available_providers: list[str] | None = None,
    elapsed_ms: int | None = None,
) -> AskResult:
    """End-to-end ask: route → dispatch → return.

    `dispatch_fn(provider_name, prompt) -> answer_text` is injected so tests
    can run without provider CLIs. Production wires through
    `providers.make_provider(...).run(prompt, cwd).stdout`.
    """
    import time

    decision = decide_route(
        query,
        top_k=top_k,
        available_providers=available_providers,
    )

    t0 = time.monotonic()
    answer = dispatch_fn(decision.routed_to, query)
    dispatch_ms = int((time.monotonic() - t0) * 1000)
    total_ms = elapsed_ms if elapsed_ms is not None else dispatch_ms

    escalate = "compare" if decision.trust_score < ESCALATE_HINT_THRESHOLD else None

    return AskResult(
        answer=answer,
        routed_to=decision.routed_to,
        trust_score=decision.trust_score,
        runner_up=decision.runner_up,
        escalate_hint=escalate,
        latency_ms=total_ms,
        decision=decision,
    )
