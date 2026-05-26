"""Regression: clicking Refine / Continue / Auto-chain on the council
review page must NOT silently swallow dispatch failures.

Before this fix, the flow was:
  1. Click Refine → chainBusy=true, chainStatusHeading shown
  2. dispatcher.dispatch (async, no await)
  3. New segment optimistically appended to thread
  4. setTimeout(800) → chainBusy=false → status panel hidden
  5. async onResult fires: chainBusy=false (no-op), chainStatusDetail=error
  6. But chainStatusDetail is rendered INSIDE v-if="chainBusy" — hidden
  7. User sees: nothing. No banner, no error, no new segment (rolled back).

Symptom is the live-council-page sibling of the launchpad stuck-launch
bug. Two-fold fix:
  - chainError (separate state) renders OUTSIDE the chainBusy guard
  - on dispatch failure: roll back optimistic segment + restore prompt
"""
from __future__ import annotations


def _render_single():
    # The Vue scaffold for both single-council and thread pages is generated
    # by the same source module — just read it directly. Both templates +
    # both <script> blocks live in this one file.
    from pathlib import Path
    src = Path(__file__).resolve().parent.parent / "src" / "trinity_local" / "council_review.py"
    return src.read_text()


def test_chain_error_data_field_initialized():
    src = _render_single()
    # There are TWO Vue apps in this file (single-council + thread); both
    # need the chainError data field. Same pattern as launchpad pendingPrompt.
    assert src.count("chainError: ''") == 2, (
        "Expected chainError init in both Vue apps (single-council + thread)"
    )
    assert "_pendingChainSegmentToken: ''" in src, (
        "Thread app needs _pendingChainSegmentToken for segment rollback"
    )


def test_chain_error_banner_renders_outside_chainBusy_guard():
    src = _render_single()
    # Find the chainError banner. Must use v-if="chainError" (not nested
    # inside chainBusy v-if).
    assert src.count('v-if="chainError"') >= 2, (
        "Expected the chainError banner template in both Vue apps"
    )
    # The banner has a Dismiss link to clear chainError manually.
    assert "chainError = ''" in src, "Banner needs a dismiss handler"


def test_dispatch_failure_sets_chainError_not_chainStatusDetail():
    """Both onResult failure paths must write to chainError, since
    chainStatusDetail is only visible while chainBusy=true.

    The failure-fallback string appears in three places:
      - 2x JS handlers (onResult bodies — must assign this.chainError)
      - 1x template banner text inside <strong> (literal HTML, not JS)
    Filter on lines that look like JS assignments to validate.
    """
    src = _render_single()
    fail_msg = "Refine could not dispatch"
    js_assign_count = 0
    for line_idx, line in enumerate(src.split("\n")):
        if fail_msg not in line:
            continue
        # Skip template-literal HTML lines (they contain <strong> etc.).
        if "<strong" in line or "</strong>" in line:
            continue
        context = "\n".join(src.split("\n")[max(0, line_idx - 5):line_idx + 2])
        if "this.chainError" in context:
            js_assign_count += 1
    assert js_assign_count >= 2, (
        f"Expected 'Refine could not dispatch' fallback to set this.chainError "
        f"in both Vue app onResult handlers; found {js_assign_count}"
    )


def test_thread_segment_rollback_on_dispatch_failure():
    """The thread page appends a new segment optimistically. When dispatch
    fails, that segment must be removed so polling doesn't hammer a
    non-existent status file + the thread visual stays accurate."""
    src = _render_single()
    assert "_pendingChainSegmentToken" in src
    # The thread onResult failure path uses this token to find + splice the segment.
    assert "findIndex((s) => s.statusToken === this._pendingChainSegmentToken)" in src
    assert "this.segments.splice(idx, 1)" in src


def test_refine_prompt_restored_on_dispatch_failure():
    """User shouldn't have to retype the refinement prompt after a
    dispatch failure — restore it so they can edit + retry."""
    src = _render_single()
    # The thread version receives refinementText and restores it.
    assert "if (refinementText) this.refinePrompt = refinementText" in src
