"""lens-import: provider JSON → lenses.json + orderings.json merge.

Pin the schema mapping (provider format ↔ LensPair), the dedup policy
(case-insensitive, order-independent on pole names), and the
"never overwrite locally-built tensions" guarantee.
"""
from __future__ import annotations

import json
from argparse import Namespace

import pytest

from trinity_local.commands.lens_import import (
    _merge,
    _normalize_pole_pair,
    _provider_dict_to_lens_pair,
    _provider_dict_to_ordering_pair,
    handle_lens_import,
    handle_lens_prompt,
)
from trinity_local.me.pair_mining import LensPair, load_lenses, load_orderings


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
    return tmp_path


def _good_tension(pole_a: str = "concrete specificity", pole_b: str = "abstract pattern") -> dict:
    return {
        "pole_a": pole_a,
        "pole_b": pole_b,
        "failure_a": "tunnel vision",
        "failure_b": "hand-waving",
        "horizon": "strategic",
        "evidence": ["sized the parquet table by hand", "drew the basin diagram first"],
        "confidence": "high",
        "why_matters": "anchor before abstracting saves rework",
    }


def _good_ordering() -> dict:
    return {
        "pole_a": "shipping velocity",
        "pole_b": "polish",
        "evidence": ["MVP shipped Fri", "skipped redesign before launch"],
    }


def _payload(tensions: list[dict], orderings: list[dict] | None = None, provider: str = "claude") -> dict:
    return {
        "source_provider": provider,
        "extracted_at": "2026-05-25T08:00:00Z",
        "horizon_window_days": 30,
        "tensions": tensions,
        "orderings": orderings or [],
    }


class TestProviderDictMapping:
    def test_minimal_valid_tension_maps_cleanly(self):
        pair = _provider_dict_to_lens_pair(_good_tension(), source_provider="claude")
        assert pair is not None
        assert pair.pole_a == "concrete specificity"
        assert pair.pole_b == "abstract pattern"
        assert pair.failure_a == "tunnel vision"
        assert pair.failure_b == "hand-waving"
        assert pair.horizon == "strategic"
        assert pair.tension_decisions == [
            "sized the parquet table by hand",
            "drew the basin diagram first",
        ]
        # provenance + confidence + why_matters folded into dual_evidence
        assert pair.dual_evidence["source_provider"] == ["claude"]
        assert pair.dual_evidence["confidence"] == ["high"]
        assert pair.dual_evidence["why_matters"] == ["anchor before abstracting saves rework"]
        assert pair.verdict == "imported"
        assert pair.basins_spanned == []

    def test_missing_required_field_returns_none(self):
        """Missing pole_a → skip silently (counted as 'skipped_malformed' upstream)."""
        bad = _good_tension()
        del bad["pole_a"]
        assert _provider_dict_to_lens_pair(bad, source_provider="claude") is None

    def test_identical_poles_rejected(self):
        bad = _good_tension(pole_a="speed", pole_b="speed")
        assert _provider_dict_to_lens_pair(bad, source_provider="claude") is None

    def test_invalid_horizon_falls_back_to_tactical(self):
        bad = _good_tension()
        bad["horizon"] = "metaphysical"  # not in VALID_HORIZONS
        pair = _provider_dict_to_lens_pair(bad, source_provider="claude")
        assert pair is not None
        assert pair.horizon == "tactical"

    def test_ordering_mapping_keeps_no_failure_modes(self):
        """Orderings are single-direction preferences — no dual-regret failure modes."""
        pair = _provider_dict_to_ordering_pair(_good_ordering(), source_provider="codex")
        assert pair is not None
        assert pair.failure_a == ""
        assert pair.failure_b == ""
        assert pair.verdict == "imported_ordering"
        assert pair.dual_evidence["source_provider"] == ["codex"]


