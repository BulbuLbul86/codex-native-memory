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
            context_code, context_output = self.run_cli(
                [
                    "--data-dir",
                    tmp,
                    "context",
                    "durable CLI token",
                    "--cwd",
                    str(root / "project"),
                    "--json",
                ]
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
            self.assertEqual(context_code, 0)
            context_payload = json.loads(context_output)
            self.assertEqual(context_payload["project"], "project")
            self.assertIn("Project: project", context_payload["brief"])
            self.assertEqual(context_payload["summaries"][0]["session_id"], "cli-session")
            self.assertEqual(context_payload["relevant_matches"][0]["session_id"], "cli-session")
            self.assertEqual(list_code, 0)
            self.assertEqual(json.loads(list_output)[0]["id"], "codex")
            self.assertEqual(remove_code, 0)
            self.assertIn("was not found", remove_output)
            self.assertEqual(default_code, 0)
            self.assertIn("Primary coding AI: Codex", default_output)

    def test_bootstrap_imports_processes_and_returns_profile(self) -> None:
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
                            "payload": {"id": "bootstrap-session", "cwd": str(root / "project")},
                        },
                        {
                            "timestamp": "2026-06-29T00:00:01Z",
                            "type": "event_msg",
                            "payload": {
                                "type": "user_message",
                                "message": "На русском. Need durable CLI token for memory.",
                            },
                        },
                        {
                            "timestamp": "2026-06-29T00:00:02Z",
                            "type": "event_msg",
                            "payload": {
                                "type": "agent_message",
                                "message": "Durable CLI token handled.",
                            },
                        },
                    ]
                ),
                encoding="utf-8",
            )

            source_code, _ = self.run_cli(
                [
                    "--data-dir",
                    tmp,
                    "sources",
                    "add",
                    "codex",
                    "--type",
                    "codex",
                    "--path",
                    str(transcript),
                ]
            )
            bootstrap_code, bootstrap_output = self.run_cli(
                [
                    "--data-dir",
                    tmp,
                    "bootstrap",
                    "durable CLI token",
                    "--cwd",
                    str(root / "project"),
                    "--json",
                    "--summary-mode",
                    "extractive",
                    "--summary-limit",
                    "1",
                    "--import-limit",
                    "10",
                    "--all-sources",
                ]
            )

            payload = json.loads(bootstrap_output)
            self.assertEqual(source_code, 0)
            self.assertEqual(bootstrap_code, 0)
            self.assertEqual(payload["import"]["codex"]["imported"], 1)
            self.assertEqual(payload["summaries"]["done"], 1)
            self.assertTrue(payload["codex_only"])
            self.assertFalse(payload["external_review_configured"])
            self.assertEqual(payload["profile"]["project"], "project")
            self.assertEqual(payload["profile"]["profile_kind"], "dynamic")
            self.assertIn("User prefers Russian responses.", payload["profile"]["preferences"])
            self.assertEqual(
                payload["context"]["relevant_matches"][0]["session_id"],
                "bootstrap-session",
            )

    def test_memory_item_cli_remembers_lists_searches_and_forgets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            remember_code, remember_output = self.run_cli(
                [
                    "--data-dir",
                    tmp,
                    "remember",
                    "Pinned CLI memory keeps Codex primary.",
                    "--cwd",
                    str(root / "project"),
                    "--subject",
                    "provider_preference",
                    "--json",
                ]
            )
            payload = json.loads(remember_output)
            list_code, list_output = self.run_cli(
                [
                    "--data-dir",
                    tmp,
                    "memories",
                    "--cwd",
                    str(root / "project"),
                    "--json",
                ]
            )
            search_code, search_output = self.run_cli(
                [
                    "--data-dir",
                    tmp,
                    "search",
                    "Codex primary",
                    "--kind",
                    "memories",
                    "--json",
                ]
            )
            forget_code, forget_output = self.run_cli(
                ["--data-dir", tmp, "forget", str(payload["id"]), "--json"]
            )
            after_code, after_output = self.run_cli(
                [
                    "--data-dir",
                    tmp,
                    "memories",
                    "--cwd",
                    str(root / "project"),
                    "--json",
                ]
            )

            self.assertEqual(remember_code, 0)
            self.assertEqual(payload["project"], "project")
            self.assertEqual(payload["scope"], "project")
            self.assertEqual(list_code, 0)
            self.assertEqual(json.loads(list_output)[0]["id"], payload["id"])
            self.assertEqual(search_code, 0)
            self.assertEqual(json.loads(search_output)[0]["memory_id"], payload["id"])
            self.assertEqual(forget_code, 0)
            self.assertTrue(json.loads(forget_output)["deleted"])
            self.assertEqual(after_code, 0)
            self.assertEqual(json.loads(after_output), [])


if __name__ == "__main__":
    unittest.main()
