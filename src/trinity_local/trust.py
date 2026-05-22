"""Trinity trust mode — config + decision + audit-log query.

Phase 6 of the three-tier architecture. Council-mandated.

The trust substrate is what makes Trinity claim "we respect your
choices" credibly. Three orthogonal pieces:

  1. ~/.trinity/trust.toml — declarative per-operation + per-tier
     grants. Default "ask" means Trinity prompts before each
     operation; "trust" means proceed; "deny" means reject.
  2. ~/.trinity/audit.log — every operation Trinity runs (skill,
     pip, or extension tier) appends one JSONL line.
     scripts/_runtime.audit_log() is the canonical writer.
  3. --dangerously-trust-all flag — matches Claude Code's
     convention. When set, operations proceed WITHOUT prompting
     but are STILL audit-logged (the flag bypasses prompts, not
     accountability).

Resolution order (most specific wins):
  trust.operations[op] > trust.tiers[tier] > trust.default

When `--dangerously-trust-all` is set OR env var
`TRINITY_TRUST_ALL=1`: every operation resolves to "trust"
regardless of trust.toml. Audit log still fires.

The schema lives at schemas/trust.schema.json (with a bundled copy at
skills/trinity/schemas/trust.schema.json that the mirror-sync guard
keeps byte-identical).
"""
from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


TrustLevel = Literal["ask", "deny", "trust"]
Tier = Literal["skill", "pip", "extension"]


def _trinity_home() -> Path:
    override = os.environ.get("TRINITY_HOME")
    return Path(override) if override else Path.home() / ".trinity"


def _trust_path() -> Path:
    return _trinity_home() / "trust.toml"


def _audit_path() -> Path:
    return _trinity_home() / "audit.log"


@dataclass
class TrustConfig:
    """Parsed trust.toml. Default-empty if file missing.

    `rules` carries exact tier.operation overrides (council
    `c18f739a0234aa58` verdict). Keys are "<tier>.<operation>"
    strings — e.g. "extension.launch_council". They win against
    both per-tier and per-operation grants because they're the
    most specific.
    """
    default: TrustLevel = "ask"
    operations: dict[str, TrustLevel] = None  # type: ignore[assignment]
    tiers: dict[str, TrustLevel] = None  # type: ignore[assignment]
    rules: dict[str, TrustLevel] = None  # type: ignore[assignment]
    schema_version: int = 1

    def __post_init__(self) -> None:
        if self.operations is None:
            self.operations = {}
        if self.tiers is None:
            self.tiers = {}
        if self.rules is None:
            self.rules = {}


def load_trust_config() -> TrustConfig:
    """Read ~/.trinity/trust.toml. Returns defaults if file is missing
    or malformed (NEVER crashes — trust failures are silent
    permissive-by-default falls-back to 'ask')."""
    path = _trust_path()
    if not path.exists():
        return TrustConfig()
    try:
        # Python 3.11+ has tomllib; 3.10 needs tomli (external dep).
        # Trinity targets 3.10+, so we try both.
        try:
            import tomllib  # type: ignore[import-not-found]
        except ImportError:
            try:
                import tomli as tomllib  # type: ignore[import-not-found]
            except ImportError:
                # No TOML reader available — degrade silently.
                return TrustConfig()
        with path.open("rb") as f:
            data = tomllib.load(f)
    except Exception:
        return TrustConfig()

    trust_block = data.get("trust", {}) if isinstance(data, dict) else {}
    schema_version = data.get("schema_version", 1) if isinstance(data, dict) else 1
    return TrustConfig(
        schema_version=int(schema_version) if isinstance(schema_version, (int, float)) else 1,
        default=_coerce_level(trust_block.get("default"), "ask"),
        operations={
            k: _coerce_level(v, "ask")
            for k, v in (trust_block.get("operations", {}) or {}).items()
        },
        tiers={
            k: _coerce_level(v, "ask")
            for k, v in (trust_block.get("tiers", {}) or {}).items()
        },
        rules={
            k: _coerce_level(v, "ask")
            for k, v in (trust_block.get("rules", {}) or {}).items()
        },
    )


def _coerce_level(value: Any, fallback: TrustLevel) -> TrustLevel:
    if value in ("ask", "deny", "trust"):
        return value  # type: ignore[return-value]
    return fallback


def resolve_trust(
    *,
    operation: str,
    tier: Tier = "pip",
    config: TrustConfig | None = None,
    trust_all_flag: bool = False,
) -> TrustLevel:
    """Return the trust level for (operation, tier).

    Resolution (most-specific first; council c18f739a0234aa58 verdict):
      1. --dangerously-trust-all OR TRINITY_DANGEROUSLY_TRUST_ALL=1
         OR TRINITY_TRUST_ALL=1 → "trust"
      2. trust.rules["<tier>.<operation>"] — exact override
      3. trust.operations[operation]
      4. trust.tiers[tier]
      5. trust.default
    """
    if (trust_all_flag
            or os.environ.get("TRINITY_DANGEROUSLY_TRUST_ALL") == "1"
            or os.environ.get("TRINITY_TRUST_ALL") == "1"):
        return "trust"
    cfg = config if config is not None else load_trust_config()
    exact_key = f"{tier}.{operation}"
    if exact_key in cfg.rules:
        return cfg.rules[exact_key]
    if operation in cfg.operations:
        return cfg.operations[operation]
    if tier in cfg.tiers:
        return cfg.tiers[tier]  # type: ignore[index]
    return cfg.default


