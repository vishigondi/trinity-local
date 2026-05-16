"""Handlers for install-mcp, install-app, install-hooks."""
from __future__ import annotations

import json
import re
import sys
from importlib import resources
from pathlib import Path

from ..launchpad_install import install_launchpad_shortcuts
from ..refresh import refresh_launchpad


def register(subparsers):
    imp = subparsers.add_parser("install-mcp", help="Install Trinity as an MCP server in Claude Code, Gemini CLI, Codex CLI, and Cursor")
    imp.add_argument("--scope", choices=["user", "project"], default="user", help="User-wide or project-specific installation")
    imp.set_defaults(handler=handle_install_mcp)

    iap = subparsers.add_parser("install-app", help="Install the Trinity desktop launcher app")
    iap.add_argument(
        "--destination",
        action="append",
        default=None,
        help="Directory to install Trinity.app into; repeat for multiple destinations. Defaults to Applications when writable plus Desktop.",
    )
    iap.set_defaults(handler=handle_install_app)

    ihp = subparsers.add_parser("install-hooks", help="Install Trinity Stop hook (calls watch-once after each Claude turn)")
    ihp.add_argument("--path", default=".", help="Project directory to install hooks into")
    ihp.set_defaults(handler=handle_install_hooks)

    iep = subparsers.add_parser(
        "install-extension",
        help="Write Chrome's Native Messaging manifest so the Trinity browser extension can spawn the local capture host",
    )
    iep.add_argument(
        "--extension-id",
        help="Chrome-assigned extension ID (the long hash from chrome://extensions). Required on first install; cached afterwards.",
    )
    iep.add_argument(
        "--host-path",
        help="Path to the trinity-local-capture-host binary. Defaults to the one resolved via shutil.which().",
    )
    iep.set_defaults(handler=handle_install_extension)

    # uninstall — inverse of install-mcp + install-app + install-extension.
    # 100-persona audit Theme D #1 (personas P30/P57/P85): the "own your
    # data" wedge cuts the wrong way if removing Trinity requires hand-
    # editing 4 MCP configs + deleting 2 Trinity.app copies + a Chrome
    # manifest + the skill file + ~/.trinity/. Dry-run by default; --yes
    # to actually delete; --include-data also removes ~/.trinity/.
    uin = subparsers.add_parser(
        "uninstall",
        help="Remove Trinity from MCP configs, Trinity.app, Chrome ext manifest, and bundled skill (idempotent). Pass --include-data to also delete ~/.trinity/.",
    )
    uin.add_argument(
        "--yes", action="store_true",
        help="Actually delete (default is dry-run that prints what would be removed).",
    )
    uin.add_argument(
        "--include-data", action="store_true",
        help="Also remove ~/.trinity/ (your prompt corpus + lens + scoreboard + council outcomes). Irreversible.",
    )
    uin.add_argument(
        "--include-hf-cache", action="store_true",
        help="Also remove the cached nomic-embed-text-v1.5 model from ~/.cache/huggingface/.",
    )
    uin.set_defaults(handler=handle_uninstall)


def handle_install_mcp(args):
    mcp_config = {
        "mcpServers": {
            "trinity-local": {
                "command": str(sys.executable),
                "args": ["-m", "trinity_local.main", "--mcp"]
            }
        }
    }

    written: list[str] = []
    if args.scope == "user":
        # Claude Code, Gemini CLI, Cursor: JSON config with `mcpServers` key.
        # 100-persona audit P16/P92 fix: Cursor was silently absent — it
        # supports MCP natively (same JSON shape as Claude Code) but the
        # install-mcp loop didn't write to its config path. Trinity-curious
        # Cursor users had no working install path despite the engine
        # already being compatible.
        json_targets = (
            Path.home() / ".claude.json",
            Path.home() / ".gemini.json",
            Path.home() / ".cursor" / "mcp.json",
        )
        for target in json_targets:
            if _write_json_mcp_config(target, mcp_config["mcpServers"]["trinity-local"]):
                written.append(str(target))
        # Codex CLI: TOML config with `[mcp_servers.<name>]` section.
        codex_path = Path.home() / ".codex" / "config.toml"
        if _write_codex_toml_mcp_config(codex_path, sys.executable):
            written.append(str(codex_path))
    else:
        # Project scope: both .mcp.json (Claude Code/Gemini default) AND
        # .cursor/mcp.json (Cursor's project-local convention).
        for target in (Path(".mcp.json"), Path(".cursor") / "mcp.json"):
            if _write_json_mcp_config(target, mcp_config["mcpServers"]["trinity-local"]):
                written.append(str(target))

    skill_status = _install_trinity_skill()
    if skill_status:
        written.append(skill_status)

    if written:
        print(f"✓ Installed Trinity MCP server to: {', '.join(written)}")
    else:
        print("No MCP configuration files were updated.")


