"""The correction-vector lens — the lens as GEOMETRY (#257).

Each preference act is a steer: the model offered `sacrificed`, the user
privileged `privileged` instead. The vector `embed(privileged) − embed(sacrificed)`
is the DIRECTION the user pushed in embedding space. Averaged over every
correction, the residual (after per-act topic noise cancels) is the user's
consistent taste *direction* — the text-tension lens, but as a single vector you
can decompose onto interpretable axes.

Validated on the real corpus (122 corrections): per-act coherence is LOW (~0.14,
just over the random-pairing null) — individual corrections scatter because each
is about a different specific thing. BUT the mean direction's projection onto
interpretable axes is highly significant (≈+0.20 = ~5σ; a random unit vector
loads ±1/√768 ≈ 0.036) and matches the known lens: this user steers strongly
toward concrete + decisive, mildly toward terse. So the lens-as-vector is real
in AGGREGATE; the right readout is the axis signature + an honest coherence
caveat, not a claim that every correction agrees.
"""
from __future__ import annotations

import math
from typing import Sequence

# Interpretable taste axes, each a (positive-pole, negative-pole) prototype pair.
# The signature reports the mean correction's cosine to each axis: + leans to the
# first pole. Add an axis = add a prototype pair (no rule, no retraining).
TASTE_AXES: dict[str, tuple[list[str], list[str]]] = {
    "concrete↔abstract": (
        ["give the complete runnable code to copy paste", "the exact command to run", "the specific product to buy"],
        ["explain the general concept", "a high-level overview", "walk through the underlying theory"],
    ),
    "terse↔verbose": (
        ["just the answer", "keep it short", "one line"],
        ["a detailed thorough explanation with full context and caveats"],
    ),
    "decisive↔hedging": (
        ["just pick one and commit", "make the call", "what would you do"],
        ["it depends on many factors", "there are tradeoffs to weigh", "I can't decide for you"],
    ),
    "action↔description": (
        ["do it now", "ship the change", "build it"],
        ["here is what you could do", "the options are", "an overview of approaches"],
    ),
}

# Below this many corrections the signature isn't worth surfacing.
_MIN_CORRECTIONS = 12


def _unit(vec: Sequence[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in vec))
    return [x / n for x in vec] if n else list(vec)


def _mean(rows: list[list[float]]) -> list[float]:
    if not rows:
        return []
    dim = len(rows[0])
    acc = [0.0] * dim
    for r in rows:
        for i, x in enumerate(r):
            acc[i] += x
    return [x / len(rows) for x in acc]


def correction_signature() -> dict:
    """Compute the user's correction-vector lens: the mean steer direction, its
    coherence (how aligned the individual corrections are), and its loading on
    each interpretable taste axis. Best-effort; `{"ready": False}` on no
    embedder or too few corrections."""
    try:
        from ..embeddings import embed_batch
        from .preference_acts import iter_preference_acts
    except Exception:
        return {"ready": False, "reason": "imports unavailable"}

    pairs = [
        ((a.sacrificed or "").strip(), (a.privileged or "").strip())
        for a in iter_preference_acts()
        if (a.sacrificed or "").strip() and (a.privileged or "").strip()
        and len((a.sacrificed or "").strip()) > 4 and len((a.privileged or "").strip()) > 2
    ]
    if len(pairs) < _MIN_CORRECTIONS:
        return {"ready": False, "n": len(pairs), "min": _MIN_CORRECTIONS}

    try:
        sac = [_unit(v) for v in embed_batch([s for s, _ in pairs])]
        pri = [_unit(v) for v in embed_batch([p for _, p in pairs])]
    except Exception as exc:
        return {"ready": False, "reason": f"embed failed: {exc!r}"}

    corrections = [[p - s for p, s in zip(pv, sv)] for pv, sv in zip(pri, sac)]
    mean_c = _mean(corrections)
    norms = [math.sqrt(sum(x * x for x in c)) for c in corrections]
    mean_norm = sum(norms) / len(norms) if norms else 0.0
    coherence = (math.sqrt(sum(x * x for x in mean_c)) / mean_norm) if mean_norm else 0.0
    mc = _unit(mean_c)

    axes: dict[str, float] = {}
    for name, (pos, neg) in TASTE_AXES.items():
        pcen = _mean([list(v) for v in embed_batch(pos)])
        ncen = _mean([list(v) for v in embed_batch(neg)])
        ax = _unit([p - n for p, n in zip(pcen, ncen)])
        axes[name] = round(sum(a * b for a, b in zip(mc, ax)), 3)

    return {
        "ready": True,
        "n": len(pairs),
        # Low per-act coherence is expected (corrections scatter by topic); the
        # axis loadings are the signal. Surfaced so callers don't over-claim.
        "coherence": round(coherence, 3),
        "axes": dict(sorted(axes.items(), key=lambda kv: -abs(kv[1]))),
    }


