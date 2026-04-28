"""Handler for research commands — replay, embed, rank."""
from __future__ import annotations

import json
import sys
import time


def register(subparsers):
    rp = subparsers.add_parser("replay", help="Replay historical transcripts into training examples")
    rp.add_argument("--source", action="append", default=None,
                     help="Source to replay (claude, codex, gemini, cowork). Repeatable.")
    rp.add_argument("--limit", type=int, default=None, help="Max examples per source")
    rp.add_argument("--json", dest="as_json", action="store_true")
    rp.set_defaults(handler=handle_replay)

    ep = subparsers.add_parser("embed", help="Embed replay examples (MLX if available, TF-IDF fallback)")
    ep.add_argument("--json", dest="as_json", action="store_true")
    ep.add_argument("--setup", action="store_true", help="Download the MLX embedding model")
    ep.add_argument("--status", action="store_true", help="Show model and cache status")
    ep.add_argument("--clear", action="store_true", help="Clear the embedding cache")
    ep.add_argument("--dim", type=int, default=512, help="Embedding dimension (default: 512)")
    ep.set_defaults(handler=handle_embed)

    rkp = subparsers.add_parser("rank", help="Run ranking evaluation: heuristic vs k-NN")
    rkp.add_argument("--k", type=int, default=5, help="k for k-NN (default: 5)")
    rkp.add_argument("--json", dest="as_json", action="store_true")
    rkp.set_defaults(handler=handle_rank)

    hp = subparsers.add_parser("hard", help="Mine hard examples from transcripts")
    hp.add_argument("--source", action="append", default=None,
                     help="Source to scan. Repeatable.")
    hp.add_argument("--limit", type=int, default=None, help="Max hard examples")
    hp.add_argument("--json", dest="as_json", action="store_true")
    hp.set_defaults(handler=handle_hard)

    hep = subparsers.add_parser("hardeval", help="Evaluate on hard examples only")
    hep.add_argument("--k", type=int, default=5, help="k for k-NN (default: 5)")
    hep.add_argument("--dim", type=int, default=512, help="Embedding dimension")
    hep.add_argument("--json", dest="as_json", action="store_true")
    hep.set_defaults(handler=handle_hardeval)

    ap = subparsers.add_parser("analytics", help="k-NN advisory analytics report")
    ap.add_argument("--json", dest="as_json", action="store_true")
    ap.set_defaults(handler=handle_analytics)


def handle_replay(args):
    from ..research.replay import replay_all, examples_dir

    sources = args.source or ["claude", "codex", "gemini", "cowork"]
    start = time.monotonic()
    results = replay_all(sources=sources, limit=args.limit)
    elapsed = time.monotonic() - start

    if args.as_json:
        payload = {
            source: {
                "sessions_scanned": stats.sessions_scanned,
                "examples_generated": stats.examples_generated,
                "skipped_low_signal": stats.skipped_low_signal,
                "skipped_no_prompt": stats.skipped_no_prompt,
                "errors": stats.errors,
            }
            for source, stats in results.items()
        }
        payload["_elapsed_seconds"] = round(elapsed, 2)
        payload["_examples_dir"] = str(examples_dir())
        print(json.dumps(payload, indent=2))
        return

    total_examples = sum(s.examples_generated for s in results.values())
    total_scanned = sum(s.sessions_scanned for s in results.values())
    print(f"Replay complete in {elapsed:.1f}s")
    print(f"  Scanned: {total_scanned} sessions")
    print(f"  Generated: {total_examples} examples")
    print()
    for source, stats in results.items():
        print(f"  {source}:")
        print(f"    scanned={stats.sessions_scanned}  examples={stats.examples_generated}  "
              f"low_signal={stats.skipped_low_signal}  no_prompt={stats.skipped_no_prompt}  "
              f"errors={stats.errors}")
    print(f"\n  Examples at: {examples_dir()}")


