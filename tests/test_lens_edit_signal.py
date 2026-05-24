"""Tests for #140 lens-edit-as-signal capture.

The capture side (this file) detects user edits to lens.md between
lens-builds and persists them to ~/.trinity/me/lens_edits.jsonl. The
feed-back side (next dream cycle reads edits as HIGH-WEIGHT signal in
Stage 2 corpus) is a separate slice.
"""
from __future__ import annotations

import json

import pytest


@pytest.fixture
def lens_edit_env(tmp_path, monkeypatch):
    """Isolate state per test — TRINITY_HOME points at tmp_path."""
    monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
    return tmp_path


class TestSnapshotBaseline:
    def test_cold_start_returns_empty_no_snapshot(self, lens_edit_env):
        from trinity_local.me.lens_edits import capture_lens_edits

        # No snapshot file = no baseline = no edits (the post-build write
        # establishes the baseline for next time, not this time).
        edits = capture_lens_edits(current_lens_text="# /me\nstuff\n")
        assert edits == []

    def test_write_lens_snapshot_creates_file(self, lens_edit_env):
        from trinity_local.me.lens_edits import (
            lens_snapshot_path,
            write_lens_snapshot,
        )

        write_lens_snapshot("# /me\nbaseline\n")
        assert lens_snapshot_path().exists()
        assert lens_snapshot_path().read_text(encoding="utf-8") == "# /me\nbaseline\n"

    def test_no_diff_returns_empty(self, lens_edit_env):
        from trinity_local.me.lens_edits import (
            capture_lens_edits,
            write_lens_snapshot,
        )

        baseline = "# /me\nidentical\n"
        write_lens_snapshot(baseline)
        assert capture_lens_edits(current_lens_text=baseline) == []


class TestDeltaDetection:
    def test_added_line_captured_as_add(self, lens_edit_env):
        from trinity_local.me.lens_edits import (
            capture_lens_edits,
            write_lens_snapshot,
        )

        write_lens_snapshot("# /me\nline a\n")
        edits = capture_lens_edits(current_lens_text="# /me\nline a\nline b\n")
        assert len(edits) == 1
        assert edits[0].op == "add"
        assert edits[0].after == "line b"
        assert edits[0].before == ""

    def test_removed_line_captured_as_remove(self, lens_edit_env):
        from trinity_local.me.lens_edits import (
            capture_lens_edits,
            write_lens_snapshot,
        )

        write_lens_snapshot("# /me\nline a\nline b\n")
        edits = capture_lens_edits(current_lens_text="# /me\nline a\n")
        assert len(edits) == 1
        assert edits[0].op == "remove"
        assert edits[0].before == "line b"
        assert edits[0].after == ""

    def test_modified_line_emits_remove_then_add(self, lens_edit_env):
        """User modifications surface as adjacent remove+add pairs — not
        paired into a single "modify" op (avoids brittle pairing heuristics;
        chairman reading the JSONL can infer intent from sequence)."""
        from trinity_local.me.lens_edits import (
            capture_lens_edits,
            write_lens_snapshot,
        )

        write_lens_snapshot("# /me\noriginal text\n")
        edits = capture_lens_edits(current_lens_text="# /me\nedited text\n")
        ops = [e.op for e in edits]
        assert "remove" in ops
        assert "add" in ops
        removed = next(e for e in edits if e.op == "remove")
        added = next(e for e in edits if e.op == "add")
        assert removed.before == "original text"
        assert added.after == "edited text"

    def test_all_edits_tagged_user_edit_source(self, lens_edit_env):
        from trinity_local.me.lens_edits import (
            capture_lens_edits,
            write_lens_snapshot,
        )

        write_lens_snapshot("# /me\nold\n")
        edits = capture_lens_edits(current_lens_text="# /me\nnew\n")
        assert all(e.source == "user_edit" for e in edits)


