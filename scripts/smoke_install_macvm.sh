#!/usr/bin/env bash
# scripts/smoke_install_macvm.sh — Cold-install gate via tart Mac VM.
#
# Boots a fresh macOS image, SCPs the locally-built wheel in, runs the
# standard install sequence, asserts `trinity-local doctor` passes.
# Models the actual "fresh Mac, never seen Trinity before" user flow that
# `scripts/smoke_install.sh local` can't, because it runs on YOUR Mac
# which already has Trinity state in ~/.trinity/.
#
# This is the v1 launch gate's strongest possible automation —
# replicates the HN-reader-installs-from-zero scenario exactly.
# Target: ≤8 minutes from `pip install` to first successful `doctor`
# inside the VM (matches spec-v1.md's HN-reader bar).
#
# Prereqs (one-time):
#   brew install cirruslabs/cli/tart sshpass
#   tart pull ghcr.io/cirruslabs/macos-sequoia-base:latest   # ~50GB, ~10 min on first pull
#
# Usage:
#   bash scripts/smoke_install_macvm.sh                  # build + boot + test + teardown
#   bash scripts/smoke_install_macvm.sh --keep           # leave VM running after for manual inspection
#   bash scripts/smoke_install_macvm.sh --image <ref>    # use a different base image
#
# Exit codes:
#   0 — install + doctor green inside VM, under 8-minute bar
#   1 — install or doctor failed inside VM (real launch blocker)
#   2 — VM setup error (tart missing, image unavailable, network, etc.)
#   3 — exceeded 8-minute bar (warning, not fatal — needs spec follow-up)

set -euo pipefail

KEEP_VM=0
BASE_IMAGE="ghcr.io/cirruslabs/macos-sequoia-base:latest"

while [ $# -gt 0 ]; do
    case "$1" in
        --keep) KEEP_VM=1; shift ;;
        --image) BASE_IMAGE="$2"; shift 2 ;;
        *) echo "usage: $0 [--keep] [--image <ref>]" >&2; exit 2 ;;
    esac
done

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
VM_NAME="trinity-smoke-$$"
VM_USER="admin"
VM_PASS="admin"
LOG_FILE="/tmp/${VM_NAME}.log"

cleanup() {
    if [ "$KEEP_VM" = "0" ]; then
        echo "[cleanup] stopping + deleting VM..."
        tart stop "$VM_NAME" 2>/dev/null || true
        sleep 2
        tart delete "$VM_NAME" 2>/dev/null || true
    else
        echo "[--keep] VM left running. Connect with: tart ssh $VM_NAME"
    fi
}
trap cleanup EXIT

# ── Step 0: prereq checks ────────────────────────────────────────────
if ! command -v tart >/dev/null 2>&1; then
    echo "FAIL: tart not installed." >&2
    echo "  Run: brew install cirruslabs/cli/tart" >&2
    exit 2
fi

if ! command -v sshpass >/dev/null 2>&1; then
    echo "FAIL: sshpass not installed (required for non-interactive SSH)." >&2
    echo "  Run: brew install sshpass  (may need: brew install esolitos/ipa/sshpass)" >&2
    exit 2
fi

# ── Step 1: build wheel locally ──────────────────────────────────────
echo "[1/6] Building wheel from current source..."
cd "$REPO_ROOT"
rm -rf dist build
if ! python -m build --wheel >&2; then
    echo "FAIL: wheel build failed" >&2
    exit 2
fi
WHEEL=$(ls dist/trinity_local-*.whl 2>/dev/null | head -1)
if [ -z "$WHEEL" ]; then
    echo "FAIL: no wheel produced in dist/" >&2
    exit 2
fi
WHEEL_NAME=$(basename "$WHEEL")
echo "      ✓ built $WHEEL_NAME"

# ── Step 2: clone fresh VM from base image ───────────────────────────
echo "[2/6] Cloning fresh VM ($VM_NAME) from $BASE_IMAGE..."
if ! tart clone "$BASE_IMAGE" "$VM_NAME" 2>&1 | tail -5; then
    echo "FAIL: tart clone failed. Did you pull the image?" >&2
    echo "  Run: tart pull $BASE_IMAGE" >&2
    exit 2
fi
echo "      ✓ cloned"

# ── Step 3: start the VM ─────────────────────────────────────────────
echo "[3/6] Starting VM (logs: $LOG_FILE)..."
tart run "$VM_NAME" --no-graphics >"$LOG_FILE" 2>&1 &
sleep 5

# Wait for VM to come up with an IP
echo "      waiting for VM IP (up to 60s)..."
VM_IP=""
for i in $(seq 1 12); do
    VM_IP=$(tart ip "$VM_NAME" 2>/dev/null || true)
    if [ -n "$VM_IP" ]; then break; fi
    sleep 5
done
if [ -z "$VM_IP" ]; then
    echo "FAIL: VM didn't get an IP within 60s." >&2
    echo "  tail of $LOG_FILE:" >&2
    tail -20 "$LOG_FILE" >&2 || true
    exit 2
fi
echo "      ✓ VM IP: $VM_IP"

# Wait for SSH to actually accept connections
echo "      waiting for SSH (up to 60s)..."
for i in $(seq 1 12); do
    if sshpass -p "$VM_PASS" ssh -o StrictHostKeyChecking=no -o ConnectTimeout=5 -o UserKnownHostsFile=/dev/null \
        "$VM_USER@$VM_IP" true 2>/dev/null; then
        echo "      ✓ SSH ready"
        break
    fi
    sleep 5
done

