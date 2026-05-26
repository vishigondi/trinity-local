"""Tests for the launchpad "Build deeper memory" card.

Surfaces the ~600 MB nomic-embed model as an explicit opt-in instead of
a surprise mid-lens-build crash. Card only shows when the user has
PROMPTS INDEXED (has signal that would benefit from embeddings) AND
the model isn't already in HF cache. Cold install → no card.
Everything wired → no card.
"""
from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
    return tmp_path


def _write_prompts(home: Path, num_records: int = 5) -> None:
    """Drop a prompt_nodes.jsonl with N indexed records so the
    helper sees prompts_indexed=True."""
    prompts_dir = home / "prompts"
    prompts_dir.mkdir(parents=True, exist_ok=True)
    (prompts_dir / "prompt_nodes.jsonl").write_text(
        "\n".join(
            f'{{"node_id":"p{i}","text":"hello world {i} hello world {i}"}}'
            for i in range(num_records)
        )
    )


def _seed_hf_cache(tmp_home: Path, monkeypatch, model_present: bool) -> None:
    """Patch Path.home to return tmp_home AND optionally populate the
    nomic snapshot dir under ~/.cache/huggingface/hub."""
    monkeypatch.setattr(Path, "home", lambda: tmp_home)
    if model_present:
        snapshot = (
            tmp_home / ".cache" / "huggingface" / "hub"
            / "models--nomic-ai--nomic-embed-text-v1.5"
            / "snapshots" / "abc123"
        )
        snapshot.mkdir(parents=True, exist_ok=True)
        # Drop at least one weight file so the helper's "any iterdir"
        # check fires.
        (snapshot / "model.safetensors").write_bytes(b"\x00" * 16)


# ─── Helper combinatorics ──────────────────────────────────────────

class TestEmbedderStatus:
    def test_no_prompts_no_card(self, isolated_home, monkeypatch):
        """Cold install: no prompts indexed → don't surface the card.
        The user has nothing to embed yet; nagging them about a ~600 MB
        download is noise."""
        from trinity_local.launchpad_data import _embedder_status
        _seed_hf_cache(isolated_home, monkeypatch, model_present=False)
        status = _embedder_status()
        assert status["promptsIndexed"] is False
        assert status["modelDownloaded"] is False
        assert status["show"] is False

    def test_prompts_indexed_model_missing_shows_card(
        self, isolated_home, monkeypatch
    ):
        """The real upsell case: user has prompts (would benefit from
        deeper memory) but the model isn't downloaded yet."""
        from trinity_local.launchpad_data import _embedder_status
        _write_prompts(isolated_home)
        _seed_hf_cache(isolated_home, monkeypatch, model_present=False)
        status = _embedder_status()
        assert status["promptsIndexed"] is True
        assert status["modelDownloaded"] is False
        assert status["show"] is True
        # Download command must include the exact model id so the user
        # can paste it verbatim.
        assert "nomic-ai/nomic-embed-text-v1.5" in status["downloadCommand"]

    def test_prompts_indexed_model_present_hides_card(
        self, isolated_home, monkeypatch
    ):
        """Once the model is downloaded, the card disappears — no
        more nagging."""
        from trinity_local.launchpad_data import _embedder_status
        _write_prompts(isolated_home)
        _seed_hf_cache(isolated_home, monkeypatch, model_present=True)
        status = _embedder_status()
        assert status["promptsIndexed"] is True
        assert status["modelDownloaded"] is True
        assert status["show"] is False

    def test_download_command_includes_pip_install_when_mlx_missing(
        self, isolated_home, monkeypatch
    ):
        """If sentence-transformers isn't installed, the download
        command on its own won't help — pip install [mlx] has to come
        first. Helper concatenates them so the user pastes one line."""
        from trinity_local import launchpad_data
        _write_prompts(isolated_home)
        _seed_hf_cache(isolated_home, monkeypatch, model_present=False)
        # Simulate MLX libs not importable.
        import sys
        original = sys.modules.get("trinity_local.embeddings")
        try:
            # Force `embeddings.is_available()` to return False by
            # patching the reference the helper goes through.
            monkeypatch.setattr(
                "trinity_local.embeddings.is_available", lambda: False
            )
            status = launchpad_data._embedder_status()
            assert "pip install" in status["downloadCommand"]
            assert "trinity-local[mlx]" in status["downloadCommand"]
        finally:
            if original is not None:
                sys.modules["trinity_local.embeddings"] = original

    def test_empty_prompt_file_does_not_count_as_indexed(
        self, isolated_home, monkeypatch
    ):
        """A prompt_nodes.jsonl that exists but is empty (or a tiny
        skeleton from cold-start) shouldn't trigger the card — that's
        not real signal."""
        from trinity_local.launchpad_data import _embedder_status
        prompts_dir = isolated_home / "prompts"
        prompts_dir.mkdir(parents=True, exist_ok=True)
        (prompts_dir / "prompt_nodes.jsonl").write_text("")  # truly empty
        _seed_hf_cache(isolated_home, monkeypatch, model_present=False)
        status = _embedder_status()
        assert status["promptsIndexed"] is False
        assert status["show"] is False


# ─── Page data integration ─────────────────────────────────────────

class TestEmbedderStatusInPageData:
    def test_page_data_includes_embedder_status(
        self, isolated_home, monkeypatch
    ):
        """The launchpad template gates the card on
        `pageData.embedderStatus.show`. Drift here = the card silently
        never renders."""
        from trinity_local import launchpad_data
        monkeypatch.setattr("shutil.which", lambda n: None)
        _seed_hf_cache(isolated_home, monkeypatch, model_present=True)
        # Stub heavier dependencies.
        monkeypatch.setattr(launchpad_data, "build_elo_snapshot", lambda: {})
        monkeypatch.setattr(launchpad_data, "_elo_chart_data", lambda s: {})
        monkeypatch.setattr(launchpad_data, "get_global_benchmarks", lambda: {})
        monkeypatch.setattr(launchpad_data, "_provider_health_data", lambda: {
            "providers": [], "missingCount": 0, "hasMissing": False, "footerNote": ""
        })
        monkeypatch.setattr(launchpad_data, "_active_launchpad_operation", lambda: None)
        monkeypatch.setattr(launchpad_data, "_load_personal_routing_table", lambda: {})

        data = launchpad_data.build_page_data(
            live_review_path=isolated_home / "live.html",
            recent_councils=[],
        )
        assert "embedderStatus" in data
        es = data["embedderStatus"]
        assert "show" in es
        assert "modelDownloaded" in es
        assert "promptsIndexed" in es
        assert "downloadCommand" in es
