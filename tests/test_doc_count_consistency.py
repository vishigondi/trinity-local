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

import re
from pathlib import Path

import pytest


REPO = Path(__file__).resolve().parents[1]
CLAUDE_MD = REPO / "claude.md"
PRODUCT_SPEC = REPO / "docs" / "product-spec.md"


def _extract(path: Path, pattern: str) -> str | None:
    """Return the first regex group match in `path`, or None if not found."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return None
    m = re.search(pattern, text)
    return m.group(1) if m else None


class TestTestCountConsistency:
    """Three known surfaces pin the pytest count. They must agree."""

    def test_three_surfaces_agree(self):
        # Surface A: claude.md Status block — "N tests passing"
        status_count = _extract(
            CLAUDE_MD,
            r"(\d+) tests passing",
        )
        # Surface B: claude.md Verified status — "pytest -q — **N passed**"
        verified_count = _extract(
            CLAUDE_MD,
            r"pytest -q.{0,5}\*\*(\d+) passed\*\*",
        )
        # Surface C: docs/product-spec.md item 11 — "Test suite: N passing"
        spec_count = _extract(
            PRODUCT_SPEC,
            r"Test suite:\s*(\d+) passing",
        )

        # All three must be present (locating-the-marker is itself a guard
        # against someone re-titling a section and breaking the pin point).
        assert status_count, "claude.md Status block lost the 'N tests passing' marker"
        assert verified_count, "claude.md Verified status lost the 'pytest -q — **N passed**' marker"
        assert spec_count, "product-spec.md item 11 lost the 'Test suite: N passing' marker"

        # All three numbers must agree.
        counts = {
            "claude.md status": status_count,
            "claude.md verified": verified_count,
            "product-spec item 11": spec_count,
        }
        unique = set(counts.values())
        assert len(unique) == 1, (
            f"Test count drifted across surfaces: {counts}. "
            f"Principle #20: when you bump the test count, bump it in "
            f"ALL three places in the same commit. Single-source-of-truth "
            f"would be cleaner long-term."
        )


class TestSmokeSurfaceCountConsistency:
    """The smoke-surface count claim appears in claude.md status + the
    product-spec. Same shape; same regression guard."""

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


class TestInstallSmokeTracksMcpTools:
    """Regression guard for the install-smoke MCP tool list. The
    install-smoke script (`scripts/smoke_install.sh`) verifies that
    the wheel-installed MCP server exposes the canonical tool set —
    that's the v1.5 Week 5 gate ratified by council_5699d0e62cf965d0.

    But the script hardcodes the canonical list. Today at T-1 (May
    14) the install smoke ran for the first time since the morning's
    11th MCP tool landed (`get_eval_summary`, plus `handoff` earlier)
    — and it FAILED because the hardcoded set was stale. Anyone
    running the wheel-install path would have hit a red gate that
    didn't reflect a real problem.

    This guard ensures the smoke script's canonical set MATCHES the
    one in test_mcp_tools.py — the single source of truth for "what
    tools MUST exist after a fresh pip install." Updating either
    requires updating both, or the suite fails loudly with a
    drift-shaped error message.
    """

    def test_smoke_install_canonical_set_matches_test_suite_canonical(self):
        smoke_script = REPO / "scripts" / "smoke_install.sh"
        try:
            text = smoke_script.read_text(encoding="utf-8")
        except OSError:
            return  # script absent — different launch path, not this guard's concern
        # Pull names out of the `canonical = { ... }` python set literal
        # inside the heredoc'd python check. Match anything that looks
        # like a quoted MCP tool identifier inside the canonical block.
        m = re.search(r"canonical\s*=\s*\{([^}]+)\}", text)
        assert m, (
            "scripts/smoke_install.sh lost its `canonical = {...}` "
            "set anchor — the install-smoke MCP check can't drift-"
            "monitor without it. Restore the set definition."
        )
        smoke_tools = set(re.findall(r'"([a-z_]+)"', m.group(1)))
        # Compare to the test_mcp_tools canonical (single source of truth)
        mcp_tests = REPO / "tests" / "test_mcp_tools.py"
        try:
            test_text = mcp_tests.read_text(encoding="utf-8")
        except OSError:
            return
        # The test file's canonical set lives in test_canonical_tools_present
        # as `assert names == {...}` literal. Scan the function body
        # for the asserted set; anchor on the function name so a future
        # restructure that splits this elsewhere still finds it.
        func_start = test_text.find("def test_canonical_tools_present")
        assert func_start > 0, (
            "tests/test_mcp_tools.py lost the test_canonical_tools_present "
            "function — the smoke parity guard anchors on it."
        )
        # Find the next "assert names == {...}" after the function def.
        func_slice = test_text[func_start:func_start + 3000]
        test_match = re.search(r"assert\s+names\s*==\s*\{([^}]+)\}", func_slice)
        assert test_match, (
            "test_canonical_tools_present body lost its `assert names == {...}` "
            "anchor. If the test was restructured, update the smoke parity guard."
        )
        test_tools = set(re.findall(r'"([a-z_]+)"', test_match.group(1)))
        # Symmetric difference: drift in EITHER direction = bug
        smoke_only = smoke_tools - test_tools
        test_only = test_tools - smoke_tools
        assert not smoke_only and not test_only, (
            f"MCP canonical-tool set drift between smoke_install.sh "
            f"and test_mcp_tools.py:\n"
            f"  in smoke_install.sh only: {sorted(smoke_only)}\n"
            f"  in test_mcp_tools.py only: {sorted(test_only)}\n"
            f"Both surfaces must agree — they're parallel gates for "
            f"the same '11 canonical tools must survive a fresh pip "
            f"install' invariant. Fix in one, fix in the other."
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
