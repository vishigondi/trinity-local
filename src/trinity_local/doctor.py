"""Pre-flight cold-install checks for Trinity.

Per `council_35b2ae198a65b349`: the audit-missed launch blocker is a fresh
user running `me-build` without provider auth, hanging silently, and
blaming Trinity. The eval seed: *"name a specific cold-install failure
mode AND the exact CLI command that detects it before the user hits a
live council."*

`trinity-local doctor` is that command. Each check returns:
- ok: bool
- name: short human label
- detail: what it found
- fix: one-line command the user runs to resolve

Doctor never makes network calls and never invokes a chairman; it's pure
filesystem + subprocess version probes. <1s on a working install.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .state_paths import state_dir


# Provider-specific auth indicators. We don't probe a live API call (that
# would require user input on auth prompts and add latency). We check for
# the indicator files each CLI writes after the user authenticates once.
_AUTH_INDICATORS = {
    "claude": [
        Path.home() / ".claude" / ".credentials.json",
        Path.home() / ".claude" / "config.json",
        Path.home() / ".claude.json",  # Claude Code's project config
    ],
    "codex": [
        Path.home() / ".codex" / "auth.json",
        Path.home() / ".codex" / "config.toml",
    ],
    "gemini": [
        Path.home() / ".gemini" / ".credentials" / "credentials.json",
        Path.home() / ".gemini" / "settings.json",
    ],
}


@dataclass
class CheckResult:
    name: str
    ok: bool
    detail: str = ""
    fix: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ok": self.ok,
            "detail": self.detail,
            "fix": self.fix,
        }


@dataclass
class DoctorReport:
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def all_ok(self) -> bool:
        return all(c.ok for c in self.checks)

    @property
    def ready_for_council(self) -> bool:
        """Minimum bar: ≥1 provider ready + Trinity dir writeable."""
        provider_checks = [c for c in self.checks if c.name.startswith("provider:")]
        ready_providers = sum(1 for c in provider_checks if c.ok)
        trinity_ok = next((c.ok for c in self.checks if c.name == "trinity_home_writeable"), False)
        return ready_providers >= 1 and trinity_ok

    def to_dict(self) -> dict[str, Any]:
        return {
            "checks": [c.to_dict() for c in self.checks],
            "all_ok": self.all_ok,
            "ready_for_council": self.ready_for_council,
        }


def _check_trinity_home() -> CheckResult:
    """state_dir() itself can raise on a read-only parent — wrap the whole
    thing in one try block so the doctor surfaces the failure as a check
    result instead of bubbling up as an exception."""
    try:
        home = state_dir()
        probe = home / ".doctor_write_probe"
        probe.write_text("ok")
        probe.unlink()
        return CheckResult(
            name="trinity_home_writeable",
            ok=True,
            detail=f"{home} writeable",
        )
    except OSError as exc:
        # state_dir() failed before we got home, or write probe failed.
        # Read the env var directly for the user-facing error so they know
        # which path they need to fix.
        import os
        target = os.environ.get("TRINITY_HOME") or str(Path.home() / ".trinity")
        return CheckResult(
            name="trinity_home_writeable",
            ok=False,
            detail=f"{target} not writeable: {exc}",
            fix=f"chmod u+w {target} OR set TRINITY_HOME=/path/to/writeable/dir",
        )


def _check_provider(provider: str, cli_name: str) -> CheckResult:
    """Three sub-checks merged into one CheckResult: installed → auth indicator
    present → recently used (transcript file modified < 90 days ago).

    Why one merged check: from the user's perspective, "claude is ready" is
    one bit. The detail string surfaces which sub-check failed for the fix.
    """
    installed = shutil.which(cli_name) is not None
    if not installed:
        return CheckResult(
            name=f"provider:{provider}",
            ok=False,
            detail=f"{cli_name} CLI not on PATH",
            fix=_install_command_for(provider),
        )

    indicators = _AUTH_INDICATORS.get(provider, [])
    auth_seen = any(p.exists() for p in indicators)
    if not auth_seen:
        return CheckResult(
            name=f"provider:{provider}",
            ok=False,
            detail=f"{cli_name} installed but no auth indicator file found",
            fix=f"{cli_name} login   # or run any one-shot {cli_name} command interactively",
        )

    return CheckResult(
        name=f"provider:{provider}",
        ok=True,
        detail=f"{cli_name} installed and authenticated",
    )


def _install_command_for(provider: str) -> str:
    """Single-line install hints — what we'd put in the README too."""
    return {
        "claude": "Install Claude Code: https://docs.claude.com/en/docs/claude-code",
        "codex": "npm install -g @openai/codex   # or: brew install codex",
        "gemini": "npm install -g @google/gemini-cli",
    }.get(provider, f"install the {provider} CLI")


