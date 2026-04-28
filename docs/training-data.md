# Training Data Plan

This project should not train on full transcripts by default. The local router
only needs compact windows plus outcome signals.

Important scope note:

- This is not only a coding router.
- It must support general cowork use cases:
  - planning
  - research
  - coding
  - debugging
  - operations
  - writing
  - verification
  - agentic desktop / MCP-heavy workflows

The long-term target is a provider-neutral cowork router. Coding is only one
high-signal early domain.

## Sources

### Claude Code

Local path:

- `~/.claude/projects/<project>/<session>.jsonl`

Useful fields already present:

- `cwd`
- `version`
- `gitBranch`
- top-level `timestamp`
- assistant `message.model`
- tool calls and tool results
- usage fields such as:
  - `input_tokens`
  - `output_tokens`
  - `cache_read_input_tokens`
  - `cache_creation_input_tokens`

Notes:

- Claude has the richest local corpus here.
- We should track the exact `message.model`, not just "claude".
- We should also track the CLI build from top-level `version`.

### Cowork / Claude Desktop Agent Mode

Local path:

- `~/Library/Application Support/Claude/local-agent-mode-sessions/...`

Existing ingester:

- `src/trinity_local/ingest.py` (`parse_cowork_session`, `iter_cowork_sessions`)

Useful fields already present:

- metadata JSON `model`
- `createdAt`
- `lastActivityAt`
- `cwd`
- `title`
- `slashCommands`
- `remoteMcpServersConfig`
- conversation `audit.jsonl` using near-Claude-Code message shape

Notes:

- This is worth keeping as a first-class source, not folding into Claude Code.
- `slashCommands` and MCP server names are unusually strong context signals.
- Those fields help predict whether a task is research-heavy, automation-heavy,
  or likely to benefit from a different provider.
- Cowork-style sessions are likely where the product scales, especially as
  Codex and Gemini ship comparable agent-mode products.

### Codex CLI

Local path:

- `~/.codex/sessions/YYYY/MM/DD/rollout-*.jsonl`

Useful fields already present:

- `session_meta.id`
- `session_meta.cwd`
- `session_meta.cli_version`
- `turn_context.model`
- `response_item` messages
- `reasoning`
- function calls and outputs

Auxiliary path:

- `~/.codex/history.jsonl`

Notes:

- `history.jsonl` is a good lightweight session index.
- Rollout files are the real training source.
- Track both `turn_context.model` and `session_meta.cli_version`.

### Gemini CLI

Local paths:

- `~/.gemini/tmp/openclaw/chats/session-*.json`
- `~/.gemini/tmp/openclaw/logs.json`

Useful fields already present in chat files:

- `sessionId`
- `startTime`
- `lastUpdated`
- per-message `type`
- per-message `model`
- `tokens`
- `toolCalls`
- shell command outputs
- file write / diff metadata

Notes:

- The chat JSON is the real source.
- `logs.json` is only a lightweight user-message log.
- We need a dedicated Gemini CLI ingester; the existing `tt` Gemini ingester is
  for Takeout exports, not this local format.

## Required Version Tracking

Routing quality changes when providers silently change models. Every training
example must carry a model descriptor with:

- `provider`
- `raw_model_id`
- `normalized_model_id`
- `model_family`
- `model_variant`
- `model_snapshot`
- `cli_name`
- `cli_version`
- `source_format_version`

Examples:

- Claude:
  - `provider=claude`
  - `raw_model_id=claude-opus-4-7`
  - `cli_name=claude`
  - `cli_version=2.1.116`
- Codex:
  - `provider=codex`
  - `raw_model_id=gpt-5.4`
  - `cli_name=codex`
  - `cli_version=0.121.0`
- Gemini:
  - `provider=gemini`
  - `raw_model_id=gemini-2.5-flash`
  - `cli_name=gemini`
  - `cli_version` should be added when we find or infer a stable source for it
- Cowork:
  - `provider=cowork`
  - `raw_model_id=<metadata.model>`
  - `cli_name=claude-desktop-agent-mode`
  - `cli_version` may be absent in current local files and should remain nullable

## Four Layers

Freeze these layers before finalizing extractors.

### 1. RawSession

This is the source-native artifact reference:

- source
- native id
- source path
- source format
- source format version
- provider session kind

Do not put model-learning assumptions here.

### 2. SessionFeatures

This is the derived metadata boundary:

- exact model descriptor
- cwd / project hint
- git branch / dirty worktree when available
- slash commands
- MCP servers
- first prompt / planner text / final text
- tool summaries
- outcome signals
- attachment / shell / web / MCP usage flags

This layer should be stable even if the training objective changes.

Do not overfit this layer to coding-only signals. It must remain useful for:

