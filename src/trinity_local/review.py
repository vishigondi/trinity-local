"""Post-hoc review: ask one provider to critique another's completed output.

This is the "Council-lite" described in the product spec — a single API call
that asks a reviewer provider to evaluate an existing task output for
correctness, missed edge cases, and improvement opportunities.
"""
from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .config import ProviderConfig, trinity_home
from .providers import ProviderResult, make_provider
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
            task_kinds=set(),
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


def _reviews_dir() -> Path:
    path = trinity_home() / "reviews"
    path.mkdir(parents=True, exist_ok=True)
    return path


def save_review(review: ReviewResult) -> Path:
    """Save a review result as a JSON file."""
    path = _reviews_dir() / f"{review.review_id}.json"
    path.write_text(json.dumps(review.to_dict(), indent=2), encoding="utf-8")
    return path


def load_review(review_id: str) -> ReviewResult | None:
    """Load a review result by ID."""
    path = _reviews_dir() / f"{review_id}.json"
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    return ReviewResult(
        review_id=raw.get("review_id", ""),
        task_id=raw.get("task_id", ""),
        original_provider=raw.get("original_provider", ""),
        reviewer_provider=raw.get("reviewer_provider", ""),
        reviewer_model=raw.get("reviewer_model"),
        verdict=raw.get("verdict"),
        issues=raw.get("issues", []),
        suggestions=raw.get("suggestions", []),
        raw_text=raw.get("raw_text", ""),
        cost_estimate_usd=raw.get("cost_estimate_usd", 0.0),
        elapsed_seconds=raw.get("elapsed_seconds", 0.0),
        reviewed_at=raw.get("reviewed_at", ""),
    )


def render_review_html(review: ReviewResult) -> Path:
    """Render a review result as static HTML."""
    parts: list[str] = []
    parts.append("<!DOCTYPE html>")
    parts.append('<html lang="en"><head>')
    parts.append('<meta charset="utf-8">')
    parts.append('<meta name="viewport" content="width=device-width, initial-scale=1">')
    parts.append(f"<title>Review: {review.task_id[:20]}</title>")
    parts.append("<style>")
    parts.append("""
        :root { --bg: #0d1117; --card: #161b22; --text: #c9d1d9; --accent: #58a6ff;
                --green: #3fb950; --red: #f85149; --yellow: #d29922; --border: #30363d; }
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
               background: var(--bg); color: var(--text); padding: 2rem; max-width: 800px; margin: 0 auto; }
        h1 { color: var(--accent); margin-bottom: 0.5rem; }
        .meta { color: #8b949e; margin-bottom: 1.5rem; }
        .verdict { background: var(--card); border: 1px solid var(--border); border-radius: 6px;
                   padding: 1rem; margin-bottom: 1rem; font-size: 1.1rem; }
        .section { margin-bottom: 1.5rem; }
        .section h2 { color: var(--accent); margin-bottom: 0.5rem; font-size: 1rem; text-transform: uppercase; letter-spacing: 0.05em; }
        .issue { background: #f8514922; border-left: 3px solid var(--red); padding: 0.5rem 1rem; margin-bottom: 0.3rem; border-radius: 0 4px 4px 0; }
        .suggestion { background: #3fb95022; border-left: 3px solid var(--green); padding: 0.5rem 1rem; margin-bottom: 0.3rem; border-radius: 0 4px 4px 0; }
        .none { color: #8b949e; font-style: italic; }
    """)
    parts.append("</style></head><body>")
    parts.append("<h1>🔍 Post-Hoc Review</h1>")
    parts.append(f'<p class="meta">{review.reviewer_provider} reviewing {review.original_provider} · {review.reviewed_at}</p>')

    parts.append(f'<div class="verdict">{review.verdict or "No verdict"}</div>')

    parts.append('<div class="section"><h2>Issues</h2>')
    if review.issues:
        for issue in review.issues:
            parts.append(f'<div class="issue">{issue}</div>')
    else:
        parts.append('<div class="none">No issues found.</div>')
    parts.append('</div>')

    parts.append('<div class="section"><h2>Suggestions</h2>')
    if review.suggestions:
        for suggestion in review.suggestions:
            parts.append(f'<div class="suggestion">{suggestion}</div>')
    else:
        parts.append('<div class="none">No suggestions.</div>')
    parts.append('</div>')

    parts.append(f'<p class="meta">Elapsed: {review.elapsed_seconds:.1f}s</p>')
    parts.append("</body></html>")

    html = "\n".join(parts)
    reviews_html_dir = trinity_home() / "review_pages"
    reviews_html_dir.mkdir(parents=True, exist_ok=True)
    out_path = reviews_html_dir / f"{review.review_id}.html"
    out_path.write_text(html, encoding="utf-8")
    return out_path
