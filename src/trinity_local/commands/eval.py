"""CLI handlers for the corpus-based eval harness (task #122).

MVP ships two subcommands:

  trinity-local eval-build [--limit N] [--source rejections] [--json]
    Build an eval set from the user's rejections.jsonl + prompt index.
    Persists to ~/.trinity/evals/<eval_id>.json. Returns stats.

  trinity-local eval-stats
    Inspect the LATEST eval set on disk. Shows item count + rejection-
    type distribution + basin distribution so the user can see what
    their personal eval set looks like before running it.

The runner (`trinity-local eval --target <provider>`) ships in a
follow-up tick. With just the builder + stats, the user already gets
the first marketing-ready artifact for launch-arc workstream #116:
"here's what we'd benchmark Model X against — YOUR actual rejections,
not someone's synthetic suite."
"""
from __future__ import annotations

import json
from pathlib import Path


def register(subparsers):
    build_p = subparsers.add_parser(
        "eval-build",
        help="Build an eval set from your prompt rejections (task #122)",
    )
    build_p.add_argument(
        "--limit", type=int, default=None,
        help="Cap the eval set to first N items (default: all rejections)",
    )
    build_p.add_argument(
        "--source", default="rejections",
        help="Eval source. MVP supports 'rejections'; cross_provider_pair lands in a follow-up.",
    )
    build_p.add_argument(
        "--json", dest="as_json", action="store_true",
        help="Output the full eval set as JSON to stdout (in addition to the file).",
    )
    build_p.set_defaults(handler=handle_eval_build)

    stats_p = subparsers.add_parser(
        "eval-stats",
        help="Show stats for the latest eval set on disk",
    )
    stats_p.add_argument(
        "--eval-id", default=None,
        help="Specific eval_id to inspect. Defaults to the most-recent eval set.",
    )
    stats_p.set_defaults(handler=handle_eval_stats)


def handle_eval_build(args):
    from ..evals.builder import build_eval_set, save_eval_set

    try:
        eval_set = build_eval_set(source=args.source, limit=args.limit)
    except FileNotFoundError as exc:
        print(f"✗ {exc}")
        raise SystemExit(2)
    except NotImplementedError as exc:
        print(f"✗ {exc}")
        raise SystemExit(2)

    path = save_eval_set(eval_set)

    if args.as_json:
        print(json.dumps(eval_set.to_dict(), indent=2, ensure_ascii=False))
        return

    # Human-readable summary: stats first (the marketing-legible
    # artifact), then where it's written.
    stats = eval_set.stats
    print(f"  Built eval set {eval_set.eval_id}")
    print(f"  Source: {eval_set.source}")
    print(f"  Items: {stats.get('items', 0)}")
    by_type = stats.get("by_rejection_type") or {}
    if by_type:
        print(f"  By rejection_type:")
        for kind, count in by_type.items():
            print(f"    {kind:<12} {count}")
    by_basin = stats.get("by_basin") or {}
    if by_basin:
        print(f"  By basin (top {min(8, len(by_basin))}):")
        for basin, count in list(by_basin.items())[:8]:
            print(f"    {basin:<8} {count}")
    print(f"\n  → {path}")
    print(f"\n  Next: `trinity-local eval --target <provider>` ships in a follow-up tick.")


def handle_eval_stats(args):
    from ..evals.builder import evals_dir, load_eval_set

    eval_id = args.eval_id
    if eval_id is None:
        # Pick the most-recent eval_<...>.json by mtime.
        candidates = sorted(
            evals_dir().glob("eval_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if not candidates:
            print("  No eval sets on disk yet — run `trinity-local eval-build` first.")
            raise SystemExit(1)
        eval_id = candidates[0].stem

    eval_set = load_eval_set(eval_id)
    if eval_set is None:
        print(f"✗ eval set {eval_id} not found at {evals_dir() / f'{eval_id}.json'}")
        raise SystemExit(2)

    stats = eval_set.stats
    print(f"  {eval_set.eval_id}  (built {eval_set.built_at}, source={eval_set.source})")
    print(f"  Items: {stats.get('items', 0)}")
    by_type = stats.get("by_rejection_type") or {}
    if by_type:
        print(f"\n  Rejection-type distribution:")
        total = sum(by_type.values())
        for kind, count in by_type.items():
            pct = (100.0 * count / total) if total else 0.0
            bar = "█" * int(round(pct / 4))  # 25 chars max bar
            print(f"    {kind:<12} {count:>3}  {pct:5.1f}%  {bar}")
    by_basin = stats.get("by_basin") or {}
    if by_basin:
        print(f"\n  Basin distribution (top 10):")
        for basin, count in list(by_basin.items())[:10]:
            print(f"    {basin:<8} {count}")

    # A few sample items so the user sees the eval shape, not just counts.
    sample = eval_set.items[:3]
    if sample:
        print(f"\n  Sample items:")
        for item in sample:
            preview = (item.prompt or "(no prompt text)")
            if len(preview) > 100:
                preview = preview[:100].rstrip() + "…"
            print(f"\n    [{item.rejection_type:<11}] {preview}")
            quote = item.rejected_response[:120].replace("\n", " ")
            print(f"       rejected: {quote}{'…' if len(item.rejected_response) > 120 else ''}")
