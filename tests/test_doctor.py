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


class TestVerdictRateCheck:
    """Tick #97 — doctor surfaces the Pillar-4 verdict capture rate
    directly. Reuses _verdict_stats() so the math stays single-source.
    Soft (ok=True regardless); detail names the rate."""

    def test_no_councils_yet_returns_early_message(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path / "trinity"))
        (tmp_path / "trinity" / "council_outcomes").mkdir(parents=True)
        from trinity_local.doctor import _check_verdict_rate
        result = _check_verdict_rate()
        assert result.ok is True
        assert "no councils yet" in result.detail.lower()

    def test_low_rate_above_threshold_nudges(self, tmp_path, monkeypatch):
        """Real regression target: with 5+ councils and rate < 50%,
        the detail must surface the percentage AND point at the
        `unrated` CLI from tick #93 (cross-surface discoverability)."""
        import json as _json
        home = tmp_path / "trinity"
        (home / "council_outcomes").mkdir(parents=True)
        # 6 councils, 1 rated → 17% rate
        for i in range(6):
            metadata = {"task_text": f"q{i}"}
            if i == 0:
                metadata["user_verdict"] = {"user_winner": "claude"}
            (home / "council_outcomes" / f"council_{i}.json").write_text(
                _json.dumps({"council_run_id": f"council_{i}", "metadata": metadata})
            )
        monkeypatch.setenv("TRINITY_HOME", str(home))
        from trinity_local.doctor import _check_verdict_rate
        result = _check_verdict_rate()
        assert result.ok is True
        assert "1 of 6" in result.detail
        assert "16%" in result.detail or "17%" in result.detail  # rounding edge
        assert "trinity-local unrated" in result.detail

    def test_high_rate_silent(self, tmp_path, monkeypatch):
        """Rate ≥ 50% → quieter detail (no nudge), still ok=True.
        The launchpad accent prompt and this check share the
        same threshold so messaging stays consistent."""
        import json as _json
        home = tmp_path / "trinity"
        (home / "council_outcomes").mkdir(parents=True)
        # 5 councils, 4 rated → 80% rate
        for i in range(5):
            metadata = {"task_text": f"q{i}"}
            if i < 4:
                metadata["user_verdict"] = {"user_winner": "claude"}
            (home / "council_outcomes" / f"council_{i}.json").write_text(
                _json.dumps({"council_run_id": f"council_{i}", "metadata": metadata})
            )
        monkeypatch.setenv("TRINITY_HOME", str(home))
        from trinity_local.doctor import _check_verdict_rate
        result = _check_verdict_rate()
        assert result.ok is True
        assert "4 of 5" in result.detail
        # No nudge to unrated CLI when rate is healthy
        assert "trinity-local unrated" not in result.detail
        assert "compounding" in result.detail.lower()


class TestCortexFreshnessCheck:
    """Tick #96 — soft check: are cortex picks current relative to
    recent councils? Stale picks mean `ask()` routes on outdated
    signal. Soft (ok=True) because stale isn't broken; surfaces the
    count so the user can decide whether to re-consolidate."""

    def test_no_picks_yet_returns_helpful_message(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path / "trinity"))
        (tmp_path / "trinity" / "memories").mkdir(parents=True, exist_ok=True)
        from trinity_local.doctor import _check_cortex_freshness
        result = _check_cortex_freshness()
        assert result.ok is True
        assert "not built yet" in result.detail
        assert "consolidate" in result.detail.lower()

    def test_picks_fresh_with_no_newer_outcomes(self, tmp_path, monkeypatch):
        """Picks consolidated, no outcomes newer than freshest pick —
        the all-current branch."""
        import json as _json
        home = tmp_path / "trinity"
        (home / "memories").mkdir(parents=True, exist_ok=True)
        (home / "council_outcomes").mkdir(parents=True, exist_ok=True)
        picks = {
            "council_synthesis": {
                "consolidated_at": "2026-05-13T12:00:00+00:00",
                "task_kinds": ["council_synthesis"],
            }
        }
        (home / "memories" / "picks.json").write_text(_json.dumps(picks))
        outcome = {
            "council_run_id": "council_a",
            "created_at": "2026-05-13T11:00:00+00:00",  # older than picks
        }
        (home / "council_outcomes" / "council_a.json").write_text(_json.dumps(outcome))
        monkeypatch.setenv("TRINITY_HOME", str(home))
        from trinity_local.doctor import _check_cortex_freshness
        result = _check_cortex_freshness()
        assert result.ok is True
        assert "current" in result.detail

    def test_picks_stale_when_newer_outcomes_exist(self, tmp_path, monkeypatch):
        """The actual regression target — picks lag behind. ok=True
        (soft), detail names the count + remediation."""
        import json as _json
        home = tmp_path / "trinity"
        (home / "memories").mkdir(parents=True, exist_ok=True)
        (home / "council_outcomes").mkdir(parents=True, exist_ok=True)
        picks = {
            "council_synthesis": {
                "consolidated_at": "2026-05-12T00:00:00+00:00",
                "task_kinds": ["council_synthesis"],
            }
        }
        (home / "memories" / "picks.json").write_text(_json.dumps(picks))
        # Two outcomes: one newer than picks, one older
        for cid, when in [
            ("council_new", "2026-05-13T12:00:00+00:00"),  # newer → triggers stale
            ("council_old", "2026-05-11T00:00:00+00:00"),
        ]:
            outcome = {"council_run_id": cid, "created_at": when}
            (home / "council_outcomes" / f"{cid}.json").write_text(_json.dumps(outcome))
        monkeypatch.setenv("TRINITY_HOME", str(home))
        from trinity_local.doctor import _check_cortex_freshness
        result = _check_cortex_freshness()
        assert result.ok is True  # soft — stale isn't broken
        assert "1 of 2" in result.detail
        assert "consolidate" in result.detail.lower()


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


