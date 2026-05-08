"""Handlers for install-mcp, install-hooks."""
from __future__ import annotations

import json
import os
import re
import sys
from importlib import resources
from pathlib import Path

from ..runtime_env import project_venv_root


def register(subparsers):
    imp = subparsers.add_parser("install-mcp", help="Install Trinity as an MCP server in Claude Code, Gemini CLI, and Codex CLI")
    imp.add_argument("--scope", choices=["user", "project"], default="user", help="User-wide or project-specific installation")
    imp.set_defaults(handler=handle_install_mcp)

    ihp = subparsers.add_parser("install-hooks", help="Install Trinity Stop hook (calls watch-once after each Claude turn)")
    ihp.add_argument("--path", default=".", help="Project directory to install hooks into")
    ihp.set_defaults(handler=handle_install_hooks)


def handle_install_mcp(args):
    venv_root = project_venv_root()
    trinity_bin = venv_root / "bin" / "trinity-local"

    if not trinity_bin.exists():
        # Fallback if not installed as script
        trinity_bin_str = f"{sys.executable} -m trinity_local.main"
    else:
        trinity_bin_str = str(trinity_bin)

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
