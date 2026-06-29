from __future__ import annotations

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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

    def test_doctor_reports_mcp_and_source_diagnostics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            code, output = self.run_cli(["--data-dir", tmp, "doctor", "--json"])
            payload = json.loads(output)

            self.assertEqual(code, 0)
            self.assertEqual(payload["package"]["name"], "codex-native-memory")
            self.assertEqual(payload["data_dir"], str(Path(tmp).resolve()))
            self.assertEqual(payload["sources"]["primary_coding_ai"]["id"], "codex")
            self.assertTrue(payload["sources"]["codex_only"])
            self.assertEqual(payload["mcp"]["transport"], "json-lines")
            self.assertTrue(payload["mcp"]["accepts_content_length"])

    def test_mcp_command_defers_database_open_until_tool_call(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            with (
                patch("codex_native_memory.cli.serve") as serve,
                patch(
                    "codex_native_memory.cli.MemoryDB",
                    side_effect=AssertionError("mcp should not open the database at startup"),
                ),
            ):
                code = main(["--data-dir", tmp, "mcp"])

            self.assertEqual(code, 0)
            serve.assert_called_once_with()

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
            duplicate_code, duplicate_output = self.run_cli(
                [
                    "--data-dir",
                    tmp,
                    "remember",
                    "Pinned CLI memory keeps Codex primary.",
                    "--cwd",
                    str(root / "project"),
                    "--subject",
                    "provider_preference",
                    "--confidence",
                    "0.7",
                    "--json",
                ]
            )
            duplicate_payload = json.loads(duplicate_output)
            revise_code, revise_output = self.run_cli(
                [
                    "--data-dir",
                    tmp,
                    "revise",
                    str(payload["id"]),
                    "--text",
                    "Pinned CLI memory now avoids duplicates.",
                    "--scope",
                    "user",
                    "--subject",
                    "language_preference",
                    "--json",
                ]
            )
            revised_payload = json.loads(revise_output)
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
                    "avoids duplicates",
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
            self.assertEqual(duplicate_code, 0)
            self.assertEqual(duplicate_payload["id"], payload["id"])
            self.assertEqual(duplicate_payload["confidence"], 0.7)
            self.assertEqual(revise_code, 0)
            self.assertEqual(revised_payload["scope"], "user")
            self.assertIsNone(revised_payload["project"])
            self.assertEqual(list_code, 0)
            self.assertEqual(json.loads(list_output)[0]["id"], payload["id"])
            self.assertEqual(search_code, 0)
            self.assertEqual(json.loads(search_output)[0]["memory_id"], payload["id"])
            self.assertEqual(forget_code, 0)
            self.assertTrue(json.loads(forget_output)["deleted"])
            self.assertEqual(after_code, 0)
            self.assertEqual(json.loads(after_output), [])

    def test_memory_export_import_cli_round_trips_file(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_data = root / "source-data"
            target_data = root / "target-data"
            export_path = root / "memory-export.json"

            remember_code, _ = self.run_cli(
                [
                    "--data-dir",
                    str(source_data),
                    "remember",
                    "CLI export memory survives round trip.",
                    "--cwd",
                    str(root / "project"),
                    "--subject",
                    "portability",
                ]
            )
            export_code, export_output = self.run_cli(
                [
                    "--data-dir",
                    str(source_data),
                    "export",
                    "--cwd",
                    str(root / "project"),
                    "--output",
                    str(export_path),
                ]
            )
            import_code, import_output = self.run_cli(
                [
                    "--data-dir",
                    str(target_data),
                    "import",
                    str(export_path),
                    "--project",
                    "imported",
                    "--json",
                ]
            )
            reimport_code, reimport_output = self.run_cli(
                [
                    "--data-dir",
                    str(target_data),
                    "import",
                    str(export_path),
                    "--project",
                    "imported",
                    "--json",
                ]
            )
            list_code, list_output = self.run_cli(
                [
                    "--data-dir",
                    str(target_data),
                    "memories",
                    "--project",
                    "imported",
                    "--json",
                ]
            )

            imported = json.loads(import_output)
            reimported = json.loads(reimport_output)
            items = json.loads(list_output)
            self.assertEqual(remember_code, 0)
            self.assertEqual(export_code, 0)
            self.assertTrue(export_path.exists())
            self.assertIn("Saved memory export", export_output)
            self.assertEqual(import_code, 0)
            self.assertEqual(imported["imported"], 1)
            self.assertEqual(reimport_code, 0)
            self.assertEqual(reimported["updated"], 1)
            self.assertEqual(list_code, 0)
            self.assertEqual(items[0]["project"], "imported")
            self.assertEqual(items[0]["text"], "CLI export memory survives round trip.")


if __name__ == "__main__":
    unittest.main()
