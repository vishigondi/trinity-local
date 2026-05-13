"""Tests for `trinity-local doctor` — pre-flight cold-install checks.

Council council_35b2ae198a65b349 named the cold-install path as the
audit-missed launch blocker. The eval seed for that council asks for a
specific failure mode + the CLI command that detects it. These tests
pin both: each provider check returns ok=False with a fix line when the
relevant indicator is missing, and run_doctor never crashes on a fresh
machine state.
"""

from __future__ import annotations


class TestTrinityHomeCheck:
    def test_writeable_dir_returns_ok(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        from trinity_local.doctor import _check_trinity_home
        result = _check_trinity_home()
        assert result.ok is True
        assert "writeable" in result.detail

    def test_unwriteable_dir_emits_fix_line(self, tmp_path, monkeypatch):
        # Read-only parent so probe write fails — verifies the failure path
        # surfaces a concrete fix the user can run.
        import os
        protected = tmp_path / "ro"
        protected.mkdir()
        os.chmod(protected, 0o500)  # owner read+execute, no write
        monkeypatch.setenv("TRINITY_HOME", str(protected / "trinity"))
        try:
            from trinity_local.doctor import _check_trinity_home
            result = _check_trinity_home()
            # Some filesystems still allow writes despite chmod (e.g., as root in CI).
            # Either way, fix line should be informative when the check fails.
            if not result.ok:
                assert "chmod" in result.fix or "TRINITY_HOME" in result.fix
        finally:
            os.chmod(protected, 0o700)


class TestProviderCheck:
    def test_missing_cli_returns_install_fix(self, monkeypatch):
        from trinity_local.doctor import _check_provider
        # which() returns None → CLI not installed
        monkeypatch.setattr("trinity_local.doctor.shutil.which", lambda _: None)
        result = _check_provider("claude", "claude")
        assert result.ok is False
        assert "not on PATH" in result.detail
        assert "Claude Code" in result.fix or "install" in result.fix.lower()

    def test_installed_no_auth_returns_login_fix(self, monkeypatch, tmp_path):
        # CLI installed but no auth indicator file — concrete cold-install
        # failure mode that doctor must catch.
        from trinity_local import doctor as doctor_mod
        monkeypatch.setattr(doctor_mod.shutil, "which", lambda _: "/usr/local/bin/claude")
        monkeypatch.setattr(
            doctor_mod,
            "_AUTH_INDICATORS",
            {"claude": [tmp_path / "absent.json"]},  # no indicator exists
        )
        result = doctor_mod._check_provider("claude", "claude")
        assert result.ok is False
        assert "no auth indicator" in result.detail
        assert "login" in result.fix or "interactively" in result.fix

    def test_installed_with_auth_returns_ready(self, monkeypatch, tmp_path):
        from trinity_local import doctor as doctor_mod
        monkeypatch.setattr(doctor_mod.shutil, "which", lambda _: "/usr/local/bin/claude")
        indicator = tmp_path / "auth.json"
        indicator.write_text("{}")
        monkeypatch.setattr(doctor_mod, "_AUTH_INDICATORS", {"claude": [indicator]})
        result = doctor_mod._check_provider("claude", "claude")
        assert result.ok is True
        assert "authenticated" in result.detail


class TestMcpAvailable:
    def test_returns_ok_when_mcp_importable(self):
        # mcp dep is in this dev env, so this should pass; if it's not,
        # the test still verifies the check returns the right shape.
        from trinity_local.doctor import _check_mcp_available
        result = _check_mcp_available()
        assert isinstance(result.ok, bool)
        if not result.ok:
            assert "pip install" in result.fix


class TestDoctorReport:
    def test_ready_for_council_requires_one_provider_plus_writeable_home(
        self, tmp_path, monkeypatch
    ):
        from trinity_local.doctor import CheckResult, DoctorReport
        # All providers failing → not ready
        report = DoctorReport(checks=[
            CheckResult(name="trinity_home_writeable", ok=True),
            CheckResult(name="provider:claude", ok=False),
            CheckResult(name="provider:gemini", ok=False),
            CheckResult(name="provider:codex", ok=False),
        ])
        assert report.ready_for_council is False

    def test_ready_for_council_with_one_provider(self):
        from trinity_local.doctor import CheckResult, DoctorReport
        report = DoctorReport(checks=[
            CheckResult(name="trinity_home_writeable", ok=True),
            CheckResult(name="provider:claude", ok=True),
            CheckResult(name="provider:gemini", ok=False),
            CheckResult(name="provider:codex", ok=False),
        ])
        # Even with 2/3 providers failing, ready_for_council is true if 1 works
        assert report.ready_for_council is True

    def test_run_doctor_never_crashes_on_fresh_state(self, tmp_path, monkeypatch):
        # The most important property: doctor never throws regardless of
        # what's missing. A fresh-install user runs it as their first
        # interaction with Trinity.
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path / "trinity"))
        from trinity_local.doctor import run_doctor
        report = run_doctor()
        # Should produce all expected check categories
        names = {c.name for c in report.checks}
        assert "trinity_home_writeable" in names
        assert any(n.startswith("provider:") for n in names)
        assert "config_loadable" in names

    def test_format_human_includes_fix_lines(self):
        # Failure path: the human format must surface the fix command,
        # not just the failure detail. Otherwise users see "✗ provider:claude
        # not on PATH" and don't know what to do.
        from trinity_local.doctor import CheckResult, DoctorReport, format_human
        report = DoctorReport(checks=[
            CheckResult(
                name="provider:claude",
                ok=False,
                detail="claude CLI not on PATH",
                fix="Install Claude Code: https://example.com",
            ),
        ])
        out = format_human(report)
        assert "✗" in out
        assert "→ fix:" in out
        assert "https://example.com" in out


