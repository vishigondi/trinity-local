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

(no open questions)

---

## Resolved

### Q1 — Lens-aware rating UX (resolved 2026-05-22)

**Surfaced:** 2026-05-21 tick 100. User pushback on a `record_outcome`
prompt: *"The whole thesis of Trinity is that it's easier to evaluate
responses than to generate them, especially using my lens. fix Trinity"*
+ *"The goal is to close the loop on my principles so they continuously
improve."*

**Decision (2026-05-22):** Full retirement, not rebuild. The user
directive *"user doesn't have to provide ratings. that's another
task for them. use the lens governed council selections"* resolved
the question structurally — none of the four options (agent-side
workaround, `present_for_rating` MCP tool, `rate-guided` CLI,
launchpad rewrite) was the right answer. The rating UX itself was
the friction.

**What shipped (task #134):** CLI `council-rate` retired, MCP
`record_outcome` retired (one day earlier), `user_winner` deprecated
with wipe-on-read migration on `outcome.metadata.user_verdict`.
Council pages now carry a "Lens pick" badge sourced from
`routing_label.winner`. Refinement prompts under each council
capture "what should it have been instead" inline — the signal
embedded in the user's natural flow, not a tax.

**Memory:** `rating_loop_product_gap.md` in `~/.claude/projects/.../memory/`
marked RESOLVED 2026-05-22.
