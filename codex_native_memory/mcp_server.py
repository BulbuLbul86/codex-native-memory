from __future__ import annotations

import json
import sys
from dataclasses import asdict
from typing import Any, BinaryIO

from . import __version__
from .bootstrap import bootstrap_memory
from .db import MemoryDB
from .ingest import backfill, backfill_configured_sources
from .sources import load_sources, review_options

TOOLS: list[dict[str, Any]] = [
    {
        "name": "memory_search",
        "description": (
            "Search imported Codex conversations, summaries, observations, and memories."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
                "kind": {
                    "type": "string",
                    "enum": [
                        "all",
                        "messages",
                        "prompts",
                        "answers",
                        "summaries",
                        "observations",
                        "memories",
                    ],
                    "default": "all",
                },
            },
            "required": ["query"],
        },
    },
    {
        "name": "memory_recent",
        "description": "List recent imported Codex sessions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10}
            },
        },
    },
    {
        "name": "memory_context",
        "description": (
            "Build project-oriented memory context: summaries, decisions, open questions, "
            "observations, recent sessions, and optional query matches."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "project": {"type": "string"},
                "cwd": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
            },
        },
    },
    {
        "name": "memory_bootstrap",
        "description": (
            "Import recent memory, summarize pending sessions, and return a dynamic "
            "project profile plus project-oriented context."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "project": {"type": "string"},
                "cwd": {"type": "string"},
                "context_limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 5},
                "import_limit": {"type": "integer", "minimum": 0, "maximum": 1000, "default": 100},
                "summary_limit": {"type": "integer", "minimum": 0, "maximum": 100, "default": 5},
                "summary_mode": {
                    "type": "string",
                    "enum": ["auto", "codex", "extractive"],
                    "default": "extractive",
                },
                "force": {"type": "boolean", "default": False},
                "source_id": {"type": "string"},
                "all_sources": {"type": "boolean", "default": False},
            },
        },
    },
    {
        "name": "memory_import",
        "description": "Import changed Codex transcript JSONL files into memory.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "minimum": 1, "maximum": 1000},
                "force": {"type": "boolean", "default": False},
                "source_id": {"type": "string"},
                "all_sources": {"type": "boolean", "default": False},
            },
        },
    },
    {
        "name": "memory_remember",
        "description": "Store a pinned memory item for future Codex project bootstrap/context.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "text": {"type": "string"},
                "scope": {
                    "type": "string",
                    "enum": ["user", "project", "workflow"],
                    "default": "project",
                },
                "subject": {"type": "string", "default": "general"},
                "project": {"type": "string"},
                "cwd": {"type": "string"},
                "source": {"type": "string", "default": "manual"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1, "default": 1},
            },
            "required": ["text"],
        },
    },
    {
        "name": "memory_notes",
        "description": "List pinned memory items for a project/cwd, including global user memory.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string"},
                "cwd": {"type": "string"},
                "scope": {"type": "string", "enum": ["user", "project", "workflow"]},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100, "default": 20},
            },
        },
    },
    {
        "name": "memory_update",
        "description": "Update a pinned memory item by id.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "integer", "minimum": 1},
                "text": {"type": "string"},
                "scope": {"type": "string", "enum": ["user", "project", "workflow"]},
                "subject": {"type": "string"},
                "project": {"type": "string"},
                "cwd": {"type": "string"},
                "source": {"type": "string"},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["id"],
        },
    },
    {
        "name": "memory_export",
        "description": "Export pinned memory and a computed project profile as a JSON bundle.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "project": {"type": "string"},
                "cwd": {"type": "string"},
                "scope": {"type": "string", "enum": ["user", "project", "workflow"]},
                "limit": {"type": "integer", "minimum": 1, "maximum": 1000, "default": 100},
                "include_profile": {"type": "boolean", "default": True},
            },
        },
    },
    {
        "name": "memory_import_bundle",
        "description": (
            "Import pinned memory items from a memory_export JSON bundle. "
            "Provide payload or payload_json."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "payload": {"type": "object"},
                "payload_json": {"type": "string"},
                "project": {"type": "string"},
                "cwd": {"type": "string"},
                "source": {"type": "string", "default": "import"},
            },
        },
    },
    {
        "name": "memory_forget",
        "description": "Delete a pinned memory item by id.",
        "inputSchema": {
            "type": "object",
            "properties": {"id": {"type": "integer", "minimum": 1}},
            "required": ["id"],
        },
    },
    {
        "name": "memory_sources",
        "description": "List attached AI sources and external review targets.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "review-options"],
                    "default": "list",
                }
            },
        },
    },
    {
        "name": "memory_health",
        "description": "Show Codex Native Memory database health and counts.",
        "inputSchema": {"type": "object", "properties": {}},
    },
]


