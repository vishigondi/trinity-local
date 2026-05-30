"""#257: the correction-vector lens — the lens as a geometric direction.

embed(privileged) - embed(sacrificed) per act, averaged, decomposed onto
interpretable taste axes. Per-act coherence is low by nature (corrections
scatter by topic); the axis loadings are the signal, and they're significant
(a random unit vector loads ~1/sqrt(768)=0.036 on an axis).
"""
from __future__ import annotations

import math

import pytest

from trinity_local.me import correction_lens as cl


def test_helpers_unit_and_mean():
    u = cl._unit([3.0, 4.0])
    assert math.isclose(math.hypot(*u), 1.0, abs_tol=1e-6)
    assert cl._mean([[1.0, 2.0], [3.0, 4.0]]) == [2.0, 3.0]
    assert cl._unit([0.0, 0.0]) == [0.0, 0.0]  # zero vector → no div-by-zero


def test_signature_shape_and_significance():
    sig = cl.correction_signature()
    if not sig.get("ready"):
        pytest.skip(f"signature not ready: {sig}")
    assert sig["n"] >= cl._MIN_CORRECTIONS
    assert "coherence" in sig and 0.0 <= sig["coherence"] <= 1.0
    axes = sig["axes"]
    assert set(axes) == set(cl.TASTE_AXES), "every axis must be scored"
    # At least one axis loads well above the random-noise floor (~0.036) —
    # otherwise the mean correction carries no interpretable taste direction.
    assert max(abs(v) for v in axes.values()) > 0.08, (
        f"no significant axis loading — correction lens has no signal: {axes}"
    )


def test_signature_thin_ledger(monkeypatch):
    # Below the minimum, not ready (don't surface a noisy direction).
    monkeypatch.setattr(cl, "_MIN_CORRECTIONS", 10**9)
    sig = cl.correction_signature()
    assert sig.get("ready") is False


def test_drift_shape_when_ready():
    """#257 diachronic drift: split early/recent, per-axis early/recent/delta +
    a biggest_mover. Skips when the embedder/ledger isn't available."""
    import trinity_local.me.correction_lens as cl

    drift = cl.correction_drift()
    if not drift.get("ready"):
        import pytest
        pytest.skip(f"drift not ready: {drift}")
    assert drift["n_early"] >= cl._MIN_CORRECTIONS
    assert drift["n_recent"] >= cl._MIN_CORRECTIONS
    assert len(drift["early_span"]) == 2 and len(drift["recent_span"]) == 2
    # early span ends no later than recent span starts (chronological split).
    assert drift["early_span"][1] <= drift["recent_span"][1]
    for name, d in drift["axes"].items():
        assert set(d.keys()) == {"early", "recent", "delta"}
        assert abs(round(d["recent"] - d["early"], 3) - d["delta"]) < 1e-6
    bm = drift["biggest_mover"]
    assert bm["axis"] in drift["axes"]
    # biggest_mover really has the max |delta|.
    assert abs(bm["delta"]) == max(abs(d["delta"]) for d in drift["axes"].values())


def test_drift_thin_ledger(monkeypatch):
    # Below 2× the per-half minimum → not ready (don't split a thin ledger).
    import trinity_local.me.correction_lens as cl
    monkeypatch.setattr(cl, "_MIN_CORRECTIONS", 10**9)
    assert cl.correction_drift().get("ready") is False


def test_by_basin_shape_when_ready():
    """#257 per-domain signature: per-basin axis loadings + top_axis, sorted by
    correction count. Skips when embedder/ledger unavailable."""
    import trinity_local.me.correction_lens as cl

    res = cl.correction_signature_by_basin()
    if not res.get("ready"):
        import pytest
        pytest.skip(f"by-basin not ready: {res}")
    assert res["n_basins"] == len(res["basins"]) >= 1
    counts = [d["n"] for d in res["basins"].values()]
    assert counts == sorted(counts, reverse=True)  # most-corrected first
    for bid, d in res["basins"].items():
        assert d["n"] >= cl._MIN_CORRECTIONS
        assert set(d["axes"].keys()) == set(cl.TASTE_AXES.keys())
        assert d["top_axis"]["axis"] in d["axes"]
        # top_axis really is the max |loading|.
        assert abs(d["top_axis"]["loading"]) == max(abs(v) for v in d["axes"].values())


def test_by_basin_high_threshold_not_ready(monkeypatch):
    # An impossibly high per-basin floor → no eligible basin → not ready.
    import trinity_local.me.correction_lens as cl
    assert cl.correction_signature_by_basin(min_per_basin=10**9).get("ready") is False


def test_taste_signature_shape(monkeypatch):
    """#254 cold-open material: adjectives (poles steered toward) + ONE
    representative correction in the user's words. Uses synthetic acts so it
    doesn't depend on the live ledger; runs through the real embedder (skips if
    the embedder isn't producing vectors)."""
    import trinity_local.me.correction_lens as cl

    class _Act:
        def __init__(self, sac, pri):
            self.sacrificed, self.privileged = sac, pri

    acts = [
        _Act("explain the general concept and underlying theory at length",
             "give me the exact command to run")
        for _ in range(cl._MIN_CORRECTIONS + 3)
    ]
    monkeypatch.setattr(cl, "iter_preference_acts", lambda: acts, raising=False)
    import trinity_local.me.preference_acts as pa
    monkeypatch.setattr(pa, "iter_preference_acts", lambda: acts)

    sig = cl.taste_signature()
    if not sig.get("ready"):
        import pytest
        pytest.skip(f"signature not ready (no embedder?): {sig}")
    assert sig["n"] == len(acts)
    assert isinstance(sig["adjectives"], list) and sig["adjectives"]
    rep = sig["representative"]
    assert set(rep.keys()) == {"model_offered", "you_wanted", "alignment"}
    assert rep["you_wanted"] and rep["model_offered"]


def test_taste_signature_thin_ledger(monkeypatch):
    import trinity_local.me.correction_lens as cl
    import trinity_local.me.preference_acts as pa
    monkeypatch.setattr(pa, "iter_preference_acts", lambda: [])
    assert cl.taste_signature().get("ready") is False
