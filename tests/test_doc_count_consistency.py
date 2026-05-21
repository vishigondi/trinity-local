"""Meta-test: load-bearing counts stay in sync across docs.

Principle #20 (duplicated facts drift in the oldest surface)
formalized in tick #89. The pattern surfaced 3× this session — each
time a numeric claim was correct in some surfaces and stale in
others (a stale claim in the OLDEST surface, specifically). The
fix shape: enforce that every place a count is pinned agrees with
every other place, so future-me catches the drift at test time
instead of grep time.

This guard scans the three known duplicate surfaces for the test
count and the smoke-surface count, and asserts they agree
internally. Doesn't enforce a SPECIFIC value — that would require
running pytest first to know what number to expect. Internal
consistency is the regression target; "all stale together" is still
a green test, but a tick that bumps one number without bumping the
others fails loudly.

Per principle #14 (every shipped feature gets a smoke regression
guard within one tick): tick #89 shipped the principle; this ticks
the guard.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[1]
CLAUDE_MD = REPO / "claude.md"
PRODUCT_SPEC = REPO / "docs" / "product-spec.md"


def _extract(path: Path, pattern: str) -> str | None:
    """Return the first regex group match in `path`, or None if not found.

    Strips canonical-placeholder markup before matching so callers can
    keep using simple regexes (e.g. ``r"(\\d+)-surface"``) without
    knowing about ``<!-- canonical:NAME -->VALUE<!-- /canonical -->``
    wrapping. The renderer's markup is invisible to consumers."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    # Strip canonical placeholders down to just their VALUE so regex
    # callers don't need to care about the wrapping.
    text = re.sub(
        r"<!--\s*canonical:[a-z_]+\s*-->([^<]*)<!--\s*/canonical\s*-->",
        r"\1",
        text,
    )
    m = re.search(pattern, text)
    return m.group(1) if m else None


class TestTestCountConsistency:
    """Six surfaces pin the pytest count. They must agree.

    CHANGELOG.md is intentionally NOT in the guard set — per Principle
    #8, CHANGELOG entries are timestamped and allowed to be stale.
    Current-state surfaces (claude.md status, claude.md verified,
    product-spec item 11, 10_hn_faq_full.md launch FAQ closing claim,
    launch-package.md T-0 runbook, LAUNCH_CHECKLIST.md \"Done — ready
    to ship\" header) are not — they describe what's true *now*, so
    they drift loudly.

    The 4→6 extension landed in iter #67 after iters #65/#66 caught
    launch-package.md (1402 → 1296) and LAUNCH_CHECKLIST.md (1372 →
    1296) drifting silently because they weren't in the guard set.
    Adding both surfaces converts that drift into commit-time work.
    """

    def test_four_surfaces_agree(self):
        # The patterns tolerate both:
        #   (a) bare digits  "1296 tests passing"
        #   (b) canonical placeholders "<!-- canonical:test_count -->1296<!-- /canonical --> tests passing"
        # Gap A's render_docs.py auto-syncs (b). Existing surfaces still
        # using (a) keep working until they're migrated.
        CANON = r"(?:<!--\s*canonical:\w+\s*-->)?"
        ENDCANON = r"(?:<!--\s*/canonical\s*-->)?"

        # Surface A: claude.md Status block — "N tests passing"
        status_count = _extract(
            CLAUDE_MD,
            rf"{CANON}(\d+){ENDCANON}\s*tests passing",
        )
        # Surface B: claude.md Verified status — "pytest -q — **N passed**"
        verified_count = _extract(
            CLAUDE_MD,
            rf"pytest -q.{{0,5}}\*\*{CANON}(\d+){ENDCANON}\s*passed\*\*",
        )
        # Surface C: docs/product-spec.md item 11 — "Test suite: N passing"
        spec_count = _extract(
            PRODUCT_SPEC,
            rf"Test suite:\s*{CANON}(\d+){ENDCANON}\s*passing",
        )
        # Surface D: docs/launch-day/10_hn_faq_full.md closing claim —
        # "N tests, M doc-consistency guards" (the launch-day "trust us"
        # numbers a reader sees on the HN FAQ page).
        hn_faq_count = _extract(
            REPO / "docs" / "launch-day" / "10_hn_faq_full.md",
            rf"{CANON}(\d+){ENDCANON}\s*tests,\s*{CANON}\d+{ENDCANON}\s*doc-consistency guards",
        )
        # Surface E: docs/launch-package.md T-0 runbook — "pytest -q
        # # ~N tests". The literal copy-paste runbook a launch operator
        # follows. Caught in iter #65 (was 1402, real was 1294 → 1296).
        launch_package_count = _extract(
            REPO / "docs" / "launch-package.md",
            rf"pytest -q\s+#\s*~{CANON}(\d+){ENDCANON}\s*tests",
        )
        # Surface F: docs/LAUNCH_CHECKLIST.md "Done — ready to ship"
        # header — "(N tests passing + 4 skipped, M doc-consistency
        # guards green". Caught in iter #66 (was 1372, real was 1296).
        launch_checklist_count = _extract(
            REPO / "docs" / "LAUNCH_CHECKLIST.md",
            rf"\({CANON}(\d+){ENDCANON}\s*tests passing \+\s*{CANON}\d+{ENDCANON}\s*skipped",
        )

        # All six must be present.
        assert status_count, "claude.md Status block lost the 'N tests passing' marker"
        assert verified_count, "claude.md Verified status lost the 'pytest -q — **N passed**' marker"
        assert spec_count, "product-spec.md item 11 lost the 'Test suite: N passing' marker"
        assert hn_faq_count, "10_hn_faq_full.md lost the 'N tests, M doc-consistency guards' closing marker"
        assert launch_package_count, "launch-package.md lost the 'pytest -q # ~N tests' runbook marker"
        assert launch_checklist_count, "LAUNCH_CHECKLIST.md lost the '(N tests passing + 4 skipped' header marker"

        # All six numbers must agree.
        counts = {
            "claude.md status": status_count,
            "claude.md verified": verified_count,
            "product-spec item 11": spec_count,
            "10_hn_faq_full closing": hn_faq_count,
            "launch-package T-0 runbook": launch_package_count,
            "LAUNCH_CHECKLIST Done header": launch_checklist_count,
        }
        unique = set(counts.values())
        assert len(unique) == 1, (
            f"Test count drifted across surfaces: {counts}. "
            f"Principle #20: when you bump the test count, bump it in "
            f"ALL six places in the same commit. Single-source-of-truth "
            f"would be cleaner long-term."
        )

    def test_prose_count_at_or_above_realistic_floor(self):
        """The four-surfaces-agree test passes if all four claim the
        SAME number — even if that number is stale. This guard locks
        in a realistic floor (the current pytest count at write time)
        so silent regression downward is caught.

        v1.7 launch state: 1372 passing. Floor set to 1300 — gives
        ~70 tests of headroom for hypothetical future test deletions
        without false-flagging, while still catching the "we claim
        1242 but actually have 1372" stale-by-130 drift this guard
        was born from.

        If the real test count grows (good), keep the floor in step
        when convenient — that's the load-bearing assertion.
        """
        FLOOR = 1280  # current count is 1293 after Pass A-BB simplification; floor allows ≤13 deletions
        # Tolerate canonical-placeholder wrapping (per Gap A renderer).
        status_count = _extract(
            CLAUDE_MD,
            r"(?:<!--\s*canonical:\w+\s*-->)?(\d+)(?:<!--\s*/canonical\s*-->)?\s*tests passing",
        )
        assert status_count is not None
        assert int(status_count) >= FLOOR, (
            f"claude.md status block claims '{status_count} tests passing' "
            f"but the realistic floor is {FLOOR}. Either: (a) you deleted "
            f">{1372-FLOOR} tests legitimately and should bump the floor "
            f"down in this file, OR (b) prose is stale and needs updating "
            f"to match the actual pytest count."
        )


class TestSmokeSurfaceCountConsistency:
    """The smoke-surface count claim appears in claude.md status +
    product-spec + CONTRIBUTING. All three must agree with EACH OTHER
    (principle #20) AND with the actual surface count in
    scripts/browser_smoke.py (principle #21). The earlier two-doc
    guard caught mutual drift but missed the bigger leak: both docs
    drifted together away from the script (33 vs 34). The script is
    now the source of truth; render_docs.canonical_smoke_surface_count
    derives the live count from the printed Surface labels."""

    def test_two_surfaces_agree(self):
        status_count = _extract(
            CLAUDE_MD,
            r"(\d+)-surface browser smoke",
        )
        spec_count = _extract(
            PRODUCT_SPEC,
            r"(\d+)-surface browser smoke",
        )
        assert status_count, "claude.md Status block lost the 'N-surface browser smoke' marker"
        assert spec_count, "product-spec.md lost the 'N-surface browser smoke' marker"
        assert status_count == spec_count, (
            f"Smoke-surface count drift: claude.md says {status_count}, "
            f"product-spec says {spec_count}. Per principle #20, pin both "
            f"in the same commit."
        )

    def test_claim_matches_actual_script_count(self):
        """Principle #21: the public claim ('N-surface smoke') must be
        derivable from the source of truth (the script itself). If a
        surface lands but the doc isn't re-rendered, this fails."""
        import sys
        sys.path.insert(0, str(REPO / "scripts"))
        try:
            from render_docs import canonical_smoke_surface_count
        finally:
            sys.path.pop(0)

        actual = canonical_smoke_surface_count()
        claim = _extract(CLAUDE_MD, r"(\d+)-surface browser smoke")
        assert claim, "claude.md Status block lost the 'N-surface browser smoke' marker"
        assert int(claim) == actual, (
            f"Smoke-surface count drift: claude.md claims {claim}-surface, "
            f"scripts/browser_smoke.py prints {actual} distinct surface labels. "
            f"Re-render via `python scripts/render_docs.py` after adding "
            f"or removing surfaces; the canonical placeholder "
            f"<!-- canonical:smoke_surface_count --> auto-fills."
        )


