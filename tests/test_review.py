"""Tests for post-hoc review module."""
from __future__ import annotations

from trinity_local.review import (
    _parse_review_response,
    build_review_prompt,
    render_review_html,
    ReviewResult,
)


class TestParseReviewResponse:
    def test_full_response(self):
        text = """
VERDICT: The output is correct but could be improved.

ISSUES:
- Missing error handling for edge case X
- The return type annotation is wrong

SUGGESTIONS:
- Add try/except around the network call
- Use Optional[str] instead of str | None for Python 3.9 compat
"""
        verdict, issues, suggestions = _parse_review_response(text)
        assert verdict == "The output is correct but could be improved."
        assert len(issues) == 2
        assert "Missing error handling" in issues[0]
        assert len(suggestions) == 2

    def test_no_issues(self):
        text = """
VERDICT: Excellent output.

ISSUES:
- No issues found.

SUGGESTIONS:
- No suggestions.
"""
        verdict, issues, suggestions = _parse_review_response(text)
        assert verdict == "Excellent output."
        assert issues == []
        assert suggestions == []

    def test_empty_response(self):
        verdict, issues, suggestions = _parse_review_response("")
        assert verdict == ""
        assert issues == []
        assert suggestions == []

    def test_partial_response(self):
        text = "VERDICT: Looks good overall."
        verdict, issues, suggestions = _parse_review_response(text)
        assert verdict == "Looks good overall."
        assert issues == []
        assert suggestions == []


class TestBuildReviewPrompt:
    def test_includes_task_and_output(self):
        prompt = build_review_prompt("Fix the auth bug", "Here is the fix...")
        assert "Fix the auth bug" in prompt
        assert "Here is the fix..." in prompt
        assert "VERDICT" in prompt

    def test_truncates_long_text(self):
        long_task = "x" * 5000
        prompt = build_review_prompt(long_task, "output")
        assert len(prompt) < 15000


class TestRenderReviewHtml:
    def test_renders_html(self, tmp_path, monkeypatch):
        monkeypatch.setattr("trinity_local.review.review_pages_dir", lambda: tmp_path)
        review = ReviewResult(
            review_id="test-review-001",
            task_id="task-001",
            original_provider="claude",
            reviewer_provider="gemini",
            verdict="Correct with minor issues",
            issues=["Missing null check"],
            suggestions=["Add input validation"],
            reviewed_at="2026-04-27T10:00:00+00:00",
        )
        path = render_review_html(review)
        assert path.exists()
        html = path.read_text()
        assert "Post-Hoc Review" in html
        assert "gemini" in html
        assert "Missing null check" in html
        assert "Add input validation" in html
