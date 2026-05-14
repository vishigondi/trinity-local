# MCP Registry Submission Packets

> **Status:** ready-to-use marketing copy for task #114 (Launch-arc
> workstream 1 of 5: MCP-dropdown distribution). When you're ready to
> submit Trinity to each registry, paste the curated pitch text into
> the registry's contribution form. Submission URLs + exact field
> shapes change frequently — verify against each registry's current
> contribution guide before submitting.

## Why these registries

`trinity-local install-mcp` already wires Trinity into Claude Code,
Codex CLI, and Gemini CLI. The remaining funnel-widener is
**discoverability** — users who don't know Trinity exists never run
`install-mcp`. Each MCP-server registry below is a directory users
browse looking for tools. Being IN the dropdown beats being
technically perfect.

Order is rough leverage estimate (highest first): user base × overlap
with our power-user-with-multi-CLI persona × ease of approval.

---

## Shared one-paragraph description (canonical pitch)

The text below is the "lede paragraph" most registries ask for. Lift
this verbatim where the registry takes a free-text description.

> **Trinity Local** is the cross-provider memory layer the labs are
> commercially prevented from building. Switch models mid-conversation
> with `handoff` — Claude → Gemini → GPT, with full context preserved
> at each hop. Run councils across all three at once and score any
> candidate against your *actual* rejection signal. Your prompts and
> the cross-provider preference corpus stay in `~/.trinity/`, on your
> machine, never proxied. macOS today; rides on your existing
> Claude / Gemini / OpenAI subscriptions, no API billing.

