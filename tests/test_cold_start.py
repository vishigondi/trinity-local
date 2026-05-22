"""Tests for cold-start auto-scan of local CLI transcripts.

On first MCP spawn, if the corpus is empty and at least one local CLI
source dir exists, kick a background scan so the first council already
has personalization signal. The wow-flow gap closer (see CLAUDE.md
forward arc).
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import pytest


@pytest.fixture
def isolated_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
    return tmp_path


@pytest.fixture
def autoscan_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """Opt back into the cold-start path inside this test."""
    monkeypatch.delenv("TRINITY_AUTOSCAN_DISABLED", raising=False)


def _stub_one_source_available(monkeypatch: pytest.MonkeyPatch, source: str = "claude") -> None:
    """Bypass real-home detection — return one source as 'available'."""
    monkeypatch.setattr(
        "trinity_local.cold_start.detect_available_sources",
        lambda: [source],
    )


class TestIsColdStart:
    def test_false_when_autoscan_disabled(self, isolated_home):
        # Default fixture sets TRINITY_AUTOSCAN_DISABLED=1
        from trinity_local.cold_start import is_cold_start
        assert is_cold_start() is False

    def test_false_when_state_file_exists(self, isolated_home, autoscan_enabled, monkeypatch):
        from trinity_local.cold_start import is_cold_start, cold_start_state_path
        _stub_one_source_available(monkeypatch)
        cold_start_state_path().parent.mkdir(parents=True, exist_ok=True)
        cold_start_state_path().write_text('{"status": "complete"}', encoding="utf-8")
        assert is_cold_start() is False

    def test_false_when_corpus_already_populated(self, isolated_home, autoscan_enabled, monkeypatch):
        from trinity_local.cold_start import is_cold_start
        from trinity_local.memory import upsert_prompt_node
        from trinity_local.memory.schemas import PromptNode

        _stub_one_source_available(monkeypatch)
        upsert_prompt_node(PromptNode(
            id="p1", transcript_id="t", provider="claude", source_path="/x",
            turn_index=0, text="hi", embedding=[], created_at="2026-05-15T00:00:00Z",
            following_assistant_text="",
        ))
        assert is_cold_start() is False

    def test_false_when_no_sources_available(self, isolated_home, autoscan_enabled, monkeypatch):
        from trinity_local.cold_start import is_cold_start
        monkeypatch.setattr(
            "trinity_local.cold_start.detect_available_sources", lambda: [],
        )
        assert is_cold_start() is False

    def test_true_when_empty_corpus_and_source_present(self, isolated_home, autoscan_enabled, monkeypatch):
        from trinity_local.cold_start import is_cold_start
        _stub_one_source_available(monkeypatch)
        assert is_cold_start() is True


class TestDetectAvailableSources:
    def test_picks_up_claude_dir_with_session_file(self, tmp_path, monkeypatch):
        from trinity_local import cold_start

        fake_home = tmp_path / "fake_home"
        claude_dir = fake_home / ".claude" / "projects" / "my-proj"
        claude_dir.mkdir(parents=True)
        (claude_dir / "session-1.jsonl").write_text("{}\n", encoding="utf-8")
        monkeypatch.setattr("trinity_local.watch_runtime.Path.home", lambda: fake_home)

        assert "claude" in cold_start.detect_available_sources()

    def test_skips_empty_dir(self, tmp_path, monkeypatch):
        from trinity_local import cold_start

        fake_home = tmp_path / "fake_home"
        (fake_home / ".claude" / "projects").mkdir(parents=True)  # exists, empty
        monkeypatch.setattr("trinity_local.watch_runtime.Path.home", lambda: fake_home)

        # No file matching *.jsonl → not picked up
        assert "claude" not in cold_start.detect_available_sources()


class TestKickColdStartScan:
    def test_returns_none_when_not_cold_start(self, isolated_home):
        from trinity_local.cold_start import kick_cold_start_scan
        # Default autoscan-disabled fixture means is_cold_start False
        assert kick_cold_start_scan() is None

    def test_spawns_thread_and_writes_initial_state(self, isolated_home, autoscan_enabled, monkeypatch):
        from trinity_local.cold_start import kick_cold_start_scan, read_state

        _stub_one_source_available(monkeypatch)

        # Stub ingest_recent to a fast no-op so the thread settles quickly.
        from trinity_local.incremental_ingest import IngestResult
        monkeypatch.setattr(
            "trinity_local.incremental_ingest.ingest_recent",
            lambda **kwargs: IngestResult(added=42, scanned=7, sources=kwargs.get("sources", [])),
        )

        initial = kick_cold_start_scan(deadline_s=1.0)
        assert initial is not None
        # Either still in_progress (thread racing) or already complete.
        assert initial["status"] in ("in_progress", "complete")
        assert initial["sources_detected"] == ["claude"]

        # Let the thread finish.
        for _ in range(50):
            state = read_state()
            if state and state["status"] in ("complete", "failed"):
                break
            time.sleep(0.02)

        final = read_state()
        assert final["status"] == "complete"
        assert final["added"] == 42
        assert final["scanned"] == 7
        assert final["sources_detected"] == ["claude"]
        assert final["finished_at"] is not None

    def test_failed_status_when_ingest_raises(self, isolated_home, autoscan_enabled, monkeypatch):
        from trinity_local.cold_start import kick_cold_start_scan, read_state

        _stub_one_source_available(monkeypatch)

        def _boom(**kwargs):
            raise RuntimeError("simulated parser breakage")
        monkeypatch.setattr("trinity_local.incremental_ingest.ingest_recent", _boom)

        kick_cold_start_scan(deadline_s=1.0)
        for _ in range(50):
            state = read_state()
            if state and state["status"] in ("complete", "failed"):
                break
            time.sleep(0.02)

        final = read_state()
        assert final["status"] == "failed"
        assert "simulated parser breakage" in (final.get("error") or "")

    def test_state_file_written_synchronously_before_thread_starts(
        self, isolated_home, autoscan_enabled, monkeypatch,
    ):
        """Cross-process race guard: when two MCP servers (e.g. Claude
        Code + Codex CLI + Antigravity + Cursor) start at session-load
        and each calls is_cold_start() simultaneously, only one should
        actually spawn a scan thread. The serialization point is the
        on-disk state file. This test asserts kick_cold_start_scan
        writes the in_progress state SYNCHRONOUSLY (before returning
        from the parent thread), so the second simultaneous caller's
        is_cold_start() check fails on the state-file-exists branch.

        Previous behavior wrote state inside the daemon thread body
        and polled for it to appear (~200ms window for the race).
        Now the parent writes synchronously, then spawns the thread.
        """
        from trinity_local.cold_start import (
            kick_cold_start_scan, cold_start_state_path, is_cold_start,
        )

        _stub_one_source_available(monkeypatch)

        # Block ingest_recent so the daemon thread sleeps forever —
        # this lets us inspect state immediately after kick returns
        # without races on test thread vs daemon thread.
        import threading
        block = threading.Event()
        monkeypatch.setattr(
            "trinity_local.incremental_ingest.ingest_recent",
            lambda **kw: (block.wait(), None)[1],
        )
        try:
            initial = kick_cold_start_scan(deadline_s=1.0)
            # The function returned — state file MUST be on disk now.
            assert cold_start_state_path().exists(), (
                "kick_cold_start_scan returned but state file not yet "
                "written — race window still open for second caller"
            )
            # And is_cold_start() must now return False (the
                # short-circuit the race fix relies on).
            assert is_cold_start() is False, (
                "is_cold_start() still True after kick_cold_start_scan "
                "returned — second caller would spawn a duplicate scan"
            )
            assert initial is not None
            assert initial["status"] == "in_progress"
        finally:
            block.set()

    def test_idempotent_when_state_file_already_present(self, isolated_home, autoscan_enabled, monkeypatch):
        """Once a scan has run (state file present), a second kick is a
        no-op — we don't re-scan transcripts already covered by the
        cursor."""
        from trinity_local.cold_start import (
            kick_cold_start_scan, cold_start_state_path,
        )

        _stub_one_source_available(monkeypatch)
        cold_start_state_path().parent.mkdir(parents=True, exist_ok=True)
        cold_start_state_path().write_text(json.dumps({
            "status": "complete", "started_at": "x", "finished_at": "y",
            "sources_detected": ["claude"], "added": 100, "scanned": 5,
            "deadline_s": 300,
        }), encoding="utf-8")

        # Should NOT spawn a second scan.
        called = []
        monkeypatch.setattr(
            "trinity_local.incremental_ingest.ingest_recent",
            lambda **kw: called.append(True) or None,
        )
        result = kick_cold_start_scan()
        assert result is None
        assert called == []


class TestColdStartHint:
    def test_none_when_no_state_file(self, isolated_home):
        from trinity_local.cold_start import cold_start_hint
        assert cold_start_hint() is None

    @pytest.mark.xfail(
        os.environ.get("CI") == "true" and sys.platform == "darwin",
        reason="Known macOS GitHub Actions runner flake: atomic-rename of pytest tmp_path file occasionally hits FileNotFoundError on the source tmp (APFS / sandbox interaction). Test passes on darwin dev + ubuntu-latest CI. Investigate post-launch.",
        strict=False,
    )
    def test_in_progress_message(self, isolated_home):
        from trinity_local.cold_start import cold_start_hint, _write_state

        _write_state({
            "status": "in_progress",
            "started_at": "2026-05-15T00:00:00+00:00",
            "finished_at": None,
            "sources_detected": ["claude", "codex"],
            "added": 12,
            "scanned": 3,
            "deadline_s": 300,
        })
        hint = cold_start_hint()
        assert hint["status"] == "in_progress"
        assert "ingesting your local CLI history" in hint["message"]
        assert "claude" in hint["message"]
        assert "codex" in hint["message"]
        assert hint["added_so_far"] == 12

    def test_complete_message_within_fresh_window(self, isolated_home):
        from trinity_local.cold_start import cold_start_hint, _write_state
        from trinity_local.utils import now_iso

        _write_state({
            "status": "complete",
            "started_at": now_iso(),
            "finished_at": now_iso(),
            "sources_detected": ["claude"],
            "added": 4521,
            "scanned": 38,
            "deadline_s": 300,
        })
        hint = cold_start_hint()
        assert hint["status"] == "complete"
        assert "4521" in hint["message"]

    def test_complete_silent_after_fresh_window(self, isolated_home):
        from trinity_local.cold_start import cold_start_hint, _write_state

        _write_state({
            "status": "complete",
            "started_at": "2020-01-01T00:00:00+00:00",
            "finished_at": "2020-01-01T00:01:00+00:00",  # ancient
            "sources_detected": ["claude"],
            "added": 1,
            "scanned": 1,
            "deadline_s": 300,
        })
        assert cold_start_hint() is None

    def test_failed_status_surfaces_with_retry_command(self, isolated_home):
        from trinity_local.cold_start import cold_start_hint, _write_state
        from trinity_local.utils import now_iso

        _write_state({
            "status": "failed",
            "started_at": now_iso(),
            "finished_at": now_iso(),
            "sources_detected": ["claude"],
            "added": 0,
            "scanned": 0,
            "deadline_s": 300,
            "error": "ParserError: bad file",
        })
        hint = cold_start_hint()
        assert hint["status"] == "failed"
        assert "seed-from-taste-terminal" in hint["message"]


class TestMcpResponseInjection:
    """Surface 34 (sub-test): MCP `_text()` helper injects the cold_start
    hint into structured responses when a scan is fresh."""

    def test_text_helper_injects_hint_when_present(self, isolated_home):
        from trinity_local.mcp_server import _text
        from trinity_local.cold_start import _write_state
        from trinity_local.utils import now_iso

        _write_state({
            "status": "in_progress",
            "started_at": now_iso(),
            "finished_at": None,
            "sources_detected": ["claude"],
            "added": 3,
            "scanned": 1,
            "deadline_s": 300,
        })
        wrapped = _text({"ok": True, "foo": "bar"})
        body = json.loads(wrapped["text"])
        assert body["ok"] is True
        assert body["foo"] == "bar"
        assert body["cold_start"]["status"] == "in_progress"

    def test_text_helper_does_not_inject_when_no_scan(self, isolated_home):
        from trinity_local.mcp_server import _text

        wrapped = _text({"ok": True})
        body = json.loads(wrapped["text"])
        assert "cold_start" not in body

    def test_text_helper_passthrough_for_strings(self, isolated_home):
        from trinity_local.mcp_server import _text

        wrapped = _text("plain string body")
        assert wrapped["text"] == "plain string body"
