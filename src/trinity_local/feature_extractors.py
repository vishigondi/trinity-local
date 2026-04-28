from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Iterable
import re

from .session_schema import SessionMessage, SessionRecord
from .training_schema import (
    ModelDescriptor,
    OutcomeSignals,
    RawSessionRef,
    SessionFeatures,
    ToolSummary,
    TranscriptWindow,
)


def _normalize_model_id(model_id: str | None) -> tuple[str | None, str | None, str | None]:
    if not model_id:
        return None, None, None
    normalized = model_id.strip()
    family = normalized.split("-", 1)[0] if "-" in normalized else normalized
    variant = normalized[len(family) + 1 :] if normalized != family else None
    return normalized, family, variant


def _session_seconds(started_at: str | None, ended_at: str | None) -> float | None:
    if not started_at or not ended_at:
        return None
    try:
        start = datetime.fromisoformat(started_at.replace("Z", "+00:00"))
        end = datetime.fromisoformat(ended_at.replace("Z", "+00:00"))
    except ValueError:
        return None
    return max(0.0, (end - start).total_seconds())


def _first_text(messages: Iterable[SessionMessage], role: str) -> str | None:
    for message in messages:
        if message.role == role and message.text.strip():
            return message.text.strip()
    return None


def _clean_prompt_text(text: str | None) -> str | None:
    if not text:
        return None
    cleaned = text.strip()
    lowered = cleaned.lower()

    if lowered.startswith("# agents.md instructions for "):
        return None
    if lowered.startswith("<environment_context>"):
        return None
    if lowered.startswith("you are extracting durable facts about the user from their ai-usage history"):
        return cleaned

    cleaned = re.sub(r"^<environment_context>.*?</environment_context>\s*", "", cleaned, flags=re.DOTALL)
    cleaned = re.sub(r"^# agents\.md instructions for .*?\n\n", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"^<instructions>.*?</instructions>\s*", "", cleaned, flags=re.IGNORECASE | re.DOTALL)
    cleaned = re.sub(r"^\s*<[^>]+>\s*", "", cleaned)
    cleaned = cleaned.strip()
    return cleaned or None


def _is_low_signal_prompt(text: str | None) -> bool:
    if not text:
        return True
    cleaned = text.strip().lower()
    if not cleaned:
        return True
    if cleaned in {
        "status",
        "continue",
        "continue.",
        "/model",
        "/status",
        "ok",
        "sure",
        "yes",
        "no",
        "check",
    }:
        return True
    if len(cleaned) <= 8 and "\n" not in cleaned:
        return True
    return False


def _primary_user_text(messages: Iterable[SessionMessage]) -> str | None:
    candidates: list[str] = []
    for message in messages:
        if message.role != "user":
            continue
        text = message.text.strip()
        if not text:
            continue
        candidates.append(text)
    for candidate in candidates:
        cleaned = _clean_prompt_text(candidate)
        if cleaned:
            return cleaned
    return candidates[0].strip() if candidates else None


def _final_assistant_text(messages: list[SessionMessage]) -> str | None:
    for message in reversed(messages):
        if message.role == "assistant" and message.text.strip():
            return message.text.strip()
    return None


def _planner_text(messages: list[SessionMessage]) -> str | None:
    for message in messages:
        if message.role == "assistant" and message.text.strip():
            return message.text.strip()
    return None


def _summarize_tools(messages: list[SessionMessage]) -> tuple[list[ToolSummary], Counter[str], int]:
    counts: Counter[str] = Counter()
    errors: Counter[str] = Counter()
    first_command: dict[str, str] = {}
    total_errors = 0

    for message in messages:
        for call in message.tool_calls:
            name = str(call.get("name") or "unknown")
            counts[name] += 1
            args = call.get("args")
            if name not in first_command and isinstance(args, dict):
                command = args.get("command") or args.get("cmd") or args.get("description")
                if isinstance(command, str) and command.strip():
                    first_command[name] = command.strip()
            result = call.get("result")
            if isinstance(result, list):
                blob = str(result)
                if "Exit Code: 1" in blob or "Error:" in blob:
                    errors[name] += 1
                    total_errors += 1

    tools = [
        ToolSummary(name=name, count=count, error_count=errors.get(name, 0), first_command=first_command.get(name))
        for name, count in counts.items()
    ]
    return tools, counts, total_errors


