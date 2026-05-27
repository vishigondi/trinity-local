"""Task #181 — seed-kernel recursion in the 4-tier gate.

Three feedback edges close here:
  1. T3 reads lens tensions AS the grading rubric (not background context).
  2. T3↔T4 calibration: per-basin promote→demote rate tunes T3's baseline.
  3. Gate-over-lens: T1/T2 primitives apply to lens tensions themselves.

These tests pin each edge independently with deterministic inputs — no
real chairman calls, no real embedding model. The contract these
functions implement IS the recursion; if the recursion breaks, these
tests are the canary.
"""
from __future__ import annotations

import json

import pytest

from trinity_local.moves import dream as dream_mod
from trinity_local.moves.gate import (
    LensTension,
    gate_lens_tension_in_basin,
    gate_lens_tensions,
    parse_lens_tensions,
    render_tension_rubric_for_basin,
)


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
    return tmp_path


# ─── Change #1: T3 rubric uses lens tensions ────────────────────────


_SAMPLE_LENS_MD = """# Lens

Some intro prose. This part is ignored.

### 1. precision ↔ simplicity
- Pure-precision fails as: **overspecified rigidity**
- Pure-simplicity fails as: **lossy hand-waving**
- Tension evidence spans basins: b00, b02

### 2. autonomy ↔ guardrails
- Pure-autonomy fails as: **runaway agent behavior**
- Pure-guardrails fails as: **brittle templating**
- Tension evidence spans basins: b03

### 3. abstract ↔ concrete
- Pure-abstract fails as: **shallow generalization**
- Pure-concrete fails as: **brittle context-coupling**
"""


class TestParseLensTensions:
    def test_parses_three_tensions_from_lens_md(self):
        tensions = parse_lens_tensions(_SAMPLE_LENS_MD)
        assert len(tensions) == 3
        assert tensions[0].pole_a == "precision"
        assert tensions[0].pole_b == "simplicity"
        assert tensions[0].basins == ("b00", "b02")
        assert tensions[0].pole_a_failure == "overspecified rigidity"
        assert tensions[0].pole_b_failure == "lossy hand-waving"

    def test_tension_without_basins_line_has_empty_basins(self):
        tensions = parse_lens_tensions(_SAMPLE_LENS_MD)
        assert tensions[2].basins == ()

    def test_empty_lens_returns_empty_list(self):
        assert parse_lens_tensions("") == []

    def test_malformed_lens_returns_partial_list(self):
        # Headings without bullets — parser should be tolerant
        out = parse_lens_tensions("### 1. a ↔ b\n\n### 2. c ↔ d\n")
        assert len(out) == 2
        assert out[0].basins == ()
        assert out[0].pole_a_failure == ""


class TestRenderTensionRubric:
    def test_basin_specific_tensions_preferred(self):
        tensions = parse_lens_tensions(_SAMPLE_LENS_MD)
        rubric = render_tension_rubric_for_basin(tensions, "b03")
        # Only the b03-scoped tension should appear
        assert "autonomy" in rubric
        assert "guardrails" in rubric
        assert "precision" not in rubric

    def test_falls_back_to_corpus_wide_when_no_basin_match(self):
        tensions = parse_lens_tensions(_SAMPLE_LENS_MD)
        rubric = render_tension_rubric_for_basin(tensions, "b99")
        # Should surface the basin-less tension (the third one has no
        # basins line)
        assert "abstract" in rubric
        assert "concrete" in rubric

    def test_empty_tensions_returns_empty_string(self):
        assert render_tension_rubric_for_basin([], "b00") == ""

    def test_caps_at_max_tensions(self):
        tensions = parse_lens_tensions(_SAMPLE_LENS_MD)
        # All tensions, capped at 1
        rubric = render_tension_rubric_for_basin(tensions, None, max_tensions=1)
        # Only one TENSION heading
        assert rubric.count("TENSION:") == 1


# ─── Change #3: gate-over-lens — T1/T2 apply to tensions themselves ──


def _make_tension(*, basins=("b00",)) -> LensTension:
    return LensTension(
        pole_a="precision",
        pole_b="simplicity",
        pole_a_failure="overspecified rigidity",
        pole_b_failure="lossy hand-waving",
        basins=basins,
    )


