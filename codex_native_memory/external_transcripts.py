from __future__ import annotations

import json
import re
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .sources import SourceDefinition
from .transcripts import ParsedMessage, ParsedSession


def parse_external_file(path: str | Path, source: SourceDefinition) -> ParsedSession:
    source_path = Path(path)
    suffix = source_path.suffix.lower()
    if suffix == ".jsonl":
        return parse_generic_jsonl(source_path, source)
    if suffix == ".json":
        return parse_generic_json(source_path, source)
    return parse_generic_text(source_path, source)


def parse_generic_jsonl(path: Path, source: SourceDefinition) -> ParsedSession:
    session_id = _session_id(path, source)
    messages: list[ParsedMessage] = []
    title: str | None = None
    cwd: str | None = None
    started_at: str | None = None
    updated_at: str | None = None

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            extracted = _extract_message(item)
            if not extracted:
                continue
            role, text, timestamp = extracted
            title = title or _title(text)
            cwd = cwd or _string_from_keys(item, ("cwd", "project_path", "workspace"))
            started_at = started_at or timestamp
            updated_at = timestamp or updated_at
            messages.append(
                _message(
                    session_id,
                    len(messages),
                    role,
                    source.source_kind,
                    text,
                    timestamp,
                )
            )

    return _session(path, source, session_id, messages, title, cwd, started_at, updated_at)


def parse_generic_json(path: Path, source: SourceDefinition) -> ParsedSession:
    payload = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    session_id = _session_id(path, source)
    messages: list[ParsedMessage] = []
    title: str | None = None
    cwd = (
        _string_from_keys(payload, ("cwd", "project_path", "workspace"))
        if isinstance(payload, dict)
        else None
    )
    started_at: str | None = None
    updated_at: str | None = None

    for item in _iter_json_messages(payload):
        extracted = _extract_message(item)
        if not extracted:
            continue
        role, text, timestamp = extracted
        title = title or _title(text)
        started_at = started_at or timestamp
        updated_at = timestamp or updated_at
        messages.append(
            _message(
                session_id,
                len(messages),
                role,
                source.source_kind,
                text,
                timestamp,
            )
        )

    return _session(path, source, session_id, messages, title, cwd, started_at, updated_at)


def parse_generic_text(path: Path, source: SourceDefinition) -> ParsedSession:
    raw = path.read_text(encoding="utf-8", errors="replace")
    session_id = _session_id(path, source)
    chunks = _split_text_transcript(raw) or [("unknown", raw.strip())]
    messages = [
        _message(session_id, index, role, source.source_kind, text, None)
        for index, (role, text) in enumerate(chunks)
        if text.strip()
    ]
    title = _title(messages[0].text) if messages else path.stem
    return _session(path, source, session_id, messages, title, None, None, None)


def _session(
    path: Path,
    source: SourceDefinition,
    session_id: str,
    messages: list[ParsedMessage],
    title: str | None,
    cwd: str | None,
    started_at: str | None,
    updated_at: str | None,
) -> ParsedSession:
    return ParsedSession(
        session_id=session_id,
        source_path=str(path.resolve()),
        source_app=source.source_app,
        source_kind=source.source_kind,
        title=title,
        cwd=cwd,
        project=source.project or _project_from_path(cwd),
        started_at=started_at,
        updated_at=updated_at,
        messages=messages,
    )


def _message(
    session_id: str,
    ordinal: int,
    role: str,
    kind: str,
    text: str,
    timestamp: str | None,
) -> ParsedMessage:
    return ParsedMessage(
        session_id=session_id,
        ordinal=ordinal,
        role=_normalize_role(role),
        kind=kind,
        text=text.strip(),
        created_at=timestamp,
    )


def _extract_message(item: Any) -> tuple[str, str, str | None] | None:
    if not isinstance(item, dict):
        return None

    message = item.get("message")
    if isinstance(message, dict):
        role = str(message.get("role") or item.get("type") or "unknown")
        text = _content_to_text(message.get("content"))
        timestamp = _timestamp(item, message)
        return (role, text, timestamp) if text else None

    role = str(item.get("role") or item.get("speaker") or item.get("type") or "unknown")
    text = _content_to_text(
        item.get("content")
        or item.get("text")
        or item.get("message")
        or item.get("prompt")
        or item.get("response")
    )
    timestamp = _timestamp(item)
    return (role, text, timestamp) if text else None


def _iter_json_messages(payload: Any) -> Iterable[dict[str, Any]]:
    if isinstance(payload, list):
        yield from (item for item in payload if isinstance(item, dict))
        return
    if not isinstance(payload, dict):
        return
    for key in ("messages", "conversation", "turns", "items", "events"):
        value = payload.get(key)
        if isinstance(value, list):
            yield from (item for item in value if isinstance(item, dict))
            return
    yield payload


def _content_to_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                parts.append(_content_to_text(item.get("text") or item.get("content")))
        return "\n".join(part for part in parts if part).strip()
    if isinstance(value, dict):
        return _content_to_text(value.get("text") or value.get("content") or value.get("value"))
    return str(value).strip()


def _split_text_transcript(raw: str) -> list[tuple[str, str]]:
    pattern = re.compile(r"(?im)^\s*(user|human|assistant|ai|claude|gemini|codex|system)\s*:\s*")
    matches = list(pattern.finditer(raw))
    chunks: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(raw)
        chunks.append((match.group(1), raw[start:end].strip()))
    return chunks


def _normalize_role(value: str) -> str:
    lowered = value.lower()
    if lowered in {"user", "human", "prompt", "input"}:
        return "user"
    if lowered in {"assistant", "ai", "claude", "gemini", "codex", "response"}:
        return "assistant"
    if lowered == "system":
        return "system"
    return "unknown"


def _timestamp(*items: dict[str, Any]) -> str | None:
    for item in items:
        for key in ("timestamp", "created_at", "createdAt", "time", "date"):
            value = item.get(key)
            if isinstance(value, str):
                return value
    return None


def _string_from_keys(item: Any, keys: tuple[str, ...]) -> str | None:
    if not isinstance(item, dict):
        return None
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return None


def _session_id(path: Path, source: SourceDefinition) -> str:
    safe_path = re.sub(r"[^a-zA-Z0-9]+", "-", str(path.resolve())).strip("-")
    return f"{source.id}:{safe_path[-120:]}"


def _title(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()[:100]


def _project_from_path(cwd: str | None) -> str | None:
    return Path(cwd).name if cwd else None
