from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

from .session_schema import SessionMessage, SessionRecord


def _message_text(payload: Any) -> str:
    if isinstance(payload, str):
        return payload
    if isinstance(payload, list):
        parts: list[str] = []
        for block in payload:
            if isinstance(block, dict):
                text = block.get("text")
                if isinstance(text, str) and text.strip():
                    parts.append(text)
        return "\n".join(parts).strip()
    return ""


def _extract_gemini_tool_calls(message: dict[str, Any]) -> list[dict[str, Any]]:
    tool_calls = message.get("toolCalls")
    if not isinstance(tool_calls, list):
        return []
    out: list[dict[str, Any]] = []
    for call in tool_calls:
        if not isinstance(call, dict):
            continue
        entry = {
            "id": call.get("id"),
            "name": call.get("name"),
            "args": call.get("args"),
        }
        result = call.get("result")
        if isinstance(result, list) and result:
            entry["result"] = result
        out.append(entry)
    return out


def parse_gemini_cli_session(path: Path, *, project_name: str | None = None) -> SessionRecord | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None

    if not isinstance(raw, dict):
        return None

    session_id = raw.get("sessionId")
    if not isinstance(session_id, str) or not session_id:
        return None

    messages: list[SessionMessage] = []
    model: str | None = None
    cwd = None
    project_hint = project_name

    for item in raw.get("messages", []):
        if not isinstance(item, dict):
            continue
        msg_type = item.get("type")
        timestamp = item.get("timestamp")
        if msg_type == "user":
            text = _message_text(item.get("content"))
            messages.append(
                SessionMessage(
                    role="user",
                    text=text,
                    timestamp=timestamp,
                    raw_type=msg_type,
                )
            )
        elif msg_type == "gemini":
            text = item.get("content") if isinstance(item.get("content"), str) else ""
            model = item.get("model") or model
            messages.append(
                SessionMessage(
                    role="assistant",
                    text=text,
                    timestamp=timestamp,
                    model=item.get("model"),
                    tokens=item.get("tokens") if isinstance(item.get("tokens"), dict) else {},
                    tool_calls=_extract_gemini_tool_calls(item),
                    raw_type=msg_type,
                )
            )
        elif msg_type == "info":
            text = item.get("content") if isinstance(item.get("content"), str) else ""
            messages.append(
                SessionMessage(
                    role="system",
                    text=text,
                    timestamp=timestamp,
                    raw_type=msg_type,
                )
            )

    return SessionRecord(
        provider="gemini",
        session_id=session_id,
        source_path=str(path),
        native_id=session_id,
        started_at=raw.get("startTime"),
        ended_at=raw.get("lastUpdated"),
        cwd=cwd,
        project_hint=project_hint,
        title=None,
        model=model,
        cli_name="gemini",
        cli_version=None,
        source_format="gemini_cli_chat",
        source_format_version="1",
        metadata={
            "kind": raw.get("kind"),
            "project_hash": raw.get("projectHash"),
        },
        messages=messages,
    )


def iter_gemini_cli_sessions(root: Path | None = None) -> Iterator[SessionRecord]:
    root = root or (Path.home() / ".gemini" / "tmp")
    if not root.exists():
        return
    for project_dir in sorted(root.iterdir()):
        chats_dir = project_dir / "chats"
        if not chats_dir.is_dir():
            continue
        for session_file in sorted(chats_dir.glob("session-*.json")):
            session = parse_gemini_cli_session(session_file, project_name=project_dir.name)
            if session is not None:
                yield session