def handle_install_app(args):
    launchpad_path = refresh_launchpad()
    destinations = None
    if args.destination:
        destinations = [Path(raw).expanduser() for raw in args.destination]
    app_paths = install_launchpad_shortcuts(
        launchpad_path=launchpad_path,
        destinations=destinations,
    )
    print(json.dumps({
        "launchpad_path": str(launchpad_path),
        "app_paths": [str(path) for path in app_paths],
    }, indent=2))


def _install_trinity_skill() -> str | None:
    """Drop the bundled /trinity skill into ~/.claude/skills/trinity/SKILL.md.

    Idempotent: writes when the target is missing OR matches the bundled
    content exactly (so re-runs are no-ops). If a user has edited the file,
    leaves it alone and reports the skip — protects user customizations
    across pip upgrades (council_d55953003bb29f9d Codex dissent).
    """
    target = Path.home() / ".claude" / "skills" / "trinity" / "SKILL.md"
    try:
        bundled = resources.files("trinity_local").joinpath("data/skills/trinity/SKILL.md").read_text(encoding="utf-8")
    except (FileNotFoundError, ModuleNotFoundError, AttributeError):
        # Source layout without package-data wired (editable install pre-pyproject change). Skip silently.
        return None

    if target.exists():
        try:
            current = target.read_text(encoding="utf-8")
        except OSError:
            return None
        if current == bundled:
            return None  # already up-to-date, no-op
        # User-modified — don't clobber.
        print(f"  skill: {target} has local edits, skipping (delete the file to refresh)")
        return None

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(bundled, encoding="utf-8")
    except OSError as exc:
        print(f"  skill install warning: {exc}")
        return None
    return f"{target} (skill)"


def _write_json_mcp_config(target: Path, server_config: dict) -> bool:
    """Merge Trinity's MCP server entry into a JSON config (Claude / Gemini / .mcp.json)."""
    existing: dict = {}
    if target.exists():
        try:
            existing = json.loads(target.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass

    servers = existing.setdefault("mcpServers", {})
    servers["trinity-local"] = server_config

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(existing, indent=2), encoding="utf-8")
        return True
    except OSError as exc:
        print(f"Error writing to {target}: {exc}")
        return False


# Match any TOML section that starts with `[mcp_servers.trinity-local`. This
# captures four shapes the user might have in their config:
#   [mcp_servers.trinity-local]            ← unquoted (what we write)
#   [mcp_servers."trinity-local"]          ← quoted (some toolchains generate this)
#   [mcp_servers.trinity-local.env]        ← nested subtable (env, args)
#   [mcp_servers."trinity-local".env]      ← quoted parent + nested
# The header pattern uses a non-capturing group with both quoted and
# unquoted parent forms, then optionally a `.<ident>` suffix. The body
# extends to the next TOML section header or end of file.
_CODEX_MCP_BLOCK_RE = re.compile(
    r"\n*\[mcp_servers\.(?:trinity-local|\"trinity-local\")(?:\.[^\]]+)?\][\s\S]*?(?=\n\[[^\n]+\]|\Z)",
)

# Inline-table form under `[mcp_servers]`:
#   trinity-local = { command = "...", args = [...] }
# or quoted-key form:
#   "trinity-local" = { command = "...", args = [...] }
# Match the whole assignment line (the inline-table value is on one line in
# canonical TOML; multi-line inline tables are rare and we leave them be).
_CODEX_INLINE_TRINITY_RE = re.compile(
    r'^\s*(?:trinity-local|"trinity-local")\s*=\s*\{[^\n]*\}\s*\n?',
    re.MULTILINE,
)


