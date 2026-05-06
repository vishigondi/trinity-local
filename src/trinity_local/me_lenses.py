"""Parse `~/.trinity/me.md` into shareable taste lenses.

The /me document has 5 sections produced by the chairman in `me-build`:
recurring topics, vocabulary, implicit rejections, cross-domain analogies,
abstract lenses. The "implicit rejections" section is the load-bearing
moat: pairwise (model_said, user_substituted, why_this_matters) cards that
encode the user's actual taste — what they actively redirect away from.

This module turns each card into a structured object the launchpad renders
as a copyable social card. The user is the artifact; the launchpad shows
their taste back to them and lets them paste any individual lens to socials
without exposing the underlying prompts.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from .me_builder import load_me


@dataclass
class ImplicitRejection:
    """One pairwise lens — what the model said vs. what the user actually did."""
    title: str
    model_frame: str
    user_substituted: str
    why_matters: str

    def to_share_text(self) -> str:
        """Tweet-thread-shaped quotable card. Pastes cleanly into socials."""
        return (
            f'"{self.title}"\n\n'
            f'Model said:\n> {self.model_frame}\n\n'
            f'What I substituted:\n> {self.user_substituted}\n\n'
            f'Why this matters: {self.why_matters}'
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "title": self.title,
            "model_frame": self.model_frame,
            "user_substituted": self.user_substituted,
            "why_matters": self.why_matters,
            "share_text": self.to_share_text(),
        }


@dataclass
class VocabularyItem:
    phrase: str
    meaning: str

    def to_dict(self) -> dict[str, str]:
        return {"phrase": self.phrase, "meaning": self.meaning}


@dataclass
class AbstractLens:
    """A short principle the user's interactions encode."""
    statement: str

    def to_dict(self) -> dict[str, str]:
        return {"statement": self.statement}


@dataclass
class TasteLenses:
    rejections: list[ImplicitRejection]
    vocabulary: list[VocabularyItem]
    abstract_lenses: list[AbstractLens]

    @property
    def is_empty(self) -> bool:
        return not (self.rejections or self.vocabulary or self.abstract_lenses)

    def to_dict(self) -> dict[str, Any]:
        return {
            "rejections": [r.to_dict() for r in self.rejections],
            "vocabulary": [v.to_dict() for v in self.vocabulary],
            "abstract_lenses": [l.to_dict() for l in self.abstract_lenses],
            "vocabulary_share_text": self._vocabulary_share_text(),
            "abstract_lenses_share_text": self._abstract_lenses_share_text(),
        }

    def _vocabulary_share_text(self) -> str:
        if not self.vocabulary:
            return ""
        bullets = "\n".join(f'· "{v.phrase}" — {v.meaning}' for v in self.vocabulary)
        return f"Vocabulary I keep using that the model didn't introduce:\n\n{bullets}"

    def _abstract_lenses_share_text(self) -> str:
        if not self.abstract_lenses:
            return ""
        bullets = "\n".join(f"→ {l.statement}" for l in self.abstract_lenses)
        return f"The abstract lenses my interactions encode:\n\n{bullets}"


# ---- parsing -------------------------------------------------------------

# Section header: "## Implicit rejections (the moat)" or "## Implicit rejections"
_REJECTIONS_HEADER = re.compile(r"^##\s+Implicit\s+rejections\b.*$", re.MULTILINE)
_VOCABULARY_HEADER = re.compile(r"^##\s+Vocabulary\s+the\s+user\s+uses\b.*$", re.MULTILINE)
_ABSTRACT_LENSES_HEADER = re.compile(r"^##\s+Abstract\s+lenses\b.*$", re.MULTILINE)
_NEXT_SECTION = re.compile(r"^##\s+", re.MULTILINE)

# Within rejections: each card starts with "### {title}" and has 3 labeled lines.
_REJECTION_TITLE = re.compile(r"^###\s+(.+)$", re.MULTILINE)
_MODEL_FRAME = re.compile(r"^Model frame:\s*(.+?)$", re.MULTILINE)
_USER_SUBSTITUTED = re.compile(r"^User substituted:\s*(.+?)$", re.MULTILINE)
_WHY_MATTERS = re.compile(r"^Why this matters:\s*(.+?)$", re.MULTILINE)

