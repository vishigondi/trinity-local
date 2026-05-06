"""Trinity capability categories.

Names + ordering aligned with the public LMArena leaderboard so we can
slot in external benchmarks later without re-mapping our UI. For v1 we
display these labels and aggregate the personal routing table into them;
no external data is auto-fetched.
"""
from __future__ import annotations


# (key, display label, trinity task_kinds that map into this category)
# Order matters — UI renders categories in this order on the launchpad.
CATEGORY_REGISTRY: list[tuple[str, str, tuple[str, ...]]] = [
    ("overall",               "Overall",                ("general", "cowork_general")),
    ("coding",                "Coding",                 ("coding", "debugging")),
    ("hard_prompts",          "Hard Prompts",           ("research",)),
    ("creative_writing",      "Creative Writing",       ("writing",)),
    ("instruction_following", "Instruction Following",  ()),
    ("multiturn",             "Multi-Turn",             ()),
    ("math",                  "Math",                   ()),
]


def category_keys() -> list[str]:
    return [key for key, _, _ in CATEGORY_REGISTRY]


def category_labels() -> dict[str, str]:
    return {key: label for key, label, _ in CATEGORY_REGISTRY}


def task_kind_to_category() -> dict[str, str]:
    """Reverse map trinity task_kind → category key."""
    out: dict[str, str] = {}
    for key, _, task_kinds in CATEGORY_REGISTRY:
        for kind in task_kinds:
            out[kind] = key
    return out