def _write_codex_toml_mcp_config(target: Path, python_executable: str) -> bool:
    """Add (or update) the Trinity MCP server in Codex CLI's TOML config.

    Codex reads `~/.codex/config.toml`. MCP servers are declared as
    `[mcp_servers.<name>]` sections. We don't depend on a TOML writer:
    a regex strips any pre-existing `[mcp_servers.trinity-local]` block, then
    we append a fresh one. Other config lines (model, project trust, plugins)
    are left untouched.
    """
    block = (
        "\n[mcp_servers.trinity-local]\n"
        f'command = "{python_executable}"\n'
        'args = ["-m", "trinity_local.main", "--mcp"]\n'
    )

    existing = ""
    if target.exists():
        try:
            existing = target.read_text(encoding="utf-8")
        except OSError as exc:
            print(f"Error reading {target}: {exc}")
            return False

    cleaned = _CODEX_MCP_BLOCK_RE.sub("", existing) if existing else ""
    # Also strip any inline-table form: `trinity-local = { command = ..., ... }`
    # nested under a `[mcp_servers]` parent. Some TOML toolchains emit this
    # shape instead of the dotted-key table. Without removing it, reinstall
    # leaves both definitions and codex picks one nondeterministically.
    cleaned = _CODEX_INLINE_TRINITY_RE.sub("", cleaned)
    cleaned = cleaned.rstrip() + "\n" if cleaned.strip() else ""
    new_content = cleaned + block

    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(new_content, encoding="utf-8")
        return True
    except OSError as exc:
        print(f"Error writing to {target}: {exc}")
        return False


