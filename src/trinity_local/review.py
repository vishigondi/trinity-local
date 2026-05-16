"""Post-hoc review: ask one provider to critique another's completed output.

This is the "Council-lite" described in the product spec — a single API call
that asks a reviewer provider to evaluate an existing task output for
correctness, missed edge cases, and improvement opportunities.
"""
from __future__ import annotations

import html
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .config import ProviderConfig
from .design_system import render_html_footer, render_html_head
from .providers import ProviderResult, make_provider
from .state_paths import review_pages_dir, reviews_dir
from .utils import now_iso, stable_id


@dataclass
class ReviewResult:
    """Result of a post-hoc review."""
    review_id: str
    task_id: str
    original_provider: str
    reviewer_provider: str
    reviewer_model: str | None = None
    verdict: str | None = None
    issues: list[str] = field(default_factory=list)
    suggestions: list[str] = field(default_factory=list)
    raw_text: str = ""
    cost_estimate_usd: float = 0.0
    elapsed_seconds: float = 0.0
    reviewed_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v not in (None, "", 0, 0.0, {}, [])}


_REVIEW_PROMPT_TEMPLATE = """\
You are reviewing the output of another AI coding assistant. Your job is to \
provide an honest, constructive critique.

## Original Task
{task_text}

## Output Being Reviewed
{output_text}

## Review Instructions
1. **Verdict**: Is this output correct, partially correct, or incorrect? One sentence.
2. **Issues**: List specific problems, bugs, missed edge cases, or incorrect claims. If none, say "No issues found."
3. **Suggestions**: List concrete improvements. If the output is excellent, say "No suggestions."

Format your response as:

VERDICT: <your verdict>

ISSUES:
- <issue 1>
- <issue 2>

SUGGESTIONS:
- <suggestion 1>
- <suggestion 2>
"""


def _parse_review_response(text: str) -> tuple[str, list[str], list[str]]:
    """Extract verdict, issues, and suggestions from reviewer response."""
    verdict = ""
    issues: list[str] = []
    suggestions: list[str] = []
    section = None

    for line in text.splitlines():
        stripped = line.strip()
        upper = stripped.upper()
        if upper.startswith("VERDICT:"):
            verdict = stripped[len("VERDICT:"):].strip()
            section = None
        elif upper.startswith("ISSUES:"):
            section = "issues"
        elif upper.startswith("SUGGESTIONS:"):
            section = "suggestions"
        elif stripped.startswith("- ") or stripped.startswith("* "):
            item = stripped[2:].strip()
            if not item:
                continue
            lowered = item.lower()
            if lowered in ("none", "no issues found.", "no suggestions.", "n/a"):
                continue
            if section == "issues":
                issues.append(item)
            elif section == "suggestions":
                suggestions.append(item)

    return verdict, issues, suggestions


def build_review_prompt(task_text: str, output_text: str) -> str:
    """Build the review prompt from task text and output text."""
    return _REVIEW_PROMPT_TEMPLATE.format(
        task_text=task_text[:4000],
        output_text=output_text[:8000],
    )


def run_review(
    *,
    task_id: str,
    task_text: str,
    output_text: str,
    original_provider: str,
    reviewer_provider: str,
    reviewer_command: list[str],
    cwd: str = ".",
) -> ReviewResult:
    """Run a post-hoc review using a real provider subprocess.

    This calls the reviewer provider's CLI with the review prompt.
    """
    review_id = stable_id("review", task_id, reviewer_provider)
    prompt = build_review_prompt(task_text, output_text)

    provider = make_provider(
        ProviderConfig(
            name=reviewer_provider,
            type="cli",
            enabled=True,
            label=reviewer_provider.title(),
            command=reviewer_command,
            args=[],
            roles=set(),
            task_types=set(),
            model=None,
        )
    )

    start = time.monotonic()
    result: ProviderResult = provider.run(prompt, cwd=Path(cwd).expanduser().resolve())
    elapsed = time.monotonic() - start

    raw_text = result.stdout or result.stderr or ""
    verdict, issues, suggestions = _parse_review_response(raw_text)

    return ReviewResult(
        review_id=review_id,
        task_id=task_id,
        original_provider=original_provider,
        reviewer_provider=reviewer_provider,
        verdict=verdict,
        issues=issues,
        suggestions=suggestions,
        raw_text=raw_text,
        elapsed_seconds=round(elapsed, 2),
        reviewed_at=now_iso(),
    )


def save_review(review: ReviewResult) -> Path:
    """Save a review result as a JSON file."""
    from .utils import atomic_write_text
    path = reviews_dir() / f"{review.review_id}.json"
    atomic_write_text(path, json.dumps(review.to_dict(), indent=2))
    return path


def render_review_html(review: ReviewResult) -> Path:
    """Render a review result as static HTML."""
    head = render_html_head(f"Trinity — Review: {review.task_id[:20]}")
    footer = render_html_footer()

    issues_html = ""
    if review.issues:
        issues_html = "\n".join(
            f'<div class="alert-box danger">{html.escape(issue)}</div>'
            for issue in review.issues
        )
    else:
        issues_html = '<p class="text-muted">No issues found.</p>'

    suggestions_html = ""
    if review.suggestions:
        suggestions_html = "\n".join(
            f'<div class="alert-box success">{html.escape(suggestion)}</div>'
            for suggestion in review.suggestions
        )
    else:
        suggestions_html = '<p class="text-muted">No suggestions.</p>'

    page = f"""{head}
  <style>
    .verdict-box {{
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 16px;
      margin-bottom: 24px;
      font-size: 16px;
      line-height: 1.5;
    }}
  </style>
  <main>
    <section class="card">
      <div class="eyebrow">Review</div>
      <h1>Post-Hoc Review</h1>
      <p class="meta">{review.reviewer_provider} reviewing {review.original_provider} · {review.reviewed_at}</p>
    </section>

    <section class="card">
      <h2>Verdict</h2>
      <div class="verdict-box">{html.escape(review.verdict) if review.verdict else "No verdict"}</div>
    </section>

    <section class="card">
      <h2>Issues</h2>
      {issues_html}
    </section>

    <section class="card">
      <h2>Suggestions</h2>
      {suggestions_html}
    </section>

    <section class="card" style="margin-bottom:32px;">
      <p class="meta">Elapsed: {review.elapsed_seconds:.1f}s</p>
    </section>
  </main>
{footer}
"""

    out_path = review_pages_dir() / f"{review.review_id}.html"
    out_path.write_text(page, encoding="utf-8")
    return out_path
