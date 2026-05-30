"""#248: _is_user_facing_prompt catches the scaffolding classes that slipped
the corpus-purity floor and concentrated into near-pure junk basins —
AGENTS.md / <environment_context> dumps, Trinity's own third-person extraction
prompts, and slash-command skill bodies. Plus: basin clustering dedups exact
texts so a prompt repeated 100s of times isn't a pseudo-cluster.
"""
from __future__ import annotations

import pytest

from trinity_local.ingest import _is_user_facing_prompt
from trinity_local.session_schema import SessionMessage


def _filtered(text: str) -> bool:
    """True when the text is REJECTED as non-user (scaffolding)."""
    return not _is_user_facing_prompt(SessionMessage(role="user", text=text))


SCAFFOLDING = [
    "# AGENTS.md instructions for /Users/openclaw/projects/trinity-local\n\n<INSTRUCTIONS>",
    "<environment_context>\n  <cwd>/Users/openclaw</cwd>\n  <shell>zsh</shell>",
    "Find the idiosyncratic words and frames this human introduces.\n\nDO NOT include",
    "Find structural analogies the human draws BETWEEN UNRELATED DOMAINS.",
    "Find places where the human was WRONG, accepted the correction, and updated.",
    "Find OPEN LOOPS in this session — explicit forward-looking commitments the user made",
    "Compose a 4–6 paragraph TASTE PROFILE about this person, in third person.",
    "# /loop — schedule a recurring or self-paced prompt\n\nParse the input",
    "# /council — launch a council\n\nDispatch members",
]

REAL_USER = [
    "find the bug in this function that crashes on empty input",
    "find me a good standing desk under $400",
    "compose a birthday poem for my daughter about ice princesses",
    "list the steps to deploy a Next.js app to Vercel",
    "why is my smart bulb not responding to the switch?",
    "identify the load-bearing wall in this floor plan",
    "summarize this article about ocean warming in 3 bullets",
]


@pytest.mark.parametrize("text", SCAFFOLDING)
def test_scaffolding_is_rejected(text):
    assert _filtered(text), f"should reject scaffolding: {text[:60]!r}"


@pytest.mark.parametrize("text", REAL_USER)
def test_real_user_prompts_survive(text):
    # The imperative+third-person heuristic must not eat genuine "find/compose/
    # list/identify/summarize" user prompts that don't refer to the user in the
    # third person.
    assert not _filtered(text), f"should keep real user prompt: {text[:60]!r}"


def test_basin_clustering_dedups_identical_texts(monkeypatch):
    # 100 identical "continue" nodes must collapse to ONE clustering point so
    # they can't form a pseudo-cluster that dominates a basin (#248/#15).
    import trinity_local.me.basins as basins_mod

    class FakeNode:
        def __init__(self, nid, text, emb):
            self.id = nid
            self.text = text
            self.transcript_id = nid
            self.embedding = emb

    nodes = []
    # 100 identical-text nodes (same vector) + 30 distinct ones
    for i in range(100):
        nodes.append(FakeNode(f"dup{i}", "continue", [1.0, 0.0, 0.0]))
    for i in range(30):
        v = [0.0, float(i % 5), float(i)]
        nodes.append(FakeNode(f"uniq{i}", f"distinct prompt {i}", v))

    monkeypatch.setattr(basins_mod, "iter_prompt_nodes", lambda *a, **k: iter(nodes))
    monkeypatch.setattr(basins_mod, "is_finite_embedding", lambda e: bool(e))

    basins = basins_mod.compute_basins(k=5)
    total = sum(b.size for b in basins)
    # 100 "continue" dups → 1 point; 30 distinct → 30. Total clustering points
    # must be 31, NOT 130 — otherwise the dup mass dominates.
    assert total == 31, f"expected 31 deduped points, got {total}"
