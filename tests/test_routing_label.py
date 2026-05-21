"""Tests for Chairman Routing JSON parsing and persistence (§8.7).

Each valid routing label is one training example for the Phase 9 controller.
Parse-success rate matters more than schema purity — be lenient on field
shape, strict on field presence.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from trinity_local.council_runtime import (
    parse_routing_label,
    render_primary_council_prompt,
    create_council_outcome,
    save_council_outcome,
    load_council_outcome,
)
from trinity_local.council_schema import (
    CouncilMemberResult,
    CouncilRoutingLabel,
    PromptBundle,
)


VALID_ROUTING_JSON = """\
```routing-json
{
  "winner": "claude",
  "runner_up": "antigravity",
  "confidence": "high",
  "task_type": "code_refactor",
  "task_domain": "python",
  "user_likely_values": ["correctness", "concision"],
  "provider_scores": {
    "claude": {"overall": 8, "planning": 8, "execution": 9, "evaluation": 7, "specificity": 8, "user_fit": 8, "risk": 2, "conciseness": 7},
    "antigravity": {"overall": 6, "planning": 7, "execution": 5, "evaluation": 6, "specificity": 6, "user_fit": 6, "risk": 3, "conciseness": 8}
  },
  "major_failure_mode": null,
  "routing_lesson": "For code_refactor tasks, prefer claude because it executes more reliably.",
  "eval_seed": "A future answer should pass: type hints preserved on every modified function."
}
```
"""


@pytest.fixture
def bundle() -> PromptBundle:
    return PromptBundle(
        bundle_id="b1",
        task_cluster_id="tc1",
        task_text="Refactor a Python module to remove duplication.",
        goal="Cleanest result",
        created_at="2026-05-01T00:00:00Z",
    )


@pytest.fixture
def members() -> list[CouncilMemberResult]:
    return [
        CouncilMemberResult(provider="claude", model="claude-sonnet-4-6", output_text="Use a helper function..."),
        CouncilMemberResult(provider="antigravity", model="gemini-2.5", output_text="Extract a base class..."),
    ]


# ---------------------------------------------------------------------------
# Prompt contract
# ---------------------------------------------------------------------------

class TestPromptContract:
    def test_prompt_includes_routing_json_contract(self, bundle: PromptBundle, members):
        prompt = render_primary_council_prompt(bundle, members)
        assert "routing-json" in prompt
        # Required fields are surfaced in the contract
        for field_name in ["winner", "confidence", "task_type", "routing_lesson", "eval_seed"]:
            assert field_name in prompt, f"missing {field_name} in prompt"
        assert "PART 1" in prompt
        assert "PART 2" in prompt


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------

class TestParseRoutingLabel:
    def test_valid_json_in_fence_parses(self):
        synthesis = "## Winner\n- Claude wins\n\n" + VALID_ROUTING_JSON
        label, error = parse_routing_label(synthesis)
        assert error is None
        assert label is not None
        assert label.winner == "claude"
        assert label.runner_up == "antigravity"
        assert label.confidence == "high"
        assert label.task_type == "code_refactor"
        assert label.task_domain == "python"
        assert "correctness" in label.user_likely_values
        assert label.provider_scores["claude"]["overall"] == 8.0
        assert label.routing_lesson.startswith("For code_refactor")
        assert label.eval_seed.startswith("A future answer should pass")

    def test_no_synthesis_returns_error(self):
        label, error = parse_routing_label(None)
        assert label is None
        assert error == "no_synthesis"

    def test_no_block_in_text_returns_error(self):
        label, error = parse_routing_label("just a memo with no JSON anywhere")
        assert label is None
        assert error == "no_routing_json_block"

    def test_malformed_json_returns_error(self):
        synthesis = """```routing-json
{ "winner": "claude", "confidence": "high",
```"""
        label, error = parse_routing_label(synthesis)
        assert label is None
        assert error and error.startswith("json_parse_failed")

    def test_missing_winner_returns_error(self):
        synthesis = """```routing-json
{"confidence": "high", "task_type": "x"}
```"""
        label, error = parse_routing_label(synthesis)
        assert label is None
        assert error == "missing_winner"

    def test_bare_json_object_fallback(self):
        # No fence — chairman emitted JSON outside a code block
        synthesis = """The winner is claude.

{"winner": "claude", "confidence": "medium", "task_type": "general"}