- code tasks
- research tasks
- planning tasks
- desktop-agent tasks
- mixed-mode cowork sessions

### 3. TaskLink

This is the cross-provider “same task” linkage:

- task cluster id
- previous provider
- next provider
- switched yes/no
- switch reason
- time to switch
- router suggestion
- suggestion accepted
- council invoked

This is the most important missing layer in `tt` for TRINITY.

### 4. RoutingExample

This is the supervised training row:

- transcript window
- task link
- chosen provider
- chosen model
- label
- confidence
- alternatives
- reasons

## Compact Window Format

Each transcript should be reduced to:

- `first_user_text`
- `planner_text`
- `final_text`
- `cwd`
- `project_hint`
- `task_kind_hint`
- `role_hint`
- tool summary counts
- outcome signals
- exact model descriptor

This is enough for a local router and avoids full-transcript training by
default.

`task_kind_hint` should not be code-centric. Start with:

- `coding`
- `debugging`
- `research`
- `planning`
- `writing`
- `operations`
- `verification`
- `cowork_general`

## Weak Labels

The local router should learn from behavior, not annotation.

Strong signals:

- user switched from one provider to another on the same task
- user accepted a reroute suggestion
- provider produced edits / commands and the task ended
- provider produced repeated failed tool calls and the user left
- provider required unusual slash commands or MCP servers to succeed
- cowork sessions with specific MCP usage patterns later get rerouted elsewhere

Useful weak signals:

- many tool errors
- long session with no edits
- high token spend with no obvious progress
- user asks the same question again in another tool
- council comparison shows another provider won

## Recommended First Labels

Use simple labels first:

- `good_fit`
- `bad_fit`
- `reroute_to_claude`
- `reroute_to_codex`
- `reroute_to_gemini`
- `needs_council`

For cowork-scale use, also allow:

- `reroute_to_cowork_agent`
- `stay_in_cowork_agent`
- `needs_agent_mode`
- `needs_lightweight_chat_mode`

Avoid training directly on raw free-form judgments at the beginning.

## Implementation Order

1. ~~Add a Gemini CLI ingester modeled after the existing Claude/Codex ingesters.~~ ✅
2. ~~Keep `cowork` as a separate source and preserve `slash_commands` + `mcp_servers`.~~ ✅
3. ~~Emit `SessionFeatures` and `TaskLink` records before `RoutingExample`.~~ ✅
4. ~~Build weak labels from cross-tool behavior.~~ ✅
5. ~~Build shared embedding layer (nomic-embed-text-v1.5, sentence-transformers).~~ ✅
6. ~~Mine hard examples via embedding-based cross-provider matching.~~ ✅
7. ~~Build 5-metric evaluation suite for hard examples.~~ ✅
8. ~~Integrate k-NN advisory into watcher (advisory only, heuristic fallback).~~ ✅
9. ~~Production analytics for advisory layer.~~ ✅
10. Train a small local ranker — **next**, when eval metrics stabilize.
11. Add LoRA or a richer local encoder only after the labels and compact windows
   are stable.

## Current Status

### Embedding Backend

- Model: `nomic-ai/nomic-embed-text-v1.5` (sentence-transformers, MPS accelerated)
- Dimensions: 512 (Matryoshka)
- Fallback: hash-projected TF-IDF (zero dependencies)
- Cache: persistent JSONL at `~/.trinity/cache/embeddings.jsonl`

### Hard Example Corpus

- 59,447 sessions scanned
- 1,026 hard examples mined (986 rerouted via embedding similarity, 40 needs_council)
- 1,031 cross-provider pairs detected
- Note: only 1 session in the entire corpus had tool errors — error-based mining
  is nearly useless, embedding-based cross-provider matching is the real signal

### Evaluation Results (k-NN vs heuristic on hard examples)

| Metric | Heuristic | k-NN |
|--------|-----------|------|
| Reroute recall | 0% | **38.7%** |
| needs_council precision | N/A | **98.1%** |
| needs_council recall | 0% | **98.4%** |
| Top-2 provider accuracy | N/A | **99.5%** |
| NN label agreement | N/A | **96.6%** |

### Production Analytics

Key product metrics tracked:
- `act_rate` — what % of suggestions are acted on
- `switch_after_acted_rate` — of acted-on suggestions, how many later switched
  (the key metric — if this drops over time, the product is getting smarter)
- Evidence spam detection (avg/max/p95 evidence lines per recommendation)
- Threshold brittleness across task kinds and provider pairs

## Product Direction

The schema should assume a future where:

- Claude Cowork is one provider
- Codex launches a cowork competitor
- Gemini launches a cowork competitor

So the router should learn:

- which provider is best
- which product mode is best
- which interaction style is best

Examples:

- quick answer vs agent mode
- research pass vs implementation pass
- single-provider route vs council escalation
