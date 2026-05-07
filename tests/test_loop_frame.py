"""Tests for the v2 outer loop (frame.py).

Council council_7a770b8b78b6bd4e ratified one-call framing. These tests pin
the parser, validator, and persistence — the chairman-call dispatch lives
in cli.py and is exercised by integration tests once a fixture provider
lands.
"""

from __future__ import annotations


class TestFramePromptAndParser:
    def test_render_frame_prompt_demands_structured_json(self):
        from trinity_local.loop.frame import render_frame_prompt
        out = render_frame_prompt("summarize a markdown doc")
        # The prompt must spell out the JSON schema and the hard requirements
        # so a well-prompted chairman returns parseable output.
        assert "INVERSIONS" in out
        assert "EVAL_SEED" in out
        assert "autobrowse" in out and "chairman_rubric" in out
        assert "summarize a markdown doc" in out

    def test_parse_frame_output_handles_markdown_fences(self):
        from trinity_local.loop.frame import parse_frame_output
        raw = """```json
{
  "inversions": ["fails on tables", "fails on code blocks", "fails on long docs"],
  "eval_seed": "Output preserves all H2 headings, bullet lists, and the order of major sections from the source markdown — at least 80 chars to satisfy the validator.",
  "verifier": "chairman_rubric"
}
```"""
        inv, seed, verifier = parse_frame_output(raw)
        assert len(inv) == 3
        assert verifier == "chairman_rubric"
        assert "preserves" in seed

    def test_parse_frame_output_normalizes_unknown_verifier(self):
        from trinity_local.loop.frame import parse_frame_output
        raw = '{"inversions": ["a", "b", "c"], "eval_seed": "' + "x" * 100 + '", "verifier": "made_up"}'
        _, _, verifier = parse_frame_output(raw)
        # Falls back to the safe default rather than passing through bogus enum
        assert verifier == "chairman_rubric"

    def test_parse_frame_output_returns_empty_on_garbage(self):
        from trinity_local.loop.frame import parse_frame_output
        inv, seed, verifier = parse_frame_output("not json at all, sorry")
        assert inv == []
        assert seed == ""
        assert verifier == "chairman_rubric"

    def test_parse_frame_output_skips_blank_inversions(self):
        from trinity_local.loop.frame import parse_frame_output
        raw = '{"inversions": ["real", "", "  ", "another"], "eval_seed": "' + "x" * 100 + '", "verifier": "chairman_rubric"}'
        inv, _, _ = parse_frame_output(raw)
        assert inv == ["real", "another"]


class TestFrameValidator:
    def test_validator_rejects_too_few_inversions(self):
        from trinity_local.loop.frame import validate_frame
        ok, reason = validate_frame(["a", "b"], "x" * 100)
        assert not ok
        assert "inversions count 2" in reason

    def test_validator_rejects_too_many_inversions(self):
        from trinity_local.loop.frame import validate_frame
        ok, reason = validate_frame(["a"] * 8, "x" * 100)
        assert not ok
        assert "inversions count 8" in reason

    def test_validator_rejects_short_eval_seed(self):
        from trinity_local.loop.frame import validate_frame
        ok, reason = validate_frame(["a", "b", "c"], "tagline only")
        assert not ok
        assert "too short" in reason

    def test_validator_accepts_minimum_legal_frame(self):
        from trinity_local.loop.frame import validate_frame
        ok, _ = validate_frame(["a", "b", "c"], "x" * 80)
        assert ok


class TestSkillIdAndPersistence:
    def test_stable_skill_id_is_deterministic(self):
        from trinity_local.loop.frame import stable_skill_id
        a = stable_skill_id("summarize a markdown doc")
        b = stable_skill_id("summarize a markdown doc")
        c = stable_skill_id("a different intent")
        assert a == b
        assert a != c
        assert a.startswith("skill_")

    def test_save_and_load_frame_round_trip(self, tmp_path, monkeypatch):
        from trinity_local.loop.frame import Frame, save_frame, load_frame
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        f = Frame(
            skill_id="skill_test123",
            intent="summarize",
            inversions=["a", "b", "c"],
            eval_seed="x" * 100,
            verifier="chairman_rubric",
            model_baseline={"claude": "opus-4-7"},
            created_at="2026-05-07T12:00:00",
        )
        path = save_frame(f)
        assert path.exists()
        loaded = load_frame("skill_test123")
        assert loaded is not None
        assert loaded.skill_id == "skill_test123"
        assert loaded.inversions == ["a", "b", "c"]
        assert loaded.verifier == "chairman_rubric"
