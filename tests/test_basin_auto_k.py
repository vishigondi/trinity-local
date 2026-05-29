"""#245 follow-on: corpus-size-aware basin count.

A fixed k=20 junk-drawered on the real clean corpus — once the 2026-05-12
scaffolding pollution was purged, 28.6k threads packed 29.6% into one b00
basin at k=20, above the 20% junk-drawer ceiling the real_corpus guard
enforces. `auto_k` scales the basin count with the corpus (≈1 basin per
650 threads, clamped to [20, 60]) so no single basin dominates as history
grows. These guards pin the clamp boundaries + that an explicit k still wins.
"""
from __future__ import annotations

from trinity_local.me.basins import _DEFAULT_K, _MAX_K, auto_k


def test_small_corpus_floors_at_historical_default():
    # Behaviour-preserving for fresh/small installs: below ~13k threads,
    # auto_k stays at the historical k=20 so nothing changes for them.
    assert auto_k(0) == _DEFAULT_K
    assert auto_k(500) == _DEFAULT_K
    assert auto_k(5_000) == _DEFAULT_K
    assert auto_k(13_000) == _DEFAULT_K  # 13000/650 = 20 → floor boundary


def test_large_corpus_scales_up():
    # The clean corpus that exposed the bug: 28,618 threads.
    # 28618/650 ≈ 44 — comfortably above the k=40 that first cleared
    # the 20% junk-drawer ceiling.
    k = auto_k(28_618)
    assert 40 <= k <= 50, f"expected ~44 for the 28.6k corpus, got {k}"


def test_huge_corpus_caps_at_max():
    # Don't fragment the topic map into uselessly many basins.
    assert auto_k(100_000) == _MAX_K
    assert auto_k(10_000_000) == _MAX_K


def test_monotonic_non_decreasing():
    # More history never yields fewer basins.
    ks = [auto_k(n) for n in (0, 1_000, 13_000, 20_000, 30_000, 50_000, 200_000)]
    assert ks == sorted(ks), f"auto_k must be non-decreasing in corpus size, got {ks}"


def test_explicit_k_never_consults_auto(monkeypatch):
    # compute_basins(k=N) must use N verbatim — the CLI --k-basins escape
    # hatch + every existing test (k=1,2,3,5) rely on this. The contract is
    # the branch `auto_k(...) if k is None else k`: an explicit k must never
    # invoke auto_k. Spy on auto_k and assert it stays untouched.
    import trinity_local.me.basins as basins_mod

    called = {"auto": False}
    real_auto = basins_mod.auto_k
    monkeypatch.setattr(
        basins_mod, "auto_k",
        lambda n: (called.__setitem__("auto", True), real_auto(n))[1],
    )
    basins_mod.compute_basins(k=3, seed=42)  # empty or real corpus — either way
    assert called["auto"] is False, "explicit k must not consult auto_k"


def test_default_consults_auto(monkeypatch):
    # The mirror: k=None (the production default) DOES consult auto_k —
    # but only once the corpus is loaded (a fully empty corpus short-circuits
    # before the k branch, which is fine). Guard the wiring on a stubbed
    # non-empty thread set is heavy; instead assert the default arg is None
    # so the auto path is reachable at all (the regression that would break
    # it is a stray k=20 default sneaking back in).
    import inspect

    from trinity_local.me.basins import compute_basins
    from trinity_local.me.pipeline import stage1_basins

    assert inspect.signature(compute_basins).parameters["k"].default is None
    assert inspect.signature(stage1_basins).parameters["k"].default is None
