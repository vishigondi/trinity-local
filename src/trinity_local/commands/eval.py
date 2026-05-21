"""CLI handlers for the corpus-based eval harness (task #122).

Four subcommands:

  trinity-local eval-build [--limit N] [--source rejections]
    Build an eval set from the user's rejections.jsonl + prompt index.
    Persists to ~/.trinity/evals/<eval_id>.json. Returns stats.

  trinity-local eval-stats [--eval-id ID]
    Inspect the LATEST eval set on disk. Shows item count + rejection-
    type distribution + basin distribution + sample items.

  trinity-local eval-run --target <provider> [--judge <provider>]
                         [--eval-id ID] [--limit N] [--no-score]
    Dispatch the eval set's prompts to <target> provider, then score
    each response against the rejected_response using <judge>. Persists
    results to ~/.trinity/evals/results/. THIS IS the empirical
    benchmark — score model X against the user's actual rejections.

  trinity-local eval-show [--target <provider>] [--eval-id ID]
                          [--limit-samples N]
    Inspect a past run result (default: most-recent). Renders aggregate
    score + per-rejection-axis bars + top/bottom sample items.
    Re-inspect without re-running; diff results across model releases.
"""
from __future__ import annotations

import json


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

    run_p = subparsers.add_parser(
        "eval-run",
        help="Dispatch the eval set against a target provider and score the results (task #122 / #116)",
    )
    run_p.add_argument(
        "--target", required=True,
        help="Provider to benchmark (claude / codex / gemini / ...).",
    )
    run_p.add_argument(
        "--judge", default=None,
        help="Provider that grades responses against the rejection axis. Defaults to a different provider than --target so the model isn't grading itself.",
    )
    run_p.add_argument(
        "--eval-id", default=None,
        help="Eval set to run. Defaults to the most-recent eval set on disk.",
    )
    run_p.add_argument(
        "--limit", type=int, default=None,
        help="Cap the dispatched items to first N (default: all). Useful for smoke tests before a full run.",
    )
    run_p.add_argument(
        "--no-score", dest="skip_score", action="store_true",
        help="Skip the scorer step. Useful when you want to inspect raw responses before paying the judge dispatch cost.",
    )
    run_p.set_defaults(handler=handle_eval_run)

    show_p = subparsers.add_parser(
        "eval-show",
        help="Inspect the latest eval run result for a target provider (task #122)",
    )
    show_p.add_argument(
        "--target", default=None,
        help="Filter to runs against this provider. Defaults to the latest run regardless of target.",
    )
    show_p.add_argument(
        "--eval-id", default=None,
        help="Filter to a specific eval_id. Useful when comparing the same eval across multiple targets.",
    )
    show_p.add_argument(
        "--limit-samples", type=int, default=3,
        help="How many per-item samples to render (default 3). Set to 0 to skip.",
    )
    show_p.set_defaults(handler=handle_eval_show)

    share_p = subparsers.add_parser(
        "eval-share",
        help="Render an eval run result as a 1200×630 PNG you can tweet (task #122 follow-up)",
    )
    share_p.add_argument(
        "--target", default=None,
        help="Filter to runs against this provider. Defaults to the latest run regardless of target.",
    )
    share_p.add_argument(
        "--eval-id", default=None,
        help="Filter to a specific eval_id.",
    )
    share_p.add_argument(
        "--out", default=None,
        help="Output PNG path. Defaults to ~/.trinity/share/eval_card.png.",
    )
    share_p.add_argument(
        "--open", dest="open_after", action="store_true",
        help="Open the produced PNG with the OS default handler (Preview on macOS).",
    )
    share_p.set_defaults(handler=handle_eval_share)


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

    # Human-readable summary: stats first (the marketing-legible
    # artifact), then where it's written.
    stats = eval_set.stats
    print(f"  Built eval set {eval_set.eval_id}")
    print(f"  Source: {eval_set.source}")
    print(f"  Items: {stats.get('items', 0)}")
    by_type = stats.get("by_rejection_type") or {}
    if by_type:
        print("  By rejection_type:")
        for kind, count in by_type.items():
            print(f"    {kind:<12} {count}")
    by_basin = stats.get("by_basin") or {}
    if by_basin:
        print(f"  By basin (top {min(8, len(by_basin))}):")
        for basin, count in list(by_basin.items())[:8]:
            print(f"    {basin:<8} {count}")
    print(f"\n  → {path}")
    print("\n  Next: `trinity-local eval-run --target <provider>` to score a model against this set,"
          "\n        then `trinity-local eval-show` to inspect results.")


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
        print("\n  Rejection-type distribution:")
        total = sum(by_type.values())
        for kind, count in by_type.items():
            pct = (100.0 * count / total) if total else 0.0
            bar = "█" * int(round(pct / 4))  # 25 chars max bar
            print(f"    {kind:<12} {count:>3}  {pct:5.1f}%  {bar}")
    by_basin = stats.get("by_basin") or {}
    if by_basin:
        print("\n  Basin distribution (top 10):")
        for basin, count in list(by_basin.items())[:10]:
            print(f"    {basin:<8} {count}")

    # A few sample items so the user sees the eval shape, not just counts.
    sample = eval_set.items[:3]
    if sample:
        print("\n  Sample items:")
        for item in sample:
            preview = (item.prompt or "(no prompt text)")
            if len(preview) > 100:
                preview = preview[:100].rstrip() + "…"
            print(f"\n    [{item.rejection_type:<11}] {preview}")
            quote = item.rejected_response[:120].replace("\n", " ")
            print(f"       rejected: {quote}{'…' if len(item.rejected_response) > 120 else ''}")


