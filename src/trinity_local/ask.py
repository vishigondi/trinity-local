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

# Token-economy budget for `ask` returns. The answer goes straight into the
# calling agent's context window — long returns are expensive in tokens AND in
# attention. Roughly 4 chars per token, so 2000 chars ≈ 500 tokens. Truncated
# with a one-line marker so the agent knows the output was capped (and can
# call `compare` or fetch the full council if it needs more).
ASK_ANSWER_CHAR_BUDGET = 2000
_TRUNCATION_MARKER = "\n\n[…truncated by Trinity for context economy — call `run_council` or read the council outcome for full output]"


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
        # Token-economy: keep this compact. The agent's context window is the
        # cost; verbose returns burn tokens AND attention. Truncate long
        # answers with a marker so the agent knows what was cut and can fetch
        # full output via `run_council` if needed.
        answer = self.answer
        if len(answer) > ASK_ANSWER_CHAR_BUDGET:
            answer = answer[: ASK_ANSWER_CHAR_BUDGET - len(_TRUNCATION_MARKER)] + _TRUNCATION_MARKER
        out = {
            "answer": answer,
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
    use_cortex: bool = True,
) -> AskDecision:
    """Pure decision logic — no dispatch. Useful for dry-run / inspection.

    Cortex layer is consulted first (week 3): classify the query into a basin
    via task_kind, look up the routing pattern, and IF its trust_score clears
    the band, use the cortex rule as the routing decision. The kNN path
    becomes the calibration / fallback when cortex trust is too low.

    `use_cortex=False` disables cortex lookup entirely — pure kNN. Useful for
    A/B testing during the human-calibration window.
    """
    if use_cortex:
        cortex_decision = _try_cortex_route(query, available_providers)
        if cortex_decision is not None:
            return cortex_decision
    hits = search_prompt_nodes(query, top_k=top_k)
    return _decide_from_hits(hits, available_providers=available_providers)


def _try_cortex_route(query: str, available_providers: list[str] | None) -> AskDecision | None:
    """Look up a cortex routing rule for this query. Returns None if no rule
    applies (no consolidation yet, basin doesn't match, or trust below floor).

    For v1.5 Week 3 we map query → basin via task_kind classification (same
    heuristic the chairman uses to label outcomes, so basin keys line up by
    construction). A centroid-based basin classifier landing later in Week 3
    upgrades this to soft top-3 membership; this is the simpler first cut.
    """
    try:
        from .cortex import TRUST_KNN_FALLBACK, load_routing_patterns
        from .task_kinds import guess_task_kind
    except ImportError:
        return None

    patterns = load_routing_patterns()
    if not patterns:
        return None  # no consolidation has run yet

    basin_id = guess_task_kind(query) or ""
    pattern = patterns.get(basin_id)
    if pattern is None:
        return None

    trust = pattern.trust_score.value
    if trust < TRUST_KNN_FALLBACK:
        # Cortex rule exists but trust is too low to drive routing alone —
        # fall through to kNN. The rule will surface as calibration context
        # in a future iteration but isn't used as the primary route.
        return None

    primary = pattern.routing_rule.primary
    if available_providers and primary not in available_providers:
        # Filter out unavailable primary — fall back to challenger if it's
        # available, otherwise let kNN handle it.
        challenger = pattern.routing_rule.challenger
        if challenger and challenger in available_providers:
            primary = challenger
        else:
            return None

    return AskDecision(
        routed_to=primary,
        trust_score=trust,
        runner_up=pattern.routing_rule.challenger,
        vote_counts={primary: pattern.n_episodes},
        evidence_prompt_ids=pattern.evidence[:5],
        reason=f"cortex rule for basin '{basin_id}' (trust={trust:.2f}, {pattern.trust_score.interpretation})",
    )


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

    # Pass 1: council-derived signals (user verdict + chairman pick).
    # These are highest-signal because they came out of explicit evaluation.
    votes: dict[str, float] = {}
    evidence: list[str] = []
    for hit in hits:
        # Each signal carries 1.0/1.5 if present. Same hit can vote multiple
        # times via different signals (chairman + user verdict).
        winner_signals = [
            (hit.user_winner, 1.5),     # strongest — user actively picked
            (hit.chairman_winner, 1.0),
        ]
        for provider, weight in winner_signals:
            if provider:
                votes[provider] = votes.get(provider, 0.0) + weight
                if hit.prompt_id not in evidence:
                    evidence.append(hit.prompt_id)

    # Pass 2 (cold-start fallback): if no council signal exists, fall back to
    # the prompt's origin provider — which CLI the user actually reached for.
    # Weak signal (0.5 weight) because "what they reached for" ≠ "what was
    # best", but better than no signal. This is what makes ask useful from
    # day-1 of install, before any councils have run. Skipped entirely when
    # any council signal is present — explicit evaluation dominates revealed
    # preference.
    reason: str
    if votes:
        reason = f"voted from {len(hits)} similar past prompts (council signals)"
    else:
        for hit in hits:
            if getattr(hit, "provider", ""):
                votes[hit.provider] = votes.get(hit.provider, 0.0) + 0.5
                if hit.prompt_id not in evidence:
                    evidence.append(hit.prompt_id)
        reason = f"voted from {len(hits)} similar past prompts (transcript origin only — no councils yet)"

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
    # Cold-start (transcript-origin only) signals are weaker — cap trust
    # accordingly so the escalate_hint fires more eagerly for the agent.
    trust = _compute_trust(
        votes,
        n_hits=len(hits),
        cold_start=("transcript origin only" in reason),
    )

    return AskDecision(
        routed_to=primary,
        trust_score=trust,
        runner_up=runner_up,
        vote_counts={p: int(v) for p, v in votes.items()},
        evidence_prompt_ids=evidence,
        reason=reason,
    )


