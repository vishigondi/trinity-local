"""Tests for two degraded-first-run hardening tasks.

#234 — `maybe_kick_lens_refresh()` cross-process lock: when several MCP
harnesses connect concurrently, only ONE may win the right to rebuild the
lens. The pure-read gate (`should_refresh_lens` + `_recently_kicked`) cannot
serialize concurrent racers, so an atomic `O_CREAT | O_EXCL` lock arbitrates.

#238 — degraded-state honesty: a partial install must degrade gracefully AND
tell the user the truth. We pin the two surfaces that previously degraded
SILENTLY: the MLX→TF-IDF embedding fallback (the #185/#186 latent lens-quality
hit) and a single-provider "reduced" council.
"""
from __future__ import annotations

import datetime as dt
import json
import threading

import pytest


def _ago(hours: float) -> str:
    return (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=hours)).isoformat()


def _seed_refreshable_state(monkeypatch):
    """Open the refresh gate: a lens exists, the build is >24h old, and the
    corpus grew by ≥5 prompts."""
    import trinity_local.me_builder as mb
    from trinity_local.me_builder import _lens_build_state_path, me_path

    p = me_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("# Lens\n", encoding="utf-8")
    sp = _lens_build_state_path()
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text(
        json.dumps({"built_at": _ago(48), "fingerprint": "100:aaa"}),
        encoding="utf-8",
    )
    monkeypatch.setattr(mb, "_corpus_fingerprint", lambda: "110:bbb")


# ── #234: cross-process refresh lock ──────────────────────────────────────


@pytest.mark.usefixtures("patch_trinity_home")
class TestRefreshLock:
    def _enable_autoscan(self, monkeypatch):
        monkeypatch.setenv("TRINITY_AUTOSCAN_DISABLED", "0")

    def test_claim_is_exclusive_then_releasable(self, monkeypatch):
        from trinity_local.cold_start import (
            _release_refresh_lock,
            _try_claim_refresh_lock,
            lens_refresh_lock_path,
        )

        assert _try_claim_refresh_lock() is True       # first wins
        assert lens_refresh_lock_path().exists()
        assert _try_claim_refresh_lock() is False       # second is locked out
        _release_refresh_lock()
        assert not lens_refresh_lock_path().exists()
        assert _try_claim_refresh_lock() is True        # reclaimable after release

    def test_stale_lock_is_reclaimed(self, monkeypatch):
        import os

        from trinity_local.cold_start import (
            _REFRESH_LOCK_STALE_S,
            _try_claim_refresh_lock,
            lens_refresh_lock_path,
        )

        # An abandoned lock from a crashed owner.
        lock = lens_refresh_lock_path()
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock.write_text("99999|old", encoding="utf-8")
        old = dt.datetime.now().timestamp() - (_REFRESH_LOCK_STALE_S + 60)
        os.utime(lock, (old, old))

        # A fresh caller reclaims the stale lock and wins.
        assert _try_claim_refresh_lock() is True

    def test_only_one_concurrent_kick_rebuilds(self, monkeypatch):
        """The headline #234 regression: N harnesses pass the pure-read gate
        in the same instant; exactly one rebuild must fire."""
        import trinity_local.me_builder as mb
        from trinity_local.cold_start import maybe_kick_lens_refresh

        self._enable_autoscan(monkeypatch)
        _seed_refreshable_state(monkeypatch)

        build_calls: list[int] = []
        gate = threading.Event()

        def _slow_build(*a, **k):
            build_calls.append(1)
            # Hold the lock so a racing caller can't see it released.
            gate.wait(timeout=2.0)
            return (mb.me_path(), {"ok": True})

        monkeypatch.setattr(mb, "build_me_via_lens_pipeline", _slow_build)
        # Defeat the single-process cooldown so the LOCK is the only guard
        # under test (the cooldown marker is written, but we force it open).
        monkeypatch.setattr(
            "trinity_local.cold_start._recently_kicked", lambda: False
        )

        results: list[object] = []
        barrier = threading.Barrier(4)

        def _connect():
            barrier.wait()
            results.append(maybe_kick_lens_refresh())

        threads = [threading.Thread(target=_connect) for _ in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=3.0)

        kicked = [r for r in results if r and r.get("status") == "kicked"]
        assert len(kicked) == 1, f"exactly one harness should kick, got {results}"

        gate.set()
        # Give the background rebuild thread a moment to finish + release.
        for _ in range(50):
            if build_calls:
                break
            threading.Event().wait(0.02)
        assert build_calls == [1], "the rebuild must run exactly once"

    def test_lock_released_even_when_build_raises(self, monkeypatch):
        import time as _time

        import trinity_local.me_builder as mb
        from trinity_local.cold_start import (
            lens_refresh_lock_path,
            maybe_kick_lens_refresh,
        )

        self._enable_autoscan(monkeypatch)
        _seed_refreshable_state(monkeypatch)
        monkeypatch.setattr(
            "trinity_local.cold_start._recently_kicked", lambda: False
        )

        def _boom(*a, **k):
            raise RuntimeError("rebuild blew up")

        monkeypatch.setattr(mb, "build_me_via_lens_pipeline", _boom)

        assert maybe_kick_lens_refresh()["status"] == "kicked"
        # The failing background thread must still release the lock.
        for _ in range(100):
            if not lens_refresh_lock_path().exists():
                break
            _time.sleep(0.02)
        assert not lens_refresh_lock_path().exists()