def handle_embed(args):
    from .. import embeddings as emb

    # Sub-commands
    if args.setup:
        message = emb.setup_model()
        print(message)
        return

    if args.status:
        status = emb.model_status()
        if args.as_json:
            print(json.dumps(status, indent=2))
        else:
            print(f"  Backend:    {status['backend']}")
            print(f"  MLX ready:  {status['mlx_available']}")
            if status['model_path']:
                print(f"  Model:      {status['model_path']}")
            print(f"  Cache:      {status['cache_entries']} entries ({status['cache_size_bytes']:,} bytes)")
        return

    if args.clear:
        from ..embeddings.cache import clear_cache
        count = clear_cache()
        print(f"Cleared {count} cached embeddings.")
        return

    # Main: embed all replay examples using the shared embeddings package
    from ..research.replay import load_examples
    from ..research.embeddings import save_embeddings, EmbeddingRecord
    import hashlib

    examples = load_examples()
    if not examples:
        print("No examples found. Run 'trinity-local replay' first.")
        return

    backend = emb.get_backend()
    dim = args.dim
    start = time.monotonic()

    records: list[EmbeddingRecord] = []
    for ex in examples:
        t = ex.transcript
        parts: list[str] = []
        if t.first_user_text:
            parts.append(t.first_user_text[:1500])
        if t.task_kind_hint:
            parts.append(f"[task:{t.task_kind_hint}]")
        tool_names = [tool.name for tool in t.tools[:5]]
        if tool_names:
            parts.append(f"[tools:{','.join(tool_names)}]")
        text = " ".join(parts)
        if not text.strip():
            continue

        vector = emb.embed(text, dim=dim)
        records.append(EmbeddingRecord(
            example_id=ex.example_id,
            provider=ex.chosen_provider,
            label=ex.label,
            task_kind=t.task_kind_hint or "general",
            method=backend,
            vector=vector,
            text_hash=hashlib.sha1(text.encode()).hexdigest()[:16],
        ))

    path = save_embeddings(records)
    elapsed = time.monotonic() - start

    if args.as_json:
        print(json.dumps({
            "examples": len(examples),
            "embeddings": len(records),
            "vector_dim": dim,
            "method": backend,
            "path": str(path),
            "elapsed_seconds": round(elapsed, 2),
        }, indent=2))
        return

    print(f"Embedded {len(records)} examples in {elapsed:.1f}s")
    print(f"  Method: {backend} (dim={dim})")
    print(f"  Saved to: {path}")


def handle_rank(args):
    from ..research.replay import load_examples
    from ..research.embeddings import load_embeddings
    from ..research.ranking import run_evaluation, save_evaluation

    examples = load_examples()
    embeddings = load_embeddings()

    if not examples:
        print("No examples found. Run 'trinity-local replay' first.")
        return
    if not embeddings:
        print("No embeddings found. Run 'trinity-local embed' first.")
        return

    start = time.monotonic()
    reports = run_evaluation(examples, embeddings, k=args.k)
    report_path = save_evaluation(reports)
    elapsed = time.monotonic() - start

    if args.as_json:
        payload = {name: report.to_dict() for name, report in reports.items()}
        payload["_elapsed_seconds"] = round(elapsed, 2)
        payload["_report_path"] = str(report_path)
        print(json.dumps(payload, indent=2))
        return

    print(f"Ranking evaluation in {elapsed:.1f}s")
    print()
    for name, report in reports.items():
        print(f"  {name}:")
        print(f"    accuracy: {report.accuracy:.1%}  ({report.correct}/{report.total})")
        if report.label_accuracy:
            print(f"    by label:  {', '.join(f'{k}={v:.0%}' for k, v in sorted(report.label_accuracy.items()))}")
        if report.provider_accuracy:
            print(f"    by provider: {', '.join(f'{k}={v:.0%}' for k, v in sorted(report.provider_accuracy.items()))}")
        if report.task_kind_accuracy:
            print(f"    by task_kind: {', '.join(f'{k}={v:.0%}' for k, v in sorted(report.task_kind_accuracy.items()))}")
        print()
    print(f"  Report: {report_path}")

    # Highlight the winner
    if len(reports) >= 2:
        best = max(reports.items(), key=lambda x: x[1].accuracy)
        print(f"\n  → Best: {best[0]} ({best[1].accuracy:.1%})")
        heuristic = reports.get("heuristic")
        knn = reports.get("knn")
        if heuristic and knn:
            delta = knn.accuracy - heuristic.accuracy
            if delta > 0:
                print(f"  → k-NN beats heuristic by {delta:.1%}")
            elif delta < 0:
                print(f"  → Heuristic still wins by {abs(delta):.1%}")
            else:
                print(f"  → Tied")


