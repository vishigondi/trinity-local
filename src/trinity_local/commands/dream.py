"""`trinity-local dream` — the once-or-nightly cold-start pass.

The user's analog to Anthropic's *Dreaming*. Walks ALL embedded prompts
on disk, finds cross-provider question pairs, turns each into a virtual
council via chairman synthesis, then re-consolidates cortex rules and
re-builds the /me lenses.

One command, four phases, end-to-end cold-start without fresh dispatch
beyond chairman calls.

Cost model (typical first run):
  - Phase 1 (discover): free, embeddings already on disk
  - Phase 2 (synthesize): ~one flagship call per cross-provider cluster.
    Usually 10–100 clusters.
  - Phase 3 (consolidate): one flagship call per basin with >= --min-basin-size
    outcomes. Caps at the cortex `--min-basin-size` default (3).
  - Phase 4 (me-build): three flagship calls total (turn-pairs, decisions,
    pair-mining) per the existing /me pipeline.

So a full dream = (n_clusters + n_basins + 3) flagship calls. For a
fresh install with 18k seeded nodes, that's typically $5–15 of
subscription credit — small for a one-time bootstrap that produces a
fully populated routing table + lenses.
"""
from __future__ import annotations

import json
import os
import sys
import time
from types import SimpleNamespace


def register(subparsers):
    sp = subparsers.add_parser(
        "dream",
        help="Cold-start the whole personal layer in one pass: discover cross-provider question pairs in your transcripts, synthesize each into a virtual council, re-consolidate cortex, re-build /me lenses. Anthropic's Dreaming, but on your data.",
    )
    sp.add_argument(
        "--similarity-threshold",
        type=float,
        default=0.85,
        help="Cosine sim floor for two prompts to count as the same question (default: 0.85)",
    )
    sp.add_argument(
        "--max-clusters",
        type=int,
        default=None,
        help="Cap the number of clusters synthesized this run. Default: all discovered.",
    )
    sp.add_argument(
        "--skip-consolidate",
        action="store_true",
        help="Skip the cortex consolidation phase (you'll need to run `trinity-local consolidate` separately).",
    )
    sp.add_argument(
        "--skip-lens-build",
        action="store_true",
        # Backward-compat short option until anyone scripting against the
        # pre-rename CLI surfaces (no one has, but it's a safe alias).
        dest="skip_me_build",
        help="Skip the lens rebuild phase (Phase 4 — `lens-build`).",
    )
    sp.add_argument(
        "--skip-vocabulary",
        action="store_true",
        help="Skip Phase 2.5: scanning vocabulary for homonyms + synonyms.",
    )
    sp.add_argument(
        "--skip-distill",
        action="store_true",
        help="Skip Phase 5: emitting the one-paragraph core.md distillation.",
    )
    sp.add_argument(
        "--dry-run",
        action="store_true",
        help="Discover clusters and print the plan; don't call any flagship.",
    )
    sp.add_argument(
        "--primary-provider",
        default=None,
        help="Force a specific chairman provider for synthesis + consolidation.",
    )
    sp.set_defaults(handler=handle_dream)


def _all_prompt_nodes_uncapped() -> list:
    """Back-compat alias — the canonical uncapped walker is
    `iter_prompt_nodes(limit=None)` from trinity_local.memory.store, which
    has been there all along. This helper used to reinvent it; kept as a
    thin wrapper so existing tests that monkey-patch it stay green.

    New code should call `iter_prompt_nodes(limit=None)` directly — it's
    cached in-process by file mtime so dream/vocabulary/basins all share
    the parse cost on a hot session."""
    from ..memory.store import iter_prompt_nodes
    return list(iter_prompt_nodes(limit=None))


