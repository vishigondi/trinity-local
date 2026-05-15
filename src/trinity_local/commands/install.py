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
    imp = subparsers.add_parser("install-mcp", help="Install Trinity as an MCP server in Claude Code, Gemini CLI, and Codex CLI")
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
        # Claude Code + Gemini CLI: JSON config with `mcpServers` key.
        for target in (Path.home() / ".claude.json", Path.home() / ".gemini.json"):
            if _write_json_mcp_config(target, mcp_config["mcpServers"]["trinity-local"]):
                written.append(str(target))
        # Codex CLI: TOML config with `[mcp_servers.<name>]` section.
        codex_path = Path.home() / ".codex" / "config.toml"
        if _write_codex_toml_mcp_config(codex_path, sys.executable):
            written.append(str(codex_path))
    else:
        target = Path(".mcp.json")
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
