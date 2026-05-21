"""Unit tests for launchpad_data._memory_health.

Smoke (Surfaces 15 + 16) covers the end-to-end render. These tests isolate
the per-signal logic so a fresh install / partial-data scenarios can't
regress without showing up — same shape as the basins regression test
that earned its place after the prompt_ids truncation bug in tick #5
(commit 4abdb41).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    """Empty TRINITY_HOME with the standard subdirs the health-check expects."""
    monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
    (tmp_path / "memories").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _import_health():
    """Lazy import so isolated_home's env var is set before module load."""
    from trinity_local.launchpad_data import _memory_health
    return _memory_health


class TestMemoryHealthEmptyState:
    """All five signals fresh / never-built — issues list is empty."""

    def test_cold_install_has_no_issues(self, isolated_home):
        _memory_health = _import_health()
        result = _memory_health()
        assert result["issues"] == []
        # ok_count tracks healthy signals (total minus issues). With no
        # data at all every signal is in "empty" state → not surfaced.
        assert result["total_count"] == 5
        assert result["ok_count"] == 5


class TestCoreStalenessSignal:
    """core.md stale relative to a source memory → surfaces as issue."""

    def test_core_stale_when_source_newer(self, isolated_home):
        import os, time

        core = isolated_home / "core.md"
        core.write_text("old distillation", encoding="utf-8")
        # Backdate so the source can be unambiguously newer
        old_mtime = time.time() - 10
        os.utime(core, (old_mtime, old_mtime))

        (isolated_home / "memories" / "lens.md").write_text("fresh lens", encoding="utf-8")
        # lens.md gets "now" mtime by default — newer than core

        _memory_health = _import_health()
        issues = _memory_health()["issues"]
        core_issues = [i for i in issues if i["name"] == "core.md"]
        assert len(core_issues) == 1
        assert core_issues[0]["status"] == "stale"
        # Actionable command flips to `dream` post-2026-05-18 (iter
        # #12): the standalone `distill` CLI was hidden in commit
        # c9b1f9d; dream Phase 5 is the live path that writes core.md.
        assert core_issues[0]["command"] == "trinity-local dream"

    def test_core_missing_when_sources_exist(self, isolated_home):
        # Sources present but no distillation yet — same `dream` flip.
        (isolated_home / "memories" / "lens.md").write_text("some lens", encoding="utf-8")
        _memory_health = _import_health()
        issues = _memory_health()["issues"]
        core_issues = [i for i in issues if i["name"] == "core.md"]
        assert len(core_issues) == 1
        assert core_issues[0]["status"] == "missing"
        assert core_issues[0]["command"] == "trinity-local dream"


class TestTopicsThreadAwareSignal:
    """Legacy per-turn topics.json (no thread_count) surfaces as upgrade prompt."""

    def test_pre_thread_aware_topics_surfaces(self, isolated_home):
        topics = isolated_home / "memories" / "topics.json"
        topics.write_text(
            json.dumps({
                "basins": [
                    {"id": "b00", "size": 100, "top_terms": [], "centroid": []},
                    {"id": "b01", "size": 50, "top_terms": [], "centroid": []},
                ]
            }),
            encoding="utf-8",
        )
        _memory_health = _import_health()
        issues = _memory_health()["issues"]
        topic_issues = [i for i in issues if i["name"] == "topics.json"]
        assert len(topic_issues) == 1
        assert topic_issues[0]["status"] == "pre-thread-aware"
        assert topic_issues[0]["command"] == "trinity-local lens-build"

    def test_thread_aware_topics_is_silent(self, isolated_home):
        topics = isolated_home / "memories" / "topics.json"
        topics.write_text(
            json.dumps({
                "basins": [
                    {"id": "b00", "size": 100, "thread_count": 20, "top_terms": [], "centroid": []},
                ]
            }),
            encoding="utf-8",
        )
        _memory_health = _import_health()
        issues = _memory_health()["issues"]
        assert not any(i["name"] == "topics.json" for i in issues)


