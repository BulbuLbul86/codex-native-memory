from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass(slots=True)
class ParsedMessage:
    session_id: str
    ordinal: int
    role: str
    kind: str
    text: str
    created_at: str | None = None


@dataclass(slots=True)
class ParsedToolEvent:
    session_id: str
    ordinal: int
    kind: str
    name: str | None = None
    call_id: str | None = None
    input_text: str | None = None
    output_text: str | None = None
    created_at: str | None = None


@dataclass(slots=True)
class ParsedSession:
    session_id: str
    source_path: str
    source_app: str = "codex"
    source_kind: str = "codex-jsonl"
    title: str | None = None
    cwd: str | None = None
    project: str | None = None
    started_at: str | None = None
    updated_at: str | None = None
    messages: list[ParsedMessage] = field(default_factory=list)
    tool_events: list[ParsedToolEvent] = field(default_factory=list)
    internal: bool = False


def parse_jsonl_file(
    path: str | os.PathLike[str],
    *,
    internal_roots: list[str | os.PathLike[str]] | None = None,
) -> ParsedSession:
    transcript_path = Path(path)
    session_id: str | None = None
    cwd: str | None = None
    started_at: str | None = None
    updated_at: str | None = None
    messages: list[ParsedMessage] = []
    tool_events: list[ParsedToolEvent] = []
    seen_messages: set[tuple[str, str]] = set()

    def sid() -> str:
        return session_id or transcript_path.stem

    def add_message(role: str, kind: str, text: str | None, created_at: str | None) -> None:
        clean = _compact_text(text)
        if not clean:
            return
        key = (role, clean)
        if key in seen_messages:
            return
        seen_messages.add(key)
        messages.append(
            ParsedMessage(
                session_id=sid(),
                ordinal=len(messages),
                role=role,
                kind=kind,
                text=clean,
                created_at=created_at,
            )
        )

    def add_tool(
        kind: str,
        *,
        name: str | None = None,
        call_id: str | None = None,
        input_text: Any = None,
        output_text: Any = None,
        created_at: str | None = None,
    ) -> None:
        tool_events.append(
            ParsedToolEvent(
                session_id=sid(),
                ordinal=len(tool_events),
                kind=kind,
                name=name,
                call_id=call_id,
                input_text=_value_to_text(input_text),
                output_text=_value_to_text(output_text),
                created_at=created_at,
            )
        )

    with transcript_path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue

            timestamp = _event_timestamp(event)
            started_at = started_at or timestamp
            updated_at = timestamp or updated_at
            event_type = event.get("type")
            payload = event.get("payload")
            if not isinstance(payload, dict):
                payload = {}

            if event_type == "session_meta":
                if session_id is None:
                    session_id = payload.get("id") or payload.get("session_id") or session_id
                cwd = payload.get("cwd") or cwd
                continue

            if event_type == "turn_context":
                cwd = payload.get("cwd") or cwd
                continue

            if event_type == "event_msg":
                payload_type = payload.get("type")
                if payload_type == "user_message":
                    add_message("user", "user_message", payload.get("message"), timestamp)
                elif payload_type == "agent_message":
                    add_message("assistant", "agent_message", payload.get("message"), timestamp)
                elif payload_type == "task_complete":
                    text = payload.get("last_agent_message") or payload.get("message")
                    add_message("assistant", "task_complete", text, timestamp)
                continue

            if event_type == "response_item":
                item_type = payload.get("type")
                if item_type == "message":
                    role = payload.get("role") or "assistant"
                    if role not in {"user", "assistant"}:
                        continue
                    text = _extract_content_text(payload.get("content"))
                    if not (role == "user" and _looks_like_context(text)):
                        add_message(role, "response_item", text, timestamp)
                elif item_type in {"function_call", "custom_tool_call"}:
                    add_tool(
                        item_type,
                        name=payload.get("name") or payload.get("tool_name"),
                        call_id=payload.get("call_id") or payload.get("id"),
                        input_text=payload.get("arguments") or payload.get("input"),
                        created_at=timestamp,
                    )
                elif item_type in {"function_call_output", "custom_tool_call_output"}:
                    add_tool(
                        item_type,
                        name=payload.get("name"),
                        call_id=payload.get("call_id") or payload.get("id"),
                        output_text=payload.get("output") or payload.get("result"),
                        created_at=timestamp,
                    )
                elif item_type == "web_search_call":
                    add_tool(
                        item_type,
                        name="web_search",
                        call_id=payload.get("id"),
                        input_text=payload,
                        created_at=timestamp,
                    )
                continue

            if event_type == "user_message":
                add_message("user", "user_message", payload.get("message"), timestamp)
            elif event_type == "agent_message":
                add_message("assistant", "agent_message", payload.get("message"), timestamp)
            elif event_type == "task_complete":
                text = payload.get("last_agent_message") or payload.get("message")
                add_message("assistant", "task_complete", text, timestamp)

    final_session_id = session_id or transcript_path.stem
    for message in messages:
        message.session_id = final_session_id
    for tool_event in tool_events:
        tool_event.session_id = final_session_id

    title = _title_from_messages(messages)
    project = _project_name(cwd)
    internal = _is_under_any(cwd, internal_roots or [])

    return ParsedSession(
        session_id=final_session_id,
        source_path=str(transcript_path.resolve()),
        source_app="codex",
        source_kind="codex-jsonl",
        title=title,
        cwd=cwd,
        project=project,
        started_at=started_at,
        updated_at=updated_at,
        messages=messages,
        tool_events=tool_events,
        internal=internal,
    )


def _event_timestamp(event: dict[str, Any]) -> str | None:
    payload = event.get("payload")
    if isinstance(payload, dict) and isinstance(payload.get("timestamp"), str):
        return payload["timestamp"]
    if isinstance(event.get("timestamp"), str):
        return event["timestamp"]
    return None


def _extract_content_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, dict):
        return _extract_content_text([content])
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
            continue
        if not isinstance(item, dict):
            continue
        for key in ("text", "output_text", "input_text", "message"):
            value = item.get(key)
            if isinstance(value, str):
                parts.append(value)
                break
    return "\n".join(part for part in parts if part)


def _value_to_text(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return str(value)


def _compact_text(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\n{3,}", "\n\n", text.strip())


def _looks_like_context(text: str) -> bool:
    stripped = text.lstrip()
    context_prefixes = (
        "<environment_context>",
        "<permissions instructions>",
        "<system",
        "<developer",
        "<skills_instructions>",
        "<plugins_instructions>",
        "<app-context>",
        "<turn_aborted>",
    )
    return stripped.startswith(context_prefixes)


def _title_from_messages(messages: list[ParsedMessage]) -> str | None:
    for message in messages:
        if message.role == "user":
            one_line = re.sub(r"\s+", " ", message.text).strip()
            return one_line[:100]
    return None


def _project_name(cwd: str | None) -> str | None:
    if not cwd:
        return None
    name = Path(cwd).name
    return name or cwd


def _is_under_any(candidate: str | None, roots: list[str | os.PathLike[str]]) -> bool:
    if not candidate:
        return False
    normalized = os.path.normcase(os.path.abspath(os.path.expanduser(candidate)))
    for root in roots:
        root_norm = os.path.normcase(os.path.abspath(os.path.expanduser(os.fspath(root))))
        if normalized == root_norm or normalized.startswith(root_norm + os.sep):
            return True
    return False
