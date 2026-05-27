---
class: live
---

# Demo asset directory

Holds asciinema casts and supporting assets for Trinity's launch-arc
demos. asciinema (over MP4) because:

- **Pure CLI captures** — council demos are terminal-driven; no GUI
  footage needed. asciinema records the actual character stream, not a
  video of the screen.
- **Click-to-copy** — viewers can pause and copy commands out of the
  embedded player. MP4s lose that.
- **Tiny file size** — a 60s session is ~30-100KB vs ~10MB for MP4 at
  the same resolution. Embeds fast even on slow connections.
- **README-friendly** — `<script src="https://asciinema.org/a/<ID>.js">`
  embed renders inline in GitHub's README. MP4s require external
  hosting (Cloudflare, YouTube) with their own UX baggage.

## Retirement note (2026-05-26)

This directory was originally scoped around the `handoff_60s.cast` — a
60-second demo of `trinity-local handoff <provider>` showing
Claude → Antigravity continuation with cross-provider data carry. The
`handoff` CLI + MCP tool were retired 2026-05-26 after 0 production
usage events (see `src/trinity_local/retired_names.py`). Cross-provider
continuity now flows via MCP Resources — agents read
`trinity://memories/lens.md` at session handshake, so the same
"Gemini knows what Claude said" beat lands without an explicit verb.

## Files

| File | Purpose | Embed surface |
|---|---|---|
| `council_60s.cast` | 60-second council demo — three-model parallel + chairman synthesis emitting Routing JSON. | `README.md` hero block + `docs/launch.md` |
| `continuity_60s.cast` | Optional companion — start a council in Claude Code, switch to Antigravity, show the lens reading through MCP Resources. Same "they shouldn't know that" beat as the original handoff demo, fewer moving parts. | `README.md` hero block (alternative to council) |

Neither is checked in pre-recording — see "Recording" below.

## Recording

`scripts/record_handoff_demo.sh` (the helper task #120 originally
scoped) survives as the recording harness; only the inner `trinity-local`
invocation needs to swap. Edit the script to run `council-launch` (or a
chained `ask` + provider switch for the continuity cut) instead of the
retired `handoff` verb. The pre-flight checks (asciinema installed,
prompt index has ≥5 entries, output directory exists) remain useful.

```bash
# Interactive — recommended for the actual launch-day cast.
# Edit the inner verb first; the harness only validates and records.
scripts/record_handoff_demo.sh

# Scripted variant — runs the verb and exits as soon as it returns.
SCRIPTED=1 scripts/record_handoff_demo.sh
```

After recording, upload + embed:

```bash
# Upload returns an asciinema.org URL like https://asciinema.org/a/abcdef
asciinema upload docs/demo/council_60s.cast

# Drop the ID into:
#   README.md            hero block
#   docs/launch.md       launch-arc artifacts section
#   docs/index.html      (if the static site has a hero embed slot)
```

## Why this directory exists

The 60-second cross-provider continuity story is the **structurally
non-refutable** marketing beat (no single provider can build it
themselves — they can't see competitors' transcripts). It's the wedge
that lands "wait, how did Gemini KNOW that?" on first view.

Until the assets are recorded, the demo lives as a *script* in
`docs/launch.md` — recorded nowhere, embedded nowhere. This directory
plus the recording helper close the "shoot it" + "host it" gates of
the launch arc.
