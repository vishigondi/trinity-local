from __future__ import annotations

from trinity_local.council_runtime import parse_synthesis_sections


def test_parse_synthesis_sections_accepts_markdown_heading_variants():
    text = """## What Each Response Does Best
Response A is strongest on specificity.

## Key Tradeoffs
Response B is simpler but less complete.

## What Reviewers Found
Reviewers agreed that both answers were accurate.

## Decision Framework
Choose Response A if you value depth.
"""

    sections = parse_synthesis_sections(text)

    assert sections["best_answer"] == "Response A is strongest on specificity."
    assert sections["differences"] == "Response B is simpler but less complete."
    assert sections["agreement"] == "Reviewers agreed that both answers were accurate."
    assert sections["winner"] == "Choose Response A if you value depth."


class TestResolveWinner:
    """Pin down the winner-resolution priority. The bug we're fixing: chairman
    narrative often mentions losing providers in passing ("claude argued for X
    even though codex won") and the old text-scan grabbed the first match.

    Routing JSON is structured and explicit — trust it first."""

    def test_routing_json_wins_over_narrative_substring(self):
        """The reproducer: chairman picked Codex but the Winner section
        narrative names claude in the first sentence. Old code returned
        'claude'. New code returns 'codex' from the structured Routing JSON."""
        from types import SimpleNamespace
        from trinity_local.council_runner import _resolve_winner

        routing_label = SimpleNamespace(winner="Codex")
        winner_section = (
            "**Codex.** Same pick (A) but adds the load-bearing follow-on "
            "that claude argued against — chairman ruled in codex's favour."
        )
        result = _resolve_winner(
            routing_label=routing_label,
            winner_section=winner_section,
            sequence=["claude", "antigravity", "codex"],
        )
        assert result == "codex"

    def test_consensus_round_uses_resolve_winner_not_prose_scan(self):
        """The iter-2 council found that run_consensus_round STILL did its own
        prose-winner scan on `sections["winner"]` instead of going through
        `_resolve_winner`. With Routing JSON missing, that path silently
        picked the first provider mentioned in the prose. Pin the fix."""
        import inspect
        from trinity_local import council_runner

        src = inspect.getsource(council_runner.run_consensus_round)
        # The legacy prose-scan loop is gone:
        assert "if \"winner\" in sections:" not in src, (
            "run_consensus_round must use _resolve_winner, not scan sections['winner']"
        )
        # And the canonical resolver IS called:
        assert "_resolve_winner(" in src

    def test_no_winner_when_routing_label_missing(self):
        # The prose-section + A/B/C label fallbacks were removed. With Routing
        # JSON parse-success ≥85%, the fallbacks were silently masking parse
        # failures rather than fixing them — `winner_provider=None` is the
        # honest signal that the rater needs to fix it.
        from trinity_local.council_runner import _resolve_winner

        assert _resolve_winner(
            routing_label=None,
            winner_section="**Gemini.** Wins on terseness.",
            sequence=["claude", "antigravity", "codex"],
        ) is None
        assert _resolve_winner(
            routing_label=None,
            winner_section="A",
            sequence=["claude", "antigravity", "codex"],
            label_to_provider={"A": "antigravity"},
        ) is None