class TestMcpToolNameConsistency:
    """Stronger than count-checking: the actual tool NAMES claude.md
    advertises must match the names mcp_server.py defines. Catches
    a future tool added to code but not documented (the path tick #88
    caught for tool-count drift, generalized to per-tool-presence).

    The match is set-equality. If claude.md mentions a tool that
    mcp_server.py doesn't define, the doc has a phantom. If
    mcp_server.py defines a tool claude.md doesn't list, the user
    learns about it by accident.
    """

    def test_claude_md_lists_all_mcp_server_tools(self):
        mcp_server = REPO / "src" / "trinity_local" / "mcp_server.py"
        # Parse mcp_server.py for `name="X"` definitions inside Tool()
        # entries. The pattern is conservative — only matches names
        # at indentation typical of Tool() constructor calls (avoids
        # picking up internal helper names).
        code = mcp_server.read_text(encoding="utf-8")
        code_tools = set(re.findall(r'\s+name="([a-z_]+)"', code))
        # Hand-curated whitelist for non-tool `name=` strings if any
        # internal helper uses the same form (none today, but keep
        # the door open for future drift without a code change).
        not_tools = set()
        code_tools -= not_tools
        # Parse claude.md's MCP section for tool names in backticks.
        # Pattern: `<tool_name>(` — the open-paren is what makes it
        # a tool definition vs a generic identifier.
        claude = CLAUDE_MD.read_text(encoding="utf-8")
        # Narrow to the MCP tools section so we don't pick up
        # parenthesized identifiers elsewhere in the file. Heading
        # uses the word-form of the current tool count (nine, ten, ...);
        # search for whichever variant is live so the test doesn't
        # need editing every time a tool is added.
        section_start = -1
        for variant in (
            "### The eleven MCP tools",
            "### The ten MCP tools",
            "### The nine MCP tools",
        ):
            idx = claude.find(variant)
            if idx > 0:
                section_start = idx
                break
        assert section_start > 0, (
            "claude.md MCP-tools section not found — looked for "
            "'### The eleven/ten/nine MCP tools'. "
            "Principle #20 anchor moved, fix the test or restore the heading"
        )
        # Find the next ### heading or end-of-file
        next_section = claude.find("\n### ", section_start + 5)
        section = claude[section_start:next_section if next_section > 0 else None]
        doc_tools = set(re.findall(r'`([a-z_]+)\(', section))
        # Sanity: docs should list a substantive set (the 9 we know about).
        # If <5, the regex broke or section was emptied.
        assert len(doc_tools) >= 5, (
            f"claude.md MCP section parsed only {len(doc_tools)} tool "
            f"names — regex anchor broken? Got: {sorted(doc_tools)}"
        )
        # Symmetric difference: anything in one set but not the other
        # is a drift. Either docs added a phantom or code shipped a
        # tool the docs don't mention.
        phantoms = doc_tools - code_tools  # in docs, not in code
        unlisted = code_tools - doc_tools  # in code, not in docs
        assert not phantoms, (
            f"claude.md lists MCP tools that aren't in mcp_server.py: "
            f"{sorted(phantoms)}. Either remove from docs or add to code."
        )
        assert not unlisted, (
            f"mcp_server.py defines MCP tools that claude.md doesn't list: "
            f"{sorted(unlisted)}. Add to the '### The nine MCP tools' section."
        )

    def test_numeric_tool_count_claims_match_code(self):
        """The numeric MCP-tool count claim (`11 tools`, `11 total`, `exposes
        11 tools`, etc.) is duplicated across ≥7 surfaces — claude.md, README,
        product-spec, spec-v1, scale-plan, SKILL.md, launch-day docs. Today
        (launch day) four of them were stale together (`9 total`, `10 total`,
        `exposes 9 tools`, `1 launch-arc addition`). Principle #20: drift
        accumulates in the OLDEST surface; principle #21: public claims need
        regression guards at the surface that ships them.

        This test parses the actual tool count from mcp_server.py and asserts
        every numeric claim across docs matches.
        """
        mcp_server = REPO / "src" / "trinity_local" / "mcp_server.py"
        code = mcp_server.read_text(encoding="utf-8")
        actual_count = len(set(re.findall(r'\s+name="([a-z_]+)"', code)))
        # Sanity: there should be at least 6 (the v1.0 canonical).
        assert actual_count >= 6, (
            f"mcp_server.py only exposes {actual_count} tools; "
            "did the Tool() definitions move?"
        )

        # Surfaces that pin the count numerically. Each entry is (path,
        # regex with one capture group for the number). The regex must
        # match exactly the public phrasing on that surface — if a doc
        # is rewritten to use a different phrasing, update the regex here
        # rather than letting drift slip through.
        surfaces: list[tuple[Path, str]] = [
            (REPO / "claude.md", r"exposes (\d+) tools"),
            (REPO / "claude.md", r"The full public surface is \*\*(\d+) tools\*\*"),
            (REPO / "docs" / "spec-v1.md", r"### MCP tool surface \((\d+) total"),
            (REPO / "docs" / "spec-v1.md", r"Current ships (\d+)"),
            (REPO / "docs" / "product-spec.md", r"\b(\d+) total\b"),
            (REPO / "docs" / "launch-day" / "07_pricing_faq.md", r"all (\d+) MCP tools"),
            (REPO / "docs" / "launch-day" / "10_hn_faq_full.md", r"(\d+) tools total"),
            (REPO / "src" / "trinity_local" / "data" / "skills" / "trinity" / "SKILL.md",
             r"—\s*(\d+)\s*total\."),
            # README hero paragraph — earned 2026-05-16 when the README
            # claimed "10 tools" while claude.md and every other surface
            # said 11. The README is the most-read surface; locking it
            # closes the highest-blast-radius gap in the count drift.
            (REPO / "README.md", r"The MCP surface ships (\d+) tools"),
            (REPO / "docs" / "launch-package.md", r"cold-install \+ (\d+) MCP tools"),
        ]

        mismatches: list[str] = []
        for path, pattern in surfaces:
            text = path.read_text(encoding="utf-8")
            for m in re.finditer(pattern, text):
                claimed = int(m.group(1))
                if claimed != actual_count:
                    line = text[: m.start()].count("\n") + 1
                    mismatches.append(
                        f"{path.relative_to(REPO)}:{line} claims {claimed} "
                        f"but mcp_server.py exposes {actual_count}"
                    )

        assert not mismatches, (
            "MCP tool-count drift across surfaces:\n  "
            + "\n  ".join(mismatches)
            + f"\n\nCanonical count is {actual_count} "
            "(parsed from mcp_server.py Tool() definitions)."
        )


class TestMcpCanonicalSubsetCountClaims:
    """Iter #61 caught 4 separate stale claims about the **canonical v1.0
    subset** of MCP tools clustered in one section of claude.md:
    - Line 610 table cell: \"v1.0 canonical 6\" (actual: 5)
    - Section header line 617: \"### The eleven MCP tools\" (actual: 9)
    - Line 619 math: \"5 + 3 + 2 = 9\" with stale \"2 launch-arc\"
    - Line 626 lifecycle header: \"v1.0 canonical six\"

    The existing TestMcpToolNameConsistency guard pins TOTAL tool counts
    against mcp_server.py but doesn't catch claims about the CANONICAL
    SUBSET (5 v1.0 tools) or the \"eleven MCP tools\" section-header
    drift. Future contributors could re-introduce \"canonical 6\" or
    \"canonical seven\" without any guard catching it.

    Principle #21: every fixed drift gets a regression guard at the
    surface it ships from. The canonical-5 claim is load-bearing in
    claude.md (lifecycle order + section structure); locking it shut
    means no future numeric drift in that section can ship silently.
    """

    def test_no_stale_canonical_count_phrasings_in_docs(self):
        # Drift-known-bad phrasings that should NEVER appear (these were
        # the iter #61 stale values + their plural-word forms).
        forbidden = [
            "canonical 6",  # iter #61 fix
            "canonical six",  # iter #61 fix
            "canonical 7",  # would mean we re-added a tool to the v1.0 subset
            "canonical seven",
            "canonical 4",  # would mean we lost a v1.0 tool
            "canonical four",
            "### The eleven MCP",  # iter #61 fix (section header)
            "### The ten MCP",
            "### The eight MCP",
            "1 launch-arc additions",  # singular/plural mismatch — "1 addition"
            "2 launch-arc addition",
            "0 launch-arc addition",
        ]
        docs_to_check = [
            REPO / "claude.md",
            REPO / "docs" / "spec-v1.md",
            REPO / "docs" / "product-spec.md",
        ]
        violations: list[str] = []
        for path in docs_to_check:
            if not path.exists():
                continue
            text = path.read_text(encoding="utf-8")
            for phrase in forbidden:
                if phrase in text:
                    line = text[: text.index(phrase)].count("\n") + 1
                    violations.append(
                        f"{path.relative_to(REPO)}:{line} contains "
                        f"forbidden stale phrasing {phrase!r}"
                    )
        assert not violations, (
            "MCP canonical-subset claims drifted to known-bad values "
            "(iter #61 catch shape):\n  " + "\n  ".join(violations)
            + "\n\nThe canonical v1.0 subset is 5 tools (route, "
            "run_council, record_outcome, get_persona, get_council_status). "
            "Total MCP surface is 9. If either changed, update both this "
            "test and the docs."
        )

    def test_canonical_count_claims_in_claude_md_agree(self):
        # All "v1.0 canonical (\d+)" claims in claude.md must agree
        # with each other AND with the literal "five" lifecycle header.
        claude = (REPO / "claude.md").read_text(encoding="utf-8")
        numeric_claims = re.findall(r"v1\.0 canonical (\d+)", claude)
        word_claims = re.findall(r"v1\.0 canonical (five|six|seven|eight)", claude)
        assert numeric_claims, (
            "claude.md has no 'v1.0 canonical (\\d+)' claims — did the "
            "MCP section get restructured? Update this test."
        )
        word_to_num = {"five": 5, "six": 6, "seven": 7, "eight": 8}
        nums = {int(n) for n in numeric_claims} | {
            word_to_num[w] for w in word_claims
        }
        assert nums == {5}, (
            f"claude.md has mixed 'v1.0 canonical' counts: {sorted(nums)}. "
            "All must agree on 5 (the v1.0 canonical subset size). "
            "Same shape as iter #61 catch — drift between adjacent lines."
        )


class TestCitedCouncilArtifactsExistInRepo:
    """Launch-artifact integrity guard. docs/launch.md and the README
    cite specific council_<hex>.json files as proof artifacts ("the
    outcome is in the repo"). If those files only live in ~/.trinity/
    and not under state/council_outcomes/, HN readers and journalists
    clicking through to verify hit a 404 — the proof claim doesn't
    survive contact with the launch audience.

    This guard scans launch-facing markdown for `council_<hex>` refs
    and asserts each cited council exists in state/council_outcomes/.
    Caught one real drift at T-1: council_d55953003bb29f9d was
    referenced in launch.md but not copied into the repo. Without
    the guard, future launch-copy edits citing new councils could
    drift the same way and only surface when a reader clicks.
    """

    def test_council_refs_in_launch_docs_exist_in_repo(self):
        launch_docs = [
            REPO / "docs" / "launch.md",
            REPO / "docs" / "launch-package.md",
            REPO / "README.md",
        ]
        # Launch-cited councils live under docs/launch_councils/ — a
        # non-gitignored public directory (state/ is reserved for
        # personal state and is .gitignore'd). Anyone copying a
        # council outcome here is signaling "this is published and
        # the launch copy may link to it."
        repo_council_dir = REPO / "docs" / "launch_councils"
        # Whitelist: councils mentioned for historical context (e.g.
        # spec-ratifying councils in claude.md) that aren't load-
        # bearing for the launch-facing surfaces. claude.md is NOT
        # in the scan list — it's the agent-context file, not the
        # public-facing launch artifact set. Reference councils in
        # claude.md that don't exist in-repo are fine because
        # claude.md isn't what HN readers click.
        cited_ids: set[str] = set()
        for path in launch_docs:
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            # Match the canonical `council_<16-hex>` pattern; ignore
            # references to fake/template IDs in code-fence examples.
            for hit in re.findall(r"council_([0-9a-f]{16})", text):
                cited_ids.add(hit)
        if not cited_ids:
            # Surfaces no cited councils — guard is a no-op (still
            # catches a future addition because cited_ids will fill).
            return
        missing: list[str] = []
        for council_id in sorted(cited_ids):
            json_path = repo_council_dir / f"council_{council_id}.json"
            if not json_path.exists():
                missing.append(council_id)
        assert not missing, (
            f"launch.md/README/launch-package cites council_<id> files "
            f"that aren't in docs/launch_councils/: {missing}. HN "
            f"readers clicking to verify the claim hit a 404. Either "
            f"copy ~/.trinity/council_outcomes/council_<id>.json into "
            f"docs/launch_councils/, OR remove the cite from the "
            f"launch copy."
        )


# TestInstallSmokeTracksMcpTools removed in T10b (proactive test-orphan hunt).
# The class enforced parity between scripts/smoke_install.sh's hardcoded
# canonical MCP tool set and test_mcp_tools.py's canonical set. Both
# scripts/smoke_install.sh and scripts/smoke_install_macvm.sh were deleted
# in commit 8469c6e (the curl|sh pivot — wheel-build smoke is no longer
# Trinity's distribution path). The guard self-skipped on OSError so it
# became silently dead code; removed here to keep the suite honest.
# If a future install-smoke script returns, restore from git history of
# this file at any commit before T10b's removal.


class TestGithubUrlOwnerConsistency:
    """Single-owner guard. Launch-facing docs and the install scripts
    reference `github.com/<owner>/trinity-local` as the canonical
    install URL. The owner field is load-bearing for the
    `git clone` command and the `pip install git+https://...` install
    path — a wrong owner segment produces a 404, and that lands as
    the user's FIRST experience after they copy the README command.

    Caught at T-1: README's quickstart used `github.com/openclaw/...`
    while launch.md, launch-package.md, and MCP_REGISTRY_SUBMISSIONS
    used `github.com/vishigondi/...` (the actual remote). The clone
    command in README would have 404'd for every reader copy-pasting
    it tomorrow morning.

    This guard scans launch-facing docs for any `github.com/.../
    trinity-local` reference and asserts the owner segment matches
    the canonical one — read from this repo's actual `git remote -v`
    output so the guard tracks reality without needing a hardcoded
    constant in two places (which would just create new drift).
    """

    def _canonical_owner(self) -> str | None:
        """Parse the remote URL for the owner. Returns None if no
        remote configured (e.g., on a fresh clone without push perms).
        """
        import subprocess
        try:
            result = subprocess.run(
                ["git", "-C", str(REPO), "remote", "get-url", "origin"],
                capture_output=True, text=True, check=False,
            )
        except FileNotFoundError:
            return None
        if result.returncode != 0:
            return None
        url = result.stdout.strip()
        m = re.search(r"github\.com[:/]([^/]+)/trinity-local", url)
        return m.group(1) if m else None

    def test_no_wrong_owner_in_launch_docs(self):
        canonical = self._canonical_owner()
        if canonical is None:
            # Can't determine canonical without a remote — skip rather
            # than fail in CI environments without git config.
            return
        scan_paths = [
            REPO / "README.md",
            REPO / "docs" / "launch.md",
            REPO / "docs" / "launch-package.md",
            REPO / "docs" / "MCP_REGISTRY_SUBMISSIONS.md",
        ]
        wrong: list[tuple[str, int, str]] = []
        for path in scan_paths:
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for lineno, line in enumerate(lines, 1):
                # Match any github.com/<owner>/trinity-local reference.
                # Allow http(s):// prefix, raw github.com, or backtick-
                # wrapped forms — all surface the same owner string.
                for m in re.finditer(
                    r"github\.com[:/]([\w.-]+)/trinity-local", line
                ):
                    owner = m.group(1)
                    if owner != canonical:
                        wrong.append((path.name, lineno, owner))
        assert not wrong, (
            f"Wrong GitHub owner in launch-facing docs (canonical = "
            f"{canonical!r} from `git remote get-url origin`):\n"
            f"  {wrong}\n"
            f"Users copying these URLs hit a 404. Fix to {canonical}/"
            f"trinity-local in every cited location."
        )


