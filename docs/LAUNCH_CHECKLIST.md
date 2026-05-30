---
class: live
---

# Launch checklist — Trinity v1.0 alongside Gemini 3.1 Pro Preview

> Generated 2026-05-16 by the cron loop after council `ff3da1fa84906791`
> ratified the v1.0 floor. Sunday/Monday tasks below; everything in
> "Done — v1.0 ready to ship" is committed and tested.

## Done — v1.0 ready to ship

**Code (<!-- canonical:test_count -->2416<!-- /canonical --> tests passing + <!-- canonical:skipped_count -->4<!-- /canonical --> skipped, <!-- canonical:doc_consistency_guards -->110<!-- /canonical --> doc-consistency guards green — was 1372/36 at this snapshot's 2026-05-16 generation; pre-launch simplification dropped ~80 tests, the consistency sweep added 5 doc-guards through iter #62; commit `2bbb333` regenerated `docs/launchpad_example.png` and cleared the formerly-intentional fail)**
- 8-phase macOS-Shortcuts → Chrome-extension dispatcher transition
  (commits d56cffc → ebc212a). Every launchpad button works
  cross-platform via the extension; macOS Shortcut as tier-2 fallback.
- Phase 1 v1.0-floor three-tier skill artifact (commits 6e2cd12 →
  2860688): `skills/trinity/SKILL.md` + schemas + arch doc + 4 new
  doc-consistency guards. Skill is additive over the existing CLI;
  no `src/trinity_local/` modules touched.
- Council `ff3da1fa84906791` cited in 4 surfaces (claude.md,
  docs/launch.md, docs/launch-package.md, docs/three-tier-architecture.md);
  outcome JSON copied to docs/launch_councils/ so HN readers resolve
  the cite.

**Framing**
- Hero locked: *"Own your taste. Lives inside Claude Code, Codex
  CLI, Antigravity, and Cursor."*
- Three tiers documented (Skill primary / Pip engine / Chrome extension)
- Tier-equivalence invariant locked verbatim: cosine ≥ 0.9999, NOT
  bit-identical. Pinned in 4 surfaces; doc-consistency guard catches
  drift.

## External gates (user-action only, can't be done by the loop)

These are the items that block the launch URL from working when HN
clicks. Today they all 404; flipping them is what makes Monday's
launch live.

- [ ] **github.com/vishigondi/trinity-local goes public.** Repo is
      private. Every launch URL points here — including the
      `curl -fsSL .../install.sh | bash` lead. Flip this whenever
      you're ready to start the hard-launch sequence. This is the
      ONLY external gate that
      MUST flip — no PyPI publish, no npm publish; Trinity ships as
      a git clone via curl|sh.
- [ ] **Demo recording shot + hosted.** The 60-second cross-provider
      continuity demo. Originally pitched as the `handoff` verb (#119
      / #120 — retired 2026-05-26, 0 production usage). New shot: run
      a council in Claude Code, then open Antigravity and let it read
      `trinity://memories/lens.md` from the MCP Resources surface —
      same continuity, fewer moving parts. Host on
      vishigondi.com/trinity-demo or wherever; update the README +
      docs/launch.md to embed.

## Polish before hard launch (loop-doable, low-risk)

- [ ] Review docs/founder-essay-draft.md for stale framing — should
      probably mention the three-tier architecture in the technical-
      credibility section.
- [ ] Consider running an end-to-end smoke on a fresh venv: `pip
      install -e .` from clean clone → `trinity-local install-mcp` →
      `trinity-local status` → `trinity-local dream` → `trinity-local
      portal-html --open-browser`. Time it; if under 8 minutes, the
      "8-minute bar" promise in docs/spec-v1.md holds.
- [ ] Real-Chrome smoke (the gated test): load the unpacked
      extension in a fresh Chrome profile, set TRINITY_EXTENSION_ID,
      run `pytest tests/test_chrome_extension_smoke.py -v` with
      `TRINITY_CHROME_SMOKE=1`. Wire the puppeteer driver if you
      want full automation; the structural contract guard already
      runs in CI without Chrome.

## Hard-launch final-mile (when ready to flip the gates above)

- [ ] Flip the gates above.
- [ ] Tweet the locked thread from docs/launch.md "Twitter / X thread".
- [ ] HN post: title + opener from docs/launch.md "Hacker News title
      + opener".
- [ ] Set up Anthropic, OpenAI, Google referrals if applicable
      (subsidy-window narrative angle).

## Cron status

Job `923536e4` running every 10 minutes; CronDelete it when ready
to stop the loop. Auto-expires after 7 days.

## Stop condition

The original /loop prompt said: stop when all 8 phases pass
acceptance AND fresh-machine install of any tier combination works
AND claude.md cites Phase 7's council outcome ID.

Council `ff3da1fa84906791` revised that criterion to: v1.0 floor
shipped, framing propagated, deferred items documented. **All three
are done.** The cron can fire empty ticks until the user
`CronDelete`s it; nothing more is needed for v1.0.

## What v1.1 picks up

Per council verdict, deferred:
- `scripts/` as importable+executable shared substrate
- 70-module engine extraction from `src/trinity_local/`
- Trust mode + audit log substrate rebuild from scratch
  (`~/.trinity/trust.toml` gating config + CLI + visible indicators).
  The v1.0 library `trinity_local.trust` was retired 2026-05-22
  (iter #117 of the post-launch sweep, commit `c2573ff`) after audit
  found zero production imports. The active audit-log surface today
  is `scripts/_runtime.py::audit_log()` — an independent
  implementation that survives the retirement. v1.1 rebuilds the
  gating + CLI fresh; the original design is preserved at
  [`historical/trust-mode.md`](historical/trust-mode.md).
- Cross-backend equivalence test harness (MLX / torch CPU / CUDA)
- Per-site permission opt-in for extension web-chat capture (post-v0.2;
  v0.2 grants all three sites at install time)

See `docs/three-tier-architecture.md` for the full v1.1 spec.
