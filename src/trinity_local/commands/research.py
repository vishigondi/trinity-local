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
