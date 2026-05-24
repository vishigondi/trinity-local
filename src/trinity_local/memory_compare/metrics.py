"""Lexical comparison metrics for memory-compare Mode 1 (#142).

Pure stdlib — no embeddings yet. The plan named lexical Jaccard as the
v1 measure with embedding-cosine dedup as the upgrade path; this slice
ships the v1.

Three metrics surface:
- **Coverage**: count of distinct claims per memory system
- **Overlap**: Jaccard similarity over normalized claim token sets
- **Specificity**: mean + median char length per claim; mean word count

Plus an **asymmetric_gaps** field listing the top-N claims unique to
each system. These are the cross-fertilization candidates — claims one
system surfaced that the other missed. Useful for "Trinity should
probably learn this" / "Auto-Dream should probably learn this" hints
in the comparison report.
"""
from __future__ import annotations

import re
import statistics
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


# Strip punctuation, lowercase, split on whitespace. Filter common
# English stopwords + Trinity / Claude jargon that doesn't add signal.
_STOPWORDS = frozenset({
    "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
    "of", "in", "on", "at", "to", "for", "from", "with", "by", "as",
    "and", "or", "not", "but", "so", "if", "then", "than", "that", "this",
    "these", "those", "it", "its", "they", "them", "their", "we", "our",
    "you", "your", "i", "me", "my", "he", "him", "his", "she", "her",
    "has", "have", "had", "do", "does", "did", "will", "would", "should",
    "can", "could", "may", "might", "must", "shall",
    # Trinity / Claude common terms — high-frequency, low-signal in both
    # systems' outputs so they smear Jaccard without indicating real
    # alignment.
    "trinity", "claude", "lens", "memory", "user", "code",
})

_PUNCT_RE = re.compile(r"[^\w\s]+")


@dataclass
class Claim:
    """One short principle / observation extracted from a memory system.

    ``tokens`` is the cached normalized token set used for Jaccard;
    computed lazily by ``from_text``.
    """
    source: str  # "trinity" | "auto-dream"
    text: str
    tokens: frozenset[str] = field(default_factory=frozenset)

    @classmethod
    def from_text(cls, source: str, text: str) -> "Claim":
        return cls(source=source, text=text, tokens=tokenize(text))

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "text": self.text,
            "token_count": len(self.tokens),
        }


@dataclass
class ComparisonReport:
    """Aggregate of the three Mode-1 metrics + asymmetric-gaps.

    Designed for trivial serialization (``to_dict``) so the eventual
    CLI can dump JSON for scripting AND render a markdown report from
    the same structure.
    """
    trinity_count: int
    claude_count: int
    overlap_count: int
    jaccard: float
    trinity_specificity: dict[str, float]
    claude_specificity: dict[str, float]
    trinity_only: list[str]  # claims unique to Trinity (top N)
    claude_only: list[str]   # claims unique to Auto-Dream (top N)
    shared_examples: list[tuple[str, str]]  # paired (trinity, claude) overlaps

    def to_dict(self) -> dict[str, Any]:
        return {
            "trinity_count": self.trinity_count,
            "claude_count": self.claude_count,
            "overlap_count": self.overlap_count,
            "jaccard": round(self.jaccard, 4),
            "trinity_specificity": self.trinity_specificity,
            "claude_specificity": self.claude_specificity,
            "trinity_only": self.trinity_only,
            "claude_only": self.claude_only,
            "shared_examples": [list(t) for t in self.shared_examples],
        }

    def headline(self) -> str:
        """One-line summary suitable for `trinity-local memory-compare` stdout."""
        pct = int(round(self.jaccard * 100))
        return (
            f"Trinity captured {self.trinity_count} principles; "
            f"Claude Auto-Dream captured {self.claude_count}; "
            f"overlap {self.overlap_count} ({pct}%)."
        )


def tokenize(text: str) -> frozenset[str]:
    """Lowercase, strip punctuation, split on whitespace, drop stopwords.

    Single-character tokens dropped too — they're almost always noise
    (a/i remnants after stopword filter, punctuation residue).
    """
    cleaned = _PUNCT_RE.sub(" ", text.lower())
    tokens = {
        t for t in cleaned.split()
        if len(t) > 1 and t not in _STOPWORDS
    }
    return frozenset(tokens)