def handle_install_hooks(args):
    target_dir = Path(args.path).expanduser().resolve()
    settings_path = target_dir / ".claude.json" # Claude Code uses this for hooks
    
    hooks_config = {
        "permissions": {
            "allow": ["Bash(trinity-local *)"]
        },
        "hooks": {
            "Stop": [
                {
                    "matcher": ".*",
                    "hooks": [
                        {
                            "type": "command",
                            "command": "trinity-local watch-once --quiet 2>/dev/null || true",
                            "async": True
                        }
                    ]
                }
            ]
        }
    }

    existing = {}
    if settings_path.exists():
        try:
            existing = json.loads(settings_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
    
    # Merge hooks
    existing_hooks = existing.setdefault("hooks", {})
    stop_hooks = existing_hooks.setdefault("Stop", [])
    
    # Check if already exists
    exists = any("trinity-local watch-once" in str(h.get("command", "")) for h in stop_hooks)
    if not exists:
        stop_hooks.append(hooks_config["hooks"]["Stop"][0])
        
        # Merge permissions
        perms = existing.setdefault("permissions", {})
        allow = perms.setdefault("allow", [])
        if "Bash(trinity-local *)" not in allow:
            allow.append("Bash(trinity-local *)")
            
        try:
            settings_path.write_text(json.dumps(existing, indent=2), encoding="utf-8")
            print(f"✓ Installed auto-ingest hooks to {settings_path}")
        except OSError as exc:
            print(f"Error writing to {settings_path}: {exc}")
    else:
        print(f"Hooks already present in {settings_path}")


def _native_messaging_dir() -> Path:
    """Chrome's per-user NativeMessagingHosts directory for the current OS."""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "Google" / "Chrome" / "NativeMessagingHosts"
    if sys.platform.startswith("linux"):
        return Path.home() / ".config" / "google-chrome" / "NativeMessagingHosts"
    raise SystemExit(
        f"install-extension: unsupported platform {sys.platform!r}. v1.6 ships macOS first; "
        "Linux works (same Native Messaging protocol) but path resolution is unverified."
    )


def handle_install_extension(args):
    import shutil

    extension_id = getattr(args, "extension_id", None)
    host_path = getattr(args, "host_path", None) or shutil.which("trinity-local-capture-host")

    if not host_path:
        print(
            "error: could not locate trinity-local-capture-host on PATH. "
            "Reinstall the wheel (pip install -e .) so the console script lands, "
            "or pass --host-path /full/path/to/trinity-local-capture-host."
        )
        return 1

    if not extension_id:
        print(
            "install-extension needs the Chrome-assigned extension ID.\n"
            "\n"
            "1. Open chrome://extensions in Chrome and enable Developer mode.\n"
            "2. Click 'Load unpacked' and select browser-extension/ in this repo.\n"
            "3. Copy the 32-character ID Chrome assigns to the extension.\n"
            "4. Rerun: trinity-local install-extension --extension-id <ID>\n"
            "\n"
            "(The ID gates which extension can invoke the local capture host. The host "
            "is otherwise unreachable.)"
        )
        return 0

    extension_id = extension_id.strip().lower()
    if not re.fullmatch(r"[a-p]{32}", extension_id):
        print(
            f"error: extension ID {extension_id!r} does not match Chrome's 32-char a-p format. "
            "Copy it from chrome://extensions next to the Trinity extension."
        )
        return 1

    manifest_dir = _native_messaging_dir()
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / "local.trinity.capture.json"

    manifest = {
        "name": "local.trinity.capture",
        "description": "Trinity local conversation capture",
        "path": str(host_path),
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{extension_id}/"],
    }
    manifest_path.write_text(json.dumps(manifest, indent=2))
    print(f"✓ Wrote {manifest_path}")
    print(f"  host: {host_path}")
    print(f"  extension: {extension_id}")
    print()
    print("Next: visit claude.ai (or chatgpt.com), send a message, then check")
    print("      ~/.trinity/conversations/<provider>/ for the captured turn.")
    return 0


def _remove_trinity_from_json_mcp_config(target: Path, plan: list[str], dry_run: bool) -> None:
    """Strip Trinity's entry from a JSON-shaped MCP config (Claude / Gemini /
    Cursor / .mcp.json). Idempotent — no-op when the file is absent or
    Trinity isn't in it."""
    if not target.exists():
        return
    try:
        existing = json.loads(target.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    servers = existing.get("mcpServers") or {}
    if "trinity-local" not in servers:
        return
    plan.append(f"remove trinity-local from {target}")
    if dry_run:
        return
    del servers["trinity-local"]
    if not servers:
        existing.pop("mcpServers", None)
    try:
        target.write_text(json.dumps(existing, indent=2), encoding="utf-8")
    except OSError as exc:
        print(f"  warn: could not write {target}: {exc}")


def _remove_trinity_from_codex_toml(target: Path, plan: list[str], dry_run: bool) -> None:
    """Strip the [mcp_servers.trinity-local] block + any nested subtables +
    inline-table form from Codex's TOML config. Uses the same regexes
    install-mcp uses for replacement, so the round-trip is symmetric."""
    if not target.exists():
        return
    try:
        content = target.read_text(encoding="utf-8")
    except OSError:
        return
    new = _CODEX_MCP_BLOCK_RE.sub("", content)
    new = _CODEX_INLINE_TRINITY_RE.sub("", new)
    if new == content:
        return
    plan.append(f"remove [mcp_servers.trinity-local] from {target}")
    if dry_run:
        return
    try:
        target.write_text(new, encoding="utf-8")
    except OSError as exc:
        print(f"  warn: could not write {target}: {exc}")


def _remove_trinity_app(plan: list[str], dry_run: bool) -> None:
    """Trinity.app may live in /Applications, ~/Applications, or ~/Desktop —
    install_launchpad_shortcuts writes wherever's writable."""
    for parent in (Path("/Applications"), Path.home() / "Applications", Path.home() / "Desktop"):
        app = parent / "Trinity.app"
        if app.exists():
            plan.append(f"remove {app}")
            if dry_run:
                continue
            try:
                import shutil
                shutil.rmtree(app, ignore_errors=True)
            except Exception as exc:
                print(f"  warn: could not remove {app}: {exc}")


def _remove_native_messaging_manifest(plan: list[str], dry_run: bool) -> None:
    """Drop Chrome's Native Messaging manifest so the v1.6 browser ext can
    no longer spawn the host. Safe regardless of whether the host was
    actually installed."""
    try:
        manifest = _native_messaging_dir() / "local.trinity.capture.json"
    except SystemExit:
        return  # unsupported platform — nothing to remove
    if manifest.exists():
        plan.append(f"remove {manifest}")
        if dry_run:
            return
        try:
            manifest.unlink()
        except OSError as exc:
            print(f"  warn: could not remove {manifest}: {exc}")


def _remove_trinity_skill(plan: list[str], dry_run: bool) -> None:
    """Remove the bundled /trinity skill. Preserves user edits — only
    deletes when the file matches the bundled contents exactly, same
    contract _install_trinity_skill uses on write."""
    target = Path.home() / ".claude" / "skills" / "trinity" / "SKILL.md"
    if not target.exists():
        return
    try:
        bundled = resources.files("trinity_local").joinpath("data/skills/trinity/SKILL.md").read_text(encoding="utf-8")
        current = target.read_text(encoding="utf-8")
    except (OSError, FileNotFoundError, ModuleNotFoundError, AttributeError):
        return
    if current != bundled:
        plan.append(f"skip {target} (locally edited; remove manually)")
        return
    plan.append(f"remove {target}")
    if dry_run:
        return
    try:
        target.unlink()
        parent = target.parent
        if not any(parent.iterdir()):
            parent.rmdir()
    except OSError as exc:
        print(f"  warn: could not remove {target}: {exc}")


def _remove_trinity_data(plan: list[str], dry_run: bool) -> None:
    """Remove ~/.trinity/ — the corpus + memories + scoreboard + council
    outcomes + cache. Destructive. Only fires when --include-data passed."""
    from ..config import trinity_home
    home = trinity_home()
    if not home.exists():
        return
    plan.append(f"remove {home} (your corpus, lens, scoreboard, council outcomes)")
    if dry_run:
        return
    try:
        import shutil
        shutil.rmtree(home, ignore_errors=True)
    except Exception as exc:
        print(f"  warn: could not remove {home}: {exc}")


def _remove_hf_cache(plan: list[str], dry_run: bool) -> None:
    """Remove just the nomic-embed-text-v1.5 model from the HuggingFace
    cache, not the whole HF cache (other projects share it). Only fires
    when --include-hf-cache passed."""
    hf_root = Path.home() / ".cache" / "huggingface" / "hub"
    if not hf_root.exists():
        return
    # The model path is models--nomic-ai--nomic-embed-text-v1.5
    nomic_dir = hf_root / "models--nomic-ai--nomic-embed-text-v1.5"
    if not nomic_dir.exists():
        return
    plan.append(f"remove {nomic_dir} (nomic embed model — first lens-build will re-download)")
    if dry_run:
        return
    try:
        import shutil
        shutil.rmtree(nomic_dir, ignore_errors=True)
    except Exception as exc:
        print(f"  warn: could not remove {nomic_dir}: {exc}")


def handle_uninstall(args) -> int:
    """Inverse of install-mcp + install-app + install-extension. Idempotent:
    safe to run on a system where some pieces were never installed."""
    dry_run = not getattr(args, "yes", False)
    plan: list[str] = []

    # Always: configs + .app + ext manifest + skill (the things install-* wrote).
    for target in (
        Path.home() / ".claude.json",
        Path.home() / ".gemini.json",
        Path.home() / ".cursor" / "mcp.json",
        Path(".mcp.json"),
        Path(".cursor") / "mcp.json",
    ):
        _remove_trinity_from_json_mcp_config(target, plan, dry_run)
    _remove_trinity_from_codex_toml(Path.home() / ".codex" / "config.toml", plan, dry_run)
    _remove_trinity_app(plan, dry_run)
    _remove_native_messaging_manifest(plan, dry_run)
    _remove_trinity_skill(plan, dry_run)

    # Opt-in destructive removals.
    if getattr(args, "include_data", False):
        _remove_trinity_data(plan, dry_run)
    if getattr(args, "include_hf_cache", False):
        _remove_hf_cache(plan, dry_run)

    if not plan:
        print("No Trinity install artifacts found. Nothing to remove.")
        return 0

    header = "Would remove (dry-run; pass --yes to actually delete):" if dry_run else "Removed:"
    print(header)
    for line in plan:
        print(f"  • {line}")

    if dry_run:
        print("")
        print("Re-run with --yes to actually delete.")
        if not getattr(args, "include_data", False):
            print("Add --include-data to also remove ~/.trinity/ (your corpus + memories).")
        if not getattr(args, "include_hf_cache", False):
            print("Add --include-hf-cache to also remove the nomic embed model.")
    return 0
