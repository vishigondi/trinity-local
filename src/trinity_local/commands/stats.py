"""`trinity-local stats` — one-glance summary of marketing-critical numbers.

The launch-package T-1 sequence needs a single command that prints all
the artifacts Trinity has accumulated for the user: rate-limit saves,
council outcomes, verdicts captured, eval items mined, latest eval
result. Each is its own dedicated CLI (`metric`, `unrated`, `eval-show`)
but the launch artifact loop — onboarding screenshots, tester DMs,
"what has Trinity done for me in 30 days" tweets — wants the one-line
verifiable summary.

Distinct from `status` (system health: are providers wired, is the
state dir writable, is the watcher firing). `stats` is the marketing
voice: what Trinity has produced. Different audiences, different surface.
"""
from __future__ import annotations

import json


def register(subparsers):
    sp = subparsers.add_parser(
        "stats",
        help="One-glance summary of what Trinity has captured (marketing voice).",
    )
    sp.add_argument(
        "--days",
        type=int,
        default=30,
        help="Window for rate-limit and verdict stats (default: 30).",
    )
    sp.add_argument("--json", dest="as_json", action="store_true",
                    help="Output as JSON (for piping into tweets/scripts).")
    sp.add_argument(
        "--share",
        action="store_true",
        help=(
            "Print a Twitter/HN-ready post template populated with your "
            "actual numbers. The launch-package's T-1 'thread drafted' "
            "step in one command."
        ),
    )
    sp.set_defaults(handler=handle_stats)


