# Launch copy — Trinity Local v1

> Drafts. Voice belongs to the user. Each block is one shippable artifact: thread, README hero
> rewrite, blog hook, 60s demo script. Send me-card PNG with every external post.
>
> Council ratification: `council_4f34cd1181d5bd08` (Codex won, high). Verdict: **conditional
> greenlight** with five edits applied. Major failure mode flagged: *"thread leads with
> comparison surface; reader pattern-matches to Poe / ChatHub before reaching the ledger
> moat in tweet 6."* Mitigation: ledger moved to tweets 1–2; opening verb changed from
> "asks" to "records disagreement as routing evidence"; HN title de-jargoned; verbatim
> lens example in tweet 5; CLI-auth setup caveat in tweet 8. Eval seed: *tweet 1 or 2 must
> name the local Routing JSON ledger as the primary product behavior, not multi-model
> comparison.*

## Twitter / X thread (10 tweets)

> Council `council_4f34cd1181d5bd08` (Codex won, high) reordered: ledger to tweets 1–2,
> recursive demo reframed, CLI-auth caveat added, verbatim lens in tweet 5.

**The ledger (1/10).** Trinity Local doesn't just ask Claude / Gemini / Codex the same
question. It records *the disagreement* as routing evidence — agreed claims, disagreed
claims with `why_matters`, winner, scores. The *click* you make today changes which model
gets trusted tomorrow.

**The mechanic (2/10).** Every council emits structured Routing JSON to
`~/.trinity/council_outcomes/<id>.json`. Not a chat log — a *labeled outcome*. After a
few, Trinity has built a personal map of which model wins your kind of question. Frontier
providers can't see that signal. You can.

**The wedge (3/10).** "Which model is best" is the wrong question. Models have *regions
of competence* that depend on your taste, your codebase, your trade-offs. Trinity captures
which region you actually live in. The data compounds.

**The privacy moat (4/10).** Your prompts never leave your machine. Trinity dispatches via
the Claude / Gemini / Codex CLIs you already have. Subsidized by the subscriptions you're
already paying for. No hosted controller. No per-call API billing.

**The /me lens (5/10).** After a few councils, Trinity distills paired tensions from where
you actually pushed back on a model. From my own ledger:

> *leading proxy signal as forecast* vs *official lagging metric as truth*
> failure of the first: paranoid pattern-matching, signals everywhere
> failure of the second: consensus follower, lag the move

Spans three topical clusters. Run `me-card` to render it as a 1200×630 PNG. [me-card image]

**Why now (6/10).** Trinity rides on consumer subscriptions — $20–200/mo flat tiers. No
per-call billing. The provider eats inference cost. Your preference signal stays in your
home directory. That's not a roadmap, that's the v1 cost model.

**The recursive demo (7/10).** I ran Trinity's launch council against its own readiness.
It exposed the failure mode (skill-not-in-pip-path), named the deterministic test
(`smoke_install.sh` asserts SKILL.md lands in `~/.claude/skills/trinity/`), drove the
commit. The full council outcome is in the repo: `council_d55953003bb29f9d.json`.

**Skill install (8/10).** `pip install trinity-local && trinity-local install-mcp` — drops
a `/trinity` skill into Claude Code globally. From a fresh terminal: type `/trinity` and
you're in. (Caveat: Trinity rides on the Claude / Gemini / Codex CLIs being authenticated
already. `trinity-local doctor` tells you which CLIs are missing.)

**The takeaway (9/10).** Trust calibration > cost optimization. The shareable artifact is
your `/me` lens, not council verdicts. Cross-pollinating lenses is how the network effect
compounds.

**CTA (10/10).** Trinity Local v1 ships open-source [date]. github.com/<repo>. If you
build with two or more model providers, run one council. Tell me what you learned. The
disagreed claims are the interesting part.

---

## README hero rewrite candidate

> *Three frontier models answered the same question. Two agreed. One substituted a cleaner
> frame than I asked for. I learned more from the disagreement than from any single answer.*
>
> Trinity Local turns that into a habit: ask all your AIs at once, see where they agree,
> see why when they don't, and walk away with a ledger of which model handles
> *your* questions best. Local-first. Rides your subscriptions. Prompts never upload.

---

## Hacker News title + opener