def _axis_vectors() -> dict:
    """Embed the interpretable taste-axis directions (pos centroid − neg
    centroid, unit). Shared by the signature + drift computations."""
    from ..embeddings import embed_batch

    out = {}
    for name, (pos, neg) in TASTE_AXES.items():
        pcen = _mean([list(v) for v in embed_batch(pos)])
        ncen = _mean([list(v) for v in embed_batch(neg)])
        out[name] = _unit([p - n for p, n in zip(pcen, ncen)])
    return out


def _mean_correction_unit(pairs: list[tuple[str, str]]) -> list[float]:
    """Mean steer direction (unit) over a set of (sacrificed, privileged)
    pairs — embed(privileged) − embed(sacrificed), averaged, normalized."""
    from ..embeddings import embed_batch

    sac = [_unit(v) for v in embed_batch([s for s, _ in pairs])]
    pri = [_unit(v) for v in embed_batch([p for _, p in pairs])]
    corrections = [[p - s for p, s in zip(pv, sv)] for pv, sv in zip(pri, sac)]
    return _unit(_mean(corrections))


def correction_drift() -> dict:
    """Diachronic correction lens (#257): split the user's timed corrections
    into an early and a recent half and report how each interpretable
    taste-axis loading MOVED.

    This is the asymmetric insight no within-session memory (Auto-Dream
    included) can produce — not "what's your taste" but "how did your taste
    *change*." On Trinity's own corpus it shows the user's #1 steer shifting
    from `concrete↔abstract` (early) to `action↔description` (recent): as the
    models matured they stopped having to ask for concreteness and started
    pushing for executability.

    Time comes from each act's prompt_id → PromptNode → prompt_time. Acts with
    no resolvable time are dropped (can't be placed on the axis). Best-effort:
    `{"ready": False}` on no embedder or too few timed corrections to split.
    """
    try:
        from ..embeddings import embed_batch  # noqa: F401 — availability probe
        from ..memory.store import load_prompt_node
        from .chapters import prompt_time
        from .preference_acts import iter_preference_acts
    except Exception:
        return {"ready": False, "reason": "imports unavailable"}

    timed: list[tuple[str, str, str]] = []
    for a in iter_preference_acts():
        s, p = (a.sacrificed or "").strip(), (a.privileged or "").strip()
        if not (len(s) > 4 and len(p) > 2 and a.prompt_id):
            continue
        node = load_prompt_node(a.prompt_id)
        if node is None:
            continue
        t = prompt_time(node)
        if t:
            timed.append((t, s, p))

    # Need enough on BOTH sides of the split to trust either half.
    if len(timed) < 2 * _MIN_CORRECTIONS:
        return {"ready": False, "n": len(timed), "min": 2 * _MIN_CORRECTIONS}

    timed.sort(key=lambda x: x[0])
    mid = len(timed) // 2
    early, recent = timed[:mid], timed[mid:]

    try:
        axisvec = _axis_vectors()
        mc_e = _mean_correction_unit([(s, p) for _, s, p in early])
        mc_r = _mean_correction_unit([(s, p) for _, s, p in recent])
    except Exception as exc:
        return {"ready": False, "reason": f"embed failed: {exc!r}"}

    axes: dict[str, dict] = {}
    for name, av in axisvec.items():
        e = round(sum(x * y for x, y in zip(mc_e, av)), 3)
        r = round(sum(x * y for x, y in zip(mc_r, av)), 3)
        axes[name] = {"early": e, "recent": r, "delta": round(r - e, 3)}

    mover_name, mover = max(axes.items(), key=lambda kv: abs(kv[1]["delta"]))
    return {
        "ready": True,
        "n_early": len(early),
        "n_recent": len(recent),
        "early_span": [early[0][0][:10], early[-1][0][:10]],
        "recent_span": [recent[0][0][:10], recent[-1][0][:10]],
        "axes": dict(sorted(axes.items(), key=lambda kv: -abs(kv[1]["delta"]))),
        "biggest_mover": {"axis": mover_name, **mover},
    }