class TestCliCommandsReferencedExistInCli:
    """Stale-subcommand guard. Every `trinity-local <subcmd>` mentioned
    in launch-facing copy must resolve to a real subcommand in the CLI.

    Caught the missing-subcommand class at T-1 by accident — `me-build`
    was renamed to `lens-build` per task #91, but a scan for "subcommands
    in launch docs that aren't in the CLI" found `me-build` references
    in CHANGELOG (legitimate: historical rename documentation). The
    launch-facing surfaces (README/launch.md/MCP_REGISTRY) were already
    clean. Promoting to a guard so the next rename doesn't slip through.

    The guard:
      - Loads the real subcommand list from `trinity-local --help`
      - Scans launch-facing docs (NOT CHANGELOG — that's commit history
        and legitimately mentions renamed commands)
      - For each `trinity-local <kebab-cmd>` pattern in those docs,
        asserts the subcommand is registered

    CHANGELOG is excluded because its job is to document the
    PRE-rename state for migration context. Treating CHANGELOG
    references as live would force rename-time edits to a file
    that's meant to be append-only history.
    """

    @staticmethod
    def _real_subcommands() -> set[str]:
        """The live argparse surface, including subparsers hidden from
        `--help` via Area 5 CLI consolidation.

        Was: parsed `trinity-local --help` for the {cmd1,cmd2,...}
        metavar. That broke when CLI consolidation collapsed the help-
        visible surface to {install,status,update,dream,debug} — the
        hidden commands (council-launch, install-mcp, ingest-recent,
        etc.) stay registered + callable + LEGITIMATELY referenced in
        docs, but `--help` no longer lists them.

        Now: build the parser in-process and read `subparsers.choices`
        directly. That's the full set of registered subparsers — same
        thing the launchpad and the Chrome extension dispatch by name."""
        import argparse
        try:
            from trinity_local.main import build_parser
        except ImportError:
            # Package not importable in this env — return empty set
            # and let the test skip via early-return.
            return set()
        try:
            parser = build_parser()
        except Exception:
            return set()
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                return set(action.choices.keys())
        return set()

    def test_subcommands_in_launch_docs_resolve(self):
        real = self._real_subcommands()
        if not real:
            return  # CLI not on PATH in this env — skip gracefully
        launch_docs = [
            REPO / "README.md",
            REPO / "docs" / "launch.md",
            REPO / "docs" / "launch-package.md",
            REPO / "docs" / "MCP_REGISTRY_SUBMISSIONS.md",
            # claude.md added 2026-05-16 after the architecture-table
            # row for `model_detector.py` / `trinity-local models-detect`
            # turned out to reference a module + a CLI command that
            # never existed in the codebase. The guard scanned launch
            # docs but not claude.md; users following the project-
            # context file hit a phantom command. Adding claude.md
            # closes that surface.
            REPO / "claude.md",
            # CHANGELOG.md deliberately excluded — historical context.
        ]
        # Pattern: `trinity-local <kebab-cmd>` where <kebab-cmd> is
        # all lowercase + hyphens. Excludes connecting words.
        cmd_re = re.compile(r"trinity-local\s+([a-z][a-z-]+[a-z])")
        # Common false positives — natural-language continuations of the
        # phrase, NOT subcommands. Add here if a real prose pattern
        # is otherwise mis-flagged.
        not_subcommands = {
            "and", "will", "is", "has", "on", "the", "now", "to",
            "from", "into", "after", "before", "as", "for", "with",
        }
        ghosts: list[tuple[str, int, str]] = []
        for path in launch_docs:
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for lineno, line in enumerate(lines, 1):
                for m in cmd_re.finditer(line):
                    cmd = m.group(1)
                    if cmd in not_subcommands or cmd in real:
                        continue
                    ghosts.append((path.name, lineno, cmd))
        assert not ghosts, (
            f"Launch-facing docs reference subcommands that the CLI "
            f"doesn't have: {ghosts}. Likely a rename without doc "
            f"update (task #91 shape — me-build → lens-build, etc). "
            f"Either update the doc to the new name, or add the "
            f"subcommand back if removal was unintentional. Live "
            f"subcommands: {sorted(real)[:10]}... (+{len(real)-10} more)"
        )


class TestArchitectureTableModulesExist:
    """Companion to TestCliCommandsReferencedExistInCli (CLI side):
    every backticked `<name>.py` in claude.md's architecture tables
    must resolve to a real file in src/ or tests/. Catches the
    phantom-module shape that bit us 2026-05-16 with
    `model_detector.py` (named in claude.md, no file anywhere).

    Allowlist exists for files explicitly documented as
    not-shipping (per Principle #20, docs can reference
    historical-state filenames with explanatory context).
    """

    # Files claude.md references with an explicit "doesn't exist /
    # didn't materialize" note. Adding here is OK when the doc text
    # makes the absence unambiguous to a reader.
    DOCUMENTED_ABSENT = {
        # "subprocess_utils.py was the original plan but the split
        # didn't materialize" — claude.md narrates this directly
        # near the runtime_env row.
        "subprocess_utils.py",
        # Retired 2026-05-17 with the macOS Shortcut dispatcher kill
        # — claude.md's Dispatch row narrates the retirement directly.
        "dispatch_runner.py",
        "shortcut_setup.py",
    }

    def test_no_phantom_py_files_in_claude_md(self):
        claude_md = (REPO / "claude.md").read_text(encoding="utf-8")
        # Find every backticked `<name>.py` reference. Bare filename
        # form only; the architecture table uses this shape
        # consistently. Path-form refs (subdir/file.py) skipped —
        # the recursive search resolves them regardless.
        files = set(re.findall(r"`([a-z_][a-z_0-9]*\.py)`", claude_md))

        # Recursive search: a referenced filename is valid if it
        # exists ANYWHERE under src/ or tests/. The architecture
        # table mentions `base.py` etc. as living under `ranker/`,
        # but claude.md writes the bare name — search has to
        # tolerate that.
        searchable = [REPO / "src", REPO / "tests"]
        phantoms: list[str] = []
        for name in sorted(files):
            if name in self.DOCUMENTED_ABSENT:
                continue
            found = False
            for root in searchable:
                if any(root.rglob(name)):
                    found = True
                    break
            if not found:
                phantoms.append(name)

        assert not phantoms, (
            "claude.md architecture table references .py files that "
            "don't exist anywhere in src/ or tests/:\n  "
            + "\n  ".join(phantoms)
            + "\n\nEither restore the file (the rename was unintended) "
            "or remove the row from claude.md (the feature didn't "
            "land). If absence is intentional + documented, add the "
            "filename to TestArchitectureTableModulesExist."
            "DOCUMENTED_ABSENT with a one-line context note."
        )


class TestReadmeHeroInstallCommand:
    """README-hero install-command guard. Narrow scope: ONLY the
    README hero section (first 25 lines) — the most-visible install
    affordance, the literal first command a user types after landing
    on GitHub. Other launch-copy references (launch.md tweets,
    MCP_REGISTRY_SUBMISSIONS, embedded HN post) ship AFTER PyPI
    publish lands, so the canonical `pip install trinity-local` is
    correct in those surfaces.

    The hero is different: it's read BEFORE the user knows whether
    PyPI publish has happened. If it 404s, that's the first impression.
    Verified at T-1: `trinity-local` package is NOT on PyPI
    (https://pypi.org/pypi/trinity-local/json → 404). So the hero
    must use the git+https:// form OR an explicit caveat.

    Once PyPI publish lands at v1.0 ship, the README hero can revert
    to the naked form; remove this guard at the same time.
    """

    NAKED_PIP_INSTALL = re.compile(
        r"\bpip\s+install\s+trinity-local\b(?!\s*[/=<>!])"
    )
    CAVEAT_MARKERS = (
        "post-ship",
        "after v1.0",
        "after publish",
        "after ship",
        "after that",
        "until then",
        "until pypi",
        "until v1.0",
        "pre-pypi",
        "pre pypi",
    )

    def test_skill_install_commands_work_today(self):
        """The bundled `/trinity` skill is the install path for users
        who hit Claude Code without seeing the README first. Its
        install commands (pipx/pip --user/venv) must work today too
        — same PyPI-404 shape as the README hero, different surface.

        Caught at T-1: the skill's three install attempts all named
        `trinity-local` (PyPI 404). Anyone typing `/trinity` in a
        fresh Claude Code session would have hit
        "ERROR: No matching distribution found for trinity-local"
        before any of Trinity's actual functionality could load.
        """
        skill = REPO / "src" / "trinity_local" / "data" / "skills" / "trinity" / "SKILL.md"
        try:
            text = skill.read_text(encoding="utf-8")
        except OSError:
            return
        leaks: list[str] = []
        for line_idx, line in enumerate(text.splitlines(), 1):
            # Skip caveat-bearing lines (Post-ship: ..., etc.) AND
            # the allowed-tools frontmatter (wildcard, not a literal
            # install). Code-fence semantics don't apply here since
            # the skill body IS the install commands.
            if line.startswith("allowed-tools:"):
                continue
            if any(marker in line.lower() for marker in self.CAVEAT_MARKERS):
                continue
            if not self.NAKED_PIP_INSTALL.search(line):
                continue
            leaks.append(f"line {line_idx}: {line.strip()[:80]}")
        assert not leaks, (
            f"Bundled /trinity SKILL.md has naked `pip install "
            f"trinity-local` commands (PyPI 404s pre-launch): "
            f"{leaks}. Update to `git+https://github.com/vishigondi/"
            f"trinity-local` or add an explicit caveat phrase nearby."
        )

    def test_readme_hero_install_works_today(self):
        readme = REPO / "README.md"
        try:
            lines = readme.read_text(encoding="utf-8").splitlines()
        except OSError:
            return
        # Hero region = the first 25 lines (above the body sections).
        # The actual hero install line is around line 8; widen the
        # window to be tolerant of small layout shifts without
        # tracking every commit.
        hero = lines[:25]
        leaks: list[tuple[int, str]] = []
        for idx, line in enumerate(hero, 1):
            if not self.NAKED_PIP_INSTALL.search(line):
                continue
            # Allow when the immediate window mentions a caveat.
            window_lo = max(0, idx - 3)
            window_hi = min(len(hero), idx + 3)
            window = " ".join(hero[window_lo:window_hi]).lower()
            if any(marker in window for marker in self.CAVEAT_MARKERS):
                continue
            leaks.append((idx, line.strip()[:80]))
        assert not leaks, (
            f"README hero (first 25 lines) carries a naked "
            f"`pip install trinity-local` command, but PyPI 404s "
            f"pre-launch: {leaks}. The README hero is the FIRST "
            f"command a reader types. Use "
            f"`pip install git+https://github.com/vishigondi/trinity-local` "
            f"or wrap the naked form with a caveat phrase like "
            f"'(After v1.0 ship: pip install trinity-local)'."
        )

    def test_launch_demo_script_install_commands_work_today(self):
        """The 60-second demo scripts in docs/launch.md (lines starting
        with `0:00–0:08  CLI: ...`) are RECORDING INSTRUCTIONS — the
        user types these commands during the T-1 recording session,
        before the launch's PyPI publish has happened. A bare
        `pip install trinity-local` at the install timecode means the
        recorder hits the 404 on camera.

        Caught at T-1: both demo variants (handoff PRIMARY at line ~239
        and council ALTERNATE at line ~266) used the bare form. Fixed
        with the git+https URL form + an explicit RECORDING NOTE
        explaining that the published video can show either form since
        they're identical from the viewer's POV.

        The published TWEET copy (line ~76 in the 'Install (10/12)'
        beat) is correctly left as the bare form — that text ships
        AFTER PyPI publish, so the canonical form is right there.
        Distinction: 'demo recording timecode' (typed pre-PyPI) vs
        'tweet body' (read post-PyPI).
        """
        launch_md = REPO / "docs" / "launch.md"
        try:
            text = launch_md.read_text(encoding="utf-8")
        except OSError:
            return
        # Find every `0:NN-0:NN  CLI: <something>` recording-timecode
        # line. The timecode pattern is the anchor.
        timecode_re = re.compile(r"^\s*\d:\d\d.\d:\d\d\s+CLI:\s*(.+)$", re.MULTILINE)
        leaks: list[str] = []
        for m in timecode_re.finditer(text):
            cmd = m.group(1)
            if not self.NAKED_PIP_INSTALL.search(cmd):
                continue
            # The git+https form passes; bare form fails. Allow any
            # caveat marker in the same line OR within 5 lines below
            # (the "RECORDING NOTE" pattern this guard accepts).
            line_start = m.start()
            window_lo = max(0, text.rfind("\n", 0, line_start) - 1)
            # Window: this line + next 5 lines after the match
            window_hi = m.end()
            for _ in range(5):
                nxt = text.find("\n", window_hi + 1)
                if nxt < 0:
                    break
                window_hi = nxt
            window = text[window_lo:window_hi].lower()
            if any(marker in window for marker in self.CAVEAT_MARKERS):
                continue
            leaks.append(cmd.strip()[:80])
        assert not leaks, (
            f"Demo-recording timecodes in docs/launch.md use naked "
            f"`pip install trinity-local` (PyPI 404s when the recorder "
            f"types this on camera at T-1): {leaks}. Use the git+https "
            f"form OR add a 'RECORDING NOTE: post-ship pip install ...' "
            f"caveat within 5 lines so the recorder can use either."
        )

    def test_founder_essay_install_command_works_today(self):
        """The founder essay ships to the personal blog at T-7
        (per launch-package). Readers of the essay see install
        commands and copy-paste them — same shape as the README
        hero, different surface. Caught a `pip install trinity-local`
        near the close of the essay at T-1 — the essay's most-quoted
        line ("Three commands. Free forever.") sits right next to
        a command that would 404 on a fresh user."""
        essay = REPO / "docs" / "founder-essay-draft.md"
        try:
            lines = essay.read_text(encoding="utf-8").splitlines()
        except OSError:
            return  # essay absent — guard is a no-op
        leaks: list[tuple[int, str]] = []
        for idx, line in enumerate(lines, 1):
            if not self.NAKED_PIP_INSTALL.search(line):
                continue
            # Allow caveat-bearing windows (a 5-line window each side
            # — essay prose has longer paragraphs than the README hero).
            window_lo = max(0, idx - 5)
            window_hi = min(len(lines), idx + 5)
            window = " ".join(lines[window_lo:window_hi]).lower()
            if any(marker in window for marker in self.CAVEAT_MARKERS):
                continue
            leaks.append((idx, line.strip()[:80]))
        assert not leaks, (
            f"docs/founder-essay-draft.md has naked `pip install "
            f"trinity-local` (PyPI 404s pre-launch): {leaks}. The "
            f"essay ships to the personal blog at T-7 — readers "
            f"copy-pasting hit the 404 as the install instruction's "
            f"first command. Use the git+https form or wrap with a "
            f"'Post-ship:' caveat."
        )


