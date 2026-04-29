#!/bin/zsh
# ───────────────────────────────────────────────────────────
#  Trinity Local — One-Line Setup
#
#  Usage:
#    ./setup.sh
#
#  What this does:
#    1. Checks Python 3.10+
#    2. Creates a Python virtual environment (.venv)
#    3. Installs trinity-local into it
#    4. Copies default config if you don't have one
#    5. Writes the dispatch wrapper (~/.trinity/bin/trinity-dispatch)
#    6. Imports the macOS Shortcut (opens "Add Shortcut" dialog)
#    7. Generates the Trinity Launchpad and adds to Desktop + Applications
#    8. Shows you what's connected
#
#  Safe to re-run — it skips steps that are already done.
# ───────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
CYAN='\033[0;36m'
DIM='\033[2m'
BOLD='\033[1m'
NC='\033[0m'

step() { echo "\n${CYAN}▸${NC} ${BOLD}$1${NC}"; }
ok()   { echo "  ${GREEN}✓${NC} $1"; }
skip() { echo "  ${DIM}– $1 (already done)${NC}"; }
warn() { echo "  ${YELLOW}⚠${NC} $1"; }
fail() { echo "  ${RED}✗${NC} $1"; }

echo ""
echo "${BOLD}┌─────────────────────────────────────────┐${NC}"
echo "${BOLD}│       Trinity Local — Setup              │${NC}"
echo "${BOLD}└─────────────────────────────────────────┘${NC}"

# ── 0. Check Python 3.10+ ─────────────────────────────────
step "Checking Python"

if ! command -v python3 &>/dev/null; then
    fail "Python 3 not found."
    echo ""
    echo "  Trinity Local requires Python 3.10 or newer."
    echo "  Download it from: ${CYAN}https://www.python.org/downloads/${NC}"
    echo "  Or install via Homebrew: ${CYAN}brew install python${NC}"
    echo ""
    exit 1
fi