Tag suite (use the registry's closest matches):

```
ai, llm, claude, gpt, gemini, multi-provider, council, evaluation,
benchmarks, routing, agent, local-first, privacy, mcp
```

Repo: `https://github.com/vishigondi/trinity-local`
Install one-liner: `pip install trinity-local && trinity-local install-mcp`

---

## Registry 1: Anthropic / Claude Desktop MCP catalog

**Audience:** Claude users who don't yet use other models. Highest
overlap with our power-user persona because the surface is exactly
where someone goes "I want Claude to be better at X."

**Submission URL:** TODO — check Anthropic's current docs site for
the official MCP-server submission process. The most recent shape was
a PR against an Anthropic-maintained registry repo.

**Tailored pitch** (lead with continuity, not council depth — Claude
users already trust Claude):

> Trinity adds a `handoff` MCP tool to Claude Desktop. Mid-conversation,
> the user can pivot to Gemini or GPT and the next model receives
> Claude's prior turns as context — no copy-paste. The wedge: only the
> layer above the labs can pull context across competitors' transcripts,
> and Trinity is open-source on your machine. Comes with the standard
> `run_council` / `record_outcome` / `search_prompts` tools, plus a
> personalized eval harness that benchmarks any provider against the
> user's empirical rejection signal.

**Required artifacts:**
- 1024×1024 icon (use `docs/icon.png` if present, or `me-card.png`)
- 60-second demo video (TODO — task #120)
- Short tagline: *"Continuity across Claude, GPT, and Gemini."*

---

## Registry 2: Cursor MCP marketplace

**Audience:** Devs who already pay for Cursor subscriptions, often
running Cursor + Claude Code in parallel. Strong overlap because
they're already polyharness users.

**Submission URL:** TODO — check Cursor docs (`cursor.sh/docs/mcp`).
Their marketplace may require approval rather than self-serve PR.

**Tailored pitch** (lead with "vendor-neutral memory" — Cursor users
are sensitive to lock-in concerns):

> Trinity gives Cursor users a vendor-neutral preference corpus that
> survives the next tool you try. Switch models mid-conversation,
> score Cursor's autocomplete model against your own rejection
> history, keep the preference signal in `~/.trinity/` regardless of
> which IDE wins the next 12 months. Rides on your existing
> subscriptions, no API billing.

**Required artifacts:**
- Same as Anthropic
- Cursor often wants a `cursor-mcp-config.json` snippet showing how
  the server registers — Trinity uses the standard stdio shape.

---

## Registry 3: Cline (autonomous coding agent)

**Audience:** Cline users tend to be experimental — they're already
running an autonomous agent locally and care about reproducibility +
local-first. Strong overlap with the Trinity persona.

**Submission URL:** TODO — Cline's MCP catalog lives in their
GitHub repo (`cline/cline`, look for `mcp-servers.json` or similar).
PR-based.

**Tailored pitch** (lead with the empirical-eval angle — Cline users
care about which model agent loops work best with):

> Trinity scores any model — Claude, GPT, Gemini, plus local Ollama /
> MLX models — against your actual rejection signal mined from prior
> transcripts. Per-rejection-type breakdown (REFRAME / COMPRESSION /
> REDIRECT / SHARPENING) tells you which model handles your kind of
> question, not someone else's synthetic benchmark suite. Plus the
> standard council + cross-provider handoff tools.

**Required artifacts:**
- `mcp-servers.json` entry showing transport=stdio, command, args
- Brief example of a `handoff` call from inside Cline

---

## Registry 4: Continue (open-source coding assistant)

**Audience:** Devs who chose Continue specifically for its
customizability + local-first stance. Strong philosophical alignment
with Trinity's privacy posture.

**Submission URL:** TODO — Continue's contribution flow goes through
their main repo or `continuedev/extensions`.

**Tailored pitch** (lead with privacy + the Preference Corpus Spec —
Continue users will appreciate the schema-standardization play):

> Trinity adds cross-provider councils + a handoff mechanism + a
> personalized eval harness to Continue. Notably: we ship a CC0
> [`Preference Corpus Spec`](https://github.com/vishigondi/trinity-local/blob/main/docs/PREFERENCE_CORPUS_SPEC.md)
> — a JSON-Schema-validated format for the supervision-signal layer
> that we'd like Continue to adopt too. The format already handles
> council outcomes, labeled rejections, and personalized eval sets.
> Standards outlive products; Trinity is what one looks like when
> someone outside the labs ships it.

**Required artifacts:**
- Link to PREFERENCE_CORPUS_SPEC.md
- The `schemas/*.schema.json` files

---

## Registry 5: Codex CLI ecosystem

**Audience:** OpenAI-CLI users who recently got MCP support. Less
overlap because they're often single-provider — but Trinity's pitch
is exactly to convert single-provider users into multi-provider users.

**Submission URL:** TODO — OpenAI's Codex CLI MCP integration list
location varies; check the `openai/codex` repo or the registry it
links to.

**Tailored pitch** (lead with the council comparison + the fact that
Codex is already a Trinity council member — flip them to the polyharness
side):

> Codex users already have a great coding model. Trinity lets them
> see when Claude or Gemini would do better on a specific task,
> without the copy-paste tax. The personal routing table builds
> automatically — after ~10 councils, Trinity tells you which model
> handles your kind of refactor / your kind of debug / your kind of
> architectural call. `install-mcp` registers Trinity in Codex CLI's
> MCP config alongside the existing OpenAI tools.

**Required artifacts:**
- Standard `~/.codex/config.toml` MCP server stanza (Trinity's
  `install-mcp` already writes this; the submission may want a
  reference example)

---

## Cross-registry checklist

Before submitting to any registry:

- [ ] Demo video (60 seconds, handoff variant; depends on task #120)
- [ ] Repo README updated with the registry-acceptance badge if they
      provide one
- [ ] License clearly displayed (MIT for Trinity itself; CC0 for the
      Preference Corpus Spec — many registries care about this distinction)
- [ ] Working install one-liner verified on a fresh macOS install
      (`pip install trinity-local && trinity-local install-mcp` followed
      by `trinity-local doctor`)
- [ ] CHANGELOG entry noting the registry inclusion (so future
      contributors know it's listed)

After each submission, drop the registry URL into the table below for
attribution + future reference:

| Registry | Submission URL | Status | Listed at |
|---|---|---|---|
| Claude Desktop | TODO | pending | — |
| Cursor | TODO | pending | — |
| Cline | TODO | pending | — |
| Continue | TODO | pending | — |
| Codex CLI | TODO | pending | — |

## Failure modes to guard against in registry copy

- **"Sounds like a wrapper."** Mitigate: every pitch leads with the
  *structural-asymmetry* angle — only Trinity has the cross-provider
  index because the labs are commercially prevented from sharing
  transcripts. Don't describe Trinity as "Claude + GPT + Gemini in one
  place." Describe it as "the layer above them that they can't build."
- **"Yet another MCP server."** Mitigate: lead with the unique tools
  (`handoff`, `eval-run`) that no other MCP server in the registry
  offers. Generic council/chat features go AFTER the unique ones.
- **"What's MCP?"** Mitigate: don't explain MCP in the pitch — the
  user is browsing an MCP registry, they already know. Save the
  explanation for the README.
- **"Privacy claim disbelief."** Mitigate: link to the install-mcp
  source. The MCP server is a stdio child of the user's harness;
  verify with `lsof`. Don't waste pitch real estate on privacy
  reassurance; let the source code do the talking.

## After submission: feedback loop

Each registry has its own approval cadence (Anthropic: days; Cline /
Continue: hours via PR review; Cursor: variable). Track inbound
issues or feature requests in the Trinity repo with the label
`from-registry:<name>`. The first round of registry feedback usually
exposes real-user confusion patterns — feed those back into the
README + the launchpad onboarding ribbon.
