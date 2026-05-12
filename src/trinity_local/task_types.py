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


# Polish-shape tasks benefit from consensus_round iteration — the user
# typed "make this better", "tighten this", "is this clearer?" The
# council's first pass usually catches the obvious; the value comes from
# rounds 2-3 where each model refines against the others' outputs.
# Detected so harnesses (or the user via the launchpad) can offer to
# auto-iterate; not auto-fired here.
_POLISH_PHRASES = (
    "make this better",
    "make it better",
    "make this stronger",
    "make it stronger",
    "make this sharper",
    "make it sharper",
    "improve this",
    "polish this",
    "polish it",
    "tighten this",
    "tighten it",
    "rewrite this",
    "refine this",
    "edit this",
    "is this clearer",
    "is this stronger",
    "is this better",
    "any better",
    "does this make sense",
    "is this right",
)
# Single-word imperative hints — caught when the input is *short* (≤20
# words). On a long task, "shorter" / "simpler" usually qualify a larger
# request rather than naming the task itself.
_POLISH_HINTS_SHORT_ONLY = (
    "shorter",
    "simpler",
    "clearer",
    "stronger",
    "punchier",
    "crisper",
)


def is_polish_task(text: str) -> bool:
    """True when the task smells like editing/polishing existing copy.

    Heuristic, not a classifier: the value isn't from precision (consensus
    rounds cost a few flagship calls), it's from recall — surface polish
    intent reliably so the harness can offer auto-iteration. Better to
    over-suggest iteration on a borderline case than miss it.

    Two paths:
      1. Phrase match: the task contains a literal polish phrase
         ("make this better", "tighten this", "any better", ...).
      2. Short imperative hint: the task is ≤20 words AND contains a
         polish hint ("shorter", "simpler", "clearer", ...). Long tasks
         pass through — "rewrite this 12-page doc into a memo" is a
         creative-writing task, not a polish pass.
    """
    if not text:
        return False
    lowered = text.lower()
    for phrase in _POLISH_PHRASES:
        if phrase in lowered:
            return True
    word_count = len(text.split())
    if word_count <= 20:
        for hint in _POLISH_HINTS_SHORT_ONLY:
            if hint in lowered:
                return True
    return False
