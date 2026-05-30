"""Semantic noise filter (geometric, prototype-based) — replaces growing regex.

Validates the load-bearing claims: a few prototype vectors catch held-out noise
phrasings a regex would miss, the DUAL criterion (noise vs taste) spares terse
*meaningful* prompts, and the filter abstains when it has no taste reference
rather than guessing.
"""
from __future__ import annotations

import pytest

from trinity_local.me import semantic_filter as sf


@pytest.fixture(scope="module")
def vectors():
    noise = sf.noise_prototype_vectors()
    if not noise:
        pytest.skip("embedder unavailable")
    # A small taste reference (the user's real domains) as L2-normalized centroids.
    from trinity_local.embeddings import embed_batch
    taste_texts = [
        "find me a quiet standing desk under 400 dollars",
        "why is my smart bulb not responding to the switch",
        "how should I stack QOZ and QSBS to defer the gain",
        "make the monkey look more expressive not a blob",
    ]
    taste = [sf._l2(v) for v in embed_batch(taste_texts)]
    return noise, taste


def test_catches_held_out_noise_variants(vectors):
    # Phrasings NOT in the prototype set — a regex would miss these entirely.
    from trinity_local.embeddings import embed_batch
    noise, taste = vectors
    # Phrasings clearly in the noise region (not at the conservative floor) —
    # none of these is a prototype, so a regex written for the prototypes would
    # miss them; the geometry generalizes.
    held_out = [
        "just reply YES, nothing more",
        "resume the previous task",
        "reply with just the word OK",
    ]
    for text, emb in zip(held_out, embed_batch(held_out)):
        assert sf.is_semantic_noise(emb, noise, taste), f"should flag held-out noise: {text!r}"


def test_spares_terse_meaningful_taste(vectors):
    # The user's terse taste sits near agent-ops geometrically but is NOT noise;
    # the dual criterion (noise vs taste) must keep it.
    from trinity_local.embeddings import embed_batch
    noise, taste = vectors
    keep = [
        "make the monkey look more expressive not a blob",
        "why is my smart bulb not responding to the switch",
        "how should I stack QOZ and QSBS to defer the gain",
    ]
    for text, emb in zip(keep, embed_batch(keep)):
        assert not sf.is_semantic_noise(emb, noise, taste), f"should keep real taste: {text!r}"


def test_abstains_without_taste_reference(vectors):
    # No taste reference (e.g. first build, no basins yet) → abstain, never guess.
    from trinity_local.embeddings import embed_batch
    noise, _ = vectors
    emb = embed_batch(["respond with the word HELLO and nothing else"])[0]
    assert sf.is_semantic_noise(emb, noise, []) is False
    assert sf.is_semantic_noise(emb, [], [[0.0] * 768]) is False


def test_clear_noise_beats_floor_and_margin(vectors):
    from trinity_local.embeddings import embed_batch
    noise, taste = vectors
    emb = embed_batch(["respond with the word HELLO and nothing else"])[0]
    assert sf.is_semantic_noise(emb, noise, taste)