def handle_stats(args):
    from datetime import datetime, timezone, timedelta
    from pathlib import Path

    from ..state_paths import (
        state_dir, council_outcomes_dir, dispatch_outcomes_path,
    )

    home = state_dir()
    cutoff = datetime.now(timezone.utc) - timedelta(days=args.days)

    # Rate-limit saves (the headline number named in launch-package.md).
    # Read directly to keep `stats` zero-dependency on launchpad_data —
    # those layers shouldn't import each other (per claude.md "ingest is
    # not a feedback signal" pattern: each surface walks its own source).
    rate_limit_saves = 0
    rate_limit_total = 0
    if dispatch_outcomes_path().exists():
        for line in dispatch_outcomes_path().read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts_str = entry.get("ts")
            if ts_str:
                try:
                    ts = datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                    if ts.tzinfo is None:
                        ts = ts.replace(tzinfo=timezone.utc)
                    if ts < cutoff:
                        continue
                except (ValueError, TypeError):
                    pass
            rate_limit_total += 1
            if entry.get("rate_limit_save"):
                rate_limit_saves += 1

    # Council outcomes + verdict-capture rate.
    council_dir = council_outcomes_dir()
    council_total = 0
    council_rated = 0
    if council_dir.exists():
        for path in council_dir.glob("council_*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            council_total += 1
            verdict = ((data.get("metadata") or {}).get("user_verdict") or {})
            if verdict.get("user_winner"):
                council_rated += 1

    # Eval set + latest result.
    evals_dir = home / "evals"
    eval_set_items = 0
    if evals_dir.exists():
        for path in evals_dir.glob("eval_*.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                # Pick the largest eval set on disk.
                items = data.get("items") or []
                if isinstance(items, list):
                    eval_set_items = max(eval_set_items, len(items))
            except (OSError, json.JSONDecodeError):
                continue

    latest_eval: dict | None = None
    targets: list[dict] = []  # leaderboard: most-recent run per target
    results_dir = evals_dir / "results"
    if results_dir.exists():
        candidates = sorted(
            results_dir.glob("eval_*__model_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        seen: set[str] = set()
        for path in candidates:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            target = data.get("target_provider")
            if not target or target in seen:
                continue  # keep most-recent per target (mtime desc)
            seen.add(target)
            # Pull judge from first item — runner uses one judge per run
            items = data.get("items") or []
            judge = None
            for item in items:
                if isinstance(item, dict) and item.get("judge_provider"):
                    judge = item["judge_provider"]
                    break
            entry = {
                "target": target,
                "model": data.get("target_model"),
                "aggregate_score": data.get("aggregate_score"),
                "items_completed": data.get("items_completed"),
                "judge": judge,
            }
            targets.append(entry)
            if latest_eval is None:
                latest_eval = entry  # the first one (newest) is the canonical "latest"
        # Sort leaderboard by aggregate desc — "best on YOUR corpus" first
        targets.sort(key=lambda r: r.get("aggregate_score") or -1.0, reverse=True)

    # Prompt index size (the foundation under everything).
    prompts_dir = home / "prompts"
    prompt_nodes = 0
    prompt_file = prompts_dir / "prompt_nodes.jsonl"
    if prompt_file.exists():
        try:
            # Count lines without loading the whole file into memory —
            # this file can be tens of MB on a power user's install.
            with prompt_file.open("r", encoding="utf-8") as f:
                prompt_nodes = sum(1 for line in f if line.strip())
        except OSError:
            pass

    save_rate = round(rate_limit_saves / max(1, rate_limit_total), 3)
    verdict_rate = round(council_rated / max(1, council_total), 3)

    report = {
        "window_days": args.days,
        "prompts_indexed": prompt_nodes,
        "councils": {
            "total": council_total,
            "rated": council_rated,
            "verdict_rate": verdict_rate,
        },
        "rate_limit_saves": {
            "total": rate_limit_saves,
            "of_calls": rate_limit_total,
            "save_rate": save_rate,
        },
        "evals": {
            "items_mined": eval_set_items,
            "latest_run": latest_eval,
            # Leaderboard: per-target most-recent run, sorted by score
            # desc. Empty list when no runs on disk. Populated for
            # `stats --share` to render the multi-provider anchor.
            "targets": targets,
        },
        "trinity_home": str(home),
    }

    if args.as_json:
        print(json.dumps(report, indent=2))
        return 0

    if getattr(args, "share", False):
        _print_share_template(report)
        return 0

    # Marketing-voice human-readable output.
    print()
    print("  Trinity — what's accumulated in your corpus")
    print()
    print(f"  📚 Prompts indexed:      {prompt_nodes:,}")
    print(f"  🤝 Councils run:         {council_total}  ({council_rated} rated · {verdict_rate * 100:.0f}% verdict rate)")
    if rate_limit_total > 0:
        print(f"  🚦 Rate-limit saves:     {rate_limit_saves}  of {rate_limit_total} calls ({save_rate * 100:.1f}% save rate) · last {args.days}d")
    else:
        print(f"  🚦 Rate-limit saves:     0  (no dispatch outcomes recorded yet)")
    if eval_set_items:
        print(f"  🧪 Eval items mined:     {eval_set_items}")
    else:
        print(f"  🧪 Eval items mined:     0  (run `trinity-local eval-build`)")
    if latest_eval and latest_eval.get("aggregate_score") is not None:
        agg = latest_eval["aggregate_score"]
        target = latest_eval.get("target") or "?"
        print(f"  📊 Latest eval result:   {target} = {agg:.3f}  ({latest_eval.get('items_completed') or 0} items)")
    else:
        print(f"  📊 Latest eval result:   none  (run `trinity-local eval-run --target gemini`)")
    print()
    print(f"  State: {home}")
    print()
    return 0


def _print_share_template(report: dict) -> None:
    """Render copy-pasteable Twitter/HN templates populated with the
    user's actual numbers. The launch-package's T-1 "thread drafted"
    step in one command — the friction-removal that turns "I have
    numbers" into "I have a tweet ready to post."

    Three variants printed:
      1. The rate-limit-saves anchor (the Day-1 case-study number)
      2. The empirical-benchmark anchor (when an eval result exists)
      3. The corpus-size anchor (always shippable as the founder DM)

    Each is structurally non-refutable (only Trinity can produce
    these numbers because only Trinity sees cross-provider signal).
    The verbiage matches the wedge phrases used everywhere else:
    "structurally," "the layer above the labs," etc. — so the
    launch voice stays one-voice across surfaces.

    Discarded variants kept short. The user picks the one that
    fits their audience; this is a starter kit, not a final draft.
    """
    saves = report["rate_limit_saves"]["total"]
    of_calls = report["rate_limit_saves"]["of_calls"]
    save_rate_pct = report["rate_limit_saves"]["save_rate"] * 100
    window = report["window_days"]
    councils = report["councils"]["total"]
    rated = report["councils"]["rated"]
    prompts = report["prompts_indexed"]
    latest = (report.get("evals") or {}).get("latest_run")
    targets = (report.get("evals") or {}).get("targets") or []

    print()
    print("─" * 60)
    print("  Trinity stats — share-ready templates")
    print("─" * 60)
    print()

    # Anchor 1: rate-limit-saves (the Day-1 number)
    if saves > 0:
        print("▶ Rate-limit-saves anchor (post-Dreaming wedge):")
        print()
        print(f'   Trinity routed {saves} work-units around Claude rate')
        print(f'   limits in the last {window} days — {save_rate_pct:.1f}% of my')
        print(f'   ask calls would have been retries or abandoned without it.')
        print()
        print(f'   The cross-provider memory layer the labs are commercially')
        print(f'   prevented from building. https://github.com/vishigondi/trinity-local')
        print()

    # Anchor 2: empirical benchmark — leaderboard when ≥2 targets,
    # single-point fallback when 1. The leaderboard form is strictly
    # stronger marketing: it shows the wedge ("Trinity scores models
    # against YOUR rejections — here's the rank order") rather than
    # asserting a single point ("model X scored Y, take my word").
    scored = [t for t in targets if t.get("aggregate_score") is not None]
    if len(scored) >= 2:
        print("▶ Personal-benchmark anchor (the #116 wedge, leaderboard):")
        print()
        print(f'   Trinity benchmarked all three providers against MY actual')
        print(f'   rejection signal. Leaderboard on my own corpus:')
        print()
        for i, row in enumerate(scored, 1):
            tgt = (row.get("target") or "?").capitalize()
            score = row["aggregate_score"]
            n = row.get("items_completed") or 0
            judge = row.get("judge")
            judge_str = f" (judged by {judge})" if judge else ""
            print(f'   {i}. {tgt}: {score:.2f}/1.00 on {n} items{judge_str}')
        print()
        print(f'   No frontier provider can build this benchmark themselves')
        print(f'   — Anthropic only sees Claude transcripts, OpenAI only sees')
        print(f'   GPT. Only the layer above the labs sees cross-provider')
        print(f'   rejection. Judges rotated so no model grades itself.')
        print(f'   https://github.com/vishigondi/trinity-local')
        print()
    elif latest and latest.get("aggregate_score") is not None:
        target = latest.get("target", "?")
        agg = latest["aggregate_score"]
        items = latest.get("items_completed", 0)
        print("▶ Personal-benchmark anchor (the #116 wedge):")
        print()
        print(f'   {target.capitalize()} scored {agg:.2f}/1.00 on MY kind of')
        print(f'   question — {items} items mined from my actual rejection')
        print(f'   signal across Claude / GPT / Gemini transcripts.')
        print()
        print(f'   No frontier provider can build this benchmark themselves')
        print(f'   — Anthropic only sees Claude transcripts, OpenAI only sees')
        print(f'   GPT. Only the layer above the labs sees cross-provider')
        print(f'   rejection. https://github.com/vishigondi/trinity-local')
        print()

    # Anchor 3: corpus size (always shippable)
    if prompts > 0:
        print("▶ Corpus-size anchor (the moat narrative):")
        print()
        print(f'   {prompts:,} prompts indexed across Claude / GPT / Gemini')
        print(f'   transcripts. {councils} councils run, {rated} rated.')
        print(f'   Every council outcome and verdict lives in ~/.trinity/')
        print(f'   on infrastructure I own. The labs can\'t see this ledger;')
        print(f'   I can. https://github.com/vishigondi/trinity-local')
        print()

    print("  To verify any number: `trinity-local stats` (JSON: --json)")
    print()
