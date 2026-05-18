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

