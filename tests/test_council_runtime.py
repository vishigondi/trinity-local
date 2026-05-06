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
            sequence=["claude", "gemini", "codex"],
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
            sequence=["claude", "gemini", "codex"],
        ) is None
        assert _resolve_winner(
            routing_label=None,
            winner_section="A",
            sequence=["claude", "gemini", "codex"],
            label_to_provider={"A": "gemini"},
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

        # Force /me to exist for this test by writing a synthetic me.md.
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


class TestThreadManifest:
    def _outcome(self, council_id: str, *, root: str | None = None, parent: str | None = None, round_number: int = 1, started_at: str = ""):
        from trinity_local.council_schema import CouncilOutcome

        metadata = {"round_number": round_number}
        if root:
            metadata["chain_root_id"] = root
        if parent:
            metadata["parent_council_id"] = parent
        if started_at:
            metadata["started_at"] = started_at
        return CouncilOutcome(
            council_run_id=council_id,
            bundle_id="b",
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
        assert "_thread_root1.js" in str(path)
        assert "root1" in text
        body = _read_thread_manifest(path)
        assert body["chain_root_id"] == "root1"
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
