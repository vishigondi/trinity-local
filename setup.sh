#!/bin/zsh
# ───────────────────────────────────────────────────────────
#  Trinity Local — One-Line Setup
#
#  Usage:
#    ./setup.sh
#
#  What this does:
#    1. Creates a Python virtual environment (.venv)
#    2. Installs trinity-local into it
#    3. Copies default config if you don't have one
#    4. Writes the dispatch wrapper (~/.trinity/bin/trinity-dispatch)
#    5. Imports the macOS Shortcut (one-click "Add Shortcut" dialog)
#    6. Shows you what's connected
#
#  Safe to re-run — it skips steps that are already done.
# ───────────────────────────────────────────────────────────
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

# Colors
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
DIM='\033[2m'
BOLD='\033[1m'
NC='\033[0m'

step() { echo "\n${CYAN}▸${NC} ${BOLD}$1${NC}"; }
ok()   { echo "  ${GREEN}✓${NC} $1"; }
skip() { echo "  ${DIM}– $1 (already done)${NC}"; }
warn() { echo "  ${YELLOW}⚠${NC} $1"; }

echo ""
echo "${BOLD}┌─────────────────────────────────────────┐${NC}"
echo "${BOLD}│       Trinity Local — Setup              │${NC}"
echo "${BOLD}└─────────────────────────────────────────┘${NC}"

# ── 1. Python venv ────────────────────────────────────────
step "Python environment"

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    ok "Created .venv"
else
    skip ".venv exists"
fi

# Activate for the rest of this script
source .venv/bin/activate

# ── 2. Install package ────────────────────────────────────
step "Installing trinity-local"

if ! .venv/bin/pip show trinity-local &>/dev/null; then
    .venv/bin/pip install -e . --quiet
    ok "Installed trinity-local"
else
    # Reinstall to pick up any code changes
    .venv/bin/pip install -e . --quiet
    ok "Updated trinity-local"
fi

# ── 3. Config ─────────────────────────────────────────────
step "Configuration"

if [ ! -f "config.json" ]; then
    cp config.example.json config.json
    ok "Created config.json from example"
else
    skip "config.json exists"
fi

# ── 4. Dispatch wrapper ──────────────────────────────────
step "Dispatch wrapper"

.venv/bin/python -c "
from trinity_local.shortcut_setup import write_dispatch_wrapper
path = write_dispatch_wrapper()
print(f'  \033[0;32m✓\033[0m Written to {path}')
"

# ── 5. macOS Shortcut ────────────────────────────────────
step "macOS Shortcut"

SHORTCUT_FILE="$SCRIPT_DIR/Trinity Dispatch.shortcut"

if shortcuts list 2>/dev/null | grep -qF "Trinity Dispatch"; then
    skip "Trinity Dispatch shortcut already installed"
else
    if [ -f "$SHORTCUT_FILE" ]; then
        # Sign for sharing and open to trigger import
        SIGNED_FILE="$SCRIPT_DIR/.Trinity Dispatch-signed.shortcut"
        if shortcuts sign --mode anyone --input "$SHORTCUT_FILE" --output "$SIGNED_FILE" 2>/dev/null; then
            open "$SIGNED_FILE"
            ok "Shortcut import dialog opened — click ${BOLD}Add Shortcut${NC} to finish"
        else
            # Signing failed (maybe no identity), try opening unsigned
            open "$SHORTCUT_FILE"
            ok "Shortcut import dialog opened — click ${BOLD}Add Shortcut${NC} to finish"
        fi
    else
        warn "No Trinity Dispatch.shortcut file found in project."
        echo "       Run: ${CYAN}trinity-local shortcut-install${NC} for manual setup."
    fi
fi

# ── 6. Shell profile ───────────────────────────────────
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
    ok "Added trinity-local to $SHELL_RC"
else
    skip "trinity-local already in PATH"
fi

# ── 7. Status ─────────────────────────────────────────────
step "Checking your providers"
echo ""
.venv/bin/trinity-local status
echo ""

# ── Done ──────────────────────────────────────────────────
echo "${BOLD}┌─────────────────────────────────────────┐${NC}"
echo "${BOLD}│            Setup complete ✓              │${NC}"
echo "${BOLD}└─────────────────────────────────────────┘${NC}"
echo ""
echo "  ${BOLD}What to do next:${NC}"
echo ""
echo "  ${CYAN}trinity-local watch-once --notify${NC}"
echo "  ${DIM}# Scan your recent AI sessions${NC}"
echo ""
echo "  ${CYAN}trinity-local watch-loop --notify${NC}"
echo "  ${DIM}# Keep watching in the background${NC}"
echo ""
echo "  ${CYAN}trinity-local portal-html --open-browser${NC}"
echo "  ${DIM}# Open the Trinity dashboard${NC}"
echo ""
echo "  (Open a new terminal or run: ${CYAN}source $SHELL_RC${NC})"
echo ""