def parse_claude_code_session(path: Path) -> SessionRecord | None:
    try:
        fh = path.open("r", encoding="utf-8")
    except OSError:
        return None

    session_id = path.stem
    started_at = None
    ended_at = None
    cwd = None
    cli_version = None
    model = None
    git_branch = None
    permission_mode = None
    messages: list[SessionMessage] = []

    with fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = entry.get("timestamp")
            if ts:
                started_at = started_at or ts
                ended_at = ts
            cwd = cwd or entry.get("cwd")
            cli_version = cli_version or entry.get("version")
            git_branch = git_branch or entry.get("gitBranch")
            permission_mode = permission_mode or entry.get("permissionMode")
            entry_type = entry.get("type")
            if entry_type == "user":
                content = (entry.get("message") or {}).get("content")
                text = content if isinstance(content, str) else _message_text(content)
                messages.append(
                    SessionMessage(
                        role="user",
                        text=text,
                        timestamp=ts,
                        raw_type=entry_type,
                    )
                )
            elif entry_type == "assistant":
                message = entry.get("message") or {}
                candidate_model = message.get("model")
                if isinstance(candidate_model, str) and candidate_model != "<synthetic>":
                    model = candidate_model or model
                text = _message_text(message.get("content"))
                tool_calls: list[dict[str, Any]] = []
                content = message.get("content")
                if isinstance(content, list):
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        if block.get("type") == "tool_use":
                            tool_calls.append(
                                {
                                    "id": block.get("id"),
                                    "name": block.get("name"),
                                    "args": block.get("input") if isinstance(block.get("input"), dict) else {},
                                    "result": [],
                                }
                            )
                usage = message.get("usage") if isinstance(message.get("usage"), dict) else {}
                tokens = {
                    "input": usage.get("input_tokens", 0),
                    "output": usage.get("output_tokens", 0),
                    "cached": (usage.get("cache_read_input_tokens", 0) or 0)
                    + (usage.get("cache_creation_input_tokens", 0) or 0),
                }
                messages.append(
                    SessionMessage(
                        role="assistant",
                        text=text,
                        timestamp=ts,
                        model=candidate_model if isinstance(candidate_model, str) and candidate_model != "<synthetic>" else None,
                        tokens=tokens,
                        tool_calls=tool_calls,
                        raw_type=entry_type,
                    )
                )
            elif entry_type == "system":
                text = _message_text((entry.get("message") or {}).get("content"))
                messages.append(
                    SessionMessage(
                        role="system",
                        text=text,
                        timestamp=ts,
                        raw_type=entry_type,
                    )
                )

    return SessionRecord(
        provider="claude",
        session_id=session_id,
        source_path=str(path),
        native_id=session_id,
        started_at=started_at,
        ended_at=ended_at,
        cwd=cwd,
        project_hint=path.parent.name,
        title=None,
        model=model,
        cli_name="claude",
        cli_version=cli_version,
        source_format="claude_code_jsonl",
        source_format_version="1",
        metadata={
            "git_branch": git_branch,
            "permission_mode": permission_mode,
        },
        messages=messages,
    )


def iter_claude_code_sessions(root: Path | None = None) -> Iterator[SessionRecord]:
    root = root or (Path.home() / ".claude" / "projects")
    if not root.exists():
        return
    for project_dir in sorted(root.iterdir()):
        if not project_dir.is_dir():
            continue
        for session_file in sorted(project_dir.glob("*.jsonl")):
            session = parse_claude_code_session(session_file)
            if session is not None:
                yield session


def parse_codex_session(path: Path) -> SessionRecord | None:
    try:
        fh = path.open("r", encoding="utf-8")
    except OSError:
        return None

    session_id = path.stem
    started_at = None
    ended_at = None
    cwd = None
    cli_version = None
    model = None
    model_provider = None
    messages: list[SessionMessage] = []

    with fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = entry.get("timestamp")
            if ts:
                started_at = started_at or ts
                ended_at = ts
            entry_type = entry.get("type")
            payload = entry.get("payload") or {}
            if entry_type == "session_meta":
                session_id = payload.get("id") or session_id
                cwd = payload.get("cwd") or cwd
                cli_version = payload.get("cli_version") or cli_version
                model_provider = payload.get("model_provider") or model_provider
            elif entry_type == "turn_context":
                model = payload.get("model") or model
            elif entry_type == "response_item":
                payload_type = payload.get("type")
                if payload_type == "message":
                    role = payload.get("role")
                    if role == "developer":
                        role = "system"
                    if role not in ("user", "assistant", "system"):
                        continue
                    text = _message_text(payload.get("content"))
                    messages.append(
                        SessionMessage(
                            role=role,
                            text=text,
                            timestamp=ts,
                            model=model if role == "assistant" else None,
                            raw_type=payload_type,
                        )
                    )
                elif payload_type == "reasoning":
                    summary = payload.get("summary")
                    text = ""
                    if isinstance(summary, list):
                        text = "\n".join(
                            item.get("text", "") for item in summary if isinstance(item, dict)
                        ).strip()
                    messages.append(
                        SessionMessage(
                            role="assistant",
                            text=text,
                            timestamp=ts,
                            model=model,
                            raw_type=payload_type,
                        )
                    )
                elif payload_type == "function_call":
                    args = payload.get("arguments")
                    try:
                        parsed_args = json.loads(args) if isinstance(args, str) else {}
                    except json.JSONDecodeError:
                        parsed_args = {"_raw": args}
                    messages.append(
                        SessionMessage(
                            role="assistant",
                            text="",
                            timestamp=ts,
                            model=model,
                            raw_type=payload_type,
                            tool_calls=[
                                {
                                    "id": payload.get("call_id"),
                                    "name": payload.get("name"),
                                    "args": parsed_args if isinstance(parsed_args, dict) else {},
                                    "result": [],
                                }
                            ],
                        )
                    )
                elif payload_type == "function_call_output":
                    messages.append(
                        SessionMessage(
                            role="tool",
                            text=str(payload.get("output") or ""),
                            timestamp=ts,
                            raw_type=payload_type,
                        )
                    )

    return SessionRecord(
        provider="codex",
        session_id=session_id,
        source_path=str(path),
        native_id=session_id,
        started_at=started_at,
        ended_at=ended_at,
        cwd=cwd,
        project_hint=cwd,
        title=None,
        model=model,
        cli_name="codex",
        cli_version=cli_version,
        source_format="codex_rollout_jsonl",
        source_format_version="1",
        metadata={"model_provider": model_provider},
        messages=messages,
    )