That's the call."""
        label, error = parse_routing_label(synthesis)
        assert error is None
        assert label is not None
        assert label.winner == "claude"

    def test_provider_scores_coerce_strings_to_floats(self):
        synthesis = """```routing-json
{"winner": "claude", "confidence": "medium",
 "provider_scores": {"claude": {"overall": "8.5"}}}
```"""
        label, error = parse_routing_label(synthesis)
        assert error is None
        assert label is not None
        assert label.provider_scores["claude"]["overall"] == 8.5

    def test_garbage_provider_scores_dropped_not_failed(self):
        synthesis = """```routing-json
{"winner": "claude", "confidence": "medium",
 "provider_scores": {"claude": "not a dict", "antigravity": {"overall": 5}}}
```"""
        label, error = parse_routing_label(synthesis)
        assert error is None
        assert label is not None
        assert "claude" not in label.provider_scores
        assert label.provider_scores["antigravity"]["overall"] == 5.0

    def test_alt_fence_label(self):
        # Tolerate "routing_json" or "routing json" variants
        for fence_label in ("routing_json", "routing json", "ROUTING-JSON"):
            synthesis = f"```{fence_label}\n{{\"winner\": \"x\", \"confidence\": \"low\"}}\n```"
            label, error = parse_routing_label(synthesis)
            assert error is None, f"fence variant {fence_label!r} failed: {error}"
            assert label is not None
            assert label.winner == "x"


# ---------------------------------------------------------------------------
# Persistence roundtrip
# ---------------------------------------------------------------------------

class TestRoutingLabelRoundtrip:
    def test_label_serializes_and_deserializes(self, patch_trinity_home: Path, bundle, members):
        label, error = parse_routing_label(VALID_ROUTING_JSON)
        assert label is not None and error is None

        outcome = create_council_outcome(
            bundle=bundle,
            primary_provider="claude",
            member_results=members,
            primary_model="claude-sonnet-4-6",
            routing_label=label,
        )
        path = save_council_outcome(outcome)
        assert path.exists()

        # Roundtrip
        loaded = load_council_outcome(outcome.council_run_id)
        assert loaded.routing_label is not None
        assert loaded.routing_label.winner == "claude"
        assert loaded.routing_label.routing_lesson == label.routing_lesson
        assert loaded.routing_label.provider_scores["claude"]["overall"] == 8.0

        # And the JSON-on-disk has the routing_label key
        on_disk = json.loads(path.read_text())
        assert "routing_label" in on_disk
        assert on_disk["routing_label"]["winner"] == "claude"

    def test_outcome_without_label_omits_field(self, patch_trinity_home: Path, bundle, members):
        outcome = create_council_outcome(
            bundle=bundle,
            primary_provider="claude",
            member_results=members,
            primary_model="claude-sonnet-4-6",
        )
        path = save_council_outcome(outcome)
        on_disk = json.loads(path.read_text())
        assert "routing_label" not in on_disk

    def test_old_outcome_without_label_still_loads(self, patch_trinity_home: Path):
        """Forward compat: outcomes saved before §8.7 must still deserialize."""
        from trinity_local.state_paths import council_outcomes_dir
        legacy_dict = {
            "council_run_id": "legacy-1",
            "bundle_id": "b1",
            "task_cluster_id": "tc1",
            "primary_provider": "claude",
            "member_results": [],
            "peer_reviews": [],
            "created_at": "2026-04-01T00:00:00Z",
            # No routing_label
        }
        path = council_outcomes_dir() / "legacy-1.json"
        path.write_text(json.dumps(legacy_dict))
        loaded = load_council_outcome("legacy-1")
        assert loaded.routing_label is None
        assert loaded.primary_provider == "claude"


# ---------------------------------------------------------------------------
# Schema serialization (CouncilRoutingLabel.to_dict drops empty fields)
# ---------------------------------------------------------------------------

class TestSchemaSerialization:
    def test_minimal_label_serializes(self):
        label = CouncilRoutingLabel(winner="claude")
        d = label.to_dict()
        assert d == {"winner": "claude", "confidence": "medium"}

    def test_full_label_roundtrips_through_from_dict(self):
        original = CouncilRoutingLabel(
            winner="claude",
            confidence="high",
            runner_up="antigravity",
            task_type="code_refactor",
            task_domain="python",
            user_likely_values=["correctness"],
            provider_scores={"claude": {"overall": 8.0}},
            routing_lesson="For X prefer Y.",
            eval_seed="should pass: tests stay green",
        )
        rebuilt = CouncilRoutingLabel.from_dict(original.to_dict())
        assert rebuilt.winner == original.winner
        assert rebuilt.task_type == original.task_type
        assert rebuilt.provider_scores == original.provider_scores

    def test_from_dict_tolerates_unknown_fields(self):
        raw = {"winner": "claude", "confidence": "high", "future_field": "ignored"}
        label = CouncilRoutingLabel.from_dict(raw)
        assert label.winner == "claude"
        assert label.confidence == "high"


