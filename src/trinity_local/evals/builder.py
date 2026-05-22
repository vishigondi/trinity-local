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
    from ..me.turn_pairs import rejections_path

    if source != "rejections":
        raise NotImplementedError(
            f"source={source!r} not yet wired. MVP supports 'rejections' only."
        )

    rej_path = rejections_path()
    if not rej_path.exists():
        raise FileNotFoundError(
            f"No rejections file at {rej_path}. "
            f"Run `trinity-local lens-build` to mine rejections from turn pairs first."
        )

    items: list[EvalItem] = []
    by_type: dict[str, int] = {}
    by_basin: dict[str, int] = {}

    with rej_path.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                raw = json.loads(line)
            except json.JSONDecodeError:
                continue
            # Drop entries missing the structural fields we need.
            rej_type = raw.get("type")
            model_quote = (raw.get("model_quote") or "").strip()
            user_sub = (raw.get("user_substitute") or "").strip()
            source_id = raw.get("id") or ""
            prompt_id = raw.get("prompt_id")
            if not (rej_type and model_quote and source_id):
                continue
            prompt_text, provider = _lookup_prompt_text(prompt_id)
            # If the prompt_id no longer resolves (corpus churn between
            # lens-build and eval-build), fall back to user_substitute
            # as a stand-in — at least we keep the rejection-shape
            # signal even when the originating prompt has been garbage-
            # collected. The eval just becomes "given THIS-shaped
            # rejection, can a model avoid it?"
            if not prompt_text:
                prompt_text = user_sub
            items.append(EvalItem(
                eval_item_id=_stable_id("ei", source_id, rej_type),
                prompt=prompt_text,
                rejection_type=rej_type,
                rejected_response=model_quote,
                user_substitute=user_sub,
                rubric_signal=(raw.get("why_signal") or "").strip(),
                basin_id=raw.get("basin"),
                source="rejections",
                source_id=source_id,
                prompt_id=prompt_id,
                provider_of_rejected_response=provider,
            ))
            by_type[rej_type] = by_type.get(rej_type, 0) + 1
            if raw.get("basin"):
                by_basin[raw["basin"]] = by_basin.get(raw["basin"], 0) + 1
            if limit is not None and len(items) >= limit:
                break

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