class TestDroppedTermsAreNotReintroduced:
    """Task #94 dropped "verifier" as Trinity's own terminology in
    favor of "chairman synthesizer" / "Synthesis JSON" — the chairman
    SYNTHESIZES, not verifies. The rename's marketing rationale: the
    chairman writes a structured verdict (the synthesis), it doesn't
    just check a precondition. "Synthesis" carries the productive
    framing; "verifier" carries the gatekeeper framing.

    T-1 catch: README:346 still said "The chairman model is the
    verifier" — a single line that survived the rename pass. Subtle
    enough that readers wouldn't flag it as a bug; loud enough that
    a future HN comment-thread on the docs would call it out.

    The guard scans launch-facing prose (README, launch.md,
    launch-package.md, MCP_REGISTRY_SUBMISSIONS) for "verifier"
    used in Trinity's own voice. EXCLUDED: research-context
    references (LLM-Blender's "generator-verifier asymmetry," etc.)
    are legitimate citations in product-spec.md but shouldn't appear
    in user-facing launch copy. product-spec.md is not in the scan
    set because it's the architecture deep-dive doc, not launch
    prose — research framings belong there.

    Word-boundary regex catches "verifier" as a standalone token but
    allows compound terms ("verification" is fine; "verifier-style"
    in a hypothetical compound noun is flagged — likely intentional).
    """

    DROPPED_TERMS = {
        # term → human-readable rationale for the rename
        "verifier": (
            "task #94 dropped 'verifier' in Trinity's own voice; "
            "use 'chairman synthesizer' or 'Synthesis JSON'"
        ),
    }

    def test_no_dropped_terms_in_launch_copy(self):
        launch_docs = [
            REPO / "README.md",
            REPO / "docs" / "launch.md",
            REPO / "docs" / "launch-package.md",
            REPO / "docs" / "MCP_REGISTRY_SUBMISSIONS.md",
        ]
        leaks: list[tuple[str, int, str, str]] = []
        for path in launch_docs:
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for lineno, line in enumerate(lines, 1):
                for term, rationale in self.DROPPED_TERMS.items():
                    # Word-boundary match — "verifier" matches but
                    # "verification" / "verifies" don't.
                    if re.search(rf"\b{term}\b", line):
                        leaks.append((path.name, lineno, term, rationale))
                        break
        assert not leaks, (
            f"Launch-facing docs reintroduced terminology Trinity "
            f"deliberately dropped: {leaks}. Each rename had a "
            f"marketing rationale — reverting to the old term in "
            f"launch copy silently undoes the brand-pivot work."
        )


class TestLaunchpadScreenshotFreshness:
    """The README + launch-package reference `docs/launchpad_example.png`
    as the canonical launchpad screenshot. Anyone clicking through from
    the README hero section to see what Trinity looks like reads from
    THIS file. If it's stale, the launchpad they see doesn't match the
    launchpad they'd get after install.

    T-1 catch: the screenshot was 6 days old. Since then Trinity added
    Surface 30 (3-provider leaderboard), Surface 32 (rate-limit-saves
    card), and several launch-arc surfaces. The stale screenshot would
    have shown a meaningfully thinner launchpad than the one a fresh
    install produces — false advertising for the launch-arc work.

    Same shape applies to docs/me_card_example.png (the OTHER Product
    Hunt asset named in launch-package): the example PNG can drift
    behind the rendering source (me_card.py) if rendering changes ship
    without re-running me-card. Both assets are guarded here.

    Guard: assert each asset's mtime isn't grossly older (>3 days) than
    the source files that drive its rendering. Threshold is generous —
    only catches true drift, not normal edit churn.
    """

    STALE_THRESHOLD_DAYS = 3

    def _assert_asset_fresh(self, asset_relpath: str, driver_relpaths: list[str], regen_recipe: str):
        asset = REPO / asset_relpath
        if not asset.exists():
            return  # not yet generated — guard is a no-op
        asset_mtime = asset.stat().st_mtime
        stale_drivers: list[tuple[str, float]] = []
        for rel in driver_relpaths:
            path = REPO / rel
            if not path.exists():
                continue
            src_mtime = path.stat().st_mtime
            age_days = (src_mtime - asset_mtime) / 86400
            if age_days > self.STALE_THRESHOLD_DAYS:
                stale_drivers.append((path.name, age_days))
        assert not stale_drivers, (
            f"{asset_relpath} is grossly stale relative to its rendering "
            f"source files: {stale_drivers}. Regenerate via: {regen_recipe}"
        )

    def test_launchpad_example_not_grossly_stale(self):
        self._assert_asset_fresh(
            "docs/launchpad_example.png",
            [
                "src/trinity_local/launchpad_template.py",
                "src/trinity_local/launchpad_data.py",
            ],
            regen_recipe=(
                "trinity-local portal-html && trinity-local serve & "
                "python scripts/browser_smoke.py && "
                "cp docs/smoke/1-launchpad.png docs/launchpad_example.png"
            ),
        )

    def test_me_card_example_not_grossly_stale(self):
        """me-card PNG is the OTHER Product Hunt asset (named in
        launch-package alongside the launchpad screenshot + demo
        video). T-1 catch: the example PNG was 6 days behind the
        me_card.py rendering source, so the example didn't show what
        `trinity-local me-card` actually produces today."""
        self._assert_asset_fresh(
            "docs/me_card_example.png",
            [
                "src/trinity_local/me_card.py",
                "src/trinity_local/commands/me_card.py",
            ],
            regen_recipe=(
                "trinity-local me-card --out docs/me_card_example.png"
            ),
        )


class TestBrandAxisConsistency:
    """Hero + sub line must read identically across launch-facing
    surfaces. Each surface independently quotes them; a copy edit
    that only touches one surface silently drifts the others.

    launch-package.md's 'locked positioning' section is the canonical
    source of truth. Other surfaces (README hero, launch.md tweet
    thread header, claude.md status block) must carry the EXACT same
    hero + sub strings.

    Verified manually at T-1 across 5 surfaces; promoting to a guard
    so a future brand-pivot rename (or even a small word change in
    one surface) fails the suite instead of shipping inconsistent
    copy to readers.

    Hero: 'Stop copy-pasting prompts. Own your context. Dream your core memories.'
    Sub:  'One question. Every model you use. One answer that knows you.'

    Both pinned by exact substring match — punctuation matters
    (em-dashes, periods, capitalization).
    """

    # Brand pivot 2026-05-16 → "Your taste, ported." Iter #33 swept
    # the live launchpad UI (the last surface carrying the old hero
    # in product code); iter #34 verified zero pre-pivot tagline
    # fragments remain anywhere in src/. Locked the new framing here
    # — guard now FAILS if any launch surface reverts to the old
    # hero or invents a third one. Historical references in claude.md
    # / CHANGELOG / docs/launch_councils/ are unaffected (they don't
    # need to carry an accepted hero verbatim; they just describe
    # the history).
    ACCEPTED_HEROES: list[str] = [
        "Your taste, ported.",
    ]
    ACCEPTED_SUBS: list[str] = [
        "No new app. No service. No API key.",
    ]

    SURFACES_CARRYING_HERO = [
        REPO / "README.md",
        REPO / "docs" / "launch.md",
        REPO / "docs" / "launch-package.md",
        REPO / "claude.md",
        # Added 2026-05-19 (iter #71) after iter #70 caught spec-v1.md
        # still carrying pre-pivot hero+sub three days post-pivot. The
        # spec doc is the load-bearing v1 contract; a careful HN reader
        # following links from launch copy lands here. Locking it shut
        # converts that drift into commit-time work.
        REPO / "docs" / "spec-v1.md",
    ]

    SURFACES_CARRYING_SUB = [
        REPO / "README.md",
        REPO / "docs" / "launch.md",
        REPO / "docs" / "launch-package.md",
        REPO / "claude.md",
        # Same shape as the hero list — added 2026-05-19 (iter #71).
        REPO / "docs" / "spec-v1.md",
    ]

    def test_hero_appears_verbatim_in_each_launch_surface(self):
        missing: list[str] = []
        for path in self.SURFACES_CARRYING_HERO:
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            if not any(h in text for h in self.ACCEPTED_HEROES):
                missing.append(path.name)
        assert not missing, (
            f"Hero line missing from launch surfaces: {missing}. "
            f"Each surface must carry AT LEAST ONE accepted hero: "
            f"{self.ACCEPTED_HEROES!r}. During brand transition both "
            f"old + new are accepted; when propagation completes, "
            f"drop the old one from ACCEPTED_HEROES to lock the new "
            f"framing in."
        )

    def test_sub_appears_verbatim_in_each_launch_surface(self):
        missing: list[str] = []
        for path in self.SURFACES_CARRYING_SUB:
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            if not any(s in text for s in self.ACCEPTED_SUBS):
                missing.append(path.name)
        assert not missing, (
            f"Sub line missing from launch surfaces: {missing}. "
            f"Each surface must carry AT LEAST ONE accepted sub: "
            f"{self.ACCEPTED_SUBS!r}."
        )


class TestNoUnregisteredVanityDomains:
    """Vanity-domain guard. Earlier launches considered using
    `trinity.local` as a vanity URL for the Teams waitlist page; the
    domain doesn't resolve (NXDOMAIN) and standing it up needs
    registrar + DNS + hosting work. Likewise `trinity-local.dev` was
    once the schema $id host (fixed in e64408d). Any future
    introduction of these or similar vanity domains as CLICKABLE
    links in launch copy would 404 for readers — same shape as the
    schema $id catch.

    T-1 catch: README line 137 had ``[trinity.local/teams](https://
    trinity.local/teams)`` as the Teams waitlist link. Verified
    trinity.local is NXDOMAIN. Replaced with GitHub Discussions link
    (which works the moment the repo flips public).

    Allowed contexts:
      - References inside test files (this file scans for them)
      - References inside CHANGELOG.md (documents the rename history)
      - References inside docs/PREFERENCE_CORPUS_SPEC.md (deferred,
        post-publish state allowed)

    Blocked contexts (must NOT contain unregistered vanity domains):
      - README.md (read pre-publish by anyone clicking through)
      - docs/launch.md (the tweet thread + HN copy)
      - docs/launch-package.md (the launch playbook)
      - docs/founder-essay-draft.md (ships to personal blog T-7)
    """

    BLOCKED_DOMAINS = [
        "trinity-local.dev",
        # NOT trinity.local — that's the mDNS .local TLD which appears
        # in legitimate contexts (mDNS, local network refs). Only flag
        # when used as a URL host: https://trinity.local/...
    ]

    def test_no_unregistered_vanity_domains_in_launch_copy(self):
        launch_docs = [
            REPO / "README.md",
            REPO / "docs" / "launch.md",
            REPO / "docs" / "launch-package.md",
            REPO / "docs" / "founder-essay-draft.md",
            # All docs/launch-day/*.md ship publicly as the tweet thread /
            # HN opener / pricing one-pager — coverage gap caught when
            # `trinity.local/install.sh` slipped through in tweet thread
            # lines 11, 72 + HN post line 19 (commit 5605d36 found this
            # via 4-agent audit; the original guard only covered launch.md
            # not the per-day launch-day directory).
            *sorted((REPO / "docs" / "launch-day").glob("*.md")),
        ]
        leaks: list[tuple[str, int, str]] = []
        for path in launch_docs:
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for lineno, line in enumerate(lines, 1):
                # Match `trinity.local/...` with or without protocol —
                # the bare-host shape (`curl trinity.local/install.sh`)
                # is the most dangerous because it's CLICK-EQUIVALENT
                # (the reader copy-pastes the command). The optional
                # `https?://` prefix is in the same match so we don't
                # need a variable-width lookbehind (which Python re
                # doesn't support).
                for m in re.finditer(r"(?:https?://)?trinity\.local/[A-Za-z0-9_./-]+", line):
                    # Allow lines that explicitly document the URL as
                    # historical / deferred / removed — same allowlist
                    # the BLOCKED_DOMAINS check uses below. Without
                    # this, the guard can't distinguish "shipping copy
                    # promises this URL" from "doc explains we dropped
                    # this URL in favor of GitHub-native channel."
                    lower = line.lower()
                    if any(marker in lower for marker in (
                        "earlier plan",
                        "deferred",
                        "removed",
                        "sunset",
                    )):
                        continue
                    leaks.append((path.name, lineno, m.group(0)))
                for blocked in self.BLOCKED_DOMAINS:
                    if blocked in line:
                        # Allow if the line is explicitly documenting
                        # the rename ("was trinity-local.dev, now ...").
                        lower = line.lower()
                        if any(marker in lower for marker in (
                            "was trinity-local.dev",
                            "earlier: trinity-local.dev",
                            "deferred",
                            "removed",
                        )):
                            continue
                        leaks.append((path.name, lineno, blocked))
        assert not leaks, (
            f"Launch-facing docs reference unregistered/non-resolving "
            f"vanity domains: {leaks}. These 404 for any reader "
            f"clicking through. Use a working channel (GitHub repo, "
            f"PyPI, email at a real domain) or wrap with explicit "
            f"deferred-state language."
        )


