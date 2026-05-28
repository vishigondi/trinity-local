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
        help="Provider to benchmark (claude / codex / antigravity / ...).",
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
    show_p.add_argument(
        "--compare",
        action="store_true",
        help=(
            "Cross-provider leaderboard view: list every target_provider "
            "that has been scored against this eval set, sorted by "
            "aggregate score desc. Mirrors the launchpad's leaderboard."
        ),
    )
    show_p.add_argument(
        "--by-axis",
        action="store_true",
        help=(
            "With --compare: render the axis × provider matrix instead "
            "of the aggregate-only table. Surfaces per-rejection-type "
            "leadership splits (e.g. claude wins REFRAME, codex wins "
            "COMPRESSION) that the aggregate flattens. Requires --compare."
        ),
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
    share_p.add_argument(
        "--compare",
        action="store_true",
        help=(
            "Render the cross-provider leaderboard card instead of the "
            "single-provider per-axis card. Pair with --eval-id when "
            "providers were run against multiple eval sets."
        ),
    )
    share_p.add_argument(
        "--by-axis",
        action="store_true",
        help=(
            "With --compare: render the axis × provider matrix card "
            "(per-axis bars per provider + per-axis leader callout) "
            "instead of the aggregate-only leaderboard card. The wedge "
            "artifact for 'X is best at this kind of question'."
        ),
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

    # Re-score nudge: if this isn't the first eval set the user has
    # built, name the providers already scored against PRIOR sets and
    # surface ready-to-paste eval-run commands against the NEW one.
    # Without this, the user has to remember to re-score after every
    # rebuild, and the leaderboard silently drifts out of sync.
    prior_targets = _targets_with_results(exclude_eval_id=eval_set.eval_id)
    if prior_targets:
        print()
        print(
            f"  Note: {len(prior_targets)} provider(s) already scored against prior "
            f"eval sets ({', '.join(sorted(prior_targets))}). Re-run against this "
            f"new set so the leaderboard reflects the fresh signals:"
        )
        for target in sorted(prior_targets):
            print(f"    trinity-local eval-run --target {target} --eval-id {eval_set.eval_id}")
    else:
        print("\n  Next: `trinity-local eval-run --target <provider>` to score a model against this set,"
              "\n        then `trinity-local eval-show` to inspect results.")


def _targets_with_results(exclude_eval_id: str | None = None) -> set[str]:
    """Return the set of target_provider names that have at least one
    eval result on disk against an eval set OTHER than `exclude_eval_id`.

    Used by handle_eval_build to nudge the user toward re-scoring after
    a rebuild. Filename convention from evals.runner.result_path:
      eval_<eval_id>__model_<target>__<ts>.json
    """
    import json

    from ..evals.builder import results_dir
    rd = results_dir()
    if not rd.exists():
        return set()
    targets: set[str] = set()
    for path in rd.glob("eval_*__model_*.json"):
        # Skip results against the same eval set we just rebuilt — the
        # nudge is about RE-scoring, not re-pointing at fresh data.
        if exclude_eval_id and f"eval_{exclude_eval_id}__" in path.name:
            continue
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        target = data.get("target_provider")
        if target:
            targets.add(target)
    return targets


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
    chairman-grade providers (claude / codex / antigravity) over local
    models — pre-launch real-run discovered MLX was being picked as
    judge by alphabetical default and returning empty stdout for the
    judge prompt, defaulting every score to 0.5. Bias-trap warning
    surfaced in the CLI output.

    (Slug `gemini` is intentionally omitted from the preferred list:
    the legacy Google CLI binary was retired as a Trinity dispatch
    target per task #127's 2026-05-21 Antigravity migration. Before
    iter #61's fix, this function listed `gemini` here, which never
    matched config.json's `antigravity` slug and silently fell
    through to the alphabetical fallback — picking MLX as judge in
    cases where Antigravity was available and preferred.)
    """
    # Preferred chairman-grade providers, in priority order.
    preferred = ("claude", "codex", "antigravity")
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

    # Accept user-facing names (gemini/gpt/chatgpt/…) for --target and
    # --judge — the most viral feature ("score the new model against my
    # taste") must not fail because the user typed the brand instead of the
    # internal slug (`antigravity`). Resolve to the slug; canonical slugs +
    # unknown names pass through unchanged.
    from ..council_schema import resolve_provider_alias
    args.target = resolve_provider_alias(args.target)
    if getattr(args, "judge", None):
        args.judge = resolve_provider_alias(args.judge)

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
            from ..evals.scorer import AXIS_ONELINER
            print("  By rejection axis (what the user wanted that the rejected response missed):")
            for axis, stats in sorted(run_result.by_rejection_type.items()):
                hint = AXIS_ONELINER.get(axis, "")
                print(f"    {axis:<12} n={stats['count']:>3}  mean={stats['mean_score']:.3f}  "
                      f"(min {stats['min_score']:.2f} max {stats['max_score']:.2f})"
                      + (f"  — {hint}" if hint else ""))
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


def _collect_leaderboard_rows(eval_id: str | None) -> tuple[list[dict], set[str]]:
    """Return (rows-sorted-desc, eval_ids_seen).

    Shared by eval-show --compare and eval-share --compare; same per-target
    dedup policy the launchpad uses (launchpad_data._compute_eval_summary).
    Returns ([], set()) when no candidates match.
    """
    import json
    from ..evals.builder import results_dir

    candidates = list(results_dir().glob("eval_*__model_*.json"))
    if eval_id:
        candidates = [p for p in candidates if p.name.startswith(f"eval_{eval_id}__")]
    if not candidates:
        return [], set()
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)

    by_target: dict[str, dict] = {}
    eval_ids_seen: set[str] = set()
    for path in candidates:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        target = data.get("target_provider")
        if not target or target in by_target:
            continue
        items = data.get("items") or []
        judge = None
        for item in items:
            if isinstance(item, dict) and item.get("judge_provider"):
                judge = item["judge_provider"]
                break
        eid = data.get("eval_id")
        if eid:
            eval_ids_seen.add(eid)
        # Per-axis means for the --by-axis matrix view. Keep as nested
        # dict so a caller doing aggregate-only work pays no parse cost.
        # by_axis_n stores per-axis sample counts so leader-suppression
        # can refuse to declare a winner on noise (n < MIN_AXIS_SAMPLES).
        by_axis = {}
        by_axis_n = {}
        for axis_name, stats in (data.get("by_rejection_type") or {}).items():
            if isinstance(stats, dict) and "mean_score" in stats:
                by_axis[axis_name] = float(stats["mean_score"])
                by_axis_n[axis_name] = int(stats.get("count", 0))
        by_target[target] = {
            "target": target,
            "model": data.get("target_model"),
            "aggregate_score": data.get("aggregate_score"),
            "items_completed": data.get("items_completed", 0),
            "judge": judge,
            "eval_id": eid,
            "ran_at": data.get("completed_at") or data.get("started_at"),
            "by_axis": by_axis,
            "by_axis_n": by_axis_n,
        }
    rows = sorted(
        by_target.values(),
        key=lambda r: r.get("aggregate_score") if r.get("aggregate_score") is not None else -1.0,
        reverse=True,
    )
    return rows, eval_ids_seen


def _handle_eval_compare(args):
    """Cross-provider leaderboard. CLI parity with the launchpad's
    evalSummary.comparison view: one row per target_provider, sorted by
    aggregate_score desc. When --eval-id is set, filter to that eval
    set so the columns are commensurate (different eval sets mean
    different items, so unfiltered comparison is suggestive only —
    surface a warning).
    """
    rows, eval_ids_seen = _collect_leaderboard_rows(args.eval_id)
    if not rows:
        msg = "  No eval results found on disk."
        if args.eval_id:
            msg += f" Filter: eval_id={args.eval_id!r}."
        msg += " Run `trinity-local eval-run --target <provider>` to produce one."
        print(msg)
        raise SystemExit(1)

    by_axis_mode = bool(getattr(args, "by_axis", False))

    print("  Cross-provider leaderboard · YOUR corpus" + ("  ·  per-axis matrix" if by_axis_mode else ""))
    if len(eval_ids_seen) > 1 and not args.eval_id:
        print(
            f"  ⚠ rows span {len(eval_ids_seen)} different eval sets — scores are NOT "
            "directly comparable. Pass --eval-id <id> to scope to one."
        )
    elif len(eval_ids_seen) == 1:
        print(f"  eval set: {next(iter(eval_ids_seen))}")
    print()

    if by_axis_mode:
        # Build the axes column list from union of all rows' axes, in a
        # stable order (alphabetical) so the header matches the data rows.
        axes_seen: set[str] = set()
        for row in rows:
            axes_seen.update((row.get("by_axis") or {}).keys())
        axes_ordered = sorted(axes_seen)
        if not axes_ordered:
            print("  (no per-axis breakdown available — runs predate by_rejection_type)")
            print("  Re-run with `trinity-local eval-run --target <provider>` to populate.")
            return None

        # Header
        axis_cols = "  ".join(f"{a[:11]:>11}" for a in axes_ordered)
        print(f"    {'target':<14} {'n':<5} {'agg':>6}  {axis_cols}")
        for row in rows:
            agg = row.get("aggregate_score")
            agg_str = f"{agg:.2f}" if agg is not None else "—"
            row_axes = row.get("by_axis") or {}
            axis_vals = "  ".join(
                f"{row_axes[a]:>11.3f}" if a in row_axes else f"{'—':>11}"
                for a in axes_ordered
            )
            print(
                f"    {row['target']:<14} {row['items_completed']:<5} {agg_str:>6}  {axis_vals}"
            )

        # Per-axis leader callouts — names the wedge claim ("X is best
        # for kind-of-question Y") in publishable form.
        #
        # SUPPRESSED in two cases:
        # 1. Mixed eval sets (commit 02f354d) — scores aren't comparable.
        # 2. Any contender on the axis has n < 3 — sample too small to
        #    declare a winner. Live trigger: COMPRESSION had n=2 per
        #    provider, mean spreads of 0.7 between providers, but n=2
        #    is noise. Better to surface no claim than a wrong one.
        # Matrix bars stay — per-provider scores are meaningful per se,
        # only the head-to-head SYNTHESIS gets suppressed.
        mixed = len(eval_ids_seen) > 1 and not args.eval_id
        MIN_AXIS_SAMPLES = 3
        if not mixed:
            print()
            leader_lines = []
            for axis in axes_ordered:
                scored = [
                    (r["target"], r["by_axis"][axis], (r.get("by_axis_n") or {}).get(axis, 0))
                    for r in rows
                    if axis in (r.get("by_axis") or {})
                ]
                if not scored:
                    continue
                # Sample-size guard
                if any(n < MIN_AXIS_SAMPLES for _, _, n in scored):
                    continue
                leader_target, leader_score, _ = max(scored, key=lambda kv: kv[1])
                leader_lines.append(f"{axis} → {leader_target} ({leader_score:.2f})")
            if leader_lines:
                print("  Per-axis leader:  " + "  |  ".join(leader_lines))
        return None

    print(f"    {'rank':<5} {'target':<14} {'n':<5} {'aggregate':>10}   {'judge':<14} {'ran'}")
    for i, row in enumerate(rows, 1):
        agg = row.get("aggregate_score")
        agg_str = f"{agg:.3f}" if agg is not None else "—"
        judge = row.get("judge") or "—"
        ran = (row.get("ran_at") or "")[:19]  # YYYY-MM-DDThh:mm:ss
        print(
            f"    {i:<5} {row['target']:<14} {row['items_completed']:<5} {agg_str:>10}"
            f"   {judge:<14} {ran}"
        )
    print()
    # Suppress the "X leads Y by ±Z" head-to-head when rows span
    # different eval sets — same consistency rule shipped to the
    # per-axis leader synthesis (commits 83b9e99, 02f354d). The
    # warning above the table already says scores aren't comparable;
    # a leader-margin line that subtracts them anyway contradicts it.
    mixed = len(eval_ids_seen) > 1 and not args.eval_id
    if not mixed and len(rows) >= 2:
        leader, runner_up = rows[0], rows[1]
        leader_agg = leader.get("aggregate_score")
        runner_agg = runner_up.get("aggregate_score")
        if leader_agg is not None and runner_agg is not None:
            print(
                f"  {leader['target']} leads {runner_up['target']} "
                f"by {leader_agg - runner_agg:+.3f} on YOUR rejection signal."
            )
    return None


def handle_eval_show(args):
    from ..evals.runner import load_run_result

    # --by-axis is meaningful only inside the leaderboard view (axis
    # × provider matrix). Without --compare it has no row dimension.
    if getattr(args, "by_axis", False) and not getattr(args, "compare", False):
        print(
            "  --by-axis only applies to the leaderboard view. Pass "
            "--compare --by-axis to render the axis × provider matrix.",
        )
        raise SystemExit(2)

    # --compare: flip to leaderboard view. Mirrors the launchpad's
    # cross-provider comparison (launchpad_data.py:_compute_eval_summary
    # builds the same shape). Different return path because --compare
    # aggregates across targets while the default view drills into one.
    if getattr(args, "compare", False):
        return _handle_eval_compare(args)

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
            from ..evals.scorer import AXIS_ONELINER
            print("\n  By rejection axis (what the user wanted that the rejected response missed):")
            for axis, stats in sorted(result.by_rejection_type.items()):
                # Visual bar — 25-char max width, scaled by mean_score
                width = int(round(stats["mean_score"] * 25))
                bar = "█" * width + "·" * (25 - width)
                hint = AXIS_ONELINER.get(axis, "")
                print(f"    {axis:<12} n={stats['count']:>3}  "
                      f"mean={stats['mean_score']:.3f}  [{bar}]  "
                      f"min {stats['min_score']:.2f} max {stats['max_score']:.2f}")
                if hint:
                    print(f"                 — {hint}")
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


def _open_if_requested(open_after: bool, path) -> bool:
    """Best-effort `open` for macOS / Linux. Never raises — the PNG is
    already on disk; opening the viewer is a convenience, not a contract."""
    if not open_after:
        return False
    try:
        import subprocess
        import sys
        if sys.platform == "darwin":
            subprocess.run(["open", str(path)], check=False)
            return True
        if sys.platform.startswith("linux"):
            subprocess.run(["xdg-open", str(path)], check=False)
            return True
    except OSError:
        return False
    return False


def handle_eval_share(args):
    """Render the latest (or filtered) eval run result as a 1200×630
    PNG share card. The artifact the user's pitch produces — "I ran my
    evals on Gemini, here's where it landed."

    Defaults to ~/.trinity/share/eval_card.png to match the me-card
    convention. Prints a small JSON summary to stdout for scriptability.
    """
    from pathlib import Path
    from ..evals.runner import load_run_result
    from ..eval_card import (
        CompareCardData,
        collect_card_data_from_result,
        render_compare_card,
        render_compare_matrix_card,
        render_eval_card,
    )
    from ..state_paths import share_dir

    # --by-axis without --compare doesn't make sense for the share card
    # either (no rows to break out by axis from a single-provider view).
    if getattr(args, "by_axis", False) and not getattr(args, "compare", False):
        print(
            "  --by-axis only applies to --compare. Pass --compare "
            "--by-axis to render the per-axis matrix PNG.",
        )
        raise SystemExit(2)

    # --compare: cross-provider leaderboard card. Different shape, same
    # canvas. The wedge artifact for #116 ("Trinity scored Claude,
    # Codex, and Gemini against my taste").
    if getattr(args, "compare", False):
        rows, eval_ids_seen = _collect_leaderboard_rows(args.eval_id)
        if not rows:
            msg = "  No eval results found on disk."
            if args.eval_id:
                msg += f" Filter: eval_id={args.eval_id!r}."
            msg += " Run `trinity-local eval-run --target <provider>` to produce one."
            print(msg)
            raise SystemExit(1)
        compare_data = CompareCardData(
            rows=rows,
            eval_id=args.eval_id if args.eval_id else (next(iter(eval_ids_seen)) if len(eval_ids_seen) == 1 else None),
            mixed_eval_sets=len(eval_ids_seen) > 1 and not args.eval_id,
        )
        by_axis_mode = bool(getattr(args, "by_axis", False))
        if by_axis_mode:
            png_bytes = render_compare_matrix_card(compare_data)
            default_filename = "eval_compare_matrix_card.png"
        else:
            png_bytes = render_compare_card(compare_data)
            default_filename = "eval_compare_card.png"
        out = Path(args.out) if args.out else (share_dir() / default_filename)
        out.write_bytes(png_bytes)
        opened = _open_if_requested(args.open_after, out)
        # Per-axis leader summary — useful in the JSON output for
        # scripted callers that want the wedge string.
        # Suppressed in two cases: mixed_eval_sets OR any contender on
        # the axis has n < MIN_AXIS_SAMPLES (sample too small to
        # declare a winner). Same rules as the launchpad + CLI surfaces.
        per_axis_leader: dict[str, dict] = {}
        MIN_AXIS_SAMPLES = 3
        if by_axis_mode and not compare_data.mixed_eval_sets:
            axes_seen: set[str] = set()
            for row in rows:
                axes_seen.update((row.get("by_axis") or {}).keys())
            for axis in sorted(axes_seen):
                scored = [
                    (r["target"], r["by_axis"][axis], (r.get("by_axis_n") or {}).get(axis, 0))
                    for r in rows
                    if axis in (r.get("by_axis") or {})
                ]
                if not scored or any(n < MIN_AXIS_SAMPLES for _, _, n in scored):
                    continue
                leader_target, leader_score, _ = max(scored, key=lambda kv: kv[1])
                per_axis_leader[axis] = {"target": leader_target, "score": leader_score}
        summary = {
            "ok": True,
            "mode": "compare-by-axis" if by_axis_mode else "compare",
            "path": str(out),
            "bytes": len(png_bytes),
            "eval_id": compare_data.eval_id,
            "mixed_eval_sets": compare_data.mixed_eval_sets,
            "rows": [
                {
                    "target": r["target"],
                    "aggregate_score": r["aggregate_score"],
                    "items_completed": r["items_completed"],
                    "judge": r["judge"],
                    **({"by_axis": r["by_axis"]} if by_axis_mode and r.get("by_axis") else {}),
                }
                for r in rows
            ],
            **({"per_axis_leader": per_axis_leader} if by_axis_mode else {}),
            "opened": opened,
        }
        print(json.dumps(summary, indent=2))
        return None

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

    out = Path(args.out) if args.out else (share_dir() / "eval_card.png")
    out.write_bytes(png_bytes)

    opened = _open_if_requested(args.open_after, out)

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