PYTHON_VERSION=$(python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
PYTHON_MAJOR=$(python3 -c "import sys; print(sys.version_info.major)")
PYTHON_MINOR=$(python3 -c "import sys; print(sys.version_info.minor)")

if [[ "$PYTHON_MAJOR" -lt 3 ]] || [[ "$PYTHON_MAJOR" -eq 3 && "$PYTHON_MINOR" -lt 10 ]]; then
    fail "Python $PYTHON_VERSION found, but 3.10+ is required."
    echo ""
    echo "  Download a newer version from: ${CYAN}https://www.python.org/downloads/${NC}"
    echo "  Or install via Homebrew: ${CYAN}brew install python${NC}"
    echo ""
    exit 1
fi

ok "Python $PYTHON_VERSION"

# ── 1. Python venv ────────────────────────────────────────
step "Python environment"

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    ok "Created virtual environment"
else
    skip "Virtual environment exists"
fi

# Activate for the rest of this script
source .venv/bin/activate

# ── 2. Install package ────────────────────────────────────
step "Installing Trinity Local"

if ! .venv/bin/pip show trinity-local &>/dev/null; then
    .venv/bin/pip install -e . --quiet
    ok "Installed trinity-local"
else
    .venv/bin/pip install -e . --quiet
    ok "Updated trinity-local"
fi

# ── 3. Config ─────────────────────────────────────────────
step "Configuration"

if [ ! -f "config.json" ]; then
    cp config.example.json config.json
    ok "Created config.json"
else
    skip "config.json exists"
fi

# ── 4. Dispatch wrapper ───────────────────────────────────
step "Dispatch bridge"

.venv/bin/python -c "
from trinity_local.shortcut_setup import write_dispatch_wrapper
path = write_dispatch_wrapper()
print(f'  \033[0;32m✓\033[0m Written to {path}')
"

# ── 5. macOS Shortcut ─────────────────────────────────────
step "macOS Shortcut"

SHORTCUT_FILE="$SCRIPT_DIR/Trinity Dispatch.shortcut"

if shortcuts list 2>/dev/null | grep -qF "Trinity Dispatch"; then
    skip "Trinity Dispatch shortcut already installed"
else
    if [ -f "$SHORTCUT_FILE" ]; then
        SIGNED_FILE="$SCRIPT_DIR/.Trinity Dispatch-signed.shortcut"
        if shortcuts sign --mode anyone --input "$SHORTCUT_FILE" --output "$SIGNED_FILE" 2>/dev/null; then
            open "$SIGNED_FILE"
        else
            open "$SHORTCUT_FILE"
        fi
        echo ""
        echo "  ${BOLD}Action required:${NC} A dialog has opened in the Shortcuts app."
        echo "  Click ${BOLD}\"Add Shortcut\"${NC} to finish installing Trinity Dispatch."
        echo ""
        read -p "  Press Enter once you've clicked Add Shortcut... " -r
        echo ""
        if shortcuts list 2>/dev/null | grep -qF "Trinity Dispatch"; then
            ok "Trinity Dispatch shortcut installed"
        else
            warn "Shortcut not detected yet — you can add it manually later from Shortcuts app"
        fi
    else
        warn "No Trinity Dispatch.shortcut file found."
        echo "       Run: ${CYAN}trinity-local shortcut-install${NC} for manual setup."
    fi
fi

# ── 6. Launchpad + Desktop icon ───────────────────────────
step "Trinity app (Desktop + Applications)"

.venv/bin/python -c "
from trinity_local.portal_page import install_launchpad_shortcuts, write_portal_html
launchpad_path = write_portal_html()
paths = install_launchpad_shortcuts(launchpad_path=launchpad_path)
print(f'  \033[0;32m✓\033[0m Launchpad written')
for path in paths:
    print(f'  \033[0;32m✓\033[0m Trinity app added to {path.parent}')
"

# Refresh Dock so custom icon appears immediately
killall Dock 2>/dev/null || true

# ── 7. Shell profile ───────────────────────────────────────
step "Shell configuration"

VENV_BIN="$SCRIPT_DIR/.venv/bin"
if [ -n "${ZSH_VERSION:-}" ]; then
    SHELL_RC="$HOME/.zshrc"
else
    SHELL_RC="$HOME/.bash_profile"
fi

VENV_PATH_LINE="export PATH=\"$VENV_BIN:\$PATH\"  # trinity-local"

if ! grep -q "trinity-local" "$SHELL_RC" 2>/dev/null; then
    echo "" >> "$SHELL_RC"
    echo "$VENV_PATH_LINE" >> "$SHELL_RC"
    ok "Added trinity-local to PATH"
else
    skip "trinity-local already in PATH"
fi

# ── 8. Connected AI tools ─────────────────────────────────
step "Detecting your AI tools"
echo ""
.venv/bin/trinity-local status
echo ""
.venv/bin/python -c "
from trinity_local.adapters import check_all_adapters
from trinity_local.setup_guidance import render_missing_provider_guidance
guidance = render_missing_provider_guidance(check_all_adapters())
if guidance:
    print(guidance)
    print()
" || true

# ── Open Launchpad ─────────────────────────────────────────
step "Opening Trinity Launchpad"

LAUNCHPAD_HTML="$HOME/.trinity/portal_pages/launchpad.html"
if [ -f "$LAUNCHPAD_HTML" ]; then
    open "file://$LAUNCHPAD_HTML"
    ok "Launchpad opened in your browser"
else
    warn "Launchpad HTML not found — run: ${CYAN}trinity-local portal-html${NC}"
fi

# ── Done ───────────────────────────────────────────────────
echo ""
echo "${BOLD}┌─────────────────────────────────────────┐${NC}"
echo "${BOLD}│            Setup complete ✓              │${NC}"
echo "${BOLD}└─────────────────────────────────────────┘${NC}"
echo ""
echo "  ${BOLD}You're ready to use Trinity Local.${NC}"
echo ""
echo "  ${BOLD}Open the Launchpad:${NC}"
echo "  ${DIM}Double-click Trinity on your Desktop or in Applications${NC}"
echo ""
echo "  ${BOLD}Start a Council:${NC}"
echo "  ${DIM}Type your task in the Launchpad and click Launch Council${NC}"
echo ""
echo "  ${BOLD}Watch your AI sessions:${NC}"
echo "  ${CYAN}trinity-local watch-once${NC}  ${DIM}# Scan your recent sessions${NC}"
echo ""
if [ -n "${ZSH_VERSION:-}" ]; then
    echo "  ${DIM}Open a new terminal or run: source ~/.zshrc${NC}"
else
    echo "  ${DIM}Open a new terminal or run: source ~/.bash_profile${NC}"
fi
echo ""
