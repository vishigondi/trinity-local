"""`lens-build` + `lens-show` — build / inspect the user's lens via a single
chairman call over sampled prompt history. The chairman of every Trinity
council reads `~/.trinity/memories/lens.md` to score council outputs
against THIS user's taste, not the world's.

Tier 1 #2 rename history (task #91): the CLI + MCP + file paths renamed
me/persona → lens pre-launch. Internal symbols (`me_builder`, `me_path`,
`build_me_via_council`, `ME_BUDGET_CHARS`) kept their me_ prefix per the
"code uses internal names; user-facing copy uses canonical name"
convention (same shape as glossary entry for member vs seat). The LLM
prompt that builds the lens (in `me_builder._render_me_build_prompt`)
still instructs the chairman to produce a `/me document` with `# /me`
heading — this gets rendered in the launchpad memory viewer; the
prompt-template rewrite to use "lens" framing is a deferred content-shape
change."""
from __future__ import annotations

import json

from ..me_builder import (
    ME_BUDGET_CHARS,
    ME_SAMPLE_SIZE,
    build_me_via_council,
    build_me_via_lens_pipeline,
    load_me,
    me_path,
    resync_lens_from_disk,
)


def register(subparsers):
    # Q4 surface-collapse (#213): `lens` is the user-facing product word.
    # `lens-build` is kept as an alias so launchpad/extension dispatch and
    # the copy-paste command strings in memory_viewer keep resolving.
    build_parser = subparsers.add_parser(
        "lens",
        aliases=["lens-build"],
        help="Build your lens (~/.trinity/memories/lens.md) from your transcripts.",
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
        "--k-basins", type=int, default=None,
        help="Stage 1 k-means cluster count. Default: corpus-size-aware "
             "(≈1 basin per 650 threads, 20–60) so the topic map doesn't "
             "junk-drawer as history grows (#245). Pass an int to force k.",
    )
    build_parser.add_argument(
        "--dry-run", action="store_true",
        help="Stage 1 only — cluster topics and print their summary, no LLM calls.",
    )
    build_parser.add_argument(
        "--legacy", action="store_true",
        help="Use the old single-pass chairman builder (pre-Option C).",
    )
    build_parser.add_argument(
        "--force", action="store_true",
        help="Rebuild even if the corpus is unchanged since the last build "
             "(skips the no-corpus-change shortcut).",
    )
    build_parser.set_defaults(handler=handle_me_build)

    show_parser = subparsers.add_parser(
        "lens-show",
        help="Print the current ~/.trinity/memories/lens.md content.",
    )
    show_parser.set_defaults(handler=handle_me_show)

    resync_parser = subparsers.add_parser(
        "lens-resync",
        help="Seed the tension registry from existing lenses.json + re-render "
             "lens.md with support/stability — no chairman calls.",
    )
    resync_parser.set_defaults(handler=handle_lens_resync)

    acts_parser = subparsers.add_parser(
        "lens-acts",
        help="Show the unified preference-act ledger (model-miss corrections "
             "+ self-expressed trade-offs) — counts by trigger / kind / basin.",
    )
    acts_parser.set_defaults(handler=handle_lens_acts)


def handle_me_build(args):
    # Fail fast if the embedder model isn't downloaded — lens-build
    # uses embeddings for assistant-text reranking + basin clustering.
    # Without this gate the user gets a multi-minute startup followed
    # by an HF_HUB_OFFLINE error mid-call.
    import sys
    from ..embeddings import EmbedderNotReadyError, require_embedder_ready
    try:
        require_embedder_ready()
    except EmbedderNotReadyError as exc:
        print(str(exc), file=sys.stderr)
        sys.exit(1)

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
            force=getattr(args, "force", False),
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
    # 100-persona audit P51 fix: tell the user where to go next.
    import sys as _sys
    if getattr(args, "dry_run", False):
        _sys.stderr.write(
            "\n→ Stage 1 dry-run complete (no lens written). To build:\n"
            "    trinity-local lens-build\n"
        )
    else:
        _sys.stderr.write(
            "\n→ Lens built. View it:\n"
            "    trinity-local lens-show\n"
            "    open ~/.trinity/portal_pages/memory.html?file=lens.md\n"
        )


def handle_me_show(args):
    text = load_me()
    if not text:
        print("# lens not built yet — run `trinity-local lens-build`")
        print(f"# expected at: {me_path()}")
        return
    print(text)


def handle_lens_acts(args):
    from collections import Counter

    from ..me.preference_acts import iter_preference_acts, preference_acts_path

    acts = iter_preference_acts()
    by_trigger = Counter(a.trigger for a in acts)
    by_kind = Counter(a.kind for a in acts if a.kind)
    by_basin = Counter(a.basin for a in acts if a.basin)
    payload = {
        "ledger": str(preference_acts_path()),
        "total": len(acts),
        "by_trigger": dict(by_trigger),
        "by_kind": dict(sorted(by_kind.items(), key=lambda kv: -kv[1])),
        "by_basin": dict(sorted(by_basin.items(), key=lambda kv: -kv[1])[:10]),
    }
    print(json.dumps(payload, indent=2))
    if not acts:
        import sys
        sys.stderr.write(
            "\n→ No preference acts yet. Build the lens first:\n"
            "    trinity-local lens-build\n"
        )


def handle_lens_resync(args):
    import sys
    path, summary = resync_lens_from_disk()
    print(json.dumps({"path": str(path), **summary}, indent=2))
    if not summary.get("ok"):
        sys.stderr.write(
            "\n→ Nothing to resync. Build a lens first:\n"
            "    trinity-local lens-build\n"
        )
        return
    sys.stderr.write(
        f"\n→ Registry seeded ({summary['active_tensions']} active tension(s)); "
        f"lens.md re-rendered with support. View it:\n"
        "    trinity-local lens-show\n"
    )
