"""Hard example mining — extract challenging examples for model evaluation.

This module identifies sessions that are informative for improving routing:
  - Switched tasks: user abandoned one provider and moved to another
  - Failed sessions: high error rates, incomplete, or very short
  - Needs council: ambiguous signals suggesting multi-provider review
  - Reroutes: prompt appeared in multiple providers within a time window
  - Disagreement cases: high-error sessions that still completed

Signals are mined from raw transcripts via feature extraction, then
cross-referenced across providers using embedding similarity.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from ..feature_extractors import extract_session_features
from ..state_paths import hard_examples_dir
from ..training_schema import (
    ModelDescriptor,
    OutcomeSignals,
    RoutingExample,
    SessionFeatures,
    TranscriptWindow,
)
from ..utils import stable_id
from .replay import _guess_task_kind, _iter_source_sessions


# hard_examples_dir is now imported from state_paths above


@dataclass
class HardMiningStats:
    """Summary of a hard mining run."""
    sessions_scanned: int = 0
    switched: int = 0
    failed: int = 0
    needs_council: int = 0
    rerouted: int = 0
    disagreement: int = 0
    cross_provider_pairs: int = 0
    total_hard: int = 0
    errors: int = 0


@dataclass
class HardExample:
    """A hard routing example with detailed signals."""
    example_id: str
    hard_type: str  # "switched", "failed", "needs_council", "rerouted", "disagreement"
    transcript: TranscriptWindow
    chosen_provider: str
    chosen_model: ModelDescriptor
    label: str  # derived from hard_type
    outcome: OutcomeSignals
    confidence: float | None = None
    # Cross-provider matching
    related_sessions: list[dict[str, Any]] = field(default_factory=list)
    hard_signals: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "example_id": self.example_id,
            "hard_type": self.hard_type,
            "transcript": self.transcript.to_dict(),
            "chosen_provider": self.chosen_provider,
            "chosen_model": self.chosen_model.to_dict(),
            "label": self.label,
            "outcome": self.outcome.to_dict(),
            "confidence": self.confidence,
            "related_sessions": self.related_sessions,
            "hard_signals": self.hard_signals,
        }

    def to_routing_example(self) -> RoutingExample:
        """Convert to standard RoutingExample for evaluation."""
        return RoutingExample(
            example_id=self.example_id,
            transcript=self.transcript,
            chosen_provider=self.chosen_provider,
            chosen_model=self.chosen_model,
            label=self.label,
            confidence=self.confidence,
            alternatives=[],
            reasons=[f"hard_type:{self.hard_type}"],
        )


def _classify_hard_type(features: SessionFeatures) -> str | None:
    """Classify a session into a hard example type, or None if easy.

    Signal-based hard criteria (applied during initial scan):
      - Explicit switch signals
      - Any tool errors (rare, so all are valuable)
      - Long sessions with many turns (ambiguous outcome)
      - Very short sessions that aborted quickly
    """
    outcome = features.outcome
    tool_calls = outcome.tool_calls_total or 0
    tool_errors = outcome.tool_errors_total or 0
    assistant_turns = outcome.assistant_turns or 0

    # 1. Switched: explicit provider switch signal
    if outcome.switched_after or outcome.switched_to_provider:
        return "switched"

    # 2. Failed: any tool errors are signal (they're rare)
    if tool_errors >= 1:
        if not outcome.completed:
            return "failed"
        error_rate = tool_errors / max(tool_calls, 1)
        if error_rate > 0.15:
            return "disagreement"

    # 3. Long sessions (high effort, ambiguous routing)
    if assistant_turns > 15 and tool_calls >= 5:
        return "needs_council"

    # 4. Short aborted sessions (started but gave up quickly)
    if not outcome.completed and assistant_turns <= 2 and tool_calls >= 3:
        return "failed"

    return None


def _hard_type_to_label(hard_type: str) -> str:
    """Map hard type to routing label."""
    return {
        "switched": "bad_fit",
        "failed": "bad_fit",
        "needs_council": "needs_council",
        "rerouted": "bad_fit",
        "disagreement": "needs_council",
    }.get(hard_type, "needs_council")


def _build_hard_signals(features: SessionFeatures, hard_type: str) -> dict[str, Any]:
    """Extract diagnostic signals for a hard example."""
    outcome = features.outcome
    tool_calls = outcome.tool_calls_total or 0
    error_rate = (outcome.tool_errors_total or 0) / max(tool_calls, 1) if tool_calls > 0 else 0.0

    return {
        "hard_type": hard_type,
        "completed": outcome.completed,
        "assistant_turns": outcome.assistant_turns,
        "user_turns": outcome.user_turns,
        "tool_calls": tool_calls,
        "tool_errors": outcome.tool_errors_total,
        "error_rate": round(error_rate, 3),
        "session_seconds": outcome.session_seconds,
        "switched_after": outcome.switched_after,
        "switched_to": outcome.switched_to_provider,
        "files_touched": outcome.files_touched,
    }

def _classify_hard_type_lenient(features: SessionFeatures) -> str | None:
    """Lenient classifier — used only for embedding-based mining.

    Captures sessions that might be interesting for cross-provider analysis.
    Criteria: has enough content to meaningfully embed.
    """
    outcome = features.outcome
    assistant_turns = outcome.assistant_turns or 0
    tool_calls = outcome.tool_calls_total or 0

    # Must have some substance
    if assistant_turns < 2:
        return None

    # Needs at least some tool usage to be a real coding session
    if tool_calls < 2:
        return None

    # If it looks like a good signal-based hard example, use that type
    signal_type = _classify_hard_type(features)
    if signal_type:
        return signal_type

    # Otherwise mark as "candidate" for embedding-based classification
    return "candidate"


def mine_hard_via_embeddings(
    sources: list[str] | None = None,
    *,
    cross_provider_threshold: float = 0.7,
    max_per_provider: int = 50,
) -> tuple[list[HardExample], HardMiningStats]:
    """Mine hard examples using embedding similarity across providers.

    Strategy:
      1. Sample sessions from each provider (lenient filter)
      2. Embed all session prompts
      3. Find cross-provider pairs above threshold
      4. Any session near another provider's session = hard example
      5. Also include signal-based hard examples (errors, switches)
    """
    try:
        from .. import embeddings as emb
    except ImportError:
        return mine_hard_examples(sources)

    sources = sources or ["claude", "codex", "gemini", "cowork"]
    stats = HardMiningStats()

    # Phase 1: collect candidate sessions per provider
    candidates_by_provider: dict[str, list[tuple[SessionFeatures, str]]] = {}
    signal_hard: list[tuple[SessionFeatures, str]] = []  # Signal-based hards

    for source in sources:
        candidates = []
        for _, session in _iter_source_sessions(source):
            stats.sessions_scanned += 1
            try:
                features = extract_session_features(session)
            except Exception:
                stats.errors += 1
                continue

            prompt = (features.first_user_text or "").strip()
            if not prompt or len(prompt) < 20:
                continue
            if features.extra.get("is_low_signal_prompt") or features.extra.get("is_automated"):
                continue

            ht = _classify_hard_type_lenient(features)
            if ht is None:
                continue

            if ht != "candidate":
                signal_hard.append((features, ht))

            candidates.append((features, ht))

        candidates_by_provider[source] = candidates

    # Phase 2: sample and embed
    import random
    random.seed(42)
    sampled: list[tuple[SessionFeatures, str]] = []
    for provider, candidates in candidates_by_provider.items():
        n = min(max_per_provider, len(candidates))
        sampled.extend(random.sample(candidates, n))
    # Always include all signal-based hards
    signal_ids = {f.session_id for f, _ in signal_hard}
    for features, ht in signal_hard:
        if not any(f.session_id == features.session_id for f, _ in sampled):
            sampled.append((features, ht))

    # Embed all prompts
    vectors: dict[str, list[float]] = {}
    features_map: dict[str, tuple[SessionFeatures, str]] = {}
    for features, ht in sampled:
        sid = features.session_id
        if sid in vectors:
            continue
        prompt = (features.first_user_text or "").strip()
        vectors[sid] = emb.embed(prompt, dim=512)
        features_map[sid] = (features, ht)

    # Phase 3: find cross-provider pairs
    sids = list(vectors.keys())
    cross_pairs: list[tuple[str, str, float]] = []
    for i in range(len(sids)):
        for j in range(i + 1, len(sids)):
            fa, _ = features_map[sids[i]]
            fb, _ = features_map[sids[j]]
            if fa.provider == fb.provider:
                continue
            sim = sum(a * b for a, b in zip(vectors[sids[i]], vectors[sids[j]]))
            if sim >= cross_provider_threshold:
                cross_pairs.append((sids[i], sids[j], sim))

    stats.cross_provider_pairs = len(cross_pairs)

    # Phase 4: build hard examples
    hard_ids: set[str] = set()
    hard_examples: list[HardExample] = []

    # All cross-provider pair members are "rerouted"
    for sid_a, sid_b, sim in cross_pairs:
        for sid in (sid_a, sid_b):
            if sid in hard_ids:
                continue
            hard_ids.add(sid)
            features, ht = features_map[sid]
            ht_final = "rerouted" if ht == "candidate" else ht
            hard_examples.append(_build_hard_example(features, ht_final, sim=sim))
            stats.rerouted += 1

    # All signal-based hards
    for features, ht in signal_hard:
        if features.session_id in hard_ids:
            continue
        hard_ids.add(features.session_id)
        hard_examples.append(_build_hard_example(features, ht))
        if ht == "switched":
            stats.switched += 1
        elif ht == "failed":
            stats.failed += 1
        elif ht == "needs_council":
            stats.needs_council += 1
        elif ht == "disagreement":
            stats.disagreement += 1

    stats.total_hard = len(hard_examples)

    # Annotate cross-provider relationships
    for sid_a, sid_b, sim in cross_pairs:
        ex_a = next((e for e in hard_examples if e.transcript.session_id == sid_a), None)
        ex_b = next((e for e in hard_examples if e.transcript.session_id == sid_b), None)
        if ex_a and ex_b:
            ex_a.related_sessions.append({
                "session_id": sid_b,
                "provider": ex_b.chosen_provider,
                "similarity": round(sim, 4),
            })
            ex_b.related_sessions.append({
                "session_id": sid_a,
                "provider": ex_a.chosen_provider,
                "similarity": round(sim, 4),
            })

    return hard_examples, stats


def _build_hard_example(features: SessionFeatures, hard_type: str, *, sim: float | None = None) -> HardExample:
    """Build a HardExample from features."""
    prompt = (features.first_user_text or "").strip()
    task_kind = _guess_task_kind(prompt)
    label = _hard_type_to_label(hard_type)

    window = TranscriptWindow(
        session_id=features.session_id,
        provider=features.provider,
        source_path=features.raw.source_path,
        started_at=features.started_at,
        ended_at=features.ended_at,
        cwd=features.cwd,
        project_hint=features.project_hint,
        first_user_text=prompt[:2000],
        planner_text=(features.planner_text or "")[:1000] or None,
        final_text=(features.final_text or "")[:1000] or None,
        task_kind_hint=task_kind,
        model=features.model,
        tools=features.tools,
        outcome=features.outcome,
    )

    example_id = stable_id("hard", features.session_id, features.provider)
    hard_signals = _build_hard_signals(features, hard_type)
    if sim is not None:
        hard_signals["cross_provider_sim"] = round(sim, 4)

    return HardExample(
        example_id=example_id,
        hard_type=hard_type,
        transcript=window,
        chosen_provider=features.provider,
        chosen_model=features.model,
        label=label,
        outcome=features.outcome,
        hard_signals=hard_signals,
    )


def mine_hard_examples(
    sources: list[str] | None = None,
    *,
    limit: int | None = None,
) -> tuple[list[HardExample], HardMiningStats]:
    """Scan all sources and extract hard examples (signal-based only).

    Returns (hard_examples, stats). For embedding-based mining,
    use mine_hard_via_embeddings() instead.
    """
    sources = sources or ["claude", "codex", "gemini", "cowork"]
    stats = HardMiningStats()
    hard_examples: list[HardExample] = []

    for source in sources:
        for _, session in _iter_source_sessions(source):
            if limit and stats.total_hard >= limit:
                break
            stats.sessions_scanned += 1

            try:
                features = extract_session_features(session)
            except Exception:
                stats.errors += 1
                continue

            # Skip automated/low-signal
            prompt = (features.first_user_text or "").strip()
            if not prompt:
                continue
            if features.extra.get("is_low_signal_prompt") or features.extra.get("is_automated"):
                continue

            hard_type = _classify_hard_type(features)
            if hard_type is None:
                continue

            # Count by type
            if hard_type == "switched":
                stats.switched += 1
            elif hard_type == "failed":
                stats.failed += 1
            elif hard_type == "needs_council":
                stats.needs_council += 1
            elif hard_type == "disagreement":
                stats.disagreement += 1

            hard_examples.append(_build_hard_example(features, hard_type))
            stats.total_hard += 1

    return hard_examples, stats


def find_cross_provider_pairs(
    hard_examples: list[HardExample],
    *,
    similarity_threshold: float = 0.7,
) -> list[tuple[HardExample, HardExample, float]]:
    """Find pairs of hard examples from different providers with similar prompts.

    Uses the shared embedding package for semantic matching.
    Returns list of (example_a, example_b, similarity_score).
    """
    try:
        from .. import embeddings as emb
        if not emb.is_available():
            return []
    except ImportError:
        return []

    pairs: list[tuple[HardExample, HardExample, float]] = []
    for i, ex_a in enumerate(hard_examples):
        for j, ex_b in enumerate(hard_examples):
            if j <= i:
                continue
            if ex_a.chosen_provider == ex_b.chosen_provider:
                continue
            prompt_a = ex_a.transcript.first_user_text or ""
            prompt_b = ex_b.transcript.first_user_text or ""
            if not prompt_a or not prompt_b:
                continue

            sim = emb.similarity(prompt_a, prompt_b)
            if sim >= similarity_threshold:
                pairs.append((ex_a, ex_b, sim))

    return pairs


def save_hard_examples(examples: list[HardExample]) -> Path:
    """Save hard examples to disk."""
    out_dir = hard_examples_dir()
    for ex in examples:
        path = out_dir / f"{ex.example_id}.json"
        path.write_text(json.dumps(ex.to_dict(), indent=2), encoding="utf-8")
    return out_dir


def load_hard_examples() -> list[HardExample]:
    """Load hard examples from disk."""
    out_dir = hard_examples_dir()
    if not out_dir.exists():
        return []

    examples: list[HardExample] = []
    for path in sorted(out_dir.glob("*.json")):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            t = raw["transcript"]
            outcome_raw = raw.get("outcome", {})
            transcript = TranscriptWindow(
                session_id=t["session_id"],
                provider=t["provider"],
                source_path=t["source_path"],
                started_at=t.get("started_at"),
                ended_at=t.get("ended_at"),
                cwd=t.get("cwd"),
                project_hint=t.get("project_hint"),
                first_user_text=t.get("first_user_text"),
                planner_text=t.get("planner_text"),
                final_text=t.get("final_text"),
                task_kind_hint=t.get("task_kind_hint"),
                model=ModelDescriptor(**t.get("model", {"provider": ""})),
                outcome=OutcomeSignals(**{
                    k: v for k, v in t.get("outcome", {}).items()
                    if k != "extra"
                }) if t.get("outcome") else OutcomeSignals(),
            )
            examples.append(HardExample(
                example_id=raw["example_id"],
                hard_type=raw["hard_type"],
                transcript=transcript,
                chosen_provider=raw["chosen_provider"],
                chosen_model=ModelDescriptor(**raw.get("chosen_model", {"provider": ""})),
                label=raw["label"],
                outcome=OutcomeSignals(**{
                    k: v for k, v in outcome_raw.items()
                    if k != "extra"
                }) if outcome_raw else OutcomeSignals(),
                confidence=raw.get("confidence"),
                related_sessions=raw.get("related_sessions", []),
                hard_signals=raw.get("hard_signals", {}),
            ))
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
    return examples