# ── #238: degraded-state honesty ──────────────────────────────────────────


class TestEmbeddingBackendHonesty:
    def test_tfidf_fallback_is_surfaced_not_silent(self, monkeypatch):
        import trinity_local.health_checks as hc

        monkeypatch.setattr(hc, "_check_embedding_backend", hc._check_embedding_backend)
        monkeypatch.setattr(
            "trinity_local.embeddings.get_backend", lambda: "tfidf", raising=False
        )
        monkeypatch.setattr(
            "trinity_local.embeddings.is_available", lambda: False, raising=False
        )
        monkeypatch.setattr(
            "trinity_local.embeddings.mlx_actually_loaded", lambda: False, raising=False
        )

        result = hc._check_embedding_backend()
        # Soft (still runs) but HONEST about reduced tension quality.
        assert result.ok is True
        assert "TF-IDF" in result.detail
        assert "reduced" in result.detail.lower() or "keyword" in result.detail.lower()
        assert result.fix  # gives the upgrade path

    def test_mlx_imported_but_no_model_is_surfaced(self, monkeypatch):
        import trinity_local.health_checks as hc

        monkeypatch.setattr(
            "trinity_local.embeddings.get_backend", lambda: "mlx", raising=False
        )
        monkeypatch.setattr(
            "trinity_local.embeddings.is_available", lambda: True, raising=False
        )
        monkeypatch.setattr(
            "trinity_local.embeddings.mlx_actually_loaded", lambda: False, raising=False
        )

        result = hc._check_embedding_backend()
        assert result.ok is True
        assert "not downloaded" in result.detail
        assert "huggingface-cli download" in result.fix

    def test_mlx_live_says_so(self, monkeypatch):
        import trinity_local.health_checks as hc

        monkeypatch.setattr(
            "trinity_local.embeddings.get_backend", lambda: "mlx", raising=False
        )
        monkeypatch.setattr(
            "trinity_local.embeddings.is_available", lambda: True, raising=False
        )
        monkeypatch.setattr(
            "trinity_local.embeddings.mlx_actually_loaded", lambda: True, raising=False
        )

        result = hc._check_embedding_backend()
        assert result.ok is True
        assert "MLX" in result.detail and "live" in result.detail.lower()
        assert not result.fix


class TestCouncilBreadthHonesty:
    def _stub_providers(self, monkeypatch, ready: set[str]):
        import trinity_local.health_checks as hc

        def _fake_check_provider(provider, cli):
            return hc.CheckResult(name=f"provider:{provider}", ok=provider in ready)

        monkeypatch.setattr(hc, "_check_provider", _fake_check_provider)

    def test_two_providers_is_full_council(self, monkeypatch):
        import trinity_local.health_checks as hc

        self._stub_providers(monkeypatch, {"claude", "codex"})
        result = hc._check_council_breadth()
        assert result.ok is True
        assert "full" in result.detail.lower()

    def test_one_provider_is_honest_reduced_signal(self, monkeypatch):
        import trinity_local.health_checks as hc

        self._stub_providers(monkeypatch, {"claude"})
        result = hc._check_council_breadth()
        # Soft gap (councils still run) but the truth is told.
        assert result.ok is False
        assert "REDUCED" in result.detail or "reduced" in result.detail
        assert result.fix

    def test_zero_providers_says_cannot_run(self, monkeypatch):
        import trinity_local.health_checks as hc

        self._stub_providers(monkeypatch, set())
        result = hc._check_council_breadth()
        assert result.ok is False
        assert "no providers" in result.detail.lower()

    def test_reduced_council_still_ready_for_council(self, monkeypatch):
        """The honesty signal must NOT flip `ready_for_council` to False —
        one authed provider is still a runnable (reduced) council."""
        import trinity_local.health_checks as hc

        # writable home + exactly one provider authed; everything else stubbed
        # to a passing soft check so we isolate ready_for_council semantics.
        self._stub_providers(monkeypatch, {"claude"})
        report = hc.DoctorReport()
        report.checks.append(
            hc.CheckResult(name="trinity_home_writeable", ok=True)
        )
        report.checks.append(hc._check_provider("claude", "claude"))
        report.checks.append(hc._check_provider("codex", "codex"))
        report.checks.append(hc._check_council_breadth())
        assert report.ready_for_council is True
