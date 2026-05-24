"""Parse Trinity's lens.md into Claim list for memory-compare (#142).

Pulls from three surfaces that map to Auto-Dream's claim-level
granularity:

1. Paired lenses (``me.pair_mining.load_lenses``) — the *current*
   modern format. Each LensPair becomes one claim: "pole_a ↔ pole_b".
2. Orderings (``me.pair_mining.load_orderings``) — single-direction
   preferences. Each becomes "pole_a > pole_b".
3. Legacy abstract-lens / implicit-rejection surfaces via
   ``me_lenses.parse_taste_lenses`` — preserved for back-compat with
   pre-pair-mining lens.md generations. The current generated lens.md
   uses different section headers ("## Lenses (paired tensions)" vs
   "## Abstract lenses") so this fallback is mostly empty in
   practice — but harmless to keep.

Verbatim model/user quotes from rejections are NOT extracted as claims
— those are private data (the privacy-safe share card path already
filters them out). Only the principle prose travels into the
comparison.
"""
from __future__ import annotations


def parse_lens(lens_text: str | None = None) -> list[str]:
    """Extract a flat claim list from Trinity's lens artifacts.

    Pass ``lens_text=None`` (default) to read the live lens state from
    disk (``lenses.json`` + ``orderings.json`` via pair_mining, plus
    ``lens.md`` via the legacy parser). Pass a string to parse a
    specific lens.md text directly (legacy path only — paired/ordering
    state is JSON-on-disk, not embedded in lens.md).

    Returns an empty list when no lens state exists yet.
    """
    from ..me_lenses import parse_taste_lenses

    claims: list[str] = []
    seen: set[str] = set()

    def _add(text: str) -> None:
        text = text.strip()
        if not text:
            return
        norm = text.lower()
        if norm in seen:
            return
        claims.append(text)
        seen.add(norm)

    # Modern format (post pair-mining). Only read JSON state when the
    # caller didn't pass an explicit lens_text snippet — explicit text
    # means "just parse this string", not "merge with whatever is on
    # disk." Keeps tests deterministic.
    if lens_text is None:
        try:
            from ..me.pair_mining import load_lenses, load_orderings
            for pair in load_lenses():
                _add(f"{pair.pole_a} ↔ {pair.pole_b}")
            for pair in load_orderings():
                _add(f"{pair.pole_a} > {pair.pole_b}")
        except Exception:
            pass

    # Legacy format (pre pair-mining, or alternate generators).
    lenses = parse_taste_lenses() if lens_text is None else parse_taste_lenses(lens_text)

    for lens in lenses.abstract_lenses:
        _add(lens.statement or "")

    for rejection in lenses.rejections:
        _add(rejection.why_matters or "")

    return claims
