# Trust mode + audit log

> Council-ratified by `council_c18f739a0234aa58` (2026-05-16). Phase 6
> of the three-tier architecture.

Trinity's trust substrate is what makes "we respect your choices" a
credible claim instead of a marketing line. Two coupled mechanisms:

  1. **~/.trinity/trust.toml** — declarative grants. What Trinity is
     allowed to do without prompting.
  2. **~/.trinity/audit.log** — every operation Trinity ran. Append-
     only JSONL. You can `grep` it.

## The 30-second model

By default, every Trinity operation either prompts (skill tier: the
prompt is Claude Code's permission dialog; pip tier: a stderr y/N) or
silently audit-logs. You can pre-grant operations you trust:

```toml
# ~/.trinity/trust.toml
schema_version = 1

[trust]
default = "ask"

[trust.operations]
embed_batch = "trust"       # always proceed
launch_council = "ask"      # always prompt
```

Bootstrap a starter file with:

```bash
trinity-local trust-init
```

This writes a default `~/.trinity/trust.toml` with all commented-out
examples. Edit to taste; Trinity reads it on every operation.

## Resolution order

Most specific wins:

1. `--dangerously-trust-all` flag OR `TRINITY_DANGEROUSLY_TRUST_ALL=1`
   env var → "trust" for everything
2. `[trust.rules]` exact `tier.operation` override (e.g.
   `"extension.launch_council" = "ask"`)
3. `[trust.operations]` per-operation grant
4. `[trust.tiers]` per-tier default
5. `[trust]` global default (defaults to "ask")

Inspect the resolved level for a specific operation:

```bash
trinity-local trust-show --operation embed_batch --tier pip
# {"resolved": {"operation": "embed_batch", "tier": "pip", "level": "trust"}, ...}
```

## --dangerously-trust-all

Matches Claude Code's convention. When set (flag or env var):

- All operations proceed without prompting.
- The audit log STILL fires. Bypassing prompts is not bypassing
  accountability — that's the whole point of the substrate.

The flag is loud on purpose. Trinity prints a stderr warning on every
top-level invocation when trust-all is active. If you don't see the
warning, the flag isn't taking effect.

## Audit log

Every Trinity operation appends one JSONL line to
`~/.trinity/audit.log`:

```json
{"ts":"2026-05-16T20:23:42","script":"embed","operation":"embed_batch","tier":"skill","trust_mode":"trust:toml:operation","outcome":"ok","args":{"n_texts":3}}
```

Read it via:

```bash
trinity-local audit-show --last 20       # human-readable
trinity-local audit-show --last 50 --json   # machine-readable
```

The audit log is append-only. Atomic single-write per operation
(POSIX O_APPEND on a regular file). If the log can't be written —
disk full, permissions wrong — Trinity emits a loud stderr warning
on first failure so you notice immediately. Silent gaps in the
audit log would defeat the trust substrate.

## Cross-tier propagation

When the Chrome extension's native host spawns `trinity-local` as a
subprocess, the audit log needs to record the originating tier
(`extension`), not the subprocess tier (`pip`). The native host sets
three env vars before spawning:

```
TRINITY_ORIGIN_TIER=extension
TRINITY_ORIGIN_ACTION=launch-council
TRINITY_INVOCATION_ID=<uuid>
```

Trinity's `audit_log()` reads these and stamps the record
accordingly. So when you grep `audit.log` for extension-originated
operations, you see them as such regardless of where they ran.

## What v1.0 ships

- `~/.trinity/trust.toml` schema (`schema_version = 1`)
- `~/.trinity/audit.log` JSONL append + atomic single-write
- `--dangerously-trust-all` flag + env var
- `trinity-local trust-init / trust-show / audit-show` CLI surface
- Cross-tier `TRINITY_ORIGIN_TIER` env propagation
- Loud-fail on audit-write errors (stderr warning, rate-limited)

## What v1.1 ships

Per the council verdict (`council_c18f739a0234aa58`):

- Automatic audit rotation (v1.0 warns above 50 MB in `doctor`)
- Visible trust indicators in launchpad header + extension popup
- `--tier`, `--operation`, `--outcome` filter flags on audit-show
- Global `--dangerously-trust-all` flag on `trinity-local` (v1.0
  has only the env var)

## See also

- `docs/three-tier-architecture.md` — full architecture spec
- `skills/trinity/schemas/trust.schema.json` — JSON Schema for trust.toml
- `docs/launch_councils/council_c18f739a0234aa58.json` — Phase 6
  council outcome