def specificity(claims: list[Claim]) -> dict[str, float]:
    """Compute char-length + word-count distribution metrics.

    Auto-Dream tends toward concrete observation ("uses pnpm not npm")
    so its claims are typically short. Trinity tends abstract
    ("infrastructure over interface") so its claims are typically
    shorter STILL but with fewer words and higher conceptual density.
    This metric makes the divergence visible without judging.
    """
    if not claims:
        return {"mean_chars": 0.0, "median_chars": 0.0, "mean_words": 0.0}
    char_lens = [len(c.text) for c in claims]
    word_counts = [len(c.text.split()) for c in claims]
    return {
        "mean_chars": round(statistics.mean(char_lens), 1),
        "median_chars": round(statistics.median(char_lens), 1),
        "mean_words": round(statistics.mean(word_counts), 1),
    }


def jaccard_pair(a: Claim, b: Claim) -> float:
    """Token-set Jaccard between two claims. 0.0 when both empty."""
    if not a.tokens and not b.tokens:
        return 0.0
    inter = len(a.tokens & b.tokens)
    union = len(a.tokens | b.tokens)
    if union == 0:
        return 0.0
    return inter / union


def find_overlaps(
    trinity: list[Claim],
    claude: list[Claim],
    threshold: float = 0.4,
) -> list[tuple[Claim, Claim, float]]:
    """Greedy-match claims across sources above token-Jaccard threshold.

    Threshold 0.4 keeps false-positives low — short claims need a real
    chunk of shared tokens to count as overlapping, not just "both
    mention X" coincidence. Each claim matches at most once (greedy:
    highest similarity wins).
    """
    matches: list[tuple[Claim, Claim, float]] = []
    claimed_claude: set[int] = set()
    for t in trinity:
        best_idx = -1
        best_score = 0.0
        for j, c in enumerate(claude):
            if j in claimed_claude:
                continue
            score = jaccard_pair(t, c)
            if score > best_score:
                best_score = score
                best_idx = j
        if best_idx >= 0 and best_score >= threshold:
            matches.append((t, claude[best_idx], best_score))
            claimed_claude.add(best_idx)
    return matches


def compare_memories(
    trinity_lens_text: str | None = None,
    claude_memory_root: Path | None = None,
    top_n: int = 5,
    overlap_threshold: float = 0.4,
) -> ComparisonReport:
    """Run Mode 1 comparison and return a structured report.

    Args:
        trinity_lens_text: lens.md contents. ``None`` reads from disk.
        claude_memory_root: Auto-Dream memory directory (containing
            MEMORY.md). ``None`` returns an empty Claude side — useful
            when comparing Trinity-only state or when the caller wants
            to handle the "no Claude install" case.
        top_n: how many asymmetric-gap claims to surface per side.
        overlap_threshold: minimum token-Jaccard for two claims to count
            as overlapping. 0.4 default — see ``find_overlaps``.

    Returns the full ``ComparisonReport``.
    """
    from .parse_claude_memory import parse_claude_memory
    from .parse_lens import parse_lens

    trinity_strings = parse_lens(trinity_lens_text)
    claude_strings: list[str] = []
    if claude_memory_root is not None:
        claude_strings = parse_claude_memory(claude_memory_root)

    trinity_claims = [Claim.from_text("trinity", s) for s in trinity_strings]
    claude_claims = [Claim.from_text("auto-dream", s) for s in claude_strings]

    overlaps = find_overlaps(trinity_claims, claude_claims, threshold=overlap_threshold)
    matched_trinity_ids = {id(t) for t, _, _ in overlaps}
    matched_claude_ids = {id(c) for _, c, _ in overlaps}

    trinity_only = [
        c.text for c in trinity_claims if id(c) not in matched_trinity_ids
    ][:top_n]
    claude_only = [
        c.text for c in claude_claims if id(c) not in matched_claude_ids
    ][:top_n]
    shared_examples = [(t.text, c.text) for t, c, _ in overlaps[:top_n]]

    union = len(trinity_claims) + len(claude_claims) - len(overlaps)
    jaccard_val = (len(overlaps) / union) if union > 0 else 0.0

    return ComparisonReport(
        trinity_count=len(trinity_claims),
        claude_count=len(claude_claims),
        overlap_count=len(overlaps),
        jaccard=jaccard_val,
        trinity_specificity=specificity(trinity_claims),
        claude_specificity=specificity(claude_claims),
        trinity_only=trinity_only,
        claude_only=claude_only,
        shared_examples=shared_examples,
    )
