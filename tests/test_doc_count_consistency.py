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

        # Surface A: claude.md Status block — "N tests passing" OR
        # "N tests scoped" (the latter wording introduced 2026-05-22 in
        # commit ef17b9a to disclose the intentional fail from the
        # tightened TestLaunchpadScreenshotFreshness guard — the test
        # gate became "X scoped (Y passing + ...)" rather than overclaiming
        # "X passing" when 1 is intentionally red).
        status_count = _extract(
            CLAUDE_MD,
            rf"{CANON}(\d+){ENDCANON}\s*tests (?:passing|scoped)",
        )
        # Surface B: claude.md Verified status — "pytest -q — **N passed**"
        # OR "pytest -q — **N scoped**" (same wording shift as Surface A).
        verified_count = _extract(
            CLAUDE_MD,
            rf"pytest -q.{{0,5}}\*\*{CANON}(\d+){ENDCANON}\s*(?:passed|scoped)\*\*",
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
            # Accept either "tests passing + N skipped" (original)
            # or "tests scoped — Y passing + N skipped" (post-ef17b9a
            # wording to disclose intentional fail).
            rf"\({CANON}(\d+){ENDCANON}\s*tests (?:passing|scoped)\s*[+—]",
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
        # Accept either "tests passing" or "tests scoped" wording
        # (the latter introduced in commit ef17b9a, 2026-05-22, to
        # disclose intentional failures from the tightened screenshot
        # guard).
        status_count = _extract(
            CLAUDE_MD,
            r"(?:<!--\s*canonical:\w+\s*-->)?(\d+)(?:<!--\s*/canonical\s*-->)?\s*tests (?:passing|scoped)",
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
            "### The eight MCP tools",
        ):
            idx = claude.find(variant)
            if idx > 0:
                section_start = idx
                break
        assert section_start > 0, (
            "claude.md MCP-tools section not found — looked for "
            "'### The eleven/ten/nine/eight MCP tools'. "
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
    surface it ships from. The canonical-4 claim is load-bearing in
    claude.md (lifecycle order + section structure); locking it shut
    means no future numeric drift in that section can ship silently.

    Updated 2026-05-21 after record_outcome retired (canonical 5 → 4,
    8 total).
    """

    def test_no_stale_canonical_count_phrasings_in_docs(self):
        # Drift-known-bad phrasings that should NEVER appear.
        forbidden = [
            "canonical 6",
            "canonical six",
            "canonical 7",
            "canonical seven",
            "canonical 5",  # record_outcome retired 2026-05-21 → canonical 4
            "canonical five",
            "### The eleven MCP",
            "### The ten MCP",
            # "### The eight MCP" was forbidden 2026-05-25 (after import_provider_memory
            # shipped, bumping total to 9). It became valid AGAIN 2026-05-26 when
            # handoff was retired (back to 8). Re-add to forbidden if total moves off 8.
            "1 launch-arc additions",
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
            "MCP canonical-subset claims drifted to known-bad values:\n  "
            + "\n  ".join(violations)
            + "\n\nThe canonical subset is 4 tools (route, run_council, "
            "get_persona, get_council_status). Total MCP surface is 8. "
            "If either changed, update both this test and the docs."
        )

    def test_canonical_count_claims_in_claude_md_agree(self):
        # All "canonical (\d+)" claims in claude.md must agree with
        # each other AND with the literal "four" lifecycle header
        # (since 2026-05-21 when record_outcome retired).
        claude = (REPO / "claude.md").read_text(encoding="utf-8")
        numeric_claims = re.findall(r"canonical (\d+)\b", claude)
        word_claims = re.findall(r"canonical (four|five|six|seven|eight)\b", claude, re.IGNORECASE)
        assert numeric_claims or word_claims, (
            "claude.md has no 'canonical (\\d+)' claims — did the "
            "MCP section get restructured? Update this test."
        )
        word_to_num = {"four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8}
        nums = {int(n) for n in numeric_claims} | {
            word_to_num[w.lower()] for w in word_claims
        }
        assert nums == {4}, (
            f"claude.md has mixed 'canonical' counts: {sorted(nums)}. "
            "All must agree on 4 (post-record_outcome-retirement, 2026-05-21)."
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
    Surface 30 (Personalized benchmark / eval summary card) and several
    launch-arc surfaces. (Surface 32 — the rate-limit-saves card — was
    also added at T-1 then retired 2026-05-21 with the rest of the
    rating UX; the smoke surface now guards its absence per iter #73.)
    The stale screenshot would have shown a meaningfully thinner
    launchpad than the one a fresh install produces — false advertising
    for the launch-arc work.

    Same shape applies to docs/me_card_example.png (the OTHER Product
    Hunt asset named in launch-package): the example PNG can drift
    behind the rendering source (me_card.py) if rendering changes ship
    without re-running me-card. Both assets are guarded here.

    Guard: assert each asset's mtime isn't grossly older (>3 days) than
    the source files that drive its rendering. Threshold is generous —
    only catches true drift, not normal edit churn.
    """

    STALE_THRESHOLD_DAYS = 3
    # Tighter threshold for launchpad_template.py specifically — that
    # file IS the visual surface. Any structural UI edit (chip removed,
    # badge swapped, color changed) MUST land alongside a regenerated
    # screenshot. Iter 2026-05-22 set this after Phase 3d swapped the
    # "Preferred" rating chip for "Lens pick" badge but README + smoke
    # screenshots stayed on the pre-swap UI for 3+ days. The existing
    # 3-day threshold was too generous for template-level structural
    # changes; tightened to 1 day for that one driver specifically.
    TEMPLATE_STRICT_THRESHOLD_DAYS = 1

    def _assert_asset_fresh(
        self,
        asset_relpath: str,
        driver_relpaths: list[str],
        regen_recipe: str,
        strict_drivers: tuple[str, ...] = (),
    ):
        asset = REPO / asset_relpath
        if not asset.exists():
            return  # not yet generated — guard is a no-op
        asset_mtime = asset.stat().st_mtime
        stale_drivers: list[tuple[str, float, float]] = []
        for rel in driver_relpaths:
            path = REPO / rel
            if not path.exists():
                continue
            src_mtime = path.stat().st_mtime
            age_days = (src_mtime - asset_mtime) / 86400
            threshold = (
                self.TEMPLATE_STRICT_THRESHOLD_DAYS
                if rel in strict_drivers
                else self.STALE_THRESHOLD_DAYS
            )
            if age_days > threshold:
                stale_drivers.append((path.name, age_days, threshold))
        assert not stale_drivers, (
            f"{asset_relpath} is grossly stale relative to its rendering "
            f"source files: {stale_drivers} (each tuple: file, age_days, threshold). "
            f"Regenerate via: {regen_recipe}"
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
            # launchpad_template.py is the visual surface — UI changes
            # there MUST land with a refreshed screenshot within 1 day.
            strict_drivers=("src/trinity_local/launchpad_template.py",),
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

    def test_docs_html_pages_declare_favicon(self):
        """keepwhatworks.com (docs/index.html + article pages) had no
        favicon for months — browser tabs all rendered Chrome's gray
        default. The favicon claim lives at the surface that ships it
        per principle #21. Earned its place 2026-05-21 after the fix.

        The favicon target shares the Trinity extension toolbar icon's
        cream-BG / sage-T mark (docs/favicon.png is a copy of
        browser-extension/icons/icon-32.png) so one product reads as
        one product across the launchpad / toolbar / marketing site
        triplet.
        """
        repo = self.REPO
        favicon = repo / "docs" / "favicon.png"
        assert favicon.exists(), (
            "docs/favicon.png missing — every keepwhatworks.com tab "
            "loses its brand mark."
        )
        # Non-Trinity scratchpads / experiment HTML pages in docs/
        # are explicitly allowlisted. Keeping a small list (not a glob
        # pattern) so adding a new Trinity docs page still requires a
        # `<link rel="icon">` — only known unrelated experiments slip
        # past. Maintained as drift is found in the post-launch sweep
        # 2026-05-23 (drift class: ad-hoc scratch HTML in docs/ ships
        # with no favicon and no Trinity branding).
        _SCRATCH_HTML_EXCLUSIONS = {"maxroom-redesign.html"}
        for html_path in sorted((repo / "docs").glob("*.html")):
            if html_path.name in _SCRATCH_HTML_EXCLUSIONS:
                continue
            content = html_path.read_text(encoding="utf-8")
            assert 'rel="icon"' in content, (
                f"{html_path.name} has no <link rel='icon'> — "
                "tab renders the gray default favicon."
            )
        for html_path in sorted((repo / "docs" / "articles").glob("*.html")):
            content = html_path.read_text(encoding="utf-8")
            assert 'rel="icon"' in content, (
                f"docs/articles/{html_path.name} has no <link rel='icon'> "
                "— article tab loses brand identity. Add "
                '<link rel="icon" type="image/png" href="../favicon.png"> '
                "to the head."
            )

    def test_manifest_declares_icons_and_files_exist(self):
        """Without an `icons` block (and an `action.default_icon` for
        the toolbar surface), Chrome renders the gray puzzle-piece
        placeholder in the toolbar + the chrome://extensions list.
        First impression breakage for every install. Earned its place
        in the regression suite 2026-05-21 after the icons were added
        — every claim made by the manifest needs the file to exist on
        disk OR a contributor's `pip install` ships a half-broken
        extension to the next user."""
        manifest_path = self.REPO / "browser-extension" / "manifest.json"
        manifest = json.loads(manifest_path.read_text())

        for surface in ("icons", "action"):
            assert surface in manifest, (
                f"manifest.json missing {surface!r} block — Chrome shows "
                "the gray puzzle-piece placeholder without it."
            )

        # The top-level icons block (chrome://extensions list + system
        # toolbar). The four sizes Chrome's docs list as expected.
        icons = manifest["icons"]
        for size in ("16", "32", "48", "128"):
            assert size in icons, (
                f"manifest.icons missing {size}px entry — Chrome scales "
                "from larger sizes but loses crispness in the toolbar."
            )
            path = self.REPO / "browser-extension" / icons[size]
            assert path.exists(), (
                f"manifest.icons[{size!r}] points at {icons[size]!r} but "
                "the file isn't on disk. Run "
                "`.venv/bin/python scripts/render_extension_icons.py` "
                "to regenerate."
            )

        # action.default_icon — the toolbar button specifically. Chrome
        # falls back to manifest.icons when this is absent, but spelling
        # it out makes the toolbar contract explicit + survives any
        # future toolbar-icon variant (active/inactive, popup-open).
        default_icon = manifest["action"].get("default_icon")
        assert default_icon, (
            "manifest.action.default_icon missing — the toolbar button "
            "stays as Chrome's gray puzzle piece without it."
        )
        for size, rel in default_icon.items():
            path = self.REPO / "browser-extension" / rel
            assert path.exists(), (
                f"manifest.action.default_icon[{size!r}] points at "
                f"{rel!r} but the file isn't on disk."
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
        ("`gemini` CLI", "`agy` CLI",
         "tick 120 found 4 user-facing surfaces (README/install-deep/"
         "SECURITY/07_pricing_faq) teaching users to authenticate the "
         "legacy `gemini` binary as a Trinity dispatch target. The "
         "config providers dict now dispatches via `agy` per the "
         "2026-05-20 rename; the `gemini` binary is read-only (ingest "
         "via parse_gemini_cli_session) but isn't a council member. "
         "The previous 'Gemini CLI' BANNED entry missed the backtick-"
         "wrapped code-quoted form because substring match couldn't "
         "see through the markdown backticks ('gemini` cli' isn't "
         "'gemini cli'). Catches both `gemini` CLI and `gemini` CLIs."),
        ("~/.trinity/cortex/", "~/.trinity/scoreboard/",
         "tick 131 — the cortex_dir() helper was retired 2026-05-20 "
         "(per claude.md L762 + retired_names.py); the directory was "
         "created as a side-effect but never written to. Canonical "
         "post-rename storage is `scoreboard/` (picks.json + "
         "routing.json). Two surfaces flipped: founder-essay-draft.md "
         "L146 + L232 (was referencing retired routing-pattern path), "
         "spec-v1.5.md L132-134 (diagram showed 3 NEW v1.5 files in "
         "cortex/ but per task #51 they collapsed into picks.json). "
         "The legacy-migration narration in state_paths.py docstring "
         "is exempt (it documents the migration FROM the retired "
         "path, which is intentional)."),
        ("(claude, codex, gemini)", "(claude, codex, antigravity)",
         "iter #37 catch — slug-list claim using the pre-rebrand "
         "`gemini` slug. Distinct from the existing `Gemini CLI` "
         "BANNED entries which catch harness-name uses; this catches "
         "the bare-lowercase 3-slug list form. The mixed marketing "
         "trio 'Claude, Codex, and Gemini' (Title Case, oxford comma) "
         "stays intentional — it's the model-family brand, not the "
         "slug. The lowercase paren'd form, however, is always a "
         "slug-list and must use `antigravity` per config.example.json. "
         "Caught in docs/architectural-gaps.md L362's Gap F symptom "
         "claim — class:aspirational but the symptom describes the "
         "CURRENT provider set."),
        ("`claude`, `codex`, `gemini`", "`claude`, `codex`, `agy`",
         "iter #57 catch — backtick-wrapped dispatch triple naming the "
         "legacy `gemini` CLI as a Trinity council member. Found in "
         "SECURITY.md L55 + docs/launch-day/03_hn_objection_faq.md L19 "
         "+ docs/launch-day/10_hn_faq_full.md L39/55/111. The shipped "
         "config.json dispatches via `agy` (Antigravity CLI, slug "
         "`antigravity`) per task #127's 2026-05-21 migration; the "
         "legacy `gemini` binary stays read-only via "
         "parse_gemini_cli_session for ingest. Distinct from the bare "
         "paren'd form caught above — substring match needs the exact "
         "backtick triple shape to catch this drift. Catches "
         "`claude`, `codex`, `gemini` and `claude` / `codex` / `gemini` "
         "(both with backticks)."),
        ("`claude` / `codex` / `gemini`", "`claude` / `codex` / `agy`",
         "iter #57 sub-case — slash-separated backtick triple, same "
         "drift as the comma form. The Antigravity rebrand applies "
         "regardless of the separator."),
        ("Skill tier — primary", "(removed — MCP is the primary tier post 2026-05-19 pivot)",
         "iter #52 catch — pre-pivot framing. The 2026-05-19 pivot "
         "made MCP the primary tier; the skill at "
         "~/.claude/skills/trinity/ is kept as a back-compat alias. "
         "INSTALL-skill.md L5/L9 had 'Skill tier — primary' as its "
         "h1 + intro framing. Same drift class as iter #38's install.sh "
         "'Skill is primary' comment. The HEADING phrase is more "
         "specific than the inline-comment phrase, so the BANNED "
         "entry is the literal heading form."),
        ("Skill is primary", "MCP is primary (per 2026-05-19 pivot)",
         "iter #52 catch — inline-comment form of the same pre-pivot "
         "claim. iter #38 fixed install.sh's instance but didn't add "
         "the phrase to BANNED, so docs/INSTALL-skill.md's L7-9 prose "
         "drift survived undetected until iter #52's audit."),
        ("@openclaw.dev", "@keepwhatworks.com",
         "contact-domain consolidation 2026-05-21 (tick 118). Trinity's "
         "ops contact addresses (security@, conduct@, teams@) had "
         "drifted onto a vestigial openclaw.dev domain from the "
         "pre-rebrand era; canonical project brand is keepwhatworks.com "
         "(same domain the share-card landing URL flipped to on "
         "2026-05-17). 5 surfaces fixed: SECURITY.md, CODE_OF_CONDUCT.md, "
         "docs/teams.md, docs/launch-package.md, docs/launch-day/"
         "10_hn_faq_full.md. Future drift caught by this BANNED entry."),
    ]

    # ----- #130: discovery-driven scan via SCAN_EXCLUSIONS -----
    #
    # Past pattern (SCAN_FILES allowlist): every new user-facing doc had
    # to be manually added; missing → drift goes undetected. The history
    # of this list shows that exact failure mode 20+ times — each
    # surface joined the list only AFTER a drift hunt found a leak in it
    # (every per-file entry below carries the iter # that caught it).
    #
    # Flipped pattern (council_76e5aef79bb9f241 #2): glob-discover all
    # files of the right extension under the repo, then subtract a
    # SCAN_EXCLUSIONS denylist. New docs join the scan automatically;
    # only intentional opt-outs need explicit entries.
    #
    # SCAN_FILES is preserved as a SANITY CHECK list: every entry here
    # must still appear in the discovered set after exclusions. Catches
    # accidental over-broadening of SCAN_EXCLUSIONS that would silently
    # drop a known load-bearing doc out of the scan.
    SCAN_GLOBS: tuple[str, ...] = (
        "*.md",
        "pyproject.toml",
        ".github/**/*.yml",
        ".github/**/*.md",
        "docs/**/*.md",
        "skills/**/*.md",
        "src/trinity_local/data/skills/**/*.md",
        "scripts/*.sh",
        "browser-extension/*.md",
    )
    # Path-prefix excludes (directory roots Trinity should never scan).
    # `node_modules/`, `.venv/`, `.git/`, etc. handled by glob roots.
    SCAN_EXCLUDED_PREFIXES: tuple[str, ...] = (
        # Historical surfaces — banned strings appear intentionally as
        # the record of what was retired
        "docs/historical/",
        # Local dev state, not user-facing
        "state/",
        # Bundled skill mirror — covered by test_bundled_skill_matches_top_level
        # which pins it byte-identical to the top-level copy. Don't
        # double-scan; if the top-level passes, the mirror passes too.
        "src/trinity_local/data/skills/",
        # Test/build/cache directories that occasionally slip past glob roots
        ".claude/",
        ".pytest_cache/",
        ".playwright-mcp/",
    )
    SCAN_FILES = [
        "README.md",
        "claude.md",
        # CONTRIBUTING.md added 2026-05-21 after iter 44 caught
        # "Gemini CLI" in the architectural-commitments list (L161
        # "Trinity dispatches via Claude Code, Codex, Gemini CLI").
        # The doc teaches contributors what NOT to violate; using
        # the pre-rebrand harness name there is structurally the
        # same drift as the launch-day docs.
        "CONTRIBUTING.md",
        "DESIGN.md",
        "SECURITY.md",
        "CODE_OF_CONDUCT.md",
        "pyproject.toml",
        ".github/ISSUE_TEMPLATE/config.yml",
        # ISSUE_TEMPLATE markdown templates added iter #64 after
        # bug_report.md L34 was caught listing "Claude Code / Codex
        # CLI / Gemini CLI / Cursor" as the harness 4-tuple — same
        # drift class as the launch-day docs (post the 2026-05-21
        # Antigravity rebrand, slot 3 is Antigravity, not Gemini
        # CLI). Every "New Issue" form on GitHub renders these
        # templates verbatim, so the harness list there is just as
        # user-facing as the README.
        ".github/ISSUE_TEMPLATE/bug_report.md",
        ".github/ISSUE_TEMPLATE/feature_request.md",
        ".github/ISSUE_TEMPLATE/adapter_request.md",
        ".github/pull_request_template.md",
        "docs/teams.md",
        "docs/launch.md",
        "docs/launch-package.md",
        "docs/MCP_REGISTRY_SUBMISSIONS.md",
        "docs/frontend-architecture.md",
        "docs/spec-v1.md",
        "docs/spec-v1.5.md",
        "docs/spec-v1.6.md",
        # spec-v2.md added 2026-05-21 after the "Gemini CLI" phrasing
        # slipped through in the v1.0 hero quote (2 lines in the
        # narrative-arc table). v2 is the sunset trained-coordinator
        # doc but still describes v1.0's pitch — that quote has to use
        # the post-Antigravity-rebrand wording to match the canonical
        # hero in README / launch-package / claude.md.
        "docs/spec-v2.md",
        "docs/product-spec.md",
        # founder-essay-draft.md added 2026-05-21 after iter 22 caught
        # "Gemini CLI is in a browser" on L31 — a personal-narrative
        # surface that ships to the founder's blog T-7 (per the
        # naked-`pip install` guard's reference at L2032). Same
        # rebrand-drift risk as the other launch-facing surfaces.
        "docs/founder-essay-draft.md",
        # three-tier-architecture.md added 2026-05-21 after iter 23
        # caught two "Gemini CLI" mentions in a class:live spec doc
        # (Tier 1 description L18, sequencing rationale L161). The
        # doc is the canonical architecture ratified by
        # council_ff3da1fa84906791 — rebrand drift here ships the
        # wrong harness name to every architectural reader.
        "docs/three-tier-architecture.md",
        # architectural-gaps.md added 2026-05-21 after iter 37 caught
        # "(claude, codex, gemini)" on L362 (Gap F symptom claim).
        # The doc is class:aspirational but the symptom prose refers
        # to the CURRENT provider slug list, which has been
        # (claude, codex, antigravity) since the 2026-05-20 rebrand.
        "docs/architectural-gaps.md",
        # scripts/install.sh added 2026-05-21 after iter 38 caught
        # 3 stale claims: two "Gemini CLI" mentions in head comments
        # (L11 + L278) and "Skill is primary" on L15 (pre-2026-05-19
        # pivot to MCP-primary). install.sh is the user-facing
        # curl-bash install path; its inline comments are the first
        # thing a curious operator reads when piping it. Drift here
        # is high-leverage launch credibility.
        "scripts/install.sh",
        # SKILL.md (top-level + bundled) added 2026-05-21 after iter 50
        # caught "Gemini CLI" in both copies' frontmatter description
        # (L3) + intro paragraph (L10). The skill is what runs when a
        # user types /trinity in Claude Code — high-visibility
        # back-compat alias per three-tier-architecture.md L31. The
        # bundled copy at src/trinity_local/data/skills/... must stay
        # byte-identical to the top-level copy (pinned by existing
        # test_bundled_skill_matches_top_level guard); scanning both
        # catches drift if a future edit only touches one half.
        "skills/trinity/SKILL.md",
        # The bundled mirror src/trinity_local/data/skills/trinity/SKILL.md
        # used to live in this list. Removed under #130: it's pinned
        # byte-identical to the top-level skills/trinity/SKILL.md by
        # test_bundled_skill_matches_top_level. Scanning the top-level
        # copy + that pin is equivalent — and SCAN_EXCLUDED_PREFIXES
        # now drops the bundled path explicitly to avoid double-scan.
        # docs/INSTALL-*.md added 2026-05-21 after iter 52 caught
        # "Skill tier — primary" in INSTALL-skill.md L5 + L9 (pre-
        # 2026-05-19 pivot framing — MCP is the primary tier now).
        # The install doc trio is the first thing a curious user
        # reads when deciding which path to take; pre-pivot framing
        # there ships the wrong mental model.
        "docs/INSTALL-skill.md",
        "docs/INSTALL-pip.md",
        "docs/INSTALL-extension.md",
        # All launch-day artifacts (paste-ready copy).
        "docs/launch-day/00_leaderboard.md",
        "docs/launch-day/01_tweet_thread.md",
        "docs/launch-day/02_show_hn_post.md",
        "docs/launch-day/03_hn_objection_faq.md",
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

    @classmethod
    def _discover_scan_files(cls) -> list[str]:
        """Discovery-driven file list (#130).

        Walks the repo using SCAN_GLOBS; drops any path matching
        SCAN_EXCLUDED_PREFIXES or appearing in EXEMPT_FILES. Returns
        repo-relative posix-style paths, sorted for deterministic
        ordering across test runs.
        """
        seen: set[str] = set()
        for pattern in cls.SCAN_GLOBS:
            for path in REPO.glob(pattern):
                if not path.is_file():
                    continue
                rel = path.relative_to(REPO).as_posix()
                if rel in cls.EXEMPT_FILES:
                    continue
                if any(rel.startswith(pfx) for pfx in cls.SCAN_EXCLUDED_PREFIXES):
                    continue
                seen.add(rel)
        return sorted(seen)

    def test_scan_files_subset_of_discovery(self):
        """Sanity: every explicit SCAN_FILES entry must still be picked
        up by the discovery walk. Catches regressions where an
        over-broad SCAN_EXCLUDED_PREFIXES would silently drop a known
        load-bearing doc out of the scan."""
        discovered = set(self._discover_scan_files())
        missing = [
            rel for rel in self.SCAN_FILES
            if rel not in self.EXEMPT_FILES and rel not in discovered
        ]
        if missing:
            raise AssertionError(
                "These SCAN_FILES entries are no longer in the discovered "
                "set (likely SCAN_EXCLUDED_PREFIXES is too broad, OR a "
                "SCAN_GLOBS root no longer covers them): "
                + ", ".join(missing)
            )

    def test_no_banned_synonyms_in_user_facing_docs(self):
        leaks: list[tuple[str, int, str, str]] = []
        # Use the discovered set rather than the explicit SCAN_FILES
        # allowlist. New user-facing docs automatically join the scan
        # without needing a manual SCAN_FILES update.
        for rel in self._discover_scan_files():
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


class TestBundledSkillCommandExamplesValidate:
    """Tick 115 — the bundled SKILL.md (shipped to
    `~/.claude/skills/trinity/SKILL.md` on install) had two example
    commands that crash post-2026-05-20 harness rename:

      mcp__trinity-local__handoff(target_provider="gemini", num_turns=3)
      trinity-local eval-run --target gemini

    Both raise on the user's machine because the config providers dict
    is now keyed by "antigravity" (handoff.py:208 KeyError,
    commands/eval.py:252 rejection). Existing TestNoBannedSynonyms scans
    for "Gemini CLI" specifically, which doesn't catch standalone slug
    references like `--target gemini`. And `SKILL.md` wasn't even in
    that scan's SCAN_FILES list.

    This guard parses the bundled SKILL.md, extracts every literal slug
    used in `target_provider="X"` (MCP handoff arg) and `--target X`
    (eval-run CLI arg), and asserts each X is a real provider in the
    shipped config.json. Catches both today's drift (gemini) and any
    future rename's drift (codex → ???, claude → ???) — the failure
    shape is "skill teaches a slug the user's machine will reject."

    Per principle #14 + #21: regression guard at the surface that
    ships the claim. SKILL.md ships to user disk and is the closest
    thing Trinity has to a tutorial; copy-paste-broken examples
    erode trust on the first command.
    """

    TARGET_PROVIDER_RE = re.compile(r'target_provider="([^"]+)"')
    EVAL_TARGET_RE = re.compile(r'--target\s+([a-z_][a-z0-9_-]*)')
    # Iter #75 catch: bundled SKILL.md "Common follow-ups" L144 taught
    # `trinity-local handoff gemini` — same crash shape as --target gemini
    # (handoff.py:208 KeyError) but the existing regexes missed the
    # positional CLI form. Anchor on the literal CLI prefix.
    HANDOFF_CLI_RE = re.compile(r'trinity-local\s+handoff\s+([a-z_][a-z0-9_-]*)')

    def test_skill_md_example_slugs_resolve_in_config(self):
        from trinity_local.config import load_config

        skill_path = REPO / "src/trinity_local/data/skills/trinity/SKILL.md"
        text = skill_path.read_text(encoding="utf-8")

        mentioned: set[str] = set()
        mentioned.update(self.TARGET_PROVIDER_RE.findall(text))
        mentioned.update(self.EVAL_TARGET_RE.findall(text))
        mentioned.update(self.HANDOFF_CLI_RE.findall(text))

        # `<provider>` is an explicit placeholder, not a literal — strip.
        # Same for `<...>` style placeholders.
        mentioned -= {"provider", "model"}
        mentioned = {m for m in mentioned if not m.startswith("<")}

        if not mentioned:
            pytest.skip("SKILL.md has no literal slug examples to check")

        config = load_config(str(REPO / "src/trinity_local/config.json"))
        valid_slugs = set(config.providers.keys())

        invalid = mentioned - valid_slugs
        if invalid:
            raise AssertionError(
                f"SKILL.md references provider slug(s) {sorted(invalid)} "
                f"that aren't in the shipped config.json providers "
                f"{sorted(valid_slugs)}. The bundled skill teaches a "
                f"command users will see crash on their machine. "
                f"Update SKILL.md to use a canonical slug, or extend "
                f"config.json if the slug should be added."
            )


class TestCouncilOutcomeSchemaCoversAllSerializedFields:
    """Tick 130 — schemas/council_outcome.schema.json is the public
    contract Trinity ships for other tools (Aider / Cline / Continue)
    to adopt — task #117. If the schema undersells the data, adopting
    tools won't know about fields Trinity actually emits.

    Today's catch: CouncilOutcome.to_dict() emits 19 distinct keys,
    but the schema documented only 16. Missing:
      - agreement_score    (aggregate consensus scalar)
      - needs_followup     (chairman re-run hint)
      - primary_session_id (chairman session correlation id)

    All three are emitted when non-None/empty per the
    `if value not in (None, '', {}, [])` filter in to_dict.

    Same drift shape as ticks 128 (dispatch_registry) and 129
    (mcp tools) at the schema-vs-dataclass layer: the dataclass IS
    the canonical source of truth for emitted fields; the schema is
    a derived view that drifted.

    Caveats:
      - Schema may legitimately have MORE fields than to_dict emits
        (e.g. legacy compatibility, planned additions). We only
        check that every TO_DICT field has a schema property.
      - additionalProperties is None (defaults to True) — adopting
        tools won't reject unknown fields, just won't be aware. Still
        a doc-vs-code drift worth catching."""

    def test_schema_describes_every_to_dict_field(self):
        import json

        from trinity_local.council_schema import CouncilOutcome

        schema = json.loads(
            (REPO / "schemas/council_outcome.schema.json").read_text(encoding="utf-8")
        )
        documented = set((schema.get("properties") or {}).keys())

        # Probe which keys to_dict emits. Build a fully-populated instance
        # so every conditional `if value not in (...)` branch fires.
        from trinity_local.council_schema import CouncilMemberResult, CouncilRoutingLabel, CouncilChainStep

        probe = CouncilOutcome(
            council_run_id="council_" + "0" * 16,
            bundle_id="b",
            task_cluster_id="t",
            primary_provider="claude",
            primary_model="claude-sonnet-4-6",
            primary_session_id="sess_42",
            agreement_score=0.85,
            winner_provider="claude",
            winner_model="claude-sonnet-4-6",
            needs_followup=True,
            differences=["X disagreed on Y"],
            member_results=[CouncilMemberResult(provider="claude", model="x", output_text="o")],
            synthesis_prompt="p",
            synthesis_output="s",
            routing_label=CouncilRoutingLabel(winner="claude"),
            mode="chain",
            chain_steps=[CouncilChainStep(step_index=0, model_provider="claude")],
            created_at="2026-05-21T00:00:00",
            metadata={"k": "v"},
        )
        emitted = set(probe.to_dict().keys())

        undocumented = emitted - documented
        if undocumented:
            raise AssertionError(
                f"CouncilOutcome.to_dict() emits keys not described in "
                f"schemas/council_outcome.schema.json: {sorted(undocumented)}. "
                f"Trinity ships this schema as a public contract for other "
                f"tools to adopt (task #117); if it undersells the data, "
                f"adopting tools won't know these fields exist. Add a "
                f"properties entry for each missing key with a clear "
                f"description, or filter the field out of to_dict if it "
                f"shouldn't be part of the contract."
            )


class TestLiveDocsReferenceOnlyRegisteredMcpTools:
    """Tick 129 — docs that claim Trinity ships specific MCP tools
    by name must only reference tools that are actually registered
    in mcp_server.py.

    Today's catch: docs/spec-v1.5.md L314 had
    `mcp__trinity-local__get_cortex_rules(basin_id?, min_trust?)`
    in a signature block — but the actual tool is `get_picks`. The
    cortex→picks rename (task #99) propagated to the surrounding
    narration but missed the signature block. A doc-reading agent
    that copy-pasted `mcp__trinity-local__get_cortex_rules(...)`
    would get tool-not-found at runtime.

    Same drift class as tick 128's dispatch-action guard at a
    different surface: code is the canonical source of truth for
    the tool name set; docs are derived views. This guard pins the
    derived view (in LIVE-class docs only — aspirational specs
    legitimately describe future tools).

    Caveats: README.md is intentionally selective (only highlights
    wedge tools like run_council/handoff). Aspirational specs
    (spec-v1.5.md / product-spec.md / scale-plan.md) describe
    future tools by design — excluded from this guard. The guard
    runs on claude.md + bundled SKILL.md only — the surfaces that
    promise SHIPPED state."""

    LIVE_DOCS_TO_CHECK = [
        "claude.md",
        "src/trinity_local/data/skills/trinity/SKILL.md",
        "skills/trinity/SKILL.md",
    ]

    def test_live_docs_only_reference_registered_mcp_tools(self):
        import re

        mcp_server = (REPO / "src/trinity_local/mcp_server.py").read_text(encoding="utf-8")
        registered = set(re.findall(r'Tool\(\s*name\s*=\s*["\']([\w_]+)["\']', mcp_server))
        assert registered, "Failed to parse MCP tool registrations from mcp_server.py"

        errors: list[str] = []
        for rel in self.LIVE_DOCS_TO_CHECK:
            path = REPO / rel
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            referenced = set(re.findall(r'mcp__trinity-local__([\w_]+)', text))
            stale = referenced - registered
            if stale:
                errors.append(
                    f"  {rel}: references {sorted(stale)} which aren't "
                    f"registered MCP tools (actual: {sorted(registered)})"
                )

        if errors:
            raise AssertionError(
                "Live-class docs reference MCP tools that don't exist in "
                "mcp_server.py:\n" + "\n".join(errors) + "\n\n"
                "Either update the doc to use the canonical tool name, "
                "or register the missing tool in mcp_server.py."
            )


class TestClaudeMdDependenciesMatchPyproject:
    """Iter #31 catch — claude.md's "Coding conventions" bullet enumerated
    runtime dependencies as "No runtime dependencies beyond `Pillow>=10`."
    Live pyproject.toml has THREE runtime deps: Pillow, mcp (HIGH#4 fix
    promoted to default in task #59), and numpy (matmul fast-path).
    Same `[mlx]` extras claim listed only `sentence-transformers` when
    the actual extras carry `einops` and `torch>=2.0` too. A reader
    relying on the claim would underestimate what `pip install trinity-local`
    actually pulls in.

    Same drift shape as the trust-substrate plan-vs-reality (iter #26)
    one layer down: the claim was accurate when written, the reality
    grew (mcp promoted from optional → default; numpy added for the
    matmul fast-path), the claim didn't follow. Principle #20 in a
    different surface.

    Guard shape: parse pyproject.toml's [project] dependencies + the
    [project.optional-dependencies] section. For each declared package,
    assert the package name appears somewhere in claude.md's deps
    paragraph (the "Minimal runtime dependencies" / "Coding conventions"
    bullet). Strict subset assertion — claude.md should mention every
    pyproject dep (it can add color the toml doesn't carry, but it
    can't omit a dep that ships).
    """

    def test_claude_md_lists_every_pyproject_runtime_dep(self):
        # Iter #44 extension: also checks CONTRIBUTING.md after the same
        # "missing numpy" drift bit the contributor-facing deps bullet —
        # iter #31's fix patched claude.md but left CONTRIBUTING.md
        # behind. Both docs are now bound to pyproject runtime deps.
        import re
        import tomllib

        with (REPO / "pyproject.toml").open("rb") as f:
            pyproject = tomllib.load(f)
        runtime_deps = pyproject["project"]["dependencies"]
        # Parse package names out of dep specifier strings like
        # `"Pillow>=10"`, `"mcp>=1.0  # comment"`, etc.
        pkg_pattern = re.compile(r"^([A-Za-z][\w-]*)")
        pkg_names = set()
        for dep in runtime_deps:
            m = pkg_pattern.match(dep)
            if m:
                pkg_names.add(m.group(1).lower())

        # Optional-dependencies: walk each extra and collect its packages too.
        extras = pyproject["project"].get("optional-dependencies", {})
        extras_pkg_names: dict[str, set[str]] = {}
        for extra_name, dep_list in extras.items():
            extras_pkg_names[extra_name] = set()
            for dep in dep_list:
                m = pkg_pattern.match(dep)
                if m:
                    extras_pkg_names[extra_name].add(m.group(1).lower())

        claude_md = (REPO / "claude.md").read_text(encoding="utf-8")
        # Restrict the search to the dependencies bullet — claude.md
        # is long and other sections mention numpy / mcp in different
        # contexts. The bullet starts with "Minimal runtime dependencies."
        # or "No runtime dependencies" (legacy form).
        bullet_match = re.search(
            r"-\s+\*\*(?:Minimal runtime dependencies|No runtime dependencies)[^\n]*\n",
            claude_md,
        )
        if not bullet_match:
            raise AssertionError(
                "Couldn't locate the deps bullet in claude.md. Either "
                "the bullet was renamed or the regex needs updating."
            )
        bullet = bullet_match.group(0).lower()

        missing_runtime = sorted(pkg for pkg in pkg_names if pkg not in bullet)
        missing_extras: list[str] = []
        for extra_name, pkgs in extras_pkg_names.items():
            for pkg in pkgs:
                if pkg not in bullet:
                    missing_extras.append(f"{extra_name}:{pkg}")
        missing_extras.sort()

        errors: list[str] = []
        if missing_runtime:
            errors.append(
                f"Runtime deps in pyproject.toml not mentioned in "
                f"claude.md deps bullet: {missing_runtime}"
            )
        if missing_extras:
            errors.append(
                f"Optional extras' packages not mentioned in claude.md "
                f"deps bullet: {missing_extras}"
            )
        if errors:
            raise AssertionError(
                "\n".join(errors)
                + "\n\nFix: extend the bullet to enumerate every dep "
                "with a one-line role description (e.g. `mcp>=1.0` "
                "(MCP server runtime — install-mcp registers Trinity "
                "in Claude Code / Codex / Antigravity)). The bullet "
                "is the canonical contributor-facing summary of "
                "what `pip install trinity-local` pulls in."
            )


    def test_architectural_commitments_counts_match(self):
        """Iter #45 catch — claude.md's "Architectural commitments
        (load-bearing, not negotiable)" section lists 5 items; the
        same section in CONTRIBUTING.md ("Architectural commitments
        (don't break these)") listed only 4. The missing item was
        #5: "HF Hub offline by default" — the privacy + reliability
        invariant that pins HF_HUB_OFFLINE=1 at startup. A PR author
        reading CONTRIBUTING.md wouldn't know they shouldn't add
        code that makes surprise HF Hub calls; the PR would get
        rejected with surprise at review time.

        Same drift shape as iter #44's deps-bullet drift between
        claude.md and CONTRIBUTING.md — two surfaces describing
        the same architectural fact, the older one (CONTRIBUTING.md
        was less-recently-edited until this iter) undercounting.

        Guard shape: count numbered list items immediately under the
        "Architectural commitments" headers in both docs; assert
        the counts match. Doesn't pin item-by-item equivalence (the
        prose can rephrase), only that the LIST LENGTH agrees —
        which is the property that bit iter #45. Adding a new
        commitment to claude.md without propagating to CONTRIBUTING.md
        now fails the test.
        """
        import re

        claude_md = (REPO / "claude.md").read_text(encoding="utf-8")
        contributing_md = (REPO / "CONTRIBUTING.md").read_text(encoding="utf-8")

        def count_commitments(doc: str, doc_name: str) -> int:
            # Find the section header.
            m = re.search(
                r"^##\s+Architectural commitments[^\n]*\n",
                doc,
                re.MULTILINE,
            )
            if not m:
                raise AssertionError(
                    f"Couldn't find '## Architectural commitments' header in "
                    f"{doc_name}"
                )
            # Section body runs until the next '## ' header.
            after = doc[m.end():]
            next_header = re.search(r"^##\s+", after, re.MULTILINE)
            section = after[: next_header.start()] if next_header else after
            # Count numbered list items at start of line:
            # `^N. **<title>**...`
            items = re.findall(
                r"^\d+\.\s+\*\*[^*]+\*\*",
                section,
                re.MULTILINE,
            )
            return len(items)

        claude_count = count_commitments(claude_md, "claude.md")
        contributing_count = count_commitments(contributing_md, "CONTRIBUTING.md")

        if claude_count != contributing_count:
            raise AssertionError(
                f"Architectural-commitments list length disagrees:\n"
                f"  claude.md       : {claude_count} commitments\n"
                f"  CONTRIBUTING.md : {contributing_count} commitments\n\n"
                f"These are two surfaces of the same load-bearing list. "
                f"Adding a commitment to one without the other means a "
                f"contributor reading the shorter list misses a "
                f"rejection-criterion that PR review will apply. "
                f"Either update the shorter list to match, or — if the "
                f"divergence is intentional — extract the count "
                f"discrepancy reason here and document the exception."
            )

    def test_contributing_md_lists_every_pyproject_runtime_dep(self):
        """Iter #44 catch — CONTRIBUTING.md L168's "Code style" bullet
        had the SAME drift the iter-#31 fix caught in claude.md:
        listed only Pillow + mcp but missed numpy>=1.26 (added per
        Bug HIGH#4 + the matmul fast-path). iter #31 patched claude.md
        but didn't co-edit CONTRIBUTING.md because nothing pinned the
        two surfaces to each other.

        Sibling of test_claude_md_lists_every_pyproject_runtime_dep —
        same shape, same source of truth (pyproject runtime deps),
        different consumer doc. The CONTRIBUTING.md bullet is the
        first-impression contributor-facing claim; under-counting
        runtime deps misleads new contributors about install
        footprint and what's actually pip-installed.

        Bullet shape: `- N runtime dependencies: <pkg>=<v> (...)`,
        or legacy `- No runtime dependencies beyond <pkg>=<v> ...`.
        """
        import re
        import tomllib

        with (REPO / "pyproject.toml").open("rb") as f:
            pyproject = tomllib.load(f)
        runtime_deps = pyproject["project"]["dependencies"]
        pkg_pattern = re.compile(r"^([A-Za-z][\w-]*)")
        pkg_names: set[str] = set()
        for dep in runtime_deps:
            m = pkg_pattern.match(dep)
            if m:
                pkg_names.add(m.group(1).lower())

        contributing_md = (REPO / "CONTRIBUTING.md").read_text(encoding="utf-8")
        # Find the dependencies bullet. The CONTRIBUTING.md form is
        # somewhat different from claude.md — we match "runtime
        # dependencies" in a code-style list item.
        bullet_match = re.search(
            r"-\s+[^\n]*runtime dependencies[^\n]*\n",
            contributing_md,
            re.IGNORECASE,
        )
        if not bullet_match:
            raise AssertionError(
                "Couldn't locate the runtime-dependencies bullet in "
                "CONTRIBUTING.md. The Code-style section should list "
                "the runtime deps in a one-line bullet."
            )
        bullet = bullet_match.group(0).lower()

        missing = sorted(pkg for pkg in pkg_names if pkg not in bullet)
        if missing:
            raise AssertionError(
                f"Runtime deps in pyproject.toml not mentioned in "
                f"CONTRIBUTING.md's deps bullet: {missing}\n\n"
                f"Bullet found: {bullet.strip()!r}\n\n"
                f"Fix: extend the bullet to name every runtime dep "
                f"(currently three: Pillow, mcp, numpy). The bullet "
                f"is the contributor-facing summary of what "
                f"`pip install -e .` pulls in — under-counting it "
                f"misleads new contributors about install footprint."
            )


class TestClaudeMdMcpSignaturesMatchSchema:
    """Iter #29 catch — claude.md's `### The eight MCP tools` section
    enumerates each tool with a prose-form signature like
    `route(task, harness?, available_models?, ...)`. Per
    three-tier-architecture.md L20-22 those signatures ARE the contract
    an MCP-capable agent reads at handshake. Drift caught: `ask` was
    documented as `(task, harness, available_models, budget)` while
    the actual inputSchema is `(query, available_providers, top_k)` —
    completely different param names. An agent literally following
    claude.md and calling `ask(task=..., harness=...)` would get
    schema-rejected. `mark_pick_wrong` had the same shape: documented
    `(task_type)`, actual `(basin_id, reason, reset)`. The
    tick-129/tick-136 guards catch tool-NAME drift; this one catches
    tool-SIGNATURE drift (one level deeper).

    Guard shape: parse each Tool(...) registration in mcp_server.py
    to extract its property names. For each tool, locate the
    enumerated signature paragraph in claude.md (the
    ``**`tool_name(...)`**`` markdown pattern). Assert every actual
    property name appears verbatim in that signature's parenthesized
    arg list.

    Excluded: nested object properties (e.g. `responses[].content`)
    — only top-level property names are checked. The signature
    string can use `param?` for optional + `param` for required;
    both forms match. Aliases that intentionally differ across
    surfaces (e.g. naming `available_models` vs `available_providers`
    for two different tools) are still caught because the guard
    pins to the SPECIFIC tool's schema.
    """

    def test_claude_md_signatures_cover_all_input_properties(self):
        import ast
        import re

        mcp_src = (REPO / "src/trinity_local/mcp_server.py").read_text(
            encoding="utf-8"
        )
        # Parse mcp_server.py and extract each Tool() ctor's name +
        # inputSchema properties. AST walk is the right tool — regex
        # over the source would miss nested-dict context.
        tree = ast.parse(mcp_src)
        tools: dict[str, set[str]] = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if not (isinstance(func, ast.Name) and func.id == "Tool"):
                continue
            kwargs = {kw.arg: kw.value for kw in node.keywords}
            name_node = kwargs.get("name")
            schema_node = kwargs.get("inputSchema")
            if not isinstance(name_node, ast.Constant):
                continue
            tool_name = name_node.value
            props: set[str] = set()
            if isinstance(schema_node, ast.Dict):
                # Walk the dict for the 'properties' key.
                for k, v in zip(schema_node.keys, schema_node.values):
                    if (
                        isinstance(k, ast.Constant)
                        and k.value == "properties"
                        and isinstance(v, ast.Dict)
                    ):
                        for pk in v.keys:
                            if isinstance(pk, ast.Constant):
                                props.add(pk.value)
            tools[tool_name] = props

        claude_md = (REPO / "claude.md").read_text(encoding="utf-8")

        missing: list[str] = []
        for tool, props in sorted(tools.items()):
            if not props:
                # Empty schema (get_persona) — nothing to check.
                continue
            # Locate the enumerated signature paragraph for this tool.
            # Pattern: `\d+\. \*\*\`<tool>(<args>)\`\*\*`
            sig_re = re.compile(
                rf"\d+\.\s+\*\*`{re.escape(tool)}\(([^)]*)\)`\*\*"
            )
            m = sig_re.search(claude_md)
            if not m:
                missing.append(
                    f"  {tool}: no enumerated `**`{tool}(...)`**` signature "
                    f"in claude.md (tool is registered with properties "
                    f"{sorted(props)})"
                )
                continue
            sig_args = m.group(1)
            # Strip `?` suffix to allow both required and optional notation.
            for prop in sorted(props):
                if not re.search(rf"\b{re.escape(prop)}\b", sig_args):
                    missing.append(
                        f"  {tool}: signature `{tool}({sig_args})` doesn't "
                        f"mention property `{prop}` (full inputSchema "
                        f"properties: {sorted(props)})"
                    )

        if missing:
            raise AssertionError(
                "claude.md's `### The eight MCP tools` section has "
                "signature drift relative to mcp_server.py's actual "
                "inputSchema definitions. The tool docstrings ARE the "
                "contract (per docs/three-tier-architecture.md L20-22) "
                "— an agent reading claude.md and calling a tool with "
                "the documented arg name would get schema-rejected if "
                "the doc names diverge from code.\n\n"
                + "\n".join(missing)
                + "\n\n"
                "Fix: update the prose signature in claude.md's tools "
                "section to match the inputSchema properties. Use "
                "`param?` to mark optional / non-required properties; "
                "required ones (from the schema's `required` list) "
                "appear without `?`."
            )


class TestLiveDocsDontClaimRetiredMcpToolsAsLive:
    """Tick 136 — extends tick 129's TestLiveDocsReferenceOnlyRegisteredMcpTools
    to catch the NARRATIVE-form drift class that bit tick 135.

    Tick 129's guard catches the invocation form
    `mcp__trinity-local__<name>(...)` — fails if `<name>` isn't a
    registered tool. But narrative mentions like ``MCP `ask` and
    `search_prompts` both trigger incremental ingest`` slipped
    past — `search_prompts` is named as a peer of `ask` (live) but
    is itself retired (pre-launch 2026-05-17).

    This guard catches narrative-form claims that a retired MCP
    tool is currently live, while exempting legitimate retirement-
    narration context. The retired tool name only fires the guard
    when the line lacks retirement markers — i.e. the line claims
    the tool ships TODAY.

    Same shape as the BANNED-synonyms scan at the retired-MCP-tool
    layer. Different from tick 129's guard because that one matches
    only invocation form; this one matches backticked name in any
    prose context."""

    # Lines containing any of these substrings get exempted — the
    # mention is in retirement-narration context, not a live claim.
    RETIREMENT_MARKERS = [
        "retired",
        "deprecated",
        "formerly",
        "used to",
        "what .* used to do",
        "subsumes",
        "subsumed",
        "dropped",
        "→",
        "renamed",
        "pre-rename",
        "post-rename",
        "earlier draft",
        "legacy",
        "rename-narration",
        "collapsed",
        "absorbed",
        "rolled into",
    ]

    DOCS_TO_CHECK = [
        "claude.md",
        "README.md",
        "src/trinity_local/data/skills/trinity/SKILL.md",
        "skills/trinity/SKILL.md",
        "docs/spec-v1.md",
        "docs/spec-v1.5.md",
        "docs/spec-v1.6.md",
        "docs/product-spec.md",
    ]

    def test_no_retired_mcp_tools_claimed_as_live(self):
        import re

        from trinity_local.retired_names import RETIRED

        retired_mcp = sorted(
            name for name, rec in RETIRED.items() if rec.kind == "mcp_tool"
        )
        assert retired_mcp, "Expected at least one retired MCP tool in registry"

        marker_pattern = re.compile(
            "|".join(self.RETIREMENT_MARKERS), re.IGNORECASE
        )

        # Look at a ±2-line window around each candidate mention.
        # Retirement narration often spans paragraph lines (e.g. a
        # parenthetical aside breaks across lines, or the marker is
        # in the sentence's predicate while the mention is in the
        # subject on the previous line). A pure line-by-line check
        # misclassifies these as bare claims.
        WINDOW = 2

        violations: list[str] = []
        for rel in self.DOCS_TO_CHECK:
            path = REPO / rel
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError:
                continue
            for lineno, line in enumerate(lines, 1):
                # Check if this line mentions a retired MCP tool.
                hits = [name for name in retired_mcp if f"`{name}`" in line]
                if not hits:
                    continue
                # Expand window to catch multi-line retirement narration.
                window_start = max(0, lineno - 1 - WINDOW)
                window_end = min(len(lines), lineno + WINDOW)
                window_text = "\n".join(lines[window_start:window_end])
                if marker_pattern.search(window_text):
                    continue  # retirement narration in ±2-line window
                for name in hits:
                    violations.append(
                        f"  {rel}:{lineno}  retired MCP tool `{name}` "
                        f"mentioned without retirement marker in ±{WINDOW}-line "
                        f"window — reads as a live-tool claim:\n      {line.strip()[:120]}"
                    )

        if violations:
            raise AssertionError(
                "Live-class docs reference retired MCP tools as if they're "
                "still live:\n" + "\n".join(violations) + "\n\n"
                "If the mention is intentional (retirement narration, "
                "rename history, etc.), add one of these markers to the "
                f"line: {sorted(self.RETIREMENT_MARKERS)}. "
                "Otherwise either remove the reference or flip it to the "
                "canonical live-tool name."
            )


class TestLauncherPatternsListsAllDispatchActions:
    """Tick 128 — docs/launcher-patterns.md L156-164 enumerates the
    set of dispatch actions Trinity's capture-host accepts. Earlier
    today that list missed `run_command` even though it's in
    DISPATCH_ACTIONS and command_for_dispatch handles it as the
    first branch (load-bearing for shell-payload dispatch).

    The drift class is the council_76e5aef79bb9f241 verdict's #3
    "docs are derived views over machine-readable facts" applied
    locally: the action set is canonical in dispatch_registry.py
    DISPATCH_ACTIONS; the doc's bullet list is a derived view. This
    guard pins the derived view to the source by asserting every
    name in DISPATCH_ACTIONS shows up somewhere in
    launcher-patterns.md's Action-taxonomy section.

    Catches both:
      (a) a new dispatch action added to code but not documented
      (b) an action retired from code but not removed from the doc
    """

    def test_doc_enumerates_all_dispatch_actions(self):
        from trinity_local.dispatch_registry import DISPATCH_ACTIONS

        path = REPO / "docs/launcher-patterns.md"
        text = path.read_text(encoding="utf-8")

        missing = sorted(
            name for name in DISPATCH_ACTIONS if f"`{name}`" not in text
        )
        if missing:
            raise AssertionError(
                f"docs/launcher-patterns.md doesn't mention these dispatch "
                f"actions: {missing}. They're registered in "
                f"DISPATCH_ACTIONS (src/trinity_local/dispatch_registry.py) "
                f"and accepted by capture_host's dispatch chain — the doc's "
                f"Action-taxonomy bullet list needs to include each one so "
                f"future readers don't miss a registered action."
            )


class TestThreeTierEnumeratesAllChromeActions:
    """Sibling of TestLauncherPatternsListsAllDispatchActions (one tier
    above). docs/three-tier-architecture.md's Tier-3 description quotes
    the Chrome-extension Native-Messaging allowlist by name. That set
    lives in capture_host.ACTION_ALLOWLIST (dashed names like
    `launch-council` / `render-me-card` — distinct from the underscored
    DISPATCH_ACTIONS set used by launchpad URL emitters).

    Drift caught 2026-05-21 iter #28: the doc enumerated 6 named
    actions + "settings toggles" but the live allowlist has 12
    entries. `council-iterate` (Phase 4b residual-drift fix),
    `dream` (Memory Health "Refresh memory" button), and
    `open-launchpad` (extension popup's canonical Trinity-launchpad
    entry point) shipped after the doc was written but never got
    enumerated. claude.md's status block similarly said "10 narrow
    action-allowlist entries" while live count was 12.

    Guard shape: for every name in ACTION_ALLOWLIST, assert it appears
    as a backticked code reference somewhere in three-tier-architecture.md.
    Mirrors the launcher-patterns guard one tier up — different set,
    different doc, same drift shape. Principle #20 + the council
    verdict cited there (docs are derived views over machine-readable
    facts; pin the view).
    """

    def test_doc_enumerates_all_chrome_actions(self):
        from trinity_local.capture_host import ACTION_ALLOWLIST

        text = (REPO / "docs/three-tier-architecture.md").read_text(
            encoding="utf-8"
        )
        missing = sorted(
            name for name in ACTION_ALLOWLIST if f"`{name}`" not in text
        )
        if missing:
            raise AssertionError(
                f"docs/three-tier-architecture.md doesn't mention these "
                f"Chrome-extension allowlist actions: {missing}. They're "
                f"registered in capture_host.ACTION_ALLOWLIST and accepted "
                f"by Native Messaging — the Tier-3 description must list "
                f"each one so a reader knows the full attack surface. The "
                f"count claim is pinned by the canonical "
                f"`chrome_action_allowlist_count` placeholder; this guard "
                f"pins the enumeration itself."
            )


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

    # CLI subcommands KNOWN to be retired. The retired_names.py registry
    # (Gap B, task #124) is the authoritative declaration — add a
    # RetirementRecord there in the same commit that drops a CLI from
    # CORE_COMMAND_MODULES, and the entry must also appear here so the
    # guard polices the runtime-visible quoted-string surface.
    #
    # Test test_retired_cli_set_is_subset_of_registry below asserts the
    # registry covers every name in this set; iter #27 (2026-05-21)
    # backfilled 22 missing records to close the historical drift.
    # `search-prompts` is intentionally present here but NOT in the
    # registry: the dashed form was never a CLI subcommand (the MCP
    # tool was `search_prompts` with underscore, already registered);
    # the dashed entry stays as defensive coverage so a future contributor
    # can't reintroduce a CLI by mistake.
    RETIRED_CLI = frozenset({
        "doctor",
        "watch-once", "watch-loop",
        "distill", "core-show",
        "stats", "metric",
        "depth-show",
        "task-create", "task-show", "task-sync",
        "bundle-create", "launch-create",
        "council-last",
        "council-rate",  # retired 2026-05-22 with full rating-surface sunset (commit 4c34757)
        "unrated",       # retired 2026-05-22, was Pillar 4 rating-funnel widening (commit 4c34757)
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
    # The legitimate use is in install.py (detects + removes stale
    # `watch-once` hooks on re-install). commands/trust.py was a
    # second exempted file but iter #115 sunset it — it was an
    # orphan module with a false test-coverage docstring, same
    # pattern as commands.tasks + commands.depth (tick 85).
    KNOWN_REFS_PATHS = frozenset({
        "src/trinity_local/commands/install.py",   # stale-hook cleanup detection
    })

    def test_retired_cli_set_is_subset_of_registry(self):
        """The retired_names.py registry is the canonical source of
        truth for retirements (per its module docstring: 'the registry
        IS the source of truth'). This guard's RETIRED_CLI set must
        match it — every CLI subcommand we police here should have a
        RetirementRecord with kind='cli' + commit + replacement + reason.

        Drift caught 2026-05-21 iter #27: 22 of the 30 CLIs in
        RETIRED_CLI had no record in the registry (`stats`, `metric`,
        `council-last`, the auto-chain/auto-open/polish-auto family,
        the cache-stats/cache-clear pair, the task/bundle/launch
        ghost-registers, core-show/depth-show, the trust-CLI deferred
        triple). The hand-maintained set grew as each simplification
        landed, but the registry — which is supposed to be the single
        source — only had 9 of them. Without this guard, every future
        retirement risks the same shape: the user-facing guard catches
        the buttons-and-hints in src/, but the structured declaration
        (used by docs renderers, runtime migration hints, MIGRATION.md
        consistency checks) stays empty.

        Exception: `search-prompts` (dashed). Was never a CLI — the
        MCP tool retirement is `search_prompts` (underscore, already
        in the registry as kind=mcp_tool). The dashed entry stays in
        RETIRED_CLI as defensive coverage so a future contributor can't
        introduce a `trinity-local search-prompts` CLI by mistake.
        """
        from trinity_local.retired_names import RETIRED
        registry_clis = {
            name for name, rec in RETIRED.items() if rec.kind == "cli"
        }
        defensive_only = {"search-prompts"}  # documented above
        expected_in_registry = self.RETIRED_CLI - defensive_only
        missing = expected_in_registry - registry_clis
        if missing:
            raise AssertionError(
                "RETIRED_CLI lists names with no RetirementRecord in "
                "src/trinity_local/retired_names.py. The registry is "
                "the canonical declaration; the guard's set should be "
                "a subset of it (plus the defensive exception for "
                "`search-prompts`). Missing:\n  - "
                + "\n  - ".join(sorted(missing))
                + "\n\nAdd a RetirementRecord(name=<n>, retired_at=<iso>, "
                "commit=<sha>, replacement=<what-instead>, reason=<one-line>, "
                "kind='cli') for each missing entry in the same commit."
            )

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

    def test_no_retired_cli_in_src_docstrings(self):
        """Sibling of test_no_retired_cli_in_test_docstrings (iter #25),
        pointed at src/ instead of tests/. Catches the SAME drift class
        one level up: a source-module docstring naming a retired CLI
        in present tense without a retirement marker anywhere in the
        same docstring block.

        Drift caught 2026-05-21 iter #30: doctor.py:281 inside
        `_check_skill_freshness()` said "This keeps `doctor` fast
        (<200ms)" — but `doctor` the CLI was absorbed into `status`
        (commit ef2f328, 2026-05-18). The underlying check function
        still ships (it's why the docstring is even there); the CLI
        name in the prose just drifted.

        Different surface from the existing
        TestNoRetiredCliInSrcQuotedStrings scanner: that one matches
        QUOTED Python strings + HTML `<code>` tags (the runtime-visible
        strings users see); this one matches BACKTICKED names inside
        triple-quoted docstrings (the developer-facing strings authors
        read). Both shapes can drift; they need both guards.

        Whole-docstring marker window (not ±200 chars): a single
        retirement note at the top of a long module docstring should
        absolve every CLI mention in the same block, since the
        retirement context is clearly established once. Mirrors how
        the iter #17 marker-proximity audit treated MD files (±3
        lines was too narrow for prose; markers at the section header
        legitimately cover the whole section).
        """
        import re

        from trinity_local.retired_names import RETIRED

        # Source the retired CLI set from the registry (per iter #27's
        # test_retired_cli_set_is_subset_of_registry — the registry
        # is canonical).
        retired_cli = {
            name for name, rec in RETIRED.items() if rec.kind == "cli"
        }
        if not retired_cli:
            raise AssertionError(
                "retired_names.py has no kind='cli' records — registry "
                "is incomplete; cannot scan."
            )

        # Match backticked `<cli>` OR `trinity-local <cli>` form.
        retired_pattern = re.compile(
            r"`(?:trinity-local\s+)?("
            + "|".join(re.escape(c) for c in retired_cli)
            + r")`"
        )
        docstring_pattern = re.compile(
            r'("""(?:.|\n)*?"""|\'\'\'(?:.|\n)*?\'\'\')',
            re.MULTILINE,
        )
        markers = (
            "retired", "former", "absorbed", "collapsed", "replaced",
            "sunset", "was ", "deprecat", "no longer", "removed",
            "deleted", "renamed", "→", "legacy", "subsume",
            "pre-rename", "post-rename",
        )

        src_dir = REPO / "src" / "trinity_local"
        hits: list[tuple[str, int, str, str]] = []
        for path in src_dir.rglob("*.py"):
            rel = path.relative_to(REPO).as_posix()
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            for ds_match in docstring_pattern.finditer(text):
                docstring = ds_match.group(1)
                docstring_lower = docstring.lower()
                # Whole-docstring marker scope: if ANY marker appears
                # anywhere in this docstring, the retirement context
                # is established.
                if any(mk in docstring_lower for mk in markers):
                    continue
                for m in retired_pattern.finditer(docstring):
                    abs_offset = ds_match.start() + m.start()
                    line_no = text[:abs_offset].count("\n") + 1
                    cli = m.group(1)
                    snippet = docstring[max(0, m.start() - 40):m.end() + 40].replace("\n", " ").strip()[:140]
                    hits.append((rel, line_no, cli, snippet))
        if hits:
            msg = [
                "Retired CLI referenced in src/ docstring without "
                "any retirement marker in the same docstring block:"
            ]
            for rel, line, cli, snippet in hits:
                msg.append(f"  {rel}:{line} mentions retired `{cli}`")
                msg.append(f"    → {snippet}")
            msg.append("")
            msg.append(
                "A source-module docstring naming a retired CLI in "
                "present tense (e.g. \"keeps `doctor` fast\") is a "
                "developer-facing lie even though the underlying "
                "function survived. Fix: rename the CLI to the live "
                "one (e.g. `status`) and add a parenthetical noting "
                "the retirement so a future reader doesn't reintroduce "
                "the old name. The whole-docstring marker scope means "
                "a single \"…was retired YYYY-MM-DD…\" note at the top "
                "of the module docstring covers every CLI mention in "
                "the same block."
            )
            raise AssertionError("\n".join(msg))

    def test_no_retired_mcp_tool_in_py_docstrings(self):
        """Iter #32 catch — sibling of iter #30's
        test_no_retired_cli_in_src_docstrings, pointed at retired MCP
        TOOLS instead of CLIs. Same drift class one dimension over.

        Caught 2026-05-21 iter #32: incremental_ingest.py:13 module
        docstring claimed ingest fires from "MCP `ask` /
        `search_prompts`" — but `search_prompts` was retired
        2026-05-17 (registry confirms). The fire-on-MCP-call behavior
        is real; the named tool just drifted. A developer reading
        incremental_ingest.py would see `search_prompts` named as a
        live MCP trigger and try to call it — would get tool-not-found
        at the MCP layer.

        Different surface from existing
        TestLiveDocsDontClaimRetiredMcpToolsAsLive guard: that one
        scans long-form docs (.md). This one scans source-code
        docstrings (.py). Both shapes can drift; both surfaces need
        guards. Sources the retired MCP set from the registry so
        future MCP-tool retirements automatically extend coverage.

        Whole-docstring marker scope (same as the iter-30 CLI guard):
        a single retirement note anywhere in the same docstring
        block exempts every retired-tool mention in that block —
        e.g. mcp_server.py legitimately names `record_outcome` in
        the long comment explaining why it was retired.
        """
        import re

        from trinity_local.retired_names import RETIRED

        retired_mcp = {
            name for name, rec in RETIRED.items() if rec.kind == "mcp_tool"
        }
        if not retired_mcp:
            raise AssertionError(
                "retired_names.py has no kind='mcp_tool' records — "
                "registry is incomplete; cannot scan."
            )

        mcp_pattern = re.compile(
            r"`(" + "|".join(re.escape(t) for t in retired_mcp) + r")`"
        )
        docstring_pattern = re.compile(
            r'("""(?:.|\n)*?"""|\'\'\'(?:.|\n)*?\'\'\')',
            re.MULTILINE,
        )
        markers = (
            "retired", "former", "absorbed", "collapsed", "replaced",
            "sunset", "was ", "deprecat", "no longer", "removed",
            "deleted", "renamed", "→", "legacy", "subsume",
            "pre-rename", "post-rename",
        )

        hits: list[tuple[str, int, str, str]] = []
        scan_roots = [REPO / "src" / "trinity_local", REPO / "tests"]
        for root in scan_roots:
            for path in root.rglob("*.py"):
                rel = path.relative_to(REPO).as_posix()
                try:
                    text = path.read_text(encoding="utf-8")
                except OSError:
                    continue
                for ds_match in docstring_pattern.finditer(text):
                    block = ds_match.group(1)
                    block_lower = block.lower()
                    if any(mk in block_lower for mk in markers):
                        continue
                    for m in mcp_pattern.finditer(block):
                        abs_offset = ds_match.start() + m.start()
                        line_no = text[:abs_offset].count("\n") + 1
                        tool = m.group(1)
                        snippet = block[max(0, m.start() - 40):m.end() + 40].replace("\n", " ").strip()[:140]
                        hits.append((rel, line_no, tool, snippet))
        if hits:
            msg = [
                "Retired MCP tool referenced in a .py docstring without "
                "any retirement marker in the same docstring block:"
            ]
            for rel, line, tool, snippet in hits:
                msg.append(f"  {rel}:{line} mentions retired MCP `{tool}`")
                msg.append(f"    → {snippet}")
            msg.append("")
            msg.append(
                "A docstring naming a retired MCP tool in present "
                "tense (e.g. \"fires from MCP `search_prompts`\") "
                "directs developers and agents to a tool that doesn't "
                "exist. Fix: rename to the live successor (per "
                "retired_names.py) and add a parenthetical noting the "
                "retirement so a future reader doesn't reintroduce "
                "the old name. Whole-docstring marker scope: a single "
                "retirement note at the top of the block covers every "
                "mention in the same block."
            )
            raise AssertionError("\n".join(msg))

    def test_no_retired_cli_in_test_docstrings(self):
        """Sibling guard born of iter #25 of the post-launch sweep.
        The `src/` scanner above catches retired CLIs in user-facing
        code paths. But test files are public-facing too — their
        docstrings describe what each test pins, and a docstring
        claiming `trinity-local doctor output` after `doctor` was
        absorbed into `status` (commit ef2f328) is a present-tense
        lie. Three sites caught: test_doctor.py:335 TestNextStepHint
        ("the handoff-demo nudge in `trinity-local doctor` output"),
        test_doctor_browser_capture.py:175 (same shape), test_ask.py:707
        ("`trinity-local metric rate-limit-saves` reads") — all written
        when those CLIs were live, none updated when they retired
        because file headers correctly noted retirement and the human
        eye stopped reading.

        Guard shape: scan tests/*.py for `trinity-local <retired-cli>`
        inside a docstring (triple-quoted block). Fail if the paragraph
        containing the mention has no retirement marker (retired,
        former, absorbed, collapsed, replaced, sunset, was). Same
        marker-proximity heuristic as the src/ scanner; same RETIRED_CLI
        set. Principle #20 (drifted-oldest-surface) + #21 (every claim
        needs a guard at the surface that ships it) applied to tests.
        """
        import re
        repo = Path(__file__).resolve().parent.parent
        tests_dir = repo / "tests"
        retired_cli = (
            TestNoRetiredCliInSrcQuotedStrings.RETIRED_CLI
        )
        # Match `trinity-local <retired>` in any context (no quote/HTML
        # prefix required — docstrings rarely quote command names with
        # backticks alone is fine but plain `trinity-local doctor` is
        # also common in prose).
        retired_pattern = re.compile(
            r"trinity-local\s+("
            + "|".join(re.escape(c) for c in retired_cli)
            + r")\b"
        )
        # Triple-quoted docstring matcher — captures everything
        # between `"""` or `'''` pairs.
        docstring_pattern = re.compile(
            r'("""(?:.|\n)*?"""|\'\'\'(?:.|\n)*?\'\'\')',
            re.MULTILINE,
        )
        markers = (
            "retired", "former", "absorbed", "collapsed", "replaced",
            "sunset", "was ", "deprecat", "no longer", "removed",
            "deleted", "renamed", "→",
        )
        hits: list[tuple[str, int, str, str]] = []
        for path in tests_dir.rglob("test_*.py"):
            rel = path.relative_to(repo).as_posix()
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                continue
            for ds_match in docstring_pattern.finditer(text):
                docstring = ds_match.group(1)
                for m in retired_pattern.finditer(docstring):
                    # Find the paragraph (≈±3 line window around the
                    # match) containing the retired CLI reference.
                    ds_start_in_file = ds_match.start()
                    abs_offset = ds_start_in_file + m.start()
                    line_no = text[:abs_offset].count("\n") + 1
                    # Pull a window of ±200 chars around the match
                    # from the docstring (paragraph proxy).
                    start = max(0, m.start() - 200)
                    end = min(len(docstring), m.end() + 200)
                    window = docstring[start:end].lower()
                    if any(mk in window for mk in markers):
                        continue
                    cli = m.group(1)
                    snippet = docstring[max(0, m.start()-40):m.end()+40].replace("\n", " ").strip()[:140]
                    hits.append((rel, line_no, cli, snippet))
        if hits:
            msg = ["Retired CLI referenced in tests/ docstrings without "
                   "a nearby retirement marker:"]
            for rel, line_no, cli, snippet in hits:
                msg.append(f"  {rel}:{line_no} mentions retired `trinity-local {cli}`")
                msg.append(f"    → {snippet}")
            msg.append("")
            msg.append(
                "A test docstring describing the behavior under test "
                "is a public claim about what the test pins. When the "
                "CLI named in the docstring retires, the docstring "
                "becomes a present-tense lie even if the underlying "
                "library function survived (e.g. `doctor` → `status`). "
                "Fix: name the live surface (`status` if doctor was "
                "absorbed; the library function if the CLI was the "
                "sole surface) and add a parenthetical noting the "
                "retirement so future readers don't re-introduce the "
                "old name."
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
        # Iter #100 extended scope to also include tests/ — same drift
        # class lived there (3 stray-`f`-prefix sites caught alongside
        # the iter-#100 undefined-name `RejectionSignal` bug).
        scan_dirs = [
            repo / "src" / "trinity_local" / "commands",
            repo / "tests",
        ]

        # Shell out to pyflakes — it correctly distinguishes top-level
        # f-strings from inner format_spec JoinedStr nodes (which a naive
        # ast.walk would false-positive on, e.g. `f"{x:>8,}"` contains
        # an inner JoinedStr `f">8,"` that isn't a real source f-string).
        result = subprocess.run(
            [sys.executable, "-m", "pyflakes", *[str(d) for d in scan_dirs]],
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
            msg = ["f-strings without placeholders in commands/ or tests/ (stray `f` prefix):"]
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
        import sys
        result = subprocess.run(
            # sys.executable, not ".venv/bin/python" — works on CI
            # runners (system python, no checked-in venv) and on local
            # dev where the test was run from inside the venv anyway.
            [sys.executable, "scripts/render_docs.py", "--check"],
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

    def test_design_md_palette_matches_design_system_colors(self):
        """Iter #51 catch — DESIGN.md's "Color palette" section lists
        16 colors with `#hex` values. design_system.COLORS is the
        canonical dict the Python rendering layer reads. Drift caught:
        design_system.COLORS was missing `accent_warm` (#b57438) —
        even though DESIGN.md documents it AND 5 inline call sites in
        memory_viewer.py + launchpad_template.py use the hex literal.
        A new dev reading design_system.COLORS to learn the palette
        would see only 15 of the 16 colors DESIGN.md says ship; a new
        dev reading DESIGN.md would think accent_warm IS in the
        canonical dict (it should be).

        Guard shape: parse DESIGN.md's palette list (lines matching
        the markdown ``- <Name>: `#XXXXXX`...`` shape) into a
        {hex → name} map. For each hex value in DESIGN.md, assert it
        appears as a value in design_system.COLORS. For each hex
        value in COLORS, assert it appears in DESIGN.md. Bidirectional
        pinning so adding a color to either surface forces the other
        to follow.

        Distinct from the existing test_no_forbidden_hex_in_launchpad
        guard which polices DESIGN.md-forbidden colors (indigo /
        violet / tailwind-blue / pink). This guard pins the positive
        palette match.
        """
        import re

        design_md = (REPO / "DESIGN.md").read_text(encoding="utf-8")
        # Extract palette hex values from DESIGN.md.
        # Lines like "- Background base: `#f5efe3`" or
        # "- Info: `#315c85` (blue used for...)".
        design_hex_re = re.compile(
            r"^- ([^:]+):\s+`(#[0-9a-fA-F]{6})`",
            re.MULTILINE,
        )
        design_palette = {
            hex_value.lower(): name.strip()
            for name, hex_value in design_hex_re.findall(design_md)
        }
        if not design_palette:
            raise AssertionError(
                "Couldn't extract any palette colors from DESIGN.md — "
                "either the section was reformatted or the regex needs "
                "updating."
            )

        # COLORS is a module-level dict; reading it doesn't need a
        # fresh import (and `del sys.modules[trinity_local.*]` leaves
        # other modules holding stale references — that pattern was
        # the root cause of 15 cross-suite failures, per principle #19).
        from trinity_local.design_system import COLORS

        code_palette = {hex_value.lower(): name for name, hex_value in COLORS.items()}

        missing_from_code = sorted(
            f"{name} ({hex_value})"
            for hex_value, name in design_palette.items()
            if hex_value not in code_palette
        )
        missing_from_doc = sorted(
            f"{name} ({hex_value})"
            for hex_value, name in code_palette.items()
            if hex_value not in design_palette
        )

        errors: list[str] = []
        if missing_from_code:
            errors.append(
                "DESIGN.md documents hex values not present in "
                "design_system.COLORS:\n  - "
                + "\n  - ".join(missing_from_code)
            )
        if missing_from_doc:
            errors.append(
                "design_system.COLORS has entries not documented in "
                "DESIGN.md's palette section:\n  - "
                + "\n  - ".join(missing_from_doc)
            )
        if errors:
            raise AssertionError(
                "DESIGN.md palette section drifted from "
                "design_system.COLORS.\n\n"
                + "\n\n".join(errors)
                + "\n\nThe two surfaces are the docs + code views of "
                "the same fact. Add the missing entries to either "
                "surface (same hex value, matching name) so a "
                "contributor reading either surface gets the full set."
            )

    def test_launch_arc_completed_tasks_have_shipped_marker(self):
        """Iter #48 catch — claude.md "Launch arc" section enumerates
        5 workstreams as future work. Two of them (#117 "Standardize
        ~/.trinity/" + #118 "Subsidy-window narrative") were marked
        completed in the task list but the prose still read like
        future intent ("Push a JSON Schema for `council_outcomes/*.json`
        into the open while we have first-mover authority"). A reader
        scanning the section to find what's done vs pending couldn't
        tell. Same drift class as the iter-#26 plan-vs-reality shape:
        the work shipped but the prose stayed future-tense.

        Guard shape: for each workstream item in the Launch arc
        numbered list (matches `N. **Title** (task #XXX...)`), check
        whether the heading carries a ship marker like "✓ shipped"
        or "shipped pre-launch". If the corresponding task is
        completed (queried via TaskList in CI is infeasible; we hard-
        code the known shipped set as the inline KNOWN_SHIPPED list
        + the guard's CHANGELOG-citation heuristic). Lighter shape:
        statically check that any task ID cited in the Launch arc
        section that ALSO appears in claude.md's broader "Forward
        arc" status block ("shipped (task #N)") carries the ship
        marker.

        Conservative form: maintain a small KNOWN_SHIPPED set of
        launch-arc task IDs that are completed; for each, assert the
        prose mentions either "✓ shipped" or "shipped" in the same
        bullet's heading. When new tasks complete, this list grows
        in the same commit that flips the prose to past-tense — a
        single-line edit.
        """
        import re

        claude_md = (REPO / "claude.md").read_text(encoding="utf-8")

        # Known-shipped launch-arc workstreams. Update inline when a
        # workstream completes — the prose update + this list update
        # are co-edited.
        KNOWN_SHIPPED = {
            "#117": "Standardize ~/.trinity/ (schemas published)",
            "#118": "Subsidy-window narrative (threaded through launch copy)",
            "#119": "Handoff mechanism (CLI + MCP tool shipped)",
            "#122": "Corpus-based eval harness (trinity-local eval CLI + scoring loop)",
        }

        # Locate the Launch arc numbered list. Header is
        # "## Launch arc (v1.0 → v1.1) — distribution beats elegance".
        m = re.search(
            r"^##\s+Launch arc[^\n]*\n",
            claude_md,
            re.MULTILINE,
        )
        if not m:
            raise AssertionError(
                "Couldn't find '## Launch arc' header in claude.md"
            )
        after = claude_md[m.end():]
        next_header = re.search(r"^##\s+", after, re.MULTILINE)
        section = after[: next_header.start()] if next_header else after

        ship_markers = ("✓ shipped", "shipped pre-launch", "shipped 2026-")
        missing: list[str] = []
        for task_id, expected_topic in KNOWN_SHIPPED.items():
            # Find the workstream's heading line(s) and a short window
            # of prose. Workstream items match `N. **<title>** (task
            # <task_id>...`.
            item_re = re.compile(
                r"^\d+\.\s+\*\*[^*]+\*\*\s+\(task\s+"
                + re.escape(task_id)
                + r"[^)]*\)",
                re.MULTILINE,
            )
            item_match = item_re.search(section)
            if not item_match:
                # Task ID not cited in launch arc — exempt (it might
                # be referenced elsewhere in claude.md but not be a
                # launch-arc workstream).
                continue
            # Check the matched heading line for a ship marker.
            heading_line = section[
                item_match.start() : section.find("\n", item_match.start())
            ]
            if not any(marker in heading_line for marker in ship_markers):
                missing.append(
                    f"  Launch arc workstream task {task_id} "
                    f"({expected_topic}) — heading lacks a ship marker.\n"
                    f"    heading: {heading_line.strip()!r}"
                )
        if missing:
            raise AssertionError(
                "Launch arc workstreams known to be completed don't "
                "carry a ship marker in claude.md:\n"
                + "\n".join(missing)
                + "\n\nAdd a `(task #N — ✓ shipped)` suffix to the "
                "heading and update the body to reference the "
                "completed work (e.g. "
                "'Now threaded through launch copy...' instead of "
                "'Tell users explicitly: ...'). When a new "
                "workstream ships, extend the KNOWN_SHIPPED dict "
                "in this test as part of the same commit."
            )

    def test_gemini_capture_deferral_documented_consistently(self):
        """Iter #47 catch — claude.md L10 says "gemini.google.com
        adapter deferred to v1.7 per protocol-fragility risk," and
        the absence of a `parse_captured_gemini_conversation` parser
        in ingest.py confirms this is real. But README + INSTALL-
        extension.md were overselling — claiming gemini.google.com
        gets ingested end-to-end alongside claude.ai + chatgpt.com.

        Reality on disk:
          - browser-extension/page-hook.js DOES intercept
            gemini.google.com traffic (stream pattern wired up)
          - Captures DO accumulate at ~/.trinity/conversations/
          - But ingest.py has NO `parse_captured_gemini_conversation`
            function — captures sit unread until v1.7

        The honest framing (now applied to README L24+L42 and INSTALL-
        extension.md L10+L16): claude.ai + chatgpt.com are ingested
        end-to-end; gemini.google.com captures hit disk but parsing
        is deferred.

        Guard shape: AST-scan ingest.py for parse_captured_* function
        defs. If parse_captured_gemini_conversation appears, the
        deferral narration in user-facing docs becomes stale (and
        should be updated to "ingested in real time"). If it
        doesn't, README + INSTALL-extension must include the
        deferral disclaimer.

        Catches:
          (a) the parser ships → docs still hedge → reader misses
              the news
          (b) docs drift back to overselling without the parser
              shipping
        """
        import ast

        ingest_src = (REPO / "src/trinity_local/ingest.py").read_text(
            encoding="utf-8"
        )
        tree = ast.parse(ingest_src)
        parser_names = {
            node.name for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
            and node.name.startswith("parse_captured_")
        }
        gemini_parser_present = "parse_captured_gemini_conversation" in parser_names

        readme = (REPO / "README.md").read_text(encoding="utf-8")
        install_ext = (REPO / "docs/INSTALL-extension.md").read_text(
            encoding="utf-8"
        )

        # The deferral disclaimer markers (any of these phrases counts
        # as "doc acknowledges the deferral"):
        deferral_markers = (
            "deferred to v1.7",
            "Python adapter that ingests them lands in v1.7",
            "captures hit disk too but Python-side ingestion is deferred",
        )

        def has_deferral_note(text: str) -> bool:
            return any(m in text for m in deferral_markers)

        readme_acknowledges = has_deferral_note(readme)
        install_ext_acknowledges = has_deferral_note(install_ext)

        if gemini_parser_present:
            # Parser shipped — docs should NOT hedge anymore.
            stale_docs = []
            if readme_acknowledges:
                stale_docs.append("README.md")
            if install_ext_acknowledges:
                stale_docs.append("docs/INSTALL-extension.md")
            if stale_docs:
                raise AssertionError(
                    f"parse_captured_gemini_conversation has shipped, but "
                    f"docs still contain the v1.7-deferral hedge: "
                    f"{stale_docs}. Update the prose to claim end-to-end "
                    f"ingestion of gemini.google.com captures."
                )
        else:
            # Parser absent — docs MUST hedge.
            missing_hedge = []
            if not readme_acknowledges:
                missing_hedge.append("README.md")
            if not install_ext_acknowledges:
                missing_hedge.append("docs/INSTALL-extension.md")
            if missing_hedge:
                raise AssertionError(
                    f"ingest.py has no parse_captured_gemini_conversation "
                    f"function (Gemini captures hit disk but aren't ingested), "
                    f"but these docs claim end-to-end Gemini ingestion "
                    f"without the v1.7-deferral hedge: {missing_hedge}\n\n"
                    f"Add the deferral note matching claude.md L10's "
                    f"existing accurate framing, or implement the parser "
                    f"and remove the hedge."
                )

    def test_install_mcp_harness_claim_matches_code(self):
        """Iter #42 catch — claude.md L439 + L584 claimed `install-mcp`
        wires "the three CLI harnesses" but install.py actually
        writes to FOUR config paths in user scope (added Cursor per
        the P16/P92 persona audit when a Cursor user discovered
        Trinity was MCP-compatible but had no install path):

          json_targets = (
              Path.home() / ".claude.json",          # Claude Code
              Path.home() / ".gemini" / "settings.json",  # Antigravity
              Path.home() / ".cursor" / "mcp.json",  # Cursor  ← was missing
          )
          codex_path = Path.home() / ".codex" / "config.toml"  # Codex

        Four harnesses. Two claude.md prose claims said three.

        Guard shape: AST-parse install.py for the tuple of
        Path.home() expressions inside the install-mcp handler,
        count them, plus the codex_path (separate because it's
        TOML not JSON), assert the total matches the "N CLI
        harnesses" prose claim in claude.md. Catches:
          (a) future harness additions that don't propagate to the doc
          (b) future harness removals that don't propagate either

        Sibling of iter #28's chrome_action_allowlist_count canonical
        helper — same "code is the source of truth, doc is a derived
        view" shape applied to the install-mcp surface count.
        """
        import ast
        import re

        install_src = (REPO / "src/trinity_local/commands/install.py").read_text(encoding="utf-8")
        tree = ast.parse(install_src)

        # Find the install-mcp handler. It contains:
        #   json_targets = ( ..., Path.home() / "X", ..., Path.home() / "Y" / "Z", ...)
        #   codex_path = Path.home() / ".codex" / "config.toml"
        # Count harness-config targets in user scope.
        json_target_count = 0
        has_codex = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign):
                target_name = (
                    node.targets[0].id
                    if node.targets and isinstance(node.targets[0], ast.Name)
                    else None
                )
                if target_name == "json_targets":
                    if isinstance(node.value, ast.Tuple):
                        json_target_count = len(node.value.elts)
                if target_name == "codex_path":
                    has_codex = True

        if json_target_count == 0:
            raise AssertionError(
                "Couldn't locate json_targets tuple in install.py — "
                "the guard's AST walk needs updating to track the "
                "new code shape."
            )

        total_harnesses = json_target_count + (1 if has_codex else 0)

        # Iter #46 extension: also scan MCP_REGISTRY_SUBMISSIONS.md.
        # That doc's "Why these registries" section is the marketing
        # copy contributors paste into registry submission forms;
        # under-counting the harness set there sells Trinity short
        # to registry reviewers. Same drift shape, two surfaces.
        targets = (
            ("claude.md", r"(\w+)\s+CLI\s+harnesses"),
            ("docs/MCP_REGISTRY_SUBMISSIONS.md", r"\((\w+)\s+harnesses"),
        )
        # Normalize spelled-out numbers to digits.
        spelled = {
            "one": 1, "two": 2, "three": 3, "four": 4,
            "five": 5, "six": 6, "seven": 7, "eight": 8,
        }
        errors: list[str] = []
        for path, pattern in targets:
            text = (REPO / path).read_text(encoding="utf-8")
            prose_matches = re.findall(pattern, text)
            claimed_counts = set()
            for m in prose_matches:
                ml = m.lower()
                if ml.isdigit():
                    claimed_counts.add(int(ml))
                elif ml in spelled:
                    claimed_counts.add(spelled[ml])
            if not claimed_counts:
                errors.append(
                    f"  {path}: couldn't find harness-count prose. "
                    f"Either the prose was renamed or this guard's "
                    f"regex needs updating."
                )
                continue
            if total_harnesses not in claimed_counts:
                errors.append(
                    f"  {path}: claims {sorted(claimed_counts)} harnesses, "
                    f"install.py reality is {total_harnesses}"
                )
        if errors:
            raise AssertionError(
                f"Install-mcp harness count drifted from install.py:\n"
                f"  install.py user scope: {json_target_count} JSON + "
                f"{1 if has_codex else 0} TOML configs = "
                f"{total_harnesses} total\n\n" + "\n".join(errors)
                + "\n\nUpdate the prose to match install.py's "
                "json_targets tuple + codex_path. List paths inline so "
                "a reader can verify the count without reading the code."
            )

    def test_doctor_install_hints_match_launchpad_canonical(self):
        """Iter #40 catch — extends iter #39's launchpad-internal
        consistency guard to also pin doctor.py's
        `_install_command_for()` against the same canonical.

        doctor.py provides the fix-hint when `trinity-local status`
        reports "claude CLI not on PATH". When that hint differs
        from what the launchpad teaches, a user sees two different
        install instructions for the same product across two
        surfaces of the same tool. Drift caught iter #40:

          doctor.py['claude'] = "Install Claude Code:
              https://docs.claude.com/en/docs/claude-code"
          launchpad canonical = "npm install -g @anthropic-ai/claude-code"

          doctor.py['codex'] = "npm install -g @openai/codex
              # or: brew install codex"
          launchpad canonical = "npm install -g @openai/codex
              && codex --login"

          (antigravity matched.)

        Guard shape: for each provider in launchpad
        _TIER_INSTALL_HELP, assert doctor._install_command_for()
        returns the SAME string. Together with the iter-#39 guard
        (which pins launchpad's two internal surfaces), this pins
        all THREE surfaces:
          - _TIER_INSTALL_HELP (tier-card)
          - _provider_install_help() (single-provider lookup)
          - doctor._install_command_for() (status fix-hint)

        Future refactor: extract the canonical to a single module-
        level dict in setup_guidance.py (or a new install_commands.py)
        and have all three surfaces import from there. The guard
        substitutes for that refactor by binding the three sites at
        the test layer.

        (Don't purge trinity_local from sys.modules to "refresh" —
        that pattern leaves other modules holding stale references
        and silently broke 15 cross-suite tests; see principle #19.)
        """
        from trinity_local.launchpad_data import _TIER_INSTALL_HELP
        from trinity_local.doctor import _install_command_for

        mismatches: list[str] = []
        for provider, (_name, install_canonical, _value_prop) in _TIER_INSTALL_HELP.items():
            doctor_str = _install_command_for(provider)
            if doctor_str != install_canonical:
                mismatches.append(
                    f"  {provider}:\n"
                    f"    launchpad canonical: {install_canonical!r}\n"
                    f"    doctor.py:           {doctor_str!r}"
                )
        if mismatches:
            raise AssertionError(
                "doctor.py's _install_command_for() strings have "
                "drifted from launchpad_data._TIER_INSTALL_HELP. "
                "These are two surfaces of the same install command "
                "fact — `status` shows doctor's hint when a provider "
                "is missing; the launchpad shows the dict version in "
                "tier cards. A user shouldn't see different commands "
                "for the same product across surfaces.\n\n"
                + "\n".join(mismatches)
                + "\n\nUpdate doctor.py to match the canonical form. "
                "If you intend to keep doctor.py's form different "
                "(e.g. terser doc-link instead of a real command), "
                "extract the divergence reason here and document "
                "the alternative-by-design exception."
            )

    def test_launchpad_install_commands_match_across_surfaces(self):
        """Iter #39 catch — launchpad_data.py had TWO sources of
        provider install commands that drifted from each other:

          _TIER_INSTALL_HELP (dict, L351 — tier-card renderer)
          _provider_install_help() (function, L295 — single-provider lookup)

        Three drifts found across the codebase:

          1. _TIER_INSTALL_HELP['claude'] used
             `curl -fsSL https://claude.ai/install.sh | bash`
             while every OTHER surface (setup_guidance.py,
             test_setup_guidance.py, _provider_install_help)
             used `npm install -g @anthropic-ai/claude-code`.

          2. _provider_install_help('antigravity') appended `&& agy`
             to the curl-bash install, while _TIER_INSTALL_HELP
             did not. The `&& agy` would auto-launch the CLI after
             install — surprising in a copy-paste one-liner.

          3. Claude form differs from launchpad_data → setup_guidance
             — fixed in this iter; now consistent.

        Guard shape: for each provider in _TIER_INSTALL_HELP, look
        up the same provider via _provider_install_help() and
        assert the install command strings match. Catches future
        edits that touch one but not the other.
        """
        from trinity_local.launchpad_data import (
            _TIER_INSTALL_HELP,
            _provider_install_help,
        )

        mismatches: list[str] = []
        for provider, (name_a, install_a, _value_prop) in _TIER_INSTALL_HELP.items():
            name_b, install_b = _provider_install_help(provider)
            if install_a != install_b:
                mismatches.append(
                    f"  {provider}: tier-card says {install_a!r}, "
                    f"provider-help says {install_b!r}"
                )
            if name_a != name_b:
                mismatches.append(
                    f"  {provider}: display-name disagrees "
                    f"({name_a!r} vs {name_b!r})"
                )
        if mismatches:
            raise AssertionError(
                "launchpad_data.py has two install-command surfaces "
                "that disagree:\n"
                + "\n".join(mismatches)
                + "\n\nBoth `_TIER_INSTALL_HELP` and "
                "`_provider_install_help` are public-facing copy "
                "describing the SAME install fact. Update both in "
                "the same commit. The canonical form per provider is "
                "the npm form for Claude (Anthropic's documented "
                "primary path) + npm for Codex + curl-bash for "
                "Antigravity (Google's documented primary path)."
            )

    def test_every_canonical_helper_is_consumed_by_a_doc(self):
        """Iter #36 catch — symmetry guard. Iter #34's
        test_state_layout_file_entries_have_writers caught
        doc → code orphans (diagram listed files no code wrote);
        this one catches CODE → DOC orphans at the renderer level.

        The scripts/render_docs.py CANONICAL dict declared 8 fields
        (chrome_action_allowlist_count / cli_command_count /
        doc_consistency_guards / mcp_tool_count / skipped_count /
        smoke_surface_count / test_count / version). 7 of them
        appeared as ``<!-- canonical:NAME -->`` placeholders somewhere
        in the repo; ``version`` was an orphan helper — the function
        computed the version from pyproject.toml but no doc actually
        used the placeholder. claude.md L56 had the version inlined
        as a raw string that would silently drift when v1.7.5 landed.

        Guard shape: walk the CANONICAL dict from render_docs.py,
        for each declared field assert at least one
        `<!-- canonical:NAME -->` placeholder exists somewhere
        in the docs (markdown + html). An orphan helper means
        either the placeholder fell out of every doc (drift), or
        the renderer never had a doc to feed (dead code).

        Pattern catalog: principle #21 (every claim needs a guard
        at the surface that ships it) inverted — every COMPUTED
        canonical value needs a SURFACE that consumes it, otherwise
        the computation is dead code. Pin both directions so the
        canonical pipeline can't drift on either end.
        """
        import subprocess
        import sys

        # Re-import the renderer fresh so we read the canonical
        # dict directly (avoids caching issues).
        for mod_name in list(sys.modules):
            if mod_name.startswith("render_docs"):
                del sys.modules[mod_name]
        sys.path.insert(0, str(REPO / "scripts"))
        import render_docs

        declared_fields = set(render_docs.CANONICAL.keys())
        if not declared_fields:
            raise AssertionError(
                "render_docs.CANONICAL is empty — guard would silently pass"
            )

        # Find every placeholder pattern in repo docs.
        result = subprocess.run(
            [
                "grep", "-rohE", r"canonical:[a-z_]+",
                "--include=*.md", "--include=*.html", "--include=*.py",
                str(REPO),
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        used = set(
            line.replace("canonical:", "") for line in result.stdout.splitlines()
            if line.strip()
        )

        orphans = sorted(declared_fields - used)
        if orphans:
            raise AssertionError(
                "render_docs.CANONICAL declares helpers with no consumer doc:\n"
                + "\n".join(f"  - {field}" for field in orphans)
                + "\n\nEach declared canonical helper should have at least one "
                "<!-- canonical:NAME --> placeholder in a doc that the "
                "renderer can substitute into. Orphan helpers are either:\n"
                "  (a) drift: a doc used to consume the helper but the "
                "placeholder fell out — restore it where the value belongs.\n"
                "  (b) dead code: the helper was added speculatively but "
                "never wired into a doc — drop it from CANONICAL.\n\n"
                "Iter #36 caught ``version`` as an orphan when claude.md "
                "L56's pyproject-version mention was inlined as a raw "
                "string rather than the placeholder; fix was to wrap the "
                "version in <!-- canonical:version -->X.Y.Z<!-- /canonical -->."
            )

    def test_command_module_count_claim_matches_main_py(self):
        """Iter #35 catch — claude.md's architecture section L597
        asserts "22 user-facing command modules (21 in
        CORE_COMMAND_MODULES + `install` in OPTIONAL_COMMAND_MODULES)".
        Iter #35 also caught L381 saying "21-command surface" — same
        metric, different number, because `install` was promoted to
        OPTIONAL_COMMAND_MODULES after the L381 prose was written
        and the count never propagated. L381 is now using the
        canonical cli_command_count placeholder (44 subcommands),
        eliminating that drift.

        Guard shape: import CORE_COMMAND_MODULES + OPTIONAL_COMMAND_MODULES
        from main.py, count both, assert claude.md's prose count
        matches. The "22 user-facing command modules" claim is the
        load-bearing public statement of v1.7.4's contract — drift
        here lies to a reader about the surface they get.

        Pattern catalog: principle #20 (drift in the oldest surface
        when two prose claims describe the same number one paragraph
        apart). L381 was the older claim; L597 got updated when
        `install` was promoted but L381 wasn't co-edited.
        """
        import re

        from trinity_local.main import (
            CORE_COMMAND_MODULES,
            OPTIONAL_COMMAND_MODULES,
        )
        core_count = len(CORE_COMMAND_MODULES)
        optional_count = len(OPTIONAL_COMMAND_MODULES)
        total = core_count + optional_count

        claude_md = (REPO / "claude.md").read_text(encoding="utf-8")
        # Match the architecture-section claim. The total count is now
        # wrapped in a canonical-placeholder (sweep iter #88):
        # "<!-- canonical:command_module_count -->22<!-- /canonical --> user-facing command modules (M in `CORE_COMMAND_MODULES` + ...)"
        # — accept either the placeholder form or a bare integer for the
        # total, then enforce that the parenthetical `M in CORE` count
        # still matches main.py's CORE_COMMAND_MODULES length.
        m = re.search(
            r"(?:<!-- canonical:command_module_count -->(\d+)<!-- /canonical -->|(\d+))"
            r"\s+user-facing command modules\s+\((\d+)\s+in\s+`CORE_COMMAND_MODULES`",
            claude_md,
        )
        if not m:
            raise AssertionError(
                "Couldn't locate the 'N user-facing command modules' "
                "claim in claude.md. Either the prose was renamed or "
                "this guard's regex needs updating."
            )
        claimed_total = int(m.group(1) or m.group(2))
        claimed_core = int(m.group(3))

        if claimed_total != total or claimed_core != core_count:
            raise AssertionError(
                f"claude.md's command-modules claim drifted from main.py.\n"
                f"  claimed: {claimed_total} total ({claimed_core} CORE + extras)\n"
                f"  actual : {total} total ({core_count} CORE + {optional_count} OPTIONAL)\n\n"
                f"Either main.py changed and the prose didn't follow, "
                f"or the prose count was wrong to begin with (the iter-#35 "
                f"drift caught the L381 '21-command surface' lying about "
                f"L597's '22 user-facing command modules' — same metric, "
                f"two paragraphs apart). Update the prose to match "
                f"CORE_COMMAND_MODULES + OPTIONAL_COMMAND_MODULES."
            )

    def test_state_layout_file_entries_have_writers(self):
        """Iter #34 catch — sibling of
        test_claude_md_state_layout_covers_every_state_paths_dir
        (iter #33). That guard catches code → doc gaps for
        directories. This one catches doc → code orphans for FILES
        named in the state-layout tree.

        Drift caught 2026-05-21 iter #34: claude.md's state-layout
        diagram listed `embeddings_matrix.npy   # numpy fast-path
        matrix (lazy)` but NO code ever wrote that file (git log -S
        confirmed no commit ever touched the name). It was a
        forward-looking artifact from the pre-task-#54 era when
        `search_prompt_nodes` used numpy matmul over a persisted
        embedding cache. Task #54 retired embedding-powered search
        in favor of substring + replay-value heuristics; the planned
        cache file never shipped, but the diagram entry survived.

        Guard shape: scrape every file leaf from the state-layout
        tree (lines like `│   └── prompt_nodes.jsonl   # ...`),
        then assert each filename appears as a string in src/.
        Looser than the directory guard because filenames are less
        likely to be constructed via helpers — most are inlined
        string literals (`"prompt_nodes.jsonl"`).

        Exceptions: a small ALLOWLIST for filenames that are
        legitimately created by external tools or older installs
        (none today; the allowlist is a forward-compat hook).

        Same pattern catalog as iter #33: docs are derived views;
        when a load-bearing list claim has no machine-readable
        binding to code, drift accumulates silently. Bind both
        directions (code → doc + doc → code) for the same diagram.
        """
        import re
        import subprocess

        claude_md = (REPO / "claude.md").read_text(encoding="utf-8")
        # Extract the state-layout section.
        m = re.search(
            r"### State layout(.*?)(?=\n###\s|\n##\s[^#])",
            claude_md,
            re.DOTALL,
        )
        if not m:
            raise AssertionError(
                "Couldn't find ### State layout section in claude.md"
            )
        layout = m.group(1)

        # Match file leaves inside the tree (lines with tree chars
        # followed by a name ending in .json / .jsonl / .md / .npy /
        # .toml / .yaml).
        file_pattern = re.compile(
            r"[├└]──\s+([\w.-]+\.(?:json|jsonl|md|npy|toml|yaml|js))\b"
        )
        diagram_files = set(file_pattern.findall(layout))

        # Forward-compat allowlist: filenames legitimately surfaced
        # in the diagram without an in-tree writer (e.g. user-curated
        # configs, files written by the Chrome extension only).
        ALLOWLIST = frozenset({
            # SCHEMA_VERSION is written by state_paths._ensure_schema_version
            # without a quoted-string literal that matches our scanner;
            # the diagram entry is still real (the file ships on every
            # mkdir of state_dir()).
        })

        src_dir = REPO / "src" / "trinity_local"
        missing: list[str] = []
        for fname in sorted(diagram_files):
            if fname in ALLOWLIST:
                continue
            # Grep src/ for the bare filename as a quoted string
            # literal or path fragment.
            result = subprocess.run(
                ["grep", "-rl", fname, str(src_dir)],
                capture_output=True,
                text=True,
                check=False,
            )
            if not result.stdout.strip():
                missing.append(f"  `{fname}` — appears in diagram, no writer in src/")
        if missing:
            raise AssertionError(
                "State-layout diagram lists files that no code in "
                "src/trinity_local/ references:\n"
                + "\n".join(missing)
                + "\n\nA file in the diagram with no writer is a "
                "doc orphan — a reader expecting it on disk will "
                "never find it. Fix: either remove the entry from "
                "the diagram (the file was forward-looking or got "
                "retired), or add the file to the allowlist with a "
                "one-line justification (the file is created by an "
                "external tool / Chrome extension / etc.)."
            )

    def test_claude_md_state_layout_covers_every_state_paths_dir(self, monkeypatch, tmp_path):
        """Iter #33 catch — claude.md's "State layout" tree diagram
        is supposed to enumerate every directory Trinity creates under
        `~/.trinity/`. Drift caught: state_paths.research_dir() was
        STILL live (used by knn_advisor via ranker/knn_ranker.py →
        ranker/fallback.py) but claude.md claimed it was retired AND
        omitted the directory from the layout diagram.

        Guard shape: for each `*_dir()` function in state_paths.py
        that takes zero arguments and returns under ~/.trinity/,
        extract the leaf directory name. Assert it appears in claude.md
        somewhere — either inside the State-layout tree (live entry)
        or inside the "Retired directories" block (legitimately
        retired but may still exist on older installs).

        Catches the same drift class as
        test_three_tier_schema_list_matches_directory one surface
        over: a load-bearing list in the doc that has to match the
        live code's view of what it produces. Without this guard,
        future state_paths additions risk being undocumented; future
        retirements risk being mis-flagged as live (or vice versa).
        """
        import inspect
        import pathlib

        # Scope TRINITY_HOME via monkeypatch (per principle #19). The
        # earlier shape mutated os.environ directly AND popped
        # `trinity_local.state_paths` from sys.modules — that combo
        # left other modules (drift.py, knn_advisor.py, ranker/...)
        # holding stale references to the original state_paths module
        # while a fresh copy lived in sys.modules. monkeypatched env
        # vars from later tests then failed to reach those stale refs,
        # silently breaking 15 unrelated tests across the suite.
        # trinity_home() reads os.environ at every call, so no
        # sys.modules.pop is needed — the env-var update propagates.
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        from trinity_local import state_paths

        zero_arg_dir_fns: list[tuple[str, pathlib.Path]] = []
        for name, fn in inspect.getmembers(state_paths, inspect.isfunction):
            if not name.endswith("_dir"):
                continue
            sig = inspect.signature(fn)
            if sig.parameters:
                continue
            if fn.__module__ != "trinity_local.state_paths":
                continue
            try:
                p = fn()
            except Exception:
                continue
            if not isinstance(p, pathlib.Path):
                continue
            # Skip the top-level state_dir itself.
            if p == tmp_path:
                continue
            # Only directories actually under TRINITY_HOME.
            try:
                rel = p.relative_to(tmp_path)
            except ValueError:
                continue
            zero_arg_dir_fns.append((name, rel))

        claude_md = (REPO / "claude.md").read_text(encoding="utf-8")
        missing: list[str] = []
        for fn_name, rel in zero_arg_dir_fns:
            # The leaf directory name is what shows up in the
            # diagram (e.g. "research", "scoreboard", "analytics").
            leaf = rel.parts[0]
            # Match either the tree-diagram form (`<leaf>/` or
            # `<leaf>` in a path-like context) or the retirement-list
            # form (backticked `<leaf>/`).
            patterns = (
                f"`{leaf}/`",
                f"`~/.trinity/{leaf}/`",
                f"├── {leaf}/",
                f"└── {leaf}/",
            )
            if not any(p in claude_md for p in patterns):
                missing.append(
                    f"  state_paths.{fn_name}() → ~/.trinity/{rel}/ "
                    f"(leaf `{leaf}/`)"
                )
        if missing:
            raise AssertionError(
                "claude.md doesn't mention these directories that "
                "state_paths.py creates:\n"
                + "\n".join(missing)
                + "\n\nEach state_paths zero-arg *_dir() function "
                "creates a directory under ~/.trinity/. The State-"
                "layout tree diagram in claude.md is the canonical "
                "view of what Trinity puts in the user's home — "
                "every directory should appear either in the tree "
                "(live) or in the 'Retired directories' note (legacy, "
                "may still exist on older installs). A directory that "
                "appears in neither place is undocumented surface."
            )

    def test_three_tier_schema_list_matches_directory(self):
        """The v1.0-floor section of `docs/three-tier-architecture.md`
        enumerates the schemas that ship in `skills/trinity/schemas/`.
        That enumeration MUST match the actual directory contents.

        Drift caught 2026-05-21 iter #26: the doc ratified 2026-05-16
        with three schemas (`council_outcome`, `eval_set`,
        `rejection_signal`). `trust.schema.json` shipped 2026-05-18
        alongside the trust substrate, the doc's enumeration was
        updated to match, then iter #121 deleted both
        `trust.schema.json` files 2026-05-22 after the trust library
        retirement (the schema was orphan reference for a library
        that no longer existed). Same drift shape as
        test_bundled_config_example_matches_top_level: a load-bearing
        fact lives in N≥2 surfaces (the schemas/ directory + the
        doc's enumeration), drift accumulates in the slower-moving
        surface. Pattern #20.

        Why this matters: three-tier-architecture.md is the architecture
        spec other tools read for the `~/.trinity/` cross-tool contract
        (task #117). A schema missing from the v1.0 floor enumeration
        signals "not stable yet" to integrators, even when the file is
        already shipping. Closes that surface.
        """
        schemas_dir = REPO / "skills/trinity/schemas"
        actual_schemas = sorted(
            p.stem.replace(".schema", "")
            for p in schemas_dir.glob("*.schema.json")
        )
        doc_text = (REPO / "docs/three-tier-architecture.md").read_text(
            encoding="utf-8"
        )
        for schema_stem in actual_schemas:
            if f"`{schema_stem}`" not in doc_text:
                raise AssertionError(
                    f"docs/three-tier-architecture.md doesn't mention "
                    f"schema `{schema_stem}` even though "
                    f"skills/trinity/schemas/{schema_stem}.schema.json "
                    f"ships. Either add it to the v1.0 floor schemas "
                    f"enumeration (around L122) with a parenthetical "
                    f"noting when it shipped, or — if the schema is "
                    f"intentionally undocumented — explain why with a "
                    f"comment so future-me doesn't re-introduce the "
                    f"drift. Schemas on disk: " + ", ".join(actual_schemas)
                )

    def test_bundled_config_example_matches_top_level(self):
        """The bundled `src/trinity_local/data/config.example.json` is the
        fallback config.py loads when the user's own config can't be found
        (config.py:76-82). It MUST match the top-level `config.example.json`
        — otherwise fresh installs get a stale shape.

        Drift detected on 2026-05-20: top-level was renamed gemini→antigravity
        in tick 5f13fe4 AND lost `default_task_kind` in tick 47, but the
        bundled copy held both stale fields for 3 days. Pattern #4 + #20:
        load-bearing fact lives in N=2 surfaces, drift accumulates in
        whichever has fewer eyes on it.
        """
        top_level = (REPO / "config.example.json").read_text(encoding="utf-8")
        bundled = (REPO / "src/trinity_local/data/config.example.json").read_text(encoding="utf-8")
        if top_level != bundled:
            raise AssertionError(
                "src/trinity_local/data/config.example.json drifted from "
                "config.example.json. The bundled copy is what fresh installs "
                "fall back to via config.py:76-82. Re-sync with:\n\n"
                "    cp config.example.json src/trinity_local/data/config.example.json\n"
            )

    def test_future_annotations_import_in_annotated_modules(self):
        """claude.md coding conventions: `from __future__ import annotations`
        in every module for PEP 604 style. Pin the convention with a guard.

        Scope: src/trinity_local/**/*.py files that actually USE type
        annotations (function signatures with arg/return types, or
        AnnAssign statements). Skips __init__.py + files with zero
        annotations (the import would be noise).

        Detected at tick 99 — only design_system.py was missing it (1 of
        ~70 annotated modules). Without this guard, the next missing
        import after a refactor would silently drift the convention.
        """
        import ast
        missing: list[str] = []
        src_dir = REPO / "src" / "trinity_local"
        for f in src_dir.rglob("*.py"):
            if "__pycache__" in str(f) or "egg-info" in str(f):
                continue
            if f.name == "__init__.py":
                continue
            try:
                text = f.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if "from __future__ import annotations" in text:
                continue
            try:
                tree = ast.parse(text)
            except SyntaxError:
                continue
            has_annotation = any(
                isinstance(node, ast.AnnAssign) or
                (isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and
                 (node.returns is not None or
                  any(arg.annotation for arg in node.args.args)))
                for node in ast.walk(tree)
            )
            if has_annotation:
                missing.append(str(f.relative_to(REPO)))
        if missing:
            details = "\n".join(f"  {m}" for m in sorted(missing))
            raise AssertionError(
                "Modules use type annotations but lack the convention "
                "`from __future__ import annotations` import. Add it "
                "right after the module docstring:\n\n" + details
            )

    def test_install_curl_commands_use_fsSL(self):
        """Every `curl … install.sh | bash` form across the repo must use
        `-fsSL` (or equivalent flags including `-f`). The `-f` flag makes
        curl exit non-zero on HTTP errors — without it, a 4xx/5xx response
        body (an HTML error page from CDN) gets piped directly into bash.
        The landing page at docs/index.html shipped briefly with `-sSL`
        before tick 88 caught it; this guard pins every install-command
        surface to the safer flag set so the same drift can't recur.

        Catches: `curl -sSL …install.sh | bash`, `curl -sL …install.sh | bash`,
        any other form missing -f when piping into bash.
        Excludes: prose narration of the form, comment lines, test fixtures.
        """
        import re
        # Pattern: curl <flags> <url with install.sh> | bash
        # Flags must include 'f' (in any order with s/S/L).
        bad_pattern = re.compile(
            r"curl\s+(-[sSL]+)\s+https?://\S+install\.sh\b[^\n]*\|\s*bash",
            re.MULTILINE,
        )
        bad_hits: list[tuple[str, int, str]] = []
        for ext in ("md", "html", "py", "sh", "toml"):
            for f in REPO.rglob(f"*.{ext}"):
                if ".venv" in str(f) or "node_modules" in str(f) or ".git/" in str(f):
                    continue
                if "launch_councils/" in str(f):
                    continue
                # Skip THIS test file (it contains the pattern in error messages)
                if f.resolve() == Path(__file__).resolve():
                    continue
                try:
                    text = f.read_text(encoding="utf-8", errors="replace")
                except Exception:
                    continue
                for m in bad_pattern.finditer(text):
                    flags = m.group(1)
                    if "f" in flags:
                        continue  # has -f, safe
                    line_no = text[:m.start()].count("\n") + 1
                    bad_hits.append((str(f.relative_to(REPO)), line_no, m.group(0)))
        if bad_hits:
            details = "\n".join(f"  {p}:{ln}  {snip}" for p, ln, snip in bad_hits)
            raise AssertionError(
                "Install curl command missing -f flag (would pipe HTTP "
                "error bodies into bash):\n\n" + details +
                "\n\nFix: use `curl -fsSL …` (the -f makes curl exit "
                "non-zero on 4xx/5xx instead of dumping the error page "
                "into the shell)."
            )


class TestNoRetiredSubsystemSectionsInDocs:
    """Permanent guard born of iter #55 of the post-launch sweep.

    Some subsystems were retired with a clean note ("X was retired
    pre-launch"), but the PROSE describing how X works lived on in
    the same file. Reader scrolls past the retirement note, hits the
    "How the watcher decides when to emit a recommendation" section,
    and walks away with a wrong mental model.

    Concrete case caught in iter #55:
    `docs/launcher-patterns.md` correctly said at L132 that the
    `watch-once`/`watch-loop` CLIs were retired pre-launch, but
    L134-152 still had a `## Watcher layer (optional)` section
    describing responsibilities, restrictions, and emit semantics
    of a subsystem that no longer exists. Same shape as principle
    #20 (drifted-oldest-surface): the retirement note lived in the
    *recent* edit area; the explanatory prose was older and didn't
    get co-edited.

    Guard: maintain a small allowlist of retired-subsystem section
    headings that must NOT appear as `##` / `###` headers in
    user-facing docs (excluding CHANGELOG / simplification_log /
    spec-v* historical-context files). When a new subsystem retires
    + its prose-section needs killing, add the heading string here in
    the same commit as the prose deletion.
    """

    # Section headings that describe a subsystem retired in
    # retired_names.py. Match is case-insensitive and uses startswith
    # (so `## Watcher layer (optional)` and `## Watcher layer`
    # both trip).
    RETIRED_SUBSYSTEM_HEADINGS = (
        "watcher layer",
        "watch loop",
        "watch-once / watch-loop",
        "macos shortcut dispatch",
    )

    DOCS_TO_CHECK = (
        "claude.md",
        "README.md",
        "docs/launcher-patterns.md",
        "docs/three-tier-architecture.md",
        "docs/product-spec.md",
        "docs/spec-v1.md",
        "docs/spec-v1.5.md",
        "docs/spec-v1.6.md",
    )

    def test_no_retired_subsystem_section_headings(self):
        import re
        repo = Path(__file__).resolve().parent.parent
        # Section heading: `## Heading text` or `### Heading text`.
        heading_re = re.compile(r"^(#{2,4})\s+(.+?)\s*$", re.MULTILINE)

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
                m = heading_re.match(line)
                if not m:
                    continue
                heading_text = m.group(2).strip().lower()
                for retired_heading in self.RETIRED_SUBSYSTEM_HEADINGS:
                    if heading_text.startswith(retired_heading):
                        hits.append((doc, lineno, line.strip(), retired_heading))
                        break
        if hits:
            msg = ["Section headings describing retired subsystems still in user-facing docs:"]
            for doc, lineno, line, retired in hits:
                msg.append(f"  {doc}:{lineno} `{line}` (retired subsystem: {retired})")
            msg.append("")
            msg.append(
                "These sections explain how a subsystem works that the rest "
                "of the doc says was retired — readers scroll past the "
                "retirement note and form a wrong mental model. Delete the "
                "section. If the subsystem is partially retained (e.g. a "
                "helper survives), name the helper directly instead of "
                "the umbrella subsystem name."
            )
            raise AssertionError("\n".join(msg))


class TestSchemaMirrorsStaySynchronized:
    """Permanent guard born of iter #58 of the post-launch sweep.

    Trinity ships JSON Schemas in two locations:
      - `schemas/` (top-level repo) — canonical, $id-referenced URL
        target, what launch-package.md L206 raw.github-fetches in the
        repo-public smoke test
      - `skills/trinity/schemas/` — bundled copy that ships with the
        Trinity skill (per docs/three-tier-architecture.md L126:
        "copies of the in-repo schemas")

    Drift caught in iter #58: past consistency iters updated
    `schemas/council_outcome.schema.json` (added 3 new fields,
    retired-record_outcome description) and
    `schemas/eval_set.schema.json` (gemini → antigravity), but
    `skills/trinity/schemas/` didn't get the same edits. Same shape
    as iter #54's SKILL.md mirror sync — two file copies + a doc
    saying "these stay in sync" + nothing enforcing it.

    Guard: for every JSON schema file in `schemas/`, the bundled
    copy at `skills/trinity/schemas/` must exist and be byte-
    identical. The guard tolerates extra files in skills/ but not
    drift between the matched pair. (Historical note: `trust.schema.
    json` previously had a skills/-only asymmetry, then a matched
    pair, then both deleted 2026-05-22 in iter #121 after the trust
    library retirement.)
    """

    def test_schemas_directories_stay_byte_identical(self):
        repo = Path(__file__).resolve().parent.parent
        top_level = repo / "schemas"
        bundled = repo / "skills" / "trinity" / "schemas"

        if not top_level.exists() or not bundled.exists():
            return  # nothing to check on this checkout

        drifts: list[str] = []
        missing: list[str] = []
        for canonical in sorted(top_level.glob("*.schema.json")):
            mirror = bundled / canonical.name
            if not mirror.exists():
                missing.append(canonical.name)
                continue
            if canonical.read_bytes() != mirror.read_bytes():
                drifts.append(canonical.name)

        if missing or drifts:
            msg = []
            if missing:
                msg.append(
                    "Schema files in `schemas/` missing from "
                    "`skills/trinity/schemas/` (would ship a stale skill "
                    "bundle to new users):"
                )
                for f in missing:
                    msg.append(f"  {f}")
            if drifts:
                if msg:
                    msg.append("")
                msg.append(
                    "Schema files that drifted between `schemas/` (canonical) "
                    "and `skills/trinity/schemas/` (bundled copy):"
                )
                for f in drifts:
                    msg.append(f"  {f}")
            msg.append("")
            msg.append(
                "Re-sync the bundled copies. `schemas/` is the canonical "
                "$id-referenced source per the URL pattern in 3 of 4 "
                "schema files. Fix:\n"
                "  cp schemas/<name>.schema.json skills/trinity/schemas/"
            )
            raise AssertionError("\n".join(msg))


class TestNoStaleNewAnnotationsInClaudeMd:
    """`(NEW)` markers on modules/symbols in `claude.md` are stale-magnets:
    they're written when something is genuinely new, then never deleted.
    By the time a reader sees them weeks later, they're noise pretending
    to be signal — the same shape as principle #20 (oldest surface
    drifts because edits touch the recent surface).

    Sweep iter #82 caught two: `CouncilChainStep (NEW)` and
    `chairman_picker.py (NEW)` — both shipped weeks before the audit
    found them. This guard fails on any `(NEW)` token in the architecture
    sections of `claude.md`. CHANGELOG.md and the explicitly-historical
    `docs/launch-package.md` "Originally recommended" block are exempt
    (CHANGELOG is timestamped append-only; the launch-package block
    explicitly preserves original framing for narrative continuity).
    """

    def test_no_new_annotation_in_claude_md(self):
        repo = Path(__file__).resolve().parent.parent
        target = repo / "claude.md"
        text = target.read_text(encoding="utf-8")

        offenders: list[tuple[int, str]] = []
        for idx, line in enumerate(text.splitlines(), start=1):
            if "(NEW)" in line:
                offenders.append((idx, line.strip()))

        if offenders:
            msg = [
                "`(NEW)` annotations found in claude.md — these go stale silently.",
                "Drop the marker; the module is stable by the time anyone reads it.",
                "",
            ]
            for ln, txt in offenders:
                msg.append(f"  claude.md:{ln}: {txt[:140]}")
            raise AssertionError("\n".join(msg))


class TestCitedCommitsResolveInGit:
    """Live docs cite commit SHAs to anchor specific events ('retired
    2026-05-18 in commit `1fed7fc`'). If a cited commit disappears
    (rebase, force-push, never-existed-typo), the doc points at
    nothing. Sweep iter #114 baselined this: 6 commit refs across
    claude.md + 4 live docs, all resolve today.

    Same shape as iter #80's `test_every_commit_ref_resolves_in_git`
    for retired_names.py — that guard catches missing commit refs in
    the retirement registry; this one catches the same drift class
    in published prose. Together they cover the two surfaces where
    Trinity anchors claims to specific commits.

    Guard: scan claude.md + README.md + class:live docs in docs/ for
    'commit <sha>' or 'commit `<sha>`' patterns. Run `git cat-file
    -t <sha>` per match. Fail if any return non-zero (= unresolved
    commit ref).
    """

    def test_every_cited_commit_resolves_in_git(self):
        import re
        import subprocess

        repo = Path(__file__).resolve().parent.parent
        targets: list[Path] = [repo / "claude.md", repo / "README.md"]
        docs_dir = repo / "docs"
        if docs_dir.exists():
            for path in sorted(docs_dir.glob("*.md")):
                try:
                    head = path.read_text(encoding="utf-8")[:200]
                except (OSError, UnicodeDecodeError):
                    continue
                if "class: live" in head:
                    targets.append(path)

        # Match `commit <sha>` or `commit \`<sha>\`` — sha is a 7-40
        # char hex string. The `commit` prefix prevents false positives
        # on basin_ids and other hex content.
        commit_re = re.compile(
            r"\bcommit\s+`?([a-f0-9]{7,40})`?",
            re.IGNORECASE,
        )

        seen: set[tuple[str, str]] = set()  # dedupe (file, sha) pairs
        broken: list[tuple[str, int, str]] = []
        for path in targets:
            rel = path.relative_to(repo).as_posix()
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            for idx, line in enumerate(lines, start=1):
                for match in commit_re.finditer(line):
                    sha = match.group(1)
                    key = (rel, sha)
                    if key in seen:
                        continue
                    seen.add(key)
                    # `git cat-file -t <sha>` is fast — single object
                    # lookup. Exit 0 = exists; 128 = not found.
                    result = subprocess.run(
                        ["git", "cat-file", "-t", sha],
                        cwd=repo,
                        capture_output=True,
                        text=True,
                    )
                    if result.returncode != 0:
                        broken.append((rel, idx, sha))

        if broken:
            msg = [
                "Live docs cite commit SHAs that don't resolve in git.",
                "Possible causes: rebase/force-push removed the commit,",
                "typo in the SHA, or the commit was never pushed.",
                "",
                "Fix: update the citation to a real commit (use `git log`",
                "to find the right SHA), or remove the citation if the",
                "event being cited has no anchorable commit.",
                "",
            ]
            for rel, ln, sha in broken:
                msg.append(f"  {rel}:{ln}: commit `{sha}` does not exist")
            raise AssertionError("\n".join(msg))


class TestSchemaNestedFieldsMatchDataclassFields:
    """Iter #109 caught real schema-vs-dataclass drift in nested
    types: schemas/council_outcome.schema.json declared 3 member_results
    fields the dataclass never emits (reasoning_summary, error,
    elapsed_seconds — they live on different dataclasses) and omitted
    2 fields the dataclass does emit (session_id, metadata). Same
    asymmetry on chain_steps. Iter #109 fixed both.

    Per task #117 ('Standardize ~/.trinity/'), the schemas are
    published as the contract for other tools to adopt. A schema that
    misrepresents what Trinity actually emits breaks adopters in two
    directions: they expect fields that never arrive, and they don't
    expect fields that do.

    Guard: introspect each nested type's schema declaration vs the
    backing dataclass's field set. Field-set parity required.
    """

    def test_council_outcome_nested_types_match_dataclasses(self):
        import json
        import dataclasses

        from trinity_local.council_schema import (
            CouncilMemberResult,
            CouncilChainStep,
            CouncilRoutingLabel,
        )
        from trinity_local.evals.builder import EvalItem

        repo = Path(__file__).resolve().parent.parent
        council_schema_path = repo / "schemas" / "council_outcome.schema.json"
        council_schema = json.loads(council_schema_path.read_text(encoding="utf-8"))
        eval_schema_path = repo / "schemas" / "eval_set.schema.json"
        eval_schema = json.loads(eval_schema_path.read_text(encoding="utf-8"))

        cases = [
            (
                "council_outcome.member_results",
                CouncilMemberResult,
                council_schema["properties"]["member_results"]["items"]["properties"],
            ),
            (
                "council_outcome.chain_steps",
                CouncilChainStep,
                council_schema["properties"]["chain_steps"]["items"]["properties"],
            ),
            (
                "council_outcome.routing_label",
                CouncilRoutingLabel,
                council_schema["$defs"]["routing_label"]["properties"],
            ),
            (
                "eval_set.eval_item",
                EvalItem,
                eval_schema["$defs"]["eval_item"]["properties"],
            ),
        ]

        offenders: list[str] = []
        for name, klass, schema_props in cases:
            schema_fields = set(schema_props.keys())
            dataclass_fields = {f.name for f in dataclasses.fields(klass)}
            only_schema = sorted(schema_fields - dataclass_fields)
            only_dataclass = sorted(dataclass_fields - schema_fields)
            if only_schema:
                offenders.append(
                    f"  {name}: schema declares fields the dataclass "
                    f"doesn't emit: {only_schema}"
                )
            if only_dataclass:
                offenders.append(
                    f"  {name}: dataclass emits fields the schema doesn't "
                    f"document: {only_dataclass}"
                )

        if offenders:
            msg = [
                "Schema nested-type fields drifted from the backing "
                "dataclasses. The schemas are the published contract "
                "(task #117); adopters break when they misrepresent "
                "reality.",
                "",
                "Fix: either add the missing field to the schema (with a "
                "JSON Schema type) or to the dataclass (and to to_dict), "
                "and mirror to skills/trinity/schemas/.",
                "",
            ]
            msg.extend(offenders)
            raise AssertionError("\n".join(msg))


class TestSaveCouncilOutcomeEnforcesSchemaRequiredFields:
    """`schemas/council_outcome.schema.json` declares `synthesis_output`
    and `routing_label` as required. The `CouncilOutcome` dataclass
    allows both to be None (same shape during async council execution
    before chairman synthesis lands). Sweep iter #106 caught the
    contract gap: nothing enforced that pre-synthesis outcomes couldn't
    accidentally hit `save_council_outcome` and write a schema-invalid
    JSON to disk.

    Fix: `save_council_outcome` now raises ValueError if either field
    is None. Live progress files belong in `council_status_dir()`;
    `council_outcomes/` is for completed councils only.

    Guard: assert the fail-fast assertion fires for both fields.
    Catches regressions where someone removes the assertion in a
    refactor.
    """

    def test_save_refuses_outcome_with_none_synthesis_output(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        # Re-import to pick up TRINITY_HOME
        import importlib
        import trinity_local.state_paths as sp
        importlib.reload(sp)

        from trinity_local.council_runtime import save_council_outcome
        from trinity_local.council_schema import (
            CouncilOutcome, CouncilMemberResult, CouncilRoutingLabel,
        )

        outcome = CouncilOutcome(
            council_run_id="c_test_no_synth",
            bundle_id="b1",
            task_cluster_id="tc1",
            primary_provider="claude",
            member_results=[CouncilMemberResult(provider="claude", output_text="hi")],
            created_at="2026-05-22T00:00:00Z",
            synthesis_output=None,  # ← schema says required
            routing_label=CouncilRoutingLabel(winner="claude"),
        )
        import pytest
        with pytest.raises(ValueError, match="synthesis_output is None"):
            save_council_outcome(outcome)

    def test_save_refuses_outcome_with_none_routing_label(self, tmp_path, monkeypatch):
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        import importlib
        import trinity_local.state_paths as sp
        importlib.reload(sp)

        from trinity_local.council_runtime import save_council_outcome
        from trinity_local.council_schema import (
            CouncilOutcome, CouncilMemberResult,
        )

        outcome = CouncilOutcome(
            council_run_id="c_test_no_label",
            bundle_id="b1",
            task_cluster_id="tc1",
            primary_provider="claude",
            member_results=[CouncilMemberResult(provider="claude", output_text="hi")],
            created_at="2026-05-22T00:00:00Z",
            synthesis_output="some output",
            routing_label=None,  # ← schema says required
        )
        import pytest
        with pytest.raises(ValueError, match="routing_label is None"):
            save_council_outcome(outcome)

    def test_rejection_signal_constructible_with_schema_required_fields_only(self):
        """Iter #108: schemas/rejection_signal.schema.json declares
        only `[id, type, model_quote, user_substitute]` as required.
        The RejectionSignal dataclass previously required 7 fields
        (no defaults on why_signal, prompt_id, basin) — tighter than
        the schema. An external schema-conformant producer would slip
        past the schema but fail dataclass construction.

        Fix: dataclass defaults aligned with schema. why_signal=\"\",
        prompt_id=None, basin=None. parse_rejections already passes
        all fields explicitly, so live behavior unchanged.

        Guard: construct a RejectionSignal with only the schema-
        required fields. Confirms the dataclass accepts what the
        schema accepts.
        """
        from trinity_local.me.turn_pairs import RejectionSignal

        # Should not raise — schema-minimal construction.
        sig = RejectionSignal(
            id="r1",
            type="REFRAME",
            model_quote="some model output",
            user_substitute="user's rewrite",
        )
        assert sig.id == "r1"
        assert sig.why_signal == ""
        assert sig.prompt_id is None
        assert sig.basin is None
        assert sig.next_user_turn == ""

    def test_save_eval_set_refuses_stats_without_items_key(self, tmp_path, monkeypatch):
        """Iter #107 extension: eval_set.schema.json declares
        `stats.items` (the integer count) as required, but the
        EvalSet dataclass types stats as a bare dict. save_eval_set
        now fails fast if the dict shape is wrong."""
        monkeypatch.setenv("TRINITY_HOME", str(tmp_path))
        import importlib
        import trinity_local.state_paths as sp
        importlib.reload(sp)

        from trinity_local.evals.builder import EvalSet, save_eval_set

        eval_set = EvalSet(
            eval_id="e_test_bad_stats",
            built_at="2026-05-22T00:00:00Z",
            source="rejections",
            stats={"total": 0},  # ← schema requires `items`, not `total`
            items=[],
        )
        import pytest
        with pytest.raises(ValueError, match="stats.*items"):
            save_eval_set(eval_set)


class TestHandoffSlugIsAntigravity:
    """The `handoff` CLI + MCP tool take the provider slug — per
    task #127, the Google harness slug is `antigravity` (not the
    legacy `gemini`). Active docs sometimes write
    `trinity-local handoff gemini` because the brand name is more
    recognizable, but the literal slug-bearing invocations must
    match what the CLI accepts.

    Sweep iter #102 caught:
    - `docs/launch.md:240` — `trinity-local handoff gemini` in the
      60-second demo script.
    - `docs/launch.md:241` — \"→ handed off to gemini — 3 prior turns\"
      in the script (this is CLI header output, echoes the slug).

    Same drift class as iter #98 (LAUNCH_CHECKLIST.md L48 same line
    of code). The fix is mechanical: handoff invocations use the
    slug, not the brand. Surrounding brand-level prose can stay
    \"Gemini\" per the claude.md L562 mixed-marketing convention.

    Guard: scan `class: live` markdown files for the literal pattern
    `handoff gemini` (case-insensitive). The slug is `antigravity` —
    any `handoff gemini` is drift.
    """

    def test_no_handoff_gemini_in_live_docs(self):
        import re

        repo = Path(__file__).resolve().parent.parent
        targets: list[Path] = [repo / "claude.md", repo / "README.md"]
        docs_dir = repo / "docs"
        if docs_dir.exists():
            for path in sorted(docs_dir.glob("*.md")):
                try:
                    head = path.read_text(encoding="utf-8")[:200]
                except (OSError, UnicodeDecodeError):
                    continue
                if "class: live" in head:
                    targets.append(path)

        # The two patterns that indicate handoff-with-wrong-slug:
        #   - `handoff gemini` (CLI invocation)
        #   - `handed off to gemini` (CLI output text echoing the slug)
        bad_invoke_re = re.compile(r"\bhandoff\s+gemini\b", re.IGNORECASE)
        bad_output_re = re.compile(r"handed off to gemini", re.IGNORECASE)

        offenders: list[str] = []
        EXEMPT_FILES = {"tests/test_doc_count_consistency.py"}
        for path in targets:
            rel = path.relative_to(repo).as_posix()
            if rel in EXEMPT_FILES:
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            for idx, line in enumerate(lines, start=1):
                if bad_invoke_re.search(line) or bad_output_re.search(line):
                    offenders.append(f"  {rel}:{idx}: {line.strip()[:140]}")

        if offenders:
            msg = [
                "Active docs cite `handoff gemini` but the CLI slug is",
                "`antigravity` (post-task-#127 rename of the Google",
                "harness). The handoff CLI + MCP tool accept the slug,",
                "not the marketing brand.",
                "",
                "Fix: replace `handoff gemini` → `handoff antigravity` and",
                "`handed off to gemini` → `handed off to antigravity`. The",
                "surrounding brand-level prose (e.g. \"Gemini picks up\")",
                "stays per the claude.md L562 mixed-marketing convention.",
                "",
            ]
            msg.extend(offenders)
            raise AssertionError("\n".join(msg))


class TestNoUnusedLocalsInTestsOrSrc:
    """Unused local variables are a signal-masking sub-class of dead
    code — pyflakes emits 'local variable X is assigned to but never
    used'. Same shape as TestNoUnusedImportsInTests (iter #99) and
    TestNoFStringWithoutPlaceholders (tick #55): noise drowns the
    next real bug.

    Sweep iter #101 cleaned 6 unused locals:
    - src/trinity_local/launchpad_data.py:1746 (`task_to_basin`) and
      :1751 (`basin_labels`) — orphaned by the 2026-05-21 sunset of
      the per-card cross-memory chips on recent-council cards. The
      build-once-per-render setup lost its consumer when the chips
      were removed.
    - tests/test_ask.py:767 (`original_log`) — save with no restore;
      monkeypatch makes the save redundant.
    - tests/test_install_mcp.py:277 (`first_mtime`) — captured for an
      mtime-equality assertion that the comment explicitly declines.
    - tests/test_doc_count_consistency.py:3451 (`ds_lower`) — lowered
      copy of docstring, never consumed.
    - tests/test_phase8_integration.py:137 (`js`) — `launchpad_runtime_js()`
      call orphaned when the test was refactored to crawl
      launchpad_template source instead.

    Guard: shell out to pyflakes against tests/ + src/, fail on any
    'assigned to but never used' line. Filters out the noqa-marked
    src/ unused imports that are intentional re-exports.
    """

    def test_no_unused_locals_in_tests_and_src(self):
        import subprocess
        import sys

        repo = Path(__file__).resolve().parent.parent
        scan_dirs = [
            repo / "tests",
            repo / "src" / "trinity_local",
        ]
        result = subprocess.run(
            [sys.executable, "-m", "pyflakes", *[str(d) for d in scan_dirs]],
            capture_output=True,
            text=True,
        )
        unused_local_hits = [
            line for line in result.stdout.splitlines()
            if "assigned to but never used" in line
        ]
        if unused_local_hits:
            msg = [
                f"pyflakes flagged {len(unused_local_hits)} unused local "
                f"variables in tests/ or src/. The post-iter-#101 baseline "
                f"is zero.",
                "",
                "Common fixes:",
                "  - delete the dead assignment",
                "  - if intentional (e.g. capturing for debugging), prefix "
                "    with `_` to signal intent",
                "  - if the variable was supposed to be used, restore the "
                "    consumer (often: assertion or comparison dropped during refactor)",
                "",
            ]
            for line in unused_local_hits[:20]:
                msg.append(f"  {line}")
            if len(unused_local_hits) > 20:
                msg.append(f"  ... and {len(unused_local_hits) - 20} more")
            raise AssertionError("\n".join(msg))


class TestNoUndefinedNamesInTests:
    """pyflakes 'undefined name' warnings are real bugs — code that
    references a name not in scope. Unlike unused-imports (signal-
    masking), undefined names indicate code that would fail at
    runtime under some path.

    Sweep iter #100 caught one in `tests/test_me_turn_pairs.py:44`:
    `def _sig(...) -> \"RejectionSignal\":` used a string-form
    forward reference annotation, and `RejectionSignal` was only
    imported inside the function body. With `from __future__ import
    annotations` in effect (L9), all annotations are lazy-strings
    anyway, so the explicit quotes were redundant — but pyflakes
    couldn't resolve `RejectionSignal` at the annotation site
    because the import was function-scoped. Fixed by hoisting the
    import to module-scope.

    Guard: shell out to pyflakes against tests/ + src/, fail on any
    'undefined name' line. Defensive against the next forward-ref-
    style annotation lookup that pyflakes can't resolve.
    """

    def test_no_undefined_names_in_tests_and_src(self):
        import subprocess
        import sys

        repo = Path(__file__).resolve().parent.parent
        scan_dirs = [
            repo / "tests",
            repo / "src" / "trinity_local",
        ]
        result = subprocess.run(
            [sys.executable, "-m", "pyflakes", *[str(d) for d in scan_dirs]],
            capture_output=True,
            text=True,
        )
        undefined_hits = [
            line for line in result.stdout.splitlines()
            if "undefined name" in line
        ]
        if undefined_hits:
            msg = [
                "pyflakes flagged undefined names in tests/ or src/. "
                "Undefined names cause runtime errors under the code path "
                "that hits them.",
                "",
                "Common fixes:",
                "  - hoist function-scope imports to module scope when used "
                "in annotations",
                "  - add the missing import",
                "  - check spelling against the actual name in the imported module",
                "",
            ]
            for line in undefined_hits:
                msg.append(f"  {line}")
            raise AssertionError("\n".join(msg))


class TestNoUnusedImportsInTests:
    """Task #100 ('Unused-imports cleanup pass — pyflakes-driven')
    was marked completed on 2026-05-12. Sweep iter #99 found the
    drift had re-accumulated: pyflakes flagged 89 unused imports
    across 49 test files. Task-#100's claim was no longer accurate.

    The drift class is signal-masking — same shape as
    `TestNoFStringWithoutPlaceholders` (tick 55): when pyflakes
    reports dozens of unused imports the warning becomes wallpaper,
    and the next real bug (an accidentally-dropped consumer of a
    legitimate import) hides in the noise.

    Iter #99 ran autoflake to remove all 89 + manually fixed one
    edge case (a misleading `# noqa: F401 — keep import` for a
    truly-unused module probe). Net: tests/ went from 89 → 0
    unused imports.

    Guard: shell out to pyflakes against `tests/` and fail if any
    'imported but unused' line is present. The same pattern as
    `test_no_fstring_without_placeholders_in_commands` (tick 55) —
    parse pyflakes stdout, filter for the specific warning class,
    fail if non-empty. Doesn't gate on pyflakes exit code (which
    fires on many other warning classes).
    """

    def test_no_unused_imports_in_tests(self):
        import subprocess
        import sys

        repo = Path(__file__).resolve().parent.parent
        tests_dir = repo / "tests"

        result = subprocess.run(
            [sys.executable, "-m", "pyflakes", str(tests_dir)],
            capture_output=True,
            text=True,
        )
        unused_import_hits = [
            line for line in result.stdout.splitlines()
            if "imported but unused" in line
        ]
        if unused_import_hits:
            msg = [
                f"pyflakes found {len(unused_import_hits)} unused imports "
                f"in tests/. The post-iter-#99 baseline is zero.",
                "",
                "Either remove the import (autoflake does this cleanly:",
                "  python -m autoflake --remove-all-unused-imports",
                "    --recursive --in-place tests/",
                "), or — if the import is intentional probing — give it a",
                "real use (assert it's importable inside the test body).",
                "",
            ]
            for line in unused_import_hits[:20]:
                msg.append(f"  {line}")
            if len(unused_import_hits) > 20:
                msg.append(f"  ... and {len(unused_import_hits) - 20} more")
            raise AssertionError("\n".join(msg))


class TestGeminiVersionMatchesCanonical:
    """`claude.md` L565 carries the canonical underlying-model trio:
    *"Claude Opus 4.7 / Sonnet 4.6 / Haiku 4.5 | GPT-5.5 | Gemini 3.1
    Pro Preview"*. Sweep iter #98 caught `docs/LAUNCH_CHECKLIST.md:5`
    titled *"Launch checklist — Trinity v1.0 alongside Gemini 4"* — a
    pre-launch expected-name guess that didn't match the actual
    Google launch (Gemini 3.1 Pro Preview).

    The drift is a model-version naming mismatch: when a frontier
    provider's actual launch name diverges from the expected
    pre-launch label, the checklist freezes the old guess. Same
    shape as principle #20 — load-bearing names need binding to a
    canonical source.

    Guard: scan `class: live` docs in docs/ for `Gemini N` claims
    where `N` differs from claude.md's canonical entry. CHANGELOG.md
    + sweep-patterns + simplification_log exempt (retrospective).
    """

    def test_gemini_version_in_live_docs_matches_canonical(self):
        import re

        repo = Path(__file__).resolve().parent.parent
        # Extract canonical Gemini version from claude.md provider trio table.
        claude_md = (repo / "claude.md").read_text(encoding="utf-8")
        canonical_match = re.search(
            r"\|\s*underlying model\s*\|.*?\|\s*(Gemini\s+[\w\s.-]*?Preview)\s*\|",
            claude_md,
        )
        if not canonical_match:
            raise AssertionError(
                "Couldn't locate the canonical 'underlying model' row "
                "in claude.md. The 'provider trio across layers' table "
                "should carry the Gemini version — guard regex needs "
                "updating if the table shape changed."
            )
        canonical_gemini = canonical_match.group(1).strip()

        # Scan class:live docs in docs/ for any `Gemini N` claim that
        # doesn't match the canonical version.
        # `Gemini N` with N being a digit/decimal version number.
        gemini_version_re = re.compile(r"\bGemini\s+(\d+(?:\.\d+)?)\b")
        canonical_version_match = re.search(r"(\d+(?:\.\d+)?)", canonical_gemini)
        if not canonical_version_match:
            return  # canonical doesn't have a parseable version number; skip
        canonical_version = canonical_version_match.group(1)

        docs_dir = repo / "docs"
        targets: list[Path] = []
        for path in sorted(docs_dir.glob("*.md")):
            try:
                head = path.read_text(encoding="utf-8")[:200]
            except (OSError, UnicodeDecodeError):
                continue
            if "class: live" in head:
                targets.append(path)

        offenders: list[str] = []
        for path in targets:
            rel = path.relative_to(repo).as_posix()
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            for idx, line in enumerate(lines, start=1):
                for match in gemini_version_re.finditer(line):
                    cited = match.group(1)
                    # Both must match — the version number itself,
                    # AND there's no obvious historical-context marker.
                    if cited == canonical_version:
                        continue
                    # Skip when the line is about a different concept
                    # entirely — gemini.google.com adapter, gemini takeout,
                    # ~/.gemini/ disk paths.
                    if re.search(
                        r"gemini\.google\.com|gemini\s+takeout|~/\.gemini/|gemini_takeout|gemini_cli_session",
                        line, re.IGNORECASE,
                    ):
                        continue
                    offenders.append(
                        f"  {rel}:{idx}: 'Gemini {cited}' "
                        f"(canonical: 'Gemini {canonical_version}'): {line.strip()[:120]}"
                    )

        if offenders:
            msg = [
                "Active docs cite a Gemini version that doesn't match",
                f"claude.md's canonical underlying-model entry "
                f"({canonical_gemini}).",
                "Update the citation, or update claude.md's provider trio",
                "table if the canonical version changed.",
                "",
            ]
            msg.extend(offenders)
            raise AssertionError("\n".join(msg))


class TestBundledSkillMatchesTopLevel:
    """The `/trinity` skill ships at `skills/trinity/SKILL.md` (the
    canonical) and is mirrored to `src/trinity_local/data/skills/trinity/SKILL.md`
    (the bundled copy that `install-skill` writes to
    `~/.claude/skills/trinity/SKILL.md`). The comment in
    `TestNoRetiredCliInUserFacingDocs` (L2182) already named the guard
    that should enforce byte-identical sync — but the test was never
    written. Sweep iter #97 caught the gap: the canonical SKILL.md
    listed providers as "Claude / Codex / Gemini" (pre-task-#127),
    fixed in this iter, and the bundled copy needed the same edit.
    Without a sync guard the next edit would silently drift again.

    Same shape as `test_schemas_directories_stay_byte_identical`:
    mirror-pair files need a single guard that asserts byte-identical
    state. The comment had been promising this guard since iter 52;
    finally writing it now.
    """

    def test_canonical_and_bundled_skill_md_are_byte_identical(self):
        repo = Path(__file__).resolve().parent.parent
        canonical = repo / "skills" / "trinity" / "SKILL.md"
        bundled = repo / "src" / "trinity_local" / "data" / "skills" / "trinity" / "SKILL.md"
        if not canonical.exists() or not bundled.exists():
            return
        if canonical.read_bytes() != bundled.read_bytes():
            raise AssertionError(
                f"Canonical {canonical.relative_to(repo)} and bundled "
                f"{bundled.relative_to(repo)} have drifted. The bundled "
                f"copy is what `install-skill` writes to "
                f"`~/.claude/skills/trinity/SKILL.md`; if these diverge, "
                f"users get a different /trinity skill than the repo "
                f"documents.\n\n"
                f"Re-sync the bundled copy:\n"
                f"  cp {canonical.relative_to(repo)} {bundled.relative_to(repo)}"
            )


class TestLensPipelineStageCountConsistent:
    """Multiple doc surfaces (claude.md L863, README.md L163, docs/
    spec-v1.md L92, docs/architecture.md L58) claim the lens-build
    pipeline is "5-stage" (Stages 0–4 inclusive). Sweep iter #96
    caught FOUR code surfaces still saying "3-stage":

      src/trinity_local/commands/me.py:33   (the live `--help` text!)
      src/trinity_local/me/pipeline.py:1    (module docstring)
      src/trinity_local/me/__init__.py:3    (package docstring)
      src/trinity_local/launchpad_data.py:1522

    The "3-stage" phrasing froze at the Option C ratification (basins
    + decisions + pair-mining = 3). Stage 0 was added later
    (council_e7560934 turn-pair gap extraction) and Stage 4 was split
    out from pair_mining for legibility — neither propagated to the
    code-side docstrings. Same shape as principle #20.

    Drift surface matters most for commands/me.py: the help text is
    what users see when they run `trinity-local lens-build --help`.
    A discrepancy between "3-stage" in help and "5-stage" in README
    is the kind of incongruity that erodes credibility.

    Guard: assert the live `lens-build` subparser help text contains
    "5-stage" (or no stage-count claim at all). Also assert all
    src/trinity_local/me/__init__.py + me/pipeline.py docstrings
    don't say "3-stage".
    """

    def test_lens_build_help_says_five_stage(self):
        import argparse, importlib

        parser = argparse.ArgumentParser(prog="trinity-local")
        subparsers = parser.add_subparsers(dest="command")
        main_mod = importlib.import_module("trinity_local.main")
        for module in main_mod._iter_command_modules():
            if (r := getattr(module, "register", None)):
                try:
                    r(subparsers)
                except Exception:
                    continue

        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                for choice_action in action._choices_actions:
                    if choice_action.dest == "lens-build":
                        help_text = choice_action.help or ""
                        if "3-stage" in help_text or "3 stage" in help_text:
                            raise AssertionError(
                                f"lens-build --help says '3-stage' but the live "
                                f"pipeline is 5 stages (0–4 inclusive). Doc surfaces "
                                f"(claude.md, README.md, docs/spec-v1.md, "
                                f"docs/architecture.md) all say 5-stage. Update the "
                                f"register() help= text to match.\n"
                                f"Current help: {help_text!r}"
                            )
                        return
        raise AssertionError("Couldn't locate lens-build subparser in argparse")

    def test_me_package_docstrings_say_five_stage(self):
        repo = Path(__file__).resolve().parent.parent
        targets = [
            repo / "src" / "trinity_local" / "me" / "__init__.py",
            repo / "src" / "trinity_local" / "me" / "pipeline.py",
        ]
        offenders: list[str] = []
        for path in targets:
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for idx, line in enumerate(text.splitlines(), start=1):
                # Stop scanning after the docstring (rough heuristic:
                # stop at first import or non-quoted line past line 30).
                if idx > 30:
                    break
                if "3-stage" in line or "3 stage" in line:
                    rel = path.relative_to(repo).as_posix()
                    offenders.append(f"  {rel}:{idx}: {line.strip()[:140]}")
        if offenders:
            msg = [
                "me/ package docstrings say '3-stage' but the live pipeline",
                "is 5 stages (0–4 inclusive). Update to '5-stage' to match",
                "claude.md / README.md / docs/spec-v1.md / docs/architecture.md.",
                "",
            ]
            msg.extend(offenders)
            raise AssertionError("\n".join(msg))


class TestProductSpecArchitectureTodayCommandsResolve:
    """`docs/product-spec.md` has an "Architecture Today" section
    (L120+) with a table that maps `commands/<name>.py` modules to
    their key CLI subcommands. The drift class — the table cites
    subcommand names, but doesn't bind them to the live argparse
    surface.

    Sweep iter #95 caught the council.py row citing `council-html`
    (retired 2026-05-17 with the verifier→synthesis rename) as a
    Key command. Same shape as iter #87 — a Phase/Architecture
    table claims completeness against current state but drifts
    silently when CLIs retire.

    Guard: for each backtick-quoted command name in the
    "Architecture Today" table of product-spec.md, assert the
    subcommand exists in the live argparse surface. Lines explicitly
    marking a retirement (`retired`, `~~`, etc.) are exempt.
    """

    def test_architecture_today_table_subcommands_resolve(self):
        import re

        repo = Path(__file__).resolve().parent.parent
        target = repo / "docs" / "product-spec.md"
        if not target.exists():
            return

        # Live argparse surface (same introspection as the canonical
        # cli_command_count helper).
        import argparse, importlib
        parser = argparse.ArgumentParser(prog="trinity-local")
        subparsers = parser.add_subparsers(dest="command")
        main_mod = importlib.import_module("trinity_local.main")
        for module in main_mod._iter_command_modules():
            if (r := getattr(module, "register", None)):
                try:
                    r(subparsers)
                except Exception:
                    continue
        live_commands: set[str] = set()
        for action in parser._actions:
            if isinstance(action, argparse._SubParsersAction):
                live_commands = set(action.choices.keys())
                break

        # Find the "Architecture Today" section and isolate its table.
        text = target.read_text(encoding="utf-8")
        section_start = text.find("## Architecture Today")
        if section_start == -1:
            return  # section was renamed, nothing to guard here
        # Stop at the next H2 heading (## ...) so we only check the
        # commands table, not the MCP-tool list further down.
        next_section = text.find("\n## ", section_start + 1)
        section = text[section_start:next_section if next_section != -1 else None]

        # Backticked tokens that look like CLI subcommands:
        #   `council-html`, `lens-build`, `install-mcp`, etc.
        token_re = re.compile(r"`([a-z]+(?:-[a-z]+)+)`")
        # Lines marking retirement get a pass.
        retirement_marker_re = re.compile(
            r"retired|deleted|removed|sunset|killed|~~|"
            r"\bcut\b|\bdrop\b|\bdrops\b|\bdelete\b|"
            r"replaced|former|legacy",
            re.IGNORECASE,
        )

        offenders: list[str] = []
        lineno = text[:section_start].count("\n") + 1
        for line in section.splitlines():
            if not line.lstrip().startswith("|"):
                lineno += 1
                continue
            for match in token_re.finditer(line):
                tok = match.group(1)
                # Heuristic: only token-shapes that look like CLI subcommands.
                # Skip non-CLI tokens (file paths, identifiers without dashes
                # to a CLI verb shape).
                if tok in live_commands:
                    continue
                # Exempt if the line marks the subcommand as retired.
                if retirement_marker_re.search(line):
                    continue
                # The token might be a file path fragment, not a CLI subcommand.
                # Filter: only tokens matching the CLI naming convention
                # (a dashed identifier of the type `verb-noun` or `verb-noun-noun`).
                # We already require the regex match; further filter by length+shape.
                if "." in tok or "/" in tok:
                    continue
                offenders.append(
                    f"  product-spec.md:{lineno}: cites `{tok}` "
                    f"(not in live argparse): {line.strip()[:120]}"
                )
            lineno += 1

        if offenders:
            msg = [
                "product-spec.md 'Architecture Today' table cites CLI",
                "subcommands that don't exist in the live argparse surface.",
                "Either remove the row, mark it retired (~~ or 'retired'),",
                "or update the prose to match the live CLI.",
                "",
            ]
            msg.extend(offenders)
            raise AssertionError("\n".join(msg))


class TestInstallMcpHarnessProseLineupIncludesCursor:
    """Sibling of `test_install_mcp_harness_claim_matches_code` —
    that guard catches counts (\"three CLI harnesses\" / \"(three
    harnesses)\" prose); this one catches *named lineups* of the
    harnesses.

    Sweep iter #93 caught `docs/spec-v1.md:96`: *"install-mcp —
    registers MCP server in Claude Code / Codex / Antigravity +
    drops /trinity skill."* Three harnesses listed, Cursor omitted.
    install.py writes to four (`.claude.json`, `.gemini/settings.json`,
    `.codex/config.toml`, `.cursor/mcp.json`).

    Same shape as principle #20 — Cursor was the most recent
    addition (P16/P92 persona audit), so older prose hadn't been
    re-edited to include it, while newer prose has.

    Guard: scan claude.md + all `class: live` docs in `docs/` for
    install-mcp prose lineups. When a line cites Claude Code AND
    Codex AND Antigravity by name in proximity, it must also cite
    Cursor. Lines that explicitly carve out the four harnesses by
    intent (e.g. listing CLI-only vs IDE harnesses) get a pass.
    """

    def test_install_mcp_harness_lineups_include_cursor(self):
        import re

        repo = Path(__file__).resolve().parent.parent
        targets: list[Path] = [repo / "claude.md", repo / "README.md"]
        docs_dir = repo / "docs"
        if docs_dir.exists():
            for path in sorted(docs_dir.glob("*.md")):
                try:
                    head = path.read_text(encoding="utf-8")[:200]
                except (OSError, UnicodeDecodeError):
                    continue
                if "class: live" in head:
                    targets.append(path)

        # Match prose that lists ≥3 of the four harnesses in proximity
        # (within a single line). The four harness names as install-mcp
        # would identify them:
        harness_re = re.compile(
            r"\bClaude Code\b|\bCodex\b|\bAntigravity\b|\bCursor\b"
        )
        # Heuristic: a line mentioning install-mcp + ≥3 harness names is
        # a lineup claim. Lines that only mention one or two are talking
        # about something narrower (e.g. just Antigravity-specific behavior).
        install_mcp_keyword_re = re.compile(
            r"install-mcp|install_mcp|\bMCP server\b|register.*MCP|wire.*MCP",
            re.IGNORECASE,
        )

        offenders: list[str] = []
        EXEMPT_FILES = {"tests/test_doc_count_consistency.py"}
        for path in targets:
            rel = path.relative_to(repo).as_posix()
            if rel in EXEMPT_FILES:
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            for idx, line in enumerate(lines, start=1):
                if not install_mcp_keyword_re.search(line):
                    continue
                hits = set(harness_re.findall(line))
                # Only enforce on lineup claims (≥3 of the four named).
                if len(hits) < 3:
                    continue
                if "Cursor" in hits:
                    continue
                offenders.append(f"  {rel}:{idx}: {line.strip()[:160]}")

        if offenders:
            msg = [
                "install-mcp prose lineups omit Cursor.",
                "install.py writes to FOUR harness configs:",
                "  ~/.claude.json   (Claude Code)",
                "  ~/.gemini/settings.json   (Antigravity)",
                "  ~/.codex/config.toml   (Codex)",
                "  ~/.cursor/mcp.json   (Cursor)",
                "Update the prose to include Cursor in the lineup.",
                "",
            ]
            msg.extend(offenders)
            raise AssertionError("\n".join(msg))


class TestShortcutDispatcherNotPresentedAsLive:
    """The macOS Shortcut dispatcher (`shortcut_setup.py`,
    `dispatch_runner.py`, `commands/shortcuts.py`, the `trinity-dispatch`
    shell wrapper) was retired 2026-05-17 in favor of the Chrome
    extension's Native Messaging bridge (capture_host.py) as the
    cross-platform launchpad dispatcher. See claude.md L656 + the
    `retired_names.py` registry.

    Sweep iter #91 caught `docs/spec-v1.md:275` — a "Deferred
    indefinitely" item phrased "the launchpad Shortcut dispatcher is
    macOS-specific until the v1.6 browser-extension fallback ships."
    Both halves were stale at the time of the audit: the Shortcut
    dispatcher had been retired, and the browser-extension fallback
    had shipped. Same shape as principle #20 — a forward-looking
    "until X" statement freezes the moment the statement was true
    and doesn't notice when X happens.

    Guard scope: any `class: live` markdown file in `docs/` plus
    claude.md / README.md. Claims like "Shortcut dispatcher is" /
    "macOS Shortcut dispatcher" / "the launchpad Shortcut" in
    present-tense or future-tense framing should fail. Lines marked
    retired/sunset/replaced (or that explicitly describe the
    historical Shortcut → Chrome extension transition) are exempt.
    """

    def test_shortcut_dispatcher_marked_retired_in_active_docs(self):
        import re

        repo = Path(__file__).resolve().parent.parent
        targets: list[Path] = [
            repo / "claude.md",
            repo / "README.md",
        ]
        docs_dir = repo / "docs"
        if docs_dir.exists():
            for path in sorted(docs_dir.glob("*.md")):
                try:
                    head = path.read_text(encoding="utf-8")[:200]
                except (OSError, UnicodeDecodeError):
                    continue
                if "class: live" in head:
                    targets.append(path)

        # Active-state claims about the Shortcut dispatcher.
        live_claim_re = re.compile(
            r"Shortcut dispatcher\s+(?:is|stays|remains|will)|"
            r"the\s+launchpad\s+Shortcut\b|"
            r"macOS\s+Shortcut\s+dispatcher\s+(?:is|stays|remains|will)",
            re.IGNORECASE,
        )
        # Exempt lines marked retired/historical.
        retirement_marker_re = re.compile(
            r"retired|sunset|replaced|deprecated|"
            r"\bgone\b|\bremoved\b|\bdeleted\b|"
            r"~~|\bwas\b|\bformer|\bprior\b|\bhistorical\b|"
            r"\btransition\b|legacy|"
            # Sentences explicitly framing the Shortcut as past-tense.
            r"used\s+to\s+be|prior\s+to|before\s+",
            re.IGNORECASE,
        )

        offenders: list[str] = []
        EXEMPT_FILES = {"tests/test_doc_count_consistency.py"}
        for path in targets:
            rel = path.relative_to(repo).as_posix()
            if rel in EXEMPT_FILES:
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            for idx, line in enumerate(lines, start=1):
                if not live_claim_re.search(line):
                    continue
                if retirement_marker_re.search(line):
                    continue
                offenders.append(f"  {rel}:{idx}: {line.strip()[:160]}")

        if offenders:
            msg = [
                "Active docs claim the macOS Shortcut dispatcher is still live.",
                "It was retired 2026-05-17 — the Chrome extension's Native",
                "Messaging bridge is the canonical dispatch path now.",
                "Either rewrite the claim with past-tense framing (was, retired,",
                "replaced) or add a retirement marker to the line.",
                "",
            ]
            msg.extend(offenders)
            raise AssertionError("\n".join(msg))


class TestScalePlanPhaseRowsResolveCitedPaths:
    """`docs/scale-plan.md` Phase tables cite backtick-quoted module
    paths as evidence of completion (✅ done). When a cited module
    gets retired or renamed, the row keeps the ✅ marker but the path
    no longer resolves — same shape as the `commands/cache.py` row
    caught in iter #87, generalized.

    Sweep iter #89 caught the Phase 0 row #12 (L80) citing
    `research/replay.py` — the `research/` package was deleted in
    the 2026-05-18 simplification pass. (The same row also claimed
    `watch_runtime.py` imports from `task_types.py`, which is no
    longer true post-watcher-retirement; that semantic drift is
    harder to catch by path-resolution alone — fixed manually in
    this iter.)

    The guard scans `docs/scale-plan.md` for backtick-quoted
    `<dir>/<file>.py` paths in lines beginning with `| ` (table rows).
    Resolves each path against either:
      - `src/trinity_local/<dir>/<file>.py`
      - `<repo>/<dir>/<file>.py`
    Lines marked retired/deleted/removed/cut/dropped/sunset/replaced
    are exempt — those explicitly document the absence. Strikethrough
    `~~`-wrapped citations are also exempt.
    """

    def test_scale_plan_phase_row_paths_resolve(self):
        import re

        repo = Path(__file__).resolve().parent.parent
        target = repo / "docs" / "scale-plan.md"
        if not target.exists():
            return

        # Match backticked paths like `dir/name.py` or `dir/sub/name.py`.
        # Stay strict — require at least one `/` so we don't catch
        # bare filenames (those are too ambiguous to resolve).
        path_re = re.compile(r"`((?:[a-z_]+/)+[a-z_]+\.py)`")
        retirement_marker_re = re.compile(
            r"retired|deleted|removed|gone|sunset|killed|~~|"
            r"\bcut\b|\bdrop\b|\bdrops\b|\bdelete\b|\bdeletes\b|"
            r"\breplaced\b|\bmoved\b|\bfolded\b|"
            r"\| (Delete|Move|Cut|Merge|Split) \|",
            re.IGNORECASE,
        )

        offenders: list[str] = []
        for idx, line in enumerate(target.read_text(encoding="utf-8").splitlines(), start=1):
            # Only scan table rows.
            if not line.lstrip().startswith("|"):
                continue
            for match in path_re.finditer(line):
                relative = match.group(1)
                resolved_under_src = (repo / "src" / "trinity_local" / relative).exists()
                resolved_under_repo = (repo / relative).exists()
                if resolved_under_src or resolved_under_repo:
                    continue
                if retirement_marker_re.search(line):
                    continue
                offenders.append(
                    f"  scale-plan.md:{idx}: cites `{relative}` "
                    f"(file absent; line not marked retired): {line.strip()[:120]}"
                )

        if offenders:
            msg = [
                "scale-plan.md Phase-table rows cite paths that no longer exist.",
                "Either the path needs to resolve (under src/trinity_local/ or",
                "repo root), or the row needs a retirement marker.",
                "",
            ]
            msg.extend(offenders)
            raise AssertionError("\n".join(msg))


class TestActiveDocsDontClaimNonexistentCommandModules:
    """docs/scale-plan.md Phase tables and similar status rows cite
    `commands/<name>.py` paths as proof of completion. When a module
    gets retired and the corresponding CLI dropped, the citation
    becomes a phantom — the path doesn't exist, but the row still
    says ✅ done.

    Sweep iter #87 caught one in `scale-plan.md:82` (Phase 0 #14)
    claiming `commands/cache.py with cache-stats/cache-clear` —
    `commands/cache.py` was deleted with the embedding-cache
    simplification 2026-05-17. Same shape as principle #20: status
    rows in mature docs rarely get re-read line-by-line.

    The guard scans all `docs/*.md` for backtick-quoted
    `commands/<name>.py` paths (`` `commands/foo.py` ``) and asserts
    each named file exists in `src/trinity_local/commands/`. Lines
    that strike-through the citation (markdown `~~`) or that contain
    a `retired`/`deleted`/`removed`/`gone` marker are exempt — those
    are explicitly documenting the absence.

    Scope limited to `docs/` to avoid noise from CHANGELOG (timestamped
    retrospective) and source-code docstrings (their own concern).
    """

    def test_scale_plan_commands_paths_resolve(self):
        import re

        repo = Path(__file__).resolve().parent.parent
        commands_dir = repo / "src" / "trinity_local" / "commands"
        docs_dir = repo / "docs"

        backtick_re = re.compile(r"`(commands/([a-z_]+)\.py)`")
        retirement_marker_re = re.compile(
            r"retired|deleted|removed|gone|sunset|killed|~~|"
            r"\bcut\b|\bdrop\b|\bdrops\b|\bdelete\b|\bdeletes\b|"
            r"\| (Delete|Move|Cut) \||"
            r"\bargparse registration\b|"
            r"\bsimplification\b",
            re.IGNORECASE,
        )
        # Dedicated retirement-narrative docs are exempt — every line
        # is about deletion by construction.
        EXEMPT_DOCS = {"docs/simplification_log.md"}

        offenders: list[str] = []
        for path in sorted(docs_dir.rglob("*.md")):
            rel = path.relative_to(repo).as_posix()
            if rel in EXEMPT_DOCS:
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            for idx, line in enumerate(lines, start=1):
                for match in backtick_re.finditer(line):
                    relative, modname = match.group(1), match.group(2)
                    if (commands_dir / f"{modname}.py").exists():
                        continue
                    if retirement_marker_re.search(line):
                        continue
                    offenders.append(
                        f"  {rel}:{idx}: cites `{relative}` (file absent, line not marked retired): {line.strip()[:120]}"
                    )

        if offenders:
            msg = [
                "Active docs cite `commands/<name>.py` modules that no longer exist.",
                "Either the cited module needs to exist, or the line needs a",
                "retirement marker (`~~strikethrough~~`, or words like",
                "'retired', 'deleted', 'removed').",
                "",
            ]
            msg.extend(offenders)
            raise AssertionError("\n".join(msg))


class TestNoDroppedTermsInTestMethodNames:
    """Task #94 dropped "verifier" as Trinity's own terminology in
    favor of "synthesis" / "Synthesis JSON". The existing
    `TestDroppedTermsAreNotReintroduced` guard scans launch-facing
    prose for the dropped term, but NOT test method names.

    Sweep iter #86 caught three stragglers in `tests/test_mcp_tools.py`:
    `test_routing_label_carries_verifier_fields`,
    `test_chairman_prompt_includes_verifier_arrays`,
    `test_routing_json_parser_extracts_verifier_fields`. All three
    bodies tested the Synthesis JSON shape (`agreed_claims`,
    `disagreed_claims`, `why_matters`) but the method names froze
    the pre-rename vocabulary. Same shape as principle #20: the test
    body got updated to match the field names; the method name
    didn't, because nothing reads back method names line-by-line.

    Drift surface matters: pytest output reads back the retired term
    every time the suite runs, training the eye to accept "verifier"
    as a live concept.

    The guard scans `tests/*.py` for `def test_*` definitions whose
    name contains a dropped term (currently just `verifier`). The
    scanner file itself is exempt (it has to mention the retired
    term to enforce the rule).
    """

    DROPPED_TERMS_IN_TEST_NAMES = {
        "verifier": (
            "task #94 dropped 'verifier' in Trinity's own voice; "
            "rename to 'synthesis' to match `agreed_claims` / "
            "`disagreed_claims` field naming"
        ),
    }

    def test_no_dropped_terms_in_test_method_names(self):
        import re

        repo = Path(__file__).resolve().parent.parent
        EXEMPT_FILES = {"tests/test_doc_count_consistency.py"}

        # Catches `def test_foo_verifier_bar(...)` etc.
        # Word-boundary at the start (`_` or word start), and an
        # underscore/paren close at the end so we don't match
        # `verifies` or `verification`.
        offenders: list[tuple[str, int, str, str]] = []
        for path in sorted((repo / "tests").rglob("test_*.py")):
            rel = path.relative_to(repo).as_posix()
            if rel in EXEMPT_FILES:
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except (OSError, UnicodeDecodeError):
                continue
            for idx, line in enumerate(lines, start=1):
                stripped = line.strip()
                if not stripped.startswith("def test_"):
                    continue
                m = re.match(r"def\s+(test_\w+)\s*\(", stripped)
                if not m:
                    continue
                method_name = m.group(1)
                for term, rationale in self.DROPPED_TERMS_IN_TEST_NAMES.items():
                    if re.search(rf"_{term}(_|$|\b)", method_name):
                        offenders.append((rel, idx, method_name, rationale))
                        break

        if offenders:
            msg = [
                "Test method names contain dropped terminology.",
                "pytest output reads back these names on every run;",
                "the retired term becomes invisible-wallpaper.",
                "",
            ]
            for rel, ln, name, rationale in offenders:
                msg.append(f"  {rel}:{ln}: {name} — {rationale}")
            raise AssertionError("\n".join(msg))


class TestMcpToolCountClaimsArePinnedToCanonical:
    """Free-floating `<N> MCP tools` / `<N> total` claims in active docs
    drift the moment the canonical count changes. The canonical-renderer
    convention (`<!-- canonical:mcp_tool_count -->8<!-- /canonical -->`)
    pins each surface to one source of truth: `mcp_server.py`'s
    registered tool count via `scripts/render_docs.py`.

    Sweep iter #85 caught two stragglers in active surfaces:
    `claude.md:574` (\"— 8 total.\") and
    `docs/launch-day/07_pricing_faq.md:13` (\"all 8 MCP tools\"). Both
    were live for >1 week; neither was guarded; both would have
    drifted silently if `mcp_server.py` had added or removed a tool.

    The guard fails on any `\\bN (MCP )?tools?\\b` claim in claude.md,
    README.md, AGENTS.md, CONTRIBUTING.md, or any `docs/launch-day/*.md`
    file that is NOT inside a `canonical:mcp_tool_count` placeholder.
    CHANGELOG.md and docs/sweep-patterns.md exempt — they are
    timestamped retrospective surfaces where historical claims are
    intentional.
    """

    def test_mcp_tool_counts_in_active_docs_use_canonical_placeholder(self):
        import re

        repo = Path(__file__).resolve().parent.parent
        targets: list[Path] = [
            repo / "claude.md",
            repo / "README.md",
            repo / "AGENTS.md",
            repo / "CONTRIBUTING.md",
        ]
        launch_day = repo / "docs" / "launch-day"
        if launch_day.exists():
            targets.extend(sorted(launch_day.glob("*.md")))
        # Sweep iter #90: extend coverage to all `class: live` docs in
        # docs/. Caught spec-v1.md L103 — a launch-spec section heading
        # hardcoded "8 total" without a canonical placeholder. Live-doc
        # status means breaking-API changes go through versioning;
        # numeric claims about the live tool surface must pin to source.
        docs_dir = repo / "docs"
        if docs_dir.exists():
            for path in sorted(docs_dir.glob("*.md")):
                try:
                    head = path.read_text(encoding="utf-8")[:200]
                except (OSError, UnicodeDecodeError):
                    continue
                if "class: live" in head and path not in targets:
                    targets.append(path)

        # `\bN tools\b` where N is a digit cluster. Captures
        # "8 tools", "8 MCP tools", "all 8 MCP tools", etc.
        # Avoids false-matches on "test_tools" or "8 tools_dir" via
        # word boundaries.
        claim_re = re.compile(
            r"\b\d+\s+(?:MCP\s+|public\s+)?tools?\b",
            re.IGNORECASE,
        )
        # A claim wrapped in a canonical placeholder takes the form
        # `<!-- canonical:mcp_tool_count -->8<!-- /canonical --> tools`.
        # Strip wrapped claims before scanning so they don't trigger.
        canonical_wrap_re = re.compile(
            r"<!-- canonical:mcp_tool_count -->\d+<!-- /canonical -->\s*(?:MCP\s+|public\s+)?tools?",
            re.IGNORECASE,
        )
        # Exempt strings that aren't actually about Trinity's current
        # MCP tool count.
        EXEMPT_PATTERNS = (
            # `available_models` is a route() parameter, not a count.
            re.compile(r"\b\d+\s+command-line\s+tools?\b", re.IGNORECASE),
            # Historical-vs-current contrasts. The original v1 spec
            # proposed 3 tools; we ship more now. Lines that contrast
            # the historical proposal with the current state are not
            # drift — they're documenting the divergence.
            re.compile(
                r"original\s+spec|spec\s+wanted|originally\s+\d+|"
                r"wanted\s+\d+\s+tools?|shipped at \d+",
                re.IGNORECASE,
            ),
        )

        offenders: list[str] = []
        for path in targets:
            if not path.exists():
                continue
            rel = path.relative_to(repo).as_posix()
            text = path.read_text(encoding="utf-8")
            stripped = canonical_wrap_re.sub("[CANONICAL]", text)
            for idx, line in enumerate(stripped.splitlines(), start=1):
                m = claim_re.search(line)
                if not m:
                    continue
                if any(p.search(line) for p in EXEMPT_PATTERNS):
                    continue
                offenders.append(f"  {rel}:{idx}: {line.strip()[:140]}")

        if offenders:
            msg = [
                "Free-floating `<N> MCP tools` claims in active docs.",
                "Pin each one to the canonical source via the placeholder:",
                "  <!-- canonical:mcp_tool_count -->8<!-- /canonical --> tools",
                "Then `scripts/render_docs.py` keeps them in sync with",
                "`mcp_server.py`. CHANGELOG + sweep-patterns are exempt",
                "(retrospective surfaces); active docs are not.",
                "",
            ]
            msg.extend(offenders)
            raise AssertionError("\n".join(msg))


class TestNoStaleSeatTerminologyAsLiveNoun:
    """Tier 2 #6 (task #95) attempted to rename `member` → `seat` in
    user-facing copy. The rename was unwound (see `claude.md` glossary
    entry L556: *"the Tier 2 #6 \"rename to seat\" was unwound;
    \"seat\" was tried as a table metaphor but never caught on"*).

    Sweep iter #84 caught one straggler in `docs/spec-v1.5.md:494`
    ("seat-vs-chairman dispute resolution"). Same shape as
    [[principle_20_oldest_surface_drift]] — aspirational specs rarely
    re-read line-by-line, so a single noun usage survives multiple
    sweep passes.

    The guard fails on any `\\bseat\\b` or `\\bseats\\b` token in
    project docs, EXCEPT lines that explicitly document the unwind
    (must contain `unwound`, `rename to seat`, `member ↔ seat`,
    `member vs seat`, or `member`/`seat` together), and EXCEPT
    `included_seats` (the JSON field in v2-loop-constitution.md's
    synthetic SaaS-pricing example — that's domain terminology, not
    council terminology).
    """

    def test_no_stale_seat_in_docs(self):
        import re

        repo = Path(__file__).resolve().parent.parent
        targets = list(repo.glob("*.md")) + list((repo / "docs").rglob("*.md"))

        token_re = re.compile(r"\bseats?\b")

        # Lines that are explicit unwind-documentation get a pass.
        unwind_marker_re = re.compile(
            r"unwound|"
            r"rename to seat|"
            r"member.*↔.*seat|"
            r"seat.*↔.*member|"
            r"member.*vs.*seat|"
            r"seat.*vs.*member|"
            r"member.*seat|"
            r"seat.*member"
        )
        # JSON-field noun from synthetic SaaS-pricing example.
        included_seats_re = re.compile(r"included_seats")

        EXEMPT_FILES = {
            "tests/test_doc_count_consistency.py",
            "src/trinity_local/retired_names.py",
        }

        offenders: list[str] = []
        for path in targets:
            rel = path.relative_to(repo).as_posix()
            if rel in EXEMPT_FILES:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for idx, line in enumerate(text.splitlines(), start=1):
                if not token_re.search(line):
                    continue
                if unwind_marker_re.search(line):
                    continue
                if included_seats_re.search(line):
                    continue
                offenders.append(f"  {rel}:{idx}: {line.strip()[:140]}")

        if offenders:
            msg = [
                "Stale `seat`/`seats` references as live council nouns in docs.",
                "Tier 2 #6 (task #95) attempted `member` → `seat`; the rename",
                "was unwound (claude.md L556). Canonical term is `member`.",
                "Either rename to `member` or add the explicit unwind marker.",
                "",
            ]
            msg.extend(offenders)
            raise AssertionError("\n".join(msg))


class TestNoStaleTaskKindInCode:
    """Task #92 unified `task_kind`/`task_kinds` → `task_type`/`task_types`
    across the live codebase. Stragglers slipped through in comments and
    test method names (sweep iter #83 caught a stale comment in
    `doctor.py:612` and a stale test method name
    `test_falls_back_to_task_kind_when_routing_label_missing`).

    The guard fails on any `task_kind` or `task_kinds` token in `src/`
    or `tests/`, EXCEPT lines that are explicit migration notes (must
    contain `pre-Tier-1-#3 rename`, `task_kind` → `task_type`, or
    `task #92`). retired_names.py and this test file itself are exempt
    (registries / scanners need to mention the retired terms by name).
    """

    def test_no_stale_task_kind_in_src_and_tests(self):
        import re

        repo = Path(__file__).resolve().parent.parent
        targets: list[Path] = []
        for sub in ("src", "tests"):
            targets.extend((repo / sub).rglob("*.py"))

        # Tokenize: `task_kind` / `task_kinds` as standalone identifiers
        # (word-boundary), not as part of `task_kinds.py` historical CHANGELOG
        # mentions or `task_kinds → task_types` rename arrows.
        token_re = re.compile(r"\btask_kinds?\b")

        # Lines that are explicit migration documentation get a pass.
        migration_marker_re = re.compile(
            r"pre-Tier-1-#3 rename|"
            r"task #92|"
            r"task_kind\s*(→|->|->)\s*task_type|"
            r"`task_kind`\s*(→|->|->)\s*`task_type`"
        )

        # Files that are scanners / registries of retired terms.
        EXEMPT_FILES = {
            "tests/test_doc_count_consistency.py",
            "src/trinity_local/retired_names.py",
        }

        offenders: list[str] = []
        for path in targets:
            rel = path.relative_to(repo).as_posix()
            if rel in EXEMPT_FILES:
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            for idx, line in enumerate(text.splitlines(), start=1):
                if not token_re.search(line):
                    continue
                if migration_marker_re.search(line):
                    continue
                offenders.append(f"  {rel}:{idx}: {line.strip()[:140]}")

        if offenders:
            msg = [
                "Stale `task_kind`/`task_kinds` references in src/ or tests/.",
                "Task #92 unified these to `task_type`/`task_types`.",
                "Rename, or add the explicit migration marker if the line is",
                "documenting the rename itself.",
                "",
            ]
            msg.extend(offenders)
            raise AssertionError("\n".join(msg))


class TestClaudeMdLineCap:
    """Cap claude.md at <=250 lines (target ~200; 50-line buffer).

    Earned 2026-05-22 (v1.7.5 cleanup). Anthropic shipped official
    Auto-Dream in Claude Code with a 200-line MEMORY.md discipline
    (https://claudefa.st/blog/guide/mechanics/auto-dream). claude.md
    is Trinity's agent-facing entry point — the file every harness
    reads to know what the project IS. Without a cap it accreted to
    918 lines (status block + 21 principles + retirement log +
    glossary + state diagram + simplification log mixed together).

    The cleanup pass cut claude.md to ~200 lines, relocated history
    to docs/historical/ (principles.md, retirement-log.md,
    brand-evolution.md), and locked the discipline with this guard.
    Same shape as Principle #14 (every shipped feature gets a smoke
    regression guard within one tick): the cleanup IS the feature.

    Buffer: cap is 250 (50 above the 200 target). When a future
    edit needs to nudge the count higher, the right move is to
    relocate content to docs/historical/, not bump the cap.
    """

    CAP_LINES = 250

    def test_claude_md_stays_under_line_cap(self):
        repo = Path(__file__).resolve().parents[1]
        claude_md = repo / "claude.md"
        text = claude_md.read_text(encoding="utf-8")
        line_count = len(text.splitlines())
        assert line_count <= self.CAP_LINES, (
            f"claude.md has {line_count} lines (cap: {self.CAP_LINES}). "
            "Anthropic's Auto-Dream ships a 200-line MEMORY.md discipline "
            "(https://claudefa.st/blog/guide/mechanics/auto-dream); "
            "claude.md is the agent-facing entry point and follows the "
            "same convention. Relocate historical context to "
            "docs/historical/{principles,retirement-log,brand-evolution}.md "
            "rather than bumping the cap. If the new content is genuinely "
            "load-bearing for first-read agent comprehension, drill harder "
            "on what's already in the file first — almost everything in "
            "claude.md ends up referenced by tests/test_doc_count_consistency.py "
            "as a regression-guarded surface, so 'load-bearing' has a "
            "higher bar than 'feels useful to mention.'"
        )
