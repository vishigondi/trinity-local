"""launchpad cortex rules: visually demote low-trust rules.

Same noise-vs-signal honesty rule that opacity-demoted low-n axis bars
(commit 0c20656). The cortex rules table renders each rule's trust
score in <strong>, which gave low-trust rules (kNN-fallback band) the
same visual authority as high-trust rules (use-rule band). The fix
opacity-demotes rows where trust_score < trust_use_rule threshold.

Pin shape: rendered HTML carries the conditional opacity binding tied
to the per-rule trust score vs the cortex's use-rule threshold.
"""
from __future__ import annotations


def test_low_trust_cortex_row_carries_opacity_binding():
    """A rule with trust below the use-rule threshold should render
    with a Vue conditional :style binding that compares the per-row
    trust score to the use-rule threshold and applies opacity when
    below."""
    from trinity_local.launchpad_template import render_launchpad_html
    html = render_launchpad_html(
        page_data={
            "cortexRules": {
                "rules": [
                    {
                        "basin_id": "test_basin",
                        "primary": "claude",
                        "challenger": "codex",
                        "trust_score": 0.55,  # in kNN-fallback band
                        "raw_trust_score": 0.55,
                        "trust_band": "kNN fallback",
                        "reason": "test",
                        "n_episodes": 3,
                        "winner_share": 0.6,
                        "audit_status": "unaudited",
                        "evidence": [],
                    },
                ],
                "total_basins": 1,
                "trust_use_rule": 0.7,
                "trust_knn_fallback": 0.55,
            },
        },
        recent_cards="",
    )
    # The binding compares r.trust_score against cortexRules.trust_use_rule.
    # A future refactor would have to keep this contract.
    assert "r.trust_score < cortexRules.trust_use_rule" in html, (
        "Cortex rule row missing the opacity binding for low-trust rules. "
        "Same honesty pattern shipped to the axis-bar surface in 0c20656."
    )
    # Tooltip explains why
    assert "Low-trust rule" in html
    assert "kNN" in html  # the remedy is named


def test_high_trust_cortex_row_keeps_full_opacity():
    """When a rule is above the use-rule threshold, the conditional
    style should resolve to null (no opacity demotion). This is a
    template-shape test; the Vue runtime evaluates the condition."""
    from trinity_local.launchpad_template import render_launchpad_html
    html = render_launchpad_html(
        page_data={
            "cortexRules": {
                "rules": [
                    {
                        "basin_id": "high_trust_basin",
                        "primary": "claude",
                        "challenger": "codex",
                        "trust_score": 0.85,
                        "raw_trust_score": 0.85,
                        "trust_band": "use rule",
                        "reason": "test",
                        "n_episodes": 12,
                        "winner_share": 0.85,
                        "audit_status": "agreed",
                        "evidence": [],
                    },
                ],
                "total_basins": 1,
                "trust_use_rule": 0.7,
                "trust_knn_fallback": 0.55,
            },
        },
        recent_cards="",
    )
    # The conditional binding is present (template doesn't branch on
    # data — Vue evaluates at runtime). Just confirm the structure
    # exists. The actual opacity is applied client-side.
    assert "r.trust_score < cortexRules.trust_use_rule" in html