def _compute_trust(votes: dict[str, float], n_hits: int, *, cold_start: bool = False) -> float:
    """4-component trust score will land in Week 2 alongside cortex rules.
    Week-1 stub uses 3 components (agreement, sample, recency-proxy=1.0) plus
    two hard floors:

    - **min-hits floor:** with fewer than 2 hits, trust caps at 0.5 regardless
      of agreement. One data point isn't enough signal to recommend without
      escalation.
    - **cold-start cap:** when the only signal is transcript-origin (the user
      reached for this provider before, but never explicitly evaluated it as
      best), cap trust at 0.55 — just below the escalate threshold — so the
      agent gets `escalate_hint=compare` and can choose to fan out for an
      explicit comparison. Routes-to-something-reasonable + suggests-compare
      is the right cold-start behavior.

    Both floors are explicit so the trust score stays interpretable: high
    trust requires either many similar past councils OR many similar past
    prompts with explicit user evaluation. Neither is true on day-1 of an
    install, so day-1 always escalates.
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

    if n_hits < 2:
        return min(raw, 0.5)
    if cold_start:
        return min(raw, 0.55)
    return raw


def run_ask(
    query: str,
    *,
    dispatch_fn: Callable[[str, str], str],
    top_k: int = 5,
    available_providers: list[str] | None = None,
    elapsed_ms: int | None = None,
    use_cortex: bool = True,
) -> AskResult:
    """End-to-end ask: route → dispatch → return.

    `dispatch_fn(provider_name, prompt) -> answer_text` is injected so tests
    can run without provider CLIs. Production wires through
    `providers.make_provider(...).run(prompt, cwd).stdout`.

    `use_cortex=False` disables cortex routing for A/B testing during the
    human-calibration window — pure kNN path. Defaults to True so once a
    consolidation pass has run, cortex rules drive routing for any basin
    whose trust_score clears the floor.
    """
    import time

    decision = decide_route(
        query,
        top_k=top_k,
        available_providers=available_providers,
        use_cortex=use_cortex,
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
