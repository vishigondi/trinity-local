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

    ep = subparsers.add_parser("embed", help="Generate TF-IDF embeddings for replay examples")
    ep.add_argument("--json", dest="as_json", action="store_true")
    ep.set_defaults(handler=handle_embed)

    rkp = subparsers.add_parser("rank", help="Run ranking evaluation: heuristic vs k-NN")
    rkp.add_argument("--k", type=int, default=5, help="k for k-NN (default: 5)")
    rkp.add_argument("--json", dest="as_json", action="store_true")
    rkp.set_defaults(handler=handle_rank)


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
    from ..research.replay import load_examples
    from ..research.embeddings import build_tfidf_vectors, save_embeddings, embeddings_path

    examples = load_examples()
    if not examples:
        print("No examples found. Run 'trinity-local replay' first.")
        return

    start = time.monotonic()
    records = build_tfidf_vectors(examples)
    path = save_embeddings(records)
    elapsed = time.monotonic() - start

    if args.as_json:
        print(json.dumps({
            "examples": len(examples),
            "embeddings": len(records),
            "vector_dim": len(records[0].vector) if records else 0,
            "method": "tfidf",
            "path": str(path),
            "elapsed_seconds": round(elapsed, 2),
        }, indent=2))
        return

    dim = len(records[0].vector) if records else 0
    print(f"Embedded {len(records)} examples in {elapsed:.1f}s")
    print(f"  Method: TF-IDF (dim={dim})")
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