def handle_dream(args):
    started = time.monotonic()
    from ..cross_provider_pairs import (
        cluster_to_synthesis_args,
        find_cross_provider_clusters,
    )

    report = {
        "ok": True,
        "phases": {},
        "total_ms": 0,
    }

    # ── Phase 1: discover ──────────────────────────────────────────────
    print("dream phase 1/4: scanning embeddings for cross-provider pairs…", file=sys.stderr)
    nodes = _all_prompt_nodes_uncapped()
    with_emb = sum(1 for n in nodes if n.embedding)
    clusters = find_cross_provider_clusters(
        nodes,
        similarity_threshold=args.similarity_threshold,
        min_providers=2,
    )
    if args.max_clusters:
        clusters = clusters[: args.max_clusters]
    report["phases"]["discover"] = {
        "checked_nodes": len(nodes),
        "with_embedding": with_emb,
        "clusters_found": len(clusters),
    }
    print(
        f"  ✓ {len(clusters)} cross-provider cluster(s) from {with_emb} embedded nodes "
        f"(of {len(nodes)} total)",
        file=sys.stderr,
    )

    if args.dry_run:
        report["phases"]["discover"]["cluster_preview"] = [
            {
                "prompt": c.representative_prompt[:160],
                "providers": sorted(c.providers),
                "coherence": round(c.coherence, 3),
            }
            for c in clusters[:10]
        ]
        report["total_ms"] = int((time.monotonic() - started) * 1000)
        print(json.dumps(report, indent=2))
        return 0

    if not clusters:
        print(
            "  no cross-provider pairs to synthesize — try --similarity-threshold 0.80 "
            "or run seed-from-taste-terminal to populate embeddings.",
            file=sys.stderr,
        )

    # ── Phase 2: synthesize each cluster as a virtual council ──────────
    if clusters:
        print(
            f"dream phase 2/4: synthesizing {len(clusters)} virtual council(s)…",
            file=sys.stderr,
        )
        synthesized, failed = _synthesize_all(clusters, args.primary_provider)
        report["phases"]["synthesize"] = {
            "attempted": len(clusters),
            "synthesized": synthesized,
            "failed": failed,
        }
        print(
            f"  ✓ {synthesized}/{len(clusters)} virtual councils landed "
            f"({failed} failed)",
            file=sys.stderr,
        )
    else:
        report["phases"]["synthesize"] = {
            "attempted": 0, "synthesized": 0, "failed": 0,
        }

    # ── Phase 3: re-consolidate cortex ─────────────────────────────────
    if args.skip_consolidate:
        print("dream phase 3/4: SKIPPED (--skip-consolidate)", file=sys.stderr)
        report["phases"]["consolidate"] = {"skipped": True}
    else:
        print("dream phase 3/4: consolidating cortex rules…", file=sys.stderr)
        consolidate_report = _consolidate(args.primary_provider or "claude")
        report["phases"]["consolidate"] = consolidate_report

    # ── Phase 4: rebuild lenses + freeze routing to disk ───────────────
    if args.skip_me_build:
        print("dream phase 4/5: SKIPPED (--skip-lens-build)", file=sys.stderr)
        report["phases"]["me_build"] = {"skipped": True}
    else:
        print("dream phase 4/5: rebuilding lenses + freezing routing…", file=sys.stderr)
        me_report = _me_build(args.primary_provider or "claude")
        # Freeze the empirical-memory entry to memories/routing.json so the
        # chairman context loader (and Phase 5 distill) sees the routing
        # signal without re-walking council_outcomes/ on every call.
        try:
            from ..personal_routing import freeze_routing_to_disk
            table = freeze_routing_to_disk()
            me_report["routing_frozen"] = {
                "task_types": len(table or {}),
            }
        except Exception as exc:
            me_report["routing_frozen"] = {"error": f"{type(exc).__name__}: {exc}"}
        report["phases"]["me_build"] = me_report

    # ── Phase 2.5: vocabulary distillation ─────────────────────────────
    # Pure-geometric scan; zero LLM calls. Builds the language-memory
    # entry in the core-memories set.
    if getattr(args, "skip_vocabulary", False):
        print("dream phase 2.5/5: SKIPPED (--skip-vocabulary)", file=sys.stderr)
        report["phases"]["vocabulary"] = {"skipped": True}
    else:
        print("dream phase 2.5/5: scanning vocabulary for overloads…", file=sys.stderr)
        report["phases"]["vocabulary"] = _vocabulary_scan()

    # ── Phase 5: distill the five plural memories into singular core.md ──
    # Always runs (cheap — one flagship call). Even if upstream phases
    # were skipped, distill emits a core.md from whatever memories DO
    # exist on disk.
    if getattr(args, "skip_distill", False):
        print("dream phase 5/5: SKIPPED (--skip-distill)", file=sys.stderr)
        report["phases"]["distill"] = {"skipped": True}
    else:
        print("dream phase 5/5: distilling memories → core.md…", file=sys.stderr)
        distill_report = _distill(args.primary_provider or "claude")
        report["phases"]["distill"] = distill_report

    report["total_ms"] = int((time.monotonic() - started) * 1000)
    print(json.dumps(report, indent=2))
    return 0


