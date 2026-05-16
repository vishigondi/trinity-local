# HN First-Comment FAQ — anticipated top 5 objections

Voice: technical, concrete, file paths and numbers over claims. Vishi pastes one or more of these as replies inline.

## 1. "Isn't this just LangChain / LiteLLM / OpenRouter with extra steps?"

No — those are dispatch layers; Trinity is a *preference corpus* layer that happens to dispatch. OpenRouter proxies prompts through their servers and charges per call. LiteLLM normalizes API shape. LangChain orchestrates a single graph. None of them persist cross-model preference signal. Trinity writes structured Routing JSON to `~/.trinity/council_outcomes/*.json` after every council — `winner`, `agreed_claims`, `disagreed_claims` with `why_matters`, `routing_lesson`. After ~10 councils, `compute_personal_routing_table()` (in `council_feedback.py`) aggregates this on-demand by `task_type`. The wedge is the ledger frontier providers structurally can't see; dispatch is the side effect. Also: Trinity rides your existing CLI subscriptions, no per-call billing, prompts never leave the machine.

## 2. "How is this different from Anthropic's Dreaming?"

Dreaming consolidates sessions inside Anthropic's runtime — same lab. Trinity consolidates sessions across `~/.claude/`, `~/.codex/`, `~/.gemini/` — three labs that are commercially prevented from reading each other. The mechanic is structurally similar (episodes → extracted patterns per question-kind, trust-scored), but the corpus is what makes it work. Our consolidation lives in `cortex.py` + `cortex_geometry.py` (Weiszfeld geometric-median centroid, 6-component trust score including mean-cosine-to-median coherence). The flagship reads structure, not language. Dreaming makes Claude smarter at being Claude; Trinity learns *which model wins which kind of YOUR question* — only the layer above the labs can do that.

## 3. "You're sending prompts to 3 providers instead of 1 — that's strictly worse for privacy."

Two responses. First: you're already sending prompts to all three — that's why you have three subscriptions. Trinity reads transcripts already on disk; it doesn't manufacture new exposure. Second: Trinity has no hosted controller, no proxy, no telemetry endpoint at runtime. `main()` pins `HF_HUB_OFFLINE=1` + `TRANSFORMERS_OFFLINE=1` at startup (see `src/trinity_local/main.py`). Dispatch goes through the same CLIs you'd use anyway (`claude`, `codex`, `gemini` subprocesses). The MCP server is a stdio child of your harness — `lsof -i | grep LISTEN` finds nothing. Opt-in telemetry (default OFF) ships only categorical labels (`task_type`, `winner`, `confidence`), never content. Break this and the brand dies; the architectural commitment is in `claude.md`.

## 4. "How do you actually evaluate this? `eval-run` on a 3-item smoke is thin."

Agreed N is small today — that's what shipped end-to-end, not the depth claim. The harness itself is the differentiator: `eval-build` mines `(prompt, rejected_response, rejection_type)` triples from your actual transcripts via the Stage 0 turn-pair gap extractor (REFRAME / COMPRESSION / REDIRECT / SHARPENING, with validators in `me/turn_pairs.py` — e.g. COMPRESSION requires user_text ≤ model_text/10). `eval-run --target <provider>` scores any model against YOUR empirical rejections using `lens.md` as judge rubric. Real run on Vishi's corpus (2026-05-15): claude N=20 → 0.66 aggregate, with COMPRESSION at 0.50 (real over-engineering weakness) vs SHARPENING 0.93 / REDIRECT 0.80. Codex N=4 → 0.74. Gemini blocked by API outage during the launch window. The point isn't current N; it's that no provider can build this benchmark — they can't see cross-provider rejection signal. N grows with corpus.

## 5. "Why should I trust the chairman synthesis? Sounds like LLM-judges-LLM hallucination."

Because the chairman's job is constrained, not generative. The prompt enforces a structured JSON contract (`council_runtime.py` renders, `council_schema.py` validates): `agreed_claims` must be statements all members made, `disagreed_claims` must cite which providers took which side with `why_matters` explaining the stake. Parse-success rate logged to `~/.trinity/analytics/routing_label_events.jsonl`. Chairman reads `core.md` first (your distilled identity) so synthesis is grounded in your taste, not the model's defaults. `consolidate --audit` runs an independent second flagship to catch drift — loud-fails on stderr. User-veto via `mark_pick_wrong` halves effective trust per click, persists across consolidations. The chairman is a constrained synthesizer with audit + override mechanisms, not an oracle.
