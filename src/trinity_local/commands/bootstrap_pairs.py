"""`trinity-local bootstrap-pairs` — cold-start personal routing without
running fresh councils.

The user's transcript exports already contain pairs: same question, asked
to claude vs gpt vs gemini, with each provider's answer on disk. Trinity
finds those pairs via embedding similarity and turns each cluster into a
synthetic council (one chairman synth call per cluster) — bootstrapping
the personal routing table from data Trinity already has, before the user
runs a single fresh council.

Cost model:
  - Zero member-dispatch calls (responses are on disk)
  - One chairman call per cluster (cheap)
  - Typical bootstrap: ~10-30 clusters → ~10-30 flagship calls → ~$1-3 in
    user's subscription credits

Compared to `replay-history`, which RE-RUNS each prompt against the
current lineup (3 member calls + 1 chairman = 4× the cost per prompt).
"""
from __future__ import annotations

import json
import sys


def register(subparsers):
    sp = subparsers.add_parser(
        "bootstrap-pairs",
        help="Discover cross-provider question pairs in your existing transcripts and synthesize them into virtual councils — cold-starts personal routing without fresh dispatch.",
    )
    sp.add_argument(
        "--similarity-threshold",
        type=float,
        default=0.85,
        help="Cosine similarity floor for two prompts to count as 'the same question' (default: 0.85)",
    )
    sp.add_argument(
        "--min-providers",
        type=int,
        default=2,
        help="Only synthesize clusters spanning at least N distinct providers (default: 2)",
    )
    sp.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Cap the number of clusters to synthesize. Default: all discovered.",
    )
    sp.add_argument(
        "--dry-run",
        action="store_true",
        help="Discover and print clusters but don't call any flagship.",
    )
    sp.add_argument(
        "--primary-provider",
        default=None,
        help="Force a specific chairman provider for every synthesis. Default: per-cluster pick.",
    )
    sp.set_defaults(handler=handle_bootstrap_pairs)


def handle_bootstrap_pairs(args):
    from ..cross_provider_pairs import cluster_to_synthesis_args, find_cross_provider_clusters
    from ..memory import iter_prompt_nodes

    # Uncapped: bootstrap-pairs is a corpus-wide mining pass (phases 1+2
    # of dream), not the hot search path. The default 5000-node cap
    # masks the older embedded cohort that dream needs.
    nodes = list(iter_prompt_nodes(limit=None))
    if not nodes:
        print(json.dumps({"ok": False, "reason": "no prompt nodes — run seed-from-taste-terminal first"}, indent=2))
        return 1

    clusters = find_cross_provider_clusters(
        nodes,
        similarity_threshold=args.similarity_threshold,
        min_providers=args.min_providers,
    )
    if not clusters:
        print(json.dumps({
            "ok": False,
            "reason": "no cross-provider clusters found",
            "checked_nodes": len(nodes),
            "hint": (
                "Either: (a) your transcripts don't contain enough overlapping "
                "questions across providers; (b) embeddings missing on most "
                "nodes (run `seed-from-taste-terminal` to populate); "
                "(c) similarity threshold too high (try --similarity-threshold 0.80)."
            ),
        }, indent=2))
        return 1

    if args.limit:
        clusters = clusters[: args.limit]

    if args.dry_run:
        report = {
            "ok": True,
            "mode": "dry-run",
            "checked_nodes": len(nodes),
            "clusters_found": len(clusters),
            "clusters": [
                {
                    "representative_prompt": c.representative_prompt[:200],
                    "providers": sorted(c.providers),
                    "coherence": round(c.coherence, 3),
                    "member_count": len(c.members),
                }
                for c in clusters[:20]  # cap dry-run output for readability
            ],
            "note": "Run without --dry-run to call chairman for each cluster.",
        }
        print(json.dumps(report, indent=2))
        return 0

    # Real run: synthesize each cluster via the existing MCP machinery.
    # `_synthesize_responses` persists a CouncilOutcome per call which
    # feeds personal_routing_table on read. Same pipeline as MCP
    # run_council(responses=[...]) — single source of truth.
    import asyncio
    from ..mcp_server import _synthesize_responses

    synthesized = 0
    failed = 0
    for i, cluster in enumerate(clusters, 1):
        synth_args = cluster_to_synthesis_args(cluster)
        if args.primary_provider:
            synth_args["primary_provider"] = args.primary_provider
        try:
            result = asyncio.run(_synthesize_responses(synth_args, synth_args["responses"]))
        except Exception as exc:
            print(
                f"  ✗ cluster {i}/{len(clusters)}: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
            failed += 1
            continue
        # Best-effort: parse the chairman output to surface the winner
        winner = "?"
        try:
            payload = json.loads(result[0].get("text", "{}")) if result else {}
            winner = payload.get("winner_provider") or "?"
        except (json.JSONDecodeError, AttributeError, TypeError):
            pass
        print(
            f"  ✓ cluster {i}/{len(clusters)} (providers={sorted(cluster.providers)}, "
            f"coherence={cluster.coherence:.2f}) → winner={winner}",
            file=sys.stderr,
        )
        synthesized += 1

    print(json.dumps({
        "ok": synthesized > 0,
        "checked_nodes": len(nodes),
        "clusters_found": len(clusters),
        "synthesized": synthesized,
        "failed": failed,
    }, indent=2))
    return 0 if synthesized > 0 else 1
