# Preference Corpus Spec (v1)

> **Status:** v1 — locked May 14, 2026. Other tools (Aider, Cline, Continue, custom MCP servers) can adopt this schema to interoperate with Trinity's preference-corpus surface. The format is JSON-Schema-validated; canonical schemas live under [`schemas/`](../schemas/).

## Why this exists

Every AI-coding tool now persists state somewhere: chat history, file context, latency stats. None of them share a schema. The user can't take their preferences from Cursor to Continue, from Aider to Cline, from one tool's "memory" to another's. The schemas are accidentally divergent, not deliberately different.

Trinity's `~/.trinity/` directory ships a small, opinionated schema for **the supervision-signal a cross-provider tool generates**. Other tools that want to interoperate — surface cross-tool preferences, contribute to a shared evidence ledger, or just read each other's state — can adopt this schema directly.

The five-minute pitch:

- **One council outcome JSON per multi-model run.** Chairman synthesis with structured Routing JSON.
- **One labeled rejection per turn-pair gap.** The user's empirical taste, mined offline.
- **One eval-set JSON per benchmark replay.** Score any new model against the user's actual prompts + rejections.

If three tools adopt this, the format becomes a category boundary instead of one product's internal state.

## Schemas

| File | Schema | Purpose |
|------|--------|---------|
| `~/.trinity/council_outcomes/council_<hash>.json` | [`council_outcome.schema.json`](../schemas/council_outcome.schema.json) | One multi-model run + chairman synthesis + user verdict. The canonical supervision signal. |
| `~/.trinity/me/rejections.jsonl` | [`rejection_signal.schema.json`](../schemas/rejection_signal.schema.json) | Labeled (prompt, response, rejection_type) triples mined from turn-pair gaps. |
| `~/.trinity/evals/eval_<hash>.json` | [`eval_set.schema.json`](../schemas/eval_set.schema.json) | Personalized eval suite assembled from rejections + cross-provider pairs. |

The schemas use JSON Schema Draft 2020-12. Each `$id` is `https://trinity-local.dev/schemas/v1/<name>.schema.json`. v1 is structural — backward-compatible additions don't bump the version, removals would.

## The four implicit-rejection signal types

The schema's most opinionated choice: four labels for *how* a user rejected a model's response. Other tools may use different label sets, but the four below are the ones Trinity mines.

| Type | What the user did | Validator (in `me/turn_pairs.py`) |
|------|-------------------|-----------------------------------|
| `REFRAME` | Substituted a different frame entirely | Substituted frame must persist into next user turn |
| `COMPRESSION` | Wanted the answer shorter | User text word count ≤ model text / 10 |
| `REDIRECT` | Wanted a structurally different output | Model text was multi-part (numbered/bulleted/multi-sentence) |
| `SHARPENING` | Wanted more precision on same topic | User text shares ≥2 keywords with model text |

These are the categories the chairman labels with; an alternative tool can use the same four labels (recommended for interop) or define its own and translate at the boundary.

## What this is NOT

- **Not a chat-history format.** That's MessageList / OpenAI-message schema territory; many tools already do that well.
- **Not a model-routing format.** Trinity has internal schemas (picks.json, routing.json) for that — keeping them out of v1 so the surface area is small and the interop story is sharp.
- **Not a backwards-compatibility commitment beyond v1.** v2 may rename fields once the spec has been pressure-tested by other adopters; for now it's locked while Trinity is the only consumer.

## Example payloads

Each canonical example below is a minimum-valid payload for its schema
— it carries every required field and none of the optional ones. The
example files live under [`schemas/examples/`](../schemas/examples/)
and the spec's CI validates each against its schema, so these stay
in sync with the JSON Schema files themselves.

The fastest sanity check after pulling the spec into your tool:

```python
import json, jsonschema
schema = json.load(open("schemas/council_outcome.schema.json"))
example = json.load(open("schemas/examples/council_outcome.example.json"))
jsonschema.validate(example, schema)  # raises ValidationError if drift
```

### `council_outcome.example.json`

```json
{
  "council_run_id": "council_a1b2c3d4e5f60718",
  "bundle_id": "bundle_demo",
  "created_at": "2026-05-14T12:00:00Z",
  "primary_provider": "claude",
  "member_results": [
    {"provider": "claude", "output_text": "answer A"},
    {"provider": "gemini", "output_text": "answer B"}
  ],
  "synthesis_output": "Both answers converge on X. Claude's framing is sharper.",
  "routing_label": {
    "task_type": "explanation",
    "winner": "claude",
    "agreed_claims": ["Both note that X follows from Y."],
    "disagreed_claims": [
      {
        "claim": "Whether to mention edge case Z",
        "why_matters": "Z applies to half the user's actual use cases",
        "providers": ["claude"]
      }
    ]
  }
}
```

### `eval_set.example.json`

```json
{
  "eval_id": "eval_a1b2c3d4e5f6",
  "built_at": "2026-05-14T12:00:00Z",
  "source": "rejections",
  "stats": {
    "items": 1,
    "by_rejection_type": {"COMPRESSION": 1},
    "by_basin": {"b00": 1}
  },
  "items": [
    {
      "eval_item_id": "ei_a1b2c3d4e5f6",
      "prompt": "Explain X concisely.",
      "rejection_type": "COMPRESSION",
      "rejected_response": "A long lecture about X with five subsections.",
      "user_substitute": "tldr",
      "rubric_signal": "user wanted shorter",
      "basin_id": "b00",
      "source": "rejections",
      "source_id": "r_001",
      "prompt_id": "pn_42",
      "provider_of_rejected_response": "claude"
    }
  ]
}
```

### `rejection_signal.example.jsonl`

One record per line — `rejections.jsonl` is line-delimited because
the lens-build pipeline appends incrementally.

```jsonl
{"id": "r_001", "type": "COMPRESSION", "model_quote": "A long lecture about X with five subsections.", "user_substitute": "tldr", "why_signal": "user explicitly asked for shorter", "prompt_id": "pn_42", "basin": "b00", "next_user_turn": ""}
```

## Adopting this in your tool

1. Validate writes against the schemas (`pip install jsonschema`; load the schema; `jsonschema.validate(your_dict, schema)`).
2. Drop the JSONL into `~/.trinity/me/rejections.jsonl` or `~/.trinity/council_outcomes/*.json` — Trinity reads incrementally and will pick the new data up.
3. Use the `provider_of_rejected_response` field on eval items to attribute which tool/model produced the rejected response, so cross-tool eval results stay traceable.
4. If your tool emits a different rejection-type label set, translate at the boundary into one of the four canonical types — or contribute a v1.1 PR adding yours.

## Reference implementation

Trinity Local itself is the reference. The canonical writers:

- `src/trinity_local/council_runtime.py::save_council_outcome` — produces `council_outcomes/*.json`
- `src/trinity_local/me/turn_pairs.py::save_rejections` — produces `rejections.jsonl`
- `src/trinity_local/evals/builder.py::save_eval_set` — produces `evals/*.json`

Schemas are validated against real on-disk data in `tests/test_preference_corpus_schemas.py`. If a Trinity write doesn't match its schema, that test fails — so the schema can't drift from the reference implementation silently.

## License

The schemas are CC0 — adopt them, fork them, embed them in commercial products. The point is interop, not protection.