class TestSchemaIdsResolveToReachableUrls:
    """Schema canonical-URL guard. The PREFERENCE_CORPUS_SPEC publishes
    three JSON Schema files (council_outcome, eval_set, rejection_
    signal) as a CC0 standard for other tools (Aider/Cline/Continue)
    to adopt. JSON Schema `$id` is the canonical resolver URL —
    consumers fetch the schema by $id to validate. If $id is a 404,
    the standardization workstream (#117) ships broken.

    T-1 catch: schemas had `$id` set to `https://trinity-local.dev/
    schemas/v1/...` but `trinity-local.dev` doesn't resolve (no DNS
    record). Any tool fetching by $id would get a connection refused.

    Fixed at T-1: switched to the GitHub raw URL form, which:
      - resolves today (the repo is public)
      - is the canonical "this is the source of truth" URL for any
        schema fetched from the trinity-local repo
      - no domain registration needed; tools fetch by https from
        GitHub's CDN

    Guard: every `$id` in schemas/ must use a URL that resolves to
    a file actually in the repo (the path component matches an
    existing schema file). Blocks future drift back to a vanity
    domain that isn't registered.
    """

    def test_schema_ids_use_github_raw_url_and_resolve_to_real_files(self):
        import json
        schemas_dir = REPO / "schemas"
        if not schemas_dir.exists():
            return
        leaks: list[tuple[str, str]] = []
        for path in schemas_dir.glob("*.schema.json"):
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                leaks.append((path.name, f"unparseable: {exc}"))
                continue
            schema_id = data.get("$id", "")
            if not schema_id:
                leaks.append((path.name, "missing $id"))
                continue
            # Pre-launch policy: $id must be a github.com/raw form, NOT
            # a vanity domain (which would need separate DNS + hosting).
            # Once trinity-local.dev is registered post-launch, the
            # vanity form can re-enter — update this guard at the same
            # commit so the policy is explicit.
            if "trinity-local.dev" in schema_id:
                leaks.append((path.name, f"uses unregistered vanity domain: {schema_id}"))
                continue
            if "raw.githubusercontent.com" not in schema_id:
                leaks.append((path.name, f"$id not on github raw: {schema_id}"))
                continue
            # The URL's path component must point at a file in schemas/
            # — same drift shape as the cited-council 404s but for
            # external-resolver URLs.
            # Pattern: raw.githubusercontent.com/<owner>/<repo>/<ref>/schemas/<file>
            m = re.search(r"/schemas/([\w.-]+\.schema\.json)$", schema_id)
            if not m:
                leaks.append((path.name, f"$id has no /schemas/<name> tail: {schema_id}"))
                continue
            referenced_file = schemas_dir / m.group(1)
            if not referenced_file.exists():
                leaks.append((path.name, f"$id references nonexistent file: {m.group(1)}"))
        assert not leaks, (
            f"Schema $id field issues: {leaks}. JSON Schema $id is the "
            f"canonical resolver URL — consumers (Aider, Cline, etc.) "
            f"fetch the schema by $id to validate. A 404 here breaks "
            f"the #117 standardization workstream. Use "
            f"https://raw.githubusercontent.com/vishigondi/trinity-local/main/"
            f"schemas/<name>.schema.json — works today, no domain "
            f"registration needed."
        )


class TestPyprojectMatchesLaunchVersion:
    """Version + description parity. Launch copy says "Trinity Local
    v1 ships open-source this week" but pyproject.toml had version =
    "0.1.0" at T-1. `pip show trinity-local` after install would
    have surfaced 0.1.0, contradicting the "v1" launch framing — an
    HN commenter spotting that discrepancy is the kind of thing
    that gets quoted out of context ("they said v1 but it says
    0.1.0?"). Description was also stale ("MLX and CLI agents on
    macOS" — pre-pivot copy).

    The guard:
      - Asserts the major version is 1.x (matches "v1 ships..." claim).
      - Asserts the description doesn't contain old-pitch wording
        ("MLX-style", "TRINITY-style coordinator") that pre-dates
        the brand pivot. The description shows up in pip show + on
        PyPI metadata — it's the package's elevator pitch.

    When v2 lands, bump the major-version assertion. When the
    description changes for v2 positioning, update the stale-pitch
    blocklist.
    """

    def test_pyproject_version_is_v1(self):
        pyproject = REPO / "pyproject.toml"
        try:
            text = pyproject.read_text(encoding="utf-8")
        except OSError:
            return
        m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
        assert m, "pyproject.toml lost its version field"
        version = m.group(1)
        major = version.split(".", 1)[0]
        assert major == "1", (
            f"pyproject.toml version is {version!r} but launch copy "
            f"says 'Trinity Local v1 ships...'. `pip show trinity-local` "
            f"after install would surface this mismatch. Update either "
            f"the version (to 1.x) or the launch claim (to '{major}.x ships')."
        )

    def test_launch_copy_pins_pyproject_minor_version(self):
        """Stricter version-parity check than `test_pyproject_version_is_v1`.

        The existing test only asserts major == '1' — passes for any
        v1.x. But H2 caught real drift: launch-package.md said "v1.0
        ships" while the actual ship was v1.7 (pyproject = 1.7.1). A
        reader pasted the v1.0 tweet would have copy-pasted a tag that
        doesn't exist.

        This guard reads pyproject.toml's `major.minor` (e.g. '1.7')
        and asserts `v1.7` appears verbatim in each of the four launch
        surfaces. When a future release bumps to v1.8, this fires
        until the launch copy is swept — exactly the gate the H2 bug
        wanted.
        """
        pyproject = REPO / "pyproject.toml"
        try:
            text = pyproject.read_text(encoding="utf-8")
        except OSError:
            return
        m = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
        assert m, "pyproject.toml lost its version field"
        parts = m.group(1).split(".")
        major_minor = f"v{parts[0]}.{parts[1]}"

        surfaces = {
            "launch.md": REPO / "docs" / "launch.md",
            "launch-package.md": REPO / "docs" / "launch-package.md",
            "01_tweet_thread.md": REPO / "docs" / "launch-day" / "01_tweet_thread.md",
            "README.md": REPO / "README.md",
        }
        missing = []
        for name, path in surfaces.items():
            try:
                doc = path.read_text(encoding="utf-8")
            except OSError:
                continue
            if major_minor not in doc:
                missing.append(name)
        assert not missing, (
            f"pyproject.toml ships as {major_minor} but launch surfaces "
            f"don't reference it: {missing}. Either bump pyproject or "
            f"sweep these files to match. Surfaces a reader sees first "
            f"must agree on the ships-today version number."
        )

    def test_pyproject_description_uses_current_brand(self):
        pyproject = REPO / "pyproject.toml"
        try:
            text = pyproject.read_text(encoding="utf-8")
        except OSError:
            return
        m = re.search(r'^description\s*=\s*"([^"]+)"', text, re.MULTILINE)
        assert m, "pyproject.toml lost its description field"
        desc = m.group(1)
        # Pre-brand-pivot phrases that should NOT appear post-pivot.
        # The pivot (#89) replaced "MLX and CLI agents on macOS" framing
        # with the prompts/dream/core-memories axis. Description shows
        # up in PyPI search and `pip show` — public-facing elevator pitch.
        stale_phrases = [
            "TRINITY-style coordinator",
            "MLX and CLI agents",
            "for MLX",  # variants
        ]
        leaks = [p for p in stale_phrases if p.lower() in desc.lower()]
        assert not leaks, (
            f"pyproject.toml description carries pre-brand-pivot "
            f"wording {leaks}: {desc!r}. The description ships to "
            f"PyPI as the package's elevator pitch. Update to the "
            f"current brand voice (cross-provider memory / councils / "
            f"handoff / Claude+GPT+Gemini)."
        )


class TestLaunchCopyHasNoPlaceholders:
    """T-1 lorem-ipsum guard. The launch surface accumulates `[date]`,
    `<github.com/...>`, `<repo>`, `[handle]`, `[name]`, and similar
    placeholder strings during drafting. When the user hits publish,
    those slots get filled in by hand — but it's easy to miss one,
    and shipping `Trinity Local v1 ships open-source [date]` as the
    literal tweet text is an unprofessional first-impression hit at
    the moment the launch most needs polish.

    Caught two unfilled placeholders at T-1 (the kick-off run): the
    CTA tweet 12/12 and the embedded HN post both had `<github.com/...>`
    and `[date]` literally in the prose. Filled in to the canonical
    values (this-week + the actual repo URL). The guard now scans
    launch-facing markdown for the placeholder shapes and fails if
    any survive into the published artifact.

    Excluded patterns (legitimate placeholders, not lorem ipsum):
      - `<...>` inside code fences (parameter syntax in CLI examples)
      - `[...]` inside markdown link text like `[Claude Code]` (real
        references, not unfilled slots)
    """

    PLACEHOLDER_PATTERNS = [
        # Literal "[date]" / "[handle]" / "[name]" style draft slots
        r"\[date\]",
        r"\[handle\]",
        r"\[name\]",
        r"\[your\s+\w+\]",  # "[your handle]", "[your name]"
        # Repo-URL placeholders. Specific shapes to avoid false-
        # positive on legitimate angle-bracket usage in CLI signatures.
        r"<github\.com/\.\.\.>",
        r"<github\.com/<\w+>>",
        r"github\.com/<repo>",
        r"<repo-url>",
        # Generic TODO markers in published copy
        r"\bTODO:?\s+(fill|add|write|update)",
    ]

    def test_launch_docs_have_no_unfilled_placeholders(self):
        launch_docs = [
            REPO / "docs" / "launch.md",
            REPO / "docs" / "launch-package.md",
            REPO / "README.md",
        ]
        leaks: list[tuple[str, str, int]] = []
        for path in launch_docs:
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            in_code_fence = False
            for lineno, line in enumerate(lines, 1):
                # Track fenced code blocks — placeholders inside code
                # fences are CLI examples (e.g. `<provider>`), not
                # lorem-ipsum in published prose.
                stripped = line.strip()
                if stripped.startswith("```"):
                    in_code_fence = not in_code_fence
                    continue
                if in_code_fence:
                    continue
                # Also skip indented code blocks (4+ space leading)
                # — same reason. Common in launch.md's quoted tweets
                # with embedded CLI commands.
                if line.startswith("    "):
                    continue
                for pattern in self.PLACEHOLDER_PATTERNS:
                    if re.search(pattern, line):
                        leaks.append((path.name, pattern, lineno))
                        break
        assert not leaks, (
            f"Unfilled placeholders in launch-facing markdown: "
            f"{leaks}. These will ship as literal '[date]' / "
            f"'<github.com/...>' in the published artifact. Fill "
            f"each one with the canonical value, or remove the slot."
        )


