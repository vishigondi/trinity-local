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
        "me-build",
        help="Build ~/.trinity/me.md via the 3-stage lens-discovery pipeline (Option C).",
    )
    build_parser.add_argument(
        "--budget-chars",
        type=int,
        default=ME_BUDGET_CHARS,
        help=f"Soft cap on /me size when using --legacy (default {ME_BUDGET_CHARS}).",
    )
    build_parser.add_argument(
        "--sample-size",
        type=int,
        default=ME_SAMPLE_SIZE,
        help=f"How many representative prompts to feed the chairman (default {ME_SAMPLE_SIZE}).",
    )
    build_parser.add_argument(
        "--k-basins",
        type=int,
        default=20,
        help="Stage 1 k-means cluster count (default 20).",
    )
    build_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Stage 1 only — cluster basins and print their summary, no LLM calls.",
    )
    build_parser.add_argument(
        "--legacy",
        action="store_true",
        help="Use the old single-pass chairman builder (pre-Option C).",
    )
    build_parser.set_defaults(handler=handle_me_build)

    show_parser = subparsers.add_parser(
        "me-show",
        help="Print the current ~/.trinity/me.md content.",
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
    print(json.dumps({
        "ok": True,
        "path": str(path),
        **summary,
    }, indent=2))


def handle_me_show(args):
    text = load_me()
    if not text:
        print(f"# /me not built yet — run `trinity-local me-build`")
        print(f"# expected at: {me_path()}")
        return
    print(text)
