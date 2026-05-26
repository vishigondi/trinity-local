"""Regression: normalizeProviderSlug must be at module scope so the
Vue-reactive formatProviderLabel() can reach it from inside Vue's
proxy evaluator. The first version of this helper lived inside
renderChart(), which made it invisible to formatProviderLabel (defined
at module scope) — every Vue template binding that called
formatProviderLabel(...) threw ReferenceError, spamming the console
27+ times on a normal page load and breaking the suggested-routing
chips + personal_routing_table cells.

The fix is structural: the helper has TWO callers (renderChart palette
lookups + formatProviderLabel display labels) and must live where both
can see it. This test pins that structural choice.
"""
from __future__ import annotations


def test_normalize_provider_slug_defined_at_module_scope():
    from trinity_local.launchpad_template import render_launchpad_html
    html = render_launchpad_html(page_data={}, recent_cards="")
    # Find the definition; there must be exactly one.
    needle = "function normalizeProviderSlug"
    assert html.count(needle) == 1, "duplicate or missing normalizeProviderSlug"

    # Locate its position and the nearest enclosing function above it.
    # If the definition lives inside another function (renderChart, etc.),
    # the helper is unreachable from formatProviderLabel at module scope.
    def_pos = html.index(needle)
    # Walk backwards looking for an enclosing function-block opener that has
    # not yet been closed. We use a simple brace-depth scan of the JS that
    # PRECEDES the definition.
    preface = html[:def_pos]
    # Strip out the HTML before the <script> block — only count braces from
    # the last <script> opener forward.
    script_open = preface.rfind("<script>")
    assert script_open != -1, "no <script> block before normalizeProviderSlug"
    js_before = preface[script_open + len("<script>"):]
    # Brace depth at the start of the definition (after the leading 4-space
    # indent of the function declaration line).
    depth = 0
    for ch in js_before:
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
    # Module scope = depth 0 (no open function above it in the script block).
    assert depth == 0, (
        f"normalizeProviderSlug is at brace-depth {depth} (nested inside another "
        f"function). It must live at module scope so Vue's formatProviderLabel "
        f"can reach it. See the original ReferenceError bug surfaced 2026-05-26."
    )


def test_format_provider_label_can_reach_normalize_provider_slug():
    """Sanity check: formatProviderLabel still calls normalizeProviderSlug,
    and the definition appears BEFORE formatProviderLabel in source order
    (JS function hoisting would technically save us, but defining the
    helper after its caller invites confusion + future regressions)."""
    from trinity_local.launchpad_template import render_launchpad_html
    html = render_launchpad_html(page_data={}, recent_cards="")
    norm_pos = html.index("function normalizeProviderSlug")
    fmt_pos = html.index("function formatProviderLabel")
    assert norm_pos < fmt_pos, (
        "normalizeProviderSlug must be defined before formatProviderLabel"
    )
    # Confirm formatProviderLabel still references it.
    fmt_body = html[fmt_pos:fmt_pos + 1000]
    assert "normalizeProviderSlug(" in fmt_body, (
        "formatProviderLabel should call normalizeProviderSlug to canonicalize "
        "the gemini→antigravity historical alias"
    )
