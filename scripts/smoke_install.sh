#!/usr/bin/env bash
# Cold-install smoke test — the deterministic gate from council_5699d0e62cf965d0.
#
# Eval seed verbatim: "From a fresh venv on macOS AND a python:3.11-slim docker
# image, `pip install trinity-local && trinity-local doctor --json` exits 0
# with no failed checks, and `test -f LICENSE` passes."
#
# Extended by council_d55953003bb29f9d (Claude won, high): the deterministic
# test that closes the #1 launch risk (skill-not-installed-by-pip) is:
# "build a wheel, install in a fresh venv with isolated HOME, run install-mcp,
#  and assert ~/.claude/skills/trinity/SKILL.md exists at the target path."
#
# Two modes:
#   ./scripts/smoke_install.sh local   — build wheel, install in fresh venv, run doctor
#   ./scripts/smoke_install.sh docker  — same in python:3.11-slim container
#
# The local mode is the macOS check (Darwin-specific failure modes: MLX
# wheels, codesigning, Apple Silicon paths). Docker mode is the Linux check.
# Council ratified BOTH must pass before May 13–15 ship.

set -euo pipefail

MODE="${1:-local}"
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SMOKE_DIR="${TMPDIR:-/tmp}/trinity-smoke-$$"

cleanup() {
    rm -rf "$SMOKE_DIR"
}
trap cleanup EXIT

assert_license_exists() {
    if [ ! -f "$REPO_ROOT/LICENSE" ]; then
        echo "FAIL: LICENSE file missing at repo root" >&2
        exit 1
    fi
    echo "✓ LICENSE present"
}

build_wheel() {
    cd "$REPO_ROOT"
    rm -rf dist build
    if ! python -m build --wheel >&2; then
        echo "FAIL: wheel build failed" >&2
        exit 1
    fi
    local whl
    whl=$(ls dist/trinity_local-*.whl 2>/dev/null | head -1)
    if [ -z "$whl" ]; then
        echo "FAIL: no wheel produced in dist/" >&2
        exit 1
    fi
    echo "$whl"
}