class TestV16BrowserExtensionArtifactsExist:
    """Per Principle #21: every public claim needs a regression guard
    at the surface that ships it. v1.6 added a handful of file
    references in launch-facing markdown (README, spec-v1.6.md,
    browser-extension/README.md) — if any of those targets get
    renamed without the README/spec updating, the install ritual
    silently 404s the user.
    """

    REPO = Path(__file__).resolve().parent.parent

    def test_browser_extension_directory_exists(self):
        ext = self.REPO / "browser-extension"
        assert ext.exists() and ext.is_dir(), (
            "browser-extension/ directory missing. README + spec-v1.6.md "
            "tell users to `chrome://extensions → Load Unpacked → "
            "browser-extension/`. If the directory was renamed or moved, "
            "the install ritual silently breaks."
        )

    def test_browser_extension_readme_exists(self):
        readme = self.REPO / "browser-extension" / "README.md"
        assert readme.exists(), (
            "browser-extension/README.md missing. README's v1.6 section + "
            "spec-v1.6.md both link here for the 60-second install ritual. "
            "Renaming this file orphans those references."
        )

    def test_spec_v16_exists(self):
        spec = self.REPO / "docs" / "spec-v1.6.md"
        assert spec.exists(), (
            "docs/spec-v1.6.md missing. README + claude.md companion-docs "
            "header reference this spec by path. Renaming it requires "
            "updating all referrers in the same commit."
        )

    def test_manifest_json_referenced_files_all_exist(self):
        """Cross-check from the test_browser_extension_manifest suite,
        replicated here so a doc-consistency run catches the same drift
        even when the structural suite is skipped."""
        manifest_path = self.REPO / "browser-extension" / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        for entry in manifest.get("content_scripts", []):
            for js_file in entry.get("js", []):
                full = self.REPO / "browser-extension" / js_file
                assert full.exists(), (
                    f"manifest.json references missing file {js_file!r}. "
                    "Chrome's Load Unpacked silently fails when any "
                    "content_script js path doesn't resolve."
                )


class TestV16ClaimedCliCommandsExist:
    """The v1.6 install ritual names two CLI surfaces:
    ``trinity-local install-extension`` (subcommand) and
    ``trinity-local-capture-host`` (separate console script). Both
    are referenced in README + spec + doctor output + browser-
    extension/README. Drift catches: subcommand renamed, console
    script removed from pyproject.toml.
    """

    REPO = Path(__file__).resolve().parent.parent

    def test_install_extension_subcommand_is_registered(self):
        """``trinity-local install-extension --help`` must succeed."""
        result = subprocess.run(
            [sys.executable, "-m", "trinity_local.main", "install-extension", "--help"],
            capture_output=True,
            text=True,
            timeout=20,
            cwd=str(self.REPO),
        )
        assert result.returncode == 0, (
            f"`trinity-local install-extension --help` exit {result.returncode}: "
            f"{result.stderr}. README v1.6 section + spec + browser-extension/"
            "README all name this subcommand; if it's been renamed or removed, "
            "those docs are silently broken."
        )

    def test_capture_host_console_script_in_pyproject(self):
        """`trinity-local-capture-host` is what Chrome's Native
        Messaging manifest spawns. If this entry-point disappears
        from pyproject.toml, `pip install` won't put the binary on
        PATH and install-extension's --host-path resolution fails."""
        pyproject = (self.REPO / "pyproject.toml").read_text()
        assert "trinity-local-capture-host" in pyproject, (
            "pyproject.toml is missing the trinity-local-capture-host "
            "console_script entry. The v1.6 install ritual depends on "
            "this binary being on PATH after `pip install -e .`. "
            "Re-add the entry under [project.scripts]."
        )
        assert "trinity_local.capture_host:main" in pyproject, (
            "pyproject.toml mentions trinity-local-capture-host but the "
            "entry-point target trinity_local.capture_host:main isn't "
            "wired. Check the [project.scripts] section."
        )


class TestV16SpecShipPlanCommitHashesResolve:
    """The spec-v1.6.md ship-plan section names commit hashes for
    traceability (Week 1 ✅ commit `4bd2e0f` etc.). If the repo gets
    rebased or those commits get squashed, the hashes become dead
    pointers. Same shape as TestCitedCouncilArtifactsExistInRepo
    earlier in this file but for git history rather than disk files.
    """

    REPO = Path(__file__).resolve().parent.parent

    def test_cited_commit_hashes_resolve_in_git_log(self):
        spec = (self.REPO / "docs" / "spec-v1.6.md").read_text()
        # Match the inline-code commit references used in the ship plan,
        # e.g. `4bd2e0f`. Use a strict pattern so we only check actual
        # short-SHA-looking tokens, not arbitrary 7-char strings.
        hashes = set(re.findall(r"`([0-9a-f]{7})`", spec))
        # Drop a known non-hash: `7216` is the Intuit IRC section number
        # the existing guards parse out of other surfaces. Filter to
        # tokens that look like git SHAs (mix of digits + letters).
        hashes = {h for h in hashes if not h.isdigit()}
        assert hashes, (
            "spec-v1.6.md ship-plan should cite at least one commit hash "
            "for traceability. Found none — either the ship-plan annotation "
            "was reverted or the regex needs updating."
        )
        for sha in hashes:
            result = subprocess.run(
                ["git", "cat-file", "-e", sha],
                capture_output=True,
                text=True,
                cwd=str(self.REPO),
            )
            assert result.returncode == 0, (
                f"spec-v1.6.md cites commit {sha!r} but it doesn't resolve "
                f"in git. stderr: {result.stderr}. If the repo was rebased, "
                "update the ship-plan annotations to the new hashes; otherwise "
                "this is a dead pointer in launch-facing copy."
            )


class TestScoreboardPathRenameInDocs:
    """v1.7 moved `picks.json` and `routing.json` out of
    `~/.trinity/memories/` (cognitive memories — lens/topics/vocabulary)
    into `~/.trinity/scoreboard/` (operational scoreboards). The rename
    has an idempotent on-disk migration in `state_paths._migrate_legacy_
    scoreboard_paths()`, but user-facing prose that still says
    `memories/picks.json` or `memories/routing.json` will mislead
    readers who go look on disk and find the file under `scoreboard/`
    instead.

    Tests/code may legitimately reference the old path as
    historical-context comments (e.g. test_freeze_routing's docstring
    explains the migration); this guard only scans user-facing prose
    docs (README, launch-facing markdown, spec docs) for the bare
    string.

    Skip docs that ARE explaining the rename — claude.md, CHANGELOG,
    scale-plan all need to describe the old vs new paths for the
    migration story to be readable. Only ban it from launch copy +
    user-onboarding surfaces where the reader will trust the path
    and go looking on disk.
    """

    BANNED_STRINGS = ("memories/picks.json", "memories/routing.json")

    # Docs that explain the migration legitimately reference the old
    # path — don't flag them.
    EXEMPT_DOCS = {
        "CHANGELOG.md",
        "claude.md",
        "CLAUDE.md",  # macOS case-insensitive FS dupe
        "docs/scale-plan.md",
        "AGENTS.md",
    }

    def test_no_old_scoreboard_paths_in_user_facing_docs(self):
        scan_globs = [
            "README.md",
            "docs/launch.md",
            "docs/launch-package.md",
            "docs/MCP_REGISTRY_SUBMISSIONS.md",
            "docs/spec-v1.md",
            "docs/spec-v1.5.md",
            "docs/spec-v1.6.md",
            "docs/launch-day/*.md",
            "DESIGN.md",
            "docs/frontend-architecture.md",
        ]
        leaks: list[tuple[str, int, str]] = []
        for pattern in scan_globs:
            for path in REPO.glob(pattern):
                rel = str(path.relative_to(REPO))
                if rel in self.EXEMPT_DOCS:
                    continue
                try:
                    lines = path.read_text(encoding="utf-8").splitlines()
                except OSError:
                    continue
                for lineno, line in enumerate(lines, 1):
                    for banned in self.BANNED_STRINGS:
                        if banned in line:
                            leaks.append((rel, lineno, banned))
        assert not leaks, (
            "User-facing docs still reference the pre-v1.7 scoreboard "
            "paths: "
            f"{leaks}. v1.7 moved picks/routing to "
            "`~/.trinity/scoreboard/` (out of `~/.trinity/memories/`). "
            "Update launch copy + specs to use the new path so readers "
            "who look on disk find the file where the docs said it would be."
        )


class TestNoBrokenSeedCommandInUserFacingDocs:
    """Pin the seed-cmd fix from launch-eve iteration (2026-05-17).

    `trinity-local seed-from-taste-terminal` has `--path` `required=True`;
    historical doc copies showed `--limit 1000` *without* `--path`, which
    fails with `error: the following arguments are required: --path`.
    The fix is `trinity-local ingest-recent` (auto-discovers transcript
    paths, no required flags).

    The launch-eve sweep caught this in 5 user-facing surfaces in three
    rounds (README, SKILL.md ×3, INSTALL-pip.md, INSTALL-skill.md).
    This guard fires loudly if any future surface introduces the broken
    form. Allowed in CHANGELOG / PUBLIC_READINESS_PLAN (historical
    record of the fixes) and tests (this file documents the pattern).
    """

    def test_user_facing_docs_dont_show_broken_seed_cmd(self):
        user_facing_paths = [
            REPO / "README.md",
            REPO / "claude.md",  # tick 24: closed the gap that let
                                 # claude.md L830 drift past the original
                                 # 9-path guard
            REPO / "skills" / "trinity" / "SKILL.md",
            REPO / "src" / "trinity_local" / "data" / "skills" / "trinity" / "SKILL.md",
            REPO / "docs" / "INSTALL-pip.md",
            REPO / "docs" / "INSTALL-skill.md",
            REPO / "docs" / "INSTALL-extension.md",
            REPO / "docs" / "launch.md",
            REPO / "docs" / "launch-package.md",
            REPO / "docs" / "founder-essay-draft.md",
            *(REPO / "docs" / "launch-day").glob("*.md"),
        ]
        leaks = []
        for path in user_facing_paths:
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            # Match `seed-from-taste-terminal --limit N` without --path
            # on the same line. A line with both --path and --limit is
            # the correct invocation and allowed.
            for lineno, line in enumerate(text.splitlines(), 1):
                if "seed-from-taste-terminal" in line and "--limit" in line:
                    if "--path" not in line:
                        leaks.append((path.name, lineno))
        assert not leaks, (
            f"Broken `seed-from-taste-terminal --limit N` (without --path) "
            f"in user-facing surfaces: {leaks}. The command's --path is "
            f"required=True; recipients copy-pasting will hit `error: the "
            f"following arguments are required: --path`. The intended "
            f"polyharness-user cold-start command is "
            f"`trinity-local ingest-recent` (no required flags; "
            f"auto-discovers ~/.claude, ~/.codex, ~/.gemini transcripts)."
        )


class TestShareWorkflowCommandsDocumented:
    """Pin the v1.7.3 share-workflow surfaces in claude.md. The launch-eve
    audit (2026-05-17) caught `eval-share` missing from the claude.md
    eval.py command-row even though the command was live. Future
    additions to the share family should land in claude.md in the same
    commit; this guard fires loudly if a new share-card is wired in code
    but the architecture doc isn't updated."""

    def test_eval_share_listed_in_claude_md_eval_row(self):
        text = (REPO / "claude.md").read_text(encoding="utf-8")
        # The eval.py row should mention eval-share alongside the other
        # eval subcommands so a reader scanning the CLI table sees the
        # full eval-command family.
        assert "eval-share" in text, (
            "claude.md must list `eval-share` in the eval.py commands row. "
            "Sweep claude.md's `commands/eval.py` row to include it."
        )

    def test_council_share_listed_in_claude_md(self):
        text = (REPO / "claude.md").read_text(encoding="utf-8")
        assert "council-share" in text, (
            "claude.md must reference `council-share`. The command exists in "
            "src/trinity_local/commands/council.py and ships a PNG share card; "
            "the architecture doc needs to mention it."
        )

    def test_share_card_modules_in_core_layers(self):
        """The 3 share-card renderers (me_card, eval_card, council_card)
        should appear in claude.md's Core layers section. The launch-eve
        audit caught eval_card.py + council_card.py missing despite being
        new production modules; this guard prevents the same shape from
        recurring."""
        text = (REPO / "claude.md").read_text(encoding="utf-8")
        for module in ("me_card.py", "eval_card.py", "council_card.py"):
            assert module in text, (
                f"claude.md Core layers must list {module}. Three share-"
                f"card renderers ship one visual language; the architecture "
                f"doc needs to surface all three or a reader can't trace "
                f"the share workflow back to implementation."
            )


