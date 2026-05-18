# Simplification log

Working memory for the simplify-app loop. Each entry records one
audit decision so the loop doesn't reaudit the same surface and so
the user can review proposals in the morning.

Verdict shapes:
- **KILL** — surface deleted outright, no replacement (audience too
  small / overlaps fully with another surface)
- **COLLAPSE-INTO-<other>** — surface folded into another existing
  surface (audience kept, but name eliminated)
- **KEEP** — surface earns its place; do not reaudit
- **PROPOSAL** — call is judgmental or blast radius is large;
  needs user decision before action

## Audited

- 2026-05-18: `trinity-local doctor` → **COLLAPSE-INTO-status + install.sh inline**.
  Tiny post-install audience (errors already name the actual problem);
  install.sh ran it as the install-verification step; MCP rate_action
  uses the same checks via internal helpers. Decision: kill the
  user-facing command, inline checks into install.sh's final verdict
  line, absorb the diagnostic header into `trinity-local status`.
  Internal helpers (provider detection, dir writability, MCP dep
  presence, verdict_rate, macOS Shortcut check) stay as importable
  Python — they're called by install.sh, status, and the MCP server.
  **Status: pending execution by the loop.** The decision was made
  during the conversation that seeded this log; the actual rename
  hasn't shipped yet. The loop should treat this as PROPOSAL until
  the rename ships, then convert to COLLAPSE.

## PROPOSAL: `search_prompts` MCP tool

**Verdict**: KILL (escalated to PROPOSAL — load-bearing per claude.md)

**Why**: The audit agent argued `search_prompts` is a convenience wrapper
over CLI `replay-history` and the lens file — agents with filesystem
access (Claude Code) can use the CLI, and replay is user-driven anyway
(agent suggests, user chooses). 6 files / ~80 lines blast radius.

**Counter**: claude.md explicitly says "Removing any of `route`,
`run_council`, `record_outcome`, `search_prompts` breaks a meaningful
surface." That's a load-bearing architectural commitment, not casual
surface area. It also exists for MCP-only environments where agents
have no shell — the audit dismissed this as speculation but didn't
disprove it.

**Blast radius**: ~6 files, ~80 lines. Sweep: mcp_server.py, claude.md
mentions (×3), spec docs, test_mcp_tools.py, test_doc_count_consistency.py
tool-count expectation.

**Risk**: Killing a v1.0 canonical MCP tool on launch day (T-0) without
data on actual agent call patterns. Tool count claim (11) becomes 10
across all surfaces that pin it.

**Decision**: PENDING USER. My recommendation: defer to v1.1 — collect
agent-call telemetry from the first week of users, then revisit. If
`search_prompts` call count is <5% of total MCP calls, kill it then.
The cost of carrying it for one extra week is one tool-count claim;
the cost of killing it incorrectly is breaking MCP-only agent flows.

**Audited**: 2026-05-18, iteration 1.

- 2026-05-18 (iter 2): README Quickstart `Or use the CLI directly:` +
  `Or, from inside Claude Code:` alternative-path blocks →
  **COLLAPSE-INTO-Help section**. The `/trinity` skill is the primary
  entry point and teaches the full CLI after the first council; the
  Help section already documents every command; offering CLI examples
  as an "Or" alternative in the Quickstart is premature cognitive
  loading for v1.0. Files touched: 1 (README.md, -15 lines).
  Tests: 1402 pass, 4 skip (unchanged).

- 2026-05-18 (iter 3): `--json` flag on `eval-build`, `eval-run`,
  `eval-show` → **KILL**. Zero documented usage (no README/SKILL.md
  mention beyond their own argparse help), zero tests exercise the
  True branch (5 test arg constructors had `as_json=False` but none
  asserted the JSON-output path), zero downstream consumers. The
  result files are already JSON on disk at `~/.trinity/evals/...`;
  power users can `cat | jq`. Pre-launch dead branch removal.
  Files touched: 2 (eval.py -22 lines, test_evals_runner.py -5 stale
  args). Tests: 1402 pass, 4 skip (unchanged). Shipped: e5947a0.

- 2026-05-18 (iter 4): user-facing error strings in `me_builder.py`
  referencing removed command `me-build` → **KILL stale refs, replace
  with `lens-build`** (renamed per task #91 but error strings missed
  the sweep). 4 user-facing strings (lines 327/354/367/389) told the
  user to re-run a command that no longer exists; 9 docstring/comment
  refs swept for hygiene; line 327 also gained the canonical
  `trinity-local` prefix (matches the form in commands/me.py). The
  audit agent first picked SKILL.md doctor refs but that was wrong
  (doctor is still a PROPOSAL, not yet removed); pivoted to this
  category 10 catch. Files touched: 1 (me_builder.py, 13 string
  replacements + 1 prefix addition). Tests: 1402 pass, 4 skip.

- 2026-05-18 (iter 5): stale `~/.trinity/memory/` paths + `me-build`
  command name in module docstrings → **KILL stale refs**. The
  memory/ → prompts/ rename (task #90) and me-build → lens-build
  rename (task #91) both missed two docstrings. Specifically:
  vocabulary.py:3 said `~/.trinity/memory/prompt_nodes.jsonl`;
  incremental_ingest.py:4 said `~/.trinity/memory/cursors.json` +
  line 7 said `me-build`. Confirmed canonical via state_paths.py:196
  (`path = state_dir() / "prompts"`); `memory_dir()` is now just a
  back-compat function name aliasing the prompts/ directory. Files
  touched: 2 (vocabulary.py, incremental_ingest.py — 3 string edits
  total). Tests: 1402 pass, 4 skip.

- 2026-05-18 (iter 6): `commands/research.py` argparse registration
  (6 user-facing CLI commands: `replay`, `embed`, `rank`, `hard`,
  `hardeval`, `analytics`) → **KILL**. claude.md explicitly tags these
  "off the live product path — research pipeline only"; they're not
  in README, SKILL.md, or launchpad. Zero outside importers (the file
  was only consumed by main.py registration). The internal
  `research/*` package stays — tests still pass because they import
  directly from `research/replay.py`, `research/embeddings.py`, etc.
  Net: 6 commands disappear from `trinity-local --help`. Files
  touched: 3 (deleted commands/research.py 431 LOC, main.py -1 line,
  claude.md -1 table row). Tests: 1402 pass, 4 skip (unchanged).