def _default_judge_provider(target: str, configs: dict) -> str | None:
    """Pick a judge that isn't the model being scored. Prefers cloud
    chairman-grade providers (claude / codex / gemini) over local
    models — pre-launch real-run discovered MLX was being picked as
    judge by alphabetical default and returning empty stdout for the
    judge prompt, defaulting every score to 0.5. Bias-trap warning
    surfaced in the CLI output."""
    # Preferred chairman-grade providers, in priority order.
    preferred = ("claude", "codex", "gemini")
    for name in preferred:
        if name != target and name in configs and configs[name].enabled:
            return name
    # Fallback: any enabled non-target provider — but log a warning
    # via the calling CLI when this branch hits, since it likely
    # means an MLX/Ollama judge that may not produce structured output.
    for name in configs:
        if name != target and configs[name].enabled:
            return name
    return None


def handle_eval_run(args):
    from ..config import load_config
    from ..evals.builder import evals_dir, load_eval_set
    from ..evals.runner import run_eval, save_run_result
    from ..evals.scorer import score_run

    eval_id = args.eval_id
    if eval_id is None:
        candidates = sorted(evals_dir().glob("eval_*.json"),
                            key=lambda p: p.stat().st_mtime, reverse=True)
        if not candidates:
            print("  No eval sets on disk. Run `trinity-local eval-build` first.")
            raise SystemExit(2)
        eval_id = candidates[0].stem

    eval_set = load_eval_set(eval_id)
    if eval_set is None:
        print(f"✗ eval set {eval_id} not found")
        raise SystemExit(2)

    config = load_config(getattr(args, "config", None), required=True)
    provider_configs = {name: p for name, p in config.providers.items() if p.enabled}
    if args.target not in provider_configs:
        print(f"✗ target provider {args.target!r} not enabled. Available: {sorted(provider_configs)}")
        raise SystemExit(2)

    def _progress(idx, total, item_run):
        pad_axis = item_run.rejection_type.ljust(11)
        status = "✗" if item_run.target_error else "→"
        print(f"  [{idx}/{total}] {status} {pad_axis} {item_run.elapsed_seconds:5.1f}s")

    print(f"Running eval {eval_id} against {args.target}...")
    run_result = run_eval(
        eval_set,
        args.target,
        provider_configs,
        limit=args.limit,
        progress_callback=_progress,
    )

    if not args.skip_score:
        judge = args.judge or _default_judge_provider(args.target, provider_configs)
        if judge is None:
            print("✗ no judge provider available (need a second enabled provider, or pass --judge).")
            raise SystemExit(2)
        if judge == args.target:
            print(f"⚠  judge ({judge}) is the same as target ({args.target}) — bias-trap warning.")
        from ..state_paths import lens_path
        lens_md = lens_path()
        lens_text = lens_md.read_text(encoding="utf-8") if lens_md.exists() else ""
        print(f"Scoring with judge={judge}...")
        score_run(run_result, lens_text, judge, provider_configs,
                  progress_callback=lambda i, t, _: print(f"  judged {i}/{t}"))

    path = save_run_result(run_result)

    print()
    print(f"  Eval run complete: {run_result.items_completed}/{run_result.items_total} dispatched, "
          f"{run_result.items_failed} failed")
    if run_result.aggregate_score is not None:
        print(f"  Aggregate score:  {run_result.aggregate_score:.3f}  ({args.target} vs rejected_responses)")
        if run_result.by_rejection_type:
            print("  By rejection axis:")
            for axis, stats in sorted(run_result.by_rejection_type.items()):
                print(f"    {axis:<12} n={stats['count']:>3}  mean={stats['mean_score']:.3f}  "
                      f"(min {stats['min_score']:.2f} max {stats['max_score']:.2f})")
    print(f"\n  → {path}")