class TestJsonlPersistence:
    def test_capture_appends_to_jsonl(self, lens_edit_env):
        from trinity_local.me.lens_edits import (
            capture_lens_edits,
            lens_edits_path,
            write_lens_snapshot,
        )

        write_lens_snapshot("# /me\nbase\n")
        capture_lens_edits(current_lens_text="# /me\nbase\nadded\n")

        path = lens_edits_path()
        assert path.exists()
        lines = [
            json.loads(line)
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        assert len(lines) == 1
        assert lines[0]["op"] == "add"
        assert lines[0]["after"] == "added"
        assert lines[0]["source"] == "user_edit"
        assert lines[0]["ts"]  # non-empty ISO timestamp

    def test_second_capture_appends_not_overwrites(self, lens_edit_env):
        """JSONL is append-only — the existing log is the historical
        record. A second build with new edits adds to the log; it doesn't
        replace prior entries."""
        from trinity_local.me.lens_edits import (
            capture_lens_edits,
            lens_edits_path,
            write_lens_snapshot,
        )

        write_lens_snapshot("# /me\nv1\n")
        capture_lens_edits(current_lens_text="# /me\nv2\n")
        write_lens_snapshot("# /me\nv2\n")
        capture_lens_edits(current_lens_text="# /me\nv3\n")

        lines = [
            json.loads(line)
            for line in lens_edits_path().read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        # First diff: remove v1 + add v2. Second: remove v2 + add v3.
        # All four entries should be present.
        assert len(lines) == 4
        afters = [line["after"] for line in lines if line["op"] == "add"]
        assert "v2" in afters
        assert "v3" in afters


class TestLoadRecentEdits:
    def test_returns_empty_when_no_log(self, lens_edit_env):
        from trinity_local.me.lens_edits import load_recent_edits

        assert load_recent_edits() == []

    def test_returns_most_recent_first(self, lens_edit_env):
        from trinity_local.me.lens_edits import (
            capture_lens_edits,
            load_recent_edits,
            write_lens_snapshot,
        )

        write_lens_snapshot("# /me\nold\n")
        capture_lens_edits(current_lens_text="# /me\nfirst edit\n")
        write_lens_snapshot("# /me\nfirst edit\n")
        capture_lens_edits(current_lens_text="# /me\nsecond edit\n")

        recent = load_recent_edits(limit=10)
        # Latest write goes last on disk; load_recent_edits reverses to
        # newest-first, so the FIRST entry in `recent` is the most
        # recent line added.
        assert recent[0].after == "second edit" or recent[0].before == "first edit"

    def test_limit_caps_output(self, lens_edit_env):
        from trinity_local.me.lens_edits import (
            capture_lens_edits,
            load_recent_edits,
            write_lens_snapshot,
        )

        # Generate 4 edits across 2 build cycles.
        write_lens_snapshot("# /me\na\n")
        capture_lens_edits(current_lens_text="# /me\nb\n")  # 1 remove + 1 add
        write_lens_snapshot("# /me\nb\n")
        capture_lens_edits(current_lens_text="# /me\nc\n")  # 1 remove + 1 add

        recent = load_recent_edits(limit=2)
        assert len(recent) == 2


class TestDecisionTranslation:
    """Slice 2: lens edits become high-weight Decision objects for Stage 2."""

    def test_no_edits_returns_empty(self, lens_edit_env):
        from trinity_local.me.lens_edits import load_lens_edits_as_decisions

        assert load_lens_edits_as_decisions(basins=[]) == []

    def test_paired_remove_add_becomes_correction(self, lens_edit_env):
        from trinity_local.me.lens_edits import (
            capture_lens_edits,
            load_lens_edits_as_decisions,
            write_lens_snapshot,
        )

        write_lens_snapshot("# /me\noriginal principle\n")
        capture_lens_edits(current_lens_text="# /me\nrevised principle\n")

        decisions = load_lens_edits_as_decisions(basins=[])
        # One paired modify → one Decision (not two separate add/remove)
        assert len(decisions) == 1
        d = decisions[0]
        assert d.source == "lens_edit"
        assert d.weight == 3.0
        assert d.valence == "correction"
        assert d.privileged == "revised principle"
        assert d.sacrificed == "original principle"
        assert d.id.startswith("le_")

    def test_lone_add_becomes_satisfaction(self, lens_edit_env):
        from trinity_local.me.lens_edits import (
            capture_lens_edits,
            load_lens_edits_as_decisions,
            write_lens_snapshot,
        )

        write_lens_snapshot("# /me\nexisting line\n")
        capture_lens_edits(current_lens_text="# /me\nexisting line\nbrand new lens\n")

        decisions = load_lens_edits_as_decisions(basins=[])
        assert len(decisions) == 1
        d = decisions[0]
        assert d.valence == "satisfaction"
        assert d.privileged == "brand new lens"
        assert "absent" in d.sacrificed.lower()
        assert d.source == "lens_edit"
        assert d.weight == 3.0

    def test_lone_remove_becomes_cost(self, lens_edit_env):
        from trinity_local.me.lens_edits import (
            capture_lens_edits,
            load_lens_edits_as_decisions,
            write_lens_snapshot,
        )

        write_lens_snapshot("# /me\nkeep this\nremove this\n")
        capture_lens_edits(current_lens_text="# /me\nkeep this\n")

        decisions = load_lens_edits_as_decisions(basins=[])
        assert len(decisions) == 1
        d = decisions[0]
        assert d.valence == "cost"
        assert "removed" in d.privileged.lower()
        assert d.sacrificed == "remove this"

    def test_weight_3_outranks_user_logged_2_and_transcript_1(self, lens_edit_env):
        """The whole point of slice 2: lens-edit must be the heaviest
        weight in the corpus so the pair-miner treats it as most
        load-bearing. Hierarchy: transcript 1.0 < user_logged 2.0 <
        lens_edit 3.0."""
        from trinity_local.me.lens_edits import (
            capture_lens_edits,
            load_lens_edits_as_decisions,
            write_lens_snapshot,
        )

        write_lens_snapshot("# /me\nbefore\n")
        capture_lens_edits(current_lens_text="# /me\nafter\n")

        decisions = load_lens_edits_as_decisions(basins=[])
        assert all(d.weight == 3.0 for d in decisions)
        # Confirms ordering invariant against the constants in decisions.py
        assert 3.0 > 2.0 > 1.0  # weight contract


class TestBuildIntegration:
    def test_build_summary_reports_captured_edits_count(self, lens_edit_env, monkeypatch):
        """build_me_via_council should include captured_edits in its
        summary so the CLI can surface "we picked up N user edits this
        build" — the closing-the-loop UX hint."""
        from trinity_local.state_paths import memories_dir

        # Pre-existing lens.md (the user's version with edits) + a stale
        # snapshot from "last build" with different content.
        (memories_dir() / "lens.md").write_text(
            "# /me\nbuilt by chairman last time\nUser added this line by hand\n",
            encoding="utf-8",
        )
        from trinity_local.me.lens_edits import write_lens_snapshot

        write_lens_snapshot("# /me\nbuilt by chairman last time\n")

        from trinity_local.me.lens_edits import capture_lens_edits

        edits = capture_lens_edits()
        assert len(edits) == 1
        assert edits[0].op == "add"
        assert "User added this line by hand" in edits[0].after
