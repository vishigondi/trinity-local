"""personal_routing.aggregate_routing_table: MIN_BEST_SAMPLES sample guard.

Live trigger 2026-05-25: of 246 task_types in the user's routing table,
89% (219) had their winner declared from n=1 council. That's noise, not
signal — same anti-pattern the per-axis leader suppression fixed at the
display layer. This pins the data-layer guard: best_per_task_type only
includes task_types with ≥3 councils, the raw by_task_type / wins
data stays complete (chairman_picker reads those directly via
sigmoid blend, doesn't need best).
"""
from __future__ import annotations


def _council(task_type: str, winner: str) -> dict:
    """One synthetic council record in the shape aggregate_routing_table reads."""
    return {
        "task_type": task_type,
        "routing_label": {
            "task_type": task_type,
            "winner": winner,
            "provider_scores": {
                # Both providers see scores so by_task_type has data
                "claude": {"overall": 7.5},
                "codex": {"overall": 7.0},
            },
        },
    }


class TestMinSampleSuppression:
    def test_single_council_winner_excluded_from_best(self):
        from trinity_local.personal_routing import aggregate_routing_table
        # One council for "rare_task" → noise, should not declare winner
        result = aggregate_routing_table([_council("rare_task", "claude")])
        assert "rare_task" in result["by_task_type"], "raw data preserved"
        assert "rare_task" in result["wins_per_task_type"], "wins preserved"
        assert "rare_task" not in result["best_per_task_type"], (
            "best_per_task_type must not declare a winner from n=1 council"
        )

    def test_two_councils_winner_excluded(self):
        from trinity_local.personal_routing import aggregate_routing_table
        result = aggregate_routing_table([
            _council("nearly_rare", "claude"),
            _council("nearly_rare", "claude"),
        ])
        # n=2 still below MIN_BEST_SAMPLES=3
        assert "nearly_rare" not in result["best_per_task_type"]

    def test_three_councils_winner_included(self):
        from trinity_local.personal_routing import aggregate_routing_table
        result = aggregate_routing_table([
            _council("at_threshold", "claude"),
            _council("at_threshold", "claude"),
            _council("at_threshold", "claude"),
        ])
        # n=3 hits MIN_BEST_SAMPLES floor
        assert "at_threshold" in result["best_per_task_type"]
        assert result["best_per_task_type"]["at_threshold"] == "claude"

    def test_raw_data_preserved_even_for_excluded(self):
        """The chairman_picker sigmoid-blends from by_task_type/wins
        directly; it never reads best_per_task_type for routing. So
        the raw data must stay complete even when best omits."""
        from trinity_local.personal_routing import aggregate_routing_table
        result = aggregate_routing_table([
            _council("rare_a", "claude"),
            _council("rare_b", "codex"),
            _council("rare_c", "claude"),
        ])
        # 3 distinct task_types each with n=1 → best_per_task_type is empty
        assert len(result["best_per_task_type"]) == 0
        # But raw data has all 3
        assert len(result["by_task_type"]) == 3
        assert len(result["wins_per_task_type"]) == 3
        # Sample counts visible per provider
        assert result["by_task_type"]["rare_a"]["claude"]["n"] == 1

    def test_high_confidence_task_types_survive(self):
        """Confidence threshold is per-task_type, not global. A run with
        a mix of low-n and high-n task_types should pass through the
        high-n ones."""
        from trinity_local.personal_routing import aggregate_routing_table
        result = aggregate_routing_table([
            _council("low_n_kind", "claude"),  # n=1
            # high_n_kind seen 4 times → above threshold
            _council("high_n_kind", "claude"),
            _council("high_n_kind", "claude"),
            _council("high_n_kind", "codex"),
            _council("high_n_kind", "claude"),
        ])
        assert "low_n_kind" not in result["best_per_task_type"]
        assert "high_n_kind" in result["best_per_task_type"]
        # claude wins (3 of 4 councils)
        assert result["best_per_task_type"]["high_n_kind"] == "claude"

    def test_council_count_uses_winner_field_first(self):
        """The sample-count gate uses the wins dict when present (chairman
        winner field). This is the canonical signal — fall back to
        provider_summary.n only when winner is missing."""
        from trinity_local.personal_routing import aggregate_routing_table
        # Two councils that lack the winner field but have provider_scores
        # → both providers get n=1 in provider_summary; falls back to
        # summing provider counts.
        no_winner_councils = [
            {"task_type": "no_winner_kind",
             "routing_label": {
                 "task_type": "no_winner_kind",
                 "provider_scores": {
                     "claude": {"overall": 7.0},
                     "codex": {"overall": 6.0},
                 },
             }},
        ] * 3  # 3 copies = 3 councils
        result = aggregate_routing_table(no_winner_councils)
        # total_n = 3 (claude) + 3 (codex) = 6 across providers → ≥3
        assert "no_winner_kind" in result["best_per_task_type"]