def handle_hard(args):
    from ..research.hard_mining import (
        mine_hard_via_embeddings,
        save_hard_examples,
        hard_examples_dir,
    )

    sources = args.source or ["claude", "codex", "gemini", "cowork"]
    start = time.monotonic()
    hard_examples, stats = mine_hard_via_embeddings(sources)
    out_dir = save_hard_examples(hard_examples)
    elapsed = time.monotonic() - start

    if args.as_json:
        print(json.dumps({
            "sessions_scanned": stats.sessions_scanned,
            "total_hard": stats.total_hard,
            "switched": stats.switched,
            "failed": stats.failed,
            "needs_council": stats.needs_council,
            "disagreement": stats.disagreement,
            "rerouted": stats.rerouted,
            "cross_provider_pairs": stats.cross_provider_pairs,
            "errors": stats.errors,
            "elapsed_seconds": round(elapsed, 2),
            "output_dir": str(out_dir),
        }, indent=2))
        return

    print(f"Hard mining complete in {elapsed:.1f}s")
    print(f"  Scanned: {stats.sessions_scanned} sessions")
    print(f"  Hard examples: {stats.total_hard}")
    print()
    print(f"  By type:")
    print(f"    switched:      {stats.switched}")
    print(f"    failed:        {stats.failed}")
    print(f"    needs_council: {stats.needs_council}")
    print(f"    disagreement:  {stats.disagreement}")
    print(f"    rerouted:      {stats.rerouted} ({stats.cross_provider_pairs} cross-provider pairs)")
    print(f"    errors:        {stats.errors}")
    print(f"\n  Output: {out_dir}")


def handle_hardeval(args):
    from ..research.hard_mining import load_hard_examples
    from ..research.hard_eval import run_hard_eval, save_hard_eval
    from ..research.embeddings import EmbeddingRecord, save_embeddings
    from .. import embeddings as emb
    import hashlib

    # Load hard examples
    hard_examples_raw = load_hard_examples()
    if not hard_examples_raw:
        print("No hard examples found. Run 'trinity-local hard' first.")
        return

    # Convert to RoutingExamples for eval
    hard_routing = [h.to_routing_example() for h in hard_examples_raw]
    hard_types = {h.example_id: h.hard_type for h in hard_examples_raw}

    # Embed the hard examples
    dim = args.dim
    backend = emb.get_backend()
    start = time.monotonic()

    records: list[EmbeddingRecord] = []
    for ex in hard_routing:
        t = ex.transcript
        parts: list[str] = []
        if t.first_user_text:
            parts.append(t.first_user_text[:1500])
        if t.task_kind_hint:
            parts.append(f"[task:{t.task_kind_hint}]")
        tool_names = [tool.name for tool in t.tools[:5]]
        if tool_names:
            parts.append(f"[tools:{','.join(tool_names)}]")
        text = " ".join(parts)
        if not text.strip():
            continue

        vector = emb.embed(text, dim=dim)
        records.append(EmbeddingRecord(
            example_id=ex.example_id,
            provider=ex.chosen_provider,
            label=ex.label,
            task_kind=t.task_kind_hint or "general",
            method=backend,
            vector=vector,
            text_hash=hashlib.sha1(text.encode()).hexdigest()[:16],
        ))

    # Run evaluation
    reports = run_hard_eval(hard_routing, records, k=args.k, hard_types=hard_types)
    report_path = save_hard_eval(reports)
    elapsed = time.monotonic() - start

    if args.as_json:
        payload = {name: report.to_dict() for name, report in reports.items()}
        payload["_elapsed_seconds"] = round(elapsed, 2)
        payload["_report_path"] = str(report_path)
        print(json.dumps(payload, indent=2))
        return

    print(f"Hard evaluation in {elapsed:.1f}s")
    print(f"  Backend: {backend} (dim={dim})")
    print(f"  Hard examples: {len(hard_routing)}")
    print()

    for name, report in reports.items():
        print(f"  ── {name.upper()} ──")
        print(f"    Total: {report.total_hard}")
        if report.by_hard_type:
            print(f"    By type: {', '.join(f'{k}={v}' for k, v in sorted(report.by_hard_type.items()))}")

        print()
        print(f"    1. Reroute recall:       {_fmt_pct(report.reroute_recall)}  ({report.reroute_detected}/{report.reroute_total})")
        print(f"    2. needs_council prec:   {_fmt_pct(report.needs_council_precision)}")
        print(f"       needs_council recall: {_fmt_pct(report.needs_council_recall)}")
        print(f"    3. Switch accuracy:      {_fmt_pct(report.switch_accuracy)}  ({report.switch_correct}/{report.switch_total})")
        print(f"    4. Top-2 provider acc:   {_fmt_pct(report.top2_provider_accuracy)}  ({report.top2_correct}/{report.top2_total})")
        print(f"    5. NN avg similarity:    {_fmt_f(report.nn_avg_similarity)}")
        print(f"       NN min similarity:    {_fmt_f(report.nn_min_similarity)}")
        print(f"       NN label agreement:   {_fmt_pct(report.nn_avg_label_agreement)}")

        if report.label_accuracy:
            print(f"    Label accuracy: {', '.join(f'{k}={v:.0%}' for k, v in sorted(report.label_accuracy.items()))}")
        if report.confusion:
            print(f"    Confusion: {json.dumps(report.confusion)}")
        print()

    print(f"  Report: {report_path}")