class TestPicksOverrideSignal:
    """picks.json with rules where override_count > 0 → user-overrides issue."""

    def test_override_count_zero_is_silent(self, isolated_home, monkeypatch):
        # All rules unaltered by user — no override issue.
        monkeypatch.setattr(
            "trinity_local.launchpad_data._load_cortex_rules",
            lambda: {
                "rules": [
                    {"basin_id": "b00", "override_count": 0, "audit_status": "unaudited"},
                    {"basin_id": "b01", "override_count": 0, "audit_status": "unaudited"},
                ]
            },
        )
        _memory_health = _import_health()
        issues = _memory_health()["issues"]
        assert not any(i["name"] == "picks.json" and i["status"] == "user-overrides" for i in issues)

    def test_override_count_positive_surfaces(self, isolated_home, monkeypatch):
        monkeypatch.setattr(
            "trinity_local.launchpad_data._load_cortex_rules",
            lambda: {
                "rules": [
                    {"basin_id": "b00", "override_count": 2, "audit_status": "unaudited"},
                    {"basin_id": "b01", "override_count": 1, "audit_status": "unaudited"},
                    {"basin_id": "b02", "override_count": 0, "audit_status": "unaudited"},
                ]
            },
        )
        _memory_health = _import_health()
        issues = _memory_health()["issues"]
        override_issues = [
            i for i in issues if i["name"] == "picks.json" and i["status"] == "user-overrides"
        ]
        assert len(override_issues) == 1
        # The hint counts non-zero overrides — 2 of 3 rules above.
        assert "2 pick(s)" in override_issues[0]["hint"]
        # The action chip must point at the re-consolidate CLI.
        assert override_issues[0]["command"] == "trinity-local consolidate"


class TestPicksAuditSignal:
    """picks.json with rules where audit_status == "disagreed" → audit issue."""

    def test_audit_unaudited_is_silent(self, isolated_home, monkeypatch):
        # Rules exist but no audit has run — no disagreement to surface.
        monkeypatch.setattr(
            "trinity_local.launchpad_data._load_cortex_rules",
            lambda: {
                "rules": [
                    {"basin_id": "b00", "override_count": 0, "audit_status": "unaudited"},
                ]
            },
        )
        _memory_health = _import_health()
        issues = _memory_health()["issues"]
        assert not any(
            i["name"] == "picks.json" and i["status"] == "audit-disagreed" for i in issues
        )

    def test_audit_disagreed_surfaces(self, isolated_home, monkeypatch):
        monkeypatch.setattr(
            "trinity_local.launchpad_data._load_cortex_rules",
            lambda: {
                "rules": [
                    {"basin_id": "b00", "override_count": 0, "audit_status": "disagreed"},
                    {"basin_id": "b01", "override_count": 0, "audit_status": "agreed"},
                    {"basin_id": "b02", "override_count": 0, "audit_status": "disagreed"},
                ]
            },
        )
        _memory_health = _import_health()
        issues = _memory_health()["issues"]
        audit_issues = [
            i for i in issues if i["name"] == "picks.json" and i["status"] == "audit-disagreed"
        ]
        assert len(audit_issues) == 1
        assert "2 pick(s)" in audit_issues[0]["hint"]
        # Audit issue is an INSPECT action, not a re-run — href, not command.
        # Memory viewer is where the user reads the disagreement context.
        assert audit_issues[0].get("href") and "picks.json" in audit_issues[0]["href"]
        # No command on this issue — the surface intentionally drives the
        # user to inspect rather than blindly re-consolidate.
        assert not audit_issues[0].get("command")


class TestGracefulDegradation:
    """Per "Analytics never crash" in claude.md — malformed data must
    not propagate exceptions out of _memory_health."""

    def test_malformed_topics_json_does_not_crash(self, isolated_home):
        (isolated_home / "memories" / "topics.json").write_text("{not valid json", encoding="utf-8")
        _memory_health = _import_health()
        # Should return without raising; topics issue silently dropped
        result = _memory_health()
        # No topics issue should surface from malformed data — the try/except
        # in launchpad_data swallows the parse error
        assert not any(i["name"] == "topics.json" for i in result["issues"])

    def test_shape_invariants_hold_on_all_paths(self, isolated_home):
        """Result always has issues + ok_count + total_count as the schema
        the template expects. If any optional path drops a field, the
        v-if guards on the launchpad break silently."""
        _memory_health = _import_health()
        result = _memory_health()
        assert set(result.keys()) >= {"issues", "ok_count", "total_count"}
        assert isinstance(result["issues"], list)
        assert isinstance(result["ok_count"], int)
        assert isinstance(result["total_count"], int)
        # Sanity: counts add up
        assert result["ok_count"] + len(result["issues"]) == result["total_count"]


