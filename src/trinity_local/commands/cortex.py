"""`trinity-local consolidate` — v1.5 cortex consolidation pass.

Walks ~/.trinity/council_outcomes/, groups by basin (chairman-classified
task_type for v1.5 Week 2), calls the flagship extractor per basin, computes
system trust_score, writes ~/.trinity/cortex/routing_patterns.json.

Per spec-v1.5.md: human calibration checkpoint required before Week 3 wires
this into the query hot-path. Run this CLI, then read 30 extracted rules and
verify they match your behavior. If <70% agreement, iterate the prompt before
shipping. The cortex fails SILENTLY with bad rules — gate exists for a reason.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path


def register(subparsers):
    cp = subparsers.add_parser(
        "consolidate",
        help="Extract routing patterns from council outcomes into ~/.trinity/cortex/",
    )
    cp.add_argument(
        "--min-basin-size",
        type=int,
        default=3,
        help="Skip basins with fewer than this many outcomes (default: 3)",
    )
    cp.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the basins + outcome counts; don't call the flagship or write to disk",
    )
    cp.add_argument(
        "--basin",
        action="append",
        default=None,
        help="Only consolidate the named basin (task_type). Repeatable. Default: all.",
    )
    cp.add_argument(
        "--provider",
        default="claude",
        help="Which provider to use for the flagship extraction call (default: claude)",
    )
    cp.add_argument(
        "--audit",
        action="store_true",
        help="Run chairman-audit-mode: a second flagship (different provider) reads each extracted rule and votes agreed/disagreed/unclear. Disagreement demotes trust via the audit_score component. Catches both rubber-stamping by the primary chairman and silent model regressions.",
    )
    cp.add_argument(
        "--audit-provider",
        default=None,
        help="Provider for the audit pass (default: gemini, or codex if --provider=gemini). Must differ from --provider — an audit by the same model that wrote the rule is worse than no audit at all.",
    )
    cp.set_defaults(handler=handle_consolidate)

    op = subparsers.add_parser(
        "cortex-override",
        help="Mark a cortex routing rule wrong; halves effective trust per click. Persists across consolidations.",
    )
    op.add_argument(
        "--basin",
        required=True,
        help="Basin id (task_type) of the rule to demote.",
    )
    op.add_argument(
        "--reason",
        default=None,
        help="Optional one-line reason — stored alongside the override for future audit.",
    )
    op.add_argument(
        "--reset",
        action="store_true",
        help="Reset override_count for this basin to 0 (the user changed their mind / the next consolidate got it right).",
    )
    op.set_defaults(handler=handle_cortex_override)


def handle_cortex_override(args):
    from ..cortex import effective_trust, load_routing_patterns, save_routing_patterns

    patterns = load_routing_patterns()
    if not patterns:
        print(json.dumps({"ok": False, "reason": "no cortex consolidation yet — run `trinity-local consolidate` first"}, indent=2))
        return 1
    if args.basin not in patterns:
        available = sorted(patterns.keys())
        print(json.dumps({
            "ok": False,
            "reason": f"basin {args.basin!r} not in cortex; known basins: {available}",
        }, indent=2))
        return 1

    pattern = patterns[args.basin]
    prior = pattern.override_count
    if args.reset:
        pattern.override_count = 0
        action = "reset"
    else:
        pattern.override_count = prior + 1
        action = "incremented"
    save_routing_patterns(patterns)

    # Append a cortex_override row to the merge log (tick #45). Same
    # additive side-channel as the council_winner row from tick #44 —
    # try/except-wrapped so a log-write failure can't break the CLI.
    try:
        from ..merges import record_merge
        record_merge({
            "type": "cortex_override",
            "basin_id": args.basin,
            "action": action,
            "prior_count": prior,
            "new_count": pattern.override_count,
            "raw_trust": round(pattern.trust_score.value, 3),
            "reason": args.reason,
        })
    except Exception:
        pass

    print(json.dumps({
        "ok": True,
        "basin_id": args.basin,
        "action": action,
        "override_count": pattern.override_count,
        "raw_trust": round(pattern.trust_score.value, 3),
        "effective_trust": round(effective_trust(pattern), 3),
        "reason": args.reason,
    }, indent=2))
    return 0


def handle_consolidate(args):
    from ..cortex import (
        consolidate_basin,
        group_outcomes_by_basin,
        iter_outcomes,
        make_flagship_extractor,
        save_routing_patterns,
        _entropy_diversity,
    )

    outcomes = iter_outcomes()
    if not outcomes:
        print(json.dumps({"ok": False, "reason": "no council outcomes yet"}, indent=2))
        return 0

    grouped = group_outcomes_by_basin(outcomes)
    if args.basin:
        grouped = {k: v for k, v in grouped.items() if k in set(args.basin)}

    # Filter by min_basin_size + report what's eligible.
    eligible = {k: v for k, v in grouped.items() if len(v) >= args.min_basin_size}
    skipped = {k: len(v) for k, v in grouped.items() if k not in eligible}

    if args.dry_run:
        report = {
            "ok": True,
            "mode": "dry-run",
            "eligible_basins": {k: len(v) for k, v in eligible.items()},
            "skipped_below_min": skipped,
            "total_outcomes": len(outcomes),
            "would_call_flagship": args.provider,
        }
        print(json.dumps(report, indent=2))
        return 0

    if not eligible:
        print(json.dumps({
            "ok": False,
            "reason": f"no basins with >= {args.min_basin_size} outcomes",
            "basins_below_min": skipped,
        }, indent=2))
        return 1

    # Build the production dispatch shim. Lazy-imported because it touches
    # provider configs / shells out to the CLI. Provider-routed — same
    # primitive serves both extractor and auditor.
    dispatch = _build_real_dispatch()

    auditor = None
    if args.audit:
        from ..cortex import make_rule_auditor

        audit_provider = args.audit_provider or ("codex" if args.provider == "gemini" else "gemini")
        if audit_provider == args.provider:
            print(json.dumps({
                "ok": False,
                "reason": f"--audit-provider must differ from --provider; both are {args.provider!r}",
            }, indent=2))
            return 1
        auditor = make_rule_auditor(dispatch, audit_provider=audit_provider)
        print(f"Chairman-audit-mode enabled (audit provider: {audit_provider})", file=sys.stderr)

    # Preserve user-veto state across re-extractions. Without this, every
    # `consolidate` would erase the user's "this rule is wrong" signal — the
    # whole point of overrides is that they persist until the user resets them.
    from ..cortex import load_routing_patterns as _load_prior_patterns
    prior_patterns = _load_prior_patterns()

    patterns: dict = {}
    for basin_id, basin_outcomes in eligible.items():
        extractor = make_flagship_extractor(dispatch, basin_id, provider=args.provider)
        diversity = _entropy_diversity(basin_outcomes)
        prior_override = prior_patterns[basin_id].override_count if basin_id in prior_patterns else 0
        try:
            pattern = consolidate_basin(
                basin_id=basin_id,
                outcomes=basin_outcomes,
                task_types=[basin_id],
                diversity_metric=diversity,
                extractor=extractor,
                auditor=auditor,
                prior_override_count=prior_override,
            )
            patterns[basin_id] = pattern
            audit_tag = f" audit={pattern.audit_status}" if auditor else ""
            print(
                f"  ✓ {basin_id} (n={len(basin_outcomes)}) "
                f"→ primary={pattern.routing_rule.primary} "
                f"trust={pattern.trust_score.value:.2f} ({pattern.trust_score.interpretation}){audit_tag}",
                file=sys.stderr,
            )
        except Exception as exc:  # noqa: BLE001 — surface to operator, don't abort the batch
            print(f"  ✗ {basin_id} (n={len(basin_outcomes)}): {type(exc).__name__}: {exc}", file=sys.stderr)
            continue

    if not patterns:
        print(json.dumps({"ok": False, "reason": "all basin extractions failed"}, indent=2))
        return 1

    save_routing_patterns(patterns)
    # picks.json was just rewritten → core.md is now stale. Auto-fire
    # distill so the chairman sees fresh picks in core context on its
    # next council. is_core_stale() guards the call internally.
    routing_summary: dict | None = None
    distill_summary: dict | None = None
    try:
        from ..personal_routing import freeze_routing_to_disk
        table = freeze_routing_to_disk()
        routing_summary = {"task_types": len((table or {}).get("by_task_type") or {})}
    except Exception as exc:
        routing_summary = {"error": f"{type(exc).__name__}: {exc}"}
    try:
        from ..distill import distill_via_chairman
        distill_summary = distill_via_chairman(provider=args.provider)
    except Exception as exc:
        distill_summary = {"ok": False, "error": f"{type(exc).__name__}: {exc}"}
    payload = {
        "ok": True,
        "basins_consolidated": len(patterns),
        "path": str(_routing_patterns_path()),
        **({"routing_frozen": routing_summary} if routing_summary is not None else {}),
        "calibration_reminder": (
            "Read ~/.trinity/scoreboard/picks.json and verify ≥70% of the "
            "extracted rules match your actual behavior before the cortex "
            "wires into the query hot-path (Week 3)."
        ),
    }
    if distill_summary is not None:
        payload["distill"] = distill_summary
    print(json.dumps(payload, indent=2))
    return 0


def _build_real_dispatch():
    """Production dispatch shim — runs the provider CLI once per call.
    Returns a Callable matching dispatch_fn(provider, prompt) -> response_text.

    Provider-routed: honors its first argument (the provider name passed by
    the extractor or auditor). The previous version closed over a single
    --provider flag and silently ignored the dispatch-call's provider arg,
    which hid a bug where make_flagship_extractor was hardcoding "claude"
    regardless of CLI choice. Both ends now agree on the provider.
    """
    from ..config import load_config
    from ..providers import make_provider, ProviderError

    def _dispatch(provider_name: str, prompt: str) -> str:
        config = load_config()
        cfg = None
        # config.providers is a dict keyed by name; iterate .values() for the
        # ProviderConfig objects. Iterating the dict yields keys (strings),
        # which crashes silently on .name/.enabled access inside the
        # try/except wrapper. Same regression that hit
        # mcp_server._dispatch_via_config in commit bb482da.
        for p in config.providers.values():
            if p.name == provider_name and p.enabled:
                cfg = p
                break
        if cfg is None:
            raise ProviderError(f"Provider not configured or not enabled: {provider_name}")
        prov = make_provider(cfg)
        result = prov.run(prompt, Path.cwd())
        if result.returncode != 0:
            raise ProviderError(f"{provider_name} exit {result.returncode}: {result.stderr[:200]}")
        return result.stdout

    return _dispatch


def _routing_patterns_path():
    from ..state_paths import cortex_routing_patterns_path
    return cortex_routing_patterns_path()