# Vocabulary: `- "phrase" — meaning ...` (em-dash or double-dash)
_VOCAB_ITEM = re.compile(
    r'^-\s+"([^"]+)"\s*[—-]+\s*(.+?)(?:\s*—\s*\[[^\]]+\])?\.?\s*$',
    re.MULTILINE,
)

# Abstract lenses: `- statement ...`
_LENS_ITEM = re.compile(r"^-\s+(.+?)\.?\s*$", re.MULTILINE)


def _section_body(text: str, header_re: re.Pattern[str]) -> str:
    """Return the body between a section header and the next ## header (or EOF)."""
    header = header_re.search(text)
    if not header:
        return ""
    start = header.end()
    next_match = _NEXT_SECTION.search(text, start + 1)
    end = next_match.start() if next_match else len(text)
    return text[start:end].strip()


def _strip_quotes(s: str) -> str:
    """Strip surrounding double quotes if present, leaving the verbatim text."""
    s = s.strip()
    if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
        return s[1:-1]
    return s


def parse_rejections(text: str) -> list[ImplicitRejection]:
    body = _section_body(text, _REJECTIONS_HEADER)
    if not body:
        return []
    # Each card spans from one "### " to the next (or end of section).
    titles = list(_REJECTION_TITLE.finditer(body))
    rejections: list[ImplicitRejection] = []
    for i, m in enumerate(titles):
        start = m.end()
        end = titles[i + 1].start() if i + 1 < len(titles) else len(body)
        card = body[start:end]
        title = m.group(1).strip()

        frame_m = _MODEL_FRAME.search(card)
        user_m = _USER_SUBSTITUTED.search(card)
        why_m = _WHY_MATTERS.search(card)
        if not (frame_m and user_m and why_m):
            # Skip malformed cards rather than failing the whole parse.
            continue
        rejections.append(ImplicitRejection(
            title=title,
            model_frame=_strip_quotes(frame_m.group(1).strip()),
            user_substituted=_strip_quotes(user_m.group(1).strip()),
            why_matters=why_m.group(1).strip().rstrip("."),
        ))
    return rejections


def parse_vocabulary(text: str) -> list[VocabularyItem]:
    body = _section_body(text, _VOCABULARY_HEADER)
    if not body:
        return []
    items: list[VocabularyItem] = []
    for m in _VOCAB_ITEM.finditer(body):
        phrase = m.group(1).strip()
        meaning = m.group(2).strip().rstrip(".")
        # Trim trailing turn-references like "— turn [28], [33]"
        meaning = re.sub(r"\s*—\s*turn\s+.*$", "", meaning)
        meaning = re.sub(r"\s*—\s*\[[^\]]+\].*$", "", meaning)
        items.append(VocabularyItem(phrase=phrase, meaning=meaning))
    return items


def parse_abstract_lenses(text: str) -> list[AbstractLens]:
    body = _section_body(text, _ABSTRACT_LENSES_HEADER)
    if not body:
        return []
    items: list[AbstractLens] = []
    for m in _LENS_ITEM.finditer(body):
        statement = m.group(1).strip().rstrip(".")
        if statement:
            items.append(AbstractLens(statement=statement))
    return items


def parse_taste_lenses(text: str | None = None) -> TasteLenses:
    """Parse the /me document into structured taste lenses.

    Pass `text=None` (default) to read the live `~/.trinity/me.md`. Returns
    an empty TasteLenses when /me is missing or hasn't been built yet.
    """
    if text is None:
        text = load_me()
    if not text:
        return TasteLenses(rejections=[], vocabulary=[], abstract_lenses=[])
    return TasteLenses(
        rejections=parse_rejections(text),
        vocabulary=parse_vocabulary(text),
        abstract_lenses=parse_abstract_lenses(text),
    )
