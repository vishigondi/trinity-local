"""Eval runner. Given an eval set + a target provider, dispatch each
prompt and capture the candidate response. Persists results to
`~/.trinity/evals/results/eval_<eval_id>__model_<provider>__<ts>.json`.

Scoring (was the candidate better than what got rejected?) happens in
the sister `evals/scorer.py` module. Separating them keeps the
expensive dispatch isolated from the chairman-judge call so a partial
run can be re-scored cheaply, and a fresh scorer can re-grade existing
result files without re-dispatching.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from ..config import ProviderConfig
from ..providers import make_provider, ProviderResult, dispatched_model
from .builder import EvalSet, results_dir


@dataclass
class EvalItemRun:
    eval_item_id: str
    rejection_type: str
    prompt: str
    rejected_response: str
    user_substitute: str
    rubric_signal: str
    basin_id: str | None
    target_response: str
    target_error: str | None
    elapsed_seconds: float
    score: float | None = None
    score_reason: str | None = None
    judge_provider: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class EvalRunResult:
    eval_id: str
    target_provider: str
    target_model: str | None
    started_at: str
    completed_at: str
    items_total: int
    items_completed: int
    items_failed: int
    items: list[EvalItemRun] = field(default_factory=list)
    aggregate_score: float | None = None
    by_rejection_type: dict[str, dict[str, float]] = field(default_factory=dict)
    # True when scoring was degenerate (>50% of items hit the empty/unparseable
    # 0.5 default — e.g. a non-LLM judge that returns nothing). aggregate_score
    # is forced to None in that case so a fabricated benchmark never persists.
    scoring_degraded: bool = False

    def to_dict(self) -> dict:
        return {
            "eval_id": self.eval_id,
            "target_provider": self.target_provider,
            "target_model": self.target_model,
            "started_at": self.started_at,
            "completed_at": self.completed_at,
            "items_total": self.items_total,
            "items_completed": self.items_completed,
            "items_failed": self.items_failed,
            "items": [it.to_dict() for it in self.items],
            "aggregate_score": self.aggregate_score,
            "by_rejection_type": self.by_rejection_type,
            "scoring_degraded": self.scoring_degraded,
        }

    def result_path(self) -> Path:
        ts_safe = self.started_at.replace(":", "").replace("-", "")[:15]
        return results_dir() / f"eval_{self.eval_id}__model_{self.target_provider}__{ts_safe}.json"


def run_eval(
    eval_set: EvalSet,
    target_provider: str,
    provider_configs: dict[str, ProviderConfig],
    *,
    limit: int | None = None,
    cwd: Path | None = None,
    progress_callback=None,
) -> EvalRunResult:
    """Dispatch each eval item's prompt to the target provider.

    Returns a populated EvalRunResult with target_response per item.
    The caller is responsible for calling `scorer.score_run` if they
    want graded results.

    Raises KeyError if target_provider isn't in provider_configs.
    """
    if target_provider not in provider_configs:
        raise KeyError(
            f"Unknown provider '{target_provider}'. "
            f"Available: {sorted(provider_configs)}"
        )
    config = provider_configs[target_provider]
    provider = make_provider(config)
    cwd = cwd or Path.cwd()

    items_to_run = eval_set.items[:limit] if limit else eval_set.items
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    runs: list[EvalItemRun] = []
    failed = 0

    for idx, item in enumerate(items_to_run, start=1):
        item_start = time.monotonic()
        try:
            result: ProviderResult = provider.run(item.prompt, cwd=cwd)
            error = None
            if result.returncode != 0:
                error = (
                    f"{target_provider} returned exit {result.returncode}: "
                    f"{(result.stderr or 'no stderr').strip()[:200]}"
                )
                failed += 1
            response_text = result.stdout
            elapsed = result.elapsed_seconds
        except Exception as exc:
            error = f"dispatch raised: {exc!r}"
            response_text = ""
            elapsed = time.monotonic() - item_start
            failed += 1

        item_run = EvalItemRun(
            eval_item_id=item.eval_item_id,
            rejection_type=item.rejection_type,
            prompt=item.prompt,
            rejected_response=item.rejected_response,
            user_substitute=item.user_substitute,
            rubric_signal=item.rubric_signal,
            basin_id=item.basin_id,
            target_response=response_text,
            target_error=error,
            elapsed_seconds=elapsed,
        )
        runs.append(item_run)
        if progress_callback is not None:
            try:
                progress_callback(idx, len(items_to_run), item_run)
            except Exception:
                pass

    completed = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return EvalRunResult(
        eval_id=eval_set.eval_id,
        target_provider=target_provider,
        # recorded == dispatched: for antigravity this reads agy's
        # settings.json (config.model is ignored by the flagless agy CLI),
        # so the eval card attributes the model that actually ran.
        target_model=dispatched_model(config),
        started_at=started,
        completed_at=completed,
        items_total=len(items_to_run),
        items_completed=len(items_to_run) - failed,
        items_failed=failed,
        items=runs,
    )


def save_run_result(run_result: EvalRunResult) -> Path:
    path = run_result.result_path()
    path.write_text(
        json.dumps(run_result.to_dict(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return path


def load_run_result(path: Path) -> EvalRunResult | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    items = []
    for it in raw.get("items", []):
        items.append(EvalItemRun(
            eval_item_id=it.get("eval_item_id", ""),
            rejection_type=it.get("rejection_type", ""),
            prompt=it.get("prompt", ""),
            rejected_response=it.get("rejected_response", ""),
            user_substitute=it.get("user_substitute", ""),
            rubric_signal=it.get("rubric_signal", ""),
            basin_id=it.get("basin_id"),
            target_response=it.get("target_response", ""),
            target_error=it.get("target_error"),
            elapsed_seconds=float(it.get("elapsed_seconds", 0.0)),
            score=it.get("score"),
            score_reason=it.get("score_reason"),
            judge_provider=it.get("judge_provider"),
        ))
    return EvalRunResult(
        eval_id=raw.get("eval_id", ""),
        target_provider=raw.get("target_provider", ""),
        target_model=raw.get("target_model"),
        started_at=raw.get("started_at", ""),
        completed_at=raw.get("completed_at", ""),
        items_total=int(raw.get("items_total", 0)),
        items_completed=int(raw.get("items_completed", 0)),
        items_failed=int(raw.get("items_failed", 0)),
        items=items,
        aggregate_score=raw.get("aggregate_score"),
        by_rejection_type=raw.get("by_rejection_type", {}),
    )
