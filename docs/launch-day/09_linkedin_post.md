---
class: live
---

A few months ago I caught myself doing the same thing for the fourth time in an hour: pasting a long context block from Claude Code into a ChatGPT tab, then into a Gemini tab, then triangulating which answer to trust. I have three subscriptions and I was still acting as the integration layer between them. That stopped feeling like a workflow problem and started feeling like a structural one.

The structural part is the interesting bit for anyone building agents right now. Anthropic isn't allowed to recommend ChatGPT. OpenAI isn't allowed to recommend Claude. Google can't read either of their transcripts. The three labs you trust most are commercially prevented from helping you use a competitor — which means cross-provider continuity, cross-provider memory, cross-provider routing can only ship from a layer that sits *above* the labs. Not as a research opinion. As a contract law observation.

That's what Trinity Local is. Two transcript sources feed it: the CLI sessions already on your machine (`~/.claude/`, `~/.codex/`, `~/.gemini/`) plus your claude.ai / chatgpt.com / gemini.google.com web chats, captured locally by a Chrome extension via Chrome's Native Messaging (no upload — the extension spawns a local capture host on demand). It builds a personal preference corpus locally and lets you hand off a conversation mid-thread to a different provider — `trinity-local handoff gemini` and Gemini picks up exactly where Claude left off, adds what it can see that Claude can't (your Drive, your Calendar), then you hand off to GPT. Same thread, three perspectives, one continuous session. No copy-paste, no re-context.

For agent builders specifically: every council emits structured Routing JSON — winner, agreed_claims, disagreed_claims with why_matters, routing_lesson — persisted to a folder you own. After enough councils a personal routing table emerges ("for code_refactor prompts, Claude wins 7.8/10 on your taste"). It doesn't replace LangGraph or CrewAI or your eval stack. It sits above the model choice and learns which lab to ask for which flavor of question. The corpus is JSON-Schema-validated and CC0 so Aider, Cline, Continue, or your own MCP server can interop with the same shape.

Local, open-source (MIT), free. Rides the subscriptions you already pay for — no hosted controller, no per-call billing, prompts never upload. If you build agents and you've hit the cross-provider gap, I'd love to know what breaks first: github.com/vishigondi/trinity-local
