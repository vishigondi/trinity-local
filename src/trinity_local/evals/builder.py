"""Eval-set builder. Reads ~/.trinity/me/rejections.jsonl + the prompt
index, emits a replayable JSON eval set with one item per labeled
rejection.

Schema is intentionally narrow for MVP (#122). v1 ships:

  {
    "eval_id": "eval_<8-char-hash>",
    "built_at": "2026-05-14T...",
    "source": "rejections",          # cross_provider_pair source comes later
    "stats": {
      "items": 44,
      "by_rejection_type": {"REFRAME": 12, "COMPRESSION": 5, ...},
      "by_basin": {"b00": 3, "b12": 8, ...},
    },
    "items": [
      {
        "eval_item_id": "ei_<hash>",
        "prompt": "<original user prompt that elicited the rejected response>",
        "rejection_type": "REFRAME",
        "rejected_response": "<model_quote>",
        "user_substitute": "<what the user actually wanted in their next turn>",
        "rubric_signal": "<chairman-extracted why_signal>",
        "basin_id": "b12",
        "source": "rejections",
        "source_id": "r_002",
        "prompt_id": "pnode_db27791f15a2d260",
        "provider_of_rejected_response": null,  # populated when prompt_node carries provider
      },
      ...
    ]
  }

The eval set is content-addressed by hash so the same corpus state
produces a stable eval_id — re-running `build_eval_set()` on an
unchanged corpus is idempotent.

Future runner consumes this shape: for each item, dispatch `prompt`
to a target provider, capture response, ask chairman-judge "given
the user's lens, is target_response better than rejected_response
on the {rejection_type} axis?"
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..state_paths import state_dir


def evals_dir() -> Path:
    """`~/.trinity/evals/` — eval sets + per-run results live here."""
    path = state_dir() / "evals"
    path.mkdir(parents=True, exist_ok=True)
    return path


def results_dir() -> Path:
    """`~/.trinity/evals/results/` — populated by future runner ticks."""
    path = evals_dir() / "results"
    path.mkdir(parents=True, exist_ok=True)
    return path


@dataclass(frozen=True)
class EvalItem:
    """One eval item: an empirically-rejected (prompt, response) pair
    that any candidate model can be scored against."""
    eval_item_id: str
    prompt: str
    rejection_type: str
    rejected_response: str
    user_substitute: str
    rubric_signal: str
    basin_id: str | None
    source: str  # "rejections" today; "cross_provider_pair" later
    source_id: str
    prompt_id: str | None
    provider_of_rejected_response: str | None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EvalSet:
    """A complete eval set; serializes to one JSON file."""
    eval_id: str
    built_at: str
    source: str
    stats: dict
    items: list[EvalItem] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "eval_id": self.eval_id,
            "built_at": self.built_at,
            "source": self.source,
            "stats": self.stats,
            "items": [item.to_dict() for item in self.items],
        }


def _stable_id(prefix: str, *parts: str) -> str:
    """sha1 hash truncated to 12 chars, prefixed. Same shape as
    utils.stable_id but localized to the evals module since we slice
    differently (12 chars vs 16) — eval IDs need to be readable in
    CLI output."""
    blob = "|".join(parts).encode("utf-8")
    return f"{prefix}_{hashlib.sha1(blob).hexdigest()[:12]}"


def _norm_eval_text(text: str) -> str:
    """Whitespace+case-collapsed text for the prompt==gold degeneracy check (#247)."""
    return " ".join((text or "").lower().split())


def _lookup_prompt_text(prompt_id: str | None) -> tuple[str, str | None]:
    """Return (prompt_text, provider) for a given prompt_id, or
    (empty, None) if not in the index.

    The rejection record carries the prompt_id; we want the actual
    prompt text plus the provider that produced the rejected response
    so eval results can attribute "this is what we expected $provider
    to do better than".
    """
    if not prompt_id:
        return "", None
    # Late-import to avoid pulling memory.store at module-load time
    # (heavy import chain). Only the builder needs it.
    from ..memory.store import load_prompt_node

    node = load_prompt_node(prompt_id)
    if node is None:
        return "", None
    return (node.text or "").strip(), getattr(node, "provider", None)


def build_eval_set(*, source: str = "rejections", limit: int | None = None) -> EvalSet:
    """Assemble an eval set from the current corpus.

    `source="rejections"` is the only path live in MVP. The shape is
    stable; future sources (cross_provider_pair, council_outcomes with
    user_winner mismatch) append to the same items list.

    Raises FileNotFoundError if rejections.jsonl doesn't exist — better
    than silently returning an empty set, which would mask a misconfig.
    """
    from ..me.preference_acts import preference_acts_path

    if source != "rejections":
        raise NotImplementedError(
            f"source={source!r} not yet wired. MVP supports 'rejections' only."
        )

    # #209: the unified ledger is the sole store. Eval items still draw the
    # model_miss subset (via iter_preference_acts below); the existence check
    # points at the ledger. First, best-effort recover any legacy
    # rejections.jsonl / decisions.jsonl into the ledger (review finding #3)
    # so an un-migrated upgrade doesn't see an empty eval set.
    try:
        from ..me.preference_acts import _migrate_legacy_preference_stores
        _migrate_legacy_preference_stores()
    except Exception:
        pass
    ledger_path = preference_acts_path()
    if not ledger_path.exists():
        raise FileNotFoundError(
            f"No preference-act ledger at {ledger_path}. "
            f"Run `trinity-local lens-build` to mine rejections from turn pairs first."
        )

    items: list[EvalItem] = []
    skipped_degenerate = 0  # #247: items dropped because prompt == gold
    by_type: dict[str, int] = {}
    by_basin: dict[str, int] = {}

    # EXTRACT-unification Stage 2: source eval items through the unified
    # PreferenceAct read layer, filtered to model-miss (the rejection
    # subset — "the model got it wrong, can a model avoid it?"). This is
    # behavior-preserving (model_miss acts come from the same
    # rejections.jsonl the loud-failure check above guards), but routes
    # the eval harness through the one evidence type. Self-expressed acts
    # (decisions) stay out of the eval set for now — including them is a
    # future enhancement, not this stage.
    from ..me.preference_acts import MODEL_MISS, iter_preference_acts

    for act in iter_preference_acts():
        if act.trigger != MODEL_MISS:
            continue
        rej_type = act.kind
        model_quote = (act.sacrificed or "").strip()
        user_sub = (act.privileged or "").strip()
        source_id = act.id or ""
        prompt_id = act.prompt_id
        if not (rej_type and model_quote and source_id):
            continue
        prompt_text, provider = _lookup_prompt_text(prompt_id)
        resolved = bool(prompt_text)
        # If the prompt_id no longer resolves (corpus churn between
        # lens-build and eval-build), fall back to user_substitute as a
        # stand-in — keep the rejection-shape signal even when the
        # originating prompt has been garbage-collected.
        if not prompt_text:
            prompt_text = user_sub
        # Drop trivially-passable items: when the RESOLVED prompt IS the gold
        # (#247). The Stage-0 schema excerpts user_substitute from the same user
        # turn prompt_id points to, so for short turns (median 9 words < the
        # 25-word cap) the excerpt == the full turn == the prompt — 71% of the
        # newest set. The judge's gold then equals the prompt, so any echo passes
        # and the rejection-axis delta has no signal. Skip (data-sampling
        # floor-guard). Only when the lookup RESOLVED — the unresolved fallback
        # above is a separate corpus-churn stand-in, intentionally kept.
        if resolved and _norm_eval_text(prompt_text) == _norm_eval_text(user_sub):
            skipped_degenerate += 1
            continue
        items.append(EvalItem(
            eval_item_id=_stable_id("ei", source_id, rej_type),
            prompt=prompt_text,
            rejection_type=rej_type,
            rejected_response=model_quote,
            user_substitute=user_sub,
            rubric_signal=(act.why or "").strip(),
            basin_id=act.basin,
            source="rejections",
            source_id=source_id,
            prompt_id=prompt_id,
            provider_of_rejected_response=provider,
        ))
    # #269 EVAL nomination: when limiting, draw the benchmark from the user's
    # HIGHEST-SIGNAL threads (real, multi-turn, substantive work) rather than
    # the first N in ledger order — the best threads make the best evals. Rank
    # each rejection by its originating thread's signal, then truncate.
    if limit is not None and len(items) > limit:
        try:
            from ..me.thread_signal import compute_thread_signals
            from ..memory.store import iter_prompt_nodes_no_embedding

            sig = compute_thread_signals()
            pid2tid = {
                getattr(n, "id", ""): getattr(n, "transcript_id", "") or ""
                for n in iter_prompt_nodes_no_embedding(limit=None)
            }
            items.sort(key=lambda it: -sig.get(pid2tid.get(it.prompt_id, ""), 0.0))
        except Exception:
            pass  # ranking is a preference, never a hard dependency
        items = items[:limit]

    # Recompute the type/basin histograms over the FINAL (possibly truncated)
    # item set so the stats describe what's actually in the eval.
    for it in items:
        by_type[it.rejection_type] = by_type.get(it.rejection_type, 0) + 1
        if it.basin_id:
            by_basin[it.basin_id] = by_basin.get(it.basin_id, 0) + 1

    # Content-addressed eval_id: hash of the source_ids so re-running on
    # the same corpus produces the same eval_id (idempotent), but adding
    # new rejections produces a new id (so historical eval results stay
    # pinned to the corpus state they were scored against).
    fingerprint = "|".join(sorted(it.source_id for it in items))
    eval_id = _stable_id("eval", source, fingerprint)

    stats = {
        "items": len(items),
        "by_rejection_type": dict(sorted(by_type.items(), key=lambda kv: -kv[1])),
        "by_basin": dict(sorted(by_basin.items(), key=lambda kv: -kv[1])),
        # #247 visibility: how many model_miss acts were dropped as
        # trivially-passable (prompt == gold). High values flag the Stage-0
        # excerpt==prompt degeneracy at its source.
        "skipped_degenerate": skipped_degenerate,
    }

    return EvalSet(
        eval_id=eval_id,
        built_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        source=source,
        stats=stats,
        items=items,
    )


def save_eval_set(eval_set: EvalSet) -> Path:
    """Persist to ~/.trinity/evals/<eval_id>.json. Returns the path.

    Contract: schemas/eval_set.schema.json declares `stats.items` (the
    integer item count) as required. The dataclass types stats as a
    bare dict — no shape enforcement at construction time, so a future
    code path that builds an EvalSet with the wrong stats shape would
    silently write a schema-invalid JSON. Fail fast at the boundary
    (same pattern as save_council_outcome — sweep iter #106).
    """
    if not isinstance(eval_set.stats, dict) or "items" not in eval_set.stats:
        raise ValueError(
            f"save_eval_set refused: eval_set.stats must be a dict with "
            f"`items` (the integer count of eval items). Got "
            f"{type(eval_set.stats).__name__} with keys "
            f"{list(eval_set.stats.keys()) if isinstance(eval_set.stats, dict) else 'n/a'}. "
            f"Schema declares `stats.items` required."
        )

    path = evals_dir() / f"{eval_set.eval_id}.json"
    path.write_text(
        json.dumps(eval_set.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def load_eval_set(eval_id: str) -> EvalSet | None:
    """Read back an eval set by id. Returns None if not found."""
    path = evals_dir() / f"{eval_id}.json"
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    items = [
        EvalItem(
            eval_item_id=it.get("eval_item_id", ""),
            prompt=it.get("prompt", ""),
            rejection_type=it.get("rejection_type", ""),
            rejected_response=it.get("rejected_response", ""),
            user_substitute=it.get("user_substitute", ""),
            rubric_signal=it.get("rubric_signal", ""),
            basin_id=it.get("basin_id"),
            source=it.get("source", "rejections"),
            source_id=it.get("source_id", ""),
            prompt_id=it.get("prompt_id"),
            provider_of_rejected_response=it.get("provider_of_rejected_response"),
        )
        for it in raw.get("items", [])
    ]
    return EvalSet(
        eval_id=raw.get("eval_id", eval_id),
        built_at=raw.get("built_at", ""),
        source=raw.get("source", "rejections"),
        stats=raw.get("stats", {}),
        items=items,
    )
