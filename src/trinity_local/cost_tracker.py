"""Session cost aggregation for cross-provider comparison.

Maps (provider, model_id) → estimated cost per token and computes per-session
and per-week cost summaries. Costs are approximate — the goal is relative
comparison, not billing accuracy.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import trinity_home
from .training_schema import SessionFeatures


# ---------------------------------------------------------------------------
# Cost table — approximate $/1M tokens, user-overridable via config
# Prices sourced from GitHub Copilot billing (June 2026 rates).
# ---------------------------------------------------------------------------

_DEFAULT_COSTS: dict[str, dict[str, float]] = {
    # Claude
    "claude-opus-4": {"input": 5.0, "output": 25.0},
    "claude-sonnet-4": {"input": 3.0, "output": 15.0},
    "claude-haiku-4": {"input": 1.0, "output": 5.0},
    # Gemini
    "gemini-3.1-pro": {"input": 2.0, "output": 12.0},
    "gemini-2.5-pro": {"input": 1.25, "output": 10.0},
    "gemini-3-flash": {"input": 0.50, "output": 3.0},
    "gemini-2.5-flash": {"input": 0.30, "output": 2.50},
    # OpenAI (Codex uses these)
    "gpt-5.5": {"input": 5.0, "output": 30.0},
    "gpt-5.4": {"input": 2.50, "output": 15.0},
    "gpt-5.3-codex": {"input": 1.75, "output": 14.0},
    "gpt-5.2": {"input": 1.75, "output": 14.0},
    "gpt-5.4-mini": {"input": 0.75, "output": 4.50},
    "gpt-5-mini": {"input": 0.25, "output": 2.0},
    "gpt-5.4-nano": {"input": 0.20, "output": 1.25},
    "gpt-4.1": {"input": 2.0, "output": 8.0},
    # Local (free)
    "mlx": {"input": 0.0, "output": 0.0},
}


def _find_cost_rate(model_id: str | None) -> dict[str, float]:
    """Find the best-matching cost rate for a model ID."""
    if not model_id:
        return {"input": 0.0, "output": 0.0}
    normalized = model_id.lower().strip()
    # Try exact prefix match (longest first)
    for prefix in sorted(_DEFAULT_COSTS.keys(), key=len, reverse=True):
        if normalized.startswith(prefix):
            return _DEFAULT_COSTS[prefix]
    return {"input": 0.0, "output": 0.0}


# ---------------------------------------------------------------------------
# Per-session cost computation
# ---------------------------------------------------------------------------

@dataclass
class SessionCost:
    """Cost estimate for a single session."""
    session_id: str
    provider: str
    model_id: str | None
    input_tokens: int
    output_tokens: int
    cached_tokens: int
    input_cost_usd: float
    output_cost_usd: float
    total_cost_usd: float
    started_at: str | None = None
    task_kind: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v not in (None, 0, 0.0)}


def compute_session_cost(features: SessionFeatures, *, task_kind: str | None = None) -> SessionCost:
    """Compute estimated cost for a session from its extracted features."""
    input_tokens = features.outcome.token_input or 0
    output_tokens = features.outcome.token_output or 0
    cached_tokens = features.outcome.token_cached or 0

    model_id = features.model.normalized_model_id
    rate = _find_cost_rate(model_id)

    # Cached tokens are typically free or heavily discounted
    billable_input = max(0, input_tokens - cached_tokens)
    input_cost = billable_input * rate["input"] / 1_000_000
    output_cost = output_tokens * rate["output"] / 1_000_000

    return SessionCost(
        session_id=features.session_id,
        provider=features.provider,
        model_id=model_id,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        cached_tokens=cached_tokens,
        input_cost_usd=round(input_cost, 6),
        output_cost_usd=round(output_cost, 6),
        total_cost_usd=round(input_cost + output_cost, 6),
        started_at=features.started_at,
        task_kind=task_kind,
    )


# ---------------------------------------------------------------------------
# Aggregate cost tracking
# ---------------------------------------------------------------------------

@dataclass
class CostSummary:
    """Aggregated costs over a time period."""
    provider: str
    sessions: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_cached_tokens: int = 0
    total_cost_usd: float = 0.0
    by_task_kind: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v not in (None, 0, 0.0, {}, [])}


def _cost_log_path() -> Path:
    path = trinity_home() / "cost_log.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def append_session_cost(cost: SessionCost) -> None:
    """Append a session cost record to the cost log."""
    with _cost_log_path().open("a", encoding="utf-8") as f:
        f.write(json.dumps(cost.to_dict()) + "\n")


def load_cost_log(*, since_days: int = 7) -> list[SessionCost]:
    """Load cost records from the log, optionally filtered by recency."""
    path = _cost_log_path()
    if not path.exists():
        return []

    cutoff = None
    if since_days > 0:
        cutoff = datetime.now(timezone.utc).timestamp() - (since_days * 86400)

    records: list[SessionCost] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        started_at = raw.get("started_at")
        if cutoff and started_at:
            try:
                ts = datetime.fromisoformat(started_at.replace("Z", "+00:00")).timestamp()
                if ts < cutoff:
                    continue
            except ValueError:
                pass
        records.append(SessionCost(
            session_id=raw.get("session_id", ""),
            provider=raw.get("provider", ""),
            model_id=raw.get("model_id"),
            input_tokens=raw.get("input_tokens", 0),
            output_tokens=raw.get("output_tokens", 0),
            cached_tokens=raw.get("cached_tokens", 0),
            input_cost_usd=raw.get("input_cost_usd", 0.0),
            output_cost_usd=raw.get("output_cost_usd", 0.0),
            total_cost_usd=raw.get("total_cost_usd", 0.0),
            started_at=started_at,
            task_kind=raw.get("task_kind"),
        ))
    return records


def summarize_costs(costs: list[SessionCost]) -> dict[str, CostSummary]:
    """Aggregate session costs by provider."""
    by_provider: dict[str, CostSummary] = {}
    for cost in costs:
        summary = by_provider.setdefault(cost.provider, CostSummary(provider=cost.provider))
        summary.sessions += 1
        summary.total_input_tokens += cost.input_tokens
        summary.total_output_tokens += cost.output_tokens
        summary.total_cached_tokens += cost.cached_tokens
        summary.total_cost_usd += cost.total_cost_usd
        if cost.task_kind:
            summary.by_task_kind[cost.task_kind] = (
                summary.by_task_kind.get(cost.task_kind, 0.0) + cost.total_cost_usd
            )
    # Round totals
    for summary in by_provider.values():
        summary.total_cost_usd = round(summary.total_cost_usd, 4)
        summary.by_task_kind = {k: round(v, 4) for k, v in summary.by_task_kind.items()}
    return by_provider
