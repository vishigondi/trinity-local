"""Registry of retired CLI names, MCP tools, modules, and concepts.

Gap B from docs/architectural-gaps.md: retirement is narrated everywhere
(claude.md, MIGRATION.md, simplification_log.md, inline comments) but
declared nowhere. Iter #68/#69 caught MIGRATION.md internally
contradicting itself ("keep `shortcut-install`" vs "the CLI no longer
exists") 20 lines apart. The narration doesn't talk to itself.

This module declares retirements as structured data so:
- Tests can grep for present-tense references to retired names
  (sweep pattern #27 as automated guard)
- ``trinity-local <retired-cli>`` can show a friendly migration message
  rather than ``unknown command``
- Docs can reference the registry at render time instead of restating

Schema:
    RetirementRecord(retired_at, commit, replacement, reason, kind,
                     artifact_persists)

When adding a retirement: add the entry here in the same commit as
the deletion. Don't narrate the retirement in 5 places + forget the
registry — the registry IS the source of truth.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal


RetirementKind = Literal["cli", "mcp_tool", "module", "file", "config_field", "concept"]


@dataclass(frozen=True)
class RetirementRecord:
    """A single retirement event captured as structured data.

    Fields:
        name: The retired name as it appeared in code or invocation
            (e.g., ``"shortcut-install"``, ``"search_prompts"``,
            ``"me-build"``, ``"Trinity.app"``).
        retired_at: ISO date the retirement landed on main (YYYY-MM-DD).
        commit: Short or full hash of the retirement commit (if known).
        replacement: The current substitute, or empty string if there
            is no direct replacement (the feature was killed without
            a successor).
        reason: One-line human-readable reason.
        kind: Category — cli / mcp_tool / module / file / config_field /
            concept. Lets tests filter by kind.
        artifact_persists: True if the retired artifact (e.g., a macOS
            Shortcut on disk) keeps working for users who already had
            it, even though the bootstrap path is gone.
    """

    name: str
    retired_at: str
    commit: str
    replacement: str
    reason: str
    kind: RetirementKind = "cli"
    artifact_persists: bool = False


# Canonical registry. Keys = retired names; values = records.
# Add entries in the SAME commit as the deletion. Sorted by retirement
# date (most recent first) for ease of audit.
RETIRED: dict[str, RetirementRecord] = {
    # ── 2026-05-20 consistency-sweep retirement ──
    "models_dir": RetirementRecord(
        name="models_dir",
        retired_at="2026-05-20",
        commit="0ae3a40",
        replacement="hf_cache_model_path() in backend_mlx (reports HF cache)",
        reason="state_paths helper built ~/.trinity/models/<name>/ but nothing "
               "read the resulting path; the actual model lives in HF cache. "
               "Tick 28 dropped the dead helper + the misleading model_path() "
               "wrapper in backend_mlx; MlxEmbedder.model_path now points at "
               "the real ~/.cache/huggingface/hub/ location.",
        kind="module",
        artifact_persists=True,  # empty ~/.trinity/models/ may exist on older installs
    ),
    "~/.trinity/models/": RetirementRecord(
        name="~/.trinity/models/",
        retired_at="2026-05-20",
        commit="0ae3a40",
        replacement="~/.cache/huggingface/hub/models--nomic-ai--nomic-embed-text-v1.5",
        reason="Directory created as side-effect of the unused models_dir() "
               "helper. Actual nomic weights cached by sentence-transformers "
               "in HF cache, not here. Safe to delete on user systems.",
        kind="file",
        artifact_persists=True,
    ),
    # ── 2026-05-18 simplification pass ──
    "doctor": RetirementRecord(
        name="doctor",
        retired_at="2026-05-18",
        commit="",  # pre-iter; collapsed into status during simplification
        replacement="status",
        reason="`status` absorbed the role; one canonical health-check entry",
        kind="cli",
    ),
    "watch-once": RetirementRecord(
        name="watch-once",
        retired_at="2026-05-18",
        commit="",
        replacement="ingest-recent",
        reason="Tool-triggered ingest (Chrome ext + MCP ask) replaces watcher daemon model",
        kind="cli",
    ),
    "watch-loop": RetirementRecord(
        name="watch-loop",
        retired_at="2026-05-18",
        commit="",
        replacement="ingest-recent",
        reason="See watch-once; same daemon-subsystem retirement",
        kind="cli",
    ),
    "distill": RetirementRecord(
        name="distill",
        retired_at="2026-05-18",
        commit="c9b1f9d",
        replacement="dream",
        reason="dream Phase 5 refreshes core.md; standalone distill CLI hidden",
        kind="cli",
    ),
    "bootstrap-pairs": RetirementRecord(
        name="bootstrap-pairs",
        retired_at="2026-05-18",
        commit="",
        replacement="dream",
        reason="dream Phase 2.5 subsumes pair-mining",
        kind="cli",
    ),
    "me-build": RetirementRecord(
        name="me-build",
        retired_at="2026-05-18",
        commit="",
        replacement="lens-build",
        reason="Tier 1 #2 rename: me/persona → lens",
        kind="cli",
    ),
    "merges-show": RetirementRecord(
        name="merges-show",
        retired_at="2026-05-18",
        commit="",
        replacement="",
        reason="Internal CLI with no skill/launchpad callers; killed in simplification iter 7",
        kind="cli",
    ),
    "get_eval_summary": RetirementRecord(
        name="get_eval_summary",
        retired_at="2026-05-18",
        commit="",
        replacement="ask + get_picks",
        reason="Agents ground via ask + picks; eval-summary surface remains on launchpad",
        kind="mcp_tool",
    ),
    # ── 2026-05-17 macOS Shortcut + Trinity.app retirement ──
    "shortcut-install": RetirementRecord(
        name="shortcut-install",
        retired_at="2026-05-17",
        commit="53db635",
        replacement="install-extension",
        reason="Chrome extension is the cross-platform dispatch path",
        kind="cli",
        artifact_persists=True,  # macOS Shortcut on existing installs still works
    ),
    "install-app": RetirementRecord(
        name="install-app",
        retired_at="2026-05-17",
        commit="",
        replacement="install-extension",
        reason="Trinity.app wrapper retired; Chrome extension is cross-platform launchpad host",
        kind="cli",
    ),
    "Trinity.app": RetirementRecord(
        name="Trinity.app",
        retired_at="2026-05-17",
        commit="",
        replacement="install-extension",
        reason="osacompile .app wrapper retired pre-launch",
        kind="file",
    ),
    "search_prompts": RetirementRecord(
        name="search_prompts",
        retired_at="2026-05-17",
        commit="",
        replacement="substring + recency + replay-value heuristics",
        reason="Embedding-free hot path; ranker/heuristic.py replaces it",
        kind="mcp_tool",
    ),
    "get_eval_summary": RetirementRecord(
        name="get_eval_summary",
        retired_at="2026-05-18",
        commit="1fed7fc",
        replacement="ask + get_picks",
        reason="Agents ground 'which model is best for me at X' via the v1.5 trio (ask + picks); the eval-summary surface remains on the launchpad card and `eval-show` CLI for direct user inspection. Bundled into the auto-chain settings retirement (commit 1fed7fc).",
        kind="mcp_tool",
    ),
    "trinity-dispatch": RetirementRecord(
        name="trinity-dispatch",
        retired_at="2026-05-17",
        commit="53db635",
        replacement="trinity-local-capture-host",
        reason="Chrome extension Native Messaging replaces the macOS Shortcut dispatcher",
        kind="file",
    ),
    "default_task_kind": RetirementRecord(
        name="default_task_kind",
        retired_at="2026-05-20",
        commit="",  # filled by next commit
        replacement="(removed, never consumed downstream)",
        reason="`task_kind` was renamed to `task_type` in task #92 (Tier 1 #3), but the `default_task_kind` config field survived as a parsed-but-never-read remnant in AppConfig. No code path read `config.default_task_kind` after the rename — pure dead state. Tick 47 swept it out of the dataclass, config.json, config.example.json, and 5 tests.",
        kind="config_field",
    ),
    "~/.trinity/analytics/watch_errors.jsonl": RetirementRecord(
        name="~/.trinity/analytics/watch_errors.jsonl",
        retired_at="2026-05-20",
        commit="",  # filled by next commit
        replacement="(none)",
        reason="Watcher subsystem retired 2026-05-17; no writer remains. Tick 44 swept the dead `_watch_error_summary` reader + status CLI surface that read the never-written file.",
        kind="file",
    ),
    # ── Earlier renames (Tier 1/2 simplification) ──
    "task_kind": RetirementRecord(
        name="task_kind",
        retired_at="2026-05-12",
        commit="",
        replacement="task_type",
        reason="Tier 1 #3 rename to disambiguate from category (LMArena grouping)",
        kind="concept",
    ),
    "persona.md": RetirementRecord(
        name="persona.md",
        retired_at="2026-05-12",
        commit="",
        replacement="lens.md",
        reason="Tier 1 #2 rename: me/persona → lens",
        kind="file",
    ),
    "TranscriptNode": RetirementRecord(
        name="TranscriptNode",
        retired_at="2026-05-12",
        commit="",
        replacement="PromptNode + TurnWindow",
        reason="Tier 2 #5: memory tier collapsed to 2 from 3",
        kind="concept",
    ),
    "judge": RetirementRecord(
        name="judge",
        retired_at="2026-05-12",
        commit="",
        replacement="run_council(responses=[...])",
        reason="Tier 1 #2: pre-supplied member outputs go straight to chairman synthesis",
        kind="mcp_tool",
    ),
    "personal_routing_table.json": RetirementRecord(
        name="personal_routing_table.json",
        retired_at="2026-05-12",
        commit="",
        replacement="compute_personal_routing_table() on demand",
        reason="Tier 1 #3: computed from council_outcomes/ at read time, no durable state",
        kind="file",
    ),
}


def get(name: str) -> RetirementRecord | None:
    """Look up a retirement record by name (returns None if not retired)."""
    return RETIRED.get(name)


def names_by_kind(kind: RetirementKind) -> list[str]:
    """All retired names of a given kind, sorted alphabetically."""
    return sorted(n for n, r in RETIRED.items() if r.kind == kind)


def all_names() -> list[str]:
    """All retired names regardless of kind."""
    return sorted(RETIRED.keys())


def format_migration_hint(name: str) -> str:
    """Format a friendly migration hint for ``trinity-local <retired-cli>``.

    Example::

        >>> format_migration_hint("shortcut-install")
        '`shortcut-install` was retired 2026-05-17 — use `install-extension`. ...'
    """
    record = RETIRED.get(name)
    if record is None:
        return f"`{name}` is not a known retired CLI."
    msg = f"`{record.name}` was retired {record.retired_at}"
    if record.replacement:
        msg += f" — use `{record.replacement}` instead"
    msg += f". ({record.reason}.)"
    if record.artifact_persists:
        msg += " Existing installs of the retired artifact may still work."
    return msg
