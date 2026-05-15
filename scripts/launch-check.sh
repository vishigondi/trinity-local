#!/usr/bin/env bash
# ───────────────────────────────────────────────────────────
#  Trinity Local — Launch Verification (T-0 Step 1)
#
#  Runs the three programmatic gates from docs/launch-package.md's
#  T-0 engineering sequence. Single command, green/red verdict per
#  step, non-zero exit on any failure.
#
#  Usage:
#    bash scripts/launch-check.sh
#    bash scripts/launch-check.sh --skip-smoke   # skip the slow wheel rebuild
#
#  After this passes, run the remaining T-0 steps manually (the ones
#  requiring credentials):
#    - gh repo edit --visibility public ...
#    - git tag v1.0.0 && git push origin v1.0.0
#    - python -m build && twine upload dist/*
#
#  Earned its place at T-1 (May 14, 2026) when 33+ ticks of drift-
#  finding produced 18 doc-consistency guards + a 1065-test suite.
#  A future launch milestone (v1.5, v2) should run this same script
#  before flipping any state.
# ───────────────────────────────────────────────────────────
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$REPO_ROOT"

# Colors
if [ -t 1 ]; then
    GREEN='\033[0;32m'
    RED='\033[0;31m'
    DIM='\033[2m'
    BOLD='\033[1m'
    NC='\033[0m'
else
    GREEN='' RED='' DIM='' BOLD='' NC=''
fi

SKIP_SMOKE=0
for arg in "$@"; do
    case "$arg" in
        --skip-smoke) SKIP_SMOKE=1 ;;
        -h|--help)
            sed -n '2,21p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
    esac
done

PYTEST="${PYTEST:-.venv/bin/python -m pytest}"

failed_steps=()

run_step() {
    local label="$1"; shift
    printf "${BOLD}─── %s ───${NC}\n" "$label"
    if "$@"; then
        printf "${GREEN}✓${NC} %s\n\n" "$label"
    else
        printf "${RED}✗${NC} %s\n\n" "$label"
        failed_steps+=("$label")
    fi
}

# Step 1: full pytest suite
run_step "Step 1/3: pytest (full suite, ~2 min)" \
    $PYTEST -q

# Step 2: doc-consistency guards (the 18 launch-credibility checks)
run_step "Step 2/3: doc-consistency guards (18 launch-credibility checks)" \
    $PYTEST tests/test_doc_count_consistency.py -q

# Step 3: cold-install smoke (build wheel + install in fresh venv + verify MCP tools)
if [ "$SKIP_SMOKE" -eq 1 ]; then
    printf "${DIM}─── Step 3/3: cold-install smoke ─── skipped (--skip-smoke)${NC}\n\n"
else
    run_step "Step 3/3: cold-install smoke (fresh venv + 11 MCP tools)" \
        bash scripts/smoke_install.sh local
fi

# Verdict
printf "${BOLD}═══════════════════════════════════════════════════════${NC}\n"
if [ ${#failed_steps[@]} -eq 0 ]; then
    printf "${GREEN}${BOLD}✓ All checks passed — ready for the next T-0 step.${NC}\n"
    printf "${DIM}Next manual steps (need credentials):${NC}\n"
    printf "${DIM}  gh repo edit vishigondi/trinity-local --visibility public --accept-visibility-change-consequences${NC}\n"
    printf "${DIM}  git tag -a v1.0.0 -m \"Trinity Local v1.0 — ships May 13–15, 2026\" && git push origin v1.0.0${NC}\n"
    printf "${DIM}  python -m build && python -m twine upload dist/*${NC}\n"
    printf "${DIM}See docs/launch-package.md for the full T-0 engineering sequence.${NC}\n"
    exit 0
else
    printf "${RED}${BOLD}✗ %d gate(s) failed:${NC}\n" "${#failed_steps[@]}"
    for step in "${failed_steps[@]}"; do
        printf "${RED}  - %s${NC}\n" "$step"
    done
    printf "${DIM}Fix before flipping the repo public or publishing to PyPI.${NC}\n"
    exit 1
fi
