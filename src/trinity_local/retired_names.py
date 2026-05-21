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

from dataclasses import dataclass
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
    # ── 2026-05-21 launchpad backend dead-code cleanup ──
    "_rate_limit_saves": RetirementRecord(
        name="_rate_limit_saves",
        retired_at="2026-05-21",
        commit="(this commit)",
        replacement="(none — function was orphan; no Vue consumer)",
        reason="launchpad_data._rate_limit_saves() computed a 30-day rate-limit-save count and shipped it into pageData['rateLimitSaves'], but the Vue template never read it. Pre-launch the user explicitly said 'remove this' for the rate-limit-saves card; the UI was deleted but the backend compute survived as orphan. Removed both the function and the pageData injection in the same commit.",
        kind="module",
    ),
    "pageData.verdictStats": RetirementRecord(
        name="pageData.verdictStats",
        retired_at="2026-05-21",
        commit="(this commit)",
        replacement="doctor._check_verdict_rate() — informational health check (same _verdict_stats() math)",
        reason="The launchpad pageData field stopped being read by Vue when the rating UX was sunset (commit 8f1fd95). The _verdict_stats() compute function stays alive because doctor._check_verdict_rate() still consumes it for the informational `trinity-local status` health check. Only the pageData injection (and its tests) are sunset.",
        kind="concept",
    ),
    "pageData.rateLimitSaves": RetirementRecord(
        name="pageData.rateLimitSaves",
        retired_at="2026-05-21",
        commit="(this commit)",
        replacement="(none — see _rate_limit_saves)",
        reason="Companion entry: the pageData field never had a Vue consumer; removed alongside the _rate_limit_saves() function.",
        kind="concept",
    ),
    # ── 2026-05-21 rate-action mechanism retirement (companion to record_outcome) ──
    "rate_action": RetirementRecord(
        name="rate_action",
        retired_at="2026-05-21",
        commit="(this commit)",
        replacement="(none — chairman pick IS the supervision signal, fed automatically)",
        reason="The `rate_action` field that route/ask/run_council/get_council_status injected into MCP responses pointed agents at the retired record_outcome tool. With record_outcome retired and chairman pick auto-flowing into the personal routing table (commit bb817b6), the nudge had no destination. Per user direction 'Retire the whole mechanism' — agents don't need a hint to capture a verdict that's already captured. Pillar 4 funnel-widener deferred until a different shape proves out (current default: refinement prompts on the council page surface 'what should the chairman have picked instead' without an agent-side tax).",
        kind="concept",
    ),
    "pending_ratings": RetirementRecord(
        name="pending_ratings",
        retired_at="2026-05-21",
        commit="(this commit)",
        replacement="(none — see rate_action)",
        reason="`pending_ratings` was the SECONDARY funnel-widener — surfaced older unrated councils in route/ask responses. Same mechanism, same retirement (the agent-side capture pressure is gone with record_outcome). Launchpad surfaces unrated councils via the existing `unrated` CLI; pending_ratings as an MCP nudge is sunset alongside the rate-action mechanism.",
        kind="concept",
    ),
    # ── 2026-05-21 rating-UX MCP retirement ──
    "record_outcome": RetirementRecord(
        name="record_outcome",
        retired_at="2026-05-21",
        commit="(this commit)",
        replacement="routing_label.winner (chairman pick) as supervision signal; refinement prompts as 'what user wanted differently'",
        reason="Per user direction 'we are sunsetting user ratings. Full retirement including MCP.' The MCP rating tool pressured agents to interrupt conversations to surface rate prompts. The chairman's pick IS the verdict (per the 2026-05-21 prime directive 'picks the answer YOU would have picked'); compute_personal_routing_table now aggregates from routing_label.winner (commit bb817b6) instead of blending with user_winner. Refinement prompts on each council carry the post-pivot 'what should it have been instead' signal — embedded in the user's natural flow, not a tax. CLI council-rate stays for power users who want to write verdicts from the terminal; only the MCP tool is gone.",
        kind="mcp_tool",
    ),
    # ── 2026-05-21 consistency-sweep retirement ──
    "commands.tasks": RetirementRecord(
        name="commands.tasks",
        retired_at="2026-05-21",
        commit="bb41bda",
        replacement="(none — task/bundle/launch flows supplanted by the live council architecture)",
        reason="`commands/tasks.py` (90 LOC) held the handle_bundle_create / handle_task_create / handle_launch_create / handle_task_show / handle_task_sync handlers for retired CLIs. The module's own docstring claimed 'Tests still import handle_* for handler-level coverage' but tick 85 audit found ZERO callers across src/ + tests/ — the false-claim docstring outlived the test coverage by months. The actual live substrate (LaunchEvent dataclass, append_launch_event, create_launch_event) survives in council_runtime.py and is exercised by the council pipeline. Pattern #4 + #20: when a CLI retires, the handler module's docstring is the last surface to update; sometimes it never does. Sunset confirmed via AskUserQuestion in tick 85.",
        kind="module",
    ),
    "commands.depth": RetirementRecord(
        name="commands.depth",
        retired_at="2026-05-21",
        commit="bb41bda",
        replacement="(none — depth-signal geometry lives in me/depth.py; no caller wants a CLI wrapper)",
        reason="`commands/depth.py` (123 LOC) held the handle_depth_show CLI handler for a CLI that was retired pre-launch. The docstring claimed 'Tests still import handle_depth_show for coverage' but tick 85 audit found ZERO callers in src/ + tests/. The actual geometry primitives (depth_score, corpus_distance, inter_turn_distance, LID) live in `me/depth.py` and ARE actively used by basins.py + lens pipeline. Sunset confirmed via AskUserQuestion in tick 85; the geometry stays.",
        kind="module",
    ),
    "thread_context": RetirementRecord(
        name="thread_context",
        retired_at="2026-05-21",
        commit="063eb80",
        replacement="(none — JS-side inline implementation in launchpad_template.py:2548-2574)",
        reason="Docstring claimed it was the canonical formatter \"used by commands/replay.py + launchpad_template.py\" but tick 81 audit found ZERO Python callers. replay.py uses its own `_build_hidden_context()` with a different format; launchpad_template.py must reimplement in JS because the file:// architecture (claude.md \"File:// is the substrate\") blocks JS from importing Python. The `_strip_thread_context()` reader in launchpad_data.py only PARSES the format, doesn't import the producer. Pure orphan; deleted cleanly with the JS-side comment updated to no longer point at the removed file. Pattern #4: when fixing a bug, audit for its shape — same orphan-module shape as the `feature_extractors` + `training_schema` sunset in tick 57.",
        kind="module",
    ),
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
    # ── 2026-05-20 dead-register strip (CLIs that lost their surface earlier) ──
    # Commit 2087cfe stripped fully-elaborated register() functions for CLIs
    # that main.py had already dropped from CORE_COMMAND_MODULES. Each had
    # been silently un-callable for some time before the dead code was
    # removed. retired_at = strip date; "deferred" replacements are explicit.
    "task-create": RetirementRecord(
        name="task-create",
        retired_at="2026-05-20",
        commit="2087cfe",
        replacement="(none — task/bundle/launch flows supplanted by the live council architecture)",
        reason="Dead register() in commands/tasks.py stripped; user-facing surface had already been orphan after the live-council architecture took over (see commands.tasks module retirement in this registry).",
        kind="cli",
    ),
    "task-show": RetirementRecord(
        name="task-show",
        retired_at="2026-05-20",
        commit="2087cfe",
        replacement="(none — see task-create)",
        reason="Companion to task-create; same dead-register strip.",
        kind="cli",
    ),
    "task-sync": RetirementRecord(
        name="task-sync",
        retired_at="2026-05-20",
        commit="2087cfe",
        replacement="(none — see task-create)",
        reason="Companion to task-create; same dead-register strip.",
        kind="cli",
    ),
    "bundle-create": RetirementRecord(
        name="bundle-create",
        retired_at="2026-05-20",
        commit="2087cfe",
        replacement="(none — bundles are now internal to council_runtime)",
        reason="Dead register() stripped; PromptBundle creation flows through council-start instead of a standalone CLI verb.",
        kind="cli",
    ),
    "launch-create": RetirementRecord(
        name="launch-create",
        retired_at="2026-05-20",
        commit="2087cfe",
        replacement="(none — LaunchEvent is internal to council_runtime)",
        reason="Dead register() stripped; launch events were never a user-facing concept post live-council.",
        kind="cli",
    ),
    "features": RetirementRecord(
        name="features",
        retired_at="2026-05-20",
        commit="2087cfe",
        replacement="ingest-recent",
        reason="Orphan handler for the retired `ingest` CLI; tool-triggered incremental ingest replaced the manual feature-extraction surface.",
        kind="cli",
    ),
    "core-show": RetirementRecord(
        name="core-show",
        retired_at="2026-05-20",
        commit="2087cfe",
        replacement="cat ~/.trinity/core.md",
        reason="Was: print core.md verbatim (symmetry with lens-show). Inlined — users can read the file directly; CLI surface didn't pay its keep.",
        kind="cli",
    ),
    "depth-show": RetirementRecord(
        name="depth-show",
        retired_at="2026-05-20",
        commit="2087cfe",
        replacement="(none — depth-signal geometry lives in me/depth.py; no caller wanted a CLI wrapper)",
        reason="Internal vectorized LID metric inspection. No user-facing surface needed it.",
        kind="cli",
    ),
    "trust-init": RetirementRecord(
        name="trust-init",
        retired_at="2026-05-20",
        commit="2087cfe",
        replacement="manual ~/.trinity/trust.toml authoring (see docs/TRUST-MODE.md)",
        reason="Trust-CLI surface deferred to v1.1 per the Phase 6 council (council_c18f739a0234aa58). The substrate ITSELF ships in v1.0 — trust.toml schema, audit.log writer, --dangerously-trust-all env-var gate — only the friendly CLI surface is deferred.",
        kind="cli",
    ),
    "trust-show": RetirementRecord(
        name="trust-show",
        retired_at="2026-05-20",
        commit="2087cfe",
        replacement="trinity_local.trust.resolve_trust() Python API (see docs/TRUST-MODE.md)",
        reason="Trust-CLI surface deferred to v1.1; library inspection available programmatically until then.",
        kind="cli",
    ),
    "audit-show": RetirementRecord(
        name="audit-show",
        retired_at="2026-05-20",
        commit="2087cfe",
        replacement="tail ~/.trinity/audit.log | jq (manual until v1.1)",
        reason="Trust-CLI surface deferred to v1.1; audit.log is plain JSONL readable directly. v1.1 picks up `--tier`/`--operation`/`--outcome` filter flags.",
        kind="cli",
    ),
    # ── 2026-05-18 simplification pass ──
    "stats": RetirementRecord(
        name="stats",
        retired_at="2026-05-18",
        commit="eac2227",
        replacement="(none — launchpad surfaces the same numbers)",
        reason="Off-the-live-product-path marketing-summary CLI; killed in the simplification pass alongside `metric` and the research/ CLIs.",
        kind="cli",
    ),
    "metric": RetirementRecord(
        name="metric",
        retired_at="2026-05-18",
        commit="eac2227",
        replacement="dispatch_health.compute_provider_health() (Python API)",
        reason="The rate-limit-saves CTA on the launchpad retired with the rest of the rating UX; the jsonl is still written by ask.py and read by dispatch_health.py — the CLI was the user-facing surface, now gone.",
        kind="cli",
    ),
    "council-last": RetirementRecord(
        name="council-last",
        retired_at="2026-05-18",
        commit="93bfe1a",
        replacement="(none — launchpad filter chips surface recent councils)",
        reason="P0 onboarding shortcut absorbed by launchpad's per-source/per-week filters; users no longer need a CLI to find their last council.",
        kind="cli",
    ),
    "polish-auto-enable": RetirementRecord(
        name="polish-auto-enable",
        retired_at="2026-05-18",
        commit="1fed7fc",
        replacement="(none — polish-shape auto-iterate setting removed)",
        reason="Implicit auto-iteration on polish-shape tasks didn't pay for itself; users prefer explicit `council-iterate --rounds N`.",
        kind="cli",
    ),
    "polish-auto-disable": RetirementRecord(
        name="polish-auto-disable",
        retired_at="2026-05-18",
        commit="1fed7fc",
        replacement="(none — see polish-auto-enable)",
        reason="Companion to polish-auto-enable; both retired together.",
        kind="cli",
    ),
    "auto-chain-enable": RetirementRecord(
        name="auto-chain-enable",
        retired_at="2026-05-18",
        commit="1fed7fc",
        replacement="council-iterate --rounds N",
        reason="Implicit chaining replaced with explicit per-invocation `--rounds` flag; the setting was global state hiding a per-call decision.",
        kind="cli",
    ),
    "auto-chain-disable": RetirementRecord(
        name="auto-chain-disable",
        retired_at="2026-05-18",
        commit="1fed7fc",
        replacement="(none — see auto-chain-enable)",
        reason="Companion to auto-chain-enable; both retired together.",
        kind="cli",
    ),
    "auto-open-enable": RetirementRecord(
        name="auto-open-enable",
        retired_at="2026-05-18",
        commit="1fed7fc",
        replacement="(none — review-page handoff via launchpad)",
        reason="Auto-shell-`open` on council completion was noisy in dev workflows; launchpad's review-link affordance replaced it.",
        kind="cli",
    ),
    "auto-open-disable": RetirementRecord(
        name="auto-open-disable",
        retired_at="2026-05-18",
        commit="1fed7fc",
        replacement="(none — see auto-open-enable)",
        reason="Companion to auto-open-enable; both retired together.",
        kind="cli",
    ),
    "cache-stats": RetirementRecord(
        name="cache-stats",
        retired_at="2026-05-18",
        commit="cc52b3b",
        replacement="(none — persistent embedding cache retired)",
        reason="Cache retired alongside the persistent-embeddings simplification; offline rebuild passes re-encode per run (~2 min on 50k prompts).",
        kind="cli",
    ),
    "cache-clear": RetirementRecord(
        name="cache-clear",
        retired_at="2026-05-18",
        commit="cc52b3b",
        replacement="(none — see cache-stats)",
        reason="Companion to cache-stats; cache no longer exists to clear.",
        kind="cli",
    ),
    "doctor": RetirementRecord(
        name="doctor",
        retired_at="2026-05-18",
        commit="ef2f328",
        replacement="status",
        reason="`status` absorbed the role; one canonical health-check entry",
        kind="cli",
    ),
    "watch-once": RetirementRecord(
        name="watch-once",
        retired_at="2026-05-18",
        commit="07ea7da",
        replacement="ingest-recent",
        reason="Tool-triggered ingest (Chrome ext + MCP ask) replaces watcher daemon model",
        kind="cli",
    ),
    "watch-loop": RetirementRecord(
        name="watch-loop",
        retired_at="2026-05-18",
        commit="07ea7da",
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
        commit="c4da425",
        replacement="dream",
        reason="dream Phase 2.5 subsumes pair-mining",
        kind="cli",
    ),
    "me-build": RetirementRecord(
        name="me-build",
        retired_at="2026-05-12",
        commit="b5d4d04",
        replacement="lens-build",
        reason="Tier 1 #2 rename: me/persona → lens",
        kind="cli",
    ),
    "merges-show": RetirementRecord(
        name="merges-show",
        retired_at="2026-05-18",
        commit="3e66465",
        replacement="",
        reason="Internal CLI with no skill/launchpad callers; killed in simplification iter 7",
        kind="cli",
    ),
    "get_eval_summary": RetirementRecord(
        name="get_eval_summary",
        retired_at="2026-05-18",
        commit="1fed7fc",
        replacement="ask + get_picks",
        reason="Agents ground 'which model is best for me at X' via the v1.5 trio (ask + picks); the eval-summary surface remains on the launchpad card and `eval-show` CLI for direct user inspection. Bundled into the auto-chain settings retirement (commit 1fed7fc).",
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
        commit="9c82ded",
        replacement="install-extension",
        reason="Trinity.app wrapper retired; Chrome extension is cross-platform launchpad host",
        kind="cli",
    ),
    "Trinity.app": RetirementRecord(
        name="Trinity.app",
        retired_at="2026-05-17",
        commit="9c82ded",
        replacement="install-extension",
        reason="osacompile .app wrapper retired pre-launch",
        kind="file",
    ),
    "search_prompts": RetirementRecord(
        name="search_prompts",
        retired_at="2026-05-17",
        commit="a815995",
        replacement="substring + recency + replay-value heuristics",
        reason="Embedding-free hot path; ranker/heuristic.py replaces it",
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
    "guess_task_kind": RetirementRecord(
        name="guess_task_kind",
        retired_at="2026-05-20",
        commit="244d15a",
        replacement="guess_task_type",
        reason="Back-compat alias from task #92 (Tier 1 #3 task_kind → task_type rename). Tick 48 audit found ZERO callers in src/ or tests/ — the comment claiming 'external callers (and a handful of tests) still import' was already untrue at the time of writing. Trinity has no external SDK consumers; internal callers all use guess_task_type directly. Pure dead aliasing.",
        kind="module",
    ),
    "default_task_kind": RetirementRecord(
        name="default_task_kind",
        retired_at="2026-05-20",
        commit="ad9abec",
        replacement="(removed, never consumed downstream)",
        reason="`task_kind` was renamed to `task_type` in task #92 (Tier 1 #3), but the `default_task_kind` config field survived as a parsed-but-never-read remnant in AppConfig. No code path read `config.default_task_kind` after the rename — pure dead state. Tick 47 swept it out of the dataclass, config.json, config.example.json, and 5 tests.",
        kind="config_field",
    ),
    "commands.ingest": RetirementRecord(
        name="commands.ingest",
        retired_at="2026-05-20",
        commit="4aa7c77",
        replacement="(none — orphan handler for retired `features` CLI)",
        reason="`commands/ingest.py` was the retired-CLI shim for `trinity-local features` (kept importable but unregistered in main.py per pre-launch simplification). Imported from `..feature_extractors`, which tick 57 deleted alongside the v2 trained-coordinator sunset. Tick 58 found the broken import via `python -c 'from trinity_local.commands import ingest'`. Pattern #4 audit-for-shape: tick 57's relative-import grep used 1-dot patterns and missed the 2-dot `from ..feature_extractors` import. The whole file was dead even before the broken import — main.py registered no handler, no tests, no smoke. Deleted cleanly.",
        kind="module",
    ),
    "training_schema": RetirementRecord(
        name="training_schema",
        retired_at="2026-05-20",
        commit="d26317f",
        replacement="(none — v2 trained-coordinator path sunset 2026-05-11)",
        reason="262-LOC module defining the v2 trained-coordinator data schema (TranscriptWindow, RoutingExample, etc). The v2 path was sunset 2026-05-11 per claude.md ('reopens only if v1.5 hits a quality ceiling'). Tick 57 audit: ZERO callers across src/ and tests/ — feature_extractors.py was the only importer, and it itself had zero importers. Same shape as the Loop Constitution substrate that was deleted in pre-launch simplification. Architecture preserved in git history + docs/spec-v2.md sunset header.",
        kind="module",
    ),
    "feature_extractors": RetirementRecord(
        name="feature_extractors",
        retired_at="2026-05-20",
        commit="d26317f",
        replacement="(none — v2 trained-coordinator path sunset)",
        reason="261-LOC module wrapping the training_schema dataclasses for feature extraction. Zero importers across src/ and tests/. Deleted alongside training_schema.py — same v2-substrate-after-sunset shape.",
        kind="module",
    ),
    "hard_examples_dir": RetirementRecord(
        name="hard_examples_dir",
        retired_at="2026-05-20",
        commit="7986c0f",
        replacement="(inlined as `research_dir() / 'hard_examples'`)",
        reason="Same Pattern #4 shape as cortex_dir / models_dir — mkdir'd `~/.trinity/research/hard_examples/` on every call but zero callers. The single consumer (knn_advisor.py L60-61) constructs the path inline from `research_dir()`. Tick 52 deleted the helper.",
        kind="module",
    ),
    "replay_examples_dir": RetirementRecord(
        name="replay_examples_dir",
        retired_at="2026-05-20",
        commit="7986c0f",
        replacement="(inlined as `research_dir() / 'examples'`)",
        reason="Misleading name: returned `research_dir() / 'examples'` (NOT 'replay_examples'). Zero callers; knn_advisor.py L60-61 inlines the path string. Tick 52 deleted alongside hard_examples_dir.",
        kind="module",
    ),
    "cortex_dir": RetirementRecord(
        name="cortex_dir",
        retired_at="2026-05-20",
        commit="598ceb4",
        replacement="(none — picks.json carries failure_modes + successful_prompts inline)",
        reason="Spec-v1.5 originally described a `~/.trinity/cortex/` subdirectory with separate failure_modes.json + successful_prompts.json files. The shipped architecture embeds those fields INSIDE each RoutingPattern entry in scoreboard/picks.json — no separate cortex/ directory was ever needed. `cortex_dir()` survived as a state_paths helper that mkdir'd an empty `~/.trinity/cortex/` on every call (same ghost-dir shape as the retired `models_dir()` from tick 28). Zero callers in src/ or tests/. Tick 51 deleted the helper.",
        kind="module",
    ),
    "~/.trinity/cortex/": RetirementRecord(
        name="~/.trinity/cortex/",
        retired_at="2026-05-20",
        commit="598ceb4",
        replacement="~/.trinity/scoreboard/picks.json (inline failure_modes / successful_prompts)",
        reason="Spec-v1.5 § L133-134 described `~/.trinity/cortex/failure_modes.json` + `~/.trinity/cortex/successful_prompts.json` as v1.5 NEW files. The shipped architecture put both fields inline in scoreboard/picks.json's RoutingPattern records. The cortex/ subdirectory was never written by any code path beyond the (zero-caller) `cortex_dir()` helper. Tick 51 sunset both.",
        kind="file",
    ),
    "~/.trinity/analytics/watch_errors.jsonl": RetirementRecord(
        name="~/.trinity/analytics/watch_errors.jsonl",
        retired_at="2026-05-20",
        commit="8d42d83",
        replacement="(none)",
        reason="Watcher subsystem retired 2026-05-17; no writer remains. Tick 44 swept the dead `_watch_error_summary` reader + status CLI surface that read the never-written file.",
        kind="file",
    ),
    # ── Earlier renames (Tier 1/2 simplification) ──
    "task_kind": RetirementRecord(
        name="task_kind",
        retired_at="2026-05-12",
        commit="22c3064",
        replacement="task_type",
        reason="Tier 1 #3 rename to disambiguate from category (LMArena grouping)",
        kind="concept",
    ),
    "persona.md": RetirementRecord(
        name="persona.md",
        retired_at="2026-05-12",
        commit="b5d4d04",
        replacement="lens.md",
        reason="Tier 1 #2 rename: me/persona → lens",
        kind="file",
    ),
    "TranscriptNode": RetirementRecord(
        name="TranscriptNode",
        retired_at="2026-05-12",
        commit="623f592",
        replacement="PromptNode + TurnWindow",
        reason="Tier 2 #5: memory tier collapsed to 2 from 3",
        kind="concept",
    ),
    "judge": RetirementRecord(
        name="judge",
        retired_at="2026-05-12",
        commit="623f592",
        replacement="run_council(responses=[...])",
        reason="Tier 1 #2: pre-supplied member outputs go straight to chairman synthesis",
        kind="mcp_tool",
    ),
    "personal_routing_table.json": RetirementRecord(
        name="personal_routing_table.json",
        retired_at="2026-05-12",
        commit="623f592",
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