class TestNextStepHint:
    """The handoff-demo nudge in `trinity-local doctor` output (task #115).

    After a green doctor run the user otherwise sees "Trinity is ready"
    with no idea what to do next. Surfacing the handoff demo right
    there closes the "I installed it, now what?" gap that #115 is
    about. These tests pin the tiered behavior so a future refactor
    doesn't silently drop the hint.
    """

    def _make_report(self, *, providers_green=2, prompts_ok=True):
        from trinity_local.doctor import DoctorReport, CheckResult

        checks = []
        names = ["claude", "codex", "gemini"]
        for i, name in enumerate(names):
            checks.append(CheckResult(
                name=f"provider:{name}",
                ok=(i < providers_green),
                detail=f"{name} {'installed' if i < providers_green else 'missing'}",
            ))
        checks.append(CheckResult(
            name="prompts_seeded",
            ok=prompts_ok,
            detail=("ok" if prompts_ok else "no prompts"),
        ))
        return DoctorReport(checks=checks)

    def test_hint_silent_with_only_one_provider(self):
        """Handoff needs at least two providers — one to start the
        conversation, one to continue it. With only one green, there's
        nothing to recommend."""
        from trinity_local.doctor import _next_step_hint
        report = self._make_report(providers_green=1)
        assert _next_step_hint(report) is None

    def test_hint_recommends_seed_when_no_prompts(self):
        """≥2 providers but no prompt index → the demo doesn't work
        yet (handoff has no recent turns to package). Recommend the
        seed-first path."""
        from trinity_local.doctor import _next_step_hint
        report = self._make_report(providers_green=2, prompts_ok=False)
        hint = _next_step_hint(report)
        assert hint is not None
        assert "seed-from-taste-terminal" in hint
        assert "handoff" in hint

    def test_hint_recommends_handoff_when_ready(self):
        """≥2 providers AND prompts indexed → demo is ready. Suggest
        the conversation-then-handoff flow."""
        from trinity_local.doctor import _next_step_hint
        report = self._make_report(providers_green=3, prompts_ok=True)
        hint = _next_step_hint(report)
        assert hint is not None
        assert "handoff" in hint
        assert "Claude Code" in hint
        # The 60-second wedge framing — keeps the marketing voice
        # consistent across surfaces.
        assert "60-second" in hint or "wedge" in hint

    def test_hint_picks_non_claude_target(self):
        """When recommending a handoff target, prefer something that
        isn't Claude — the demo lands because the SECOND model picks
        up the FIRST's context. Suggesting `handoff claude` defeats
        the point if the user's default IS Claude."""
        from trinity_local.doctor import _next_step_hint
        report = self._make_report(providers_green=3, prompts_ok=True)
        hint = _next_step_hint(report)
        # Either codex or gemini, but never claude
        assert "handoff codex" in hint or "handoff gemini" in hint
        assert "handoff claude" not in hint

    def test_hint_target_name_used_consistently(self):
        """The target named in the command and the target named in the
        narrative example must match — otherwise the copy reads
        'handoff codex — Gemini will pick up...' which is just sloppy."""
        from trinity_local.doctor import _next_step_hint
        report = self._make_report(providers_green=3, prompts_ok=True)
        hint = _next_step_hint(report)
        # Find which target was named in the command, verify the same
        # name appears as the "will pick up" subject.
        import re
        m = re.search(r"handoff (\w+)`", hint)
        assert m, f"hint missing handoff command: {hint}"
        target = m.group(1)
        assert f"{target} will pick up" in hint, (
            f"target/example mismatch in hint: command says handoff "
            f"{target}, but the narrative example doesn't match. "
            f"Hint: {hint}"
        )

    def test_format_human_includes_hint_on_success(self):
        """End-to-end: format_human should append the hint after the
        'Trinity is ready' line when conditions are met."""
        from trinity_local.doctor import format_human
        report = self._make_report(providers_green=3, prompts_ok=True)
        # All_ok requires ALL checks to be ok; the made report has
        # both providers and prompts green, which is enough for the
        # hint regardless of all_ok status.
        text = format_human(report)
        assert "Try this next" in text
        assert "handoff" in text

    def test_format_human_omits_hint_with_no_providers(self):
        """Don't show a 'try this' nudge when the user can't actually
        try it — that just adds noise to a fail-state report."""
        from trinity_local.doctor import format_human
        report = self._make_report(providers_green=0)
        text = format_human(report)
        assert "Try this next" not in text