def extract_session_features(session: SessionRecord) -> SessionFeatures:
    normalized_model_id, family, variant = _normalize_model_id(session.model)
    model = ModelDescriptor(
        provider=session.provider,
        raw_model_id=session.model,
        normalized_model_id=normalized_model_id,
        model_family=family,
        model_variant=variant,
        cli_name=session.cli_name,
        cli_version=session.cli_version,
        source_format_version=session.source_format_version,
    )
    tools, tool_counts, total_errors = _summarize_tools(session.messages)
    slash_commands = []
    first_user_text = _primary_user_text(session.messages)
    if not first_user_text:
        initial_message = session.metadata.get("initial_message")
        if isinstance(initial_message, str) and initial_message.strip():
            first_user_text = initial_message.strip()
    is_automated = False
    if first_user_text:
        lowered = first_user_text.lower()
        if "<scheduled-task" in lowered:
            is_automated = True
        if "extracting durable facts about the user from their ai-usage history" in lowered:
            is_automated = True
    if first_user_text:
        for line in first_user_text.splitlines():
            stripped = line.strip()
            if stripped.startswith("/"):
                slash_commands.append(stripped.split()[0])

    token_input = 0
    token_output = 0
    token_cached = 0
    did_use_web = False
    did_edit_files = False
    did_use_mcp = bool(session.metadata.get("mcp_servers"))

    for message in session.messages:
        if message.tokens:
            token_input += int(message.tokens.get("input", 0) or 0)
            token_output += int(message.tokens.get("output", 0) or 0)
            token_cached += int(message.tokens.get("cached", 0) or 0)
        for call in message.tool_calls:
            args = call.get("args")
            if isinstance(args, dict):
                blob = " ".join(str(v) for v in args.values() if isinstance(v, str))
                if "http://" in blob or "https://" in blob or "search" in blob.lower():
                    did_use_web = True
            result = call.get("result")
            if isinstance(result, list):
                blob = str(result)
                if "fileDiff" in blob or "Successfully overwrote file" in blob or "Writing to " in blob:
                    did_edit_files = True

    raw = RawSessionRef(
        source=session.provider,
        native_id=session.native_id,
        source_path=session.source_path,
        source_format=session.source_format,
        source_format_version=session.source_format_version,
        provider_session_kind=session.metadata.get("kind"),
    )
    outcome = OutcomeSignals(
        completed=bool(_final_assistant_text(session.messages)),
        assistant_turns=sum(1 for message in session.messages if message.role == "assistant"),
        user_turns=sum(1 for message in session.messages if message.role == "user"),
        tool_turns=sum(1 for message in session.messages if message.tool_calls),
        tool_calls_total=sum(tool_counts.values()),
        tool_errors_total=total_errors,
        files_touched=1 if did_edit_files else 0,
        shell_commands=tool_counts.get("run_shell_command", 0) + tool_counts.get("shell", 0),
        session_seconds=_session_seconds(session.started_at, session.ended_at),
        verifier_like=False,
        token_input=token_input or None,
        token_output=token_output or None,
        token_cached=token_cached or None,
    )

    return SessionFeatures(
        raw=raw,
        provider=session.provider,
        session_id=session.session_id,
        model=model,
        started_at=session.started_at,
        ended_at=session.ended_at,
        cwd=session.cwd,
        project_hint=session.project_hint,
        slash_commands=slash_commands or list(session.metadata.get("slash_commands", [])),
        mcp_servers=list(session.metadata.get("mcp_servers", [])),
        first_user_text=first_user_text,
        planner_text=_planner_text(session.messages),
        final_text=_final_assistant_text(session.messages),
        attachments_present=False,
        did_edit_files=did_edit_files,
        did_run_shell=outcome.shell_commands is not None and outcome.shell_commands > 0,
        did_use_web=did_use_web,
        did_use_mcp=did_use_mcp,
        retry_count=None,
        tools=tools,
        outcome=outcome,
        extra={
            **({"title": session.title} if session.title else {}),
            "is_automated": is_automated,
            "is_low_signal_prompt": _is_low_signal_prompt(first_user_text),
            "host_loop_mode": session.metadata.get("host_loop_mode"),
            "user_selected_folders": session.metadata.get("user_selected_folders"),
            "web_fetch_allowed_urls": session.metadata.get("web_fetch_allowed_urls"),
        },
    )


def make_transcript_window(features: SessionFeatures, *, task_kind_hint: str | None = None, role_hint: str | None = None) -> TranscriptWindow:
    return TranscriptWindow(
        session_id=features.session_id,
        provider=features.provider,
        source_path=features.raw.source_path,
        started_at=features.started_at,
        ended_at=features.ended_at,
        cwd=features.cwd,
        project_hint=features.project_hint,
        first_user_text=features.first_user_text,
        planner_text=features.planner_text,
        final_text=features.final_text,
        task_kind_hint=task_kind_hint,
        role_hint=role_hint,
        model=features.model,
        tools=features.tools,
        outcome=features.outcome,
        extra={
            "slash_commands": features.slash_commands,
            "mcp_servers": features.mcp_servers,
            "did_edit_files": features.did_edit_files,
            "did_run_shell": features.did_run_shell,
            "did_use_web": features.did_use_web,
            "did_use_mcp": features.did_use_mcp,
        },
    )
