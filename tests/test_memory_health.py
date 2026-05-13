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
    """All four signals fresh / never-built — issues list is empty."""

    def test_cold_install_has_no_issues(self, isolated_home):
        _memory_health = _import_health()
        result = _memory_health()
        assert result["issues"] == []
        # ok_count tracks healthy signals (total minus issues). With no
        # data at all every signal is in "empty" state → not surfaced.
        assert result["total_count"] == 4
        assert result["ok_count"] == 4


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
        # The actionable command must be the distill CLI — that's what
        # the click-to-copy chip needs to copy.
        assert core_issues[0]["command"] == "trinity-local distill"

    def test_core_missing_when_sources_exist(self, isolated_home):
        # Sources present but no distillation yet.
        (isolated_home / "memories" / "lens.md").write_text("some lens", encoding="utf-8")
        _memory_health = _import_health()
        issues = _memory_health()["issues"]
        core_issues = [i for i in issues if i["name"] == "core.md"]
        assert len(core_issues) == 1
        assert core_issues[0]["status"] == "missing"
        assert core_issues[0]["command"] == "trinity-local distill"


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
