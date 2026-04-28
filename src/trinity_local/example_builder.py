from __future__ import annotations

import hashlib
from collections import defaultdict

from .feature_extractors import make_transcript_window
from .training_schema import RoutingExample, SessionFeatures, TaskLink


def _example_id(session_id: str, label: str) -> str:
    return hashlib.sha1(f"{session_id}|{label}".encode("utf-8")).hexdigest()[:16]


def _provider_rank(provider: str) -> int:
    order = {
        "cowork": 4,
        "claude": 3,
        "codex": 2,
        "gemini": 1,
    }
    return order.get(provider, 0)


def build_routing_examples(
    features: list[SessionFeatures],
    task_links: list[TaskLink],
) -> list[RoutingExample]:
    deduped_features: list[SessionFeatures] = []
    seen_feature_keys: set[tuple[str, str, str]] = set()
    for feature in features:
        key = (feature.provider, feature.session_id, feature.raw.source_path)
        if key in seen_feature_keys:
            continue
        seen_feature_keys.add(key)
        if not feature.first_user_text:
            continue
        if feature.extra.get("is_automated"):
            continue
        if feature.extra.get("is_low_signal_prompt"):
            continue
        deduped_features.append(feature)

    feature_by_session = {feature.session_id: feature for feature in deduped_features}
    links_by_cluster: dict[str, list[TaskLink]] = defaultdict(list)
    for link in task_links:
        links_by_cluster[link.task_cluster_id].append(link)

    examples: list[RoutingExample] = []
    for cluster_id, links in links_by_cluster.items():
        ordered = [
            link
            for link in links
            if link.session_id in feature_by_session
        ]
        ordered.sort(
            key=lambda link: (
                feature_by_session[link.session_id].started_at or "",
                feature_by_session[link.session_id].provider,
            )
        )
        if not ordered:
            continue

        best_link = max(ordered, key=lambda link: _provider_rank(link.provider))
        best_feature = feature_by_session[best_link.session_id]

        if len(ordered) >= 2 and len({link.provider for link in ordered}) >= 2:
            for link in ordered:
                feature = feature_by_session[link.session_id]
                if link.session_id == best_link.session_id:
                    label = "good_fit"
                    reasons = ["provider remained or emerged as best option within same task cluster"]
                    alternatives = [candidate.provider for candidate in ordered if candidate.provider != link.provider]
                else:
                    label = f"reroute_to_{best_link.provider}"
                    reasons = [f"same task later moved to {best_link.provider}"]
                    alternatives = [best_link.provider]
                examples.append(
                    RoutingExample(
                        example_id=_example_id(link.session_id, label),
                        transcript=make_transcript_window(feature),
                        task_link=link,
                        chosen_provider=best_feature.provider,
                        chosen_model=best_feature.model,
                        label=label,
                        confidence=0.7 if label == "good_fit" else 0.8,
                        alternatives=alternatives,
                        reasons=reasons,
                        source_event_ids=[link.session_id],
                    )
                )
        else:
            only_link = ordered[0]
            feature = feature_by_session[only_link.session_id]
            shell_commands = feature.outcome.shell_commands or 0
            did_use_web = bool(feature.did_use_web)
            did_use_mcp = bool(feature.did_use_mcp)
            if did_use_web and shell_commands == 0:
                label = "needs_council"
                reasons = ["research-heavy task with no observed cross-provider comparison"]
                confidence = 0.55
            else:
                label = "good_fit"
                reasons = ["single observed provider for this task cluster"]
                confidence = 0.5
            examples.append(
                RoutingExample(
                    example_id=_example_id(only_link.session_id, label),
                    transcript=make_transcript_window(feature),
                    task_link=only_link,
                    chosen_provider=feature.provider,
                    chosen_model=feature.model,
                    label=label,
                    confidence=confidence,
                    alternatives=["cowork"] if did_use_mcp else [],
                    reasons=reasons,
                    source_event_ids=[only_link.session_id],
                )
            )
    return examples
