---
class: aspirational
---

# Pending product questions

Open product-direction decisions that came up during consistency-sweep
ticks but were deferred (not coded). Each entry: what the question is,
when it surfaced, the tradeoff, and what would trigger revisit. Append
new entries at the top. Move resolved ones to a "Resolved" section at
the bottom with the actual decision.

Doc class is `aspirational` because each entry describes a possible
future change — not the current state of the codebase.

---

## Q1 — Lens-aware rating UX

**Surfaced:** 2026-05-21 tick 100. User pushback on a `record_outcome`
prompt: *"The whole thesis of Trinity is that it's easier to evaluate
responses than to generate them, especially using my lens. fix Trinity"*
+ *"The goal is to close the loop on my principles so they continuously
improve."*

**Decision:** Defer (user picked "revisit when it bites" in tick 101).
Keep drift sweeps going; surface a real fix when the user actually
hits the friction during normal use, not from a speculative rebuild.

**The gap (plain):** Trinity builds a lens from your past
conversations (the tensions you care about, the corrections you
make). The chairman uses this lens when picking a winner. But when
**you** rate the council afterward, the rating tool just asks "which
model wins?" — it doesn't show you the lens. You're being asked to
**evaluate** without the framing you built. That violates the wedge.

**The fix (sketch, smallest viable first):**

- **Option A — agent-side workaround:** the agent loads council JSON +
  lens.md manually, renders disagreed_claims against lens tensions,
  surfaces. Limited because raw member responses still aren't shown.
- **Option B — new MCP tool** `present_for_rating(council_run_id)` that
  returns a lens-augmented payload (responses + lens-aligned framing).
  Agent calls it, renders, collects verdict, calls `record_outcome`.
- **Option C — CLI command** `trinity-local rate-guided` that prints the
  same payload to stdout + prompts inline. Avoids new MCP tool.
- **Option D — launchpad rating page rewrite** that surfaces raw
  responses with lens-aware highlighting. Largest surface area.

None include the propagation-back-to-lens step yet (verdict → lens
refinement). The dream pipeline rebuild via cortex extraction is the
existing indirect path (verdict → picks.json → next dream rebuild may
reweight lens), but it's not direct.

**Trigger to revisit:** User encounters the friction in normal use —
i.e., they want to rate a real council and find the prompt doesn't
help them evaluate. At that point: the friction itself shapes the
fix better than speculation.

**Memory:** `rating_loop_product_gap.md` in `~/.claude/projects/.../memory/`.

---

(no resolved questions yet)
