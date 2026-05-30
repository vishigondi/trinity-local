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
