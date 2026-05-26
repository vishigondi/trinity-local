---
class: live
---

# Trinity Local — Pricing FAQ

The five questions every HN reader is going to ask before they install. Honest answers, no hand-waving.

---

## 1. Is it free?

Yes. Trinity Local v1.7 is **free forever**, MIT-licensed, and open source on GitHub. There's no account to create, no email gate, no "free tier with paid upgrade" trick where the useful features sit behind a paywall. The council mechanic, the cortex, `dream`, the lens, the personal routing table, the launchpad, all <!-- canonical:mcp_tool_count -->8<!-- /canonical --> MCP tools — everything described in the README ships in the free build and stays in the free build.

## 2. What's the catch?

Trinity rides **your existing subscriptions**. It dispatches to the `claude`, `codex`, and `agy` CLIs you already have authenticated on your machine — so when Trinity runs a council, the inference cost falls on Anthropic / OpenAI / Google, not on you and not on us. No hosted controller, no per-call API billing, no proxy in the middle. You need at least one provider CLI working; the catch is that Trinity is only as capable as the subs you already pay for.

## 3. What does Trinity actually cost to use?

**$0 above what you already pay.** A council = three CLI calls + one chairman synthesis call, all charged to your existing Claude Pro / ChatGPT Plus / Gemini Advanced subscriptions. Trinity itself never touches a paid API endpoint — the architectural commitment in `claude.md` is explicit: "subsidized consumer credits as cost basis." If you have one sub, Trinity uses one model. If you have three, it runs the full council. Local resource cost: ~62 MB resident while the MCP server is connected.

## 4. What's Pro / Teams?

Roadmap placeholders, no pricing committed. **Trinity Pro** (post-launch, no committed version) is sketched as a hosted-capability layer for individuals who want optional features that genuinely need a server (cross-device sync of `~/.trinity/`, hosted aggregation dashboards). **Trinity for Teams** (later still) is the enterprise track — same local-first architecture, but with VPC-friendly deployment, shared lens governance, and audit logging for regulated industries naming "agent lock-in" as a procurement concern. Both are visible on the roadmap so the monetization story isn't a surprise later; the v1.7 ship (May 2026) included neither and neither changes the free-forever commitment for individuals.

## 5. How does Vishi make money?

Honestly: not yet, and not from v1.7 (the ship at hand). v1.0 was the data pipe and the distribution play — get Trinity into the MCP dropdowns of Claude Desktop, Codex, Cursor, Cline, Continue while consumer-AI is still in the land-grab phase. Revenue, when it arrives, comes from optional Pro-tier hosted capabilities and the Teams track — never from individual users of the local build, never from a hosted API tier that would destroy both the cost basis and the privacy story. If you read the v1.5 spec, the architectural commitment "no hosted controller, no per-call billing" is load-bearing — it's not a bullet point that gets quietly dropped at Series A.
