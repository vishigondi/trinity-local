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
    # provider configs / shells out to the CLI.
    dispatch = _build_real_dispatch(args.provider)

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
        # The auditor calls a DIFFERENT provider via the same dispatch shim
        # shape (dispatch_fn(provider_name, prompt) -> str). Need a real
        # dispatch that respects the provider arg, not the captured-default
        # `dispatch` above. Build a provider-aware one for the auditor.
        audit_dispatch = _build_provider_routed_dispatch()
        auditor = make_rule_auditor(audit_dispatch, audit_provider=audit_provider)
        print(f"Chairman-audit-mode enabled (audit provider: {audit_provider})", file=sys.stderr)

    patterns: dict = {}
    for basin_id, basin_outcomes in eligible.items():
        extractor = make_flagship_extractor(dispatch, basin_id)
        diversity = _entropy_diversity(basin_outcomes)
        try:
            pattern = consolidate_basin(
                basin_id=basin_id,
                outcomes=basin_outcomes,
                task_kinds=[basin_id],
                diversity_metric=diversity,
                extractor=extractor,
                auditor=auditor,
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
    print(json.dumps({
        "ok": True,
        "basins_consolidated": len(patterns),
        "path": str(_routing_patterns_path()),
        "calibration_reminder": (
            "Read ~/.trinity/cortex/routing_patterns.json and verify "
            "≥70% of the extracted rules match your actual behavior before "
            "the cortex wires into the query hot-path (Week 3)."
        ),
    }, indent=2))
    return 0


def _build_real_dispatch(provider_name: str):
    """Production dispatch shim — runs the provider CLI once per call.
    Returns a Callable matching dispatch_fn(provider, prompt) -> response_text.
    Separate from the ask shim so it's easy to swap in a different model or
    cheaper sub for consolidation later.
    """
    from ..config import load_config
    from ..providers import make_provider, ProviderError

    def _dispatch(_provider: str, prompt: str) -> str:
        # Note: we ignore the first arg here and always route to the user's
        # configured `provider_name` flag — consolidation is one model writing
        # the rule, not a council. (The ask dispatch shim is per-provider.)
        config = load_config()
        cfg = None
        # config.providers is a DICT keyed by name; iterate .values() for the
        # ProviderConfig objects. Iterating the dict directly yields keys
        # (strings), which would crash silently on .name/.enabled access
        # inside the try/except wrapper. Same regression that hit
        # mcp_server._dispatch_via_config in commit bb482da — kept fixed
        # here too.
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


def _build_provider_routed_dispatch():
    """Build a dispatch shim that respects its provider argument (unlike the
    extractor dispatch, which is closed over a single provider). The audit
    pass needs this because it deliberately calls a DIFFERENT provider than
    the primary extractor — same shape, different routing.
    """
    from ..config import load_config
    from ..providers import make_provider, ProviderError

    def _dispatch(provider_name: str, prompt: str) -> str:
        config = load_config()
        cfg = None
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
