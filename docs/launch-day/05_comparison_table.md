---
class: live
---

| | Trinity Local | promptfoo / Claude evals | OpenRouter | LangChain | LiteLLM | Continue.dev | Karpathy LLM Council |
|---|---|---|---|---|---|---|---|
| Data source | Your own prompts | Test fixtures you write | Your prompt per call | Code you wire up | Your prompt per call | IDE buffer + retrieval | Your prompt, not stored |
| Cost basis | Your CLI subscriptions | Per-call API | Per-call API + markup | Per-call API | Per-call API (proxy) | Per-call API or local | Per-call API |
| Output | Routing JSON + lens.md | Pass/fail per case | One model's answer | Whatever you build | One model's answer | Code completion / chat | Three answers + summary |
| Privacy | Local-only; no upload | Local fixtures, hosted calls | Prompts transit their proxy | Depends on your build | Prompts transit the proxy | Depends on provider | Prompts hit each provider |
| Persistence | Council outcomes on disk | Eval run history | None across calls | You implement it | Optional logging DB | Per-workspace history | None |
| Learning | Personal routing table + lens | Re-run the suite | Static price/latency rules | None built in | None built in | None across providers | None |
| Cross-provider continuity | handoff carries context across models | n/a | Same prompt to a model | You build the glue | Same prompt to a model | Single model per session | n/a |
| Open-source | MIT, local binary | MIT (promptfoo) | Closed proxy service | MIT framework | MIT proxy | Apache-2.0 client | Gist, no maintenance |