class TestChairmanPromptOrdering:
    """Pin down /me → task → members ordering in the chairman prompt.

    The council ran the meta-question 'should persona come BEFORE or AFTER
    member responses?' and converged unanimously on BEFORE: 'persona should
    function as the evaluation rubric, not a post-hoc adjustment. AFTER
    ordering causes the chairman to anchor on a generic best answer first.'
    Lock that ordering in so a future refactor doesn't accidentally invert.
    """

    def test_me_comes_before_task_and_members(self, tmp_path, monkeypatch):
        from trinity_local.council_runtime import render_primary_council_prompt
        from trinity_local.council_schema import CouncilMemberResult, PromptBundle

        # Force /me to exist for this test by writing a synthetic lens.
        # (Pre-rename path was ~/.trinity/me.md — file auto-migrates.)
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        (tmp_path / "me.md").write_text(
            "# /me\nUser profile: prefers terse answers.\n",
            encoding="utf-8",
        )

        bundle = PromptBundle(bundle_id="b", task_cluster_id="c", task_text="Pick a cache.")
        members = [CouncilMemberResult(provider="claude", model="opus", output_text="Redis.")]
        prompt = render_primary_council_prompt(bundle, members)

        me_pos = prompt.find("User profile")
        task_pos = prompt.find("Original task:")
        member_pos = prompt.find("Council member outputs:")

        assert me_pos > 0, "User profile section missing"
        assert task_pos > me_pos, "task must come AFTER /me"
        assert member_pos > task_pos, "members must come AFTER task"

    def test_chairman_prefers_core_md_over_lens_md(self, tmp_path, monkeypatch):
        """When ~/.trinity/core.md exists, the chairman context loader must
        use the distilled paragraph and NOT the full lens. core is the
        identity memory — one paragraph subsuming the five plural memories.
        Loading both wastes context; loading only lens defeats Phase 5."""
        from trinity_local.council_runtime import render_primary_council_prompt
        from trinity_local.council_schema import CouncilMemberResult, PromptBundle

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        # Both files present — core.md should win.
        (tmp_path / "core.md").write_text(
            "You ship leverage over structural ownership.", encoding="utf-8",
        )
        (tmp_path / "memories").mkdir()
        (tmp_path / "memories" / "lens.md").write_text(
            "# Lens\nSHOULD NOT APPEAR — core.md takes precedence.\n",
            encoding="utf-8",
        )

        bundle = PromptBundle(bundle_id="b", task_cluster_id="c", task_text="Pick a cache.")
        members = [CouncilMemberResult(provider="claude", model="opus", output_text="Redis.")]
        prompt = render_primary_council_prompt(bundle, members)

        assert "You ship leverage over structural ownership." in prompt
        assert "SHOULD NOT APPEAR" not in prompt, (
            "When core.md exists, the full lens MUST NOT also be loaded — "
            "it duplicates context and defeats the distillation."
        )

    def test_chairman_falls_back_to_lens_when_core_missing(self, tmp_path, monkeypatch):
        """Cold install — no core.md distilled yet. Chairman must still load
        the lens so it has SOMETHING to personalize on."""
        from trinity_local.council_runtime import render_primary_council_prompt
        from trinity_local.council_schema import CouncilMemberResult, PromptBundle

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        # core.md absent, only lens.md present.
        (tmp_path / "memories").mkdir()
        (tmp_path / "memories" / "lens.md").write_text(
            "# Lens\nFallback context line.\n", encoding="utf-8",
        )

        bundle = PromptBundle(bundle_id="b", task_cluster_id="c", task_text="Pick a cache.")
        members = [CouncilMemberResult(provider="claude", model="opus", output_text="Redis.")]
        prompt = render_primary_council_prompt(bundle, members)

        assert "Fallback context line" in prompt
        assert "core.md" not in prompt or "not yet distilled" in prompt, (
            "When core.md is absent, prompt should still mention WHY "
            "the lens is being read directly."
        )


