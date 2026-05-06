"""Tests for council review HTML rendering."""
from __future__ import annotations

from trinity_local.council_review import (
    render_live_council_page,
    render_unified_council_page,
    write_live_council_page,
)
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

        html = render_unified_council_page(bundle, outcome)

        # Synthesis output is markdown-rendered
        assert "<h1>The Strongest Answer</h1>" in html
        assert "<strong>Gemini</strong>" in html
        # Member output is markdown-rendered
        assert "<h2>Best take</h2>" in html
        assert '<pre class="md-code-block"><code>print(&#x27;hello&#x27;)</code></pre>' in html
        # Page structure
        assert "Back to Launchpad" in html
        assert "Comparative Analysis" in html
        assert "Full Responses" in html

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
        assert "Back to Launchpad" in html
        assert "confirm your preference in the floating bar" not in html
        assert "floating-actions" not in html
        assert "@click=\"chooseAnswer(" in html
        assert "role=\"button\"" in html
        assert "tabindex=\"0\"" in html
        assert "Preferred</span>" in html
        assert "initialSelection" in html
        assert "trinity:council-selection:${pageData.councilId}" not in html
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

    def test_live_council_page_renders_stop_control(self, patch_trinity_home):
        html = render_live_council_page()

        assert "Back to Launchpad" in html
        assert "Stop council" in html
        assert "statusScriptBaseUrl" in html
        assert "window.addEventListener('pageshow'" in html
        assert "back_forward" in html
        assert "base.includes('?') ? `&t=${Date.now()}` : `?t=${Date.now()}`" in html
        assert "formatProviderLabel" in html
        assert "label: analysisLabel" in html
        assert "progressScriptBaseUrl" not in html
        assert "stop_council" in html
        assert "fallbackMembers" in html
        assert "memberOrder: params.fallbackMembers" in html
        assert "Object.keys(memberMap).length ? Object.keys(memberMap) : (this.runState?.memberOrder || [])" in html

        path = write_live_council_page()
        assert path.name == "live_council.html"
        assert path.exists()