class TestIssueSchema:
    """Each issue carries the fields the launchpad template + memory viewer
    banner consume. A missing field would break rendering silently."""

    def test_issue_has_required_fields(self, isolated_home):
        # Force one issue to exist (legacy topics shape)
        (isolated_home / "memories" / "topics.json").write_text(
            json.dumps({"basins": [{"id": "b00", "size": 1, "top_terms": [], "centroid": []}]}),
            encoding="utf-8",
        )
        _memory_health = _import_health()
        issues = _memory_health()["issues"]
        assert issues, "fixture should produce at least one issue"
        issue = issues[0]
        # Template's v-for reads name, status, hint, and either command or href
        for field in ("name", "status", "hint"):
            assert field in issue, f"issue missing required field: {field}"
        # Either command (click-to-copy chip) or href (inspect link) must be present
        assert issue.get("command") or issue.get("href"), (
            "issue must expose either a command for copy or an href for navigation"
        )


class TestCortexFreshnessSignal:
    """5th signal (tick #106): picks.json is stale if any council outcome
    on disk is newer than the freshest consolidated_at. The doctor's
    `_check_cortex_freshness` mirrors this check from the CLI side; both
    must compute the same result so the user gets consistent signal
    whether they look at the launchpad or run `doctor`.

    The real-corpus motivation: tick #106's doctor run showed `7 of 19
    councils are newer than the last consolidate` — 7 verdicts worth of
    routing signal that `ask` was ignoring because picks.json hadn't
    been refreshed. The launchpad surfaced 0 of those issues until
    this signal landed.
    """

    def test_no_issue_when_no_picks_file(self, isolated_home):
        # No picks.json → empty-state, but cortex freshness shouldn't
        # spuriously fire either. Test guards against "no picks means
        # everything is newer than [missing timestamp]".
        _memory_health = _import_health()
        issues = _memory_health()["issues"]
        assert not any(
            i.get("name") == "picks.json" and i.get("status") == "cortex-stale"
            for i in issues
        )

    def test_no_issue_when_picks_newer_than_all_outcomes(self, isolated_home):
        """picks.json was consolidated after every outcome → fresh."""
        from trinity_local.state_paths import picks_path, council_outcomes_dir
        # Outcome from 2026-01-01 — old
        outcomes_dir = council_outcomes_dir()
        (outcomes_dir / "council_old.json").write_text(
            json.dumps({"created_at": "2026-01-01T00:00:00"}), encoding="utf-8"
        )
        # picks consolidated 2026-05-01 — newer than the outcome
        picks_path().write_text(
            json.dumps({
                "general": {"consolidated_at": "2026-05-01T00:00:00", "rules": []},
            }),
            encoding="utf-8",
        )
        _memory_health = _import_health()
        issues = _memory_health()["issues"]
        cortex_issues = [
            i for i in issues
            if i.get("name") == "picks.json" and i.get("status") == "cortex-stale"
        ]
        assert not cortex_issues, f"unexpected cortex-stale issue: {cortex_issues}"

    def test_surfaces_when_outcomes_newer_than_picks(self, isolated_home):
        """The Pillar 4 case: user just rated a fresh council, the
        outcome JSON timestamp beats the picks consolidated_at, and
        the launchpad must tell them `ask` is now routing on stale data."""
        from trinity_local.state_paths import picks_path, council_outcomes_dir
        outcomes_dir = council_outcomes_dir()
        # picks consolidated 2026-01-01
        picks_path().write_text(
            json.dumps({
                "general": {"consolidated_at": "2026-01-01T00:00:00", "rules": []},
            }),
            encoding="utf-8",
        )
        # Three outcomes after consolidation (e.g., from "rate the last
        # three councils" backlog session)
        for i, ts in enumerate(["2026-05-01", "2026-05-02", "2026-05-03"]):
            (outcomes_dir / f"council_{i:02d}.json").write_text(
                json.dumps({"created_at": f"{ts}T12:00:00"}), encoding="utf-8"
            )
        _memory_health = _import_health()
        result = _memory_health()
        cortex_issues = [
            i for i in result["issues"]
            if i.get("name") == "picks.json" and i.get("status") == "cortex-stale"
        ]
        assert len(cortex_issues) == 1
        issue = cortex_issues[0]
        assert "3 council(s) newer" in issue["hint"], (
            f"hint should report the outcome count; got: {issue['hint']}"
        )
        # Click-to-copy command for re-consolidation
        assert issue["command"] == "trinity-local consolidate"

    def test_malformed_picks_json_does_not_crash(self, isolated_home):
        """Per "Analytics never crash" — a broken picks.json must not
        propagate exceptions from _memory_health."""
        from trinity_local.state_paths import picks_path
        picks_path().write_text("{not valid json", encoding="utf-8")
        _memory_health = _import_health()
        # Should return without raising
        result = _memory_health()
        # No cortex-stale issue surfaces from malformed data
        assert not any(
            i.get("name") == "picks.json" and i.get("status") == "cortex-stale"
            for i in result["issues"]
        )


