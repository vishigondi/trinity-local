"""Tests for the v2 inner loop (run.py).

Most tests use a stub provider so the chairman dispatch path isn't actually
called — we're pinning state-machine behavior, not LLM output. The
council eval seed test is the load-bearing one: state.json transitions must
include `cull → re_verify → commit` whenever cull mutated the artifact.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace


class StubProvider:
    """A scriptable stand-in for `make_provider(...)`. Each call to .run()
    returns the next entry from `responses` (a list of (stdout, stderr) tuples)."""

    def __init__(self, responses):
        self._responses = list(responses)
        self.calls = []

    def run(self, prompt, cwd=None):
        self.calls.append(prompt)
        if not self._responses:
            return SimpleNamespace(stdout="", stderr="ran out of stub responses")
        stdout, stderr = self._responses.pop(0)
        return SimpleNamespace(stdout=stdout, stderr=stderr)


def _seed_frame(tmp_path, monkeypatch, *, verifier="chairman_rubric"):
    """Write a fixture frame.json so load_frame() finds it."""
    monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
    from trinity_local.loop.frame import Frame, save_frame
    f = Frame(
        skill_id="skill_fixture",
        intent="summarize markdown preserving structure",
        inversions=["fabricate", "drop sections", "break syntax"],
        eval_seed="x" * 100,
        verifier=verifier,
        model_baseline={"claude": "opus-4-7"},
        created_at="2026-05-07T00:00:00",
    )
    save_frame(f)
    return f


class TestParsers:
    def test_parse_verify_passed_with_reasons(self):
        from trinity_local.loop.run import parse_verify_output
        passed, reasons = parse_verify_output(
            '{"passed": true, "reasons": ["heading hierarchy preserved", "no fabricated facts"]}'
        )
        assert passed is True
        assert len(reasons) == 2

    def test_parse_verify_passed_without_reasons_treated_as_failure(self):
        # Per the prompt's own rule — no reasons means no audit trail
        from trinity_local.loop.run import parse_verify_output
        passed, reasons = parse_verify_output('{"passed": true, "reasons": []}')
        assert passed is False
        assert "no reasons" in reasons[0]

    def test_parse_verify_handles_garbage_input(self):
        from trinity_local.loop.run import parse_verify_output
        passed, reasons = parse_verify_output("not json")
        assert passed is False

    def test_parse_cull_no_op_returns_original(self):
        from trinity_local.loop.run import parse_cull_output
        removed, post = parse_cull_output(
            '{"removed": [], "artifact": "original text"}',
            original="original text",
        )
        assert removed == []
        assert post == "original text"

    def test_parse_cull_mutated_returns_post_cull(self):
        from trinity_local.loop.run import parse_cull_output
        removed, post = parse_cull_output(
            '{"removed": ["dropped fluff intro"], "artifact": "tightened version"}',
            original="original text with fluff intro",
        )
        assert removed == ["dropped fluff intro"]
        assert post == "tightened version"

    def test_parse_cull_falls_back_to_original_on_garbage(self):
        # Defensive: chairman drift never silently rewrites the artifact
        from trinity_local.loop.run import parse_cull_output
        _, post = parse_cull_output("not json at all", original="keep me")
        assert post == "keep me"


class TestArtifactHash:
    def test_hash_is_deterministic(self):
        from trinity_local.loop.run import artifact_hash
        assert artifact_hash("hello") == artifact_hash("hello")
        assert artifact_hash("hello") != artifact_hash("hello!")
        assert artifact_hash("").startswith("sha256:")


class TestStatePersistence:
    def test_state_round_trip(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        _seed_frame(tmp_path, monkeypatch)
        from trinity_local.loop.run import State, HistoryRecord, save_state, load_state

        s = State(
            skill_id="skill_fixture",
            iteration=2,
            artifact="hello world",
            history=[HistoryRecord(
                iteration=1, stage="verify", outcome="failed",
                reasons=["heading missing"], timestamp="2026-05-07T00:00:01",
            )],
        )
        save_state(s)
        loaded = load_state("skill_fixture")
        assert loaded is not None
        assert loaded.iteration == 2
        assert len(loaded.history) == 1
        assert loaded.history[0].outcome == "failed"


class TestInnerLoopStateMachine:
    """The load-bearing tests. Drive the state machine with a stub provider
    and assert the council eval seed: cull → re_verify → commit when cull mutates."""

    def _patched_run(self, monkeypatch, tmp_path, responses, frame_kwargs=None):
        """Wire a StubProvider into _resolve_chairman and run the inner loop."""
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        _seed_frame(tmp_path, monkeypatch, **(frame_kwargs or {}))

        provider = StubProvider(responses)
        from trinity_local.loop import run as run_mod
        from trinity_local.loop import cli as cli_mod
        monkeypatch.setattr(
            cli_mod,
            "_resolve_chairman",
            lambda: ("claude", SimpleNamespace(model="opus-4-7"), provider),
        )
        # Capture stdout to suppress noisy CLI prints during tests
        import io
        import contextlib
        with contextlib.redirect_stdout(io.StringIO()):
            exit_code = run_mod.run_inner_loop("skill_fixture", max_iter=3)
        return exit_code, run_mod.load_state("skill_fixture"), provider

    def test_cull_mutates_triggers_re_verify_then_commit(self, tmp_path, monkeypatch):
        # The council eval seed: when cull mutates, re-verify fires before commit.
        responses = [
            ("draft artifact with extra fluff", ""),  # execute (iter 1)
            ('{"passed": true, "reasons": ["matches eval_seed"]}', ""),  # verify
            ('{"removed": ["fluff"], "artifact": "tightened artifact"}', ""),  # cull (mutates!)
            ('{"passed": true, "reasons": ["tighter version still matches"]}', ""),  # re-verify
        ]
        exit_code, state, provider = self._patched_run(monkeypatch, tmp_path, responses)
        assert exit_code == 0
        assert state.graduated is True
        # The eval seed assertion: history must contain cull→mutated, then re_verify→passed, then commit
        stages = [(r.stage, r.outcome) for r in state.history]
        assert ("cull", "mutated") in stages
        assert ("re_verify", "passed") in stages
        assert ("commit", "passed") in stages
        # And the order: cull's mutated record sits before re_verify's record sits before commit
        cull_idx = next(i for i, s in enumerate(stages) if s == ("cull", "mutated"))
        reverify_idx = next(i for i, s in enumerate(stages) if s == ("re_verify", "passed"))
        commit_idx = next(i for i, s in enumerate(stages) if s == ("commit", "passed"))
        assert cull_idx < reverify_idx < commit_idx, f"order broken: {stages}"

    def test_cull_no_op_skips_re_verify(self, tmp_path, monkeypatch):
        # When the artifact hash didn't change, re-verify is a no-op (saves a chairman call).
        responses = [
            ("draft artifact", ""),  # execute
            ('{"passed": true, "reasons": ["matches"]}', ""),  # verify
            ('{"removed": [], "artifact": "draft artifact"}', ""),  # cull no-op
            # NO re-verify response needed
        ]
        exit_code, state, provider = self._patched_run(monkeypatch, tmp_path, responses)
        assert exit_code == 0
        assert state.graduated is True
        stages = [(r.stage, r.outcome) for r in state.history]
        # Cull is "noop", not "mutated"; re_verify never fired
        assert ("cull", "noop") in stages
        assert not any(s == "re_verify" for s, _ in stages)
        assert ("commit", "passed") in stages

    def test_re_verify_failure_discards_cull_keeps_pre_cull(self, tmp_path, monkeypatch):
        # If cull breaks the verifier, the pre-cull artifact stays valid but
        # the iteration is logged as failed and the loop retries.
        responses = [
            ("good artifact", ""),  # execute (iter 1)
            ('{"passed": true, "reasons": ["matches"]}', ""),  # verify
            ('{"removed": ["everything"], "artifact": "broken stub"}', ""),  # cull mutates
            ('{"passed": false, "reasons": ["lost the structure"]}', ""),  # re-verify FAILS
            # iter 2 starts...
            ("better artifact", ""),  # execute (iter 2)
            ('{"passed": true, "reasons": ["matches"]}', ""),  # verify
            ('{"removed": [], "artifact": "better artifact"}', ""),  # cull no-op
        ]
        exit_code, state, provider = self._patched_run(monkeypatch, tmp_path, responses)
        assert exit_code == 0
        assert state.graduated is True
        # Iter 1 saw a re_verify failure
        iter1_records = [r for r in state.history if r.iteration == 1]
        re_verify_failed = any(r.stage == "re_verify" and r.outcome == "failed" for r in iter1_records)
        assert re_verify_failed
        # Iter 2 graduated
        iter2_commits = [r for r in state.history if r.iteration == 2 and r.stage == "commit"]
        assert iter2_commits

    def test_resumes_when_state_exists(self, tmp_path, monkeypatch):
        # Pre-graduated runs no-op rather than re-execute.
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        _seed_frame(tmp_path, monkeypatch)
        from trinity_local.loop.run import State, save_state, run_inner_loop
        save_state(State(skill_id="skill_fixture", graduated=True))

        from trinity_local.loop import cli as cli_mod
        monkeypatch.setattr(
            cli_mod,
            "_resolve_chairman",
            lambda: ("claude", SimpleNamespace(model="opus-4-7"), StubProvider([])),
        )
        import io, contextlib
        with contextlib.redirect_stdout(io.StringIO()):
            exit_code = run_inner_loop("skill_fixture", max_iter=3)
        assert exit_code == 0  # no-op success

    def test_max_iter_exhausted_marks_failed_to_graduate(self, tmp_path, monkeypatch):
        # All execute/verify cycles fail → exhaust budget → record failure terminal state.
        responses = []
        for _ in range(3):
            responses.extend([
                ("attempt", ""),  # execute
                ('{"passed": false, "reasons": ["wrong shape"]}', ""),  # verify failed
            ])
        exit_code, state, _ = self._patched_run(monkeypatch, tmp_path, responses)
        assert exit_code == 3
        assert state.failed_to_graduate is True
        assert state.iteration == 3