def trust_mode_source(
    *,
    operation: str,
    tier: Tier = "pip",
    config: TrustConfig | None = None,
    trust_all_flag: bool = False,
) -> str:
    """Return a label describing WHY the trust decision was reached.

    Council verdict (c18f739a): audit log records this so cross-tier
    debugging is possible. Values: "trust:flag", "trust:env",
    "trust:toml:rule", "trust:toml:operation", "trust:toml:tier",
    "trust:toml:default", "ask:toml:default", "deny:toml:rule", etc.

    Format: "<level>:<source>" where source is `flag` / `env` / `toml:<dim>`.
    """
    if trust_all_flag:
        return "trust:flag"
    if os.environ.get("TRINITY_DANGEROUSLY_TRUST_ALL") == "1" \
            or os.environ.get("TRINITY_TRUST_ALL") == "1":
        return "trust:env"
    cfg = config if config is not None else load_trust_config()
    exact_key = f"{tier}.{operation}"
    if exact_key in cfg.rules:
        return f"{cfg.rules[exact_key]}:toml:rule"
    if operation in cfg.operations:
        return f"{cfg.operations[operation]}:toml:operation"
    if tier in cfg.tiers:
        return f"{cfg.tiers[tier]}:toml:tier"  # type: ignore[index]
    return f"{cfg.default}:toml:default"


def trust_warning_banner(*, trust_all: bool = False) -> str | None:
    """Return a one-line warning string when trust mode is permissive,
    or None when in default 'ask' mode. Loud enough to notice on first
    invocation; quiet enough not to clutter repeated calls."""
    if trust_all or os.environ.get("TRINITY_TRUST_ALL") == "1":
        return (
            "⚠ Trinity is in --dangerously-trust-all mode. All operations "
            "proceed without prompting. Audit log at ~/.trinity/audit.log."
        )
    cfg = load_trust_config()
    if cfg.default == "trust":
        return (
            "⚠ Trinity trust.toml has default = \"trust\". All operations "
            "proceed without prompting. Audit log at ~/.trinity/audit.log."
        )
    return None


def emit_trust_warning_to_stderr(*, trust_all: bool = False) -> None:
    """Idempotent per-process: print the trust-warning banner once."""
    if getattr(emit_trust_warning_to_stderr, "_emitted", False):
        return
    banner = trust_warning_banner(trust_all=trust_all)
    if banner:
        print(banner, file=sys.stderr)
        emit_trust_warning_to_stderr._emitted = True  # type: ignore[attr-defined]


def read_audit_log(limit: int = 20, since_ts: str | None = None) -> list[dict]:
    """Read the last `limit` entries from ~/.trinity/audit.log.

    Returns most-recent-first. Each entry is the parsed JSON dict
    `audit_log()` wrote. Skips malformed lines silently (one corrupt
    write should not break audit-show).

    `since_ts` (ISO 8601 string) filters to entries on/after the
    timestamp. (The audit-show CLI is deferred to v1.1 per commit
    47e8250; this library function is the canonical read path.)
    """
    path = _audit_path()
    if not path.exists():
        return []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    entries: list[dict] = []
    for line in reversed(lines):
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if not isinstance(record, dict):
            continue
        if since_ts and record.get("ts", "") < since_ts:
            continue
        entries.append(record)
        if len(entries) >= limit:
            break
    return entries


def write_default_trust_toml() -> Path:
    """Create ~/.trinity/trust.toml with the v1.0 default shape, if it
    doesn't already exist. Idempotent — never overwrites."""
    path = _trust_path()
    if path.exists():
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        '# Trinity trust configuration. Schema version 1.\n'
        '# Resolution (most specific first):\n'
        '#   rules ("tier.operation") > operations > tiers > default\n'
        '# "ask" prompts the user; "trust" proceeds; "deny" rejects.\n'
        '# Override per-invocation: --dangerously-trust-all flag or\n'
        '# TRINITY_DANGEROUSLY_TRUST_ALL=1 env (still audit-logged).\n'
        '#\n'
        '# Schema: schemas/trust.schema.json\n'
        '# Ratified by council_c18f739a0234aa58 (2026-05-16).\n'
        '\n'
        'schema_version = 1\n'
        '\n'
        '[trust]\n'
        'default = "ask"\n'
        '\n'
        '[trust.tiers]\n'
        '# Per-tier defaults. skill = trust because Claude Code\n'
        '# already gates via its own permission prompts.\n'
        '# skill = "trust"\n'
        '# pip = "ask"\n'
        '# extension = "ask"\n'
        '\n'
        '[trust.operations]\n'
        '# Per-operation grants (cross-tier).\n'
        '# embed_batch = "trust"\n'
        '# kmeans = "trust"\n'
        '# launch_council = "ask"\n'
        '\n'
        '[trust.rules]\n'
        '# Exact tier.operation overrides — wins against tier and\n'
        '# operation defaults. Use for cross-tier asymmetries:\n'
        '# "skill.launch_council" = "trust"\n'
        '# "extension.launch_council" = "ask"\n',
        encoding="utf-8",
    )
    return path