class TestRefreshMemoryButton:
    """The 'Refresh memory' button on the Memory Health card.

    Earned by council_1f9cbecd7104f90f priority #3 (2026-05-21). The
    council's explicit verdict on auto-running dream: "User's intent is
    'don't make me open a terminal' — not 'run LLM calls without my
    knowledge.' Dream is expensive and surprising. A single button
    labeled 'Refresh memory' that shows a spinner and then 'Updated'
    satisfies the intent."

    Three invariants this guards:
      1. capture_host.ACTION_ALLOWLIST has a `dream` entry (otherwise the
         Chrome extension dispatch path silently no-ops, same shape as
         the refine-button bug fixed in `abf923c`).
      2. The launchpad template renders the button + dispatches via
         `__TRINITY_DISPATCH__` (the canonical post-Shortcut path).
      3. The button is INSIDE the memory-health-card v-if so it can't
         render on installs where the health card is hidden.
    """

    def test_dream_in_action_allowlist(self):
        """The Chrome extension dispatch path requires an allowlist
        entry — without it `_run_action` rejects the kind. Same shape
        as the missing `council-iterate` entry that silently killed
        the refine button (commit abf923c)."""
        from trinity_local.capture_host import ACTION_ALLOWLIST
        assert "dream" in ACTION_ALLOWLIST, (
            "Memory Health 'Refresh memory' button dispatches kind='dream' — "
            "without an ACTION_ALLOWLIST entry capture_host rejects it."
        )
        entry = ACTION_ALLOWLIST["dream"]
        # Tuple shape: (cli_subcommand, arg_spec, [constant_flags]).
        # No required args — `trinity-local dream` with defaults is
        # what "Refresh memory" means.
        assert entry[0] == "dream"
        assert entry[1] == [], (
            "dream entry should declare no arg-spec — the launchpad "
            "fires it with defaults; any required field would make "
            "the button error on click."
        )

    def test_refresh_memory_button_renders_in_health_card(self):
        """The button + its state machine must be wired into the
        memory-health-card section. Verifies the button label, the
        three transient states (running/done/failed), the Vue method
        ref, and the extensionAction kind."""
        from trinity_local.launchpad_template import render_launchpad_html
        html = render_launchpad_html(
            page_data={
                "memoryHealth": {
                    "issues": [{
                        "name": "lens.md",
                        "status": "STALE",
                        "hint": "Hasn't been refreshed in a week",
                    }],
                    "ok_count": 3,
                    "total_count": 4,
                }
            },
            recent_cards="",
        )
        # Button label (idle)
        assert "Refresh memory" in html, "button label missing"
        # State machine transitions
        assert "Refreshing" in html, "running-state label missing"
        assert "Updated" in html, "done-state label missing"
        assert "Failed" in html, "failed-state label missing"
        # Vue plumbing
        assert "@click=\"refreshMemory\"" in html, "click handler missing"
        assert "refreshMemoryStatus" in html, "state field missing"
        # Dispatch path — Chrome extension, not the retired shortcuts://
        assert "kind: 'dream'" in html, "extensionAction kind missing"
        # Button MUST sit inside the memory-health-card v-if so it doesn't
        # render when there are no issues — guards against a future
        # refactor that hoists the button into a section that always
        # renders, which would resurrect the auto-fire pressure the
        # council explicitly rejected. The first `memory-health-card`
        # substring lives in SHARED_CSS, so anchor on the actual
        # <section class="card memory-health-card" v-if=...> opener.
        card_start = html.index('<section class="card memory-health-card"')
        card_end = html.index("</section>", card_start)
        button_pos = html.index("Refresh memory", card_start)
        assert button_pos < card_end, (
            "'Refresh memory' button must render inside memory-health-card; "
            "hoisting it outside the v-if would surface it on installs "
            "with no health issues, contradicting the council's rejection "
            "of auto-fire / always-on dream surfacing."
        )
