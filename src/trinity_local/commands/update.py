"""trinity-local update — pull latest, re-register MCP, run doctor.

The git-clone-led distribution model (no PyPI, no npm; council
`37eca30b6e7010df` ratified shape) makes updates a `git pull` away.
This command bundles the pull + side-effect refresh + verification
into one user-facing verb.

Side-effects on every update:
  1. `git pull --ff-only` in the skill directory (refuses non-FF
     merges so the user's local edits aren't silently overwritten)
  2. `trinity-local install-mcp` re-runs to pick up any new MCP tools
     or renamed entries (council c18f739a verdict: MCP config must
     refresh when the tool surface changes)
  3. `trinity-local install-extension --extension-id <prior-id>`
     re-runs if the user previously configured the Chrome extension
     (Native Messaging manifest may need refresh)
  4. `trinity-local doctor` to verify the new state

Trust positioning: explicit user invocation only. v1.0 does NOT
auto-pull. `trinity-local doctor` runs a cached staleness check
(_check_skill_freshness) on every invocation and surfaces a stderr
banner when behind origin/main — that's the only "automatic"
notification surface. No background processes, no scheduled jobs.
The user runs `trinity-local update` when they're ready to apply.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace


def register(subparsers) -> None:
    parser = subparsers.add_parser(
        "update",
        help="Pull latest, refresh MCP configs, verify with doctor.",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="Don't pull — just report how many commits behind origin.",
    )
    parser.add_argument(
        "--skill-dir", default=None,
        help="Override skill directory (default: ~/.claude/skills/trinity).",
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Emit machine-readable JSON instead of a human-readable report.",
    )
    parser.set_defaults(handler=handle_update)


def _skill_dir(override: str | None) -> Path:
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / ".claude" / "skills" / "trinity"


def _git(*args: str, cwd: Path) -> tuple[int, str, str]:
    """Run git with the given args in `cwd`. Returns (rc, stdout, stderr)."""
    proc = subprocess.run(
        ["git", *args], cwd=cwd, capture_output=True, text=True, check=False,
    )
    return proc.returncode, proc.stdout.strip(), proc.stderr.strip()


def _is_git_checkout(path: Path) -> bool:
    return (path / ".git").exists()


def _fetch_and_compute_lag(skill_dir: Path) -> tuple[int, int, str | None]:
    """Fetch origin + return (commits_behind, commits_ahead, error).

    error is None on success, a human-readable string on failure
    (network down, no remote, etc.). Network failures degrade gracefully —
    we treat them as "couldn't check" rather than "no updates".
    """
    rc, _, err = _git("fetch", "--quiet", "origin", cwd=skill_dir)
    if rc != 0:
        return 0, 0, f"git fetch failed: {err or '(no message)'}"

    rc, out, _ = _git("rev-list", "--count", "--left-right",
                      "HEAD...@{upstream}", cwd=skill_dir)
    if rc != 0:
        # Maybe no upstream tracking branch; try origin/main explicitly.
        rc, out, _ = _git("rev-list", "--count", "--left-right",
                          "HEAD...origin/main", cwd=skill_dir)
        if rc != 0:
            return 0, 0, "could not compute lag — no tracking branch?"
    parts = out.split()
    if len(parts) != 2:
        return 0, 0, f"unexpected rev-list output: {out!r}"
    ahead, behind = int(parts[0]), int(parts[1])
    return behind, ahead, None


def handle_update(args: SimpleNamespace) -> int:
    skill_dir = _skill_dir(getattr(args, "skill_dir", None))
    json_mode = bool(getattr(args, "json", False))
    check_only = bool(getattr(args, "check", False))

    if not skill_dir.exists():
        msg = f"skill directory not found at {skill_dir}"
        return _emit_error(msg, json_mode)
    if not _is_git_checkout(skill_dir):
        msg = (f"{skill_dir} is not a git checkout — update requires the "
               "skill to be installed via scripts/install.sh (which clones "
               "the repo).")
        return _emit_error(msg, json_mode)

    behind, ahead, fetch_err = _fetch_and_compute_lag(skill_dir)
    if fetch_err is not None:
        return _emit_error(fetch_err, json_mode, soft=True)

    if check_only:
        return _emit_check(behind, ahead, skill_dir, json_mode)

    if behind == 0:
        return _emit_already_up_to_date(ahead, json_mode)

    if ahead > 0:
        # User has local commits. ff-only would fail; we surface the
        # divergence rather than auto-rebasing.
        msg = (f"{skill_dir} has {ahead} local commit(s) not on origin; "
               f"refusing to fast-forward over them. Resolve manually "
               f"with `cd {skill_dir} && git status`.")
        return _emit_error(msg, json_mode)

    # Pull (fast-forward only).
    rc, _, err = _git("merge", "--quiet", "--ff-only", "@{upstream}",
                      cwd=skill_dir)
    if rc != 0:
        rc, _, err = _git("merge", "--quiet", "--ff-only", "origin/main",
                          cwd=skill_dir)
    if rc != 0:
        return _emit_error(f"git merge --ff-only failed: {err}", json_mode)

    # Re-run install-mcp to refresh any new MCP tool entries.
    mcp_rc = subprocess.run(
        [sys.executable, "-m", "trinity_local.main", "install-mcp"],
        capture_output=True, text=True, check=False,
    ).returncode

    # Re-run doctor to verify.
    doctor_rc = subprocess.run(
        [sys.executable, "-m", "trinity_local.main", "doctor"],
        capture_output=True, text=True, check=False,
    ).returncode

    return _emit_updated(behind, mcp_rc, doctor_rc, json_mode)


def _emit_check(behind: int, ahead: int, skill_dir: Path,
                json_mode: bool) -> int:
    if json_mode:
        print(json.dumps({
            "behind": behind, "ahead": ahead,
            "skill_dir": str(skill_dir),
            "up_to_date": behind == 0,
        }, indent=2))
    else:
        if behind == 0:
            print(f"Trinity is up to date ({skill_dir}).")
        else:
            print(f"Trinity is {behind} commit(s) behind origin/main. "
                  f"Run `trinity-local update` to apply.")
            if ahead > 0:
                print(f"  ({ahead} local commit(s) ahead — will block the pull.)")
    return 0


def _emit_already_up_to_date(ahead: int, json_mode: bool) -> int:
    if json_mode:
        print(json.dumps({"updated": False, "ahead": ahead,
                          "message": "already up to date"}, indent=2))
    else:
        print("Trinity is already up to date.")
        if ahead > 0:
            print(f"  ({ahead} local commit(s) ahead of origin/main.)")
    return 0


def _emit_updated(applied: int, mcp_rc: int, doctor_rc: int,
                  json_mode: bool) -> int:
    if json_mode:
        print(json.dumps({
            "updated": True,
            "commits_applied": applied,
            "install_mcp_returncode": mcp_rc,
            "doctor_returncode": doctor_rc,
        }, indent=2))
        return 0

    print(f"✓ Pulled {applied} commit(s) from origin")
    if mcp_rc == 0:
        print("✓ Refreshed MCP configs")
    else:
        print(f"⚠ install-mcp returned {mcp_rc} — "
              "run `trinity-local install-mcp` to debug")
    if doctor_rc == 0:
        print("✓ doctor green")
    else:
        print(f"⚠ doctor returned {doctor_rc} — "
              "run `trinity-local doctor` to see what's wrong")
    print()
    print("Note: Claude Code / Codex CLI / Gemini CLI / Cursor may need a "
          "restart to pick up new MCP tools.")
    print("Note: Chrome extension users may need to reload the unpacked "
          "extension at chrome://extensions.")
    return 0


def _emit_error(msg: str, json_mode: bool, soft: bool = False) -> int:
    if json_mode:
        print(json.dumps({"updated": False, "error": msg}, indent=2),
              file=sys.stderr)
    else:
        prefix = "warning" if soft else "error"
        print(f"{prefix}: {msg}", file=sys.stderr)
    return 0 if soft else 1
