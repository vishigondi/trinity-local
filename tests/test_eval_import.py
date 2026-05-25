"""eval-import: provider JSON → rejections.jsonl merge.

Pins schema mapping (REFRAME/REDIRECT/SHARPENING/COMPRESSION axis
validation), dedup-by-stable-id (same input → same id, second import
no-ops), and append-only file semantics (matches existing turn_pairs
producer).
"""
from __future__ import annotations

import json
from argparse import Namespace

import pytest

from trinity_local.commands.eval_import import (
    _provider_dict_to_rejection_signal,
    _read_existing_ids,
    handle_eval_import,
    handle_eval_prompt,
)
from trinity_local.me.turn_pairs import rejections_path


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
    return tmp_path


def _good_rejection(axis: str = "REFRAME") -> dict:
    return {
        "type": axis,
        "model_quote": "Let me explain why X is hard before showing the answer",
        "user_substitute": "skip the why, just give me the SQL",
        "why_signal": "user wants the answer first, justification second",
        "confidence": "high",
    }


def _payload(rejections: list[dict], provider: str = "claude") -> dict:
    return {
        "source_provider": provider,
        "extracted_at": "2026-05-25T08:00:00Z",
        "horizon_window_days": 30,
        "rejections": rejections,
    }


class TestProviderDictMapping:
    def test_canonical_rejection_maps_cleanly(self):
        sig = _provider_dict_to_rejection_signal(_good_rejection(), "claude", 0)
        assert sig is not None
        assert sig.type == "REFRAME"
        assert "skip the why" in sig.user_substitute
        # source_provider + confidence get folded into why_signal so eval-run
        # downstream sees the provenance.
        assert "[claude/high]" in sig.why_signal
        assert sig.id.startswith("rej_")

    def test_invalid_axis_rejected(self):
        bad = _good_rejection(axis="EXPLAIN")  # not one of the 4 valid axes
        assert _provider_dict_to_rejection_signal(bad, "claude", 0) is None

    def test_missing_quote_or_substitute_rejected(self):
        for missing in ("model_quote", "user_substitute"):
            bad = _good_rejection()
            del bad[missing]
            assert _provider_dict_to_rejection_signal(bad, "claude", 0) is None

    def test_axis_normalized_to_uppercase(self):
        bad = _good_rejection(axis="reframe")  # lowercase
        sig = _provider_dict_to_rejection_signal(bad, "claude", 0)
        assert sig is not None
        assert sig.type == "REFRAME"

    def test_stable_id_deterministic_across_calls(self):
        """Same content → same id, so re-import dedups cleanly."""
        a = _provider_dict_to_rejection_signal(_good_rejection(), "claude", 0)
        b = _provider_dict_to_rejection_signal(_good_rejection(), "claude", 5)
        assert a.id == b.id  # seq deliberately NOT mixed in for true dedup

    def test_stable_id_distinguishes_providers(self):
        """Same quote captured by two providers → distinct ids (so both land)."""
        a = _provider_dict_to_rejection_signal(_good_rejection(), "claude", 0)
        b = _provider_dict_to_rejection_signal(_good_rejection(), "codex", 0)
        assert a.id != b.id