# ── Step 4: SCP wheel into VM ────────────────────────────────────────
echo "[4/6] SCP'ing wheel into VM..."
if ! sshpass -p "$VM_PASS" scp -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    "$WHEEL" "$VM_USER@$VM_IP:~/$WHEEL_NAME" >&2; then
    echo "FAIL: scp failed" >&2
    exit 2
fi
echo "      ✓ wheel copied"

# ── Step 5: install + doctor inside the VM ───────────────────────────
echo "[5/6] Running install + doctor inside VM..."
START=$(date +%s)

# All-in-one script that mirrors the HN reader's experience:
# 1) Ensure Python 3.10+ exists
# 2) Create fresh venv (the user wouldn't have a project venv)
# 3) Install trinity-local from the SCP'd wheel
# 4) Run install-mcp (no harness configs to merge into; lays the groundwork)
# 5) Run doctor --json and assert internal checks pass
#    (provider CLIs absent in a vanilla VM — that's expected, not a fail)
REMOTE_SCRIPT=$(cat <<'REMOTE_EOF'
set -e
WHEEL_NAME=$(ls ~/trinity_local-*.whl | head -1)
if [ -z "$WHEEL_NAME" ]; then echo "FAIL: no wheel in home dir"; exit 1; fi

# macOS Sequoia ships Python 3.9 at /usr/bin/python3 — too old for Trinity's
# >=3.10 requirement. This mirrors the actual user-flow per README:
# "If you need to upgrade: brew install python"
PYV=$(/usr/bin/python3 -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>/dev/null || echo "missing")
echo "      system python3: $PYV"

PYTHON=python3
if [ "$PYV" = "3.9" ] || [ "$PYV" = "missing" ] || [ "$PYV" = "3.8" ]; then
    # macos-sequoia-base doesn't ship brew. Use python.org's official PKG
    # installer (no brew dep, no sudo prompt — admin user has NOPASSWD on
    # cirruslabs images). README mentions brew as the recommended path; this
    # is the fallback that works on minimal images.
    PY_VER="3.12.7"
    PKG_URL="https://www.python.org/ftp/python/${PY_VER}/python-${PY_VER}-macos11.pkg"
    echo "      installing python ${PY_VER} via python.org PKG installer..."
    curl -fsSL "$PKG_URL" -o /tmp/python.pkg
    echo admin | sudo -S installer -pkg /tmp/python.pkg -target / >/dev/null 2>&1
    if [ -x /usr/local/bin/python3.12 ]; then
        PYTHON=/usr/local/bin/python3.12
    elif [ -x /Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12 ]; then
        PYTHON=/Library/Frameworks/Python.framework/Versions/3.12/bin/python3.12
    else
        echo "FAIL: python 3.12 not found after PKG install" >&2
        exit 1
    fi
    echo "      ✓ python 3.12 ready at $PYTHON"
fi

$PYTHON -m venv ~/trinity-venv
~/trinity-venv/bin/pip install --quiet --upgrade pip
~/trinity-venv/bin/pip install --quiet "$WHEEL_NAME"
echo "      ✓ pip install ok"

~/trinity-venv/bin/trinity-local install-mcp 2>&1 | head -5
echo "      ✓ install-mcp ran"

REPORT=$(~/trinity-venv/bin/trinity-local doctor --json)
echo "$REPORT" | $PYTHON -c "
import json, sys
data = json.load(sys.stdin)
home = next((c for c in data['checks'] if c['name'] == 'trinity_home_writeable'), None)
mcp = next((c for c in data['checks'] if c['name'] == 'mcp_available'), None)
cfg = next((c for c in data['checks'] if c['name'] == 'config_loadable'), None)
# Trinity-internal checks: must pass. Provider CLI checks (claude/codex/gemini)
# legitimately fail on a fresh Mac without those CLIs installed yet — that's
# the user's setup task, not a Trinity install failure. config_loadable is
# present but may not be ok (fresh install has no enabled providers); just
# assert it exists, matching the local smoke's contract.
assert home and home['ok'], 'trinity_home_writeable failed: ' + json.dumps(home)
assert mcp and mcp['ok'], 'mcp_available failed: ' + json.dumps(mcp)
assert cfg is not None, 'config_loadable check missing'
print('      ✓ doctor: home + mcp green; config present (providers absent — expected)')
"

SKILL=~/.claude/skills/trinity/SKILL.md
if [ -f "$SKILL" ]; then
    echo "      ✓ /trinity skill bundled to $SKILL"
else
    echo "FAIL: skill not bundled to $SKILL" >&2
    exit 1
fi
REMOTE_EOF
)

if ! sshpass -p "$VM_PASS" ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
    "$VM_USER@$VM_IP" "bash -s" <<< "$REMOTE_SCRIPT" >&2; then
    echo "FAIL: install or doctor failed inside VM" >&2
    exit 1
fi

END=$(date +%s)
DURATION=$((END - START))

# ── Step 6: summary + bar check ──────────────────────────────────────
echo
echo "[6/6] Summary"
echo "      install + install-mcp + doctor took ${DURATION}s inside fresh macOS VM"

if [ "$DURATION" -le 480 ]; then
    echo "      ✓ under the 8-minute HN-reader bar (480s)"
    echo
    echo "=== cold-install (Mac VM) PASSED ==="
    exit 0
else
    echo "      ⚠ exceeded 8-minute bar ($DURATION s > 480s)"
    echo "        Spec-v1.md bar test failed — needs investigation."
    echo
    echo "=== cold-install (Mac VM) SLOW (over bar but functional) ==="
    exit 3
fi
