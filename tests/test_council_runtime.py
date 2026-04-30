from __future__ import annotations

from trinity_local.council_runtime import parse_peer_review_sections, parse_synthesis_sections


def test_parse_synthesis_sections_accepts_markdown_heading_variants():
    text = """## What Each Response Does Best
Response A is strongest on specificity.

## Key Tradeoffs
Response B is simpler but less complete.

## What Reviewers Found
Reviewers agreed that both answers were accurate.

## Decision Framework
Choose Response A if you value depth.
"""

    sections = parse_synthesis_sections(text)

    assert sections["best_answer"] == "Response A is strongest on specificity."
    assert sections["differences"] == "Response B is simpler but less complete."
    assert sections["agreement"] == "Reviewers agreed that both answers were accurate."
    assert sections["winner"] == "Choose Response A if you value depth."


def test_parse_peer_review_sections_accepts_numbered_and_colon_headers():
    text = """1. Agreement:
Both responses are factually sound.

2. Strengths
- Response A is clearer.

3. Concerns
- Response B buries the recommendation.

Final Ranking
Response A
Response B
"""

    sections = parse_peer_review_sections(text)

    assert sections["agreement"] == "Both responses are factually sound."
    assert sections["strengths"] == "- Response A is clearer."
    assert sections["weaknesses"] == "- Response B buries the recommendation."
    assert sections["ranking"] == "Response A\nResponse B"
