"""#260 — do-operator discipline in routing + ingest.

The routing table must weight the user's OWN verdict (revealed preference) above
the chairman's pick (a model action), and the ingest role gate must keep every
assistant/tool token out of the user's PromptNode corpus ("do not train on
self-authored tokens as external evidence").
"""
from __future__ import annotations

from trinity_local.personal_routing import USER_VOTE_WEIGHT, aggregate_routing_table


def _council(task_type, chairman, user=None, scores=None):
    # Provider scores are required for the task_type to register in the table
    # (the output loop iterates by_task_scores). Real councils always carry them.
    if scores is None:
        scores = {
            "claude": {"overall": 0.8},
            "codex": {"overall": 0.7},
            "antigravity": {"overall": 0.6},
        }
    return {
        "task_type": task_type,
        "routing_label": {"task_type": task_type, "provider_scores": scores},
        "chairman_winner": chairman,
        "user_winner": user,
    }


class TestUserVerdictOutweighsChairman:
    def test_user_vote_counts_more_than_chairman(self):
        # 1 council: chairman picked codex, but the USER chose claude.
        table = aggregate_routing_table([_council("code", chairman="codex", user="claude")])
        wins = table["wins_per_task_type"]["code"]
        assert wins.get("claude") == USER_VOTE_WEIGHT
        assert "codex" not in wins  # the user's choice supersedes the chairman's

    def test_one_user_vote_beats_two_chairman_picks(self):
        # 2 councils chairman→codex, 1 council user→claude. User weight (3) wins.
        councils = [
            _council("code", chairman="codex"),
            _council("code", chairman="codex"),
            _council("code", chairman="codex", user="claude"),
        ]
        table = aggregate_routing_table(councils)
        assert table["best_per_task_type"]["code"] == "claude"
        wins = table["wins_per_task_type"]["code"]
        assert wins["claude"] == 3 and wins["codex"] == 2

    def test_chairman_pick_used_when_no_user_verdict(self):
        councils = [_council("code", chairman="codex") for _ in range(3)]
        table = aggregate_routing_table(councils)
        assert table["best_per_task_type"]["code"] == "codex"
        assert table["wins_per_task_type"]["code"]["codex"] == 3


class TestAssistantTokensNeverIngested:
    def test_assistant_and_tool_roles_rejected(self):
        from trinity_local.ingest import SessionMessage, _is_user_facing_prompt

        for role in ("assistant", "tool", "system"):
            msg = SessionMessage(role=role, text="a long substantive message " * 20)
            assert _is_user_facing_prompt(msg) is False, role

    def test_user_role_with_real_text_kept(self):
        from trinity_local.ingest import SessionMessage, _is_user_facing_prompt

        msg = SessionMessage(role="user", text="what should I do about the tax gain?")
        assert _is_user_facing_prompt(msg) is True

    def test_role_gate_is_the_first_check(self):
        """The role gate must be the FIRST line of the guard — defense in depth
        so no later branch can resurrect assistant text."""
        import inspect

        from trinity_local.ingest import _is_user_facing_prompt

        src = inspect.getsource(_is_user_facing_prompt)
        body = src.split(":", 1)[1]  # after the signature
        assert 'message.role != "user"' in body
        # It appears before any text-content inspection.
        assert body.index('message.role != "user"') < body.index("lowered")
