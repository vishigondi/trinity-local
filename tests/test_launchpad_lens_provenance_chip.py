"""launchpad lens card: provenance chip surfaces lens-build vs import source.

Same honesty pattern as the trust-band on cortex rules + n= on axis
bars: name the SOURCE of each claim instead of presenting all lenses
as equally weighted. Lens shapes:

- verdict='accepted' → built via lens-build (local rejection corpus
  distillation). Chip reads 'lens-build', sage color.
- verdict='imported' → came from provider-side loop (lens-prompt →
  paste into provider → lens-import). Chip reads 'via <provider>',
  steel color.

The chip is small/inline (not opacity demotion — different epistemic
status, not low-confidence — but visible so the user knows).
"""
from __future__ import annotations


def _render(paired_lenses):
    from trinity_local.launchpad_template import render_launchpad_html
    return render_launchpad_html(
        page_data={"tasteLenses": {"paired_lenses": paired_lenses}},
        recent_cards="",
    )


def test_accepted_lens_renders_lens_build_chip():
    html = _render([{
        "pole_a": "specificity",
        "pole_b": "abstraction",
        "verdict": "accepted",
        "dual_evidence": {"source_provider": ["lens-build"]},
        "tension_decisions": ["d1", "d2", "d3"],
    }])
    # Vue conditional emits the literal text 'lens-build' for accepted
    assert "lens-build" in html
    # The conditional binding shape exists for a future refactor to keep
    assert "p.verdict === 'accepted'" in html


def test_imported_lens_renders_via_provider_chip():
    html = _render([{
        "pole_a": "generator",
        "pole_b": "generated",
        "verdict": "imported",
        "dual_evidence": {"source_provider": ["claude"]},
        "tension_decisions": ["evidence-1"],
    }])
    # The "via X" pattern is rendered by Vue at runtime, but the binding
    # shape is in the template source. The provenance-naming machinery
    # is the contract.
    assert "via " in html
    assert "p.dual_evidence" in html and "source_provider" in html


def test_chip_carries_explanatory_title_for_each_verdict():
    """Tooltip on hover should explain the provenance — same UX
    pattern as the trust-band tooltip on cortex rules."""
    html = _render([{
        "pole_a": "A", "pole_b": "B",
        "verdict": "accepted",
        "dual_evidence": {"source_provider": ["lens-build"]},
        "tension_decisions": [],
    }])
    # Both branches of the ternary appear in the template — confirms
    # the tooltip path renders for either verdict.
    assert "Built from your local rejection corpus via lens-build" in html
    assert "Imported from a provider" in html
