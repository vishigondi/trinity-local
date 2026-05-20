"""Pre-flight cold-install checks for Trinity.

Per `council_35b2ae198a65b349`: the audit-missed launch blocker is a fresh
user running `lens-build` without provider auth, hanging silently, and
blaming Trinity. The eval seed: *"name a specific cold-install failure
mode AND the exact CLI command that detects it before the user hits a
live council."*

`trinity-local status` runs these checks (the standalone `doctor`
command was collapsed into `status` pre-launch). Each check returns:
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
        "gemini": "curl -fsSL https://antigravity.google/cli/install.sh | bash",
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
            fix="python3 -m pip install --user 'mcp>=1.0' 'Pillow>=10' 'numpy>=1.26'",
        )


def _check_feedback_consistency() -> CheckResult:
    """Council feedback entries should point at outcomes that still exist.

    Tick #69's data audit found 16 of 19 feedback entries in
    `~/.trinity/council_feedback.jsonl` pointed at council_ids whose
    outcome JSON had been deleted by older cleanup passes. The orphans
    are read-only history — they're not corrupting anything, but they
    DO skew downstream audits ("verdict capture rate is 16%!" was
    partially the orphans' fault). Surfacing the orphan count here
    makes the count reproducible and gives the user a hint when the
    feedback log has accumulated cruft.

    Soft check: passes either way (orphans are harmless), just reports
    the count so doctor isn't lying about cleanliness.
    """
    from .council_feedback import council_feedback_path
    from .state_paths import council_outcomes_dir
    fb = council_feedback_path()
    if not fb.exists():
        return CheckResult(
            name="feedback_consistency",
            ok=True,
            detail="no feedback log yet (fresh install)",
        )
    outcomes_dir = council_outcomes_dir()
    existing_outcomes = {p.stem for p in outcomes_dir.glob("council_*.json")}
    feedback_cids: set[str] = set()
    try:
        with fb.open(encoding="utf-8") as handle:
            for line in handle:
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                cid = entry.get("council_id")
                if cid:
                    feedback_cids.add(cid)
    except OSError as exc:
        return CheckResult(
            name="feedback_consistency",
            ok=False,
            detail=f"feedback log unreadable: {exc}",
        )
    orphans = feedback_cids - existing_outcomes
    total = len(feedback_cids)
    if not orphans:
        return CheckResult(
            name="feedback_consistency",
            ok=True,
            detail=f"all {total} feedback entries align with current outcomes",
        )
    return CheckResult(
        name="feedback_consistency",
        ok=True,  # orphans are harmless; just surface the count
        detail=(
            f"{len(orphans)} of {total} feedback entries reference outcomes "
            f"that no longer exist (history from earlier cleanups; safe to ignore)"
        ),
    )


def _check_skill_freshness() -> CheckResult:
    """Auto-CHECK leg of automatic updates: report whether the cloned
    skill repo is behind origin/main.

    No network call by default — uses git's cached refs which were
    last updated by `git fetch`. Users who want fresher staleness
    info can run `trinity-local update --check` (which does a real
    fetch). This keeps `doctor` fast (<200ms) while still surfacing
    the "you should update" signal in the common case where the
    fetch happened recently (last update, last install, etc.).

    Trust positioning: this surfaces "you're behind" — never auto-
    pulls. The user runs `trinity-local update` to apply.
    """
    import os
    import subprocess
    from pathlib import Path

    skill_dir = Path(os.environ.get(
        "TRINITY_SKILL_DIR", Path.home() / ".claude" / "skills" / "trinity"
    ))
    if not (skill_dir / ".git").exists():
        # Not a git checkout (or skill not installed via install.sh) —
        # nothing to compare against. This is fine (some users may run
        # straight from a repo clone for dev).
        return CheckResult(
            name="skill_freshness",
            ok=True,
            detail=(
                f"skill at {skill_dir} is not a git checkout; "
                "freshness check skipped"
            ),
        )

    try:
        result = subprocess.run(
            ["git", "rev-list", "--count", "HEAD..origin/main"],
            cwd=skill_dir, capture_output=True, text=True, check=False,
            timeout=2,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return CheckResult(
            name="skill_freshness", ok=True,
            detail="git not available; freshness check skipped",
        )
    if result.returncode != 0:
        return CheckResult(
            name="skill_freshness", ok=True,
            detail="no origin/main ref cached; "
                   "run `trinity-local update --check` to fetch",
        )
    behind = int(result.stdout.strip() or "0")
    if behind == 0:
        return CheckResult(
            name="skill_freshness", ok=True,
            detail="skill is up to date with origin/main (cached refs)",
        )
    return CheckResult(
        name="skill_freshness", ok=False,
        detail=(
            f"skill is {behind} commit(s) behind origin/main "
            "(per cached refs; run --check for a fresh fetch)"
        ),
        fix="trinity-local update   # pulls + refreshes MCP + verifies",
    )


def _check_dispatch_ready() -> CheckResult:
    """Extension dispatch readiness — the Chrome extension's Native
    Messaging host must be reachable for the launchpad to do anything.

    The macOS Shortcut tier was retired 2026-05-17 (Chrome extension is
    now the cross-platform launchpad host); this check covers macOS,
    Linux, and Windows with the same shape.

    Surfaces the same `recommended_action` hint the launchpad shows in
    its inline banner so the doctor and the launchpad agree.
    """
    try:
        from .launchpad_data import dispatch_readiness
    except Exception as exc:
        return CheckResult(
            name="dispatch_ready",
            ok=False,
            detail=f"could not import dispatch_readiness: {exc}",
        )
    readiness = dispatch_readiness()
    if readiness["ready"]:
        return CheckResult(
            name="dispatch_ready",
            ok=True,
            detail="launchpad dispatch ready via Chrome extension",
        )
    fix_command = (
        "trinity-local install-extension --extension-id <ID>   "
        "# 1. Load browser-extension/ in chrome://extensions first."
    )
    return CheckResult(
        name="dispatch_ready",
        ok=False,
        detail=readiness["recommended_action"] or "no dispatch path wired",
        fix=fix_command,
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
            fix="trinity-local dream   # rebuild memories; Phase 5 writes ~/.trinity/core.md (distill CLI was hidden 2026-05-17 — dream is the live path)",
        )
    size = core.stat().st_size
    return CheckResult(
        name="core_distilled",
        ok=True,
        detail=f"~/.trinity/core.md present ({size} bytes)",
    )


def _check_verdict_rate() -> CheckResult:
    """Soft check: what fraction of councils have a user verdict?

    The most direct Pillar 4 signal — Trinity's moat thesis ("the
    personal ledger of cross-model preferences") is empty without
    user verdicts. Tick #69 found 16% on the dev install; ticks
    #70/#93/#94 surfaced the gap on launchpad / CLI / per-card.
    This adds the same number to `trinity-local status` so the
    cold-install / launch-readiness path sees it too.

    Soft check (ok=True regardless) — low capture is the user's
    choice. The detail names the rate so they can decide whether
    to widen the funnel. Reuses `_verdict_stats()` from
    launchpad_data (single-source for the math).
    """
    try:
        from .launchpad_data import _verdict_stats
        stats = _verdict_stats()
    except Exception as exc:
        return CheckResult(
            name="verdict_rate",
            ok=True,
            detail=f"could not compute verdict stats: {exc}",
        )
    total = int(stats.get("total", 0))
    rated = int(stats.get("rated", 0))
    rate = stats.get("rate", 0.0) or 0.0
    if total == 0:
        return CheckResult(
            name="verdict_rate",
            ok=True,
            detail="no councils yet — run one to start the ledger",
        )
    # Same thresholds the launchpad accent prompt uses (tick #70):
    # quiet below total<5; nudge between 5 and 50% rate; silent
    # above 50% rate.
    pct = round(rate * 100)
    if total < 5:
        return CheckResult(
            name="verdict_rate",
            ok=True,
            detail=f"{rated} of {total} councils rated ({pct}%) — early days; widening the funnel matters more once you have ≥5",
        )
    if rate >= 0.5:
        return CheckResult(
            name="verdict_rate",
            ok=True,
            detail=f"{rated} of {total} councils rated ({pct}%) — ledger compounding",
        )
    return CheckResult(
        name="verdict_rate",
        ok=True,  # soft — under-rating is a choice, not broken
        detail=(
            f"{rated} of {total} councils rated ({pct}%). Trinity's moat is "
            f"the ledger; widening the funnel matters. Try `trinity-local "
            f"unrated` to see the backlog."
        ),
    )


def _check_vendor_published() -> CheckResult:
    """Soft check: are all VENDORED_FILES present under portal_pages/vendor/?

    vendor.py publishes 12 bundled JS files (petite-vue, chart.js, marked,
    9 d3-* modules) into `~/.trinity/portal_pages/vendor/` on every
    `refresh_launchpad`. The privacy claim ("never leaves your machine")
    is structural — every render references `./vendor/<file>.js`. If the
    publish silently failed at install (perms / disk full / etc.),
    `vendor.py`'s stderr warning will tell whoever ran install-mcp, but
    a user who clicks the launchpad days later sees broken `./vendor/*`
    404s with no surface that explains it. This check closes that loop.

    Soft (ok=True regardless of result). When some vendor files are
    missing, the detail names how many + suggests the one-liner that
    re-publishes them. Re-running `trinity-local portal-html` (or any
    `refresh_launchpad`-touching command) re-publishes.
    """
    try:
        from .state_paths import portal_pages_dir
        from .vendor import VENDORED_FILES
    except Exception as exc:
        return CheckResult(
            name="vendor_published",
            ok=True,
            detail=f"could not check vendor files: {exc}",
        )
    vendor_dir = portal_pages_dir() / "vendor"
    if not vendor_dir.exists():
        return CheckResult(
            name="vendor_published",
            ok=True,
            detail=(
                "vendor/ not yet populated — run "
                "`trinity-local portal-html` to publish "
                f"{len(VENDORED_FILES)} JS files into "
                "~/.trinity/portal_pages/vendor/"
            ),
        )
    missing = [n for n in VENDORED_FILES if not (vendor_dir / n).exists()]
    if missing:
        sample = ", ".join(missing[:3])
        suffix = "" if len(missing) <= 3 else f" (+{len(missing) - 3} more)"
        return CheckResult(
            name="vendor_published",
            ok=True,
            detail=(
                f"{len(missing)} of {len(VENDORED_FILES)} vendored JS "
                f"files missing ({sample}{suffix}) — launchpad will 404 "
                f"on those scripts. Re-run `trinity-local portal-html` "
                f"to republish. If it fails again, check perms on "
                f"{vendor_dir}."
            ),
        )
    return CheckResult(
        name="vendor_published",
        ok=True,
        detail=f"all {len(VENDORED_FILES)} vendored JS files present",
    )


def _check_cortex_freshness() -> CheckResult:
    """Soft check: are cortex picks current relative to recent councils?

    `picks.json` carries `consolidated_at` per task_type. If any council
    outcome on disk is newer than the freshest `consolidated_at`, the
    cortex layer's routing rules don't yet reflect the new training
    data — `ask()` will route based on stale signal until the user
    re-runs `consolidate`. Tick #96 noticed this concretely: real
    corpus had 19 outcomes but picks.json was based on 2.

    Soft check: ok stays True (stale picks aren't broken, just dated).
    Detail surfaces the count so the user can decide whether to
    re-consolidate. Pre-rated user (no record_outcome calls yet) gets
    a different message than rated-but-stale.
    """
    from .state_paths import picks_path, council_outcomes_dir
    picks = picks_path()
    if not picks.exists():
        return CheckResult(
            name="cortex_freshness",
            ok=True,
            detail="picks.json not built yet — run `trinity-local consolidate` once you have ≥10 rated councils",
        )
    try:
        picks_data = json.loads(picks.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return CheckResult(
            name="cortex_freshness",
            ok=True,
            detail="picks.json unreadable — re-run `trinity-local consolidate`",
        )
    # Find the freshest consolidated_at across all task_kinds in picks.
    consolidated_ats: list[str] = []
    for entry in picks_data.values() if isinstance(picks_data, dict) else []:
        if isinstance(entry, dict):
            ts = entry.get("consolidated_at")
            if isinstance(ts, str):
                consolidated_ats.append(ts)
    if not consolidated_ats:
        return CheckResult(
            name="cortex_freshness",
            ok=True,
            detail="picks.json has no task_types yet — re-run `trinity-local consolidate`",
        )
    freshest_picks = max(consolidated_ats)
    # Find newer outcomes on disk.
    outcomes = council_outcomes_dir()
    newer = 0
    total = 0
    if outcomes.is_dir():
        for path in outcomes.glob("council_*.json"):
            try:
                outcome = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            total += 1
            created = outcome.get("created_at") or ""
            if isinstance(created, str) and created > freshest_picks:
                newer += 1
    if newer == 0:
        return CheckResult(
            name="cortex_freshness",
            ok=True,
            detail=f"picks.json current ({total} outcomes, all consolidated)",
        )
    return CheckResult(
        name="cortex_freshness",
        ok=True,  # soft — not a failure, just outdated
        detail=(
            f"{newer} of {total} councils are newer than the last consolidate. "
            f"Run `trinity-local consolidate` to refresh cortex routing rules."
        ),
    )


def _check_handoff_ready() -> CheckResult:
    """Composite readiness for the 60-second hero demo (#115/#120/#121).

    Per-provider checks pass individually but the demo PATH fails on
    several real shapes that aren't caught:

      (1) Recent prompts have empty `following_assistant_text` — the
          handoff prompt's `ASSISTANT (provider):` lines are blank,
          and the receiving model has nothing to "continue from".
          This was the seed-without-assistant-text shape we saw on
          some gemini-takeout corpora.

      (2) All recent prompts come from ONE provider — handoff still
          works mechanically but the demo's "different model picks
          up where the other left off" beat depends on cross-provider
          history. Single-provider history = handoff = "same model
          continuing" = not the wedge.

      (3) Fewer than 2 enabled providers — there's nothing to hand
          off TO; the cross-provider wedge is structurally impossible.

    Each failure mode gets a specific fix hint so the user knows what
    to actually DO, not just that something's wrong. The check is
    SOFT (ok=True even when not demo-ready) — the user might be using
    Trinity for councils without ever wanting the handoff demo. But
    surfacing "your install isn't demo-ready and here's why" prevents
    the recording-day surprise where the user clicks handoff and gets
    a wall of empty ASSISTANT lines.
    """
    from .config import load_config
    from .memory.store import iter_prompt_nodes

    # (3) Are there ≥2 enabled providers to hand off between?
    try:
        config = load_config(required=False)
        enabled = [name for name, p in (config.providers or {}).items() if p.enabled]
    except Exception:
        enabled = []
    if len(enabled) < 2:
        return CheckResult(
            name="handoff_ready",
            ok=True,  # soft — handoff isn't required to use Trinity
            detail=(
                f"{len(enabled)} enabled providers — handoff demo needs "
                "≥2 (claude + gemini, or claude + codex). "
                "Enable a second in config.json or run "
                "`trinity-local install-mcp` to wire CLIs."
            ),
        )

    # (1) Do recent prompts carry assistant text the handoff can replay?
    # iter_prompt_nodes returns most-recent-first; we want a small
    # sample (the same shape `_select_recent_turns` uses) to mirror
    # what handoff would actually package.
    try:
        sample = list(iter_prompt_nodes(limit=10))
    except Exception:
        sample = []
    if not sample:
        return CheckResult(
            name="handoff_ready",
            ok=True,
            detail=(
                "no prompts indexed yet — handoff has nothing to package. "
                "Run `trinity-local seed-from-taste-terminal` to import "
                "your existing AI history."
            ),
        )
    with_assistant = [
        n for n in sample
        if (n.following_assistant_text or n.preceding_assistant_text or "").strip()
    ]
    if not with_assistant:
        return CheckResult(
            name="handoff_ready",
            ok=True,
            detail=(
                f"{len(sample)} recent prompts indexed but NONE carry assistant "
                "text — handoff would package empty ASSISTANT lines. Re-seed "
                "with `trinity-local seed-from-taste-terminal --include-assistant` "
                "or wait for incremental ingest to pick up a fresh conversation."
            ),
        )

    # (2) Do recent prompts span ≥2 providers? (Cross-provider demo beat)
    providers_seen = {n.provider for n in sample if n.provider}
    cross_provider = providers_seen & set(enabled)
    if len(cross_provider) < 2:
        only = next(iter(providers_seen), "unknown")
        return CheckResult(
            name="handoff_ready",
            ok=True,
            detail=(
                f"recent prompts only span 1 provider ({only}) — handoff "
                "works but the demo loses the cross-provider beat. Have a "
                f"quick conversation in a second provider, then re-run."
            ),
        )

    # All composite checks pass — ready for the killer-hook recording.
    target = next(iter(cross_provider - {"claude"}), next(iter(cross_provider)))
    return CheckResult(
        name="handoff_ready",
        ok=True,
        detail=(
            f"demo-ready: {len(with_assistant)}/{len(sample)} recent prompts "
            f"carry assistant text, history spans {sorted(cross_provider)}. "
            f"Try: `trinity-local handoff {target} --continuation \"...\"`"
        ),
    )


def _check_browser_capture() -> CheckResult:
    """v1.6 browser-capture preflight.

    Three install stages; first failure wins. All SOFT (ok=True) — the
    extension is optional. The user might be CLI-only and never want
    browser capture.

    Stage 1 — host binary on PATH. ``trinity-local install-extension``
    refuses to write the Native Messaging manifest until this exists.
    If missing, the wheel installed without the v1.6 console script
    (pre-v1.6 install of the package).

    Stage 2 — Chrome Native Messaging manifest written. Chrome only
    knows to spawn the host if its per-user
    ``NativeMessagingHosts/local.trinity.capture.json`` exists with
    Trinity's extension ID in ``allowed_origins``.

    Stage 3 — at least one capture exists. If both above pass but
    ``~/.trinity/conversations/`` is empty after the user has
    presumably installed the extension, the host has never been
    spawned — extension not loaded in Chrome, or its ID doesn't match
    the manifest's ``allowed_origins``. Surface what to check.

    Stage 4 — last capture freshness. Same threshold as Surface 33's
    ``stale`` flag (24h): if at least one capture exists but the most
    recent is > 24h old, surface as "investigate" (could be a provider
    refactor, extension disabled, or just genuine no-use).
    """
    import shutil
    import sys
    import time

    host_path = shutil.which("trinity-local-capture-host")
    if not host_path:
        return CheckResult(
            name="browser_capture",
            ok=True,  # soft
            detail=(
                "browser capture host not installed — `trinity-local-capture-host` "
                "not on PATH. Reinstall the wheel (`pip install -e .` or "
                "`pip install -U trinity-local`) so the v1.6 console script lands. "
                "Skip if you don't use claude.ai / chatgpt.com chat UIs."
            ),
        )

    # Stage 2 — Native Messaging manifest written?
    if sys.platform == "darwin":
        manifest_path = Path.home() / "Library" / "Application Support" / "Google" / "Chrome" / "NativeMessagingHosts" / "local.trinity.capture.json"
    elif sys.platform.startswith("linux"):
        manifest_path = Path.home() / ".config" / "google-chrome" / "NativeMessagingHosts" / "local.trinity.capture.json"
    else:
        # Windows path unverified; surface as soft skip.
        return CheckResult(
            name="browser_capture",
            ok=True,
            detail=f"v1.6 browser capture is macOS/Linux-first; platform {sys.platform!r} not yet supported.",
        )

    if not manifest_path.exists():
        return CheckResult(
            name="browser_capture",
            ok=True,
            detail=(
                "Native Messaging manifest not written — Chrome doesn't know how to "
                "spawn the capture host. Load `browser-extension/` in chrome://extensions, "
                "copy the extension ID, then `trinity-local install-extension "
                "--extension-id <ID>`. Skip if you don't use chat-UI captures."
            ),
        )

    # Stage 3 — any captures yet?
    from .state_paths import trinity_home
    conv_root = trinity_home() / "conversations"
    capture_files: list[Path] = []
    if conv_root.exists():
        for provider_dir in conv_root.iterdir():
            if not provider_dir.is_dir():
                continue
            for f in provider_dir.glob("*.json"):
                # Skip both sidecar flavors so doctor's "captures
                # exist" stage matches Surface 33's user-facing count
                # exactly: .stream.json (adapter accumulator) +
                # stream-<urlhash>.json (raw fallback for providers
                # without an adapter, e.g. gemini today).
                if f.name.endswith(".stream.json"):
                    continue
                if f.name.startswith("stream-"):
                    continue
                capture_files.append(f)

    if not capture_files:
        return CheckResult(
            name="browser_capture",
            ok=True,
            detail=(
                "Manifest installed but no captures yet. Check: extension loaded in "
                "chrome://extensions, extension ID in the manifest matches Chrome's "
                "assigned ID, then send a message on claude.ai or chatgpt.com. "
                "Debug steps in `browser-extension/README.md`."
            ),
        )

    # Stage 4 — freshness.
    try:
        latest_mtime = max(f.stat().st_mtime for f in capture_files)
    except OSError:
        latest_mtime = 0
    age_hours = (time.time() - latest_mtime) / 3600 if latest_mtime else None
    if age_hours is not None and age_hours > 24:
        return CheckResult(
            name="browser_capture",
            ok=True,
            detail=(
                f"{len(capture_files)} captures total but newest is "
                f"{int(age_hours)}h old. Provider may have refactored their API, "
                "extension may be disabled, or you may genuinely not have chatted "
                "lately. chrome://extensions → service worker console for diagnosis."
            ),
        )

    age_label = f"{int(age_hours * 60)}m" if age_hours and age_hours < 1 else f"{int(age_hours or 0)}h"
    return CheckResult(
        name="browser_capture",
        ok=True,
        detail=f"{len(capture_files)} captures across providers; newest {age_label} ago.",
    )


def format_one_line(report: DoctorReport) -> str:
    """Terse one-line health verdict for the `status` command header.

    `ready_for_council` is the launch bar (≥1 provider + writable home);
    everything else is optional / informational.
    """
    ok_count = sum(1 for c in report.checks if c.ok)
    total = len(report.checks)
    failed = [c for c in report.checks if not c.ok]
    if not report.ready_for_council:
        # No usable provider OR home not writable — the user can't run
        # a council until this is fixed.
        return f"red — not ready for council ({len(failed)} checks failing); run `trinity-local status --json` for detail"
    if failed:
        return f"yellow — ready for council, {ok_count}/{total} green ({len(failed)} optional gaps)"
    return f"green — {ok_count}/{total} checks pass"


def run_doctor() -> DoctorReport:
    """Sequential checks — fast (<1s), no network, no chairman calls."""
    report = DoctorReport()
    report.checks.append(_check_trinity_home())
    report.checks.append(_check_config())
    report.checks.append(_check_mcp_available())
    report.checks.append(_check_skill_freshness())
    report.checks.append(_check_dispatch_ready())
    report.checks.append(_check_feedback_consistency())
    report.checks.append(_check_provider("claude", "claude"))
    report.checks.append(_check_provider("codex", "codex"))
    report.checks.append(_check_provider("gemini", "gemini"))
    report.checks.append(_check_prompts_seeded())
    report.checks.append(_check_lens_built())
    report.checks.append(_check_core_distilled())
    report.checks.append(_check_verdict_rate())
    report.checks.append(_check_cortex_freshness())
    report.checks.append(_check_handoff_ready())
    report.checks.append(_check_browser_capture())
    report.checks.append(_check_vendor_published())
    return report


def _next_step_hint(report: DoctorReport) -> str | None:
    """Return a single 'try this next' line based on what's healthy.

    Pillar 4 + #115 first-run-wow: after a green doctor run, the user
    doesn't know what to DO next. The handoff demo is the 60-second
    wedge — surfacing it here closes the "I installed it, now what?"
    gap that #115 was originally about.

    Tiered by what's actually possible given the state we just checked:
      - <2 providers green: handoff has nothing to hand off TO; skip
      - ≥2 providers green, no prompts: suggest seeding first
      - ≥2 providers green AND prompts indexed: handoff demo
    """
    provider_checks = [c for c in report.checks if c.name.startswith("provider:")]
    green_providers = [c for c in provider_checks if c.ok]
    if len(green_providers) < 2:
        return None
    # Pick a target that ISN'T the user's default — the demo lands
    # when the SECOND model picks up the FIRST's context. If claude
    # is green, suggest handing off TO gemini (or codex if no gemini).
    others = [c.name.split(":", 1)[1] for c in green_providers if c.name != "provider:claude"]
    target = others[0] if others else green_providers[1].name.split(":", 1)[1]

    prompts_check = next((c for c in report.checks if c.name == "prompts_seeded"), None)
    if prompts_check is None or not prompts_check.ok:
        return (
            "Try this next: seed your prompt index with "
            "`trinity-local seed-from-taste-terminal`, then run "
            f"`trinity-local handoff {target}` to see the 60-second "
            "cross-provider continuity demo."
        )
    return (
        "Try this next: have a conversation in Claude Code, then run "
        f"`trinity-local handoff {target}` — {target} will pick up exactly "
        "where Claude left off. The 60-second wedge demo."
    )


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
        lines.append("Trinity is NOT ready. Fix the ✗ items above, then re-run `trinity-local status`.")
    hint = _next_step_hint(report)
    if hint:
        lines.append("")
        lines.append(hint)
    return "\n".join(lines)