def _fmt_pct(v):
    return f"{v:.1%}" if v is not None else "N/A"


def _fmt_f(v):
    return f"{v:.4f}" if v is not None else "N/A"


def handle_analytics(args):
    from ..knn_analytics import generate_report, save_report

    report = generate_report()
    report_path = save_report(report)

    if args.as_json:
        print(json.dumps(report.to_dict(), indent=2))
        return

    print(f"k-NN Advisory Analytics")
    print(f"  Total events: {report.total_events}")
    print(f"  k-NN active:  {report.knn_active_count}")
    print(f"  k-NN missed:  {report.knn_inactive_count}")
    print()

    # Evidence spam
    print(f"  Evidence spam check:")
    print(f"    avg lines/event: {report.evidence_count_avg:.1f}")
    print(f"    max lines:       {report.evidence_count_max}")
    print(f"    p95 lines:       {report.evidence_count_p95}")
    print()

    # Upgrade tracking
    print(f"  Upgrade tracking:")
    print(f"    upgrades:   {report.upgrades_total} ({_fmt_pct(report.upgrade_rate)})")
    print(f"    council total:      {report.council_triggered}")
    print(f"    council by heuristic: {report.council_by_heuristic}")
    print(f"    council by k-NN:      {report.council_by_knn}")
    print()

    # Threshold analysis
    if report.confidence_by_task_kind:
        print(f"  Threshold by task kind:")
        for kind, stats in sorted(report.confidence_by_task_kind.items()):
            print(f"    {kind:16s}: mean={stats['mean']:.2f}  min={stats['min']:.2f}  max={stats['max']:.2f}  n={stats['count']}")
        print()

    if report.confidence_by_provider_pair:
        print(f"  Reroute similarity by provider pair:")
        for pair, stats in sorted(report.confidence_by_provider_pair.items()):
            print(f"    {pair:20s}: mean={stats['mean']:.2f}  min={stats['min']:.2f}  max={stats['max']:.2f}  n={stats['count']}")
        print()

    # Product metrics
    print(f"  Product metrics:")
    print(f"    suggestions tracked:  {report.suggestions_total}")
    print(f"    acted on:             {report.suggestions_acted_on} ({_fmt_pct(report.act_rate)})")
    print(f"    later switched:       {report.later_switched_total} ({_fmt_pct(report.later_switch_rate)})")
    if report.switch_targets:
        print(f"    switch targets:       {', '.join(f'{k}={v}' for k, v in report.switch_targets.items())}")
    print()

    # Alerts
    if report.alerts:
        print(f"  ⚠ ALERTS:")
        for alert in report.alerts:
            print(f"    • {alert}")
    else:
        print(f"  ✓ No alerts")

    print(f"\n  Report: {report_path}")