class TestDedupAndMerge:
    def test_normalize_pole_pair_case_and_order_independent(self):
        """`(Focus, Breadth)`, `(focus, breadth)`, `(breadth, focus)` all dedupe."""
        a = LensPair("Focus", "Breadth", "fa", "fb")
        b = LensPair("breadth", "focus", "fa", "fb")
        assert _normalize_pole_pair(a) == _normalize_pole_pair(b)

    def test_new_pair_appended(self):
        existing: list[LensPair] = []
        incoming = [_provider_dict_to_lens_pair(_good_tension(), "claude")]
        merged, new, aug = _merge(existing, [p for p in incoming if p])
        assert new == 1
        assert aug == 0
        assert len(merged) == 1

    def test_duplicate_pair_augments_existing(self):
        """Same poles from a second provider — augment evidence + provenance,
        NEVER overwrite the existing record (load-bearing for locally-built
        verdict='accepted' tensions)."""
        local = LensPair(
            pole_a="concrete specificity",
            pole_b="abstract pattern",
            failure_a="hand-built failure_a (local)",
            failure_b="hand-built failure_b (local)",
            tension_decisions=["local evidence 1"],
            dual_evidence={"source_provider": ["lens-build"]},
            verdict="accepted",
            horizon="strategic",
        )
        incoming = [_provider_dict_to_lens_pair(_good_tension(), "codex")]
        merged, new, aug = _merge([local], [p for p in incoming if p])
        assert new == 0
        assert aug == 1
        survivor = merged[0]
        # Failure-mode text is the LOCAL one — provider didn't overwrite
        assert survivor.failure_a == "hand-built failure_a (local)"
        # Evidence + provenance grew
        assert "local evidence 1" in survivor.tension_decisions
        assert "sized the parquet table by hand" in survivor.tension_decisions
        assert set(survivor.dual_evidence["source_provider"]) == {"lens-build", "codex"}
        # Verdict stays "accepted" (local label wins) — provenance shows it was also imported
        assert survivor.verdict == "accepted"


class TestCliEndToEnd:
    def test_dry_run_does_not_write(self, home, tmp_path, capsys):
        payload_file = tmp_path / "lens.json"
        payload_file.write_text(json.dumps(_payload([_good_tension()], [_good_ordering()])))

        args = Namespace(
            path=str(payload_file),
            from_json=False,
            dry_run=True,
            as_json=True,
        )
        rc = handle_lens_import(args)
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["dry_run"] is True
        assert result["tensions"]["new"] == 1
        # Sanity: nothing landed on disk
        assert load_lenses() == []
        assert load_orderings() == []

    def test_full_import_persists_and_round_trips(self, home, tmp_path, capsys):
        payload_file = tmp_path / "lens.json"
        payload_file.write_text(json.dumps(_payload(
            [_good_tension(), _good_tension(pole_a="depth", pole_b="breadth")],
            [_good_ordering()],
        )))
        args = Namespace(
            path=str(payload_file),
            from_json=False,
            dry_run=False,
            as_json=True,
        )
        rc = handle_lens_import(args)
        assert rc == 0
        result = json.loads(capsys.readouterr().out)
        assert result["tensions"]["new"] == 2
        assert result["orderings"]["new"] == 1
        # Verify on-disk state
        lenses = load_lenses()
        assert len(lenses) == 2
        pole_pairs = {(p.pole_a, p.pole_b) for p in lenses}
        assert ("concrete specificity", "abstract pattern") in pole_pairs
        assert ("depth", "breadth") in pole_pairs
        orderings = load_orderings()
        assert len(orderings) == 1
        assert orderings[0].pole_a == "shipping velocity"

    def test_malformed_top_level_exits_nonzero(self, home, tmp_path, capsys):
        payload_file = tmp_path / "bad.json"
        payload_file.write_text("not valid json {")
        args = Namespace(
            path=str(payload_file),
            from_json=False,
            dry_run=False,
            as_json=False,
        )
        rc = handle_lens_import(args)
        assert rc == 2
        err = capsys.readouterr().err
        assert "not valid JSON" in err

    def test_missing_file_exits_nonzero(self, home, tmp_path, capsys):
        args = Namespace(
            path=str(tmp_path / "nope.json"),
            from_json=False,
            dry_run=False,
            as_json=False,
        )
        rc = handle_lens_import(args)
        assert rc == 1
        assert "file not found" in capsys.readouterr().err


class TestLensPromptCli:
    def test_prompt_body_starts_with_user_facing_instruction(self, capsys):
        rc = handle_lens_prompt(Namespace(with_instructions=False))
        assert rc == 0
        out = capsys.readouterr().out
        # Body starts with the actual user-facing instruction
        assert out.lstrip().startswith("Look back over my recent work")
        # And does NOT include the intro README-y stuff
        assert "trinity-local lens-import" not in out

    def test_with_instructions_includes_full_doc(self, capsys):
        rc = handle_lens_prompt(Namespace(with_instructions=True))
        assert rc == 0
        out = capsys.readouterr().out
        assert "Provider-side lens prompt" in out  # the doc title
        assert "trinity-local lens-import" in out  # the install hint
