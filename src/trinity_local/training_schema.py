from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class RawSessionRef:
    """Minimal provenance for a source-native transcript artifact."""

    source: str
    native_id: str
    source_path: str
    source_format: str | None = None
    source_format_version: str | None = None
    provider_session_kind: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v not in (None, {}, [])}


@dataclass
class ModelDescriptor:
    """Versioned model identity for one session or one turn.

    Keep both a normalized view and the raw source values. Model capabilities
    drift over time, so routing examples must remember exactly which model
    variant and CLI build produced the behavior.
    """

    provider: str
    raw_model_id: str | None = None
    normalized_model_id: str | None = None
    model_family: str | None = None
    model_variant: str | None = None
    model_snapshot: str | None = None
    cli_name: str | None = None
    cli_version: str | None = None
    sdk_version: str | None = None
    source_format_version: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v not in (None, {}, [])}


@dataclass
class ToolSummary:
    name: str
    count: int = 0
    error_count: int = 0
    first_command: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v not in (None, {}, [])}


@dataclass
class OutcomeSignals:
    completed: bool | None = None
    assistant_turns: int | None = None
    user_turns: int | None = None
    tool_turns: int | None = None
    tool_calls_total: int | None = None
    tool_errors_total: int | None = None
    files_touched: int | None = None
    shell_commands: int | None = None
    session_seconds: float | None = None
    switched_after: bool | None = None
    switched_to_provider: str | None = None
    manual_reroute_accepted: bool | None = None
    verifier_like: bool | None = None
    token_input: int | None = None
    token_output: int | None = None
    token_cached: int | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v not in (None, {}, [])}


@dataclass
class TranscriptWindow:
    """Compact session slice for router training.

    This intentionally avoids storing the entire transcript. The router only
    needs a stable window around the decision boundary plus outcome metadata.
    """

    session_id: str
    provider: str
    source_path: str
    started_at: str | None = None
    ended_at: str | None = None
    cwd: str | None = None
    project_hint: str | None = None
    first_user_text: str | None = None
    planner_text: str | None = None
    final_text: str | None = None
    task_kind_hint: str | None = None
    role_hint: str | None = None
    model: ModelDescriptor = field(default_factory=lambda: ModelDescriptor(provider=""))
    tools: list[ToolSummary] = field(default_factory=list)
    outcome: OutcomeSignals = field(default_factory=OutcomeSignals)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "session_id": self.session_id,
            "provider": self.provider,
            "source_path": self.source_path,
            "model": self.model.to_dict(),
            "tools": [tool.to_dict() for tool in self.tools],
            "outcome": self.outcome.to_dict(),
        }
        for key in (
            "started_at",
            "ended_at",
            "cwd",
            "project_hint",
            "first_user_text",
            "planner_text",
            "final_text",
            "task_kind_hint",
            "role_hint",
        ):
            value = getattr(self, key)
            if value not in (None, "", [], {}):
                payload[key] = value
        if self.extra:
            payload["extra"] = self.extra
        return payload


@dataclass
class SessionFeatures:
    """Derived metadata from one source session.

    This is the stable boundary between raw transcript parsing and training
    example generation.
    """

    raw: RawSessionRef
    provider: str
    session_id: str
    model: ModelDescriptor
    started_at: str | None = None
    ended_at: str | None = None
    cwd: str | None = None
    project_hint: str | None = None
    git_branch: str | None = None
    dirty_worktree: bool | None = None
    slash_commands: list[str] = field(default_factory=list)
    mcp_servers: list[str] = field(default_factory=list)
    first_user_text: str | None = None
    planner_text: str | None = None
    final_text: str | None = None
    attachments_present: bool | None = None
    did_edit_files: bool | None = None
    did_run_shell: bool | None = None
    did_use_web: bool | None = None
    did_use_mcp: bool | None = None
    retry_count: int | None = None
    tools: list[ToolSummary] = field(default_factory=list)
    outcome: OutcomeSignals = field(default_factory=OutcomeSignals)
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "raw": self.raw.to_dict(),
            "provider": self.provider,
            "session_id": self.session_id,
            "model": self.model.to_dict(),
            "tools": [tool.to_dict() for tool in self.tools],
            "outcome": self.outcome.to_dict(),
        }
        for key in (
            "started_at",
            "ended_at",
            "cwd",
            "project_hint",
            "git_branch",
            "first_user_text",
            "planner_text",
            "final_text",
            "attachments_present",
            "did_edit_files",
            "did_run_shell",
            "did_use_web",
            "did_use_mcp",
            "dirty_worktree",
            "retry_count",
        ):
            value = getattr(self, key)
            if value not in (None, "", [], {}):
                payload[key] = value
        if self.slash_commands:
            payload["slash_commands"] = self.slash_commands
        if self.mcp_servers:
            payload["mcp_servers"] = self.mcp_servers
        if self.extra:
            payload["extra"] = self.extra
        return payload


@dataclass
class TaskLink:
    """Cross-provider linkage for the same underlying task."""

    task_cluster_id: str
    session_id: str
    provider: str
    previous_provider: str | None = None
    next_provider: str | None = None
    switched: bool | None = None
    switch_reason: str | None = None
    time_to_switch_seconds: float | None = None
    router_suggestion: str | None = None
    router_suggestion_accepted: bool | None = None
    council_invoked: bool | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v not in (None, {}, [])}


@dataclass
class RoutingExample:
    """One supervised example for the local coordinator."""

    example_id: str
    transcript: TranscriptWindow
    chosen_provider: str
    chosen_model: ModelDescriptor
    label: str
    task_link: TaskLink | None = None
    confidence: float | None = None
    alternatives: list[str] = field(default_factory=list)
    reasons: list[str] = field(default_factory=list)
    source_event_ids: list[str] = field(default_factory=list)
    schema_version: str = "0.1"

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "example_id": self.example_id,
            "schema_version": self.schema_version,
            "transcript": self.transcript.to_dict(),
            "chosen_provider": self.chosen_provider,
            "chosen_model": self.chosen_model.to_dict(),
            "label": self.label,
        }
        if self.task_link is not None:
            payload["task_link"] = self.task_link.to_dict()
        if self.confidence is not None:
            payload["confidence"] = self.confidence
        if self.alternatives:
            payload["alternatives"] = self.alternatives
        if self.reasons:
            payload["reasons"] = self.reasons
        if self.source_event_ids:
            payload["source_event_ids"] = self.source_event_ids
        return payload
