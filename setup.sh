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
#    6. Generates the Trinity Launchpad and adds shortcuts to Desktop + Applications
#    7. Shows you what's connected
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

# ── 6. Launchpad shortcuts ────────────────────────────
step "Launchpad shortcuts"

.venv/bin/python -c "
from trinity_local.portal_page import install_launchpad_shortcuts, write_portal_html
launchpad_path = write_portal_html()
paths = install_launchpad_shortcuts(launchpad_path=launchpad_path)
print(f'  \033[0;32m✓\033[0m Launchpad written to {launchpad_path}')
for path in paths:
    print(f'  \033[0;32m✓\033[0m Shortcut written to {path}')
"

# ── 7. Shell profile ───────────────────────────────────
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

# ── 8. Status ─────────────────────────────────────────────
step "Checking your providers"
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

# ── Auto-open Launchpad ──────────────────────────────────
step "Opening Trinity Launchpad"

LAUNCHPAD_HTML="$HOME/.trinity/portal_pages/launchpad.html"
if [ -f "$LAUNCHPAD_HTML" ]; then
    open "file://$LAUNCHPAD_HTML"
    ok "Launchpad opened in your browser"
else
    warn "Launchpad HTML not found at $LAUNCHPAD_HTML"
fi

# ── Done ──────────────────────────────────────────────────
echo "${BOLD}┌─────────────────────────────────────────┐${NC}"
echo "${BOLD}│            Setup complete ✓              │${NC}"
echo "${BOLD}└─────────────────────────────────────────┘${NC}"
echo ""
echo "  ${BOLD}Next steps:${NC}"
echo ""
echo "  ${CYAN}trinity-local watch-once --notify${NC}"
echo "  ${DIM}# Scan your recent sessions once${NC}"
echo ""
echo "  ${CYAN}trinity-local watch-loop --notify${NC}"
echo "  ${DIM}# Keep watching for new sessions (runs in this terminal)${NC}"
echo ""
echo "  Your launchpad has opened in the browser."
echo "  Council launch requires Trinity Dispatch shortcut to be installed."
echo ""
echo "  (Open a new terminal or run: ${CYAN}source $SHELL_RC${NC})"
echo ""