class TestThreadManifest:
    def _outcome(self, council_id: str, *, root: str | None = None, parent: str | None = None, round_number: int = 1, started_at: str = ""):
        from trinity_local.council_schema import CouncilOutcome

        # Mirror real Trinity convention: bundle_id is the canonical chain
        # root identifier. For root councils, chain_root_id falls back to
        # bundle_id. For chain rounds, chain_root_id is the root's bundle_id.
        bundle_id = f"bundle_{council_id}"
        metadata = {"round_number": round_number}
        if root:
            # Translate the test's logical "root council_id" into its bundle_id
            metadata["chain_root_id"] = f"bundle_{root}"
        if parent:
            metadata["parent_council_id"] = parent
        if started_at:
            metadata["started_at"] = started_at
        return CouncilOutcome(
            council_run_id=council_id,
            bundle_id=bundle_id,
            task_cluster_id="c",
            primary_provider="claude",
            created_at=started_at or "2026-05-06T00:00:00",
            metadata=metadata,
        )

    def test_root_only_writes_single_segment(self, tmp_path, monkeypatch):
        from trinity_local.council_runtime import update_thread_manifest

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        (tmp_path / "council_outcomes").mkdir(parents=True, exist_ok=True)

        path = update_thread_manifest(self._outcome("root1"))

        from trinity_local.council_runtime import _read_thread_manifest
        text = path.read_text()
        # Manifest is keyed off bundle_id (canonical chain root)
        assert "_thread_bundle_root1.js" in str(path)
        assert "bundle_root1" in text
        body = _read_thread_manifest(path)
        assert body["chain_root_id"] == "bundle_root1"
        assert len(body["segments"]) == 1
        assert body["segments"][0]["council_id"] == "root1"
        assert body["segments"][0]["round_number"] == 1

    def test_appends_chained_segments_in_order(self, tmp_path, monkeypatch):
        from trinity_local.council_runtime import update_thread_manifest

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        (tmp_path / "council_outcomes").mkdir(parents=True, exist_ok=True)

        update_thread_manifest(self._outcome("root1", started_at="2026-05-06T00:00:00"))
        update_thread_manifest(self._outcome("c2", root="root1", parent="root1", round_number=2, started_at="2026-05-06T00:01:00"))
        path = update_thread_manifest(self._outcome("c3", root="root1", parent="c2", round_number=3, started_at="2026-05-06T00:02:00"))

        from trinity_local.council_runtime import _read_thread_manifest
        body = _read_thread_manifest(path)
        assert [s["council_id"] for s in body["segments"]] == ["root1", "c2", "c3"]
        assert body["segments"][2]["parent_council_id"] == "c2"

    def test_re_save_is_idempotent(self, tmp_path, monkeypatch):
        from trinity_local.council_runtime import update_thread_manifest

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        (tmp_path / "council_outcomes").mkdir(parents=True, exist_ok=True)

        update_thread_manifest(self._outcome("root1"))
        update_thread_manifest(self._outcome("c2", root="root1", parent="root1", round_number=2))
        path = update_thread_manifest(self._outcome("c2", root="root1", parent="root1", round_number=2))

        from trinity_local.council_runtime import _read_thread_manifest
        body = _read_thread_manifest(path)
        # c2 appears once even after re-save
        ids = [s["council_id"] for s in body["segments"]]
        assert ids.count("c2") == 1
        assert ids == ["root1", "c2"]

    def test_consensus_rounds_sharing_bundle_id_all_appear(self, tmp_path, monkeypatch):
        """Regression for the lost-iterations bug.

        consensus_round rounds derive their bundle_id deterministically from
        (task_cluster_id, task_text, goal, origin_session) — so all rounds of
        a refinement chain share ONE bundle_id. The old dedup-by-bundle_id
        wiped the prior round each time update_thread_manifest ran, leaving
        only the latest round visible at `?thread_id=bundle_X`.

        This test pins the fix: rounds 1+2+3 of the same bundle MUST all
        appear in the manifest, ordered by round_number.
        """
        from trinity_local.council_runtime import update_thread_manifest, _read_thread_manifest
        from trinity_local.council_schema import CouncilOutcome

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        (tmp_path / "council_outcomes").mkdir(parents=True, exist_ok=True)

        # All three rounds share bundle_id (deterministic hash).
        SHARED_BUNDLE = "bundle_42f8cea9c9e705e5"

        def _round(council_id: str, round_number: int, parent: str | None) -> CouncilOutcome:
            meta = {"chain_root_id": SHARED_BUNDLE, "round_number": round_number}
            if parent:
                meta["parent_council_id"] = parent
            return CouncilOutcome(
                council_run_id=council_id,
                bundle_id=SHARED_BUNDLE,
                task_cluster_id="copywriting_polish",
                primary_provider="claude",
                created_at=f"2026-05-12T14:3{round_number}:00",
                metadata=meta,
            )

        update_thread_manifest(_round("council_caf", round_number=1, parent=None))
        update_thread_manifest(_round("council_32b", round_number=2, parent="council_caf"))
        path = update_thread_manifest(_round("council_dd0", round_number=3, parent="council_32b"))

        # Manifest lives at the bundle-keyed filename (matches the URL the
        # launchpad emits for this bundle).
        assert path.name == f"_thread_{SHARED_BUNDLE}.js"

        body = _read_thread_manifest(path)
        ids = [s["council_id"] for s in body["segments"]]
        assert ids == ["council_caf", "council_32b", "council_dd0"], (
            f"All three rounds must survive in the manifest; got {ids}"
        )
        round_numbers = [s["round_number"] for s in body["segments"]]
        assert round_numbers == [1, 2, 3]

    def test_pending_to_finalized_only_replaces_same_round(self, tmp_path, monkeypatch):
        """When register_pending_round adds a placeholder for round 2 and
        update_thread_manifest later replaces it, prior rounds' completed
        entries must not be collateral damage."""
        from trinity_local.council_runtime import (
            update_thread_manifest, register_pending_round, _read_thread_manifest
        )
        from trinity_local.council_schema import CouncilOutcome

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        (tmp_path / "council_outcomes").mkdir(parents=True, exist_ok=True)

        SHARED = "bundle_shared_xyz"

        def _round(cid: str, rn: int) -> CouncilOutcome:
            return CouncilOutcome(
                council_run_id=cid, bundle_id=SHARED, task_cluster_id="c",
                primary_provider="claude",
                created_at=f"2026-05-12T14:3{rn}:00",
                metadata={"chain_root_id": SHARED, "round_number": rn},
            )

        # Round 1 finalized.
        update_thread_manifest(_round("c1", 1))
        # Round 2 pending (no council_id yet).
        register_pending_round(
            chain_root_id=SHARED, bundle_id=SHARED, status_token="tok2",
            round_number=2, parent_council_id="c1",
        )
        # Round 2 finalizes — should REPLACE only the pending round-2 entry.
        path = update_thread_manifest(_round("c2", 2))

        body = _read_thread_manifest(path)
        ids = [s["council_id"] for s in body["segments"]]
        assert ids == ["c1", "c2"], (
            f"Pending→finalized handoff must only replace round 2's entry; got {ids}"
        )

    def test_pending_round_is_replaced_by_completed_outcome(self, tmp_path, monkeypatch):
        # When a chain round starts we register a pending segment (no
        # council_id yet, status_token set, running=true) so the thread
        # view picks it up mid-flight. When the round saves, the matching
        # pending entry must be replaced by the completed one — keyed off
        # bundle_id, since council_run_id is allocated only at finalize time.
        # All threads use bundle_id as the chain root identifier.
        from trinity_local.council_runtime import (
            register_pending_round,
            update_thread_manifest,
            _read_thread_manifest,
        )
        from trinity_local.council_schema import CouncilOutcome

        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        (tmp_path / "council_outcomes").mkdir(parents=True, exist_ok=True)

        # Root council: chain_root_id == bundle_id == "bundle_root1"
        update_thread_manifest(self._outcome("root1", started_at="2026-05-06T00:00:00"))

        # Round 2 starts: pending entry under chain_root_id = root's bundle_id
        path = register_pending_round(
            chain_root_id="bundle_root1",
            bundle_id="bundle_round2",
            status_token="status_xyz",
            round_number=2,
            parent_council_id="root1",
            started_at="2026-05-06T00:01:00",
        )
        body = _read_thread_manifest(path)
        running = [s for s in body["segments"] if s.get("running")]
        assert len(running) == 1
        assert running[0]["status_token"] == "status_xyz"
        assert running[0]["bundle_id"] == "bundle_round2"
        assert running[0]["council_id"] is None

        # Round 2 completes: outcome saved, pending entry replaced
        completed = CouncilOutcome(
            council_run_id="real_round2_id",
            bundle_id="bundle_round2",
            task_cluster_id="c",
            primary_provider="claude",
            created_at="2026-05-06T00:02:00",
            metadata={
                "chain_root_id": "bundle_root1",
                "parent_council_id": "root1",
                "round_number": 2,
                "started_at": "2026-05-06T00:01:00",
            },
        )
        path = update_thread_manifest(completed)
        body = _read_thread_manifest(path)
        # No more pending — replaced by the completed entry
        assert all(not s.get("running") for s in body["segments"])
        ids = [s["council_id"] for s in body["segments"]]
        assert ids == ["root1", "real_round2_id"]
