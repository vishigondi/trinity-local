#!/bin/zsh
# ───────────────────────────────────────────────────────────
#  Trinity Local — Uninstall Script
#
#  Usage:
#    ./uninstall.sh [minimal|complete]
#
#  Modes:
#    minimal (default)  - Remove apps, wrapper, daemon (keep state)
#    complete           - Remove everything including state directory
#
# ───────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# Colors
RED='\033[0;31m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
DIM='\033[2m'
BOLD='\033[1m'
NC='\033[0m'

step() { echo "\n${CYAN}▸${NC} ${BOLD}$1${NC}"; }
ok()   { echo "  ${RED}✓${NC} $1"; }
warn() { echo "  ${YELLOW}⚠${NC} $1"; }

MODE="${1:-minimal}"

if [[ "$MODE" != "minimal" && "$MODE" != "complete" ]]; then
    echo "Usage: $0 [minimal|complete]"
    echo ""
    echo "  minimal (default) - Remove apps, wrapper, daemon (keep state at ~/.trinity)"
    echo "  complete          - Remove everything including ~/.trinity state"
    exit 1
fi

echo ""
echo "${BOLD}┌─────────────────────────────────────────┐${NC}"
echo "${BOLD}│     Trinity Local — Uninstall ($MODE)      │${NC}"
echo "${BOLD}└─────────────────────────────────────────┘${NC}"
echo ""

if [[ "$MODE" == "complete" ]]; then
    echo "${YELLOW}⚠  This will remove ALL Trinity Local data including:${NC}"
    echo "   - ~/.trinity/ (state, cache, analytics)"
    echo "   - Desktop and Applications shortcuts"
    echo "   - ~/.trinity/bin/trinity-dispatch"
    echo "   - launchd daemon if installed"
    echo ""
    read -p "$(echo ${BOLD}Continue? [y/N]:${NC} )" -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        echo "Cancelled."
        exit 0
    fi
fi

# ── 1. Uninstall daemon ──────────────────────────────────
step "Checking for daemon"

DAEMON_LABEL="com.trinity.local.watch"
DAEMON_PLIST="$HOME/Library/LaunchAgents/$DAEMON_LABEL.plist"

if [ -f "$DAEMON_PLIST" ]; then
    launchctl unload "$DAEMON_PLIST" 2>/dev/null || true
    rm -f "$DAEMON_PLIST"
    ok "Daemon uninstalled"
else
    echo "  ${DIM}– No daemon installed${NC}"
fi

# ── 2. Remove Trinity.app ────────────────────────────────
step "Removing Trinity.app shortcuts"

for path in "$HOME/Desktop/Trinity.app" "$HOME/Applications/Trinity.app"; do
    if [ -e "$path" ]; then
        rm -rf "$path"
        ok "Removed: $path"
    fi
done

# ── 3. Remove dispatch wrapper ───────────────────────────
step "Removing dispatch wrapper"

WRAPPER="$HOME/.trinity/bin/trinity-dispatch"
if [ -f "$WRAPPER" ]; then
    rm -f "$WRAPPER"
    ok "Removed: $WRAPPER"
fi

# ── 4. Remove shell profile entry ────────────────────────
step "Removing PATH entry"

if [ -n "${ZSH_VERSION:-}" ]; then
    SHELL_RC="$HOME/.zshrc"
else
    SHELL_RC="$HOME/.bash_profile"
fi

if grep -q "trinity-local" "$SHELL_RC" 2>/dev/null; then
    # Remove the trinity-local PATH entry (and preceding blank line if it exists)
    sed -i '' '/trinity-local/d' "$SHELL_RC"
    ok "Removed trinity-local from $SHELL_RC"
else
    echo "  ${DIM}– Not found in shell RC${NC}"
fi

# ── 5. Remove state directory (complete mode only) ───────
if [ "$MODE" == "complete" ]; then
    step "Removing state directory"

    if [ -d "$HOME/.trinity" ]; then
        rm -rf "$HOME/.trinity"
        ok "Removed: ~/.trinity/"
    fi
fi

# ── 6. Remove venv and local package ─────────────────────
step "Local development cleanup"

if [ -d "$SCRIPT_DIR/.venv" ]; then
    echo "  ${DIM}– .venv found (keep for development or delete manually)${NC}"
fi

# ── Done ──────────────────────────────────────────────────
echo ""
echo "${BOLD}┌─────────────────────────────────────────┐${NC}"
echo "${BOLD}│        Uninstall complete ✓             │${NC}"
echo "${BOLD}└─────────────────────────────────────────┘${NC}"
echo ""

if [ "$MODE" == "minimal" ]; then
    echo "  ${DIM}State kept at: ~/.trinity/${NC}"
    echo "  ${DIM}To remove state, run: ./uninstall.sh complete${NC}"
    echo ""
elif [ "$MODE" == "complete" ]; then
    echo "  ${DIM}All Trinity Local data removed.${NC}"
    echo ""
fi
