"""Regression: when the Chrome extension dispatch fails (no extension
installed in this browser, or native host missing), the launchpad must
ROLL BACK the optimistic Vue state so the user isn't stuck staring at:

  - "Council in Progress" panel showing forever (operation polling a
    status file that will never be written)
  - Launch button disabled (.busy stuck true)
  - Prompt textarea empty (user has to retype)

Surfaced 2026-05-26 during e2e Chrome testing of the launchpad —
exactly the symptom the user reported with launch_mpm0bght_gx1y9v.
The fix is in handleDispatchResult: on dispatch failure, call
clearOperation() + restore this.pendingPrompt → this.prompt.
"""
from __future__ import annotations


def test_handle_dispatch_result_rolls_back_on_install_prompt_tier():
    from trinity_local.launchpad_template import render_launchpad_html
    html = render_launchpad_html(page_data={}, recent_cards="")

    # The handler must check for failure (install-prompt OR extension !ok).
    assert "tier === 'install-prompt'" in html
    # ... AND it must call clearOperation() to drop the optimistic state.
    # The order matters: rollback before banner display.
    handler_start = html.index("handleDispatchResult(result)")
    handler_excerpt = html[handler_start:handler_start + 3000]
    assert "this.clearOperation()" in handler_excerpt, (
        "handleDispatchResult must clearOperation() on failed dispatch "
        "to unstick the busy state — otherwise Launch button stays disabled "
        "and 'Council in Progress' panel polls forever"
    )
    # And restore the prompt the user typed.
    assert "this.pendingPrompt" in handler_excerpt
    assert "this.prompt = this.pendingPrompt" in handler_excerpt


def test_launch_council_snapshots_prompt_before_clearing():
    """The rollback in handleDispatchResult needs the original text — it
    must be snapshotted before launchCouncil clears `this.prompt`."""
    from trinity_local.launchpad_template import render_launchpad_html
    html = render_launchpad_html(page_data={}, recent_cards="")
    launch_start = html.index("launchCouncil()")
    launch_block = html[launch_start:launch_start + 1500]
    snapshot_idx = launch_block.find("this.pendingPrompt = prompt")
    clear_idx = launch_block.find("this.prompt = ''")
    assert snapshot_idx != -1, "launchCouncil must snapshot prompt into pendingPrompt"
    assert clear_idx != -1, "launchCouncil should still clear this.prompt for the optimistic UX"
    assert snapshot_idx < clear_idx, (
        "snapshot must happen BEFORE clear — otherwise pendingPrompt is empty "
        "when the user's text is wiped"
    )


def test_pending_prompt_initialized_in_reactive_state():
    """pendingPrompt must be declared in the reactive data block so the
    handler can read/write it. petite-vue only reacts to keys present
    at app-mount time."""
    from trinity_local.launchpad_template import render_launchpad_html
    html = render_launchpad_html(page_data={}, recent_cards="")
    assert "pendingPrompt: ''" in html, (
        "pendingPrompt must be initialized in the createApp({...}) data block"
    )