class TestGateLensTensionInBasin:
    def test_t1_vacuous_pass_when_no_accepted_patterns(self):
        t = _make_tension()
        t1, t2 = gate_lens_tension_in_basin(
            t, "b00",
            accepted_patterns=None,
            basin_centroid=[0.0, 1.0, 0.0],
        )
        assert t1.passed is True
        assert "vacuous" in t1.reason.lower()

    def test_t1_passes_when_lexical_overlap_above_threshold(self):
        t = _make_tension()
        # Pattern shares many trigrams with the probe text
        patterns = [
            "precision · simplicity · overspecified rigidity · lossy hand-waving"
        ]
        t1, _ = gate_lens_tension_in_basin(
            t, "b00",
            accepted_patterns=patterns,
            basin_centroid=None,
            t1_threshold=0.05,
        )
        assert t1.passed is True
        assert t1.score > 0.05

    def test_t2_fails_when_no_centroid(self):
        t = _make_tension()
        _, t2 = gate_lens_tension_in_basin(
            t, "b00",
            accepted_patterns=["something"],
            basin_centroid=None,
        )
        assert t2.passed is False
        assert "no basin centroid" in t2.reason.lower()


class TestGateLensTensions:
    def test_tension_with_no_basins_passes_through(self):
        t = _make_tension(basins=())
        report = gate_lens_tensions([t])
        assert len(report["kept"]) == 1
        assert report["kept"][0] is t
        assert report["narrowed"] == []
        assert report["archived"] == []

    def test_all_basins_fail_tension_archived(self):
        t = _make_tension(basins=("b00", "b01"))
        # Empty patterns + no centroids → T1 vacuous-passes but T2
        # fails for both. With default require_both_tiers=False, T1's
        # vacuous pass keeps the tension alive — test the stricter
        # require_both_tiers=True mode here so we can pin "fully fail"
        # semantics.
        report = gate_lens_tensions(
            [t],
            basin_patterns={"b00": ["foo bar"], "b01": ["baz qux"]},
            basin_centroids={},
            require_both_tiers=True,
        )
        # Both basins fail T2 (no centroid) → archived
        assert len(report["archived"]) == 1
        archived_tension, reason = report["archived"][0]
        assert archived_tension is t
        assert "b00" in reason and "b01" in reason

    def test_partial_basin_failure_yields_narrowed(self):
        t = _make_tension(basins=("b00", "b01"))
        # b00 has matching patterns (T1 will pass), b01 has nothing
        report = gate_lens_tensions(
            [t],
            basin_patterns={
                "b00": [
                    "precision · simplicity · overspecified rigidity · lossy hand-waving"
                ],
                "b01": ["totally unrelated content"],
            },
            basin_centroids={},  # no T2 signal anywhere
            require_both_tiers=False,  # T1-only is enough
        )
        # b00 keeps via T1, b01 has T1 fail (low Jaccard) + no T2 → drops
        assert len(report["narrowed"]) == 1
        orig, new = report["narrowed"][0]
        assert orig is t
        assert new.basins == ("b00",)

    def test_multiple_tensions_with_same_basin_all_kept_when_t1_vacuous(self):
        t1 = _make_tension(basins=("b00",))
        t2 = _make_tension(basins=("b00",))
        report = gate_lens_tensions(
            [t1, t2],
            basin_patterns={"b00": None},  # vacuous T1 pass
            basin_centroids={},
            require_both_tiers=False,
        )
        assert len(report["kept"]) == 2
        assert report["archived"] == []
        assert report["narrowed"] == []


# ─── Change #2: T3↔T4 calibration loop ────────────────────────────


class _FakeMove:
    """Minimal stand-in for Move.list_moves() output. The calibration
    pass only reads `.trinity_basin_id` so we don't need a full Move."""
    def __init__(self, basin_id: str):
        self.trinity_basin_id = basin_id


