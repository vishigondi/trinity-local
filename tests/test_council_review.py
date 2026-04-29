"""Tests for council review HTML rendering."""
from __future__ import annotations

from trinity_local.council_review import render_review_html, render_unified_council_page
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

    def test_unified_page_uses_clickable_cards_for_preference(self):
        bundle = PromptBundle(
            bundle_id="bundle_123",
            task_cluster_id="cluster_123",
            task_text="Why is the sky blue?",
            goal="Choose the strongest answer.",
            comparison_instructions="Prefer the strongest answer for the user.",
            created_at="2026-04-28T12:00:00+00:00",
        )
        outcome = CouncilOutcome(
            council_run_id="council_123",
            bundle_id=bundle.bundle_id,
            task_cluster_id=bundle.task_cluster_id,
            primary_provider="claude",
            member_results=[
                CouncilMemberResult(provider="claude", model="claude", output_text="Claude answer"),
                CouncilMemberResult(provider="gemini", model="gemini", output_text="Gemini answer"),
            ],
            synthesis_output="# Compare\n\nPick the clearest answer.",
            created_at="2026-04-28T12:05:00+00:00",
        )

        html = render_unified_council_page(bundle, outcome)

        assert "Click the answer you prefer." in html
        assert "Back to Launchpad" not in html
        assert "confirm your preference in the floating bar" not in html
        assert "floating-actions" not in html
        assert "@click=\"chooseAnswer(" in html
        assert "role=\"button\"" in html
        assert "tabindex=\"0\"" in html
        assert "Preferred</span>" in html
        assert "trinity:council-selection:${pageData.councilId}" in html
        assert "signal_page" not in html

    def test_unified_page_uses_three_column_layout_for_three_members(self):
        bundle = PromptBundle(
            bundle_id="bundle_123",
            task_cluster_id="cluster_123",
            task_text="Why is the sky blue?",
            goal="Choose the strongest answer.",
            comparison_instructions="Prefer the strongest answer for the user.",
            created_at="2026-04-28T12:00:00+00:00",
        )
        outcome = CouncilOutcome(
            council_run_id="council_123",
            bundle_id=bundle.bundle_id,
            task_cluster_id=bundle.task_cluster_id,
            primary_provider="claude",
            member_results=[
                CouncilMemberResult(provider="claude", model="claude", output_text="Claude answer"),
                CouncilMemberResult(provider="gemini", model="gemini", output_text="Gemini answer"),
                CouncilMemberResult(provider="codex", model="codex", output_text="Codex answer"),
            ],
            synthesis_output="# Compare\n\nPick the clearest answer.",
            created_at="2026-04-28T12:05:00+00:00",
        )

        html = render_unified_council_page(bundle, outcome)

        assert 'class="answers-grid answers-grid-three"' in html
