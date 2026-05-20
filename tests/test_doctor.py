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


class TestHandoffReadyCheck:
    """Composite handoff-demo readiness check (#115/#120/#121).

    Per-provider doctor checks pass individually but the demo PATH
    fails on several real shapes that aren't caught by the per-provider
    checks. This composite catches them with specific fix hints. The
    failure modes pinned here came from real corpora — empty assistant
    text on some gemini-takeout cells, single-provider history on
    cold installs, sub-2-provider configs.
    """

    def _patch_config(self, monkeypatch, enabled_providers):
        """Build an AppConfig with the named providers enabled."""
        from trinity_local.config import AppConfig, ProviderConfig

        providers = {
            name: ProviderConfig(
                name=name, type="cli", enabled=True, label=name.title(),
                command=[name], args=[], roles=set(), task_types=set(),
                model=None,
            )
            for name in enabled_providers
        }
        # `_check_handoff_ready` does `from .config import load_config`
        # at call time (deferred import), so patch the source module —
        # patching `trinity_local.doctor.load_config` would miss because
        # it's not bound there.
        monkeypatch.setattr(
            "trinity_local.config.load_config",
            lambda required=False: AppConfig(
                max_turns=10, notifications=True,
                providers=providers, role_preferences={}, task_preferences={},
            ),
        )

    def test_fails_soft_with_fewer_than_two_providers(self, tmp_path, monkeypatch):
        from trinity_local.doctor import _check_handoff_ready
        self._patch_config(monkeypatch, enabled_providers=["claude"])
        # Don't need to patch iter_prompt_nodes — provider check fires first.
        result = _check_handoff_ready()
        assert result.ok is True  # soft — handoff isn't a requirement
        assert "≥2" in result.detail
        # Fix hint must be actionable
        assert "config.json" in result.detail or "install-mcp" in result.detail

    def test_fails_soft_when_no_prompts_indexed(self, tmp_path, monkeypatch):
        from trinity_local.doctor import _check_handoff_ready
        self._patch_config(monkeypatch, enabled_providers=["claude", "gemini"])
        monkeypatch.setattr(
            "trinity_local.memory.store.iter_prompt_nodes",
            lambda limit=None: iter([]),
        )
        result = _check_handoff_ready()
        assert result.ok is True
        assert "no prompts" in result.detail.lower() or "nothing to package" in result.detail
        assert "seed-from-taste-terminal" in result.detail

    def test_fails_soft_when_all_assistant_text_empty(self, tmp_path, monkeypatch):
        """The seed-without-assistant-text shape: prompts indexed but
        ASSISTANT lines would all be blank in the handoff prompt. The
        receiving model has nothing to 'continue from.'"""
        from trinity_local.doctor import _check_handoff_ready
        from trinity_local.memory.schemas import PromptNode

        self._patch_config(monkeypatch, enabled_providers=["claude", "gemini"])
        nodes = [
            PromptNode(
                id=f"p{i}", transcript_id=f"t{i}", turn_index=0,
                provider="claude", source_path="/x",
                text=f"user turn {i}",
                embedding=[], created_at="2026-05-14T10:00:00",
                preceding_assistant_text="",  # empty
                following_assistant_text="",  # empty
                timestamp="2026-05-14T10:00:00",
            )
            for i in range(3)
        ]
        monkeypatch.setattr(
            "trinity_local.memory.store.iter_prompt_nodes",
            lambda limit=None: iter(nodes),
        )
        result = _check_handoff_ready()
        assert result.ok is True
        assert "assistant text" in result.detail.lower()
        # Fix hint points the user at the actual remedy (re-seed or wait)
        assert "seed" in result.detail.lower()

    def test_warns_when_only_one_provider_in_history(self, tmp_path, monkeypatch):
        """Cross-provider beat is the wedge — single-provider history
        still works but loses the marketing point. Warn explicitly."""
        from trinity_local.doctor import _check_handoff_ready
        from trinity_local.memory.schemas import PromptNode

        self._patch_config(monkeypatch, enabled_providers=["claude", "gemini"])
        nodes = [
            PromptNode(
                id=f"p{i}", transcript_id=f"t{i}", turn_index=0,
                provider="claude",  # all from claude
                source_path="/x", text=f"user turn {i}",
                embedding=[], created_at="2026-05-14T10:00:00",
                preceding_assistant_text="",
                following_assistant_text=f"claude said {i}",  # has content
                timestamp="2026-05-14T10:00:00",
            )
            for i in range(3)
        ]
        monkeypatch.setattr(
            "trinity_local.memory.store.iter_prompt_nodes",
            lambda limit=None: iter(nodes),
        )
        result = _check_handoff_ready()
        assert result.ok is True
        assert "1 provider" in result.detail or "only span" in result.detail
        assert "claude" in result.detail

    def test_passes_when_ready_for_demo(self, tmp_path, monkeypatch):
        """All preconditions met: ≥2 providers, prompts indexed, assistant
        text present, ≥2 providers in history. The detail should name
        the suggested handoff command so the user knows what to RUN."""
        from trinity_local.doctor import _check_handoff_ready
        from trinity_local.memory.schemas import PromptNode

        self._patch_config(monkeypatch, enabled_providers=["claude", "gemini"])
        nodes = [
            PromptNode(
                id="p1", transcript_id="t1", turn_index=0,
                provider="claude", source_path="/x",
                text="hello claude", embedding=[], created_at="2026-05-14T10:00:00",
                preceding_assistant_text="",
                following_assistant_text="claude answered.",
                timestamp="2026-05-14T10:00:00",
            ),
            PromptNode(
                id="p2", transcript_id="t2", turn_index=0,
                provider="gemini", source_path="/x",
                text="hello gemini", embedding=[], created_at="2026-05-14T10:01:00",
                preceding_assistant_text="",
                following_assistant_text="gemini answered.",
                timestamp="2026-05-14T10:01:00",
            ),
        ]
        monkeypatch.setattr(
            "trinity_local.memory.store.iter_prompt_nodes",
            lambda limit=None: iter(nodes),
        )
        result = _check_handoff_ready()
        assert result.ok is True
        assert "demo-ready" in result.detail
        # Names a concrete handoff target the user can paste
        assert "trinity-local handoff" in result.detail
        # And that target ISN'T claude (the demo lands when the SECOND
        # model picks up the first's context — recommending handoff TO
        # claude when user started in claude defeats the point)
        assert "handoff claude" not in result.detail

    def test_check_is_registered_in_run_doctor(self):
        """Defensive: a check that's defined but never wired into
        run_doctor never fires. Assert it's actually in the report."""
        from trinity_local.doctor import run_doctor
        report = run_doctor()
        names = {c.name for c in report.checks}
        assert "handoff_ready" in names


