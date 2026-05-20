"""Importable utility — trust + audit-log handlers (CLI deferred to v1.1).

The standalone `trinity-local audit-show / trust-init / trust-show`
CLIs are deferred to v1.1 per the pre-launch simplification. The
trust + audit substrate ships in v1.0 as a library — `trinity_local.trust`
remains importable, the handlers below stay reachable by tests, but
main.py doesn't register them into the CLI surface yet.
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
