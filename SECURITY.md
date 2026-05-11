# Security policy

Trinity Local is local-first by architecture. Most "security" in our threat model is
*privacy* — the user's transcripts and council outcomes should never leave their
machine without an explicit opt-in. If you find a bug that violates that commitment,
it's a P0 for us regardless of severity in the traditional security sense.

## Reporting a vulnerability

Email reports to **security@openclaw.dev** with subject `[Trinity Local] <short summary>`.

Include if applicable:
- Affected Trinity version (`trinity-local --version`)
- Repro steps or a minimal example
- What the user-visible impact is
- Suggested fix (optional)

We aim to respond within 5 business days. Coordinated disclosure preferred for issues
that could affect users in the wild.

## Threat model

What Trinity defends against (in priority order):

1. **Prompt content leaving the user's machine.** Highest priority. The
   `telemetry.py` module is the single audit surface for anything that crosses the
   wire. Council fan-out happens directly from the user's CLI subprocess to the
   provider's API — Trinity is not in the data path for those calls.

2. **Stale MCP servers overwriting state with old code.** `write_live_council_page()`
   is skip-if-exists by default; only `trinity-local portal-html` (CLI) passes
   `force=True`. Long-running MCP servers running pre-upgrade code can no longer
   clobber the on-disk launchpad with stale templates.

3. **Folder ownership.** Setup script (`setup.sh`) enforces `~/.trinity/` permissions
   to 700. Other processes on the same machine should not be able to read the user's
   council outcomes by default.

4. **CLI subprocess auth boundaries.** Trinity dispatches to `claude`, `codex`,
   `gemini` CLIs via `subprocess.Popen` with explicit argv. We do not pass user-provided
   strings as shell arguments without explicit quoting. The `subprocess_utils.py`
   module is the single audit surface for shell-execution patterns.

What Trinity does NOT defend against (out of scope):

- **Compromised provider CLIs.** If `claude` / `codex` / `gemini` is malicious, Trinity
  can't help — the user's prompt is already being sent to the wrong place by definition.
  Verify your provider CLI integrity via official package distribution channels.

- **Compromised user machine.** If a process on the user's machine has read access to
  `~/.trinity/`, it has read access to everything Trinity knows. We don't encrypt at
  rest (the `lens` is meaningless without the user's logged-in OS session).

- **Network adversaries on the path between the user and the provider's API.** That's
  the provider's TLS configuration's problem, not Trinity's.

## Disclosure timeline

For confirmed vulnerabilities affecting Trinity Local's privacy commitments:

| Day | Step |
|---|---|
| 0 | Report received, acknowledged within 5 business days |
| 7 | Reproducer + scope confirmed |
| 14 | Fix in PR (private branch if needed) |
| 30 | Public patch release + CVE if applicable |
| 90 | Full public disclosure (if requested by reporter) |

For non-security bugs (functional issues, UX bugs, etc.), open a regular GitHub issue.

## Hall of thanks

Security researchers who help us hold the privacy line will be acknowledged here (with
permission). Trinity's wedge is *"your prompts and the models' answers never leave your
machine"* — defending that commitment is core to the project.
