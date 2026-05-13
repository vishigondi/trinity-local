"""Handler for `unrated` — list councils without a user verdict.

Closes Pillar 4 (verdict-capture funnel widening) from the forward arc
in claude.md. Ticks #69-74 made the rate-capture failure VISIBLE
across surfaces; this command makes the backlog ACTIONABLE — the user
runs it, sees their unrated councils with prompt previews + chairman
picks, and rates them via the existing `council-rate` flow.

The 16%-rate problem isn't a UX-flaw-per-click; it's that the user
doesn't realize how many councils they haven't rated. A one-shot CLI
view of the backlog turns "I should rate more" into "I have 16
pending — let me knock out the top 5 right now."

No new state — walks `~/.trinity/council_outcomes/*.json` on every
call (same shape as `_verdict_stats()` in launchpad_data.py from
tick #70). Output format mirrors `council-rate` so the user can
copy-paste the next command directly.
"""
from __future__ import annotations

import json
from pathlib import Path

from ..state_paths import council_outcomes_dir, prompt_bundles_dir


def register(subparsers):
    parser = subparsers.add_parser(
        "unrated",
        help="List councils without a user verdict (Pillar 4 funnel widening — task #110 follow-up)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=10,
        help="Number of councils to show (default 10, sorted newest first)",
    )
    parser.add_argument(
        "--json",
        dest="as_json",
        action="store_true",
        help="Emit JSON for harness use",
    )
    parser.set_defaults(handler=handle_unrated)


def handle_unrated(args):
    outcomes = council_outcomes_dir()
    bundles = prompt_bundles_dir()
    if not outcomes.is_dir():
        if args.as_json:
            print(json.dumps({"total": 0, "unrated": 0, "rows": []}, indent=2))
        else:
            print("  No council outcomes yet — run a council first.")
        return 0

    rows: list[dict] = []
    total = 0
    rated = 0
    for path in outcomes.glob("council_*.json"):
        try:
            outcome = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        total += 1
        metadata = outcome.get("metadata") or {}
        verdict = metadata.get("user_verdict") or {}
        if isinstance(verdict, dict) and verdict.get("user_winner"):
            rated += 1
            continue
        # Unrated council. Pull prompt text from the bundle when possible,
        # fall back to metadata.task_text. Chairman's pick from
        # routing_label.winner.
        bundle_id = outcome.get("bundle_id") or metadata.get("bundle_id")
        prompt_text = metadata.get("task_text") or ""
        if bundle_id:
            bp = bundles / f"{bundle_id}.json"
            if bp.is_file():
                try:
                    bundle = json.loads(bp.read_text(encoding="utf-8"))
                    prompt_text = bundle.get("task_text") or prompt_text
                except (OSError, json.JSONDecodeError):
                    pass
        prompt_text = (prompt_text or "").strip().replace("\n", " ")
        if len(prompt_text) > 100:
            prompt_text = prompt_text[:100].rstrip() + "…"
        routing_label = outcome.get("routing_label") or {}
        chairman_pick = (
            routing_label.get("winner")
            or outcome.get("primary_provider")
            or outcome.get("winner_provider")
            or ""
        )
        rows.append({
            "council_id": outcome.get("council_run_id") or path.stem,
            "created_at": outcome.get("created_at") or "",
            "prompt": prompt_text or "(no prompt text)",
            "chairman_pick": chairman_pick,
        })

    # Newest first — the user rates recent thinking before old stuff.
    rows.sort(key=lambda r: r["created_at"], reverse=True)
    if args.limit > 0:
        rows = rows[: args.limit]

    if args.as_json:
        print(json.dumps({
            "total": total,
            "rated": rated,
            "unrated_count": total - rated,
            "rows": rows,
        }, indent=2))
        return 0

    unrated_count = total - rated
    if total == 0:
        print("  No council outcomes yet — run a council first.")
        return 0
    if unrated_count == 0:
        print(f"  All {total} councils rated. The moat is full.")
        return 0
    print(f"  {unrated_count} of {total} councils unrated. Showing {len(rows)} (newest first):")
    print()
    for r in rows:
        # Compact format: council_id (short) · chairman pick · prompt preview
        cid_short = r["council_id"][:24]
        pick = r["chairman_pick"] or "—"
        when = (r["created_at"] or "")[:10]
        print(f"  {cid_short}  {when}  chairman={pick:<8}  {r['prompt']}")
    print()
    print("  Rate a council:")
    print("    trinity-local council-rate --council <id> --provider <name>")
    print()
    print("  Every rating feeds the personal_routing_table + cortex picks.")
    print("  Trinity's moat is this ledger — see claude.md Pillar 4 / task #110.")
    return 0
