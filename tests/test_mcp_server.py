from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from codex_native_memory.db import MemoryDB
from codex_native_memory.mcp_server import handle_message
from codex_native_memory.transcripts import ParsedMessage, ParsedSession


class McpServerTests(unittest.TestCase):
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
            context = handle_message(
                db,
                {
                    "jsonrpc": "2.0",
                    "id": 3,
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
                    "id": 4,
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
            db.close()

        tool_names = {tool["name"] for tool in tools["result"]["tools"]}
        payload = json.loads(search["result"]["content"][0]["text"])
        context_payload = json.loads(context["result"]["content"][0]["text"])
        bootstrap_payload = json.loads(bootstrap["result"]["content"][0]["text"])
        self.assertIn("memory_context", tool_names)
        self.assertIn("memory_bootstrap", tool_names)
        self.assertIn("memory_sources", tool_names)
        self.assertEqual(payload[0]["session_id"], "s1")
        self.assertEqual(context_payload["project"], "demo")
        self.assertEqual(context_payload["relevant_matches"][0]["session_id"], "s1")
        self.assertEqual(bootstrap_payload["import"]["seen"], 0)
        self.assertEqual(bootstrap_payload["summaries"]["seen"], 0)
        self.assertEqual(bootstrap_payload["profile"]["project"], "demo")
        self.assertEqual(bootstrap_payload["context"]["relevant_matches"][0]["session_id"], "s1")

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