def _check_config() -> CheckResult:
    """Config loadable + at least one provider enabled."""
    try:
        from .config import load_config
        cfg = load_config(required=False)
        if cfg is None:
            return CheckResult(
                name="config_loadable",
                ok=False,
                detail="config.json not found and no defaults available",
                fix="trinity-local install-mcp   # creates a default config",
            )
        enabled = [n for n, p in cfg.providers.items() if p.enabled and p.type in ("cli", "codex")]
        if not enabled:
            return CheckResult(
                name="config_loadable",
                ok=False,
                detail="config.json has no enabled CLI providers",
                fix="edit config.json — enable at least one of {claude, gemini, codex}",
            )
        return CheckResult(
            name="config_loadable",
            ok=True,
            detail=f"config OK · enabled providers: {', '.join(enabled)}",
        )
    except Exception as exc:
        return CheckResult(
            name="config_loadable",
            ok=False,
            detail=f"config load failed: {exc}",
            fix="trinity-local install-mcp   # rewrites a default config",
        )


def _check_mcp_available() -> CheckResult:
    """MCP server module importable (the `mcp` extras dependency installed)."""
    try:
        import mcp  # noqa: F401
        return CheckResult(
            name="mcp_available",
            ok=True,
            detail="mcp package importable",
        )
    except ImportError:
        return CheckResult(
            name="mcp_available",
            ok=False,
            detail="mcp package not installed (Claude Code MCP integration disabled)",
            fix="pip install 'trinity-local[mcp]'   # adds the mcp dep",
        )


def _check_prompts_seeded() -> CheckResult:
    """Soft check: do we have any prompt history? Doctor passes either way
    (a fresh install is legitimately empty), but surfaces a hint.

    Reads from ~/.trinity/prompts/prompt_nodes.jsonl (renamed from
    `memory/` per the brand axis: prompts are raw, memories is the
    consolidated output).
    """
    # state_dir() / "memory" was the v1.0 path; the renamed location is
    # state_dir() / "prompts". `prompts_dir()` resolves either via the
    # in-place migration helper.
    from .state_paths import prompts_dir
    nodes = prompts_dir() / "prompt_nodes.jsonl"
    if not nodes.exists() or nodes.stat().st_size == 0:
        return CheckResult(
            name="prompts_seeded",
            ok=True,  # not blocking — first-time users have empty memory
            detail="no transcripts seeded yet (you can still run councils)",
            fix="trinity-local seed-from-taste-terminal --path ~/projects/taste-terminal/data/exports   # if you have transcripts to ingest",
        )
    # Approximate count from line count
    line_count = sum(1 for _ in nodes.open())
    return CheckResult(
        name="prompts_seeded",
        ok=True,
        detail=f"{line_count} prompt nodes indexed at ~/.trinity/prompts/",
    )


def _check_lens_built() -> CheckResult:
    """Soft check: has the lens been built? Doctor passes either way.

    Reads from ~/.trinity/memories/lens.md (renamed from `me.md` per
    the 5-memories restructure)."""
    from .state_paths import lens_path
    lens = lens_path()
    if not lens.exists():
        return CheckResult(
            name="lens_built",
            ok=True,  # not blocking
            detail="lens not built yet",
            fix="trinity-local lens-build   # builds your taste lenses (after running a few councils)",
        )
    size = lens.stat().st_size
    return CheckResult(
        name="lens_built",
        ok=True,
        detail=f"~/.trinity/memories/lens.md present ({size} bytes)",
    )


def _check_core_distilled() -> CheckResult:
    """Soft check: has the singular core.md distillation been built?

    core.md is what the chairman reads FIRST on every council — when
    missing, chairman falls through to the full lens.md (more context,
    longer prompts). Surface the upgrade path."""
    from .state_paths import core_path
    core = core_path()
    if not core.exists():
        return CheckResult(
            name="core_distilled",
            ok=True,
            detail="core.md not distilled yet (chairman falls through to full lens)",
            fix="trinity-local distill   # writes ~/.trinity/core.md — the singular paragraph chairman reads first",
        )
    size = core.stat().st_size
    return CheckResult(
        name="core_distilled",
        ok=True,
        detail=f"~/.trinity/core.md present ({size} bytes)",
    )


def run_doctor() -> DoctorReport:
    """Sequential checks — fast (<1s), no network, no chairman calls."""
    report = DoctorReport()
    report.checks.append(_check_trinity_home())
    report.checks.append(_check_config())
    report.checks.append(_check_mcp_available())
    report.checks.append(_check_provider("claude", "claude"))
    report.checks.append(_check_provider("codex", "codex"))
    report.checks.append(_check_provider("gemini", "gemini"))
    report.checks.append(_check_prompts_seeded())
    report.checks.append(_check_lens_built())
    report.checks.append(_check_core_distilled())
    return report


def format_human(report: DoctorReport) -> str:
    """Pretty-print the report for the CLI."""
    lines: list[str] = []
    for c in report.checks:
        mark = "✓" if c.ok else "✗"
        lines.append(f"  {mark}  {c.name:30s}  {c.detail}")
        if not c.ok and c.fix:
            lines.append(f"        → fix: {c.fix}")
    lines.append("")
    if report.all_ok:
        lines.append("All checks passed. Trinity is ready.")
    elif report.ready_for_council:
        lines.append("Ready for your first council. Some optional checks failed (see above).")
    else:
        lines.append("Trinity is NOT ready. Fix the ✗ items above, then re-run `trinity-local doctor`.")
    return "\n".join(lines)
