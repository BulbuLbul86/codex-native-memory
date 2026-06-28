from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from codex_native_memory.cli import main


class CliTests(unittest.TestCase):
    def run_cli(self, argv: list[str]) -> tuple[int, str]:
        stream = io.StringIO()
        with contextlib.redirect_stdout(stream):
            code = main(argv)
        return code, stream.getvalue()

    def test_sources_cli_keeps_codex_primary_and_blocks_external_default(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            transcript_glob = str(Path(tmp) / "*.jsonl")

            code, output = self.run_cli(
                [
                    "--data-dir",
                    tmp,
                    "sources",
                    "add",
                    "gemini",
                    "--type",
                    "gemini",
                    "--path",
                    transcript_glob,
                    "--review-enabled",
                ]
            )
            self.assertEqual(code, 0)
            self.assertIn("Codex remains the primary coding AI", output)

            with self.assertRaises(SystemExit):
                self.run_cli(["--data-dir", tmp, "sources", "set-default", "gemini"])

            code, output = self.run_cli(["--data-dir", tmp, "sources", "review-options", "--json"])
            payload = json.loads(output)

            self.assertEqual(code, 0)
            self.assertEqual(payload["primary_coding_ai"]["id"], "codex")
            self.assertEqual(payload["review_targets"][0]["id"], "gemini")

    def test_unknown_command_prints_help_status(self) -> None:
        code, output = self.run_cli([])

        self.assertEqual(code, 2)
        self.assertIn("codex-native-memory", output)

    def test_core_cli_workflow_imports_searches_and_processes_queue(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            transcript = root / "codex.jsonl"
            transcript.write_text(
                "\n".join(
                    json.dumps(event)
                    for event in [
                        {
                            "timestamp": "2026-06-29T00:00:00Z",
                            "type": "session_meta",
                            "payload": {"id": "cli-session", "cwd": str(root / "project")},
                        },
                        {
                            "timestamp": "2026-06-29T00:00:01Z",
                            "type": "event_msg",
                            "payload": {
                                "type": "user_message",
                                "message": "Need durable CLI token",
                            },
                        },
                        {
                            "timestamp": "2026-06-29T00:00:02Z",
                            "type": "event_msg",
                            "payload": {
                                "type": "agent_message",
                                "message": "Durable CLI token handled",
                            },
                        },
                    ]
                ),
                encoding="utf-8",
            )

            init_code, init_output = self.run_cli(["--data-dir", tmp, "init"])
            backfill_code, backfill_output = self.run_cli(
                ["--data-dir", tmp, "backfill", "--glob", str(transcript), "--force"]
            )
            search_code, search_output = self.run_cli(
                ["--data-dir", tmp, "search", "durable CLI token", "--json"]
            )
            process_code, process_output = self.run_cli(
                ["--data-dir", tmp, "process-queue", "--mode", "extractive", "--limit", "1"]
            )
            list_code, list_output = self.run_cli(["--data-dir", tmp, "sources", "list", "--json"])
            remove_code, remove_output = self.run_cli(
                ["--data-dir", tmp, "sources", "remove", "missing"]
            )
            default_code, default_output = self.run_cli(
                ["--data-dir", tmp, "sources", "set-default"]
            )

            self.assertEqual(init_code, 0)
            self.assertEqual(json.loads(init_output)["sessions"], 0)
            self.assertEqual(backfill_code, 0)
            self.assertEqual(json.loads(backfill_output)["imported"], 1)
            self.assertEqual(search_code, 0)
            self.assertEqual(json.loads(search_output)[0]["session_id"], "cli-session")
            self.assertEqual(process_code, 0)
            self.assertEqual(json.loads(process_output)["done"], 1)
            self.assertEqual(list_code, 0)
            self.assertEqual(json.loads(list_output)[0]["id"], "codex")
            self.assertEqual(remove_code, 0)
            self.assertIn("was not found", remove_output)
            self.assertEqual(default_code, 0)
            self.assertIn("Primary coding AI: Codex", default_output)


if __name__ == "__main__":
    unittest.main()