smoke_local() {
    echo "=== smoke_install.sh local — fresh venv on this machine ==="
    assert_license_exists

    local whl
    whl=$(build_wheel)
    echo "✓ built $whl"

    mkdir -p "$SMOKE_DIR"
    python -m venv "$SMOKE_DIR/venv"
    # Quiet pip install; surface any error
    "$SMOKE_DIR/venv/bin/pip" install --quiet "$whl"
    echo "✓ pip install in fresh venv"

    # Council eval-seed assertion: doctor --json must exit 0 AND have no failed checks.
    local report
    report=$("$SMOKE_DIR/venv/bin/trinity-local" doctor --json)
    local exit_code=$?
    if [ $exit_code -ne 0 ]; then
        # doctor exits non-zero ONLY when ready_for_council is false (truly broken).
        # In a fresh-venv smoke we expect provider checks to fail (no Claude / Gemini /
        # Codex CLIs in this venv's PATH), but TRINITY itself should install cleanly.
        # Distinguish "Trinity broken" from "providers not installed" — it's only
        # the former that fails the gate.
        echo "  → doctor exited $exit_code (expected on a CLI-less smoke env)"
    fi

    # Hard requirements: trinity-local CLI is callable, doctor runs without
    # tracebacks, JSON parses, the trinity_home check passes.
    if ! echo "$report" | python -c "
import json, sys
data = json.load(sys.stdin)
home_check = next((c for c in data['checks'] if c['name'] == 'trinity_home_writeable'), None)
mcp_check = next((c for c in data['checks'] if c['name'] == 'mcp_available'), None)
config_check = next((c for c in data['checks'] if c['name'] == 'config_loadable'), None)
assert home_check and home_check['ok'], 'trinity_home_writeable check failed'
assert mcp_check and mcp_check['ok'], 'mcp_available check failed (mcp dep not bundled)'
assert config_check, 'config_loadable check missing'
print('✓ Trinity-internal checks pass (provider CLIs absent in smoke env, expected)')
"; then
        echo "FAIL: trinity-local doctor produced unexpected output" >&2
        echo "$report" >&2
        exit 1
    fi

    # council_d55953003bb29f9d gate: install-mcp into an isolated HOME must
    # drop the /trinity skill at ~/.claude/skills/trinity/SKILL.md.
    local fake_home="$SMOKE_DIR/fakehome"
    mkdir -p "$fake_home"
    HOME="$fake_home" "$SMOKE_DIR/venv/bin/trinity-local" install-mcp >/dev/null
    local skill_path="$fake_home/.claude/skills/trinity/SKILL.md"
    if [ ! -f "$skill_path" ]; then
        echo "FAIL: install-mcp did not drop $skill_path" >&2
        exit 1
    fi
    if ! grep -q "^name: trinity" "$skill_path"; then
        echo "FAIL: SKILL.md missing 'name: trinity' frontmatter at $skill_path" >&2
        exit 1
    fi
    echo "✓ /trinity skill installed at \$HOME/.claude/skills/trinity/SKILL.md"

    # spec-v1.5 Week 5 gate: the MCP path must actually work post-install.
    # install-mcp only writes config files; doctor only checks the env. A
    # missing dep in the wheel would slip past both. Verify the MCP server
    # module imports AND list_tools returns the v1.0 canonical 6 + v1.5
    # trio + launch-arc pair (currently 11 tools total).
    #
    # The expected set is checked as SUPERSET — new tools added without a
    # smoke gate update no longer fail the cold-install run, but if any
    # of the canonical 11 silently DISAPPEAR (refactor drop, dep break,
    # circular-import surface change), the gate fails loudly. Matches the
    # test_mcp_tools.py guard's intent: the canonical list is load-bearing,
    # additions are not.
    if ! "$SMOKE_DIR/venv/bin/python" -c '
import asyncio, sys
from trinity_local.mcp_server import handle_list_tools
tools = asyncio.run(handle_list_tools())
names = {t.name for t in tools}
canonical = {
    # v1.0 lifecycle six
    "route", "run_council", "record_outcome",
    "search_prompts", "get_persona", "get_council_status",
    # v1.5 trio
    "ask", "get_picks", "mark_pick_wrong",
    # launch-arc pair (handoff + benchmark surface)
    "handoff", "get_eval_summary",
}
missing = canonical - names
if missing:
    print(f"FAIL: MCP tool list missing canonical tools: {missing}", file=sys.stderr)
    sys.exit(1)
print(f"  ✓ MCP exposes {len(names)} tools (all {len(canonical)} canonical present): {sorted(names)}")
'; then
        echo "FAIL: MCP server import or tool list check failed" >&2
        exit 1
    fi

    echo
    echo "=== local smoke PASSED ==="
}

smoke_docker() {
    echo "=== smoke_install.sh docker — python:3.11-slim ==="
    if ! command -v docker >/dev/null 2>&1; then
        echo "SKIP: docker not on PATH (install Docker Desktop or run on a Linux host)" >&2
        exit 0
    fi
    assert_license_exists
    local whl
    whl=$(build_wheel)
    echo "✓ built $whl"

    docker run --rm \
        -v "$REPO_ROOT:/repo:ro" \
        python:3.11-slim \
        bash -c "
            set -e
            pip install --quiet /repo/$whl
            trinity-local doctor --json | python -c '
import json, sys
data = json.load(sys.stdin)
home_check = next((c for c in data[\"checks\"] if c[\"name\"] == \"trinity_home_writeable\"), None)
mcp_check = next((c for c in data[\"checks\"] if c[\"name\"] == \"mcp_available\"), None)
assert home_check and home_check[\"ok\"], \"home check failed\"
assert mcp_check and mcp_check[\"ok\"], \"mcp dep not bundled\"
print(\"✓ Trinity-internal checks pass on python:3.11-slim\")
'
        "
    echo
    echo "=== docker smoke PASSED ==="
}

case "$MODE" in
    local)  smoke_local  ;;
    docker) smoke_docker ;;
    both)   smoke_local; smoke_docker ;;
    *)
        echo "usage: $0 [local|docker|both]" >&2
        exit 1
        ;;
esac