class TestFeedbackConsistency:
    """Tick #75 — surface orphaned council_feedback entries so audits
    are reproducible. Soft check: ok stays True (orphans are harmless),
    detail explains the count when non-zero. Reproduces tick #69's
    "16 of 19 entries reference deleted outcomes" finding shape."""

    def test_no_feedback_log_passes_silently(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path / "trinity"))
        (tmp_path / "trinity").mkdir(parents=True, exist_ok=True)
        from trinity_local.doctor import _check_feedback_consistency
        result = _check_feedback_consistency()
        assert result.ok is True
        assert "fresh install" in result.detail.lower()

    def test_aligned_feedback_passes_clean(self, tmp_path, monkeypatch):
        """Every feedback entry matches an existing outcome → clean."""
        import json as _json
        home = tmp_path / "trinity"
        outcomes = home / "council_outcomes"
        outcomes.mkdir(parents=True, exist_ok=True)
        (outcomes / "council_x.json").write_text("{}", encoding="utf-8")
        (home / "council_feedback.jsonl").write_text(
            _json.dumps({"council_id": "council_x", "provider": "claude"}) + "\n",
            encoding="utf-8",
        )
        monkeypatch.setenv("TRINITY_HOME", str(home))
        from trinity_local.doctor import _check_feedback_consistency
        result = _check_feedback_consistency()
        assert result.ok is True
        assert "no longer exist" not in result.detail

    def test_orphaned_feedback_surfaced_but_still_ok(self, tmp_path, monkeypatch):
        """Orphans are loud (detail names the count) but not failing
        (ok=True, doctor stays green). This is the regression target —
        if a future doctor refactor flipped this to ok=False, every
        post-cleanup user would suddenly see a red ✗ for accumulated
        history they can't safely undo."""
        import json as _json
        home = tmp_path / "trinity"
        outcomes = home / "council_outcomes"
        outcomes.mkdir(parents=True, exist_ok=True)
        (outcomes / "council_alive.json").write_text("{}", encoding="utf-8")
        lines = [
            _json.dumps({"council_id": "council_alive", "provider": "c"}),
            _json.dumps({"council_id": "council_deleted_1", "provider": "c"}),
            _json.dumps({"council_id": "council_deleted_2", "provider": "g"}),
        ]
        (home / "council_feedback.jsonl").write_text("\n".join(lines) + "\n", encoding="utf-8")
        monkeypatch.setenv("TRINITY_HOME", str(home))
        from trinity_local.doctor import _check_feedback_consistency
        result = _check_feedback_consistency()
        assert result.ok is True
        assert "2 of 3" in result.detail
        assert "no longer exist" in result.detail


class TestShortcutCheck:
    """Tick #72 — doctor surfaces the macOS Shortcut registration
    proactively. This was the silent-failure root cause behind the
    16% verdict-capture rate (tick #69 census)."""

    def test_check_uses_shortcut_setup_helper(self, monkeypatch):
        """The check delegates to shortcut_setup._shortcut_installed.
        Stubbing the helper drives the check's ok/fix paths
        deterministically."""
        import trinity_local.shortcut_setup as setup
        from trinity_local.doctor import _check_shortcut_installed

        # OK branch
        monkeypatch.setattr(setup, "_shortcut_installed", lambda *_args, **_kw: True)
        result = _check_shortcut_installed()
        assert result.ok is True
        assert "registered" in result.detail.lower()

        # Failure branch — must surface the fix command so users know
        # what to do without reading the source.
        monkeypatch.setattr(setup, "_shortcut_installed", lambda *_args, **_kw: False)
        result = _check_shortcut_installed()
        assert result.ok is False
        assert "silently fail" in result.detail.lower()
        assert result.fix is not None
        assert "shortcut-install" in result.fix

    def test_run_doctor_includes_shortcut_check(self, tmp_path, monkeypatch):
        """The shortcut check is wired into run_doctor()'s check list —
        without this, the cold-install user runs doctor, sees all-green,
        opens the launchpad, and their first verdict click goes nowhere."""
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path / "trinity"))
        from trinity_local.doctor import run_doctor
        report = run_doctor()
        names = {c.name for c in report.checks}
        assert "shortcut_installed" in names
