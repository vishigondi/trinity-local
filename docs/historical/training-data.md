---
class: historical
---

# Training Data

> **Sunset notice (2026-05-11):** the trained-coordinator path Phase 9
> describes is **sunset** per [`claude.md`](../claude.md). Trinity v1.5
> ships the routing-coordinator architecture via *context engineering*
> (flagship reads cortex picks + lens) instead of training a tiny adapter.
> The Phase 9 spec is preserved as architectural-decision history;
> reopens only if v1.5 hits a quality ceiling on real user data. See
> [`spec-v2.md`](spec-v2.md) for the full sunset header.

This file's content has moved to [`scale-plan.md` § Phase 9](./scale-plan.md#phase-9--tiny-coordinator-the-learned-router) — specifically §9.2 *Training data shape* and §9.3 *Training objective*.

The Phase 9 spec (sunset) defines:

- `RouterExample` — one row per Trinity council, sourced from each user's local outcomes.
- The three-loss training objective (mode classification, provider ranking, confidence calibration).
- Why training stays per-user (a tiny adapter) instead of pooling across users.

There is no separate training data spec to maintain here.
