from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from codex_native_memory.transcripts import parse_jsonl_file


class TranscriptParserTests(unittest.TestCase):
    def test_parses_codex_desktop_events_without_context_noise(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sample.jsonl"
            events = [
                {
                    "timestamp": "2026-06-28T10:00:00Z",
                    "type": "session_meta",
                    "payload": {
                        "session_id": "s1",
                        "id": "rollout1",
                        "cwd": str(Path(tmp) / "project"),
                    },
                },
                {
                    "timestamp": "2026-06-28T10:00:01Z",
                    "type": "response_item",
                    "payload": {
                        "type": "message",
                        "role": "user",
                        "content": [{"type": "input_text", "text": "<environment_context>noise"}],
                    },
                },
                {
                    "timestamp": "2026-06-28T10:00:02Z",
                    "type": "event_msg",
                    "payload": {"type": "user_message", "message": "Remember this project"},
                },
                {
                    "timestamp": "2026-06-28T10:00:03Z",
                    "type": "event_msg",
                    "payload": {"type": "agent_message", "message": "Done."},
                },
                {
                    "timestamp": "2026-06-28T10:00:04Z",
                    "type": "response_item",
                    "payload": {
                        "type": "function_call",
                        "name": "shell_command",
                        "call_id": "call-1",
                        "arguments": '{"command":"pwd"}',
                    },
                },
            ]
            path.write_text("\n".join(json.dumps(event) for event in events), encoding="utf-8")

            parsed = parse_jsonl_file(path)

            self.assertEqual(parsed.session_id, "rollout1")
            self.assertEqual(parsed.project, "project")
            self.assertEqual([message.role for message in parsed.messages], ["user", "assistant"])
            self.assertEqual(parsed.messages[0].text, "Remember this project")
            self.assertEqual(parsed.tool_events[0].name, "shell_command")


if __name__ == "__main__":
    unittest.main()
