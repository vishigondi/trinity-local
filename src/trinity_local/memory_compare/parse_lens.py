"""Parse Trinity's lens.md into Claim list for memory-compare (#142).

Wraps ``me_lenses.parse_taste_lenses()`` and extracts the two surfaces
that map 1:1 to Auto-Dream's claim-level granularity:

1. Abstract lenses — short principles like "infrastructure over interface".
   These are Trinity's directly-comparable analog to Auto-Dream's
   MEMORY.md bullet descriptions.
2. Implicit-rejection ``why_matters`` lines — one-sentence explanations
   of each rejection. These map to Auto-Dream's topic-file descriptions.

Verbatim model/user quotes from rejections are NOT extracted as claims
— those are private data (the privacy-safe share card path already
filters them out). Only the principle prose travels into the
comparison.
"""
from __future__ import annotations


def parse_lens(lens_text: str | None = None) -> list[str]:
    """Extract a flat claim list from lens.md.

    Pass ``lens_text=None`` (default) to read the live
    ``~/.trinity/memories/lens.md``; pass a string for tests / for
    callers that already loaded the file. Returns an empty list when
    lens.md is empty or unparseable.
    """
    from ..me_lenses import parse_taste_lenses

    if lens_text is None:
        lenses = parse_taste_lenses()
    else:
        lenses = parse_taste_lenses(lens_text)

    claims: list[str] = []
    seen: set[str] = set()

    for lens in lenses.abstract_lenses:
        statement = (lens.statement or "").strip()
        if not statement:
            continue
        norm = statement.lower()
        if norm not in seen:
            claims.append(statement)
            seen.add(norm)

    for rejection in lenses.rejections:
        why = (rejection.why_matters or "").strip()
        if not why:
            continue
        norm = why.lower()
        if norm not in seen:
            claims.append(why)
            seen.add(norm)

    return claims
