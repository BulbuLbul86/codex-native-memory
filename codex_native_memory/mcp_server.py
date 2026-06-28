from __future__ import annotations

import json
import sys
from dataclasses import asdict
from typing import Any, BinaryIO

from . import __version__
from .db import MemoryDB
from .ingest import backfill, backfill_configured_sources
from .sources import load_sources, review_options

TOOLS: list[dict[str, Any]] = [
    {
        "name": "memory_search",
        "description": "Search imported Codex conversations, summaries, and observations.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 50, "default": 10},
                "kind": {
                    "type": "string",
                    "enum": ["all", "messages", "prompts", "answers", "summaries", "observations"],
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
    database = db or MemoryDB()
    transport = StdioTransport(stdin or sys.stdin.buffer, stdout or sys.stdout.buffer)
    while True:
        message = transport.read_message()
        if message is None:
            break
        response = handle_message(database, message)
        if response is not None:
            transport.write_message(response)


def handle_message(db: MemoryDB, message: dict[str, Any]) -> dict[str, Any] | None:
    method = message.get("method")
    request_id = message.get("id")
    if method and method.startswith("notifications/"):
        return None
    try:
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
            result = call_tool(db, message.get("params") or {})
        else:
            return _error(request_id, -32601, f"Unknown method: {method}")
        return {"jsonrpc": "2.0", "id": request_id, "result": result}
    except Exception as exc:
        return _error(request_id, -32000, str(exc))


def call_tool(db: MemoryDB, params: dict[str, Any]) -> dict[str, Any]:
    name = params.get("name")
    arguments = params.get("arguments") or {}
    if name == "memory_search":
        query = str(arguments.get("query") or "")
        limit = int(arguments.get("limit") or 10)
        kind = str(arguments.get("kind") or "all")
        payload = db.search(query, limit=limit, kind=kind)
    elif name == "memory_recent":
        limit = int(arguments.get("limit") or 10)
        payload = db.recent_sessions(limit=limit)
    elif name == "memory_import":
        limit = arguments.get("limit")
        source_id = arguments.get("source_id")
        if source_id or bool(arguments.get("all_sources") or False):
            payload = backfill_configured_sources(
                db,
                source_id=str(source_id) if source_id else None,
                limit=int(limit) if limit is not None else None,
                force=bool(arguments.get("force") or False),
                data_root=db.path.parent,
            )
        else:
            payload = backfill(
                db,
                limit=int(limit) if limit is not None else None,
                force=bool(arguments.get("force") or False),
                data_root=db.path.parent,
            )
    elif name == "memory_sources":
        config = load_sources(db.path.parent)
        action = str(arguments.get("action") or "list")
        if action == "review-options":
            payload = review_options(config)
        else:
            payload = {
                "primary_coding_ai": (
                    asdict(config.default_coding_source())
                    if config.default_coding_source()
                    else None
                ),
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
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        self.stdout.write(header + body)
        self.stdout.flush()


def _error(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}
