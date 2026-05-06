"""replay-history — re-evaluate the user's past prompts against the current model lineup.

This is the v1 mechanism that produces the personal routing table:
  1. Pick top-N PromptNodes by replay_value_score (uncertainty + theme + staleness,
     prefer prompts that have NOT been re-evaluated against the current lineup).
  2. For each candidate, build a council bundle with the original prompt as task
     and (later) TurnWindow context as hidden context.
  3. Run a council; the chairman emits Routing JSON.
  4. Print the per-task-type aggregation as the CLI summary. The canonical
     personal routing table is computed on demand by readers
     (chairman_picker + launchpad) directly from ~/.trinity/council_outcomes/.
  5. Launchpad reads the JSON to render the per-task-type "best provider" view.

No LLM calls outside the councils themselves (per the architectural commitment).
"""
from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from ..config import load_config
from ..council_runner import run_council
from ..council_runtime import create_prompt_bundle, save_prompt_bundle
from ..memory import PromptNode, iter_prompt_nodes
from ..memory.replay_value import (
    infer_hardness,
    replay_value_score,
    staleness_score,
    theme_score,
)
from ..ranker import predict_strongest_chairman
from ..task_kinds import guess_task_kind
from ..utils import now_iso, stable_id


def register(subparsers):
    parser = subparsers.add_parser(
        "replay-history",
        help="Re-evaluate top-N replay-worthy past prompts against the current model lineup",
    )
    parser.add_argument("--limit", type=int, default=20, help="Max councils to run")
    parser.add_argument("--task-type", default=None, help="Only replay prompts of this task_kind")
    parser.add_argument("--source", default=None, help="Only replay prompts from this provider source")
    parser.add_argument(
        "--members",
        nargs="+",
        default=["claude", "gemini", "codex"],
        help="Council members to compare",
    )
    parser.add_argument(
        "--primary-provider",
        default=None,
        help="Chairman provider. Auto-selected per prompt if omitted.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-run prompts even if they already have a council against the current lineup",
    )
    parser.add_argument("--dry-run", action="store_true", help="Print candidates without running councils")
    parser.add_argument("--cwd", default=".", help="Working dir for provider runs")
    parser.add_argument("--quiet", action="store_true", help="Suppress confirmation prompt")
    parser.set_defaults(handler=handle_replay_history)


def _candidate_score(node: PromptNode) -> float:
    """Score for replay-history selection. Empty query → all weight on
    intrinsic factors (uncertainty, theme, staleness, importance)."""
    hardness = infer_hardness(node)
    stale = staleness_score(node.last_replayed_at)
    return replay_value_score(
        prompt_similarity=0.0,
        cluster_density=0.0,
        known_theme=theme_score(node.themes),
        uncertainty=hardness,
        importance=node.importance or 0.0,
        staleness=stale,
        recently_run=1.0 if stale < 0.25 else 0.0,
    )


def _select_candidates(
    *,
    limit: int,
    task_type_filter: str | None,
    source_filter: str | None,
    force: bool,
) -> list[tuple[PromptNode, str]]:
    """Pick replay-worthy nodes. Returns (node, task_kind) pairs."""
    candidates: list[tuple[PromptNode, str, float]] = []
    for node in iter_prompt_nodes():
        if not node.text or len(node.text) < 8:
            continue
        if source_filter and node.provider != source_filter:
            continue
        kind = guess_task_kind(node.text)
        if task_type_filter and kind != task_type_filter:
            continue
        if not force and node.council_run_ids:
            # Already evaluated against current lineup at some point — skip
            # unless --force. Phase 9 will refine this with a model-version check.
            continue
        candidates.append((node, kind, _candidate_score(node)))
    candidates.sort(key=lambda triple: triple[2], reverse=True)
    return [(n, k) for n, k, _ in candidates[:limit]]


from ..personal_routing import aggregate_routing_table as _aggregate_routing_table


def _format_dry_run_row(idx: int, node: PromptNode, task_kind: str) -> str:
    snippet = node.text.replace("\n", " ").strip()
    if len(snippet) > 100:
        snippet = snippet[:97] + "..."
    return (
        f"  [{idx + 1:>3}] task_kind={task_kind:<15} provider={node.provider:<10} "
        f"councils={len(node.council_run_ids)} "
        f"→ {snippet}"
    )


