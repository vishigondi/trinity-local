from __future__ import annotations


def guess_task_type(text: str, provider: str | None = None) -> str:
    """Heuristic classifier — the short label that flows into routing decisions.

    The same value is emitted by the chairman as ``task_type`` in Routing JSON,
    so input-time classification and synthesis-time labeling speak one language.
    """
    lowered = text.lower()
    if any(term in lowered for term in ("stock", "research", "compare", "market", "investigate")):
        return "research"
    if any(term in lowered for term in ("debug", "bug", "error", "failing", "traceback")):
        return "debugging"
    if any(term in lowered for term in ("write", "draft", "email", "memo")):
        return "writing"
    if provider == "cowork":
        return "cowork_general"
    if any(term in lowered for term in ("code", "refactor", "repo", "function", "script")):
        return "coding"
    return "general"


# Back-compat shim — external callers (and a handful of tests) still import
# guess_task_kind. New code should call guess_task_type directly.
guess_task_kind = guess_task_type
