"""Tests for council review HTML rendering."""
from __future__ import annotations

from trinity_local.council_review import render_review_html
from trinity_local.council_schema import CouncilMemberResult, CouncilOutcome, PromptBundle


class TestCouncilReviewMarkdown:
    def test_renders_markdown_blocks(self):
        bundle = PromptBundle(
            bundle_id="bundle_123",
            task_cluster_id="cluster_123",
            task_text="# Launch task\n\n- compare answers\n- pick a winner",
            goal="## Goal\nChoose the **strongest** answer.",
            comparison_instructions="Prefer answers with `specificity` and [clarity](https://example.com).",
            context_excerpt="```text\nmarket context\n```",
            created_at="2026-04-28T12:00:00+00:00",
        )
        outcome = CouncilOutcome(
            council_run_id="council_123",
            bundle_id=bundle.bundle_id,
            task_cluster_id=bundle.task_cluster_id,
            primary_provider="claude",
            winner_provider="gemini",
            member_results=[
                CouncilMemberResult(
                    provider="gemini",
                    model="gemini-pro",
                    output_text="## Best take\n\n- fast\n- social\n\n```py\nprint('hello')\n```",
                )
            ],
            synthesis_output="# The Strongest Answer\n\nUse the **Gemini** version.",
            synthesis_prompt="## Prompt\n\nReview all council answers.",
            created_at="2026-04-28T12:05:00+00:00",
        )

        html = render_review_html(bundle, outcome)

        assert "Origin: Direct Council" in html
        assert "Session: unknown" not in html
        assert "Origin: unknown" not in html
        assert '<div class="markdown-body"><h1>Launch task</h1>' in html
        assert "<strong>strongest</strong>" in html
        assert "<code>specificity</code>" in html
        assert '<a href="https://example.com">clarity</a>' in html
        assert '<pre class="md-code-block"><code>print(&#x27;hello&#x27;)</code></pre>' in html
        assert "<h1>The Strongest Answer</h1>" in html
