"""Regression: live council page must surface a clear "council never
started" message when the status_token URL has no backing status file
after sustained polling.

User-reported symptom (2026-05-26, launch_mpm0bght_gx1y9v): clicked
Launch from the launchpad, dispatcher silently failed because the
Chrome extension wasn't installed in that browser. The launchpad
fix (aeba2cd) prevents construction of these URLs going forward,
but stale tabs / bookmarks / shared links can still land users on
a status_token URL whose status file was never written. Before
this fix, the page polled the missing file every 1.5s indefinitely,
showing "Council running / Generating witty dialog..." with no
indication that nothing was actually happening.

After this fix, MAX_MISSING_POLLS (=8 ~= 12s @ 1.5s/poll) consecutive
404s flips the segment to failed=true with a self-explanatory message
referencing install-extension.
"""
from __future__ import annotations

from pathlib import Path


def _src():
    return (Path(__file__).resolve().parent.parent
            / "src" / "trinity_local" / "council_review.py").read_text()


def test_missing_status_poll_counter_exists():
    src = _src()
    assert "missingPollCount" in src
    assert "MAX_MISSING_POLLS" in src
    # MAX must be reachable in a reasonable timeframe; 8 polls @ 1.5s = 12s.
    # That's long enough for a slow first launch but short enough to give
    # the user feedback before they walk away frustrated.
    assert "MAX_MISSING_POLLS = 8" in src, "stuck-timeout count drifted"


def test_missing_status_resets_counter_on_success():
    """If status file shows up mid-poll-stream, the counter must reset —
    otherwise a slow-starting council that takes 13s to write its first
    status frame would be incorrectly declared dead."""
    src = _src()
    # The reset comment + assignment must both exist
    assert "missingPollCount = 0" in src
    assert "Reset the missing-poll counter" in src


def test_missing_status_patches_segment_failed_with_install_hint():
    """When the threshold is hit, the segment is patched to failed=true
    with an errorText that names install-extension as the most likely
    cause — that's the specific cause that produced the user-reported
    stuck token."""
    src = _src()
    assert 'failed: true' in src
    assert "This council never started" in src
    # The error message must mention install-extension since that's
    # the most common cause (Chrome extension not installed).
    assert "install-extension" in src


def test_polling_stops_after_threshold():
    """Don't keep polling after we've declared failure — clearPolling()
    must run inside the threshold branch."""
    src = _src()
    # Locate the MAX_MISSING_POLLS branch and confirm clearPolling fires.
    threshold_idx = src.find("missingPollCount >= MAX_MISSING_POLLS")
    assert threshold_idx != -1
    branch_excerpt = src[threshold_idx:threshold_idx + 400]
    assert "this.clearPolling()" in branch_excerpt, (
        "must stop polling once we've declared the council dead"
    )