def iter_codex_sessions(root: Path | None = None) -> Iterator[SessionRecord]:
    root = root or (Path.home() / ".codex" / "sessions")
    if not root.exists():
        return
    for session_file in sorted(root.rglob("rollout-*.jsonl")):
        session = parse_codex_session(session_file)
        if session is not None:
            yield session


def parse_cowork_session(meta_path: Path) -> SessionRecord | None:
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(meta, dict):
        return None

    session_id = meta.get("sessionId")
    if not isinstance(session_id, str) or not session_id:
        return None
    session_dir = meta_path.with_suffix("")
    audit_candidates = [session_dir / "audit.jsonl", session_dir / "audit1.jsonl"]
    audit_path = next((candidate for candidate in audit_candidates if candidate.exists()), None)
    if audit_path is None:
        return None

    messages: list[SessionMessage] = []
    model = meta.get("model")
    started_at: str | None = None
    ended_at: str | None = None
    try:
        fh = audit_path.open("r", encoding="utf-8")
    except OSError:
        return None
    with fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            ts = entry.get("timestamp")
            if ts:
                started_at = started_at or ts
                ended_at = ts
            entry_type = entry.get("type")
            if entry_type == "user":
                content = (entry.get("message") or {}).get("content")
                text = content if isinstance(content, str) else _message_text(content)
                messages.append(SessionMessage(role="user", text=text, timestamp=ts, raw_type=entry_type))
            elif entry_type == "assistant":
                message = entry.get("message") or {}
                model = message.get("model") or model
                text = _message_text(message.get("content"))
                tool_calls: list[dict[str, Any]] = []
                content = message.get("content")
                if isinstance(content, list):
                    for block in content:
                        if not isinstance(block, dict):
                            continue
                        if block.get("type") == "tool_use":
                            tool_calls.append(
                                {
                                    "id": block.get("id"),
                                    "name": block.get("name"),
                                    "args": block.get("input") if isinstance(block.get("input"), dict) else {},
                                    "result": [],
                                }
                            )
                usage = message.get("usage") if isinstance(message.get("usage"), dict) else {}
                tokens = {
                    "input": usage.get("input_tokens", 0),
                    "output": usage.get("output_tokens", 0),
                    "cached": (usage.get("cache_read_input_tokens", 0) or 0)
                    + (usage.get("cache_creation_input_tokens", 0) or 0),
                }
                messages.append(
                    SessionMessage(
                        role="assistant",
                        text=text,
                        timestamp=ts,
                        model=message.get("model"),
                        tokens=tokens,
                        tool_calls=tool_calls,
                        raw_type=entry_type,
                    )
                )
            elif entry_type == "system":
                text = _message_text((entry.get("message") or {}).get("content"))
                messages.append(SessionMessage(role="system", text=text, timestamp=ts, raw_type=entry_type))

    mcp_servers = []
    for item in meta.get("remoteMcpServersConfig") or []:
        if isinstance(item, dict) and item.get("name"):
            mcp_servers.append(item["name"])

    return SessionRecord(
        provider="cowork",
        session_id=session_id,
        source_path=str(audit_path),
        native_id=session_id,
        started_at=started_at,
        ended_at=ended_at,
        cwd=meta.get("cwd"),
        project_hint=meta.get("cwd"),
        title=meta.get("title"),
        model=model,
        cli_name="claude-desktop-agent-mode",
        cli_version=None,
        source_format="cowork_audit_jsonl",
        source_format_version="1",
        metadata={
            "slash_commands": meta.get("slashCommands") if isinstance(meta.get("slashCommands"), list) else [],
            "mcp_servers": mcp_servers,
            "host_loop_mode": meta.get("hostLoopMode"),
            "web_fetch_allowed_urls": meta.get("webFetchAllowedUrls") if isinstance(meta.get("webFetchAllowedUrls"), list) else [],
            "user_selected_folders": meta.get("userSelectedFolders") if isinstance(meta.get("userSelectedFolders"), list) else [],
            "initial_message": meta.get("initialMessage"),
            "process_name": meta.get("processName"),
            "cli_session_id": meta.get("cliSessionId"),
        },
        messages=messages,
    )


def iter_cowork_sessions(root: Path | None = None) -> Iterator[SessionRecord]:
    root = root or (Path.home() / "Library" / "Application Support" / "Claude" / "local-agent-mode-sessions")
    if not root.exists():
        return
    for meta_path in sorted(root.rglob("local_*.json")):
        session = parse_cowork_session(meta_path)
        if session is not None:
            yield session