class TestCliEndToEnd:
    def test_first_import_persists_to_rejections_jsonl(self, home, tmp_path, capsys):
        payload_file = tmp_path / "evals.json"
        payload_file.write_text(json.dumps(_payload([
            _good_rejection("REFRAME"),
            _good_rejection("REDIRECT"),
            _good_rejection("SHARPENING"),
        ])))
        args = Namespace(
            path=str(payload_file),
            from_json=False,
            dry_run=False,
            as_json=True,
        )
        rc = handle_eval_import(args)
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["rejections"]["new"] == 3
        assert result["rejections"]["duplicates"] == 0
        # File written, lines match
        lines = rejections_path().read_text(encoding="utf-8").splitlines()
        assert len(lines) == 3

    def test_re_import_same_payload_dedups(self, home, tmp_path, capsys):
        """Same payload imported twice: second run sees all-duplicates."""
        payload_file = tmp_path / "evals.json"
        payload_file.write_text(json.dumps(_payload([
            _good_rejection("REFRAME"),
            _good_rejection("REDIRECT"),
        ])))
        args = Namespace(
            path=str(payload_file),
            from_json=False,
            dry_run=False,
            as_json=True,
        )
        # First import — both land
        rc = handle_eval_import(args)
        assert rc == 0
        first = json.loads(capsys.readouterr().out)
        assert first["rejections"]["new"] == 2

        # Second import — same content → all dedup
        rc = handle_eval_import(args)
        assert rc == 0
        second = json.loads(capsys.readouterr().out)
        assert second["rejections"]["new"] == 0
        assert second["rejections"]["duplicates"] == 2
        # File still has only 2 lines (append-only didn't double)
        lines = rejections_path().read_text(encoding="utf-8").splitlines()
        assert len(lines) == 2

    def test_dry_run_does_not_write(self, home, tmp_path, capsys):
        payload_file = tmp_path / "evals.json"
        payload_file.write_text(json.dumps(_payload([_good_rejection()])))
        args = Namespace(
            path=str(payload_file),
            from_json=False,
            dry_run=True,
            as_json=True,
        )
        rc = handle_eval_import(args)
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["dry_run"] is True
        assert result["rejections"]["new"] == 1
        assert _read_existing_ids() == set()  # never landed

    def test_malformed_axes_skipped_not_aborted(self, home, tmp_path, capsys):
        """One bad axis shouldn't kill the import of the good ones."""
        payload_file = tmp_path / "evals.json"
        payload_file.write_text(json.dumps(_payload([
            _good_rejection("REFRAME"),
            _good_rejection("EXPLAIN"),  # invalid
            _good_rejection("COMPRESSION"),
        ])))
        args = Namespace(
            path=str(payload_file),
            from_json=False,
            dry_run=False,
            as_json=True,
        )
        rc = handle_eval_import(args)
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["rejections"]["new"] == 2
        assert result["rejections"]["skipped_malformed"] == 1

    def test_missing_file_exits_nonzero(self, home, tmp_path, capsys):
        args = Namespace(
            path=str(tmp_path / "nope.json"),
            from_json=False,
            dry_run=False,
            as_json=False,
        )
        rc = handle_eval_import(args)
        assert rc == 1
        assert "file not found" in capsys.readouterr().err

    def test_provider_flag_supplies_missing_source_provider(self, home, tmp_path, capsys):
        """Payload omits source_provider → --provider fills the gap."""
        payload_file = tmp_path / "evals.json"
        payload_file.write_text(json.dumps({"rejections": [_good_rejection()]}))
        args = Namespace(
            path=str(payload_file),
            from_json=False,
            provider="claude",
            dry_run=False,
            as_json=True,
        )
        rc = handle_eval_import(args)
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["source_provider"] == "claude"

    def test_provider_flag_overrides_payload_source_provider(self, home, tmp_path, capsys):
        """--provider wins over source_provider in the payload (re-attribution)."""
        payload_file = tmp_path / "evals.json"
        payload_file.write_text(json.dumps(_payload([_good_rejection()], provider="gemini")))
        args = Namespace(
            path=str(payload_file),
            from_json=False,
            provider="codex",
            dry_run=False,
            as_json=True,
        )
        rc = handle_eval_import(args)
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["source_provider"] == "codex"


class TestEvalPromptCli:
    def test_prompt_body_starts_with_the_user_instruction(self, capsys):
        rc = handle_eval_prompt(Namespace(with_instructions=False))
        assert rc == 0
        out = capsys.readouterr().out
        assert out.lstrip().startswith("Look back over my recent work")
        # No intro README content
        assert "trinity-local eval-import" not in out

    def test_with_instructions_includes_install_hint(self, capsys):
        rc = handle_eval_prompt(Namespace(with_instructions=True))
        assert rc == 0
        out = capsys.readouterr().out
        assert "Provider-side eval prompt" in out
        assert "trinity-local eval-import" in out
