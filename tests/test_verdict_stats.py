"""Verdict-capture stats on the launchpad — gates the moat thesis.

Trinity's "personal ledger of cross-model preferences" only exists for
councils the user actually rates. Tick #69's data audit found 3 of 19
outcomes carried verdicts (16%) on the dev install; surfacing that on
the launchpad is how the user notices the gap (task #110).

These tests exercise the pure aggregator (_verdict_stats) against
synthetic outcomes in an isolated TRINITY_HOME, and the build_page_data
plumbing that ships it to the template.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
    (tmp_path / "council_outcomes").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _write_outcome(home: Path, council_id: str, *, with_verdict: bool) -> Path:
    """Synthesize a minimal council_outcome JSON in the isolated home."""
    metadata: dict = {}
    if with_verdict:
        metadata["user_verdict"] = {"user_winner": "claude"}
    payload = {
        "council_run_id": council_id,
        "bundle_id": f"bundle_{council_id}",
        "metadata": metadata,
    }
    path = home / "council_outcomes" / f"{council_id}.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class TestVerdictStats:
    """_verdict_stats walks council_outcomes/*.json and counts how many
    carry metadata.user_verdict.user_winner."""

    def test_empty_install_returns_zero(self, isolated_home):
        from trinity_local.launchpad_data import _verdict_stats
        stats = _verdict_stats()
        assert stats == {
            "total": 0,
            "rated": 0,
            "rate": 0.0,
            "threads_total": 0,
            "threads_rated": 0,
        }

    def test_counts_rated_vs_unrated(self, isolated_home):
        _write_outcome(isolated_home, "council_a", with_verdict=True)
        _write_outcome(isolated_home, "council_b", with_verdict=False)
        _write_outcome(isolated_home, "council_c", with_verdict=False)
        from trinity_local.launchpad_data import _verdict_stats
        stats = _verdict_stats()
        assert stats["total"] == 3
        assert stats["rated"] == 1
        assert stats["rate"] == pytest.approx(1 / 3)
        # Tick #98: thread-level fields. Each test outcome here gets a
        # unique chain_root_id via bundle_id, so threads should equal
        # outcomes when there are no multi-round chains.
        assert stats["threads_total"] == 3
        assert stats["threads_rated"] == 1

    def test_multi_round_chain_counts_one_thread_per_chain(self, isolated_home):
        """Real corpus shape: a chain refinement has multiple outcomes
        but ONE chain_root_id. The thread-level count groups them, so
        the launchpad eyebrow matches what the user sees in cards."""
        import json as _json
        # Three rounds of one chain, plus one standalone — 4 outcomes,
        # 2 threads. One round of the chain is rated → thread is rated.
        # Filenames must start with "council_" to match the glob in
        # _verdict_stats (it's how Trinity distinguishes outcome files
        # from manifest sidecars like `_thread_*.js`).
        for i, with_verdict in enumerate([False, True, False]):
            metadata = {
                "chain_root_id": "bundle_chain1",
                "task_text": f"round {i}",
            }
            if with_verdict:
                metadata["user_verdict"] = {"user_winner": "claude"}
            (isolated_home / "council_outcomes" / f"council_chain_round_{i}.json").write_text(
                _json.dumps({
                    "council_run_id": f"council_chain_round_{i}",
                    "bundle_id": "bundle_chain1",
                    "metadata": metadata,
                })
            )
        # Standalone — unrated
        (isolated_home / "council_outcomes" / "council_standalone.json").write_text(
            _json.dumps({
                "council_run_id": "council_standalone",
                "bundle_id": "bundle_standalone",
                "metadata": {"task_text": "standalone q"},
            })
        )
        from trinity_local.launchpad_data import _verdict_stats
        stats = _verdict_stats()
        assert stats["total"] == 4
        assert stats["rated"] == 1
        # 2 distinct threads, 1 has any-rated → threads_rated = 1
        assert stats["threads_total"] == 2
        assert stats["threads_rated"] == 1

    def test_unparseable_outcomes_skipped_silently(self, isolated_home):
        """A corrupt JSON file in the outcomes dir must not break the
        whole launchpad render — the count just excludes that file."""
        _write_outcome(isolated_home, "council_good", with_verdict=True)
        bad = isolated_home / "council_outcomes" / "council_bad.json"
        bad.write_text("{not valid json", encoding="utf-8")
        from trinity_local.launchpad_data import _verdict_stats
        stats = _verdict_stats()
        assert stats["total"] == 1  # good only
        assert stats["rated"] == 1


class TestPageDataVerdictStats:
    """Plumbing test: build_page_data exposes verdictStats so the launchpad
    template can render the "N of M rated" eyebrow without re-walking outcomes."""

    def test_page_data_contains_verdict_stats(self, isolated_home, tmp_path):
        from trinity_local.launchpad_data import build_page_data
        _write_outcome(isolated_home, "council_a", with_verdict=True)
        _write_outcome(isolated_home, "council_b", with_verdict=False)
        data = build_page_data(
            live_review_path=tmp_path / "live_council.html",
            recent_councils=[],
        )
        assert "verdictStats" in data
        assert data["verdictStats"]["total"] == 2
        assert data["verdictStats"]["rated"] == 1

    def test_cold_install_has_zero_filled_stats(self, isolated_home, tmp_path):
        """No outcomes → stats present with zeros, not missing — frontend
        v-if guards on rate < 0.5 + total >= 5 stay simple."""
        from trinity_local.launchpad_data import build_page_data
        data = build_page_data(
            live_review_path=tmp_path / "live_council.html",
            recent_councils=[],
        )
        assert data["verdictStats"] == {
            "total": 0,
            "rated": 0,
            "rate": 0.0,
            "threads_total": 0,
            "threads_rated": 0,
        }


class TestShortcutStatus:
    """The macOS Shortcut dispatcher was retired 2026-05-17. `_shortcut_status`
    survives only as a backward-compat stub so old payload consumers don't
    crash — it always reports applicable=False. The banner that used to
    surface a missing-Shortcut warning is gone; the dispatch-readiness
    banner (Phase 7 doctor check) is the canonical surface."""

    def test_always_returns_not_applicable(self):
        from trinity_local.launchpad_data import _shortcut_status
        result = _shortcut_status()
        assert result == {"ok": True, "applicable": False}

    def test_page_data_contains_shortcut_status(self, isolated_home, tmp_path):
        from trinity_local.launchpad_data import build_page_data
        data = build_page_data(
            live_review_path=tmp_path / "live_council.html",
            recent_councils=[],
        )
        assert "shortcutStatus" in data
        assert data["shortcutStatus"]["applicable"] is False

    def test_launchpad_html_contains_lens_rebuild_chip(self, isolated_home):
        """Tick #76 — lens card gets a rebuild chip when lens exists.
        Closes the forward-arc gap "See a rejected lens → rebuild
        lens.md link." Same shape as Surface 18's rebuild chips for
        picks/core in the memory viewer."""
        from trinity_local.launchpad_page import render_launchpad_html
        html = render_launchpad_html()
        # The chip-firing handler + flash key
        assert "copyText('trinity-local lens-build', 'lens-rebuild')" in html
        # The v-if guard so the chip stays hidden in the empty-state
        # (where the bare command is shown in a code block instead)
        assert "v-if=\"tasteLenses\"" in html
        # The flash-on-copy text — pinning the rebuild action's
        # confirmation cycle (same 2400ms reset as copyHealthCommand)
        assert "copiedKey === 'lens-rebuild'" in html

    def test_launchpad_html_contains_cortex_rebuild_chip(self, isolated_home):
        """Tick #77 — cortex/routing card gets the same in-page rebuild
        chip as the lens card. consolidate is the command that turns
        new council outcomes into routing patterns; without an in-page
        affordance the user had to remember it. Same pattern as #76."""
        from trinity_local.launchpad_page import render_launchpad_html
        html = render_launchpad_html()
        assert "copyText('trinity-local consolidate', 'cortex-rebuild')" in html
        assert "copiedKey === 'cortex-rebuild'" in html

    def test_provider_install_button_has_flash_feedback(self, isolated_home):
        """Tick #82 — provider install ⧉ button gets ✓ flash feedback
        when clicked. Same shape as the rebuild chips: copyText now
        accepts (value, flashKey), and the button content swaps based
        on `copiedKey === '<key>'`. Catches a regression that drops
        the flash key — the button would still copy but the user
        would have no idea the click registered."""
        from trinity_local.launchpad_page import render_launchpad_html
        html = render_launchpad_html()
        # The flashKey arg distinguishes per-provider clicks; key shape
        # must be 'install-' + provider name so simultaneous installs
        # don't share a flash key.
        assert "copyText(provider.installCommand, 'install-' + provider.provider)" in html
        # The conditional render that drives the icon swap
        assert "copiedKey === 'install-' + provider.provider" in html

    def test_recent_cards_show_unrated_badge(self, isolated_home, tmp_path):
        """Tick #94 — recent cards visually distinguish unrated vs
        rated councils. An unrated thread (no segment carries
        metadata.user_verdict.user_winner) gets a small badge in the
        eyebrow; a rated thread renders the bare 'Thread' eyebrow.

        Surfaces Pillar 4 (rate funnel) AT the click target — the
        cards already click through to the live council where rating
        happens; the badge tells the user WHICH cards need their
        attention without opening each one.
        """
        import json as _json
        # Two threads: one rated, one not. The function under test
        # (build_recent_cards_html) takes the same recent_councils
        # dict shape that _load_recent_councils emits, so we can
        # test it directly without needing a full corpus on disk.
        from trinity_local.launchpad_data import build_recent_cards_html
        recent = [
            {
                "council_id": "council_rated",
                "chain_root_id": "council_rated",
                "title": "Rated council",
                "winner_provider": "claude",
                "created_at": "2026-05-13T10:00:00+00:00",
                "segment_count": 1,
                "task_type": None,
                "rated": True,
                "review_page_path": str(tmp_path / "live_council.html"),
            },
            {
                "council_id": "council_unrated",
                "chain_root_id": "council_unrated",
                "title": "Unrated council",
                "winner_provider": "codex",
                "created_at": "2026-05-13T11:00:00+00:00",
                "segment_count": 1,
                "task_type": None,
                "rated": False,
                "review_page_path": str(tmp_path / "live_council.html"),
            },
        ]
        html = build_recent_cards_html(recent)
        # The unrated card has the badge
        assert "Unrated council" in html
        assert "unrated-badge" in html
        # Count exactly one badge — the rated card must NOT have it
        assert html.count("unrated-badge") == 1, (
            "Rated card should NOT carry the Unrated badge — got "
            f"{html.count('unrated-badge')} badges for 1 unrated + 1 rated"
        )

    def test_rebuild_chips_use_shared_css_class(self, isolated_home):
        """Tick #80 — both launchpad rebuild chips share the
        `.lp-rebuild-chip` CSS class instead of duplicating ~200-char
        inline styles. Principle #11 (shared UI primitives) at the CSS
        layer. Drift target: a future hand-styled chip that misses the
        class would render with bare-button look instead of the
        unified pill."""
        from trinity_local.launchpad_page import render_launchpad_html
        html = render_launchpad_html()
        # Class definition exists
        assert ".lp-rebuild-chip {" in html, (
            "CSS rule for .lp-rebuild-chip was dropped — the rebuild "
            "pills will fall back to default browser button styling"
        )
        # Both chips reference it (not just one); the launchpad has at
        # least two chips today (lens + cortex). Counting catches the
        # case where a future chip forgets the class.
        assert html.count('class="lp-rebuild-chip"') >= 2, (
            "fewer than 2 chips use the shared class — verify rebuild "
            "chips on lens + cortex cards both opt in"
        )


class TestHandoffNudge:
    """The launchpad handoff demo nudge (post-#115 browser-side mirror
    of the doctor CLI hint)."""

    def test_silent_when_no_config(self, isolated_home, monkeypatch):
        """Empty config → no providers → no nudge."""
        from trinity_local.config import AppConfig
        empty_cfg = AppConfig(
            max_turns=4, default_task_kind="general", notifications=True,
            providers={},
            role_preferences={}, task_preferences={},
        )
        monkeypatch.setattr("trinity_local.launchpad_data.load_config",
                            lambda required=False: empty_cfg)
        from trinity_local.launchpad_data import _handoff_nudge
        result = _handoff_nudge()
        assert result["applicable"] is False
        assert result["target"] is None
        assert result["source_count"] == 0

    def test_silent_when_only_one_provider(self, isolated_home, monkeypatch):
        """Handoff needs ≥2 providers. With one, the demo can't run —
        don't suggest it."""
        from trinity_local.config import AppConfig, ProviderConfig
        cfg = AppConfig(
            max_turns=4, default_task_kind="general", notifications=True,
            providers={"claude": ProviderConfig(
                name="claude", type="cli", enabled=True, label="Claude",
                command=["claude"], args=[], roles={"thinker"},
                task_types=set(), model="claude-opus",
            )},
            role_preferences={}, task_preferences={},
        )
        monkeypatch.setattr("trinity_local.launchpad_data.load_config", lambda required=False: cfg)
        from trinity_local.launchpad_data import _handoff_nudge
        assert _handoff_nudge()["applicable"] is False

    def test_silent_when_no_prompts_indexed(self, isolated_home, monkeypatch):
        """≥2 providers but empty prompt index → handoff has no
        context to package. Don't suggest until seed has run."""
        from trinity_local.config import AppConfig, ProviderConfig
        cfg = AppConfig(
            max_turns=4, default_task_kind="general", notifications=True,
            providers={
                "claude": ProviderConfig(name="claude", type="cli", enabled=True, label="Claude",
                    command=["claude"], args=[], roles={"thinker"}, task_types=set(), model="x"),
                "gemini": ProviderConfig(name="gemini", type="cli", enabled=True, label="Gemini",
                    command=["gemini"], args=[], roles={"thinker"}, task_types=set(), model="y"),
            },
            role_preferences={}, task_preferences={},
        )
        monkeypatch.setattr("trinity_local.launchpad_data.load_config", lambda required=False: cfg)
        # iter_prompt_nodes returns empty on a clean home
        from trinity_local.launchpad_data import _handoff_nudge
        result = _handoff_nudge()
        # Conditions met (≥2 providers) but no prompts → target is set
        # but applicable=False
        assert result["target"] in ("gemini", "claude")  # something picked
        assert result["applicable"] is False
        assert result["source_count"] == 0

    def test_fires_with_2_providers_and_prompts(self, isolated_home, monkeypatch):
        """The conditions the doctor hint uses — mirrored here."""
        from trinity_local.config import AppConfig, ProviderConfig
        from trinity_local.memory.schemas import PromptNode
        from trinity_local.memory.store import upsert_prompt_node

        cfg = AppConfig(
            max_turns=4, default_task_kind="general", notifications=True,
            providers={
                "claude": ProviderConfig(name="claude", type="cli", enabled=True, label="Claude",
                    command=["claude"], args=[], roles={"thinker"}, task_types=set(), model="x"),
                "gemini": ProviderConfig(name="gemini", type="cli", enabled=True, label="Gemini",
                    command=["gemini"], args=[], roles={"thinker"}, task_types=set(), model="y"),
            },
            role_preferences={}, task_preferences={},
        )
        monkeypatch.setattr("trinity_local.launchpad_data.load_config", lambda required=False: cfg)
        upsert_prompt_node(PromptNode(
            id="pn_1", transcript_id="t1", provider="claude",
            source_path="/fake.json", turn_index=0, text="some prompt",
            embedding=None, created_at="2026-05-14T10:00:00",
            timestamp="2026-05-14T10:00:00",
            preceding_assistant_text="", following_assistant_text="",
            themes=[],
        ))
        from trinity_local.launchpad_data import _handoff_nudge
        result = _handoff_nudge()
        assert result["applicable"] is True
        assert result["target"] == "gemini"  # non-claude target preferred
        assert result["source_count"] >= 1

    def test_skips_mlx_provider_for_handoff_target(self, isolated_home, monkeypatch):
        """The handoff CLI dispatches via the CLI-provider path. MLX
        (local model) doesn't have a CLI handoff surface — exclude it
        from the target list so we don't suggest `handoff mlx`."""
        from trinity_local.config import AppConfig, ProviderConfig
        cfg = AppConfig(
            max_turns=4, default_task_kind="general", notifications=True,
            providers={
                "claude": ProviderConfig(name="claude", type="cli", enabled=True, label="Claude",
                    command=["claude"], args=[], roles={"thinker"}, task_types=set(), model="x"),
                "mlx": ProviderConfig(name="mlx", type="mlx", enabled=True, label="MLX",
                    command=["python", "-m", "mlx_lm.generate"], args=[],
                    roles={"thinker"}, task_types=set(), model="local"),
            },
            role_preferences={}, task_preferences={},
        )
        monkeypatch.setattr("trinity_local.launchpad_data.load_config", lambda required=False: cfg)
        from trinity_local.launchpad_data import _handoff_nudge
        result = _handoff_nudge()
        # Only one valid CLI-class provider (claude) → can't handoff
        assert result["applicable"] is False
        assert result["target"] is None or result["target"] != "mlx"

    def test_handoff_nudge_wired_into_build_page_data(self):
        """Source-level wiring check: build_page_data references
        handoffNudge in its return dict. Calling build_page_data with
        real kwargs is too heavy for a unit test (requires recent_councils,
        live review state, etc.), but asserting the source code mentions
        the key is enough to catch removal-by-refactor."""
        from pathlib import Path
        src = Path(__file__).resolve().parents[1] / "src/trinity_local/launchpad_data.py"
        text = src.read_text(encoding="utf-8")
        assert "\"handoffNudge\":" in text or "'handoffNudge':" in text, (
            "build_page_data lost the handoffNudge key — the launchpad "
            "banner has nothing to read from."
        )


class TestEvalSummary:
    """Launchpad-side surface of the eval harness output (post-Surface 29)."""

    def _seed_run_result(self, home: Path, target="gemini", aggregate=0.65, mtime=None):
        evals = home / "evals"
        results = evals / "results"
        results.mkdir(parents=True, exist_ok=True)
        payload = {
            "eval_id": "eval_aaaaaaaaaaaa",
            "target_provider": target,
            "target_model": f"{target}-mock",
            "started_at": "2026-05-14T15:00:00",
            "completed_at": "2026-05-14T15:01:00",
            "items_total": 2,
            "items_completed": 2,
            "items_failed": 0,
            "items": [],
            "aggregate_score": aggregate,
            "by_rejection_type": {
                "REFRAME": {"count": 1, "mean_score": 0.4, "min_score": 0.4, "max_score": 0.4},
                "COMPRESSION": {"count": 1, "mean_score": 0.9, "min_score": 0.9, "max_score": 0.9},
            },
        }
        import json
        path = results / f"eval_{payload['eval_id']}__model_{target}__20260514150000.json"
        path.write_text(json.dumps(payload), encoding="utf-8")
        if mtime is not None:
            import os
            os.utime(path, (mtime, mtime))
        return path

    def _seed_eval_set(self, home: Path):
        evals = home / "evals"
        evals.mkdir(parents=True, exist_ok=True)
        path = evals / "eval_aaaaaaaaaaaa.json"
        path.write_text('{"eval_id": "eval_aaaaaaaaaaaa", "items": []}', encoding="utf-8")
        return path

    def test_empty_state_when_no_evals_dir(self, isolated_home):
        from trinity_local.launchpad_data import _eval_summary
        s = _eval_summary()
        assert s["has_results"] is False
        assert s["eval_set_available"] is False
        assert s["axes"] == []

    def test_empty_state_eval_set_available_flag(self, isolated_home):
        """User built an eval set but never ran it — empty state should
        flip the eval_set_available flag so the CTA points at
        `eval-run`, not `eval-build`."""
        self._seed_eval_set(isolated_home)
        from trinity_local.launchpad_data import _eval_summary
        s = _eval_summary()
        assert s["has_results"] is False
        assert s["eval_set_available"] is True

    def test_populated_when_run_exists(self, isolated_home):
        self._seed_eval_set(isolated_home)
        self._seed_run_result(isolated_home, target="gemini", aggregate=0.67)
        from trinity_local.launchpad_data import _eval_summary
        s = _eval_summary()
        assert s["has_results"] is True
        assert s["target"] == "gemini"
        assert s["model"] == "gemini-mock"
        assert s["aggregate_score"] == pytest.approx(0.67)
        # Per-axis array sorted by mean descending (COMPRESSION 0.9 > REFRAME 0.4)
        assert s["axes"][0]["name"] == "COMPRESSION"
        assert s["axes"][1]["name"] == "REFRAME"
        assert s["total_runs"] == 1

    def test_most_recent_wins_when_multiple_runs(self, isolated_home):
        """Multiple eval-run invocations leave multiple result files;
        the latest by mtime should win the launchpad slot."""
        self._seed_run_result(isolated_home, target="gemini", aggregate=0.50, mtime=1000)
        self._seed_run_result(isolated_home, target="claude", aggregate=0.80, mtime=2000)
        from trinity_local.launchpad_data import _eval_summary
        s = _eval_summary()
        assert s["target"] == "claude"  # newest
        assert s["aggregate_score"] == pytest.approx(0.80)
        assert s["total_runs"] == 2

    def test_comparison_field_present_with_single_run(self, isolated_home):
        """Even single-run installs get a `comparison` list — len 1.
        Template uses `comparison.length >= 2` to decide whether to
        render the leaderboard, so single-run installs render only
        the per-axis bars (correct UX)."""
        self._seed_run_result(isolated_home, target="gemini", aggregate=0.70, mtime=1000)
        from trinity_local.launchpad_data import _eval_summary
        s = _eval_summary()
        assert "comparison" in s
        assert len(s["comparison"]) == 1
        assert s["comparison"][0]["target"] == "gemini"
        assert s["comparison"][0]["aggregate_score"] == pytest.approx(0.70)

    def test_comparison_lists_all_unique_targets_sorted_by_score(self, isolated_home):
        """Three-provider snapshot (the launch-arc #116 deliverable):
        comparison field surfaces all three targets, sorted by
        aggregate_score desc. This is the leaderboard a journalist
        screenshotting the launchpad sees — the wedge only lands when
        multiple providers are visible side-by-side."""
        self._seed_run_result(isolated_home, target="codex", aggregate=0.80, mtime=1000)
        self._seed_run_result(isolated_home, target="gemini", aggregate=0.83, mtime=2000)
        self._seed_run_result(isolated_home, target="claude", aggregate=1.00, mtime=3000)
        from trinity_local.launchpad_data import _eval_summary
        s = _eval_summary()
        assert len(s["comparison"]) == 3
        # Sorted by aggregate score descending (leaderboard order):
        scores = [row["aggregate_score"] for row in s["comparison"]]
        assert scores == [1.00, 0.83, 0.80]
        targets = [row["target"] for row in s["comparison"]]
        assert targets == ["claude", "gemini", "codex"]

    def test_comparison_dedupes_to_most_recent_per_target(self, isolated_home):
        """Multiple runs of the same target (re-runs after model
        version bumps) should produce one row per target — the most
        recent. Otherwise the leaderboard repeats targets and the
        rank order becomes meaningless."""
        # Two gemini runs, second is newer + higher score
        self._seed_run_result(isolated_home, target="gemini", aggregate=0.50, mtime=1000)
        self._seed_run_result(isolated_home, target="gemini", aggregate=0.83, mtime=2000)
        # One claude run between them
        self._seed_run_result(isolated_home, target="claude", aggregate=0.90, mtime=1500)
        from trinity_local.launchpad_data import _eval_summary
        s = _eval_summary()
        assert len(s["comparison"]) == 2  # two unique targets
        # Gemini's most-recent score (0.83), NOT the older 0.50
        gemini_row = next(r for r in s["comparison"] if r["target"] == "gemini")
        assert gemini_row["aggregate_score"] == pytest.approx(0.83)

    def test_malformed_result_falls_back_to_empty_state(self, isolated_home):
        """Per Analytics-never-crash: a corrupted result JSON must not
        bring down the launchpad. Returns empty_state with the
        eval_set_available flag still correct."""
        self._seed_eval_set(isolated_home)
        results = isolated_home / "evals" / "results"
        results.mkdir(parents=True, exist_ok=True)
        (results / "eval_aaaaaaaaaaaa__model_gemini__bogus.json").write_text(
            "{not valid json", encoding="utf-8",
        )
        from trinity_local.launchpad_data import _eval_summary
        s = _eval_summary()
        assert s["has_results"] is False
        assert s["eval_set_available"] is True  # flag still surfaced

    def test_evalSummary_wired_into_build_page_data(self):
        """Source-level wiring check — build_page_data references the
        evalSummary key. Refactor-by-removal would fail this loudly."""
        from pathlib import Path
        src = Path(__file__).resolve().parents[1] / "src/trinity_local/launchpad_data.py"
        text = src.read_text(encoding="utf-8")
        assert "\"evalSummary\":" in text or "'evalSummary':" in text


class TestRateLimitSaves:
    """Launchpad-side surface of the rate-limit-saves metric.

    docs/launch-package.md names this as THE Day-1 number for the
    launch case study. Helper reads dispatch_outcomes.jsonl, returns
    the same shape the CLI metric command does so the launchpad and
    `trinity-local metric rate-limit-saves` can't disagree.
    """

    def _write_outcomes(self, home: Path, entries: list[dict]):
        analytics = home / "analytics"
        analytics.mkdir(parents=True, exist_ok=True)
        path = analytics / "dispatch_outcomes.jsonl"
        with path.open("w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")
        return path

    def test_empty_when_no_analytics_file(self, isolated_home):
        from trinity_local.launchpad_data import _rate_limit_saves
        result = _rate_limit_saves()
        assert result["has_data"] is False
        assert result["total_saves"] == 0
        assert result["save_rate"] == 0.0

    def test_empty_when_no_saves_but_calls_exist(self, isolated_home):
        """If there are dispatch_outcomes but none are saves (all
        primary-succeeded), don't flip has_data — the card should stay
        silent until there's a number worth bragging about."""
        from trinity_local.launchpad_data import _rate_limit_saves
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        self._write_outcomes(isolated_home, [
            {"ts": now, "primary": "claude", "rate_limit_save": False},
            {"ts": now, "primary": "claude", "rate_limit_save": False},
        ])
        result = _rate_limit_saves()
        assert result["has_data"] is False
        assert result["total_calls"] == 2  # still surfaced for diagnostic

    def test_populated_state_shape_matches_cli_metric(self, isolated_home):
        """The launchpad number and `trinity-local metric rate-limit-saves`
        must agree — if they drift, the launch claim and the user's
        verification command will tell different stories.

        Three entries: 2 saves + 1 plain call; primary=claude on
        all saves; failure_kind=rate_limited on one, auth_failed on
        the other.
        """
        from trinity_local.launchpad_data import _rate_limit_saves
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc).isoformat()
        self._write_outcomes(isolated_home, [
            {"ts": now, "primary": "claude", "rate_limit_save": True,
             "failure_kind": "rate_limited"},
            {"ts": now, "primary": "claude", "rate_limit_save": True,
             "failure_kind": "auth_failed"},
            {"ts": now, "primary": "claude", "rate_limit_save": False},
        ])
        result = _rate_limit_saves()
        assert result["has_data"] is True
        assert result["total_saves"] == 2
        assert result["total_calls"] == 3
        assert abs(result["save_rate"] - 0.667) < 0.01
        # Sorted desc by count, stable.
        kind_names = [r["kind"] for r in result["by_failure_kind"]]
        assert sorted(kind_names) == ["auth_failed", "rate_limited"]
        # by_primary_provider names a real provider (matches `primary`
        # field in ask.py, not `primary_provider`). The bug shape is:
        # if this helper reads the wrong field, by_primary becomes all
        # "unknown" and the launch claim "Claude routed around X times"
        # can't be supported.
        assert result["by_primary_provider"][0]["provider"] == "claude"

    def test_respects_30_day_window(self, isolated_home):
        """Old saves outside the 30-day window aren't counted —
        prevents stale data from inflating the launch claim."""
        from trinity_local.launchpad_data import _rate_limit_saves
        from datetime import datetime, timedelta, timezone
        now = datetime.now(timezone.utc)
        old = (now - timedelta(days=45)).isoformat()
        fresh = now.isoformat()
        self._write_outcomes(isolated_home, [
            {"ts": old, "primary": "claude", "rate_limit_save": True,
             "failure_kind": "rate_limited"},
            {"ts": fresh, "primary": "claude", "rate_limit_save": True,
             "failure_kind": "rate_limited"},
        ])
        result = _rate_limit_saves()
        # 1 fresh save, 1 fresh call (window filters both)
        assert result["total_saves"] == 1

    def test_malformed_lines_skipped_without_crashing(self, isolated_home):
        """Analytics never crash — a corrupt jsonl line shouldn't
        take down the whole launchpad."""
        from trinity_local.launchpad_data import _rate_limit_saves
        from datetime import datetime, timezone
        analytics = isolated_home / "analytics"
        analytics.mkdir(parents=True, exist_ok=True)
        path = analytics / "dispatch_outcomes.jsonl"
        path.write_text(
            'not json\n'
            + json.dumps({
                "ts": datetime.now(timezone.utc).isoformat(),
                "primary": "claude",
                "rate_limit_save": True,
                "failure_kind": "rate_limited",
            }) + "\n"
            + '\n'  # empty line
            + '{broken: json,}\n',
            encoding="utf-8",
        )
        result = _rate_limit_saves()
        # The one valid line counts; the rest are silently dropped.
        assert result["has_data"] is True
        assert result["total_saves"] == 1

    def test_rateLimitSaves_wired_into_build_page_data(self):
        """Source-level wiring check (same shape as other launchpad
        fields). Build_page_data must return the rateLimitSaves key
        or the launchpad surface silently disappears."""
        from pathlib import Path
        src = Path(__file__).resolve().parents[1] / "src/trinity_local/launchpad_data.py"
        text = src.read_text(encoding="utf-8")
        assert "\"rateLimitSaves\":" in text or "'rateLimitSaves':" in text

    def test_timestamp_field_matches_ask_writer(self, isolated_home):
        """Regression guard for the silent dead-code bug caught at
        T-1 day. ask.py writes `ts` as the timestamp field. An earlier
        version of `_rate_limit_saves` read `entry.get("at")` —
        which silently returned None for every real entry, falling
        through the try/except, and the 30-day window filter NEVER
        APPLIED. Tests passed because the test fixtures used `at`
        too, and real-corpus output matched the CLI metric for an
        unrelated reason (entries weren't stale enough to differ).

        This test writes an entry using ONLY the production field
        name (`ts`), with a timestamp OUTSIDE the window, and asserts
        the entry is excluded. If a future refactor reverts to `at`
        or any other key, the entry will sneak through the filter
        and `total_calls` will be wrong.
        """
        from trinity_local.launchpad_data import _rate_limit_saves
        from datetime import datetime, timedelta, timezone
        far_past = (datetime.now(timezone.utc) - timedelta(days=400)).isoformat()
        self._write_outcomes(isolated_home, [
            # Production-shape entry: only `ts`, no `at`. Far outside
            # the 30-day window. If the helper reads a different key,
            # this slips through and total_calls > 0.
            {"ts": far_past, "primary": "claude", "rate_limit_save": True,
             "failure_kind": "rate_limited"},
        ])
        result = _rate_limit_saves()
        assert result["has_data"] is False, (
            "Entry with `ts` 400 days old was counted — the window "
            "filter isn't applying. Check that _rate_limit_saves "
            "reads the same timestamp field that ask.py writes (`ts`)."
        )
        assert result["total_calls"] == 0, (
            "Expected zero calls in the 30d window; got "
            f"{result['total_calls']}. The launchpad number and the "
            "CLI metric have drifted on field naming."
        )
