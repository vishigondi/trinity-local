from __future__ import annotations

import hashlib
import re
from collections import defaultdict
from datetime import datetime
from difflib import SequenceMatcher

from .training_schema import SessionFeatures, TaskLink


_WS_RE = re.compile(r"\s+")
_NONWORD_RE = re.compile(r"[^a-z0-9\s]+")


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def _normalize_prompt(text: str | None) -> str:
    if not text:
        return ""
    text = text.lower().strip()
    text = _NONWORD_RE.sub(" ", text)
    text = _WS_RE.sub(" ", text).strip()
    return text[:240]


def _project_key(feature: SessionFeatures) -> str:
    return (feature.project_hint or feature.cwd or "").strip().lower()


def _prompt_tokens(text: str) -> set[str]:
    return {token for token in _normalize_prompt(text).split() if len(token) >= 3}


def _prompt_similarity(left: str | None, right: str | None) -> float:
    left_norm = _normalize_prompt(left)
    right_norm = _normalize_prompt(right)
    if not left_norm or not right_norm:
        return 0.0
    if left_norm == right_norm:
        return 1.0
    left_tokens = _prompt_tokens(left_norm)
    right_tokens = _prompt_tokens(right_norm)
    if not left_tokens or not right_tokens:
        return 0.0
    jaccard = len(left_tokens & right_tokens) / max(1, len(left_tokens | right_tokens))
    seq = SequenceMatcher(None, left_norm, right_norm).ratio()
    return max(jaccard, seq)


def _tool_similarity(left: SessionFeatures, right: SessionFeatures) -> float:
    left_names = {tool.name for tool in left.tools}
    right_names = {tool.name for tool in right.tools}
    if not left_names or not right_names:
        return 0.0
    return len(left_names & right_names) / max(1, len(left_names | right_names))


def _task_cluster_id(prompt_key: str, project_key: str) -> str:
    digest = hashlib.sha1(f"{project_key}|{prompt_key}".encode("utf-8")).hexdigest()
    return digest[:16]


def build_task_links(
    features: list[SessionFeatures],
    *,
    max_gap_seconds: float = 6 * 60 * 60,
    min_similarity: float = 0.58,
) -> list[TaskLink]:
    """Link nearby cross-provider sessions into coarse same-task clusters.

    This is intentionally conservative. It should be treated as a weak-label
    source, not a source of perfect truth.
    """

    grouped: dict[str, list[SessionFeatures]] = defaultdict(list)
    for feature in features:
        if not feature.first_user_text:
            continue
        if feature.extra.get("is_low_signal_prompt"):
            continue
        if feature.extra.get("is_automated"):
            continue
        project_key = _project_key(feature)
        if not project_key:
            continue
        grouped[project_key].append(feature)

    links: list[TaskLink] = []
    for project_key, group in grouped.items():
        group = sorted(group, key=lambda item: _parse_ts(item.started_at) or datetime.min)
        clusters: list[list[SessionFeatures]] = []
        for feature in group:
            placed = False
            for cluster in clusters:
                anchor = cluster[-1]
                anchor_ts = _parse_ts(anchor.ended_at or anchor.started_at)
                cur_ts = _parse_ts(feature.started_at)
                if anchor_ts and cur_ts:
                    delta = (cur_ts - anchor_ts).total_seconds()
                    if delta < 0 or delta > max_gap_seconds:
                        continue
                prompt_similarity = _prompt_similarity(anchor.first_user_text, feature.first_user_text)
                tool_similarity = _tool_similarity(anchor, feature)
                similarity = max(prompt_similarity, 0.75 * prompt_similarity + 0.25 * tool_similarity)
                if similarity >= min_similarity:
                    cluster.append(feature)
                    placed = True
                    break
            if not placed:
                clusters.append([feature])

        for cluster in clusters:
            prompt_key = _normalize_prompt(cluster[0].first_user_text)
            cluster_id = _task_cluster_id(prompt_key, project_key)
            for index, feature in enumerate(cluster):
                previous = cluster[index - 1] if index > 0 else None
                nxt = cluster[index + 1] if index + 1 < len(cluster) else None
                switched = None
                time_to_switch_seconds = None
                if previous is not None:
                    prev_ts = _parse_ts(previous.ended_at or previous.started_at)
                    cur_ts = _parse_ts(feature.started_at)
                    if prev_ts and cur_ts:
                        delta = (cur_ts - prev_ts).total_seconds()
                        if 0 <= delta <= max_gap_seconds:
                            time_to_switch_seconds = delta
                            switched = previous.provider != feature.provider
                links.append(
                    TaskLink(
                        task_cluster_id=cluster_id,
                        session_id=feature.session_id,
                        provider=feature.provider,
                        previous_provider=previous.provider if previous is not None else None,
                        next_provider=nxt.provider if nxt is not None else None,
                        switched=switched,
                        time_to_switch_seconds=time_to_switch_seconds,
                    )
                )
    return links
