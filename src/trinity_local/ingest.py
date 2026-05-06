from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

from .session_schema import PromptTurn, SessionMessage, SessionRecord


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
            is_sidechain = bool(entry.get("isSidechain"))
            if entry_type == "user":
                content = (entry.get("message") or {}).get("content")
                text = content if isinstance(content, str) else _message_text(content)
                extra: dict[str, Any] = {}
                if is_sidechain:
                    extra["is_sidechain"] = True
                messages.append(
                    SessionMessage(
                        role="user",
                        text=text,
                        timestamp=ts,
                        raw_type=entry_type,
                        extra=extra,
                    )
                )
            elif entry_type == "assistant":
                message = entry.get("message") or {}
                candidate_model = message.get("model")
                is_synthetic = candidate_model == "<synthetic>"
                is_api_error = bool(entry.get("isApiErrorMessage"))
                if isinstance(candidate_model, str) and not is_synthetic:
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
                extra = {}
                if is_sidechain:
                    extra["is_sidechain"] = True
                if is_synthetic:
                    extra["is_synthetic"] = True
                if is_api_error:
                    extra["is_api_error"] = True
                messages.append(
                    SessionMessage(
                        role="assistant",
                        text=text,
                        timestamp=ts,
                        model=candidate_model if isinstance(candidate_model, str) and not is_synthetic else None,
                        tokens=tokens,
                        tool_calls=tool_calls,
                        raw_type=entry_type,
                        extra=extra,
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


def _is_user_facing_prompt(message: SessionMessage) -> bool:
    if message.role != "user":
        return False
    if not message.text or not message.text.strip():
        return False
    if message.extra.get("is_sidechain"):
        return False
    return True


def _is_substantive_assistant(message: SessionMessage) -> bool:
    if message.role != "assistant":
        return False
    if message.extra.get("is_sidechain") or message.extra.get("is_api_error") or message.extra.get("is_synthetic"):
        return False
    return bool(message.text and message.text.strip())


def iter_prompt_turns(session: SessionRecord) -> Iterator[PromptTurn]:
    """Yield clean user-facing prompts from a session, ready for embedding.

    Excludes sidechain (subagent) turns, API-error responses, and empty messages.
    Each yielded turn includes the substantive assistant text immediately before
    and after, for use when constructing TurnWindow embeddings.
    """
    messages = session.messages
    user_indices = [i for i, m in enumerate(messages) if _is_user_facing_prompt(m)]
    turn_index = 0
    for msg_idx in user_indices:
        msg = messages[msg_idx]
        preceding = ""
        for j in range(msg_idx - 1, -1, -1):
            if _is_substantive_assistant(messages[j]):
                preceding = messages[j].text
                break
        following = ""
        for j in range(msg_idx + 1, len(messages)):
            if _is_substantive_assistant(messages[j]):
                following = messages[j].text
                break
        yield PromptTurn(
            transcript_id=session.session_id,
            provider=session.provider,
            source_path=session.source_path,
            turn_index=turn_index,
            text=msg.text.strip(),
            timestamp=msg.timestamp,
            preceding_assistant_text=preceding,
            following_assistant_text=following,
        )
        turn_index += 1


# ---------------------------------------------------------------------------
# Claude.ai webapp export
# ---------------------------------------------------------------------------
# Format: single JSON array of conversations.
# Each conversation: {uuid, name, summary, created_at, updated_at, account, chat_messages[]}
# Each chat_message: {uuid, text, content[], sender ("human" or null), created_at, updated_at}
# Each content block: {type:"text", text, start_timestamp, ...}


def parse_claude_ai_export(path: Path) -> Iterator[SessionRecord]:
    """Parse a Claude.ai webapp export (conversations.json).

    Yields one SessionRecord per conversation. Multi-turn structure preserved.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(raw, list):
        return

    source_path = str(path)
    for conv in raw:
        if not isinstance(conv, dict):
            continue
        session_id = conv.get("uuid")
        if not isinstance(session_id, str) or not session_id:
            continue
        messages: list[SessionMessage] = []
        for msg in conv.get("chat_messages", []):
            if not isinstance(msg, dict):
                continue
            sender = msg.get("sender")
            role = "user" if sender == "human" else "assistant"
            text = _message_text(msg.get("content")) or (
                msg.get("text") if isinstance(msg.get("text"), str) else ""
            )
            messages.append(SessionMessage(
                role=role,
                text=text,
                timestamp=msg.get("created_at"),
                raw_type=sender or "assistant",
            ))
        yield SessionRecord(
            provider="claude_ai",
            session_id=session_id,
            source_path=source_path,
            native_id=session_id,
            started_at=conv.get("created_at"),
            ended_at=conv.get("updated_at"),
            cwd=None,
            project_hint=None,
            title=(conv.get("name") or conv.get("summary") or "").strip() or None,
            model=None,
            cli_name="claude_ai_webapp",
            cli_version=None,
            source_format="claude_ai_export_json",
            source_format_version="1",
            metadata={},
            messages=messages,
        )


# ---------------------------------------------------------------------------
# ChatGPT webapp export
# ---------------------------------------------------------------------------
# Format: single JSON array of conversations.
# Each conversation has `mapping` (node graph) + `current_node`.
# To get linear order: walk parent links from current_node back to root, then reverse.


def _chatgpt_extract_text(content: Any) -> str:
    """Extract user-facing text from a ChatGPT message.content payload.

    content is typically: {content_type, parts: [str|dict]} OR a multimodal list.
    """
    if not isinstance(content, dict):
        return ""
    parts = content.get("parts")
    if not isinstance(parts, list):
        return ""
    chunks: list[str] = []
    for part in parts:
        if isinstance(part, str):
            stripped = part.strip()
            if stripped:
                chunks.append(stripped)
        elif isinstance(part, dict):
            text = part.get("text") or part.get("content") or ""
            if isinstance(text, str) and text.strip():
                chunks.append(text)
    return "\n".join(chunks).strip()


def parse_chatgpt_export(path: Path) -> Iterator[SessionRecord]:
    """Parse a ChatGPT webapp export (conversations*.json).

    Yields one SessionRecord per conversation. Walks the node tree from
    current_node back to root via parent links, then reverses for linear order.
    """
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    if not isinstance(raw, list):
        return

    source_path = str(path)
    for conv in raw:
        if not isinstance(conv, dict):
            continue
        conv_id = conv.get("conversation_id") or conv.get("id")
        if not isinstance(conv_id, str) or not conv_id:
            continue
        mapping = conv.get("mapping")
        if not isinstance(mapping, dict):
            continue
        current_id = conv.get("current_node")
        if not isinstance(current_id, str) or current_id not in mapping:
            # Fall back: iterate mapping in insertion order
            ordered_ids = list(mapping.keys())
        else:
            ordered_ids = []
            seen: set[str] = set()
            cursor = current_id
            while cursor and cursor in mapping and cursor not in seen:
                seen.add(cursor)
                ordered_ids.append(cursor)
                node = mapping[cursor]
                cursor = node.get("parent") if isinstance(node, dict) else None
            ordered_ids.reverse()

        messages: list[SessionMessage] = []
        model: str | None = None
        for node_id in ordered_ids:
            node = mapping.get(node_id)
            if not isinstance(node, dict):
                continue
            msg = node.get("message")
            if not isinstance(msg, dict):
                continue
            author = msg.get("author") if isinstance(msg.get("author"), dict) else {}
            role = author.get("role")
            if role not in ("user", "assistant", "system", "tool"):
                continue
            text = _chatgpt_extract_text(msg.get("content"))
            if not text and role != "user":
                continue
            metadata = msg.get("metadata") if isinstance(msg.get("metadata"), dict) else {}
            model_slug = metadata.get("model_slug") or metadata.get("default_model_slug")
            if isinstance(model_slug, str) and not model:
                model = model_slug
            create_time = msg.get("create_time")
            timestamp = None
            if isinstance(create_time, (int, float)):
                from datetime import datetime, timezone

                timestamp = datetime.fromtimestamp(create_time, tz=timezone.utc).isoformat()
            messages.append(SessionMessage(
                role=role,
                text=text,
                timestamp=timestamp,
                model=model_slug if isinstance(model_slug, str) else None,
                raw_type=role,
            ))

        create_time = conv.get("create_time")
        update_time = conv.get("update_time")
        from datetime import datetime, timezone

        started_at = (
            datetime.fromtimestamp(create_time, tz=timezone.utc).isoformat()
            if isinstance(create_time, (int, float))
            else None
        )
        ended_at = (
            datetime.fromtimestamp(update_time, tz=timezone.utc).isoformat()
            if isinstance(update_time, (int, float))
            else None
        )
        yield SessionRecord(
            provider="chatgpt",
            session_id=conv_id,
            source_path=source_path,
            native_id=conv_id,
            started_at=started_at,
            ended_at=ended_at,
            cwd=None,
            project_hint=None,
            title=(conv.get("title") or "").strip() or None,
            model=model or conv.get("default_model_slug"),
            cli_name="chatgpt_webapp",
            cli_version=None,
            source_format="chatgpt_export_json",
            source_format_version="1",
            metadata={},
            messages=messages,
        )


# ---------------------------------------------------------------------------
# Gemini Takeout HTML (Google "My Activity" Material Design Lite export)
# ---------------------------------------------------------------------------
# Each `outer-cell` is one prompt + response activity entry.
# Google flattens multi-turn conversations into independent entries — each
# one becomes a 2-message session (user prompt + assistant response).


import re as _re


_GEMINI_OUTER_RE = _re.compile(
    r'<div class="outer-cell mdl-cell mdl-cell--12-col mdl-shadow--2dp">(.*?)</div></div></div>',
    _re.DOTALL,
)
_GEMINI_CONTENT_CELL_RE = _re.compile(
    r'<div class="content-cell mdl-cell mdl-cell--6-col mdl-typography--body-1">(.*?)</div>',
    _re.DOTALL,
)
_GEMINI_TAG_RE = _re.compile(r"<[^>]+>")
_GEMINI_WS_RE = _re.compile(r"\s+")
_GEMINI_TS_RE = _re.compile(
    r"([A-Z][a-z]{2}\s+\d{1,2},\s+\d{4},\s+\d{1,2}:\d{2}(?::\d{2})?\s*[AP]M(?:\s+[A-Z]{2,4})?)"
)
_GEMINI_TZ_OFFSETS = {
    "UTC": 0, "GMT": 0,
    "EDT": -4, "EST": -5,
    "CDT": -5, "CST": -6,
    "MDT": -6, "MST": -7,
    "PDT": -7, "PST": -8,
}


def _gemini_parse_takeout_timestamp(s: str) -> str | None:
    """Parse 'Apr 12, 2026, 3:34:31 PM EDT' → ISO8601 UTC."""
    import html as _html_mod
    from datetime import datetime, timedelta, timezone

    s = _html_mod.unescape(s).strip()
    tz_offset = 0
    for code, offset in _GEMINI_TZ_OFFSETS.items():
        if s.endswith(code):
            s = s[: -len(code)].strip()
            tz_offset = offset
            break
    for fmt in ("%b %d, %Y, %I:%M:%S %p", "%b %d, %Y, %I:%M %p"):
        try:
            dt = datetime.strptime(s, fmt)
            dt = dt.replace(tzinfo=timezone.utc) - timedelta(hours=tz_offset)
            return dt.isoformat().replace("+00:00", "Z")
        except ValueError:
            continue
    return None


def _gemini_strip_html(s: str) -> str:
    import html as _html_mod

    s = _GEMINI_TAG_RE.sub(" ", s)
    s = _html_mod.unescape(s)
    s = _GEMINI_WS_RE.sub(" ", s).strip()
    return s


# Group consecutive Gemini Takeout cells into one SessionRecord when they
# occur within this many seconds of each other. Google flattens multi-turn
# conversations into independent cells, but the timestamps on consecutive
# cells reveal the original threading: turns within a single conversation
# typically land seconds-to-minutes apart, while a new conversation usually
# starts hours later.
GEMINI_TAKEOUT_SESSION_GAP_SECONDS = 30 * 60  # 30 minutes


def _parse_gemini_takeout_cells(raw: str) -> list[dict]:
    """Extract every outer-cell as a dict: {prompt, response, ts_iso, native_id}."""
    cells: list[dict] = []
    for match in _GEMINI_OUTER_RE.finditer(raw):
        cell_html = match.group(1)
        content_cells = _GEMINI_CONTENT_CELL_RE.findall(cell_html)
        if not content_cells:
            continue
        main = content_cells[0]
        p_match = _re.search(r"<p>(.*?)</p>", main, _re.DOTALL)
        response_text = _gemini_strip_html(p_match.group(1)) if p_match else ""
        head = main[: p_match.start()] if p_match else main

        ts_match = _GEMINI_TS_RE.search(head)
        ts_iso = _gemini_parse_takeout_timestamp(ts_match.group(1)) if ts_match else None

        prompt_html = head
        if ts_match:
            prompt_html = prompt_html.replace(ts_match.group(1), "")
        prompt_text = _gemini_strip_html(prompt_html)
        if prompt_text.startswith("Prompted "):
            prompt_text = prompt_text[len("Prompted "):]
        prompt_text = prompt_text.replace("Audio included.", "").strip()

        if not prompt_text and not response_text:
            continue

        native_id_match = _re.search(r'href="https?://[^"]+/([^/"]+)"', head)
        native_id = native_id_match.group(1) if native_id_match else (ts_iso or "")
        if not native_id:
            continue

        cells.append({
            "prompt": prompt_text,
            "response": response_text,
            "ts_iso": ts_iso,
            "native_id": native_id,
        })
    return cells


def _group_cells_into_sessions(cells: list[dict]) -> list[list[dict]]:
    """Group time-adjacent cells into sessions.

    Cells in the Takeout HTML are in reverse-chronological order. Sort
    ascending by timestamp, then start a new group whenever the gap to the
    previous cell exceeds GEMINI_TAKEOUT_SESSION_GAP_SECONDS or whenever
    a timestamp is missing.
    """
    from datetime import datetime

    def parse_ts(value: str | None) -> datetime | None:
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    timed = [(parse_ts(c["ts_iso"]), c) for c in cells]
    timed.sort(key=lambda pair: pair[0] or datetime.max)

    groups: list[list[dict]] = []
    current: list[dict] = []
    last_ts: object = None
    for ts, cell in timed:
        if not current:
            current = [cell]
            last_ts = ts
            continue
        gap = None
        if ts is not None and last_ts is not None:
            gap = (ts - last_ts).total_seconds()
        if gap is None or gap > GEMINI_TAKEOUT_SESSION_GAP_SECONDS:
            groups.append(current)
            current = [cell]
        else:
            current.append(cell)
        last_ts = ts
    if current:
        groups.append(current)
    return groups


def parse_gemini_takeout_html(path: Path) -> Iterator[SessionRecord]:
    """Parse a Gemini Takeout MyActivity.html file.

    Each outer-cell is one prompt+response activity entry. Google flattens
    multi-turn conversations into independent cells, but the timestamps reveal
    the original threading. We group cells whose gap is <30min into a single
    SessionRecord so downstream consumers see proper multi-turn context
    (preceding/following assistant turns).
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError:
        return
    source_path = str(path)
    cells = _parse_gemini_takeout_cells(raw)
    if not cells:
        return

    for group in _group_cells_into_sessions(cells):
        if not group:
            continue
        first_native_id = group[0]["native_id"]
        session_id = f"gemini_takeout_{first_native_id}"
        first_ts = group[0]["ts_iso"]
        last_ts = group[-1]["ts_iso"]
        title_source = group[0]["prompt"] or group[0]["response"] or ""

        messages: list[SessionMessage] = []
        for cell in group:
            if cell["prompt"]:
                messages.append(SessionMessage(
                    role="user",
                    text=cell["prompt"],
                    timestamp=cell["ts_iso"],
                    raw_type="user",
                ))
            if cell["response"]:
                messages.append(SessionMessage(
                    role="assistant",
                    text=cell["response"],
                    timestamp=cell["ts_iso"],
                    raw_type="assistant",
                ))
        if not messages:
            continue

        yield SessionRecord(
            provider="gemini",
            session_id=session_id,
            source_path=source_path,
            native_id=first_native_id,
            started_at=first_ts,
            ended_at=last_ts,
            cwd=None,
            project_hint=None,
            title=(title_source[:80] if title_source else None),
            model=None,
            cli_name="gemini_takeout",
            cli_version=None,
            source_format="gemini_takeout_html",
            source_format_version="2",  # multi-turn grouping
            metadata={"cell_count": len(group)},
            messages=messages,
        )
