"""Tests for Phase 6 trust + audit substrate.

Covers:
  - trust.toml load / parse / default fallback
  - resolve_trust precedence (op > tier > default; --trust-all
    overrides all)
  - read_audit_log returns most-recent-first
  - read_audit_log handles missing file / malformed lines silently
  - write_default_trust_toml is idempotent
  - CLI subcommands audit-show / trust-init / trust-show
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def isolated_home(tmp_path, monkeypatch):
    monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
    # Reset the "warning already emitted" flag from the module
    from trinity_local import trust
    if hasattr(trust.emit_trust_warning_to_stderr, "_emitted"):
        del trust.emit_trust_warning_to_stderr._emitted
    return tmp_path


# ─── trust.toml load + parse ───────────────────────────────────────


def test_load_trust_config_missing_file_returns_defaults(isolated_home):
    from trinity_local.trust import load_trust_config

    cfg = load_trust_config()
    assert cfg.default == "ask"
    assert cfg.operations == {}
    assert cfg.tiers == {}


def test_load_trust_config_parses_valid_toml(isolated_home):
    from trinity_local.trust import load_trust_config

    (isolated_home / "trust.toml").write_text(
        '[trust]\ndefault = "trust"\n'
        '[trust.operations]\nembed_batch = "trust"\n'
        '[trust.tiers]\nskill = "trust"\n'
    )
    cfg = load_trust_config()
    assert cfg.default == "trust"
    assert cfg.operations["embed_batch"] == "trust"
    assert cfg.tiers["skill"] == "trust"


def test_load_trust_config_malformed_file_returns_defaults(isolated_home):
    """Garbage in trust.toml MUST NOT crash — degrade to safe defaults
    (trust system fails CLOSED to 'ask'). The audit log is the safety net."""
    from trinity_local.trust import load_trust_config

    (isolated_home / "trust.toml").write_text(
        "this is not valid toml -- []]}\n"
    )
    cfg = load_trust_config()
    assert cfg.default == "ask"


def test_load_trust_config_invalid_level_coerces_to_ask(isolated_home):
    """If user writes default = 'maybe' (not a valid level), coerce
    to 'ask' rather than propagating an invalid string."""
    from trinity_local.trust import load_trust_config

    (isolated_home / "trust.toml").write_text(
        '[trust]\ndefault = "maybe"\n'
    )
    cfg = load_trust_config()
    assert cfg.default == "ask"


# ─── resolve_trust precedence ──────────────────────────────────────


def test_resolve_trust_uses_default_when_no_overrides(isolated_home):
    from trinity_local.trust import resolve_trust

    assert resolve_trust(operation="x", tier="pip") == "ask"


def test_resolve_trust_operation_beats_tier_beats_default(isolated_home):
    from trinity_local.trust import resolve_trust, TrustConfig

    cfg = TrustConfig(
        default="ask",
        operations={"trusted_op": "trust"},
        tiers={"skill": "deny"},
    )
    # operation override wins
    assert resolve_trust(operation="trusted_op", tier="skill",
                         config=cfg) == "trust"
    # tier beats default
    assert resolve_trust(operation="other_op", tier="skill",
                         config=cfg) == "deny"
    # fall through to default
    assert resolve_trust(operation="other_op", tier="pip",
                         config=cfg) == "ask"


def test_resolve_trust_exact_rule_beats_operation_and_tier(isolated_home):
    """council c18f739a verdict: [trust.rules] entry with key
    '<tier>.<operation>' is the MOST specific override and wins
    against per-operation and per-tier grants."""
    from trinity_local.trust import resolve_trust, TrustConfig

    cfg = TrustConfig(
        default="ask",
        operations={"launch_council": "trust"},
        tiers={"extension": "trust"},
        rules={"extension.launch_council": "ask"},  # Most specific = wins
    )
    # Operation says trust, tier says trust, but the exact rule says ask.
    assert resolve_trust(
        operation="launch_council", tier="extension", config=cfg,
    ) == "ask"
    # No exact rule for skill.launch_council → operation grant ("trust") applies.
    assert resolve_trust(
        operation="launch_council", tier="skill", config=cfg,
    ) == "trust"


def test_trust_mode_source_labels(isolated_home, monkeypatch):
    """council c18f739a verdict: audit log records WHY a trust
    decision was reached. Source labels must be precise enough to
    debug cross-tier surprises."""
    from trinity_local.trust import trust_mode_source, TrustConfig

    cfg = TrustConfig(
        default="ask",
        operations={"op1": "trust"},
        tiers={"skill": "trust"},
        rules={"extension.op2": "deny"},
    )
    # Flag wins
    assert trust_mode_source(operation="x", trust_all_flag=True) == "trust:flag"
    # Env var wins
    monkeypatch.setenv("TRINITY_DANGEROUSLY_TRUST_ALL", "1")
    assert trust_mode_source(operation="x") == "trust:env"
    monkeypatch.delenv("TRINITY_DANGEROUSLY_TRUST_ALL")
    # Exact rule
    assert trust_mode_source(
        operation="op2", tier="extension", config=cfg,
    ) == "deny:toml:rule"
    # Operation grant
    assert trust_mode_source(
        operation="op1", tier="pip", config=cfg,
    ) == "trust:toml:operation"
    # Tier default
    assert trust_mode_source(
        operation="other", tier="skill", config=cfg,
    ) == "trust:toml:tier"
    # Global default
    assert trust_mode_source(
        operation="other", tier="pip", config=cfg,
    ) == "ask:toml:default"


def test_resolve_trust_dangerously_trust_all_overrides_all(isolated_home):
    from trinity_local.trust import resolve_trust, TrustConfig

    cfg = TrustConfig(default="deny", operations={"x": "deny"},
                      tiers={"skill": "deny"})
    # --dangerously-trust-all flag wins
    assert resolve_trust(operation="x", tier="skill", config=cfg,
                         trust_all_flag=True) == "trust"


def test_resolve_trust_env_var_overrides_all(isolated_home, monkeypatch):
    from trinity_local.trust import resolve_trust, TrustConfig

    cfg = TrustConfig(default="deny")
    monkeypatch.setenv("TRINITY_TRUST_ALL", "1")
    assert resolve_trust(operation="x", tier="pip", config=cfg) == "trust"


# ─── audit-log read ────────────────────────────────────────────────


def test_read_audit_log_missing_returns_empty(isolated_home):
    from trinity_local.trust import read_audit_log

    assert read_audit_log() == []


def test_read_audit_log_most_recent_first(isolated_home):
    """Audit log is JSONL append-only; reader inverts to most-recent-first."""
    from trinity_local.trust import read_audit_log

    audit = isolated_home / "audit.log"
    audit.write_text("\n".join([
        json.dumps({"ts": "2026-01-01T00:00:00", "script": "a", "operation": "op1", "outcome": "ok"}),
        json.dumps({"ts": "2026-01-02T00:00:00", "script": "b", "operation": "op2", "outcome": "ok"}),
        json.dumps({"ts": "2026-01-03T00:00:00", "script": "c", "operation": "op3", "outcome": "ok"}),
    ]) + "\n")
    entries = read_audit_log(limit=10)
    assert len(entries) == 3
    assert entries[0]["script"] == "c"  # most recent first
    assert entries[-1]["script"] == "a"


def test_read_audit_log_respects_limit(isolated_home):
    from trinity_local.trust import read_audit_log

    audit = isolated_home / "audit.log"
    lines = "\n".join([
        json.dumps({"ts": f"2026-01-{i:02d}", "script": "x", "operation": "y", "outcome": "ok"})
        for i in range(1, 11)
    ])
    audit.write_text(lines + "\n")
    entries = read_audit_log(limit=3)
    assert len(entries) == 3


def test_read_audit_log_skips_malformed_lines(isolated_home):
    """One corrupted JSONL line must not block reading the rest."""
    from trinity_local.trust import read_audit_log

    audit = isolated_home / "audit.log"
    audit.write_text(
        json.dumps({"ts": "2026-01-01", "script": "a", "operation": "x", "outcome": "ok"}) + "\n"
        + "{ this is corrupt json }}}\n"
        + json.dumps({"ts": "2026-01-02", "script": "b", "operation": "y", "outcome": "ok"}) + "\n"
    )
    entries = read_audit_log()
    assert len(entries) == 2


# ─── write_default_trust_toml ─────────────────────────────────────


def test_write_default_trust_toml_creates_file(isolated_home):
    from trinity_local.trust import write_default_trust_toml

    path = write_default_trust_toml()
    assert path.exists()
    assert '[trust]' in path.read_text()
    assert 'default = "ask"' in path.read_text()


def test_write_default_trust_toml_idempotent_does_not_overwrite(isolated_home):
    from trinity_local.trust import write_default_trust_toml

    path = isolated_home / "trust.toml"
    path.write_text("[trust]\ndefault = \"trust\"\n# user-edited\n")
    original = path.read_text()
    write_default_trust_toml()  # no-op when file exists
    assert path.read_text() == original


# ─── CLI subcommands ───────────────────────────────────────────────


def test_cli_audit_show_human_readable(isolated_home):
    audit = isolated_home / "audit.log"
    audit.write_text(json.dumps({
        "ts": "2026-05-16T12:00:00", "script": "embed",
        "operation": "embed_batch", "outcome": "ok", "tier": "skill",
    }) + "\n")
    result = subprocess.run(
        [sys.executable, "-m", "trinity_local.main", "audit-show", "--last", "5"],
        capture_output=True, text=True,
        env={**os.environ, "TRINITY_HOME": str(isolated_home)},
        timeout=15,
    )
    assert result.returncode == 0
    assert "embed.embed_batch" in result.stdout
    assert "[skill]" in result.stdout


def test_cli_audit_show_json_mode(isolated_home):
    audit = isolated_home / "audit.log"
    audit.write_text(json.dumps({
        "ts": "2026-05-16T12:00:00", "script": "x",
        "operation": "y", "outcome": "ok",
    }) + "\n")
    result = subprocess.run(
        [sys.executable, "-m", "trinity_local.main", "audit-show",
         "--last", "5", "--json"],
        capture_output=True, text=True,
        env={**os.environ, "TRINITY_HOME": str(isolated_home)},
        timeout=15,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert isinstance(data, list)
    assert len(data) == 1


def test_cli_trust_init_creates_file(isolated_home):
    result = subprocess.run(
        [sys.executable, "-m", "trinity_local.main", "trust-init"],
        capture_output=True, text=True,
        env={**os.environ, "TRINITY_HOME": str(isolated_home)},
        timeout=15,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert Path(data["path"]).exists()
    assert (isolated_home / "trust.toml").exists()


def test_cli_trust_show_with_operation_resolves(isolated_home):
    (isolated_home / "trust.toml").write_text(
        '[trust]\ndefault = "ask"\n'
        '[trust.operations]\nembed_batch = "trust"\n'
    )
    result = subprocess.run(
        [sys.executable, "-m", "trinity_local.main", "trust-show",
         "--operation", "embed_batch", "--tier", "skill"],
        capture_output=True, text=True,
        env={**os.environ, "TRINITY_HOME": str(isolated_home)},
        timeout=15,
    )
    assert result.returncode == 0
    data = json.loads(result.stdout)
    assert data["resolved"]["level"] == "trust"
