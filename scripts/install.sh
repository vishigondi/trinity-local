#!/usr/bin/env bash
# Trinity Local installer — curl|sh entry point.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/vishigondi/trinity-local/main/scripts/install.sh | bash
#   bash scripts/install.sh
#
# Idempotent: clones the repo if missing, updates if present. Writes thin
# shell wrappers to ~/.local/bin/ so `trinity-local <cmd>` works without
# pip-installing the wheel. Detects the harnesses you have (Claude Code,
# Codex CLI, Gemini CLI, Cursor) and registers Trinity's MCP server in
# each. Verifies with `trinity doctor`.
#
# Architecture ratified by council_37eca30b6e7010df (see
# docs/three-tier-architecture.md). Skill is primary; this script is the
# user-facing install path. No PyPI, no npm — just a git clone + a
# couple of shell wrappers.

set -euo pipefail

TRINITY_REPO_URL="${TRINITY_REPO_URL:-https://github.com/vishigondi/trinity-local}"
TRINITY_SKILL_DIR="${TRINITY_SKILL_DIR:-$HOME/.claude/skills/trinity}"
TRINITY_BIN_DIR="${TRINITY_BIN_DIR:-$HOME/.local/bin}"
TRINITY_BRANCH="${TRINITY_BRANCH:-main}"

# ─── Output helpers ────────────────────────────────────────────────

# Colors only when stdout is a real terminal — clean output under
# curl|sh OR redirection.
if [[ -t 1 ]]; then
  C_GREEN=$'\033[32m'; C_YELLOW=$'\033[33m'; C_RED=$'\033[31m'
  C_DIM=$'\033[2m'; C_BOLD=$'\033[1m'; C_RESET=$'\033[0m'
else
  C_GREEN=''; C_YELLOW=''; C_RED=''; C_DIM=''; C_BOLD=''; C_RESET=''
fi

step()  { printf "%s→%s %s\n" "$C_BOLD" "$C_RESET" "$1"; }
ok()    { printf "  %s✓%s %s\n" "$C_GREEN" "$C_RESET" "$1"; }
warn()  { printf "  %s⚠%s %s\n" "$C_YELLOW" "$C_RESET" "$1" >&2; }
fail()  { printf "  %s✗%s %s\n" "$C_RED" "$C_RESET" "$1" >&2; exit 1; }

# ─── 1. Prerequisites ──────────────────────────────────────────────

step "Checking prerequisites"

command -v git >/dev/null 2>&1 || fail "git not found. Install git and re-run."
ok "git $(git --version | awk '{print $3}')"

