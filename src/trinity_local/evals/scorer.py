"""Eval scorer. Given a populated EvalRunResult (target_response per
item) + the user's lens.md, ask the chairman: "is the target_response
better than the rejected_response on the {rejection_type} axis?"

The chairman returns a structured judgment per item. Aggregates roll
up by rejection_type so the marketing-legible output is "model X scored
0.73 on YOUR COMPRESSION-prone prompts."

The judge is itself a model call; we deliberately let the caller pick
which provider plays judge (default: the user's chairman provider).
That avoids the obvious bias-trap of "the model being scored grades
itself" — score gemini using claude or codex as the judge, etc.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from ..config import ProviderConfig
from ..providers import make_provider, ProviderResult
from .runner import EvalRunResult


# One-liner per axis, surfaced in user-facing eval output (terminal +
# share card) so a reader knows what each axis measures without
# leaving the output. Long-form rubric below is for the chairman judge.
AXIS_ONELINER = {
    "REFRAME": "user wanted a different frame",
    "COMPRESSION": "user wanted shorter",
    "REDIRECT": "user wanted a different shape (spec vs narrative, etc.)",
    "SHARPENING": "user wanted more precision (numbers, identifiers)",
}


# Per-rejection-type rubric the chairman gets in the judge prompt.
# Each describes WHAT the user wanted that the rejected_response missed,
# so the chairman can grade on the right axis instead of generic quality.
REJECTION_AXIS_RUBRIC = {
    "REFRAME": (
        "The user substituted a different FRAME — the rejected response "
        "answered a different question than the user actually wanted asked. "
        "Score higher if the candidate response notices the user's likely "
        "frame and addresses THAT, not the literal question."
    ),
    "COMPRESSION": (
        "The user wanted SHORTER. The rejected response was a long lecture "
        "or multi-section essay. Score higher if the candidate response is "
        "concise and direct."
    ),
    "REDIRECT": (
        "The user wanted a structurally DIFFERENT output (e.g. spec vs "
        "narrative). The rejected response gave the wrong shape. Score "
        "higher if the candidate response delivers the shape the user "
        "implicitly wanted."
    ),
    "SHARPENING": (
        "The user wanted more PRECISION on the same topic. The rejected "
        "response was vague. Score higher if the candidate response "
        "names specifics (numbers, identifiers, concrete examples)."
    ),
}


JUDGE_PROMPT_TEMPLATE = """You are scoring a candidate model's response against the user's empirical taste.

The user's taste rubric (excerpted from their personal lens):
---
{lens_excerpt}
---

REJECTION AXIS: {rejection_type}
{rubric}

What the user previously got and IMPLICITLY REJECTED:
---
{rejected_response}
---

What the user's NEXT TURN looked like (their implicit correction):
---
{user_substitute}
---

Chairman's annotation of why this was a rejection:
{rubric_signal}

Now grade THIS candidate response to the same prompt:
---
{target_response}
---

Output ONLY a JSON object on a single line. No prose, no markdown fences:
{{"score": <float in [0.0, 1.0]>, "reason": "<one-sentence rationale>"}}

