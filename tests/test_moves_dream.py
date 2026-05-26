"""Phase 6 of dream — moves substrate update (task #172).

The wedge-close: when this ships, the eval-gated promotion loop runs
end-to-end on each `trinity-local dream` cycle.

Phase 6 has three sub-phases:
  6a. T4 update from completed councils (Beta-Binomial alpha/beta)
  6b. Discovery + promotion (rejection-corpus → candidates → gate)
  6c. Demotion (re-eval T4 on active moves, archive drifted)

Tests pin each independently + the orchestrator's report shape.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
    return tmp_path


def _seed_council_outcome(
    home: Path,
    *,
    council_id: str,
    winner_provider: str,
    winner_text: str,
    basin_id: str | None = "b03",
) -> Path:
    """Drop a realistic council_outcome JSON file at the canonical
    location."""
    outcomes_dir = home / "council_outcomes"
    outcomes_dir.mkdir(parents=True, exist_ok=True)
    path = outcomes_dir / f"council_{council_id}.json"
    data = {
        "council_run_id": f"council_{council_id}",
        "bundle_id": f"bundle_{council_id}",
        "created_at": "2026-05-26T12:00:00Z",
        "primary_provider": "claude",
        "member_results": [
            {"provider": "claude", "output_text": winner_text if winner_provider == "claude" else "alt"},
            {"provider": "codex", "output_text": winner_text if winner_provider == "codex" else "alt"},
        ],
        "routing_label": {
            "winner": winner_provider,
            "basin_id": basin_id,
        },
    }
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


# ─── Phase 6a: T4 update ────────────────────────────────────────────


class TestT4UpdateFromCouncils:
    def test_cold_install_no_outcomes_no_moves(self, isolated_home):
        """Day-1 state: no council_outcomes dir, no active moves. Phase
        6a returns zeros without crashing."""
        from trinity_local.moves.dream import update_t4_from_recent_councils
        report = update_t4_from_recent_councils()
        assert report["councils_processed"] == 0
        assert report["moves_updated"] == 0

    def test_alpha_increments_when_winner_follows_move(self, isolated_home):
        """Seed an active move + a council whose winner's response
        contains the move's pattern. Expect alpha++. The winner text
        carries enough of the move's body verbatim to clear the Jaccard
        applicability threshold (0.2 default)."""
        from trinity_local.moves.dream import update_t4_from_recent_councils
        from trinity_local.moves.schemas import Move
        from trinity_local.moves.store import read_move, write_move

        move_body = (
            "tighten verbose bullet lists into short paragraphs by "
            "compressing the list into a single direct sentence"
        )
        write_move(Move(
            name="tighten-bullets",
            description="tighten verbose bullet lists into short paragraphs",
            body=move_body,
            trinity_basin_id="b03",
            trinity_promoted_at="2026-05-26T00:00:00+00:00",
        ))
        # Winner mirrors the move body closely enough that ≥20% of the
        # move's 3-grams appear in the winner — exceeds applicability threshold
        winner = (
            "I'll tighten verbose bullet lists into short paragraphs "
            "by compressing the list into a single direct sentence."
        )
        _seed_council_outcome(
            isolated_home,
            council_id="aaa111",
            winner_provider="claude",
            winner_text=winner,
            basin_id="b03",
        )
        report = update_t4_from_recent_councils()
        assert report["councils_processed"] == 1
        assert report["alpha_increments"] == 1
        assert report["beta_increments"] == 0
        assert report["moves_updated"] == 1
        # Persisted alpha/beta survives reload
        m = read_move("tighten-bullets")
        assert m.trinity_alpha == 2  # prior 1 + 1 increment

    def test_beta_increments_when_winner_doesnt_follow(self, isolated_home):
        from trinity_local.moves.dream import update_t4_from_recent_councils
        from trinity_local.moves.schemas import Move
        from trinity_local.moves.store import read_move, write_move

        write_move(Move(
            name="x",
            description="tighten bullet lists",
            body="compress to paragraph",
            trinity_basin_id="b03",
            trinity_promoted_at="2026-05-26T00:00:00+00:00",
        ))
        _seed_council_outcome(
            isolated_home,
            council_id="bbb222",
            winner_provider="claude",
            winner_text="here's a recipe for chocolate chip cookies",
            basin_id="b03",
        )
        report = update_t4_from_recent_councils()
        assert report["beta_increments"] == 1
        m = read_move("x")
        assert m.trinity_beta == 2  # prior 1 + 1 increment

    def test_skips_wrong_basin(self, isolated_home):
        """A move whose basin doesn't match the council's basin is
        skipped — no alpha/beta change."""
        from trinity_local.moves.dream import update_t4_from_recent_councils
        from trinity_local.moves.schemas import Move
        from trinity_local.moves.store import read_move, write_move

        write_move(Move(
            name="x",
            description="y",
            trinity_basin_id="b07",  # different from council
            trinity_promoted_at="2026-05-26T00:00:00+00:00",
        ))
        _seed_council_outcome(
            isolated_home,
            council_id="ccc333",
            winner_provider="claude",
            winner_text="some text",
            basin_id="b03",
        )
        report = update_t4_from_recent_councils()
        m = read_move("x")
        assert m.trinity_alpha == 1
        assert m.trinity_beta == 1
        assert report["moves_updated"] == 0


# ─── Phase 6b: Discovery ────────────────────────────────────────────


class TestDiscoverCandidates:
    def test_empty_corpus_no_candidates(self):
        from trinity_local.moves.dream import discover_candidates
        assert discover_candidates([]) == []

    def test_groups_below_min_size_skipped(self):
        """Default min_group_size=3. A group of 2 rejections doesn't
        produce a candidate (not enough pattern evidence)."""
        from trinity_local.moves.dream import discover_candidates
        corpus = [
            {"id": "r1", "basin": "b03", "type": "COMPRESSION",
             "user_substitute": "tldr"},
            {"id": "r2", "basin": "b03", "type": "COMPRESSION",
             "user_substitute": "shorter"},
        ]
        assert discover_candidates(corpus) == []

    def test_group_of_three_produces_candidate(self):
        from trinity_local.moves.dream import discover_candidates
        corpus = [
            {"id": "r1", "basin": "b03", "type": "COMPRESSION",
             "user_substitute": "tldr"},
            {"id": "r2", "basin": "b03", "type": "COMPRESSION",
             "user_substitute": "shorter please"},
            {"id": "r3", "basin": "b03", "type": "COMPRESSION",
             "user_substitute": "be brief"},
        ]
        candidates = discover_candidates(corpus)
        assert len(candidates) == 1
        c = candidates[0]
        assert c.trinity_basin_id == "b03"
        assert sorted(c.trinity_promoted_from) == ["r1", "r2", "r3"]
        # Body carries the user_substitute examples
        assert "tldr" in c.body or "shorter please" in c.body

    def test_multiple_groups_produce_multiple_candidates(self):
        """Different (basin, type) groups each produce their own
        candidate when threshold is cleared."""
        from trinity_local.moves.dream import discover_candidates
        corpus = (
            [
                {"id": f"r_c{i}", "basin": "b03", "type": "COMPRESSION",
                 "user_substitute": f"shorter {i}"}
                for i in range(3)
            ]
            + [
                {"id": f"r_r{i}", "basin": "b07", "type": "REFRAME",
                 "user_substitute": f"different frame {i}"}
                for i in range(3)
            ]
        )
        candidates = discover_candidates(corpus)
        assert len(candidates) == 2
        basins = sorted(c.trinity_basin_id for c in candidates)
        assert basins == ["b03", "b07"]

    def test_skips_rejections_missing_basin_or_type(self):
        """Defensive: bad records shouldn't crash discovery — they get
        skipped silently."""
        from trinity_local.moves.dream import discover_candidates
        corpus = [
            {"id": "r1", "basin": "b03", "type": "COMPRESSION",
             "user_substitute": "x"},
            {"id": "r2", "basin": "b03"},  # missing type
            {"id": "r3", "type": "COMPRESSION"},  # missing basin
            {"id": "r4"},  # missing both
        ]
        candidates = discover_candidates(corpus, min_group_size=1)
        assert len(candidates) == 1
        assert candidates[0].trinity_basin_id == "b03"


# ─── Phase 6b: Promotion pass ───────────────────────────────────────


class TestPromotionPass:
    def _fake_chairman_returning(self, score: float):
        from types import SimpleNamespace
        class Fake:
            def run(self, prompt, cwd=None):
                return SimpleNamespace(
                    stdout=f'{{"score": {score}}}',
                    stderr="",
                    returncode=0,
                    elapsed_seconds=0.0,
                    provider="fake",
                )
        return Fake()

    def test_t1_pass_t2_no_centroid_fails_and_logs(self, isolated_home):
        """A candidate whose basin has no centroid fails T2 → logged
        to dream_rejections.jsonl with which tier rejected."""
        from trinity_local.moves.dream import run_promotion_pass
        from trinity_local.moves.schemas import Move
        candidate = Move(
            name="c1",
            description="tighten lists",
            body="compress",
            trinity_basin_id="b99",
        )
        report = run_promotion_pass(
            [candidate],
            accepted_patterns_for_basin={},  # T1 vacuous pass
            basin_centroids={},  # T2 missing centroid
            rejection_corpus=[],
        )
        assert report["promoted"] == 0
        assert report["rejected"] == 1
        assert report["rejected_by_tier"]["T2"] == 1
        # Log file exists with the rejection
        log_path = isolated_home / "dream_rejections.jsonl"
        assert log_path.exists()
        records = [
            json.loads(ln)
            for ln in log_path.read_text(encoding="utf-8").splitlines()
            if ln.strip()
        ]
        assert len(records) == 1
        assert records[0]["candidate_name"] == "c1"
        assert records[0]["why_rejected"] == "failed at T2"

    def test_full_promotion_with_chairman_persists_move(self, isolated_home, monkeypatch):
        """Happy path: candidate clears T1+T2 with seeded centroid;
        T3's chairman returns a high score → promoted, persisted to
        disk, baseline set from T3 score."""
        from trinity_local import providers as _providers
        from trinity_local.embeddings import embed
        from trinity_local.moves.dream import run_promotion_pass
        from trinity_local.moves.gate import _candidate_text
        from trinity_local.moves.schemas import Move
        from trinity_local.moves.store import read_move

        monkeypatch.setattr(
            _providers, "make_provider",
            lambda cfg: self._fake_chairman_returning(0.84),
        )
        candidate = Move(
            name="tighten-bullets",
            description="tighten verbose bullet lists",
            body="compress to a paragraph",
            trinity_basin_id="b03",
            trinity_promoted_from=["r_001"],
        )
        # Self-aligned centroid → T2 perfect alignment
        centroid = embed(_candidate_text(candidate))
        report = run_promotion_pass(
            [candidate],
            accepted_patterns_for_basin={},  # T1 vacuous pass (empty)
            basin_centroids={"b03": centroid},
            rejection_corpus=[{
                "id": "r_001", "basin": "b03", "type": "COMPRESSION",
                "model_quote": "long lecture", "user_substitute": "short",
                "why_signal": "wanted shorter",
            }],
            chairman_provider_config={"dummy": True},
        )
        assert report["promoted"] == 1
        assert report["rejected"] == 0
        # Persisted with the baseline set from T3 score
        m = read_move("tighten-bullets")
        assert m.trinity_promoted_at is not None
        assert m.trinity_t3_chairman_score == pytest.approx(0.84)
        assert m.trinity_eval_baseline == pytest.approx(0.84)


# ─── Phase 6c: Demotion pass ────────────────────────────────────────


class TestDemotionPass:
    def test_no_active_moves_empty_report(self, isolated_home):
        from trinity_local.moves.dream import run_demotion_pass
        report = run_demotion_pass()
        assert report["active_moves_evaluated"] == 0
        assert report["demoted"] == 0

    def test_under_executions_move_not_demoted(self, isolated_home):
        """A fresh move with alpha=1, beta=1, execution_count=0 should
        NOT be demoted — T4 vacuous pass under min_executions guard."""
        from trinity_local.moves.dream import run_demotion_pass
        from trinity_local.moves.schemas import Move
        from trinity_local.moves.store import list_moves, write_move
        write_move(Move(
            name="fresh-move",
            description="new",
            trinity_basin_id="b03",
            trinity_promoted_at="2026-05-26T00:00:00+00:00",
        ))
        report = run_demotion_pass()
        assert report["demoted"] == 0
        # Move still in active list
        assert [m.name for m in list_moves()] == ["fresh-move"]

    def test_drifted_move_demoted_and_archived(self, isolated_home):
        """A move with high execution_count but low posterior gets
        demoted on a T4 check."""
        from trinity_local.moves.dream import run_demotion_pass
        from trinity_local.moves.schemas import Move
        from trinity_local.moves.store import list_moves, write_move
        write_move(Move(
            name="drifted-move",
            description="x",
            trinity_basin_id="b03",
            trinity_promoted_at="2026-05-20T00:00:00+00:00",
            trinity_alpha=3,
            trinity_beta=12,  # posterior ≈ 0.2
            trinity_execution_count=13,
            trinity_eval_baseline=0.7,
        ))
        report = run_demotion_pass()
        assert report["demoted"] == 1
        assert report["by_tier"]["T4"] == 1
        # Active list now empty
        assert list_moves() == []
        # Archive has the entry
        archived = list_moves(archived=True)
        assert len(archived) == 1
        assert archived[0].trinity_demoted_by_tier == "T4"


# ─── Orchestrator ────────────────────────────────────────────────────


class TestPhase6Orchestrator:
    def test_cold_install_returns_clean_report(self, isolated_home):
        """No state, no councils, no rejections, no moves → orchestrator
        returns a tidy report with zeros."""
        from trinity_local.moves.dream import phase_6_moves_pass
        report = phase_6_moves_pass()
        assert "t4_update" in report
        assert "promotion" in report
        assert "demotion" in report
        assert report["t4_update"]["councils_processed"] == 0
        assert report["promotion"]["candidates_evaluated"] == 0
        assert report["demotion"]["active_moves_evaluated"] == 0

    def test_skip_flags_short_circuit_phases(self, isolated_home):
        """skip_promotion / skip_demotion mark their phases as skipped
        without running them."""
        from trinity_local.moves.dream import phase_6_moves_pass
        report = phase_6_moves_pass(skip_promotion=True, skip_demotion=True)
        assert report["promotion"] == {"skipped": True}
        assert report["demotion"] == {"skipped": True}

    def test_cursor_updated_after_run(self, isolated_home):
        """After phase_6, the dream_state cursor is updated with
        last_run_at so the next cycle only processes new councils."""
        from trinity_local.moves.dream import phase_6_moves_pass, _load_dream_state
        before = _load_dream_state()
        assert "last_run_at" not in before
        phase_6_moves_pass()
        after = _load_dream_state()
        assert "last_run_at" in after
