---
class: live
---

# Training Data

This file's content has moved to [`scale-plan.md` § Phase 9](./scale-plan.md#phase-9--tiny-coordinator-the-learned-router) — specifically §9.2 *Training data shape* and §9.3 *Training objective*.

The Phase 9 spec defines:

- `RouterExample` — one row per Trinity council, sourced from each user's local outcomes.
- The three-loss training objective (mode classification, provider ranking, confidence calibration).
- Why training stays per-user (a tiny adapter) instead of pooling across users.

There is no separate training data spec to maintain here.
