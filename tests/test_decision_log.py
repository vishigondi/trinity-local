"""Tests for `trinity-local decision-log` CLI + decision_log.jsonl load path.

Plan iter 1 (2026-05-23), task #137 — Track A of the counterfactual
decision capture extension. Capture-at-decision-time vs. retroactive
transcript extraction; the live signal is HIGH-QUALITY (weight 2.0),
the transcript signal is LOW-QUALITY backfill (weight 1.0).
"""
from __future__ import annotations

import io
import json
from contextlib import redirect_stdout, redirect_stderr
from unittest.mock import patch

import pytest

from trinity_local.commands.decision_log import (
    _normalize_record,
    handle_decision_log,
    register,
)
from trinity_local.me.decisions import (
    Decision,
    VALID_HORIZONS,
    VALID_VALENCES,
    decision_log_path,
    load_decision_log,
    parse_decisions,
)


@pytest.fixture
def trinity_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
    # Ensure me/ subdir exists for decision_log_path() writes
    (tmp_path / "me").mkdir(parents=True, exist_ok=True)
    return tmp_path


def test_decision_dataclass_default_back_compat():
    """Transcript-extracted decisions get sensible defaults so existing
    decisions.jsonl files still parse."""
    d = Decision(
        id="d_001",
        privileged="momentum to close",
        sacrificed="relational reciprocity",
        valence="satisfaction",
        basin=None,
        verbatim="let's just pay 2% to the buyer agent",
    )
    assert d.would_flip_if == ""
    assert d.source == "transcript"
    assert d.logged_at == ""
    assert d.weight == 1.0


def test_decision_to_dict_omits_default_fields():
    """to_dict() only emits the new fields when non-default — keeps
    existing decisions.jsonl line shape compact."""
    d = Decision(
        id="d_001",
        privileged="A",
        sacrificed="B",
        valence="satisfaction",
        basin=None,
        verbatim="x",
    )
    payload = d.to_dict()
    assert "would_flip_if" not in payload
    assert "source" not in payload
    assert "logged_at" not in payload
    assert "weight" not in payload


def test_decision_to_dict_emits_user_logged_fields():
    """User-logged decisions emit the full shape."""
    d = Decision(
        id="u_001",
        privileged="capability hidden in structure",
        sacrificed="capability surfaced as features",
        valence="satisfaction",
        basin="b03",
        verbatim="intelligence is infrastructure",
        would_flip_if="If user-facing iteration were the only validation surface",
        source="user_logged",
        logged_at="2026-05-23T11:00:00+00:00",
        weight=2.0,
    )
    payload = d.to_dict()
    assert payload["would_flip_if"] == "If user-facing iteration were the only validation surface"
    assert payload["source"] == "user_logged"
    assert payload["logged_at"] == "2026-05-23T11:00:00+00:00"
    assert payload["weight"] == 2.0


def test_normalize_record_clamps_invalid_valence():
    rec = _normalize_record(
        decision="x",
        privileged="a",
        sacrificed="b",
        valence="bogus",
        would_flip_if="",
        horizon="strategic",
        basin="",
    )
    assert rec["valence"] == "satisfaction"


def test_normalize_record_clamps_invalid_horizon():
    rec = _normalize_record(
        decision="x",
        privileged="a",
        sacrificed="b",
        valence="cost",
        would_flip_if="",
        horizon="bogus",
        basin="",
    )
    assert rec["horizon"] == "strategic"


def test_normalize_record_omits_empty_optional_fields():
    rec = _normalize_record(
        decision="x",
        privileged="a",
        sacrificed="b",
        valence="cost",
        would_flip_if="",
        horizon="tactical",
        basin="",
    )
    assert "would_flip_if" not in rec
    assert "basin" not in rec
    assert rec["source"] == "user_logged"
    assert rec["weight"] == 2.0


def test_normalize_record_truncates_long_verbatim():
    rec = _normalize_record(
        decision="x" * 500,
        privileged="a",
        sacrificed="b",
        valence="cost",
        would_flip_if="",
        horizon="tactical",
        basin="",
    )
    assert len(rec["verbatim"]) == 200


def test_handle_decision_log_json_mode_appends_jsonl(trinity_home):
    """Non-interactive mode reads JSON from stdin and writes one line."""
    payload = {
        "decision": "Komorebi over conventional venture fund",
        "privileged": "patient capital allocation",
        "sacrificed": "convention conformance",
        "valence": "satisfaction",
        "would_flip_if": "If LP conviction in the thesis hadn't held",
        "horizon": "philosophical",
    }
    stdin_text = json.dumps(payload)

    class _Args:
        from_json = True
        decision = privileged = sacrificed = None
        valence = would_flip_if = horizon = basin = None

    out = io.StringIO()
    with redirect_stdout(out), patch("sys.stdin", io.StringIO(stdin_text)):
        handle_decision_log(_Args())

    path = decision_log_path()
    assert path.exists()
    lines = path.read_text().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    assert entry["privileged"] == "patient capital allocation"
    assert entry["sacrificed"] == "convention conformance"
    assert entry["would_flip_if"] == "If LP conviction in the thesis hadn't held"
    assert entry["horizon"] == "philosophical"
    assert entry["source"] == "user_logged"
    assert entry["weight"] == 2.0
    assert entry["logged_at"]  # ISO8601 stamp


