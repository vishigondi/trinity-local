"""Loop Constitution v2 — skill-graduation double-loop.

Council `council_5fbf909119830643` (Codex won, high) ratified the substrate.
Council `council_7a770b8b78b6bd4e` (Codex won, high) ratified the compressed
double-loop shape with two modifications:

1. State history is STRUCTURED records, not raw failure strings.
2. Re-verify gate is HASH-based, not boolean — sha256(pre_cull) vs sha256(post_cull).

Modules:
- frame.py: outer loop. One chairman call emits inversions + eval_seed.
- run.py:   inner loop state machine. execute → verify → cull → re-verify → commit.
- verify_web.py: Autobrowse subprocess wrapper for web-task verify; chairman-rubric fallback.
- cli.py:   `trinity-loop frame|run|reframe`.
"""

from __future__ import annotations
