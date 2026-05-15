"""Tests for ``_check_browser_capture`` — the v1.6 doctor preflight.

Four stages (first failure wins). All SOFT (ok=True) so the check
never breaks the doctor for users who don't use browser captures.
"""

from __future__ import annotations

import os
import time

import pytest

from trinity_local.doctor import _check_browser_capture


@pytest.fixture
def isolated_trinity_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
    return tmp_path


def test_check_is_always_soft(isolated_trinity_home, monkeypatch):
    """The check must never set ok=False — the extension is optional
    and users may be CLI-only."""
    # Force the most-failing state (no host on PATH).
    monkeypatch.setattr("trinity_local.doctor.shutil.which", lambda _: None)
    result = _check_browser_capture()
    assert result.ok is True
    assert result.name == "browser_capture"


def test_stage_1_no_host_on_path(isolated_trinity_home, monkeypatch):
    monkeypatch.setattr("trinity_local.doctor.shutil.which", lambda _: None)
    result = _check_browser_capture()
    assert "not on PATH" in result.detail
    assert "pip install" in result.detail


def test_stage_2_host_present_but_manifest_missing(isolated_trinity_home, tmp_path, monkeypatch):
    """Host installed, but Chrome's Native Messaging manifest hasn't
    been written. install-extension --extension-id <ID> is the fix."""
    monkeypatch.setattr("trinity_local.doctor.shutil.which", lambda _: "/usr/local/bin/trinity-local-capture-host")
    # Point manifest path to a non-existent file by redirecting Home.
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()
    monkeypatch.setattr("trinity_local.doctor.Path.home", classmethod(lambda cls: fake_home))

    result = _check_browser_capture()
    assert "Native Messaging manifest not written" in result.detail
    assert "install-extension" in result.detail


def _write_macos_manifest(home_dir):
    """Drop a fake Native Messaging manifest at the macOS path so
    Stage 2 passes."""
    manifest_dir = home_dir / "Library" / "Application Support" / "Google" / "Chrome" / "NativeMessagingHosts"
    manifest_dir.mkdir(parents=True)
    (manifest_dir / "local.trinity.capture.json").write_text("{}")


def test_stage_3_manifest_present_but_no_captures(isolated_trinity_home, tmp_path, monkeypatch):
    monkeypatch.setattr("trinity_local.doctor.shutil.which", lambda _: "/usr/local/bin/trinity-local-capture-host")
    import sys
    monkeypatch.setattr(sys, "platform", "darwin")
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()
    _write_macos_manifest(fake_home)
    monkeypatch.setattr("trinity_local.doctor.Path.home", classmethod(lambda cls: fake_home))

    result = _check_browser_capture()
    assert "no captures yet" in result.detail
    assert "chrome://extensions" in result.detail


def test_stage_4_stale_when_last_capture_older_than_24h(isolated_trinity_home, tmp_path, monkeypatch):
    monkeypatch.setattr("trinity_local.doctor.shutil.which", lambda _: "/usr/local/bin/trinity-local-capture-host")
    import sys
    monkeypatch.setattr(sys, "platform", "darwin")
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()
    _write_macos_manifest(fake_home)
    monkeypatch.setattr("trinity_local.doctor.Path.home", classmethod(lambda cls: fake_home))

    capture_dir = isolated_trinity_home / "conversations" / "claude"
    capture_dir.mkdir(parents=True)
    old = capture_dir / "old.json"
    old.write_text("{}")
    two_days_ago = time.time() - 2 * 86400
    os.utime(old, (two_days_ago, two_days_ago))

    result = _check_browser_capture()
    assert "but newest is" in result.detail
    assert "h old" in result.detail


def test_stage_4_fresh_captures_report_count_and_age(isolated_trinity_home, tmp_path, monkeypatch):
    monkeypatch.setattr("trinity_local.doctor.shutil.which", lambda _: "/usr/local/bin/trinity-local-capture-host")
    import sys
    monkeypatch.setattr(sys, "platform", "darwin")
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()
    _write_macos_manifest(fake_home)
    monkeypatch.setattr("trinity_local.doctor.Path.home", classmethod(lambda cls: fake_home))

    capture_dir = isolated_trinity_home / "conversations" / "claude"
    capture_dir.mkdir(parents=True)
    (capture_dir / "fresh.json").write_text("{}")
    (capture_dir / "fresher.json").write_text("{}")

    result = _check_browser_capture()
    assert "2 captures" in result.detail
    assert "newest" in result.detail


def test_excludes_stream_sidecar_files_from_count(isolated_trinity_home, tmp_path, monkeypatch):
    """The user-facing count must match Surface 33's count — both
    skip ``.stream.json`` adapter outputs."""
    monkeypatch.setattr("trinity_local.doctor.shutil.which", lambda _: "/usr/local/bin/trinity-local-capture-host")
    import sys
    monkeypatch.setattr(sys, "platform", "darwin")
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()
    _write_macos_manifest(fake_home)
    monkeypatch.setattr("trinity_local.doctor.Path.home", classmethod(lambda cls: fake_home))

    capture_dir = isolated_trinity_home / "conversations" / "claude"
    capture_dir.mkdir(parents=True)
    (capture_dir / "conv.json").write_text("{}")
    (capture_dir / "conv.stream.json").write_text("{}")  # NOT counted

    result = _check_browser_capture()
    assert "1 captures" in result.detail


def test_excludes_raw_stream_prefix_files_from_count(isolated_trinity_home, tmp_path, monkeypatch):
    """Raw-stream fallback files (``stream-<urlhash>.json`` from
    capture_host's no-adapter path) don't count either. Currently
    relevant for the gemini.google.com path — gemini.js adapter is
    deferred to v1.7, so gemini captures land as raw stream files.
    Doctor stage 3 must not pretend those are real conversations.
    """
    import sys
    monkeypatch.setattr("trinity_local.doctor.shutil.which", lambda _: "/usr/local/bin/trinity-local-capture-host")
    monkeypatch.setattr(sys, "platform", "darwin")
    fake_home = tmp_path / "fake_home"
    fake_home.mkdir()
    _write_macos_manifest(fake_home)
    monkeypatch.setattr("trinity_local.doctor.Path.home", classmethod(lambda cls: fake_home))

    gemini_dir = isolated_trinity_home / "conversations" / "gemini"
    gemini_dir.mkdir(parents=True)
    (gemini_dir / "stream-abc.json").write_text("{}")
    (gemini_dir / "stream-def.json").write_text("{}")
    (gemini_dir / "stream-789.json").write_text("{}")

    result = _check_browser_capture()
    # 3 raw-stream files → "no captures yet" because none are
    # user-facing conversations.
    assert "no captures yet" in result.detail


def test_unsupported_platform_skips_with_note(isolated_trinity_home, monkeypatch):
    import sys
    monkeypatch.setattr("trinity_local.doctor.shutil.which", lambda _: "/usr/local/bin/trinity-local-capture-host")
    monkeypatch.setattr(sys, "platform", "win32")
    result = _check_browser_capture()
    assert result.ok is True
    assert "macOS/Linux" in result.detail


def test_run_doctor_includes_browser_capture_check():
    """Regression guard: ``run_doctor()`` must include the new check
    in its sequence. If anyone removes the append call the check is
    silently missing from `trinity-local doctor` output."""
    from trinity_local.doctor import run_doctor

    # Don't care about pass/fail of the actual check here — just that
    # it ran (the name is in the report).
    report = run_doctor()
    names = [c.name for c in report.checks]
    assert "browser_capture" in names, (
        f"browser_capture missing from run_doctor() sequence; got {names}"
    )
