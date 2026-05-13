"""Tick #44 — `~/.trinity/me/merges.jsonl` writer.

Seeds the unified merge corpus the v1.5+ direction-of-preference
vectors / collapsed lens-build will read. v1.0 ships with one row
type (council_winner) so the lifecycle (write → read → schema) can
be exercised end-to-end before more types get added.
"""
from __future__ import annotations

import json

import pytest


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
    return tmp_path


class TestRecordMerge:
    """`record_merge` appends one row + stamps ts if absent.
    Cold-install path: directory created lazily, no error."""

    def test_creates_file_on_first_call(self, isolated_home):
        from trinity_local.merges import record_merge, merges_path
        assert not merges_path().exists(), "cold install starts without the file"
        record_merge({"type": "council_winner", "chosen": "claude"})
        assert merges_path().exists(), "first call must create the file"

    def test_appends_one_row_per_call(self, isolated_home):
        from trinity_local.merges import record_merge, merges_path
        record_merge({"type": "council_winner", "chosen": "claude"})
        record_merge({"type": "council_winner", "chosen": "gemini"})
        lines = merges_path().read_text(encoding="utf-8").strip().split("\n")
        assert len(lines) == 2, f"expected 2 rows, got {len(lines)}"

    def test_stamps_ts_when_missing(self, isolated_home):
        from trinity_local.merges import record_merge
        out = record_merge({"type": "council_winner", "chosen": "claude"})
        assert "ts" in out, "record_merge didn't stamp ts"
        # ISO-8601 sanity: starts with year-month-day separators
        assert out["ts"][:4].isdigit() and out["ts"][4] == "-", (
            f"ts not ISO-8601: {out['ts']!r}"
        )

    def test_preserves_caller_ts_when_provided(self, isolated_home):
        from trinity_local.merges import record_merge
        out = record_merge({
            "type": "council_winner",
            "chosen": "claude",
            "ts": "2026-01-01T00:00:00",
        })
        assert out["ts"] == "2026-01-01T00:00:00", "caller ts must win"


class TestIterMergeRecords:
    """Read-side: malformed lines silently skipped, missing file
    returns empty iterator (cold install path)."""

    def test_cold_install_returns_empty(self, isolated_home):
        from trinity_local.merges import iter_merge_records
        # No file written yet — must iterate cleanly.
        assert list(iter_merge_records()) == []

    def test_round_trip(self, isolated_home):
        from trinity_local.merges import record_merge, iter_merge_records
        record_merge({"type": "council_winner", "chosen": "claude", "task_type": "coding"})
        record_merge({"type": "council_winner", "chosen": "gemini", "task_type": "writing"})
        rows = list(iter_merge_records())
        assert len(rows) == 2
        assert rows[0]["chosen"] == "claude"
        assert rows[1]["task_type"] == "writing"

    def test_malformed_lines_skipped(self, isolated_home):
        from trinity_local.merges import record_merge, iter_merge_records, merges_path
        record_merge({"type": "council_winner", "chosen": "claude"})
        # Hand-corrupt: append a malformed line + a blank line.
        with merges_path().open("a", encoding="utf-8") as f:
            f.write("{not valid json\n")
            f.write("\n")
            f.write('{"type": "council_winner", "chosen": "gemini"}\n')
        rows = list(iter_merge_records())
        # The malformed line is silently dropped — but the good rows
        # before AND after it both come through.
        assert len(rows) == 2, f"good rows lost; got {len(rows)}"
        assert rows[0]["chosen"] == "claude"
        assert rows[1]["chosen"] == "gemini"


class TestCortexOverrideRow:
    """Tick #45 — cortex_override row type. Every veto via
    `trinity-local cortex-override --basin X` OR the MCP
    `mark_pick_wrong` tool appends one row. Pin the schema +
    that both call-sites write the same shape."""

    def test_cli_handler_appends_cortex_override_row(self, isolated_home, monkeypatch):
        # Fixture a routing patterns file the CLI handler will mutate.
        import json
        cortex_dir = isolated_home / "memories"
        cortex_dir.mkdir(parents=True, exist_ok=True)
        # Use the same minimal pattern shape as the picks-Reader tests.
        from tests.test_launchpad_topology_chip import _minimal_pattern_payload
        (cortex_dir / "picks.json").write_text(
            json.dumps({"coding": _minimal_pattern_payload("coding", centroid=[1.0, 0.0])}),
            encoding="utf-8",
        )
        # Call the handler with argparse-style args.
        from trinity_local.commands.cortex import handle_cortex_override
        class Args:
            basin = "coding"
            reset = False
            reason = "feels noisy"
        rc = handle_cortex_override(Args())
        assert rc == 0, "CLI handler returned non-zero"
        # Merge row should have landed.
        from trinity_local.merges import iter_merge_records
        rows = [r for r in iter_merge_records() if r["type"] == "cortex_override"]
        assert len(rows) == 1, f"expected 1 cortex_override row, got {len(rows)}"
        row = rows[0]
        assert row["basin_id"] == "coding"
        assert row["action"] == "incremented"
        assert row["prior_count"] == 0
        assert row["new_count"] == 1
        assert row["reason"] == "feels noisy"
        assert "ts" in row

    def test_reset_action_records_distinct_row(self, isolated_home, monkeypatch):
        import json
        cortex_dir = isolated_home / "memories"
        cortex_dir.mkdir(parents=True, exist_ok=True)
        from tests.test_launchpad_topology_chip import _minimal_pattern_payload
        # Pre-seed override_count=3 so reset has work to do.
        pattern_payload = _minimal_pattern_payload("coding", centroid=[1.0, 0.0])
        pattern_payload["override_count"] = 3
        (cortex_dir / "picks.json").write_text(
            json.dumps({"coding": pattern_payload}),
            encoding="utf-8",
        )
        from trinity_local.commands.cortex import handle_cortex_override
        class Args:
            basin = "coding"
            reset = True
            reason = None
        rc = handle_cortex_override(Args())
        assert rc == 0
        from trinity_local.merges import iter_merge_records
        rows = [r for r in iter_merge_records() if r["type"] == "cortex_override"]
        assert len(rows) == 1
        row = rows[0]
        assert row["action"] == "reset"
        # Reset records the prior count + the new zeroed count so the
        # delta is fully recoverable from the log.
        assert row["prior_count"] == 3, f"prior_count drift: {row['prior_count']}"
        assert row["new_count"] == 0


class TestCouncilWinnerSchema:
    """Pin the schema for the council_winner row type so future
    consumers (direction-of-preference vector, lens-build collapse)
    can rely on these keys being present.

    Note: the MCP-side wiring writes the actual rows; this test
    fixtures a representative row directly to lock the contract."""

    def test_canonical_row_has_required_fields(self, isolated_home):
        from trinity_local.merges import record_merge, iter_merge_records
        record_merge({
            "type": "council_winner",
            "council_id": "council_abc",
            "task_type": "coding",
            "chosen": "claude",
            "rejected": ["gemini", "codex"],
            "chairman_winner": "claude",
            "answer_label": "thumbs_up",
        })
        rows = list(iter_merge_records())
        row = rows[0]
        # Required keys downstream consumers will read:
        for key in ("type", "council_id", "task_type", "chosen", "rejected", "chairman_winner", "ts"):
            assert key in row, f"required key {key!r} missing from canonical row"
        assert row["rejected"] == ["gemini", "codex"], "rejected provider list must round-trip"
