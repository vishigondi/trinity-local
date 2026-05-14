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
    results_dir = evals_dir / "results"
    if results_dir.exists():
        candidates = sorted(
            results_dir.glob("eval_*__model_*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        if candidates:
            try:
                data = json.loads(candidates[0].read_text(encoding="utf-8"))
                latest_eval = {
                    "target": data.get("target_provider"),
                    "model": data.get("target_model"),
                    "aggregate_score": data.get("aggregate_score"),
                    "items_completed": data.get("items_completed"),
                }
            except (OSError, json.JSONDecodeError):
                latest_eval = None

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
        },
        "trinity_home": str(home),
    }

    if args.as_json:
        print(json.dumps(report, indent=2))
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
