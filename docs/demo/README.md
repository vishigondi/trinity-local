---
class: live
---

# Demo asset directory (#120)

Holds the asciinema casts and supporting assets for Trinity's launch-arc
demos. asciinema (over MP4) because:

- **Pure CLI captures** — handoff/council demos are terminal-driven; no
  GUI footage needed. asciinema records the actual character stream,
  not a video of the screen.
- **Click-to-copy** — viewers can pause and copy commands out of the
  embedded player. MP4s lose that.
- **Tiny file size** — a 60s session is ~30-100KB vs ~10MB for MP4 at
  the same resolution. Embeds fast even on slow connections.
- **README-friendly** — `<script src="https://asciinema.org/a/<ID>.js">`
  embed renders inline in GitHub's README. MP4s require external
  hosting (Cloudflare, YouTube) with their own UX baggage.

## Files

| File | Purpose | Embed surface |
|---|---|---|
| `handoff_60s.cast` | The PRIMARY 60-second demo. Claude → handoff → Antigravity continuation. | `README.md` hero block + `docs/launch.md` L286 |
| `council_60s.cast` | Alternate 60-second demo. Three-model parallel + chairman synthesis. | `docs/launch.md` L255 |

Neither is checked in pre-recording — see "Recording" below.

## Recording

Use `scripts/record_handoff_demo.sh` (task #120). The script:

1. Validates `asciinema` + `trinity-local` are installed
2. Warns if the prompt index has <5 entries (handoff falls back to a
   thin-context message that doesn't tell the demo story)
3. Records to `docs/demo/handoff_60s.cast`

```bash
# Interactive — recommended for the actual launch-day cast
scripts/record_handoff_demo.sh

# Scripted — runs handoff and exits as soon as it returns. Smaller
# file but no setup/intro space.
SCRIPTED=1 scripts/record_handoff_demo.sh
```

After recording, upload + embed:

```bash
# Upload returns an asciinema.org URL like https://asciinema.org/a/abcdef
asciinema upload docs/demo/handoff_60s.cast

# Drop the ID into:
#   README.md            hero block
#   docs/launch.md L286  launch-arc artifacts section
#   docs/index.html      (if the static site has a hero embed slot)
```

## Why this directory exists

The 60-second handoff demo is the **structurally non-refutable** marketing
beat (no provider can build it themselves — they can't see competitors'
transcripts). It's the wedge that lands "wait, how did Gemini KNOW that?"
on first view.

Until now, the demo lived as a *script* in `docs/launch.md` — recorded
nowhere, embedded nowhere. This directory + the recording helper close the
"shoot it" + "host it" gates of the launch arc.