# Trinity needs Python 3.10+. Most polyharness users have it (Claude Code
# itself needs Node + Python for tools; Codex CLI needs Node). If missing,
# tell them; don't try to install Python ourselves — the system Python
# story is too varied (pyenv, asdf, system, brew, uv, mise).
PYTHON_BIN=""
for candidate in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$candidate" >/dev/null 2>&1; then
    PY_VER=$("$candidate" -c 'import sys; print(f"{sys.version_info[0]}.{sys.version_info[1]}")' 2>/dev/null || echo "0.0")
    PY_MAJOR=${PY_VER%%.*}
    PY_MINOR=${PY_VER##*.}
    if [[ "$PY_MAJOR" == "3" ]] && (( PY_MINOR >= 10 )); then
      PYTHON_BIN="$candidate"
      ok "$candidate ($PY_VER)"
      break
    fi
  fi
done
if [[ -z "$PYTHON_BIN" ]]; then
  fail "Python 3.10+ not found. Install Python 3.10 or newer and re-run.
       macOS: brew install python@3.12   (or use pyenv / uv / mise)
       Linux: apt install python3.12      (or your distro's equivalent)"
fi

# ─── 2. Clone or update the repo ───────────────────────────────────

step "Installing skill to $TRINITY_SKILL_DIR"

mkdir -p "$(dirname "$TRINITY_SKILL_DIR")"

if [[ -d "$TRINITY_SKILL_DIR/.git" ]]; then
  # Already cloned — fetch + fast-forward.
  cd "$TRINITY_SKILL_DIR"
  if git remote get-url origin >/dev/null 2>&1; then
    REMOTE_URL=$(git remote get-url origin)
    if [[ "$REMOTE_URL" != "$TRINITY_REPO_URL" ]] \
        && [[ "$REMOTE_URL" != "${TRINITY_REPO_URL}.git" ]]; then
      warn "Existing checkout has remote: $REMOTE_URL"
      warn "Expected:                       $TRINITY_REPO_URL"
      warn "Skipping git update (preserving user's customizations)."
    else
      git fetch --quiet origin "$TRINITY_BRANCH"
      BEHIND=$(git rev-list --count "HEAD..origin/$TRINITY_BRANCH")
      if (( BEHIND > 0 )); then
        git merge --quiet --ff-only "origin/$TRINITY_BRANCH"
        ok "Updated ($BEHIND new commits)"
      else
        ok "Already up to date"
      fi
    fi
  else
    warn "Existing checkout has no 'origin' remote; skipping update"
  fi
else
  # First-time clone — single shallow clone for fast install. Use the
  # full history if the user wants `git log` exploration; default to
  # depth 1 to keep curl|sh installs snappy.
  git clone --quiet --depth 1 --branch "$TRINITY_BRANCH" \
      "$TRINITY_REPO_URL" "$TRINITY_SKILL_DIR"
  ok "Cloned to $TRINITY_SKILL_DIR"
fi

# ─── 3. Install CLI wrappers in ~/.local/bin/ ──────────────────────

step "Installing CLI wrappers to $TRINITY_BIN_DIR"

mkdir -p "$TRINITY_BIN_DIR"

# Write the trinity-local wrapper. Stable file — points at the skill
# directory via env var so the wrapper survives the user moving the
# skill if they want to. The resolved Python binary is baked in so the
# wrapper doesn't drift if the user later installs a stale `python3`
# symlink ahead of the one we validated.
cat > "$TRINITY_BIN_DIR/trinity-local" <<WRAPPER_EOF
#!/usr/bin/env bash
# Trinity Local CLI wrapper — installed by scripts/install.sh.
# Resolves to the cloned skill repo via \$TRINITY_SKILL_DIR (default
# ~/.claude/skills/trinity/).
TRINITY_SKILL_DIR="\${TRINITY_SKILL_DIR:-\$HOME/.claude/skills/trinity}"
if [[ ! -d "\$TRINITY_SKILL_DIR/src/trinity_local" ]]; then
  echo "error: Trinity skill not found at \$TRINITY_SKILL_DIR" >&2
  echo "Re-install: curl -fsSL https://raw.githubusercontent.com/vishigondi/trinity-local/main/scripts/install.sh | bash" >&2
  exit 1
fi
export PYTHONPATH="\$TRINITY_SKILL_DIR/src:\${PYTHONPATH:-}"
exec "$PYTHON_BIN" -m trinity_local.main "\$@"
WRAPPER_EOF
chmod +x "$TRINITY_BIN_DIR/trinity-local"
ok "trinity-local"

# Native Messaging host wrapper — same pattern, points at capture_host.py.
cat > "$TRINITY_BIN_DIR/trinity-local-capture-host" <<CAPTURE_EOF
#!/usr/bin/env bash
# Trinity Local Native Messaging host wrapper — installed by scripts/
# install.sh. Chrome / Edge talk to this via stdio.
TRINITY_SKILL_DIR="\${TRINITY_SKILL_DIR:-\$HOME/.claude/skills/trinity}"
export PYTHONPATH="\$TRINITY_SKILL_DIR/src:\${PYTHONPATH:-}"
exec "$PYTHON_BIN" "\$TRINITY_SKILL_DIR/src/trinity_local/capture_host.py" "\$@"
CAPTURE_EOF
chmod +x "$TRINITY_BIN_DIR/trinity-local-capture-host"
ok "trinity-local-capture-host"

# Sanity-check PATH. If ~/.local/bin isn't on PATH, the user has to fix
# their shell config — we surface this loudly rather than silently
# failing later.
if ! echo "$PATH" | tr ':' '\n' | grep -qx "$TRINITY_BIN_DIR"; then
  warn "$TRINITY_BIN_DIR is not on your PATH."
  warn "Add this line to your shell config (~/.zshrc, ~/.bashrc, etc.):"
  warn "  export PATH=\"\$HOME/.local/bin:\$PATH\""
  warn "Then re-open your terminal."
fi

# ─── 3.5. Install Python runtime deps (Pillow, mcp) ────────────────

# Trinity's runtime deps are declared in pyproject.toml: Pillow>=10 (for
# me-card PNG rendering, loaded lazily) and mcp>=1.0 (for the MCP server
# the harness spawns). We don't pip-install trinity-local itself — the
# wrapper points at the cloned repo via PYTHONPATH. But the runtime deps
# still have to be available to the system python; without them,
# doctor's first run flags two failures the user has to fix manually.
#
# --user installs into ~/.local (or the venv if active) without touching
# system site-packages. If pip is missing we surface a warning rather
# than failing: dispatch + lens-build don't need Pillow/mcp; only
# me-card and the MCP server do.

step "Installing Python runtime deps"

if "$PYTHON_BIN" -m pip --version >/dev/null 2>&1; then
  if "$PYTHON_BIN" -m pip install --quiet --user --upgrade \
       'Pillow>=10' 'mcp>=1.0' 2>/dev/null; then
    ok "Pillow + mcp installed"
  else
    warn "pip install reported issues (Pillow / mcp) — see 'trinity-local doctor'"
  fi
else
  warn "pip not available for $PYTHON_BIN — install pip and re-run, or:"
  warn "  $PYTHON_BIN -m ensurepip --user && $PYTHON_BIN -m pip install --user 'Pillow>=10' 'mcp>=1.0'"
fi

# ─── 4. Register MCP server in installed harnesses ─────────────────

step "Registering MCP server"

# Delegate to install-mcp, which knows how to detect Claude Code /
# Codex CLI / Gemini CLI / Cursor configs and write the right entries.
if "$TRINITY_BIN_DIR/trinity-local" install-mcp 2>&1 | sed 's/^/  /'; then
  ok "MCP server registered"
else
  warn "install-mcp reported issues — run 'trinity-local install-mcp' to retry"
fi

# ─── 5. Verify ─────────────────────────────────────────────────────

step "Running doctor"
"$TRINITY_BIN_DIR/trinity-local" doctor 2>&1 | sed 's/^/  /' || \
  warn "doctor reported issues — fix what it surfaces, then 'trinity-local doctor' again"

# ─── 6. Done ───────────────────────────────────────────────────────

echo ""
printf "%sTrinity Local installed.%s\n" "$C_BOLD$C_GREEN" "$C_RESET"
echo ""
echo "Type /trinity in Claude Code to start. Or run 'trinity-local doctor'"
echo "to verify. Updates: 'trinity-local update' pulls the latest."
echo ""
echo "Skill:  $TRINITY_SKILL_DIR"
echo "CLI:    $TRINITY_BIN_DIR/trinity-local"
echo "Docs:   $TRINITY_SKILL_DIR/docs/INSTALL-skill.md"