class TestNoBannedSynonyms:
    """Single guard for the drift CLASS that this session caught
    one-instance-at-a-time across 30+ ticks. Each entry is a string
    that USED to be the right framing but was retired by a rename
    (v1.7 architectural collapse, brand-pivot work, etc.). Catching
    them in the same test means a future rename's propagation is a
    grep-then-add-one-line operation, not a 14-commit drift hunt.

    Rationale (the per-instance ticks earned each entry):
      - "five plural" / "five core memories": v1.7 collapse retired
        the 5-memory framing; chairman now reads 3 thinking memories
        + core.md distillation. picks/routing are scoreboards.
      - "Your memories" in user-facing headers: replaced by "Your lens"
        on the memory viewer h1 + launchpad chip card (tick AA).
      - "6-chip" / "six-chip": memory viewer was 6 chips pre-collapse,
        now describes itself as "lens + scoreboards" (4 + 2).
      - "models-detect" CLI / `model_detector.py`: phantom command +
        module documented but never shipped (tick U).
      - `memories/picks.json` / `memories/routing.json`: pre-v1.7
        scoreboard paths (caught earlier via TestScoreboardPathRename
        InDocs; included here so all banned strings share one test).

    Surface scope is user-facing prose ONLY: README, claude.md, docs/
    launch.md, launch-package.md, MCP_REGISTRY, launch-day/*.md,
    DESIGN.md, frontend-architecture.md. CHANGELOG + scale-plan are
    exempt — they legitimately describe the pre-rename state for
    migration context (Principle #8: timestamped + okay to be stale).
    """

    # (banned_substring, suggested_replacement, why)
    BANNED: list[tuple[str, str, str]] = [
        ("five plural memor", "lens hierarchy / three thinking memories",
         "v1.7 collapse retired the 5-memory framing"),
        ("five core memor", "lens hierarchy / three thinking memories",
         "v1.7 collapse retired the 5-memory framing"),
        ("six plural memor", "lens hierarchy / three thinking memories",
         "pre-v1.7 framing — was 5/6 'memories', now lens + scoreboards"),
        # NOTE: "6-chip" / "six-chip" intentionally NOT banned. The only
        # place they legitimately appear is rename narration like "6-chip
        # nav collapses to a 4-chip card" — banning would force awkward
        # rewordings of legitimate change-log descriptions. The "Your
        # memories" → "Your lens" header rename is what caught the real
        # drift; chip-count appears purely in rename narration.
        ("models-detect", "(removed — feature never shipped)",
         "phantom CLI command documented but never wired"),
        ("model_detector.py", "(removed — module never shipped)",
         "phantom module documented but never written"),
        ("Gemini CLI", "Antigravity",
         "harness rename per the 2026-05-20 multi-tick rebrand: Google's "
         "CLI binary is now `agy` (Antigravity v1.0.0 standalone CLI); "
         "the legacy `gemini` binary is preserved on disk but Trinity's "
         "shipped config dispatches via Antigravity. Pitch surfaces and "
         "harness lists must use the post-rebrand name to match what "
         "users see when they install. Model-family 'Gemini' (without "
         "the 'CLI' suffix) remains accurate — the model behind "
         "Antigravity is still Gemini 3.1 Pro Preview."),
    ]

    # Files that get the scan. User-facing surfaces only.
    SCAN_FILES = [
        "README.md",
        "claude.md",
        "DESIGN.md",
        "docs/launch.md",
        "docs/launch-package.md",
        "docs/MCP_REGISTRY_SUBMISSIONS.md",
        "docs/frontend-architecture.md",
        "docs/spec-v1.md",
        "docs/spec-v1.5.md",
        "docs/spec-v1.6.md",
        "docs/product-spec.md",
        # All launch-day artifacts (paste-ready copy).
        "docs/launch-day/00_leaderboard.md",
        "docs/launch-day/01_tweet_thread.md",
        "docs/launch-day/02_show_hn_post.md",
        "docs/launch-day/03_hn_objection_faq.md",
        "docs/launch-day/04_demo_voiceover.md",
        "docs/launch-day/05_comparison_table.md",
        "docs/launch-day/06_founder_narrative.md",
        "docs/launch-day/07_pricing_faq.md",
        "docs/launch-day/08_twitter_bio.md",
        "docs/launch-day/09_linkedin_post.md",
        "docs/launch-day/10_hn_faq_full.md",
        "docs/launch-day/README.md",
    ]

    # Files exempt by design (Principle #8 + migration-context).
    # CHANGELOG entries are timestamped; scale-plan documents history.
    # The test file itself contains the banned strings as data.
    EXEMPT_FILES: set[str] = {
        "CHANGELOG.md",
        "docs/scale-plan.md",
        "AGENTS.md",
        "tests/test_doc_count_consistency.py",
    }

    def test_no_banned_synonyms_in_user_facing_docs(self):
        leaks: list[tuple[str, int, str, str]] = []
        for rel in self.SCAN_FILES:
            if rel in self.EXEMPT_FILES:
                continue
            path = REPO / rel
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for lineno, line in enumerate(lines, 1):
                lower = line.lower()
                for banned, replacement, _why in self.BANNED:
                    if banned.lower() in lower:
                        leaks.append((rel, lineno, banned, replacement))
                        break  # one hit per line is enough
        if leaks:
            msg_lines = ["Banned synonym strings found in user-facing docs:"]
            for rel, lineno, banned, replacement in leaks:
                msg_lines.append(
                    f"  {rel}:{lineno} contains {banned!r} — "
                    f"use {replacement} instead"
                )
            msg_lines.append("")
            msg_lines.append(
                "These strings were retired by past renames (v1.7 "
                "architectural collapse, brand pivot, etc.). Each "
                "appears here because a per-instance drift-hunt tick "
                "caught it; adding to TestNoBannedSynonyms.BANNED makes "
                "the next rename's propagation a one-line add, not a "
                "session-long drift hunt."
            )
            raise AssertionError("\n".join(msg_lines))


class TestNoRetiredCliInSrcQuotedStrings:
    """Permanent guard born of iterations #9 + #11 + #12 + #13 of the
    pre-launch consistency-loop, EXTENDED in iter #32 after iters
    #30 + #31 found 4 more retired-CLI runtime bugs in HTML-wrapped
    form that the original quoted-string regex didn't catch.

    The simplification pass on 2026-05-18 killed ~10 CLI subcommands;
    the kills left dead `trinity-local <name>` fragments in 9+ product
    code paths (launchpad buttons, doctor fix hints, install-hooks
    templates, memory-viewer rebuild suggestions, health-card chips,
    review-page error panels, rate-limit-saves CTA, core-memory empty
    state hint). Each was a runtime bug — user click / copy-paste
    would error with `unknown command: <name>`.

    Guard shape: parse `mcp_server.py` + `main.py` for the live CLI
    subcommands. Walk every `.py` file in `src/`. Fail if any
    `trinity-local <retired>` appears in EITHER form:
      - Quoted string:    `"trinity-local distill"` / `'trinity-local distill'`
      - HTML-wrapped:     `<code>trinity-local distill</code>`
    where `<retired>` isn't a live subcommand. Files in KNOWN_REFS_PATHS
    get a pass (legitimate retirement-context uses).

    Why this matters: it catches the next CLI kill before it ships dead
    button strings into production. Without this, the human (me) became
    the regression guard — iters #9/#11/#12 caught 5 such bugs, iter #13
    installed the quoted-string guard, then iters #30+#31 caught 4 MORE
    in HTML-wrapped form because the original regex's `['"]trinity-local`
    prefix didn't match `<code>trinity-local`. The HTML form is the
    Vue-template idiom; missing it left every empty-state hint and error
    panel unprotected.
    """

    # CLI subcommands KNOWN to be retired (extracted from this session's
    # commit log). When adding a new retirement, add the bare subcommand
    # name here in the same commit that drops it from CORE_COMMAND_MODULES.
    RETIRED_CLI = frozenset({
        "doctor",
        "watch-once", "watch-loop",
        "distill", "core-show",
        "stats", "metric",
        "depth-show",
        "task-create", "task-show", "task-sync",
        "bundle-create", "launch-create",
        "council-last",
        "trust-init", "trust-show", "audit-show",
        "install-app", "shortcut-install",
        "bootstrap-pairs",
        "auto-chain-enable", "auto-chain-disable",
        "polish-auto-enable", "polish-auto-disable",
        "auto-open-enable", "auto-open-disable",
        "cache-stats", "cache-clear",
        "features",
        "search-prompts",
    })

    # Files that legitimately reference retired CLIs in retirement-
    # context strings (docstrings, comments, upgrade detection logic).
    # The legitimate uses cluster in install.py (detects + removes stale
    # `watch-once` hooks on re-install) and commands/trust.py (module
    # docstring naming the retired CLI surface it's deferred to v1.1).
    KNOWN_REFS_PATHS = frozenset({
        "src/trinity_local/commands/install.py",   # stale-hook cleanup detection
        "src/trinity_local/commands/trust.py",     # deferred-to-v1.1 docstring
    })

    def test_no_retired_cli_strings_in_src(self):
        import re
        repo = Path(__file__).resolve().parent.parent
        src = repo / "src" / "trinity_local"
        # Match `trinity-local <retired-subcommand>` when preceded by
        # EITHER a Python quote char (`"` / `'`) OR an HTML open-code
        # tag (`<code>`). Word boundary after the subcommand so
        # `install-extension` doesn't match `install`. The HTML form
        # is the Vue-template idiom used in launchpad_template.py,
        # council_review.py, memory_viewer.py — every empty-state hint
        # and error panel relies on it.
        retired_pattern = re.compile(
            r"""(?:['"]|<code>)trinity-local\s+("""
            + "|".join(re.escape(c) for c in self.RETIRED_CLI)
            + r""")\b"""
        )
        hits: list[tuple[str, int, str, str]] = []
        for path in src.rglob("*.py"):
            rel = path.relative_to(repo).as_posix()
            if rel in self.KNOWN_REFS_PATHS:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                m = retired_pattern.search(line)
                if m:
                    hits.append((rel, lineno, m.group(1), line.strip()[:120]))
        if hits:
            msg = ["Retired CLI subcommands referenced in src/ quoted strings:"]
            for rel, lineno, cli, snippet in hits:
                msg.append(f"  {rel}:{lineno} mentions retired `trinity-local {cli}`")
                msg.append(f"    → {snippet}")
            msg.append("")
            msg.append(
                "These would produce runtime errors when users click "
                "buttons / paste fix hints / fire hook commands. Either "
                "flip to the live CLI name, or add the file to "
                "TestNoRetiredCliInSrcQuotedStrings.KNOWN_REFS_PATHS "
                "with a one-line justification (legitimate retirement-"
                "context use, e.g. stale-hook cleanup detection)."
            )
            raise AssertionError("\n".join(msg))


class TestNoRetiredMcpToolEnumeratedAsLive:
    """Permanent guard born of tick 45 of the post-launch sweep.
    `search_prompts` was retired 2026-05-17 (per the registry +
    SKILL.md), but product-spec.md kept it in its numbered MCP-tool
    enumeration as tool #5 — and the same enumeration was missing
    `handoff`, which had been added as the launch-arc tool #9. The
    header said "9 total" but the body still enumerated the pre-
    retirement 9. spec-v1.5.md's "MCP stable contract" table had
    the same drift, contradicting its own L278 drift note.

    Guard shape: for every retired MCP tool from the registry, walk
    user-facing long-form docs and fail if the tool name appears in
    a numbered-enumeration position (`N. **\\`tool_name\\`** ...` or
    `N. **\\`tool_name(...)\\`** ...`). Historical-context mentions
    in prose ("formerly", "retired", "deliberately deleted") stay
    legal because they don't fit the enumeration regex.

    Why this matters: a doc reader scanning for "what MCP tools
    exist" lands on numbered lists first. A retired tool listed
    there is a credibility loss + a literal misdirection — an LLM
    agent reading the doc would call a tool that doesn't exist.
    Same shape as TestNoRetiredCliInSrcQuotedStrings, one layer up.
    """

    # User-facing long-form docs where MCP tools get enumerated.
    # Excluded: CHANGELOG (frozen history), simplification_log
    # (historical decision log), sweep-patterns (pattern catalog,
    # legitimately names the retired tool to illustrate the pattern),
    # scale-plan (class: aspirational), spec-v2 (sunset), spec-v1.6
    # (forward-trajectory aspirational doc), architectural-gaps
    # (literally contains the registry entries).
    DOCS_TO_CHECK = (
        "claude.md",
        "README.md",
        "docs/product-spec.md",
        "docs/spec-v1.md",
        "docs/spec-v1.5.md",
        "docs/architecture.md",
        "skills/trinity/SKILL.md",
    )

    def test_no_retired_mcp_tool_in_numbered_enumeration(self):
        import re
        from trinity_local.retired_names import RETIRED
        repo = Path(__file__).resolve().parent.parent
        retired_mcp_tools = [
            name for name, rec in RETIRED.items()
            if rec.kind == "mcp_tool"
        ]
        assert retired_mcp_tools, "Registry has no MCP-tool entries — guard would silently pass"

        # Numbered enumeration line:
        #   N. **`tool_name`** ...
        #   N. **`tool_name(args)`** ...
        # `N` is 1-99 (decimal). The bold-backtick pattern is the
        # MCP-tool-enumeration idiom across all long-form docs.
        def pattern_for(tool: str) -> re.Pattern:
            return re.compile(
                r"^\s*\d+\.\s+\*\*`" + re.escape(tool) + r"(\(|`)",
            )

        hits: list[tuple[str, int, str, str]] = []
        for doc in self.DOCS_TO_CHECK:
            path = repo / doc
            if not path.exists():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                for tool in retired_mcp_tools:
                    if pattern_for(tool).search(line):
                        hits.append((doc, lineno, tool, line.strip()[:120]))
        if hits:
            msg = ["Retired MCP tools enumerated as live in user-facing docs:"]
            for doc, lineno, tool, snippet in hits:
                msg.append(f"  {doc}:{lineno} enumerates retired `{tool}`")
                msg.append(f"    → {snippet}")
            msg.append("")
            msg.append(
                "Update the enumeration to drop the retired tool and "
                "add a one-line drift note if the surrounding count "
                "claim ('N total') needs reconciling. Historical-context "
                "mentions outside numbered-enumeration syntax are still "
                "legal — this guard only fires on the `N. **`tool`**` "
                "MCP-tool enumeration idiom."
            )
            raise AssertionError("\n".join(msg))


