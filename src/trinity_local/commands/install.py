"""Handlers for install-mcp + install-hooks + install-launcher + install-extension + uninstall."""
from __future__ import annotations

import json
import re
import sys
from importlib import resources
from pathlib import Path


def register(subparsers):
    imp = subparsers.add_parser("install-mcp", help="Install Trinity as an MCP server in Claude Code, Gemini CLI, Codex CLI, and Cursor")
    imp.add_argument("--scope", choices=["user", "project"], default="user", help="User-wide or project-specific installation")
    imp.set_defaults(handler=handle_install_mcp)

    ihp = subparsers.add_parser("install-hooks", help="Install Trinity Stop hook (calls `trinity-local ingest-recent --deadline 1.0` after each Claude turn for tool-triggered incremental ingest)")
    ihp.add_argument("--path", default=".", help="Project directory to install hooks into")
    ihp.set_defaults(handler=handle_install_hooks)

    iep = subparsers.add_parser(
        "install-extension",
        help="Write the Native Messaging manifest so the Trinity browser extension can spawn the local capture host (Chrome + Edge by default; Firefox via --firefox)",
    )
    iep.add_argument(
        "--extension-id",
        help="Chrome-assigned extension ID (the long hash from chrome://extensions). Required on first install; cached afterwards.",
    )
    iep.add_argument(
        "--host-path",
        help="Path to the trinity-local-capture-host binary. Defaults to the one resolved via shutil.which().",
    )
    iep.add_argument(
        "--browsers",
        nargs="+",
        choices=["chrome", "edge"],
        default=None,
        help="Chromium browsers to install the manifest for. Default: chrome edge (covers ~85%% of audience).",
    )
    iep.add_argument(
        "--firefox",
        action="store_true",
        help="Also write a Firefox-format manifest (uses allowed_extensions instead of allowed_origins; ID must be hand-edited).",
    )
    iep.set_defaults(handler=handle_install_extension)

    # Cross-platform desktop launcher (Linux .desktop / Windows .url
    # shortcut). The macOS path is intentionally absent — the Chrome
    # extension is now the canonical "open the launchpad" entry point
    # on Mac (and works as a fallback for Linux/Windows users who
    # install the extension too).
    ilp = subparsers.add_parser(
        "install-launcher",
        help="Install a desktop launcher pointing at the local Trinity launchpad (Linux .desktop / Windows Start Menu .url; macOS users open the launchpad via the Chrome extension).",
    )
    ilp.add_argument(
        "--destination",
        action="append",
        default=None,
        help="Directory to install into; repeat for multiple. Defaults per platform.",
    )
    ilp.set_defaults(handler=handle_install_launcher)

    # uninstall — inverse of install-mcp + install-extension + install-launcher.
    # The "own your data" wedge cuts the wrong way if removing Trinity
    # requires hand-editing 4 MCP configs + the Chrome manifest + the
    # skill file + ~/.trinity/. Dry-run by default; --yes to actually
    # delete; --include-data also removes ~/.trinity/.
    uin = subparsers.add_parser(
        "uninstall",
        help="Remove Trinity from MCP configs, Chrome ext manifest, desktop launcher, and bundled skill (idempotent). Pass --include-data to also delete ~/.trinity/.",
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
            # Gemini CLI / Antigravity (`agy`) both read MCP servers from
            # ~/.gemini/settings.json's `mcpServers` key — NOT the top-level
            # ~/.gemini.json that Trinity used to write to. The flat file
            # was a silent no-op for the interactive `gemini`/`agy` session
            # path (council dispatch via `-p` doesn't read MCP config, so
            # the bug only bit users who tried to call mcp__trinity-local__*
            # from inside the Gemini CLI agent).
            Path.home() / ".gemini" / "settings.json",
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
        # 100-persona audit P01/C4: restart-prompt — running harnesses
        # cache MCP tool lists at connect time. Without this line, users
        # type /trinity or hit run_council in the same session and see
        # nothing happen.
        print(
            "\nNext: restart Claude Code / Codex / Gemini CLI / Cursor to pick "
            "up the new tools.\n"
            "Then verify with:  trinity-local status   (or type /trinity in "
            "Claude Code)\n"
            "On first MCP spawn, Trinity auto-scans ~/.claude, ~/.codex, "
            "~/.gemini, cowork in the background — your first council is "
            "already personalized."
        )
    else:
        print("No MCP configuration files were updated.")


def _install_linux_desktop_entry(launchpad_path: Path,
                                 destination: Path | None = None) -> Path:
    """Write a freedesktop.org `.desktop` entry pointing at the launchpad.

    Default location: ~/.local/share/applications/ (the XDG per-user app
    directory). Most distros auto-pick this up so the entry appears in
    GNOME/KDE/etc. application launchers without further action.

    The Exec line uses `xdg-open` so the user's default browser opens
    the file:// URL. `xdg-open` is shipped by every major distro; we
    don't try to be clever about Chrome-vs-Firefox here.
    """
    if destination is None:
        destination = Path.home() / ".local" / "share" / "applications"
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / "trinity-local.desktop"
    uri = launchpad_path.expanduser().resolve().as_uri()
    desktop_entry = "\n".join([
        "[Desktop Entry]",
        "Type=Application",
        "Name=Trinity Local",
        "GenericName=Your taste, ported",
        "Comment=Open the Trinity launchpad in your default browser",
        f"Exec=xdg-open {uri}",
        "Terminal=false",
        "Categories=Development;Utility;",
        "Keywords=Trinity;council;LLM;Claude;Codex;Gemini;",
        "",
    ])
    target.write_text(desktop_entry)
    target.chmod(0o755)
    return target


def _install_macos_webloc(launchpad_path: Path,
                          destination: Path | None = None) -> Path:
    """Write a macOS Internet location (.webloc) pointing at the launchpad.

    `.webloc` is a tiny XML plist; double-clicking it in Finder opens the
    URL in the user's default browser. Works for file:// URIs without
    any signing or osacompile gymnastics — the cross-platform analog to
    the Linux .desktop entry and the Windows .url shortcut.

    Default location: ~/Applications (per-user app directory; surfaces in
    Spotlight + Launchpad). Falls back to /Applications-equivalent path
    only when the caller passes an explicit destination.
    """
    if destination is None:
        destination = Path.home() / "Applications"
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / "Trinity Local.webloc"
    uri = launchpad_path.expanduser().resolve().as_uri()
    webloc = "\n".join([
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">',
        '<plist version="1.0">',
        '<dict>',
        '\t<key>URL</key>',
        f'\t<string>{uri}</string>',
        '</dict>',
        '</plist>',
        '',
    ])
    target.write_text(webloc, encoding="utf-8")
    return target


def _install_windows_url_shortcut(launchpad_path: Path,
                                  destination: Path | None = None) -> Path:
    """Write a Windows Internet Shortcut (.url) to the Start Menu.

    The .url format is plain INI; writing it from Python avoids the
    PowerShell COM-object dance for .lnk files. Windows treats .url
    entries in the Start Menu folder as first-class launchable items
    and respects the user's default browser when opening file:// URLs.
    """
    from os import environ
    if destination is None:
        appdata = environ.get("APPDATA")
        if not appdata:
            destination = Path.home() / "AppData" / "Roaming"
        else:
            destination = Path(appdata)
        destination = destination / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    destination.mkdir(parents=True, exist_ok=True)
    target = destination / "Trinity Local.url"
    uri = launchpad_path.expanduser().resolve().as_uri()
    url_entry = "\r\n".join([
        "[InternetShortcut]",
        f"URL={uri}",
        # IconIndex / IconFile would point at an icon; the launchpad
        # path itself is a fine fallback (Windows falls back to the
        # default browser icon when IconFile is absent).
        "",
    ])
    target.write_text(url_entry)
    return target


def handle_install_launcher(args) -> int:
    """Cross-platform desktop launcher installer (macOS + Linux + Windows).

    Dispatches by platform:
      macOS   → ~/Applications/Trinity Local.webloc
      Linux   → ~/.local/share/applications/trinity-local.desktop
      Windows → Start Menu/Programs/Trinity Local.url
      Other   → loud failure with a hint pointing at the extension.

    The Chrome extension remains the canonical launchpad host (works on
    every OS, gets you the Native Messaging dispatch); the launcher just
    writes a desktop shortcut that opens the file:// launchpad in the
    user's default browser for users who don't want the extension.
    """
    from ..refresh import refresh_launchpad
    launchpad_path = refresh_launchpad()

    destinations = None
    if getattr(args, "destination", None):
        destinations = [Path(raw).expanduser() for raw in args.destination]

    paths: list[Path] = []
    try:
        if sys.platform == "darwin":
            targets = destinations or [None]
            for dest in targets:
                paths.append(_install_macos_webloc(launchpad_path, dest))
        elif sys.platform.startswith("linux"):
            targets = destinations or [None]
            for dest in targets:
                paths.append(_install_linux_desktop_entry(launchpad_path, dest))
        elif sys.platform.startswith("win") or sys.platform == "cygwin":
            targets = destinations or [None]
            for dest in targets:
                paths.append(_install_windows_url_shortcut(launchpad_path, dest))
        else:
            print(
                f"install-launcher: no desktop launcher for sys.platform={sys.platform!r}.\n"
                "Use `trinity-local serve` to open the launchpad at "
                "http://localhost:8765, or run `trinity-local portal-html "
                "--open-browser` to open the file:// version.",
                file=sys.stderr,
            )
            return 1
    except OSError as exc:
        print(f"install-launcher: failed to write desktop entry: {exc}",
              file=sys.stderr)
        return 1

    print(json.dumps({
        "platform": sys.platform,
        "launchpad_path": str(launchpad_path),
        "launcher_paths": [str(p) for p in paths],
    }, indent=2))
    return 0


def _install_trinity_skill() -> str | None:
    """Drop the bundled /trinity skill into ~/.claude/skills/trinity/SKILL.md.

    Path note (2026-05-19+): on installs where scripts/install.sh ran the
    repo clone, ~/.claude/skills/trinity/ is a symlink to ~/.trinity/code/
    (the canonical post-pivot location); the file written here resolves
    through the symlink. On pip-install-only installs (no curl-bash), the
    legacy path is the canonical write target — Claude Code's skill loader
    reads from ~/.claude/skills/<name>/SKILL.md regardless. We write to
    the legacy path because it works in both shapes.

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
                            "command": "trinity-local ingest-recent --deadline 1.0 2>/dev/null || true",
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
    
    # Detect existing Trinity hook + clean up the retired watch-once
    # variant. Older Trinity versions installed `trinity-local watch-once
    # --quiet ...`; the watch-once CLI was retired 2026-05-17 (commit
    # 07ea7da). On re-install, strip the stale hook so the new
    # ingest-recent shape lands cleanly.
    stale_idx = [
        i for i, h in enumerate(stop_hooks)
        if "trinity-local watch-once" in str(h.get("command", ""))
    ]
    for i in reversed(stale_idx):
        stop_hooks.pop(i)

    exists = any(
        "trinity-local ingest-recent" in str(h.get("command", ""))
        for h in stop_hooks
    )
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


def _native_messaging_dirs(browsers: list[str]) -> list[tuple[str, Path]]:
    """Per-browser, per-OS NativeMessagingHosts directories.

    Phase 2 of the Chrome-extension transition adds Edge support and a
    Windows path; Firefox uses a different manifest schema so is
    handled by _firefox_manifest_dir() separately.

    Returns [(browser_label, dir_path), ...] for the requested browsers
    on the current OS. Unsupported (browser, OS) combinations are
    silently omitted — caller reports which targets actually wrote.
    """
    out: list[tuple[str, Path]] = []
    home = Path.home()
    for b in browsers:
        if b == "chrome":
            if sys.platform == "darwin":
                out.append(("chrome", home / "Library" / "Application Support"
                            / "Google" / "Chrome" / "NativeMessagingHosts"))
            elif sys.platform.startswith("linux"):
                out.append(("chrome", home / ".config" / "google-chrome"
                            / "NativeMessagingHosts"))
            elif sys.platform == "win32":
                # Windows uses HKCU registry, not a filesystem path —
                # callers detect win32 and dispatch to the registry
                # writer. We surface this as a sentinel "registry:" path
                # rather than skipping silently.
                out.append(("chrome", Path("registry:HKCU\\Software\\Google"
                            "\\Chrome\\NativeMessagingHosts")))
        elif b == "edge":
            # Edge mirrors Chrome's NM protocol verbatim (Chromium fork).
            # Same manifest schema; different per-user dir.
            if sys.platform == "darwin":
                out.append(("edge", home / "Library" / "Application Support"
                            / "Microsoft Edge" / "NativeMessagingHosts"))
            elif sys.platform.startswith("linux"):
                out.append(("edge", home / ".config" / "microsoft-edge"
                            / "NativeMessagingHosts"))
            elif sys.platform == "win32":
                out.append(("edge", Path("registry:HKCU\\Software\\Microsoft"
                            "\\Edge\\NativeMessagingHosts")))
        # Firefox handled by _firefox_manifest_dir() — different schema.
    return out


def _firefox_manifest_dirs() -> list[Path]:
    """Firefox per-user NativeMessagingHosts dirs (manifest schema differs;
    uses ``allowed_extensions`` instead of ``allowed_origins``)."""
    home = Path.home()
    if sys.platform == "darwin":
        return [home / "Library" / "Application Support" / "Mozilla"
                / "NativeMessagingHosts"]
    if sys.platform.startswith("linux"):
        return [home / ".mozilla" / "native-messaging-hosts"]
    if sys.platform == "win32":
        return [Path("registry:HKCU\\Software\\Mozilla\\NativeMessagingHosts")]
    return []


def _write_windows_nm_registry(reg_path_sentinel: Path, host_name: str,
                                manifest_path: Path) -> bool:
    """On Windows, the NM host is registered via a registry value pointing
    at the manifest JSON on disk. We still write the JSON to a stable
    AppData path; the registry just points there.

    No-ops on non-Windows (caller already checks but this is defensive).
    Returns True on success.
    """
    if sys.platform != "win32":
        return False
    try:
        import winreg  # stdlib on Windows; absent elsewhere
    except ImportError:
        return False
    sub = str(reg_path_sentinel).removeprefix("registry:HKCU\\")
    # HKCU is the assumed root (we only write per-user). Path string
    # is the rest. winreg.OpenKey + SetValueEx.
    try:
        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER,
                                 f"{sub}\\{host_name}") as key:
            winreg.SetValueEx(key, "", 0, winreg.REG_SZ, str(manifest_path))
        return True
    except OSError:
        return False


def _native_messaging_dir() -> Path:
    """DEPRECATED: pre-Phase-2 single-Chrome path lookup. Kept for any
    external callers; new code uses _native_messaging_dirs(browsers)."""
    dirs = _native_messaging_dirs(["chrome"])
    if not dirs:
        raise SystemExit(
            f"install-extension: unsupported platform {sys.platform!r}."
        )
    return dirs[0][1]


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

    # Phase 2 (extension transition): write the manifest to every
    # browser the user requested. Default: chrome + edge (covers ~85%
    # of audience per the locked architectural decision). Firefox uses
    # a different schema (allowed_extensions vs allowed_origins) and
    # is opt-in via --firefox.
    browsers = getattr(args, "browsers", None) or ["chrome", "edge"]
    include_firefox = getattr(args, "firefox", False)

    chromium_manifest = {
        "name": "local.trinity.capture",
        "description": "Trinity local conversation capture",
        "path": str(host_path),
        "type": "stdio",
        "allowed_origins": [f"chrome-extension://{extension_id}/"],
    }
    written: list[str] = []
    for browser_label, dir_path in _native_messaging_dirs(browsers):
        if str(dir_path).startswith("registry:"):
            # Windows path — write manifest to %APPDATA% AND set
            # the registry pointer to it.
            from os import environ
            appdata = Path(environ.get("APPDATA",
                                       Path.home() / "AppData" / "Roaming"))
            manifest_path = (appdata / "trinity-local" /
                             f"local.trinity.capture.{browser_label}.json")
            manifest_path.parent.mkdir(parents=True, exist_ok=True)
            manifest_path.write_text(json.dumps(chromium_manifest, indent=2))
            if _write_windows_nm_registry(dir_path, "local.trinity.capture",
                                           manifest_path):
                written.append(f"{browser_label} (Windows registry → {manifest_path})")
            else:
                print(f"  warn: could not write {browser_label} Windows registry — "
                      f"manifest dropped at {manifest_path} but Chrome won't find it")
            continue
        try:
            dir_path.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            print(f"  warn: could not create {browser_label} NM dir {dir_path}: {exc}")
            continue
        manifest_path = dir_path / "local.trinity.capture.json"
        try:
            manifest_path.write_text(json.dumps(chromium_manifest, indent=2))
            written.append(f"{browser_label}: {manifest_path}")
        except OSError as exc:
            print(f"  warn: could not write {browser_label} manifest at "
                  f"{manifest_path}: {exc}")

    if include_firefox:
        # Firefox manifest schema diverges: allowed_extensions (a list of
        # add-on IDs like "trinity@local.example") instead of
        # allowed_origins. The extension_id format also differs — for
        # AMO-published extensions it's an email-like ID, for unsigned
        # dev builds it's the manifest applications.gecko.id field.
        # For v1.6 we just write the manifest with a placeholder; the
        # caller can hand-edit allowed_extensions once they have the
        # Firefox-assigned ID.
        firefox_manifest = {
            "name": "local.trinity.capture",
            "description": "Trinity local conversation capture",
            "path": str(host_path),
            "type": "stdio",
            "allowed_extensions": [f"trinity-local@{extension_id[:8]}.example"],
        }
        for dir_path in _firefox_manifest_dirs():
            if str(dir_path).startswith("registry:"):
                # Windows Firefox also via registry — defer for now.
                print(f"  warn: Firefox on Windows registry not yet supported")
                continue
            try:
                dir_path.mkdir(parents=True, exist_ok=True)
                manifest_path = dir_path / "local.trinity.capture.json"
                manifest_path.write_text(json.dumps(firefox_manifest, indent=2))
                written.append(f"firefox: {manifest_path}")
            except OSError as exc:
                print(f"  warn: Firefox manifest write failed at "
                      f"{dir_path}: {exc}")

    if not written:
        print(
            f"error: no browser manifests written. Platform "
            f"{sys.platform!r} may be unsupported, or requested "
            f"browsers ({browsers}) aren't installed in standard "
            f"locations on this OS."
        )
        return 1

    # Phase 4: persist the extension ID for the file:// launchpad. The
    # launchpad needs the ID to call chrome.runtime.sendMessage; without it,
    # tier-1 dispatch is silently dead. Settings file is the bridge between
    # install-extension (writes) and launchpad_data._browser_extension (reads).
    from .. import state_paths as _sp
    settings_path = _sp.telemetry_settings_dir() / "extension.json"
    settings_payload = {
        "extension_id": extension_id,
        "host_path": str(host_path),
        "browsers": list(written),
    }
    try:
        settings_path.write_text(json.dumps(settings_payload, indent=2))
    except OSError as exc:
        print(f"  warn: could not persist extension ID to {settings_path}: {exc}")

    print(f"✓ Wrote {len(written)} manifest(s):")
    for entry in written:
        print(f"    {entry}")
    print(f"  host: {host_path}")
    print(f"  extension: {extension_id}")
    print()
    print("Next: visit claude.ai (or chatgpt.com), send a message, then check")
    print("      ~/.trinity/conversations/<provider>/ for the captured turn.")
    print("Or click any launchpad button to dispatch a CLI command via the")
    print("extension (Phase 1 action-dispatch path).")
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
    """Inverse of install-mcp + install-extension + install-launcher.
    Idempotent: safe to run on a system where some pieces were never
    installed."""
    dry_run = not getattr(args, "yes", False)
    plan: list[str] = []

    # Always: configs + ext manifest + skill (the things install-* wrote).
    for target in (
        Path.home() / ".claude.json",
        # Current canonical path agy/gemini read from.
        Path.home() / ".gemini" / "settings.json",
        # Legacy path Trinity wrote to before the fix — clean up on
        # uninstall so reinstall doesn't re-orphan it.
        Path.home() / ".gemini.json",
        Path.home() / ".cursor" / "mcp.json",
        Path(".mcp.json"),
        Path(".cursor") / "mcp.json",
    ):
        _remove_trinity_from_json_mcp_config(target, plan, dry_run)
    _remove_trinity_from_codex_toml(Path.home() / ".codex" / "config.toml", plan, dry_run)
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
