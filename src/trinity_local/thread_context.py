"""Build a threaded prompt that gives a fresh model the prior context.

Older transcripts have short turns ("continue.", "Let me restart.") that mean
nothing in isolation. When we replay them through current models — either via
the launchpad autofill or via `replay-history` — we must include the
immediately-preceding assistant turn so the new model has something to react
to. Without this, scores are garbage.

This module is the single canonical formatter, used by:
  - `commands/replay.py` when building bundles for re-evaluation
  - `portal_template.py` when the user clicks an autofill suggestion that
    has stored thread context
"""
from __future__ import annotations


# How much of the prior assistant turn to send into the council. ~1500 chars
# is enough for context without dominating the bundle. The original turn
# could be 50k chars (long answers); we don't want to flood the model.
DEFAULT_CONTEXT_BUDGET_CHARS = 1500


def truncate_excerpt(text: str, *, budget: int = DEFAULT_CONTEXT_BUDGET_CHARS) -> str:
    """Trim from the middle so we keep both the lede and the closing summary."""
    text = (text or "").strip()
    if len(text) <= budget:
        return text
    half = budget // 2
    return f"{text[:half].rstrip()}\n[... excerpt truncated ...]\n{text[-half:].lstrip()}"


def build_threaded_prompt(
    prompt: str,
    *,
    preceding_assistant_text: str | None = None,
    budget: int = DEFAULT_CONTEXT_BUDGET_CHARS,
) -> str:
    """Return a council-ready prompt that includes the prior thread.

    If `preceding_assistant_text` is empty, returns `prompt` unchanged so this
    is a no-op for prompts that have no prior thread (and for fresh prompts
    typed straight into the launchpad).
    """
    prompt = (prompt or "").strip()
    excerpt = truncate_excerpt(preceding_assistant_text or "", budget=budget)
    if not excerpt:
        return prompt
    return (
        "Prior conversation context — the user is continuing a thread.\n"
        "The previous assistant turn said:\n"
        f"---\n{excerpt}\n---\n"
        "\n"
        "Current user message:\n"
        f"{prompt}"
    )