**Title:** *Show HN: Trinity Local — a local routing ledger for Claude, Gemini, and Codex*

**First comment (the unfair-advantage post):**

> I built this because "which AI is best" is the wrong question for me. Different models
> have different regions of competence — and which region matters depends on the taste of
> the person asking. Trinity asks all three, names the agreed claims, names the disagreed
> ones with `why_matters`, and persists the verdict locally as one labeled outcome.
>
> Two architectural commitments worth flagging:
>
> 1. **No hosted controller.** Trinity dispatches via the Claude / Gemini / Codex CLIs
>    you already have. The provider eats inference cost. Trinity rides on subscriptions
>    you're already paying for.
> 2. **Prompts never upload.** What CAN be opted in (default off) is anonymous categorical
>    routing labels — `task_type`, `winner`, `confidence`. Powers a future leaderboard for
>    the curious; works perfectly fine without it.
>
> The interesting bit isn't the comparison — it's that every council emits *Routing JSON*
> (winner / agreed_claims / disagreed_claims / routing_lesson / eval_seed). After a few
> councils, the chairman picker gets smarter at routing *your* flavor of question to the
> *right model for that flavor*. After more, you get a `/me` lens: paired tensions
> distilled from where you pushed back on a model. Pair-wise tensions like *"systems
> thinking that ships"* vs *"elegant theory left in the doc"* — each pole with its named
> failure mode.
>
> Open-source. MIT. Repo: <github.com/...>. Three commands to first council:
>
>     pip install trinity-local
>     trinity-local install-mcp
>     trinity-local council-launch --task "..."
>
> Or `/trinity` inside Claude Code (skill bundled with the wheel).

---

## 60-second demo script (for OBS)

```
0:00–0:08  CLI: pip install trinity-local && trinity-local install-mcp
           (text overlay: "rides Claude / Gemini / Codex subs you already have")
0:08–0:15  CLI: trinity-local doctor   (green checks scroll)
0:15–0:23  Switch to Claude Code. Type /trinity. Show first-council prompt.
0:23–0:38  Type real question (eg "Should I use SQLite or DuckDB for 50M-row analytics?")
           Three model headers stream answers in parallel.
0:38–0:48  Chairman synthesis card: agreed_claims (3 bullets), disagreed_claims
           (1 bullet + why_matters), winner card.
0:48–0:55  Click winner. Open ~/.trinity/council_outcomes/<id>.json — point at the
           Routing JSON: this is a labeled outcome.
0:55–1:00  Switch to launchpad. Personal Routing Table card visible.
           "Best model per task type, from your own councils."
           [End card: github + handle]
```

---

## Failure modes to guard against in launch copy

- **Sounds like wrapper.** Mitigate: every claim leads with the *Routing JSON moat*, not
  the comparison. The data you generate is the wedge, not the act of comparison itself.
- **Sounds like Karpathy LLM Council.** Mitigate: persistence (the ledger) is the
  differentiator. Karpathy's version is per-prompt. Trinity's version compounds.
- **"What's a council." Cognitive load.** Mitigate: lead the demo with one concrete
  question (DuckDB vs SQLite). Concrete > abstract.
- **Privacy claim disbelief.** Mitigate: link to `install-mcp` source. The MCP server
  is a stdio child of the user's harness; verify with `lsof`.
- **"Why not just ask Claude alone."** Answer: because you don't see what the other models
  saw differently, and you don't get the *why_matters* on disagreement. The disagreement
  is the interesting part.

---

## What I'm holding back from the launch

- v2 (Loop Constitution double-loop) is alpha. Mention briefly with a "what's next" link.
  Not the launch headline — v1 is the wedge.
- The personal `/me` lens demo on real data — only mention if I have ≥3 lenses to show.
  An empty `me.md` undersells.
- Anthropic Managed Agents tier — wait for pricing.
- Hosted leaderboard — opt-in upload not yet wired (v1.1).

---

## Send-with checklist

- [ ] me-card PNG attached (use `trinity-local me-card --out /tmp/me.png` to generate fresh)
- [ ] Repo URL is current (post-pubic-push)
- [ ] LICENSE link in footer of every artifact
- [ ] `trinity-local doctor` output recorded for the demo
- [ ] One real council outcome JSON quoted (not synthetic)
- [ ] Skill discoverability tested in a fresh Claude Code session
