from __future__ import annotations

import json
import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from codex_native_memory.db import MemoryDB
from codex_native_memory.mcp_server import handle_message, serve
from codex_native_memory.transcripts import ParsedMessage, ParsedSession


def _frame(payload: dict[str, object]) -> bytes:
    body = json.dumps(payload).encode("utf-8")
    return b"Content-Length: " + str(len(body)).encode("ascii") + b"\r\n\r\n" + body


def _line(payload: dict[str, object]) -> bytes:
    return json.dumps(payload).encode("utf-8") + b"\n"


class McpServerTests(unittest.TestCase):
    def test_serve_lists_tools_without_opening_memory_db(self) -> None:
        initialize = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "test", "version": "0"},
            },
        }
        tools_list = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        stdin = BytesIO(_frame(initialize) + _frame(tools_list))
        stdout = BytesIO()

        with patch(
            "codex_native_memory.mcp_server.MemoryDB",
            side_effect=AssertionError("tools/list should not open the memory database"),
        ):
            serve(stdin=stdin, stdout=stdout)

        output = stdout.getvalue()
        self.assertNotIn(b"Content-Length", output)
        self.assertIn(b"codex-native-memory", output)
        self.assertIn(b"memory_search", output)

    def test_serve_supports_json_lines_transport_used_by_codex(self) -> None:
        initialize = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}}
        initialized = {
            "jsonrpc": "2.0",
            "method": "notifications/initialized",
            "params": {},
        }
        tools_list = {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}
        stdin = BytesIO(_line(initialize) + _line(initialized) + _line(tools_list))
        stdout = BytesIO()

        with patch(
            "codex_native_memory.mcp_server.MemoryDB",
            side_effect=AssertionError("tools/list should not open the memory database"),
        ):
            serve(stdin=stdin, stdout=stdout)

        messages = [
            json.loads(line)
            for line in stdout.getvalue().splitlines()
            if line.strip()
        ]
        self.assertEqual([message["id"] for message in messages], [1, 2])
        self.assertEqual(messages[0]["result"]["serverInfo"]["name"], "codex-native-memory")
        self.assertIn("tools", messages[1]["result"])

    def test_tools_list_and_memory_search_return_json_rpc_results(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = MemoryDB(Path(tmp) / "memory.sqlite3")
            db.replace_session(
                ParsedSession(
                    session_id="s1",
                    source_path=str(Path(tmp) / "s1.jsonl"),
                    project="demo",
                    cwd=str(Path(tmp) / "demo"),
                    messages=[
                        ParsedMessage("s1", 0, "user", "user_message", "Find MCP token", None)
                    ],
                ),
                source_mtime=1.0,
            )

            tools = handle_message(db, {"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
            search = handle_message(
                db,
                {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/call",
                    "params": {
                        "name": "memory_search",
                        "arguments": {"query": "MCP token", "limit": 5},
                    },
                },
            )
            remember = handle_message(
                db,
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {
                        "name": "memory_remember",
                        "arguments": {
                            "text": "Pinned MCP memory keeps Codex primary.",
                            "project": "demo",
                            "subject": "provider_preference",
                        },
                    },
                },
            )
            memory_id = json.loads(remember["result"]["content"][0]["text"])["id"]
            update = handle_message(
                db,
                {
                    "jsonrpc": "2.0",
                    "id": 8,
                    "method": "tools/call",
                    "params": {
                        "name": "memory_update",
                        "arguments": {
                            "id": memory_id,
                            "text": "Pinned MCP memory keeps Codex primary and editable.",
                            "confidence": 0.8,
                        },
                    },
                },
            )
            notes = handle_message(
                db,
                {
                    "jsonrpc": "2.0",
                    "id": 4,
                    "method": "tools/call",
                    "params": {
                        "name": "memory_notes",
                        "arguments": {"project": "demo"},
                    },
                },
            )
            context = handle_message(
                db,
                {
                    "jsonrpc": "2.0",
                    "id": 5,
                    "method": "tools/call",
                    "params": {
                        "name": "memory_context",
                        "arguments": {"project": "demo", "query": "MCP token", "limit": 5},
                    },
                },
            )
            bootstrap = handle_message(
                db,
                {
                    "jsonrpc": "2.0",
                    "id": 6,
                    "method": "tools/call",
                    "params": {
                        "name": "memory_bootstrap",
                        "arguments": {
                            "project": "demo",
                            "query": "MCP token",
                            "import_limit": 0,
                            "summary_limit": 0,
                        },
                    },
                },
            )
            exported = handle_message(
                db,
                {
                    "jsonrpc": "2.0",
                    "id": 9,
                    "method": "tools/call",
                    "params": {
                        "name": "memory_export",
                        "arguments": {"project": "demo", "limit": 10},
                    },
                },
            )
            exported_payload = json.loads(exported["result"]["content"][0]["text"])
            forget = handle_message(
                db,
                {
                    "jsonrpc": "2.0",
                    "id": 7,
                    "method": "tools/call",
                    "params": {
                        "name": "memory_forget",
                        "arguments": {"id": memory_id},
                    },
                },
            )
            imported = handle_message(
                db,
                {
                    "jsonrpc": "2.0",
                    "id": 10,
                    "method": "tools/call",
                    "params": {
                        "name": "memory_import_bundle",
                        "arguments": {"payload": exported_payload, "project": "demo"},
                    },
                },
            )
            restored_notes = handle_message(
                db,
                {
                    "jsonrpc": "2.0",
                    "id": 11,
                    "method": "tools/call",
                    "params": {
                        "name": "memory_notes",
                        "arguments": {"project": "demo"},
                    },
                },
            )
            db.close()

        tool_names = {tool["name"] for tool in tools["result"]["tools"]}
        import_tool = next(
            tool for tool in tools["result"]["tools"] if tool["name"] == "memory_import_bundle"
        )
        payload = json.loads(search["result"]["content"][0]["text"])
        remember_payload = json.loads(remember["result"]["content"][0]["text"])
        update_payload = json.loads(update["result"]["content"][0]["text"])
        notes_payload = json.loads(notes["result"]["content"][0]["text"])
        context_payload = json.loads(context["result"]["content"][0]["text"])
        bootstrap_payload = json.loads(bootstrap["result"]["content"][0]["text"])
        exported_payload = json.loads(exported["result"]["content"][0]["text"])
        forget_payload = json.loads(forget["result"]["content"][0]["text"])
        imported_payload = json.loads(imported["result"]["content"][0]["text"])
        restored_notes_payload = json.loads(restored_notes["result"]["content"][0]["text"])
        self.assertIn("memory_context", tool_names)
        self.assertIn("memory_bootstrap", tool_names)
        self.assertIn("memory_remember", tool_names)
        self.assertIn("memory_notes", tool_names)
        self.assertIn("memory_update", tool_names)
        self.assertIn("memory_export", tool_names)
        self.assertIn("memory_import_bundle", tool_names)
        self.assertIn("memory_forget", tool_names)
        self.assertIn("memory_sources", tool_names)
        self.assertNotIn("anyOf", import_tool["inputSchema"])
        self.assertEqual(payload[0]["session_id"], "s1")
        self.assertEqual(remember_payload["project"], "demo")
        self.assertEqual(update_payload["id"], remember_payload["id"])
        self.assertEqual(update_payload["confidence"], 0.8)
        self.assertIn("editable", update_payload["text"])
        self.assertEqual(notes_payload[0]["id"], remember_payload["id"])
        self.assertEqual(context_payload["project"], "demo")
        self.assertEqual(context_payload["memories"][0]["id"], remember_payload["id"])
        self.assertEqual(context_payload["relevant_matches"][0]["session_id"], "s1")
        self.assertEqual(bootstrap_payload["import"]["seen"], 0)
        self.assertEqual(bootstrap_payload["summaries"]["seen"], 0)
        self.assertEqual(bootstrap_payload["profile"]["project"], "demo")
        self.assertEqual(bootstrap_payload["profile"]["memories"][0]["id"], remember_payload["id"])
        self.assertEqual(bootstrap_payload["context"]["relevant_matches"][0]["session_id"], "s1")
        self.assertEqual(exported_payload["version"], 1)
        self.assertEqual(exported_payload["memories"][0]["id"], remember_payload["id"])
        self.assertTrue(forget_payload["deleted"])
        self.assertEqual(imported_payload["imported"], 1)
        self.assertEqual(restored_notes_payload[0]["text"], update_payload["text"])

    def test_sources_and_errors_are_reported_without_crashing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = MemoryDB(Path(tmp) / "memory.sqlite3")
            sources = handle_message(
                db,
                {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "method": "tools/call",
                    "params": {
                        "name": "memory_sources",
                        "arguments": {"action": "review-options"},
                    },
                },
            )
            unknown = handle_message(db, {"jsonrpc": "2.0", "id": 2, "method": "nope"})
            bad_tool = handle_message(
                db,
                {
                    "jsonrpc": "2.0",
                    "id": 3,
                    "method": "tools/call",
                    "params": {"name": "missing_tool", "arguments": {}},
                },
            )
            db.close()

        payload = json.loads(sources["result"]["content"][0]["text"])
        self.assertEqual(payload["primary_coding_ai"]["id"], "codex")
        self.assertFalse(payload["external_review_configured"])
        self.assertEqual(payload["review_targets"], [])
        self.assertEqual(unknown["error"]["code"], -32601)
        self.assertEqual(bad_tool["error"]["code"], -32000)


if __name__ == "__main__":
    unittest.main()