def handle_replay_history(args):
    candidates = _select_candidates(
        limit=args.limit,
        task_type_filter=args.task_type,
        source_filter=args.source,
        force=args.force,
    )

    if not candidates:
        print(json.dumps({
            "ok": True,
            "candidates": 0,
            "councils_run": 0,
            "note": "No replay candidates found. Run `seed-from-taste-terminal` to populate the index, or relax filters.",
        }, indent=2))
        return

    print(f"Selected {len(candidates)} replay candidate(s):", file=sys.stderr)
    for i, (node, kind) in enumerate(candidates):
        print(_format_dry_run_row(i, node, kind), file=sys.stderr)

    if args.dry_run:
        print(json.dumps({
            "ok": True,
            "dry_run": True,
            "candidates": len(candidates),
            "preview": [
                {"prompt_id": n.id, "task_kind": k, "text": n.text[:120]}
                for n, k in candidates
            ],
        }, indent=2))
        return

    if not args.quiet:
        approx_calls = len(candidates) * (len(args.members) + 1)
        print(
            f"\nThis will run {len(candidates)} council(s) "
            f"(~{approx_calls} model calls) using your subscriptions. Proceed? [y/N] ",
            end="",
            file=sys.stderr,
        )
        try:
            answer = input().strip().lower()
        except EOFError:
            answer = ""
        if answer not in ("y", "yes"):
            print("Aborted.", file=sys.stderr)
            return

    config = load_config(getattr(args, "config", None))
    cwd = Path(args.cwd).expanduser().resolve()
    council_results: list[dict[str, Any]] = []

    started = time.time()
    for i, (node, kind) in enumerate(candidates):
        print(f"\n[{i + 1}/{len(candidates)}] Running council for: {node.text[:80]}...", file=sys.stderr)
        bundle = create_prompt_bundle(
            task_cluster_id=stable_id("cluster", "replay_history", node.text[:400]),
            task_text=node.text,
            context_excerpt=_build_hidden_context(node),
            goal="Find the strongest current-model answer for this past prompt.",
            comparison_instructions="Re-evaluate against the current model lineup.",
            origin_provider="replay_history",
            origin_session_id=node.transcript_id,
            metadata={
                "replay_history": True,
                "prompt_node_id": node.id,
                "task_kind": kind,
                "original_provider": node.provider,
            },
        )
        save_prompt_bundle(bundle)

        chairman = args.primary_provider or predict_strongest_chairman(
            node.text,
            available_providers=list(args.members),
        )
        try:
            t0 = time.time()
            result = run_council(
                config=config,
                bundle=bundle,
                member_providers=list(args.members),
                primary_provider=chairman,
                cwd=cwd,
                run_state_token=bundle.bundle_id,
            )
            elapsed = time.time() - t0
        except Exception as exc:
            print(f"  council failed: {exc}", file=sys.stderr)
            continue

        outcome = result.outcome
        routing_label = outcome.routing_label.to_dict() if outcome.routing_label else None
        council_results.append({
            "council_run_id": outcome.council_run_id,
            "prompt_node_id": node.id,
            "task_kind": kind,
            "primary_provider": outcome.primary_provider,
            "winner_provider": outcome.winner_provider,
            "elapsed_seconds": round(elapsed, 2),
            "routing_label": routing_label,
        })
        winner = outcome.winner_provider or (routing_label or {}).get("winner") or "unknown"
        overall = ""
        if routing_label and routing_label.get("provider_scores"):
            scores = routing_label["provider_scores"]
            if winner in scores and isinstance(scores[winner], dict):
                overall = f" (overall {scores[winner].get('overall', '?')})"
        print(f"  -> task_kind={kind} winner={winner}{overall} [{elapsed:.0f}s]", file=sys.stderr)

    elapsed_total = time.time() - started
    # Aggregate just THIS replay run's outcomes for the CLI summary. The
    # canonical personal routing table is computed on demand from all rated
    # outcomes on disk — see personal_routing.compute_personal_routing_table.
    table = _aggregate_routing_table(council_results)
    table["replay_history_run_at"] = now_iso()

    print(json.dumps({
        "ok": True,
        "candidates_seen": len(candidates),
        "councils_run": len(council_results),
        "elapsed_seconds": round(elapsed_total, 2),
        "by_task_type": table["by_task_type"],
        "best_per_task_type": table["best_per_task_type"],
    }, indent=2))


def _build_hidden_context(node: PromptNode) -> str:
    """Construct hidden TurnWindow-style context to ground the chairman.

    The user re-runs the original prompt as-is; we inject the *preceding*
    assistant turn so the new model has the framing the user was responding
    to. We deliberately do NOT include `following_assistant_text` (the
    original model's answer to this prompt) — including it would bias the
    fresh members toward agreeing with the original instead of judging the
    prompt independently.
    """
    if not node.preceding_assistant_text:
        return ""
    return (
        "Earlier in the original conversation, the assistant said:\n"
        f"{node.preceding_assistant_text}"
    )