class TestCalibrationFromDemotions:
    def test_no_basins_no_demotion_rate_yields_no_state(self, isolated_home, monkeypatch):
        monkeypatch.setattr(dream_mod.store, "list_moves", lambda archived=False: [])
        report = dream_mod.update_calibration_from_demotions()
        assert report["basins_inspected"] == 0
        assert report["deltas"] == []
        # File should not have been written meaningfully
        calib = dream_mod._load_calibration()
        assert calib.get("per_basin", {}) == {}

    def test_high_demotion_rate_elevates_baseline(self, isolated_home, monkeypatch):
        # 1 active, 4 archived in same basin → 80% demotion rate
        monkeypatch.setattr(
            dream_mod.store,
            "list_moves",
            lambda archived=False: (
                [_FakeMove("b00")] if not archived
                else [_FakeMove("b00") for _ in range(4)]
            ),
        )
        report = dream_mod.update_calibration_from_demotions()
        assert report["basins_inspected"] >= 1
        # At least one delta should mark this basin as elevated
        elev = [d for d in report["deltas"] if d["action"] == "elevated"]
        assert elev, f"expected elevation delta, got {report['deltas']}"
        assert elev[0]["new_baseline"] > elev[0]["prior_baseline"]

    def test_low_demotion_rate_with_enough_evidence_relaxes(self, isolated_home, monkeypatch):
        # 9 active, 1 archived in same basin → 10% demotion rate, n=10
        # Seed an elevated baseline so there's room to relax.
        path = dream_mod._calibration_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "version": 1,
            "per_basin": {"b00": {"elevated_baseline": 0.7}}
        }), encoding="utf-8")
        monkeypatch.setattr(
            dream_mod.store,
            "list_moves",
            lambda archived=False: (
                [_FakeMove("b00") for _ in range(9)] if not archived
                else [_FakeMove("b00")]
            ),
        )
        report = dream_mod.update_calibration_from_demotions()
        relaxed = [d for d in report["deltas"] if d["action"] == "relaxed"]
        assert relaxed, f"expected relaxation, got {report['deltas']}"
        assert relaxed[0]["new_baseline"] < relaxed[0]["prior_baseline"]

    def test_insufficient_observations_no_change(self, isolated_home, monkeypatch):
        # Only 2 events total — below _CALIBRATION_MIN_OBSERVATIONS
        monkeypatch.setattr(
            dream_mod.store,
            "list_moves",
            lambda archived=False: (
                [_FakeMove("b00")] if not archived
                else [_FakeMove("b00")]
            ),
        )
        report = dream_mod.update_calibration_from_demotions()
        assert report["deltas"] == []


class TestCalibratedBaselineForBasin:
    def test_returns_none_for_unknown_basin(self, isolated_home):
        assert dream_mod.calibrated_baseline_for_basin("b00") is None
        assert dream_mod.calibrated_baseline_for_basin(None) is None

    def test_returns_elevated_baseline_after_calibration(self, isolated_home):
        path = dream_mod._calibration_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({
            "version": 1,
            "per_basin": {"b00": {"elevated_baseline": 0.65}}
        }), encoding="utf-8")
        assert dream_mod.calibrated_baseline_for_basin("b00") == 0.65

    def test_malformed_state_returns_none_without_crashing(self, isolated_home):
        path = dream_mod._calibration_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("not json at all {", encoding="utf-8")
        # Should not raise; should return None for any basin
        assert dream_mod.calibrated_baseline_for_basin("b00") is None


class TestOrchestratorPhase6d:
    def test_phase_6_runs_calibration(self, isolated_home, monkeypatch):
        # Stub all the sub-phases so we exercise the orchestrator's
        # ordering, not the implementations (those are tested elsewhere).
        monkeypatch.setattr(dream_mod, "update_t4_from_recent_councils", lambda **_: {"updated": 0})
        monkeypatch.setattr(dream_mod, "_load_rejection_corpus", lambda: [])
        monkeypatch.setattr(dream_mod, "discover_candidates", lambda _c: [])
        monkeypatch.setattr(dream_mod, "_accepted_patterns_by_basin", lambda _c: {})
        monkeypatch.setattr(dream_mod, "run_promotion_pass", lambda *a, **kw: {"promoted": 0})
        monkeypatch.setattr(dream_mod, "run_demotion_pass", lambda: {"demoted": 0})
        monkeypatch.setattr(
            dream_mod,
            "update_calibration_from_demotions",
            lambda: {"basins_inspected": 1, "deltas": []},
        )
        report = dream_mod.phase_6_moves_pass()
        assert "calibration" in report
        assert report["calibration"]["basins_inspected"] == 1
