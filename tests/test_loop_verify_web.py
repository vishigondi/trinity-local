"""Tests for the Autobrowse subprocess wrapper.

The wrapper has to handle three regimes: Autobrowse installed and graduating,
Autobrowse installed but failing, and Autobrowse missing entirely. The third
is the most common path on a fresh install — must degrade gracefully so the
inner loop falls back to chairman_rubric, not crashes.
"""

from __future__ import annotations


class TestAutobrowseDetection:
    def test_returns_false_when_npx_missing(self, monkeypatch):
        from trinity_local.loop import verify_web
        monkeypatch.setattr(verify_web.shutil, "which", lambda _: None)
        assert verify_web.autobrowse_available() is False

    def test_graceful_when_subprocess_raises(self, monkeypatch):
        from trinity_local.loop import verify_web
        monkeypatch.setattr(verify_web.shutil, "which", lambda _: "/usr/bin/npx")

        def fake_run(*args, **kwargs):
            raise OSError("boom")

        monkeypatch.setattr(verify_web.subprocess, "run", fake_run)
        # Wrapper swallows OSError → not available, no crash
        assert verify_web.autobrowse_available() is False


class TestOutputParser:
    def test_parses_graduation_signal(self):
        from trinity_local.loop.verify_web import parse_autobrowse_output
        stdout = """
        Iteration 1/5: working...
        Iteration 2/5: refining strategy
        Iteration 3/5: passed on attempt
        graduated SKILL.md to /Users/me/.claude/skills/extract-pricing/SKILL.md
        """
        passed, reasons, skill_md, iters, _ = parse_autobrowse_output(stdout)
        assert passed is True
        assert iters == 3
        assert skill_md and skill_md.endswith("/SKILL.md")

    def test_did_not_graduate_means_failed(self):
        from trinity_local.loop.verify_web import parse_autobrowse_output
        stdout = """
        Iteration 5/5: still failing
        FAIL: target page never loaded
        did not graduate after 5 iterations
        """
        passed, reasons, _, iters, _ = parse_autobrowse_output(stdout)
        assert passed is False
        assert iters == 5
        # FAIL line surfaces in reasons
        assert any("target page" in r for r in reasons)

    def test_summary_truncates_long_output(self):
        from trinity_local.loop.verify_web import parse_autobrowse_output
        stdout = "x" * 2000
        _, _, _, _, summary = parse_autobrowse_output(stdout)
        assert len(summary) <= 500


class TestVerifyWebDegradation:
    def test_returns_uniform_failure_when_autobrowse_missing(self, monkeypatch):
        # The whole point of the wrapper: when Autobrowse isn't installed, the
        # inner loop still gets a structured VerifyResult and can fall back to
        # chairman_rubric. No crash, no None — explicit not-available reason.
        from trinity_local.loop import verify_web
        monkeypatch.setattr(verify_web, "autobrowse_available", lambda: False)
        out = verify_web.verify_web(
            skill_id="skill_test",
            eval_seed="x" * 100,
            iterations=5,
        )
        assert out.passed is False
        assert any("not_available" in r for r in out.reasons)
        assert out.iterations_used == 0

    def test_handles_subprocess_timeout(self, monkeypatch):
        from trinity_local.loop import verify_web
        monkeypatch.setattr(verify_web, "autobrowse_available", lambda: True)

        def fake_run(*args, **kwargs):
            raise verify_web.subprocess.TimeoutExpired(cmd="npx", timeout=5)

        monkeypatch.setattr(verify_web.subprocess, "run", fake_run)
        out = verify_web.verify_web(
            skill_id="skill_test",
            eval_seed="x" * 100,
            iterations=5,
            timeout_seconds=5,
        )
        assert out.passed is False
        assert any("timed out" in r for r in out.reasons)

    def test_nonzero_exit_overrides_stdout_graduation(self, monkeypatch):
        # Defensive: even if Autobrowse stdout claims "graduated", a non-zero
        # exit code means the wrapper didn't trust the run.
        from trinity_local.loop import verify_web

        class FakeCompleted:
            stdout = "graduated SKILL.md to /tmp/SKILL.md"
            stderr = "exit code 1"
            returncode = 1

        monkeypatch.setattr(verify_web, "autobrowse_available", lambda: True)
        monkeypatch.setattr(verify_web.subprocess, "run", lambda *a, **kw: FakeCompleted())
        out = verify_web.verify_web(
            skill_id="skill_test",
            eval_seed="x" * 100,
        )
        assert out.passed is False
        assert any("exit code 1" in r for r in out.reasons)


class TestSlugDerivation:
    def test_slug_strips_skill_prefix(self):
        from trinity_local.loop.verify_web import _slug_from_skill_id
        assert _slug_from_skill_id("skill_abc123") == "abc123"

    def test_slug_unchanged_when_no_prefix(self):
        from trinity_local.loop.verify_web import _slug_from_skill_id
        assert _slug_from_skill_id("custom-name") == "custom-name"
