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
        import subprocess
        try:
            result = subprocess.run(
                ["trinity-local", "--help"],
                capture_output=True, text=True, check=False,
            )
        except FileNotFoundError:
            # CLI not on PATH (CI env without venv activation) — return
            # empty set and let the test skip via early-return.
            return set()
        if result.returncode != 0:
            return set()
        # The argparse help output shows the subparser choices inside
        # `{cmd1,cmd2,...}`. Pull the first occurrence (the
        # top-level subparser).
        m = re.search(r"\{([a-z][^}]+)\}", result.stdout)
        if not m:
            return set()
        return {c.strip() for c in m.group(1).split(",") if c.strip()}

    def test_subcommands_in_launch_docs_resolve(self):
        real = self._real_subcommands()
        if not real:
            return  # CLI not on PATH in this env — skip gracefully
        launch_docs = [
            REPO / "README.md",
            REPO / "docs" / "launch.md",
            REPO / "docs" / "launch-package.md",
            REPO / "docs" / "MCP_REGISTRY_SUBMISSIONS.md",
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

    Guard: assert the screenshot isn't grossly older than the source-
    tree files that drive what the launchpad renders. If
    launchpad_template.py or launchpad_data.py was edited more recently
    than the screenshot, the screenshot is likely stale. Threshold is
    generous (3 days) to avoid forcing re-render on every UI tweak —
    only catches true drift, not normal edit churn.
    """

    def test_launchpad_example_not_grossly_stale(self):
        screenshot = REPO / "docs" / "launchpad_example.png"
        if not screenshot.exists():
            return  # not yet generated — guard is a no-op
        source_drivers = [
            REPO / "src" / "trinity_local" / "launchpad_template.py",
            REPO / "src" / "trinity_local" / "launchpad_data.py",
        ]
        screenshot_mtime = screenshot.stat().st_mtime
        STALE_THRESHOLD_DAYS = 3
        stale_drivers: list[tuple[str, float]] = []
        for path in source_drivers:
            if not path.exists():
                continue
            src_mtime = path.stat().st_mtime
            age_days = (src_mtime - screenshot_mtime) / 86400
            if age_days > STALE_THRESHOLD_DAYS:
                stale_drivers.append((path.name, age_days))
        assert not stale_drivers, (
            f"docs/launchpad_example.png is grossly stale relative to "
            f"the launchpad source files: {stale_drivers}. The README + "
            f"launch-package link to this screenshot as the canonical "
            f"'what Trinity looks like.' Regenerate via "
            f"`trinity-local portal-html && trinity-local serve & "
            f"python scripts/browser_smoke.py && cp docs/smoke/1-"
            f"launchpad.png docs/launchpad_example.png`."
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