Score 0.0 = the candidate makes the same mistake as the rejected response.
Score 1.0 = the candidate avoids the rejection-axis failure mode entirely AND aligns with what the user actually wanted.
0.5 = neutral / inconclusive.
"""


# Cap the lens excerpt sent to the judge. Full lens.md can be 6-10KB;
# 2000 chars of the most-relevant section is enough for a per-item
# rubric without dominating the judge's context window.
LENS_EXCERPT_BUDGET = 2000


def _lens_excerpt(lens_text: str, budget: int = LENS_EXCERPT_BUDGET) -> str:
    text = (lens_text or "").strip()
    if len(text) <= budget:
        return text
    head = budget // 2
    return f"{text[:head].rstrip()}\n[... excerpted ...]\n{text[-head:].lstrip()}"


def _parse_judge_response(raw: str) -> tuple[float, str]:
    """Extract {score, reason} from the judge's stdout. Falls back to
    a neutral 0.5 if parsing fails — better than crashing the whole
    score run on one judge that returned prose around the JSON."""
    if not raw:
        return 0.5, "judge returned empty output"
    # Strip code fences if the judge wrapped its JSON.
    cleaned = raw.strip()
    cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
    cleaned = re.sub(r"\s*```$", "", cleaned)
    # First try direct JSON parse.
    try:
        parsed = json.loads(cleaned)
        score = float(parsed.get("score", 0.5))
        reason = str(parsed.get("reason", "")).strip()
        return max(0.0, min(1.0, score)), reason
    except (json.JSONDecodeError, ValueError, TypeError):
        pass
    # Fall back: find the first JSON-looking object in the text.
    m = re.search(r"\{[^{}]*\"score\"\s*:\s*([0-9.]+)[^{}]*\}", cleaned)
    if m:
        try:
            score = float(m.group(1))
            return max(0.0, min(1.0, score)), "judge output partially parsed"
        except ValueError:
            pass
    return 0.5, f"judge output unparseable: {cleaned[:200]}"


def score_run(
    run_result: EvalRunResult,
    lens_text: str,
    judge_provider: str,
    provider_configs: dict[str, ProviderConfig],
    *,
    cwd: Path | None = None,
    progress_callback=None,
) -> EvalRunResult:
    """Score each item in the run by asking a judge provider whether
    the target_response is better than the rejected_response on the
    item's rejection axis.

    Mutates `run_result.items[*].score` + `.score_reason` +
    `.judge_provider` in place AND returns the same object for chaining.

    Aggregate score = mean of per-item scores, ignoring skipped items
    (where dispatch failed).

    Raises KeyError if `judge_provider` isn't in `provider_configs`.
    """
    if judge_provider not in provider_configs:
        raise KeyError(
            f"Unknown judge provider '{judge_provider}'. "
            f"Available: {sorted(provider_configs)}"
        )
    config = provider_configs[judge_provider]
    judge = make_provider(config)
    cwd = cwd or Path.cwd()
    lens_excerpt = _lens_excerpt(lens_text)

    scored_count = 0
    score_sum = 0.0
    per_type: dict[str, list[float]] = {}

    for idx, item in enumerate(run_result.items, start=1):
        if item.target_error:
            # Failed dispatch — can't score. Leave score=None.
            continue

        rubric = REJECTION_AXIS_RUBRIC.get(
            item.rejection_type,
            "Score on overall quality and alignment with the user's taste rubric above.",
        )
        prompt = JUDGE_PROMPT_TEMPLATE.format(
            lens_excerpt=lens_excerpt,
            rejection_type=item.rejection_type,
            rubric=rubric,
            rejected_response=(item.rejected_response or "")[:2000],
            user_substitute=(item.user_substitute or "")[:1000],
            rubric_signal=(item.rubric_signal or "(none)")[:500],
            target_response=(item.target_response or "")[:2000],
        )
        try:
            result: ProviderResult = judge.run(prompt, cwd=cwd)
            score, reason = _parse_judge_response(result.stdout)
        except Exception as exc:
            score, reason = 0.5, f"judge dispatch raised: {exc!r}"

        item.score = score
        item.score_reason = reason
        item.judge_provider = judge_provider

        scored_count += 1
        score_sum += score
        per_type.setdefault(item.rejection_type, []).append(score)

        if progress_callback is not None:
            try:
                progress_callback(idx, len(run_result.items), item)
            except Exception:
                pass

    run_result.aggregate_score = (score_sum / scored_count) if scored_count else None
    run_result.by_rejection_type = {
        rtype: {
            "count": len(scores),
            "mean_score": sum(scores) / len(scores) if scores else 0.0,
            "min_score": min(scores) if scores else 0.0,
            "max_score": max(scores) if scores else 0.0,
        }
        for rtype, scores in per_type.items()
    }
    return run_result