def serve(
    db: MemoryDB | None = None,
    stdin: BinaryIO | None = None,
    stdout: BinaryIO | None = None,
) -> None:
    database = db
    transport = StdioTransport(stdin or sys.stdin.buffer, stdout or sys.stdout.buffer)
    while True:
        message = transport.read_message()
        if message is None:
            break
        if database is None and message.get("method") == "tools/call":
            database = MemoryDB()
        response = handle_message(database, message)
        if response is not None:
            transport.write_message(response)


def handle_message(db: MemoryDB | None, message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    request_id = message.get("id")
    if method is None and request_id is None:
        return None
    if method and method.startswith("notifications/"):
        return None
    try:
        result: dict[str, Any]
        if method == "initialize":
            result = {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "codex-native-memory", "version": __version__},
            }
        elif method == "ping":
            result = {}
        elif method == "tools/list":
            result = {"tools": TOOLS}
        elif method == "tools/call":
            if db is None:
                db = MemoryDB()
            result = call_tool(db, message.get("params") or {})
        else:
            return _error(request_id, -32601, f"Unknown method: {method}")
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    except Exception as exc:
        return _error(request_id, -32000, str(exc))


def call_tool(db: MemoryDB, params: dict[str, Any]) -> dict[str, Any]:
    name = params.get("name")
    arguments = params.get("arguments") or {}
    payload: Any
    if name == "memory_search":
        query = str(arguments.get("query") or "")
        limit = int(arguments.get("limit") or 10)
        kind = str(arguments.get("kind") or "all")
        payload = db.search(query, limit=limit, kind=kind)
    elif name == "memory_recent":
        limit = int(arguments.get("limit") or 10)
        payload = db.recent_sessions(limit=limit)
    elif name == "memory_context":
        limit = int(arguments.get("limit") or 5)
        payload = db.project_context(
            project=_optional_string(arguments.get("project")),
            cwd=_optional_string(arguments.get("cwd")),
            query=_optional_string(arguments.get("query")),
            limit=limit,
        )
    elif name == "memory_bootstrap":
        payload = bootstrap_memory(
            db,
            data_root=db.path.parent,
            project=_optional_string(arguments.get("project")),
            cwd=_optional_string(arguments.get("cwd")),
            query=_optional_string(arguments.get("query")),
            context_limit=int(arguments.get("context_limit") or 5),
            import_limit=_optional_int(arguments.get("import_limit"), default=100),
            summary_limit=_optional_int(arguments.get("summary_limit"), default=5) or 0,
            summary_mode=str(arguments.get("summary_mode") or "extractive"),
            force=bool(arguments.get("force") or False),
            source_id=_optional_string(arguments.get("source_id")),
            all_sources=bool(arguments.get("all_sources") or False),
        )
    elif name == "memory_import":
        raw_limit = arguments.get("limit")
        source_id = arguments.get("source_id")
        if source_id or bool(arguments.get("all_sources") or False):
            payload = backfill_configured_sources(
                db,
                source_id=str(source_id) if source_id else None,
                limit=int(raw_limit) if raw_limit is not None else None,
                force=bool(arguments.get("force") or False),
                data_root=db.path.parent,
            )
        else:
            payload = backfill(
                db,
                limit=int(raw_limit) if raw_limit is not None else None,
                force=bool(arguments.get("force") or False),
                data_root=db.path.parent,
            )
    elif name == "memory_remember":
        payload = db.remember(
            str(arguments.get("text") or ""),
            scope=str(arguments.get("scope") or "project"),
            subject=str(arguments.get("subject") or "general"),
            project=_optional_string(arguments.get("project")),
            cwd=_optional_string(arguments.get("cwd")),
            source=str(arguments.get("source") or "manual"),
            confidence=float(arguments.get("confidence") or 1.0),
        )
    elif name == "memory_notes":
        payload = db.memory_items(
            project=_optional_string(arguments.get("project")),
            cwd=_optional_string(arguments.get("cwd")),
            scope=_optional_string(arguments.get("scope")),
            limit=int(arguments.get("limit") or 20),
        )
    elif name == "memory_update":
        payload = db.update_memory(
            int(arguments.get("id") or 0),
            text=_optional_string(arguments.get("text")),
            scope=_optional_string(arguments.get("scope")),
            subject=_optional_string(arguments.get("subject")),
            project=_optional_string(arguments.get("project")),
            cwd=_optional_string(arguments.get("cwd")),
            source=_optional_string(arguments.get("source")),
            confidence=_optional_float(arguments.get("confidence")),
        )
    elif name == "memory_export":
        payload = db.export_bundle(
            project=_optional_string(arguments.get("project")),
            cwd=_optional_string(arguments.get("cwd")),
            scope=_optional_string(arguments.get("scope")),
            limit=int(arguments.get("limit") or 100),
            include_profile=bool(arguments.get("include_profile", True)),
        )
    elif name == "memory_import_bundle":
        raw_payload = arguments.get("payload")
        if raw_payload is None:
            payload_json = _optional_string(arguments.get("payload_json"))
            if payload_json is None:
                raise ValueError("memory_import_bundle requires payload or payload_json.")
            raw_payload = json.loads(payload_json)
        payload = db.import_bundle(
            raw_payload,
            project=_optional_string(arguments.get("project")),
            cwd=_optional_string(arguments.get("cwd")),
            source=str(arguments.get("source") or "import"),
        )
    elif name == "memory_forget":
        memory_id = int(arguments.get("id") or 0)
        payload = {"id": memory_id, "deleted": db.forget_memory(memory_id)}
    elif name == "memory_sources":
        config = load_sources(db.path.parent)
        action = str(arguments.get("action") or "list")
        if action == "review-options":
            payload = review_options(config)
        else:
            default_source = config.default_coding_source()
            payload = {
                "primary_coding_ai": asdict(default_source) if default_source is not None else None,
                "sources": [asdict(source) for source in config.sources],
            }
    elif name == "memory_health":
        payload = db.stats()
    else:
        raise ValueError(f"Unknown tool: {name}")
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    return {"content": [{"type": "text", "text": text}]}


class StdioTransport:
    def __init__(self, stdin: BinaryIO, stdout: BinaryIO):
        self.stdin = stdin
        self.stdout = stdout

    def read_message(self) -> dict[str, Any] | None:
        first = self.stdin.readline()
        if not first:
            return None
        if first.lower().startswith(b"content-length:"):
            length = int(first.split(b":", 1)[1].strip())
            while True:
                header = self.stdin.readline()
                if header in {b"\r\n", b"\n", b""}:
                    break
            body = self.stdin.read(length)
            if not body:
                return None
            return json.loads(body.decode("utf-8"))
        return json.loads(first.decode("utf-8"))

    def write_message(self, message: dict[str, Any]) -> None:
        body = json.dumps(message, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.stdout.write(body + b"\n")
        self.stdout.flush()


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def _optional_string(value: Any) -> str | None:
    text = str(value).strip() if value is not None else ""
    return text or None


def _optional_int(value: Any, *, default: int | None = None) -> int | None:
    if value is None:
        return default
    return int(value)


def _optional_float(value: Any) -> float | None:
    if value is None:
        return None
    return float(value)