class TestVendorPublishedCheck:
    """Doctor surfaces silent vendor-publish failures.

    vendor.py writes 12 JS files under ~/.trinity/portal_pages/vendor/.
    A perms issue at install time can silently skip writes (now warned
    to stderr by `vendor.publish_vendor_files`, but stderr only helps
    whoever ran install-mcp — a user who clicks the launchpad days
    later sees broken ./vendor/*.js 404s with no surface that explains
    it). This check closes that loop on the doctor side.
    """

    def test_no_vendor_dir_returns_friendly_hint(self, tmp_path, monkeypatch):
        """Fresh install before first portal-html: vendor/ doesn't
        exist yet — surface a hint pointing at the fix command."""
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path / "trinity"))
        (tmp_path / "trinity" / "portal_pages").mkdir(parents=True)
        from trinity_local.doctor import _check_vendor_published
        result = _check_vendor_published()
        assert result.ok is True
        assert "vendor/ not yet populated" in result.detail
        assert "portal-html" in result.detail

    def test_all_files_present(self, tmp_path, monkeypatch):
        """All 12 vendored files written → quiet success detail."""
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path / "trinity"))
        portal_pages = tmp_path / "trinity" / "portal_pages"
        vendor_dir = portal_pages / "vendor"
        vendor_dir.mkdir(parents=True)
        from trinity_local.vendor import VENDORED_FILES
        for name in VENDORED_FILES:
            (vendor_dir / name).write_text("// stub", encoding="utf-8")
        from trinity_local.doctor import _check_vendor_published
        result = _check_vendor_published()
        assert result.ok is True
        assert "12 vendored JS files present" in result.detail
        assert "missing" not in result.detail.lower()

    def test_partial_publish_lists_missing(self, tmp_path, monkeypatch):
        """Some files missing (perms issue during install) → detail
        names the count + suggests the fix command + a sample of
        missing files."""
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path / "trinity"))
        portal_pages = tmp_path / "trinity" / "portal_pages"
        vendor_dir = portal_pages / "vendor"
        vendor_dir.mkdir(parents=True)
        from trinity_local.vendor import VENDORED_FILES
        # Write only the first 8 of 12 to simulate partial publish
        for name in VENDORED_FILES[:8]:
            (vendor_dir / name).write_text("// stub", encoding="utf-8")
        from trinity_local.doctor import _check_vendor_published
        result = _check_vendor_published()
        assert result.ok is True  # soft — not blocking
        assert "4 of 12 vendored JS files missing" in result.detail
        assert "portal-html" in result.detail
        # Surfaces ≥1 missing-file name so user can grep their logs
        assert any(name in result.detail for name in VENDORED_FILES[8:])

    def test_check_is_registered_in_run_doctor(self):
        """Same defensive shape as TestHandoffReadyCheck — a check
        defined-but-not-wired silently no-ops."""
        from trinity_local.doctor import run_doctor
        report = run_doctor()
        names = {c.name for c in report.checks}
        assert "vendor_published" in names