def _latest_result_path(target: str | None, eval_id: str | None):
    """Find the most-recent result file under ~/.trinity/evals/results/,
    optionally filtered by target and/or eval_id. Returns None if none.

    Filename shape (from runner.result_path()):
      eval_<eval_id>__model_<target>__<ts>.json
    """
    from ..evals.builder import results_dir

    candidates = list(results_dir().glob("eval_*__model_*.json"))
    if not candidates:
        return None
    if target:
        candidates = [p for p in candidates if f"__model_{target}__" in p.name]
    if eval_id:
        candidates = [p for p in candidates if p.name.startswith(f"eval_{eval_id}__")]
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def handle_eval_show(args):
    from ..evals.runner import load_run_result

    path = _latest_result_path(args.target, args.eval_id)
    if path is None:
        msg = "No eval results found on disk."
        if args.target or args.eval_id:
            msg += " Filters: "
            if args.target:
                msg += f"target={args.target!r} "
            if args.eval_id:
                msg += f"eval_id={args.eval_id!r}"
            msg += " — try without filters or run `trinity-local eval-run --target <provider>` first."
        else:
            msg += " Run `trinity-local eval-run --target <provider>` to produce one."
        print(f"  {msg}")
        raise SystemExit(1)

    result = load_run_result(path)
    if result is None:
        print(f"✗ result at {path} unreadable")
        raise SystemExit(2)

    # Header: which eval, which model, when
    print(f"  {result.eval_id}  →  {result.target_provider}"
          f"{f' ({result.target_model})' if result.target_model else ''}")
    print(f"  ran {result.started_at} → {result.completed_at}")
    print(f"  {result.items_completed}/{result.items_total} dispatched"
          f"{f', {result.items_failed} failed' if result.items_failed else ''}")

    if result.aggregate_score is not None:
        print()
        print(f"  Aggregate score: {result.aggregate_score:.3f}  "
              f"(vs the rejected_responses the original prompts elicited)")
        if result.by_rejection_type:
            print("\n  By rejection axis:")
            for axis, stats in sorted(result.by_rejection_type.items()):
                # Visual bar — 25-char max width, scaled by mean_score
                width = int(round(stats["mean_score"] * 25))
                bar = "█" * width + "·" * (25 - width)
                print(f"    {axis:<12} n={stats['count']:>3}  "
                      f"mean={stats['mean_score']:.3f}  [{bar}]  "
                      f"min {stats['min_score']:.2f} max {stats['max_score']:.2f}")
    else:
        print("\n  (No aggregate score — run completed without --no-score, or scoring failed.)")

    if args.limit_samples > 0 and result.items:
        # Show a few items with the strongest signal: extremes are
        # informative — the top + bottom score tell the user where the
        # model wins and where it loses on their corpus.
        scored = [it for it in result.items if it.score is not None]
        if scored:
            scored.sort(key=lambda it: it.score or 0.0, reverse=True)
            best = scored[:args.limit_samples]
            worst = scored[-args.limit_samples:] if len(scored) > args.limit_samples else []
            print(f"\n  Top {len(best)} scored items:")
            for it in best:
                _print_sample_line(it)
            if worst:
                print(f"\n  Bottom {len(worst)} scored items:")
                for it in worst:
                    _print_sample_line(it)
        else:
            print("\n  (No scored items to sample.)")

    print(f"\n  → {path}")


def _print_sample_line(item):
    """Render a single scored item compactly. Used by eval-show sample list."""
    score = f"{item.score:.2f}" if item.score is not None else "—  "
    prompt_preview = (item.prompt or "")[:70].replace("\n", " ")
    if len(item.prompt or "") > 70:
        prompt_preview += "…"
    print(f"    [{item.rejection_type:<11}] {score}  {prompt_preview}")


def handle_eval_share(args):
    """Render the latest (or filtered) eval run result as a 1200×630
    PNG share card. The artifact the user's pitch produces — "I ran my
    evals on Gemini, here's where it landed."

    Defaults to ~/.trinity/share/eval_card.png to match the me-card
    convention. Prints a small JSON summary to stdout for scriptability.
    """
    from pathlib import Path
    from ..evals.runner import load_run_result
    from ..eval_card import collect_card_data_from_result, render_eval_card
    from ..state_paths import state_dir

    path = _latest_result_path(args.target, args.eval_id)
    if path is None:
        msg = "No eval results found on disk."
        if args.target or args.eval_id:
            msg += " Try without --target/--eval-id, or run `trinity-local eval-run --target <provider>` first."
        else:
            msg += " Run `trinity-local eval-run --target <provider>` to produce one."
        print(f"  {msg}")
        raise SystemExit(1)

    result = load_run_result(path)
    if result is None:
        print(f"✗ result at {path} unreadable")
        raise SystemExit(2)

    card_data = collect_card_data_from_result(result)
    png_bytes = render_eval_card(card_data)

    out = Path(args.out) if args.out else (state_dir() / "share" / "eval_card.png")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(png_bytes)

    opened = False
    if args.open_after:
        try:
            # macOS `open`, Linux `xdg-open`. Best-effort; print errors but
            # don't fail the command — the file is written either way.
            import subprocess
            import sys
            if sys.platform == "darwin":
                subprocess.run(["open", str(out)], check=False)
                opened = True
            elif sys.platform.startswith("linux"):
                subprocess.run(["xdg-open", str(out)], check=False)
                opened = True
        except OSError:
            opened = False

    summary = {
        "ok": True,
        "path": str(out),
        "bytes": len(png_bytes),
        "target_provider": card_data.target_provider,
        "target_model": card_data.target_model,
        "aggregate_score": card_data.aggregate_score,
        "items_completed": card_data.items_completed,
        "axes": [a for a, _, _ in card_data.by_axis],
        "opened": opened,
    }
    print(json.dumps(summary, indent=2))