def test_handle_decision_log_json_mode_append_not_overwrite(trinity_home):
    """Repeated invocations append rather than replace."""
    class _Args:
        from_json = True
        decision = privileged = sacrificed = None
        valence = would_flip_if = horizon = basin = None

    for i in range(3):
        payload = json.dumps({
            "decision": f"Decision {i}",
            "privileged": f"A{i}",
            "sacrificed": f"B{i}",
            "valence": "satisfaction",
            "horizon": "strategic",
        })
        out = io.StringIO()
        with redirect_stdout(out), patch("sys.stdin", io.StringIO(payload)):
            handle_decision_log(_Args())

    lines = decision_log_path().read_text().splitlines()
    assert len(lines) == 3


def test_handle_decision_log_rejects_malformed_json(trinity_home):
    class _Args:
        from_json = True
        decision = privileged = sacrificed = None
        valence = would_flip_if = horizon = basin = None

    err = io.StringIO()
    with redirect_stderr(err), patch("sys.stdin", io.StringIO("{not valid json")):
        with pytest.raises(SystemExit) as exc:
            handle_decision_log(_Args())
    assert exc.value.code == 2


def test_load_decision_log_missing_file_returns_empty(trinity_home):
    assert load_decision_log(basins=[]) == []


def test_load_decision_log_reads_appended_entries(trinity_home):
    path = decision_log_path()
    path.write_text(
        json.dumps({
            "privileged": "capability hidden in structure",
            "sacrificed": "capability surfaced as features",
            "valence": "satisfaction",
            "verbatim": "intelligence is infrastructure",
            "would_flip_if": "If interface-first iteration validated faster",
            "source": "user_logged",
            "logged_at": "2026-05-23T11:00:00+00:00",
            "weight": 2.0,
        }) + "\n"
    )
    decisions = load_decision_log(basins=[])
    assert len(decisions) == 1
    d = decisions[0]
    assert d.privileged == "capability hidden in structure"
    assert d.would_flip_if == "If interface-first iteration validated faster"
    assert d.source == "user_logged"
    assert d.weight == 2.0


def test_load_decision_log_skips_blank_and_comment_lines(trinity_home):
    path = decision_log_path()
    path.write_text(
        "# this is a comment line\n"
        "\n"
        + json.dumps({
            "privileged": "A", "sacrificed": "B",
            "valence": "satisfaction", "verbatim": "x",
        }) + "\n"
    )
    assert len(load_decision_log(basins=[])) == 1


def test_load_decision_log_assigns_auto_ids_when_missing(trinity_home):
    path = decision_log_path()
    path.write_text(
        json.dumps({
            "privileged": "A", "sacrificed": "B",
            "valence": "satisfaction", "verbatim": "first",
        }) + "\n" +
        json.dumps({
            "privileged": "C", "sacrificed": "D",
            "valence": "cost", "verbatim": "second",
        }) + "\n"
    )
    decisions = load_decision_log(basins=[])
    ids = [d.id for d in decisions]
    assert ids[0].startswith("u_")
    assert ids[1].startswith("u_")
    assert ids[0] != ids[1]


def test_load_decision_log_skips_malformed_lines(trinity_home):
    path = decision_log_path()
    path.write_text(
        "not valid json\n"
        + json.dumps({
            "privileged": "A", "sacrificed": "B",
            "valence": "satisfaction", "verbatim": "valid",
        }) + "\n"
    )
    decisions = load_decision_log(basins=[])
    assert len(decisions) == 1
    assert decisions[0].verbatim == "valid"


def test_load_decision_log_requires_both_poles_and_verbatim(trinity_home):
    path = decision_log_path()
    path.write_text(
        # Missing sacrificed
        json.dumps({"privileged": "A", "valence": "satisfaction", "verbatim": "x"}) + "\n" +
        # Missing privileged
        json.dumps({"sacrificed": "B", "valence": "satisfaction", "verbatim": "y"}) + "\n" +
        # Missing verbatim
        json.dumps({"privileged": "A", "sacrificed": "B", "valence": "satisfaction"}) + "\n" +
        # Full — should land
        json.dumps({"privileged": "A", "sacrificed": "B", "valence": "satisfaction", "verbatim": "ok"}) + "\n"
    )
    assert len(load_decision_log(basins=[])) == 1


def test_parse_decisions_back_compat_no_new_fields(trinity_home):
    """Existing decisions.jsonl lines (pre-extension) still parse cleanly."""
    raw = json.dumps({
        "id": "d_001",
        "privileged": "A",
        "sacrificed": "B",
        "valence": "satisfaction",
        "basin": None,
        "verbatim": "x",
        "prompt_id": "p001",
    })
    decisions = parse_decisions(raw, basins=[])
    assert len(decisions) == 1
    assert decisions[0].would_flip_if == ""
    assert decisions[0].source == "transcript"
    assert decisions[0].weight == 1.0


def test_parse_decisions_reads_new_fields_when_present(trinity_home):
    raw = json.dumps({
        "id": "d_001",
        "privileged": "A",
        "sacrificed": "B",
        "valence": "satisfaction",
        "basin": "b03",
        "verbatim": "x",
        "prompt_id": "p001",
        "would_flip_if": "the gradient",
        "source": "user_logged",
        "logged_at": "2026-05-23T11:00:00+00:00",
        "weight": 2.0,
    })
    decisions = parse_decisions(raw, basins=[])
    assert len(decisions) == 1
    d = decisions[0]
    assert d.would_flip_if == "the gradient"
    assert d.source == "user_logged"
    assert d.weight == 2.0


def test_cli_registration():
    import argparse
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command")
    register(subparsers)
    args = parser.parse_args(["decision-log", "--json"])
    assert args.command == "decision-log"
    assert args.from_json is True


def test_valid_horizons_constant():
    assert VALID_HORIZONS == {"tactical", "strategic", "philosophical"}


def test_valid_valences_unchanged():
    assert VALID_VALENCES == {"satisfaction", "regret", "unresolved", "correction", "cost"}