def _vocabulary_scan() -> dict:
    """Phase 2.5 — geometric scan of the user's terminology."""
    from ..vocabulary import distill_vocabulary
    return distill_vocabulary()


def _distill(provider: str) -> dict:
    """Phase 5 — collapse the five plural core memories into one paragraph."""
    from ..distill import distill_via_chairman
    return distill_via_chairman(provider=provider)


def _synthesize_all(clusters, primary_provider):
    """Run one chairman synth per cluster. Reuses the MCP machinery so the
    persisted CouncilOutcomes flow into personal_routing / consolidate
    via the standard path."""
    import asyncio
    from ..cross_provider_pairs import cluster_to_synthesis_args
    from ..mcp_server import _synthesize_responses

    synthesized = 0
    failed = 0
    for i, cluster in enumerate(clusters, 1):
        synth_args = cluster_to_synthesis_args(cluster)
        if primary_provider:
            synth_args["primary_provider"] = primary_provider
        try:
            asyncio.run(_synthesize_responses(synth_args, synth_args["responses"]))
            synthesized += 1
            if i % 10 == 0 or i == len(clusters):
                print(f"    {i}/{len(clusters)} synthesized…", file=sys.stderr)
        except Exception as exc:
            failed += 1
            print(
                f"    ! cluster {i} synth failed: {type(exc).__name__}: {exc}",
                file=sys.stderr,
            )
    return synthesized, failed


def _consolidate(provider: str) -> dict:
    """Invoke the existing `consolidate` handler in-process."""
    from .cortex import handle_consolidate

    consolidate_args = SimpleNamespace(
        min_basin_size=3,
        dry_run=False,
        basin=None,
        provider=provider,
        audit=False,
        audit_provider=None,
    )
    import io
    import contextlib
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            rc = handle_consolidate(consolidate_args)
    except SystemExit as exc:
        return {"ok": False, "error": f"consolidate exited: {exc}"}
    captured = buf.getvalue().strip()
    try:
        payload = json.loads(captured) if captured else {}
    except json.JSONDecodeError:
        payload = {"raw": captured}
    payload["rc"] = rc
    return payload


def _me_build(provider: str) -> dict:
    """Invoke the existing `me-build` handler in-process. Best-effort —
    if the lens pipeline doesn't have enough data yet, it'll skip phases
    gracefully and report that."""
    try:
        from .me import handle_me_build
    except ImportError:
        return {"ok": False, "error": "me-build handler not importable"}

    me_args = SimpleNamespace(
        provider=provider,
        limit=None,
        stages=None,
        force=False,
    )
    import io
    import contextlib
    buf = io.StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            handle_me_build(me_args)
    except SystemExit as exc:
        return {"ok": False, "error": f"me-build exited: {exc}"}
    except TypeError as exc:
        # handle_me_build's actual signature may differ — surface the gap
        # without breaking dream.
        return {"ok": False, "error": f"me-build args mismatch: {exc}"}
    except Exception as exc:
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    captured = buf.getvalue().strip()
    try:
        return json.loads(captured) if captured else {"ok": True, "raw_empty": True}
    except json.JSONDecodeError:
        return {"ok": True, "raw": captured[:1000]}
