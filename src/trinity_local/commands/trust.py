"""trinity-local audit-show / trust-init / trust-show — Phase 6 CLI surface.

Council-mandated (Phase 6). Audit log readability is the user-visible
half of the trust+audit substrate; without it the trust mode is
write-only and users can't grep what Trinity did.
"""
from __future__ import annotations

import json
from types import SimpleNamespace

from ..trust import (
    load_trust_config,
    read_audit_log,
    resolve_trust,
    write_default_trust_toml,
)


def register(subparsers) -> None:
    asp = subparsers.add_parser(
        "audit-show",
        help="Show the last N entries from ~/.trinity/audit.log (most-recent first).",
    )
    asp.add_argument("--last", type=int, default=20,
                     help="Number of entries to show (default: 20).")
    asp.add_argument("--since", default=None,
                     help="ISO 8601 timestamp; only entries on/after this fire.")
    asp.add_argument("--json", action="store_true",
                     help="Emit JSON (default: human-readable table).")
    asp.set_defaults(handler=handle_audit_show)

    tip = subparsers.add_parser(
        "trust-init",
        help="Write a default ~/.trinity/trust.toml if missing (idempotent).",
    )
    tip.set_defaults(handler=handle_trust_init)

    tsp = subparsers.add_parser(
        "trust-show",
        help="Show the current trust configuration and resolved levels.",
    )
    tsp.add_argument("--operation", default=None,
                     help="Resolve trust level for a specific operation.")
    tsp.add_argument("--tier", default="pip",
                     choices=["skill", "pip", "extension"],
                     help="Tier for the resolution check.")
    tsp.set_defaults(handler=handle_trust_show)


def handle_audit_show(args: SimpleNamespace) -> int:
    entries = read_audit_log(limit=args.last, since_ts=args.since)
    if args.json:
        print(json.dumps(entries, indent=2))
        return 0
    if not entries:
        print("(no audit-log entries; ~/.trinity/audit.log is empty or absent)")
        return 0
    for entry in entries:
        ts = entry.get("ts", "")
        script = entry.get("script", "?")
        op = entry.get("operation", "?")
        outcome = entry.get("outcome", "?")
        tier = entry.get("tier", "?")
        detail = entry.get("detail", "")
        line = f"{ts}  [{tier}]  {script}.{op}  → {outcome}"
        if detail:
            line += f"  ({detail})"
        print(line)
    return 0


def handle_trust_init(args: SimpleNamespace) -> int:
    path = write_default_trust_toml()
    print(json.dumps({
        "path": str(path),
        "created": True,
    }, indent=2))
    return 0


def handle_trust_show(args: SimpleNamespace) -> int:
    cfg = load_trust_config()
    payload: dict = {
        "default": cfg.default,
        "operations": dict(cfg.operations),
        "tiers": dict(cfg.tiers),
    }
    if args.operation:
        level = resolve_trust(operation=args.operation, tier=args.tier,
                              config=cfg)
        payload["resolved"] = {
            "operation": args.operation,
            "tier": args.tier,
            "level": level,
        }
    print(json.dumps(payload, indent=2))
    return 0