# ---------------------------------------------------------------------------
# Council review HTML renders the routing label
# ---------------------------------------------------------------------------

class TestRoutingLabelInHtml:
    def test_routing_label_renders_in_review(self, patch_trinity_home: Path, bundle, members):
        from trinity_local.council_review import write_unified_council_page
        from trinity_local.council_runtime import save_council_outcome
        from trinity_local.state_paths import council_outcomes_dir

        label = CouncilRoutingLabel(
            winner="claude",
            runner_up="antigravity",
            confidence="high",
            task_type="code_refactor",
            task_domain="python",
            routing_lesson="For code_refactor, prefer claude because it executes reliably.",
            eval_seed="should pass: type hints preserved",
            provider_scores={"claude": {"overall": 8.5}, "antigravity": {"overall": 6.2}},
        )
        outcome = create_council_outcome(
            bundle=bundle,
            primary_provider="claude",
            member_results=members,
            primary_model="claude-sonnet-4-6",
            routing_label=label,
        )
        save_council_outcome(outcome)
        write_unified_council_page(bundle, outcome)

        # Routing label data lives in the JSONP wrapper that the unified
        # page loads at runtime.
        outcome_js = (council_outcomes_dir() / f"{outcome.council_run_id}.js").read_text(encoding="utf-8")
        assert "code_refactor" in outcome_js
        assert "For code_refactor" in outcome_js
        assert "type hints preserved" in outcome_js
        assert "8.5" in outcome_js

    def test_no_routing_label_hides_section(self, patch_trinity_home: Path, bundle, members):
        from trinity_local.council_review import write_unified_council_page
        from trinity_local.council_runtime import save_council_outcome
        from trinity_local.state_paths import council_outcomes_dir

        outcome = create_council_outcome(
            bundle=bundle,
            primary_provider="claude",
            member_results=members,
            primary_model="claude-sonnet-4-6",
        )
        save_council_outcome(outcome)
        write_unified_council_page(bundle, outcome)
        outcome_js = (council_outcomes_dir() / f"{outcome.council_run_id}.js").read_text(encoding="utf-8")
        assert '"routing_label"' not in outcome_js


class TestLegacyProviderSlugNormalization:
    """`from_dict` normalizes the legacy `gemini` slug → canonical
    `antigravity` at the load boundary, so personal_routing aggregation,
    chairman picker, and launchpad rendering all see one canonical key.

    Pins the fix from tick 96: without normalization, historical outcomes
    keyed under `provider_scores["gemini"]` would aggregate as a separate
    bucket from new outcomes under `provider_scores["antigravity"]`,
    splitting the per-task_type stats for the same model across two
    apparent providers."""

    def test_winner_gemini_normalized_to_antigravity(self):
        from trinity_local.council_schema import CouncilRoutingLabel
        label = CouncilRoutingLabel.from_dict({"winner": "gemini"})
        assert label.winner == "antigravity"

    def test_runner_up_gemini_normalized(self):
        from trinity_local.council_schema import CouncilRoutingLabel
        label = CouncilRoutingLabel.from_dict({
            "winner": "claude",
            "runner_up": "gemini",
        })
        assert label.runner_up == "antigravity"

    def test_provider_scores_key_normalized(self):
        from trinity_local.council_schema import CouncilRoutingLabel
        label = CouncilRoutingLabel.from_dict({
            "winner": "claude",
            "provider_scores": {
                "gemini": {"overall": 0.72},
                "claude": {"overall": 0.81},
            },
        })
        # Aggregator should see "antigravity", not "gemini"
        assert set(label.provider_scores.keys()) == {"antigravity", "claude"}
        assert label.provider_scores["antigravity"]["overall"] == 0.72

    def test_already_canonical_slugs_pass_through(self):
        from trinity_local.council_schema import CouncilRoutingLabel
        label = CouncilRoutingLabel.from_dict({
            "winner": "antigravity",
            "runner_up": "claude",
            "provider_scores": {"antigravity": {"overall": 0.9}},
        })
        assert label.winner == "antigravity"
        assert label.runner_up == "claude"
        assert "antigravity" in label.provider_scores

    def test_unknown_slug_passes_through_unchanged(self):
        from trinity_local.council_schema import CouncilRoutingLabel
        label = CouncilRoutingLabel.from_dict({"winner": "mlx"})
        assert label.winner == "mlx"