class TestNoForbiddenColorsInLaunchpadTemplates:
    """Permanent guard born of iter #37 of the consistency-loop.
    DESIGN.md is explicit: lines 297 + 343 forbid indigo, violet,
    tailwind-blue, purple, and neon accents. Principle #13 in
    claude.md narrates the prior violation: "Memory viewer's first
    cut shipped #6366f1 indigo + #8b5cf6 violet anyway, because
    nothing enforced the palette."

    Iter #37 found the same violation still live across 5 places
    in launchpad_template.py + memory_viewer.py:
      - #6366f1 (Tailwind indigo-500) × 2 — empty-state hints
      - #3b6bd6 (Tailwind-blue) × 3 — handoff demo + eval card
      - #4a90e2 (corporate blue) × 6 — browser-capture card
      - #f59e0b (Tailwind amber-500) × 1 — stale-core warning
      - #be185d (Tailwind pink-700, purple-adjacent) × 1 — JSON bool

    All flipped to in-palette `design_system.COLORS` values. The
    guard below enforces that future UI edits don't reintroduce a
    forbidden hex.

    Approach: scan launchpad_template / council_review / memory_viewer
    / launchpad_data for hex literals. Compare against a forbidden
    set extracted from common Tailwind / indigo / violet / pink /
    saturated palettes that DESIGN.md rules out. Any hit raises.

    If you legitimately need a NEW color (e.g. for a chart or topic-
    graph dark canvas), add it to design_system.COLORS and remove
    from the FORBIDDEN_HEXES set in the same commit.
    """

    # Hex codes DESIGN.md lines 297 + 343 explicitly rule out, plus
    # the specific past-violation hexes from this session (locked so
    # they can't sneak back in). Bare `#` followed by 3-or-6 hex chars
    # matched case-insensitively.
    FORBIDDEN_HEXES = frozenset({
        # Indigo (Tailwind 400-700 range + the prior-violation hex):
        "#6366f1",  # Tailwind indigo-500 (the principle #13 hex)
        "#818cf8",  # indigo-400
        "#4f46e5",  # indigo-600
        "#4338ca",  # indigo-700
        "#8b5cf6",  # Tailwind violet-500 (the OTHER principle #13 hex)
        "#a78bfa",  # violet-400
        "#7c3aed",  # violet-600
        # Tailwind blue (DESIGN.md "no tailwind-blue"):
        "#3b82f6",  # blue-500
        "#3b6bd6",  # an off-Tailwind blue used in handoff card
        "#4a90e2",  # corporate-blue used in browser-capture card
        "#2563eb",  # blue-600
        # Pink / fuchsia (purple-adjacent):
        "#be185d",  # pink-700 (was on .json-bool)
        "#ec4899",  # pink-500
        "#d946ef",  # fuchsia-500
        # Tailwind amber-500 (out-of-palette; warm-brown #b26a1f
        # is the in-palette warning color):
        "#f59e0b",
    })

    # Files that legitimately reference these hexes in retirement-
    # context (e.g. test-cases that assert a forbidden color is
    # absent, or DESIGN.md's own "no indigo" list). Empty for now;
    # add files with one-line justification if a real exception
    # surfaces.
    KNOWN_REFS_PATHS = frozenset()

    SCAN_PATHS = (
        "src/trinity_local/launchpad_template.py",
        "src/trinity_local/launchpad_data.py",
        "src/trinity_local/council_review.py",
        "src/trinity_local/memory_viewer.py",
    )

    def test_no_forbidden_hex_colors(self):
        repo = Path(__file__).resolve().parent.parent
        # Match `#XXXXXX` or `#XXX` case-insensitively at word
        # boundaries. The forbidden-set comparison is also case-
        # insensitive (DESIGN.md uses lowercase; code might use any).
        hex_re = re.compile(r"(#[0-9a-fA-F]{6}|#[0-9a-fA-F]{3})\b")
        forbidden_lower = {h.lower() for h in self.FORBIDDEN_HEXES}
        hits: list[tuple[str, int, str, str]] = []
        for rel in self.SCAN_PATHS:
            if rel in self.KNOWN_REFS_PATHS:
                continue
            path = repo / rel
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            for lineno, line in enumerate(text.splitlines(), start=1):
                for m in hex_re.finditer(line):
                    hex_val = m.group(1).lower()
                    if hex_val in forbidden_lower:
                        hits.append((rel, lineno, hex_val, line.strip()[:140]))
        if hits:
            msg = [
                "DESIGN.md-forbidden hex colors found in launchpad UI source.",
                "Lines 297 + 343 of DESIGN.md forbid: no indigo, no violet,",
                "no tailwind-blue, no purple, no neon. Use in-palette colors",
                "from `design_system.COLORS` (info=#315c85 for slate-blue",
                "callouts, warning=#b26a1f for amber callouts).",
                "",
            ]
            for rel, lineno, hex_val, snippet in hits:
                msg.append(f"  {rel}:{lineno} uses forbidden {hex_val}")
                msg.append(f"    → {snippet}")
            msg.append("")
            msg.append(
                "Per principle #13: 'design system is a contract, not a "
                "suggestion.' If a new color is truly needed, add it to "
                "design_system.COLORS and remove from FORBIDDEN_HEXES in "
                "the same commit."
            )
            raise AssertionError("\n".join(msg))


class TestNoFStringWithoutPlaceholders:
    """Permanent guard born of tick 55 of the post-launch sweep.
    `python -m pyflakes src/trinity_local/commands/` flagged 10
    f-strings with no `{}` placeholders — all constant strings with
    a stray `f` prefix (`print(f"  By rejection axis:")`). The
    `f` prefix is misleading + slightly less efficient, but the
    real harm is signal-masking: pyflakes catches accidentally-
    dropped placeholders (e.g. someone refactors `f"...{var}..."`
    to `f"..."` by mistake) using exactly this warning. When the
    codebase has 10 false positives the warning becomes wallpaper.

    Guard shape: parse `src/trinity_local/commands/*.py` as AST,
    find every f-string with zero `FormattedValue` children, fail.
    Limits scope to commands/ (where the bug actually lived) rather
    than all of src/ — template modules legitimately use long
    f-string blocks with placeholders for HTML rendering, and
    expanding scope would slow the test without adding signal.

    Why this matters in the sweep context: signal-masking warnings
    are the cousin of stale claims. If pyflakes complains 10 times
    about non-bugs, the 11th time (a real bug — dropped placeholder)
    is invisible. Same shape as Principle #14 (regression guards
    must run to count): warnings must mean something to be useful.
    """

    def test_no_fstring_without_placeholders_in_commands(self):
        import subprocess
        import sys
        repo = Path(__file__).resolve().parent.parent
        commands_dir = repo / "src" / "trinity_local" / "commands"

        # Shell out to pyflakes — it correctly distinguishes top-level
        # f-strings from inner format_spec JoinedStr nodes (which a naive
        # ast.walk would false-positive on, e.g. `f"{x:>8,}"` contains
        # an inner JoinedStr `f">8,"` that isn't a real source f-string).
        result = subprocess.run(
            [sys.executable, "-m", "pyflakes", str(commands_dir)],
            capture_output=True,
            text=True,
        )
        # pyflakes prints findings to stdout; exit code is nonzero when
        # warnings exist but we parse output rather than rely on rc since
        # we only want the specific f-string-missing-placeholders class.
        fstring_hits = [
            line for line in result.stdout.splitlines()
            if "f-string is missing placeholders" in line
        ]
        if fstring_hits:
            msg = ["f-strings without placeholders in commands/ (stray `f` prefix):"]
            for line in fstring_hits:
                msg.append(f"  {line}")
            msg.append("")
            msg.append(
                "Either remove the `f` prefix (constant string), or "
                "add the placeholders that were intended. The `f` "
                "prefix is misleading + masks the pyflakes warning "
                "that catches accidentally-dropped placeholders."
            )
            raise AssertionError("\n".join(msg))


class TestPostLaunchTenseConsistency:
    """Today is post-launch (v1.0 shipped 2026-05-14). Public-facing
    docs must not describe the launch in future tense ("ships May
    13–15"), or visitors arriving from keepwhatworks.com / GitHub
    read it as if the project hasn't launched yet.

    Two exceptions are intentional:
      - CHANGELOG.md — historical record; the "ship window" entries
        are quoting state at the time and SHOULD stay future-tense.
      - PUBLIC_READINESS_PLAN.md — audit log with literal quotes of
        prior doc state ("status block still said …"); those quoted
        strings are evidence, not claims.

    Guard added 2026-05-19 after a consistency-sweep grep found 8
    surfaces (claude.md, docs/spec-v1.md, docs/spec-v1.5.md,
    docs/product-spec.md ×2, docs/launch-package.md, docs/scale-plan.md,
    docs/spec-v1.md launch-day line) all reading "ships May 13–15" in
    present/future tense. Per principle #21 ("public claims need
    regression guards at the surface that ships them"), the tense
    consistency now has its own guard.
    """

    FUTURE_TENSE_PATTERNS = [
        # The specific dated phrase that was scattered across docs.
        "ships May 13–15",
        "will ship May 13–15",
        "ship for May 13–15",
        "May 13–15 ship",
    ]

    EXEMPT_FILES = {
        # Historical records; future-tense framing belongs there.
        "CHANGELOG.md",
        "docs/PUBLIC_READINESS_PLAN.md",
    }

    def test_no_future_tense_launch_framing_in_public_docs(self):
        repo = Path(__file__).resolve().parents[1]
        hits: list[tuple[str, int, str]] = []
        for md in sorted(repo.rglob("*.md")):
            rel = md.relative_to(repo).as_posix()
            if rel in self.EXEMPT_FILES:
                continue
            # Skip vendored/node_modules/etc
            if any(part.startswith(".") for part in md.parts):
                continue
            if "node_modules" in md.parts or ".venv" in md.parts:
                continue
            # Skip the in-repo memory dir if it ever ends up here
            if "memory" in md.parts and md.parts.index("memory") == 0:
                continue
            try:
                text = md.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for lineno, line in enumerate(text.splitlines(), 1):
                for pat in self.FUTURE_TENSE_PATTERNS:
                    if pat in line:
                        hits.append((rel, lineno, line.strip()[:160]))
        if hits:
            msg = [
                "Future-tense launch framing found in public docs after "
                "v1.0 already shipped (2026-05-14):",
                "",
            ]
            for rel, lineno, snippet in hits:
                msg.append(f"  {rel}:{lineno}")
                msg.append(f"    → {snippet}")
            msg.append("")
            msg.append(
                "Replace future-tense ('ships May 13–15') with past-tense "
                "('shipped May 13–15, 2026') so visitors to public docs "
                "don't read the project as pre-launch. Exemptions live in "
                "EXEMPT_FILES (CHANGELOG, PUBLIC_READINESS_PLAN — historical "
                "records that legitimately quote prior state)."
            )
            raise AssertionError("\n".join(msg))


class TestCanonicalPlaceholdersAreRendered:
    """Catch the meta-drift class: 'someone added/removed tests but
    didn't re-run scripts/render_docs.py.'

    Earlier this session the canonical placeholders sat at 1560 while
    the live count was 1558 — the renderer had run in a prior tick
    when the test set was different, then test_doc_class_frontmatter
    lost 2 parametrized cases (docs/index.md deletion) without the
    renderer being re-invoked. The N=6 four-surfaces-agree test
    passed because all six surfaces drifted in lockstep — they all
    said 1560.

    `scripts/render_docs.py --check` exits 1 if any canonical
    placeholder is out-of-date relative to its derivation function.
    Spawning it from pytest catches this exact shape without
    duplicating the canonical-computation logic here.

    Cost: ~5s (renderer spawns pytest --collect-only internally).
    Acceptable for a single-test guard that closes the meta-loop.
    """

    def test_render_docs_check_exits_clean(self):
        import subprocess
        result = subprocess.run(
            [".venv/bin/python", "scripts/render_docs.py", "--check"],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        if result.returncode != 0:
            raise AssertionError(
                "scripts/render_docs.py --check reports canonical-placeholder "
                "drift. The likely cause: tests/CLI/MCP-tools/etc changed but "
                "the canonical-rendered docs weren't re-flowed. Run:\n\n"
                "    python scripts/render_docs.py\n\n"
                "to update the placeholders, then commit. Stdout:\n"
                f"{result.stdout[-800:]}\n\nStderr:\n{result.stderr[-400:]}"
            )
