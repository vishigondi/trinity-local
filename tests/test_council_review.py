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
            winner_provider="antigravity",
            member_results=[
                CouncilMemberResult(
                    provider="antigravity",
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
        assert "← Launchpad" in html
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
                CouncilMemberResult(provider="antigravity", model="antigravity", output_text="Gemini answer"),
            ],
            synthesis_output="# Compare\n\nPick the clearest answer.",
            created_at="2026-04-28T12:05:00+00:00",
        )

        html = render_unified_council_page(bundle, outcome)

        assert "Click the answer you prefer." in html
        assert "← Launchpad" in html
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
                CouncilMemberResult(provider="antigravity", model="antigravity", output_text="Gemini answer"),
                CouncilMemberResult(provider="codex", model="codex", output_text="Codex answer"),
            ],
            synthesis_output="# Compare\n\nPick the clearest answer.",
            created_at="2026-04-28T12:05:00+00:00",
        )

        html = render_unified_council_page(bundle, outcome)

        assert 'class="answers-grid answers-grid-three"' in html

    def test_live_council_page_renders_stop_control(self, patch_trinity_home):
        html = render_live_council_page()

        assert "← Launchpad" in html
        assert "Stop council" in html
        assert "statusScriptBaseUrl" in html
        assert "window.addEventListener('pageshow'" in html
        assert "back_forward" in html
        assert "base.includes('?') ? `&t=${Date.now()}` : `?t=${Date.now()}`" in html
        assert "formatProviderLabel" in html
        assert "label: analysisLabel" in html
        assert "progressScriptBaseUrl" not in html
        # Stop button now dispatches via the Chrome extension instead
        # of the retired shortcuts:// path — assert the dispatcher
        # kind ('stop-council' per capture_host.ACTION_ALLOWLIST).
        assert "'stop-council'" in html
        assert "fallbackMembers" in html
        assert "members: params.fallbackMembers" in html
        assert "Object.keys(memberMap).length ? Object.keys(memberMap) : (seg.runState?.memberOrder || [])" in html
        # Threading UX: page renders stacked segments and supports ?thread_id= mode.
        assert "segments: []" in html
        assert "loadThreadScript" in html
        assert "_thread_" in html
        # Refinement directive is surfaced in the eyebrow row for any round
        # that has one. Source: outcome.metadata.user_refinement → rs.metadata.
        # Regression guard for bundle_42f8cea9c9e705e5 ("Stop copy-pasting
        # prompts. Own your context. Forge your core memories.") which had
        # its refinement directive vanish from the rendered thread.
        assert "seg.refinementText" in html
        assert "rs.metadata?.user_refinement" in html
        # Quote-into-refinement affordance (tick #60). Lets the user
        # cherry-pick fragments across member responses and stack them
        # into the refinement input, matching the user's hand-rolled
        # flow on bundle_42f8cea9c9e705e5 (took "Own your context" from
        # Gemini, merged with Claude's response, typed the merged line).
        # The button must have @click.stop so it doesn't trigger the
        # parent article's pick-winner click handler.
        assert "quoteMember(row.provider, row)" in html
        assert "quote-member-btn" in html
        assert "@click.stop=" in html
        # Verify-on-shortcut-fire (tick #71). chooseMember can't trust
        # the dispatch URL succeeded — if the Chrome extension's Native
        # Messaging host isn't wired up, the dispatch goes nowhere, the
        # user_verdict never gets written, and the optimistic "Preferred"
        # badge lies. After 3s, re-load the outcome JSONP and check the
        # verdict actually persisted; if not, switch the badge to "Save
        # failed" with install guidance. This is the root cause behind
        # tick #69's 16% verdict-capture rate. (Pass A: dispatch path
        # migrated from macOS Shortcut to Chrome extension pre-launch;
        # the install hint now points at install-extension, not the
        # retired shortcut-install CLI.)
        assert "verifyPending" in html
        assert "verifyFailed" in html
        assert "Save failed" in html
        assert "install-extension" in html

        path = write_live_council_page()
        assert path.name == "live_council.html"
        assert path.exists()
