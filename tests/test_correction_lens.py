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
