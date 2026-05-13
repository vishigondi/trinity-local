"""/me — build the user's persona document via a single chairman call
over sampled prompt history. The chairman of every Trinity council reads it
to score council outputs against THIS user's taste, not the world's."""
from __future__ import annotations

import json

from ..me_builder import (
    ME_BUDGET_CHARS,
    ME_SAMPLE_SIZE,
    build_me_via_council,
    build_me_via_lens_pipeline,
    load_me,
    me_path,
)


def register(subparsers):
    build_parser = subparsers.add_parser(
        "lens-build",
        help="Build ~/.trinity/memories/lens.md via the 3-stage lens-discovery pipeline.",
    )
    build_parser.add_argument(
        "--budget-chars", type=int, default=ME_BUDGET_CHARS,
        help=f"Soft cap on lens.md size when using --legacy (default {ME_BUDGET_CHARS}).",
    )
    build_parser.add_argument(
        "--sample-size", type=int, default=ME_SAMPLE_SIZE,
        help=f"How many representative prompts to feed the chairman (default {ME_SAMPLE_SIZE}).",
    )
    build_parser.add_argument(
        "--k-basins", type=int, default=20,
        help="Stage 1 k-means cluster count (default 20).",
    )
    build_parser.add_argument(
        "--dry-run", action="store_true",
        help="Stage 1 only — cluster topics and print their summary, no LLM calls.",
    )
    build_parser.add_argument(
        "--legacy", action="store_true",
        help="Use the old single-pass chairman builder (pre-Option C).",
    )
    build_parser.set_defaults(handler=handle_me_build)

    show_parser = subparsers.add_parser(
        "lens-show",
        help="Print the current ~/.trinity/memories/lens.md content.",
    )
    show_parser.set_defaults(handler=handle_me_show)


def handle_me_build(args):
    if args.legacy:
        path, summary = build_me_via_council(
            budget_chars=args.budget_chars,
            sample_size=args.sample_size,
        )
    else:
        path, summary = build_me_via_lens_pipeline(
            sample_size=args.sample_size,
            k_basins=args.k_basins,
            dry_run=args.dry_run,
        )
    # Lens was just rewritten → freeze the routing table to disk +
    # auto-fire distill. Both are no-ops if the data hasn't changed
    # (routing is empty without rated councils; distill skips if
    # core.md is already newer than every source memory). Skipped
    # in dry-run since no real changes hit disk.
    routing_summary: dict | None = None
    distill_summary: dict | None = None
    if not getattr(args, "dry_run", False):
        try:
            from ..personal_routing import freeze_routing_to_disk
            table = freeze_routing_to_disk()
            routing_summary = {"task_types": len((table or {}).get("by_task_type") or {})}
        except Exception as exc:
            routing_summary = {"error": f"{type(exc).__name__}: {exc}"}
        try:
            from ..distill import distill_via_chairman
            distill_summary = distill_via_chairman()
        except Exception as exc:
            distill_summary = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    payload = {"ok": True, "path": str(path), **summary}
    if routing_summary is not None:
        payload["routing_frozen"] = routing_summary
    if distill_summary is not None:
        payload["distill"] = distill_summary
    print(json.dumps(payload, indent=2))


def handle_me_show(args):
    text = load_me()
    if not text:
        print("# lens not built yet — run `trinity-local lens-build`")
        print(f"# expected at: {me_path()}")
        return
    print(text)
