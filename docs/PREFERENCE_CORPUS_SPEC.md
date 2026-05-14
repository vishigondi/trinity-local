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
