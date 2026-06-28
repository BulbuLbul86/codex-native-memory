from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from codex_native_memory.db import MemoryDB
from codex_native_memory.transcripts import ParsedMessage, ParsedSession


class MemoryDBTests(unittest.TestCase):
    def test_replace_session_indexes_messages_and_searches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = MemoryDB(Path(tmp) / "memory.sqlite3")
            parsed = ParsedSession(
                session_id="s1",
                source_path=str(Path(tmp) / "s1.jsonl"),
                source_app="codex",
                source_kind="codex-jsonl",
                title="VPN setup",
                cwd=str(Path(tmp)),
                project="tmp",
                messages=[
                    ParsedMessage("s1", 0, "user", "user_message", "Need VPN setup", None),
                    ParsedMessage(
                        "s1", 1, "assistant", "agent_message", "Configured WireGuard", None
                    ),
                ],
            )
            db.replace_session(parsed, source_mtime=1.0)

            results = db.search("VPN", limit=5, kind="all")
            stats = db.stats()

            self.assertGreaterEqual(len(results), 1)
            self.assertEqual(stats["sessions"], 1)
            self.assertEqual(stats["messages"], 2)
            self.assertEqual(stats["queue"]["pending"], 1)
            self.assertEqual(stats["sources"]["codex"], 1)
            db.close()

    def test_project_context_collects_durable_project_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = MemoryDB(Path(tmp) / "memory.sqlite3")
            parsed = ParsedSession(
                session_id="s1",
                source_path=str(Path(tmp) / "s1.jsonl"),
                source_app="codex",
                source_kind="codex-jsonl",
                title="Memory context",
                cwd=str(Path(tmp) / "demo"),
                project="demo",
                messages=[
                    ParsedMessage("s1", 0, "user", "user_message", "Make memory smarter", None),
                    ParsedMessage(
                        "s1", 1, "assistant", "agent_message", "Added project context", None
                    ),
                ],
            )
            db.replace_session(parsed, source_mtime=1.0)
            db.store_summary(
                "s1",
                {
                    "summary": "Implemented project memory context.",
                    "decisions": [
                        "Use Codex-only mode by default.",
                        "Скажи, что там подключить дальше?",
                    ],
                    "open_questions": ["Should context be shown automatically?"],
                    "observations": [
                        {
                            "scope": "project",
                            "subject": "memory",
                            "text": "Project uses project-oriented memory context.",
                            "confidence": 0.9,
                        },
                        {
                            "scope": "user",
                            "subject": "language_preference",
                            "text": "User prefers Russian responses.",
                            "confidence": 0.95,
                        },
                        {
                            "scope": "project",
                            "subject": "provider_preference",
                            "text": "Codex remains the primary coding AI.",
                            "confidence": 0.9,
                        },
                        {
                            "scope": "workflow",
                            "subject": "multi_agent_usage",
                            "text": "Avoid spawning dashboard windows during background work.",
                            "confidence": 0.85,
                        },
                    ],
                },
            )

            context = db.project_context(project="demo", query="smarter", limit=5)

            self.assertEqual(context["project"], "demo")
            self.assertEqual(context["session_count"], 1)
            self.assertEqual(context["decisions"], ["Use Codex-only mode by default."])
            self.assertEqual(context["open_questions"], ["Should context be shown automatically?"])
            self.assertIn("Use Codex-only mode by default.", context["brief"])
            self.assertIn("memory", {item["subject"] for item in context["observations"]})
            self.assertEqual(context["summaries"][0]["session_id"], "s1")
            self.assertEqual(context["relevant_matches"][0]["session_id"], "s1")

            nested_context = db.project_context(cwd=Path(tmp) / "demo" / "nested", limit=5)
            self.assertEqual(nested_context["project"], "demo")
            self.assertEqual(nested_context["session_count"], 1)

            profile = db.project_profile(cwd=Path(tmp) / "demo" / "nested", limit=5)
            self.assertEqual(profile["project"], "demo")
            self.assertEqual(profile["profile_kind"], "dynamic")
            self.assertIn("User prefers Russian responses.", profile["preferences"])
            self.assertIn("Codex remains the primary coding AI.", profile["constraints"])
            self.assertIn(
                "Avoid spawning dashboard windows during background work.",
                profile["warnings"],
            )
            self.assertIn("Dynamic project profile: demo", profile["brief"])
            db.close()

    def test_pinned_memory_items_are_project_aware_and_searchable(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = MemoryDB(root / "memory.sqlite3")
            user_memory = db.remember(
                "Always answer in Russian for this user.",
                scope="user",
                subject="language_preference",
            )
            project_memory = db.remember(
                "Codex Native Memory must keep Codex as the primary coding AI.",
                scope="project",
                subject="provider_preference",
                cwd=root / "demo",
            )
            warning_memory = db.remember(
                "Avoid dashboard windows unless explicitly requested.",
                scope="workflow",
                subject="multi_agent_usage",
                project="demo",
            )

            items = db.memory_items(cwd=root / "demo" / "nested", limit=10)
            context_by_cwd = db.project_context(cwd=root / "demo" / "nested", limit=5)
            context = db.project_context(project="demo", query="primary coding AI", limit=5)
            profile = db.project_profile(project="demo", limit=5)
            results = db.search("primary coding AI", limit=5, kind="memories")
            deleted = db.forget_memory(project_memory["id"])
            remaining = db.memory_items(project="demo", limit=10)
            duplicate = db.remember(
                "Always answer in Russian for this user.",
                scope="user",
                subject="language_preference",
                confidence=0.5,
            )
            updated_warning = db.update_memory(
                warning_memory["id"],
                text="Avoid dashboard windows unless the user explicitly asks for them.",
                scope="user",
                subject="workflow_preference",
            )

            self.assertIsNone(user_memory["project"])
            self.assertEqual(project_memory["project"], "demo")
            self.assertEqual(warning_memory["project"], "demo")
            self.assertEqual({item["id"] for item in items}, {1, 2, 3})
            self.assertEqual(context_by_cwd["project"], "demo")
            self.assertIn(project_memory["id"], {item["id"] for item in context_by_cwd["memories"]})
            self.assertIn(project_memory["text"], context["brief"])
            self.assertIn(user_memory["id"], {item["id"] for item in context["memories"]})
            self.assertIn("Always answer in Russian for this user.", profile["preferences"])
            self.assertIn(project_memory["text"], profile["constraints"])
            self.assertIn(warning_memory["text"], profile["warnings"])
            self.assertEqual(results[0]["memory_id"], project_memory["id"])
            self.assertTrue(deleted)
            self.assertNotIn(project_memory["id"], {item["id"] for item in remaining})
            self.assertEqual(duplicate["id"], user_memory["id"])
            self.assertEqual(duplicate["confidence"], 0.5)
            self.assertEqual(updated_warning["scope"], "user")
            self.assertIsNone(updated_warning["project"])
            self.assertIn("explicitly asks", updated_warning["text"])
            db.close()

    def test_memory_export_import_bundle_round_trips_with_project_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_db = MemoryDB(root / "source.sqlite3")
            source_db.remember(
                "Always answer in Russian.",
                scope="user",
                subject="language_preference",
            )
            project_memory = source_db.remember(
                "Project memory can be exported.",
                scope="project",
                subject="portability",
                cwd=root / "demo",
            )

            all_bundle = source_db.export_bundle(limit=10)
            bundle = source_db.export_bundle(cwd=root / "demo", limit=10)
            target_db = MemoryDB(root / "target.sqlite3")
            imported = target_db.import_bundle(bundle, project="copy")
            reimported = target_db.import_bundle(bundle, project="copy")
            source_db.update_memory(
                project_memory["id"],
                text="Project memory can be exported after edits.",
            )
            edited_bundle = source_db.export_bundle(cwd=root / "demo", limit=10)
            edited_import = target_db.import_bundle(edited_bundle, project="copy")
            imported_items = target_db.memory_items(project="copy", limit=10)
            all_items = target_db.memory_items(limit=10)
            user_item = next(
                item for item in all_items if item["text"] == "Always answer in Russian."
            )
            project_item = next(
                item
                for item in all_items
                if item["text"] == "Project memory can be exported after edits."
            )
            cwd_target_db = MemoryDB(root / "cwd-target.sqlite3")
            cwd_imported = cwd_target_db.import_bundle(bundle, cwd=root / "other")
            cwd_items = cwd_target_db.memory_items(project="other", limit=10)
            cwd_project_item = next(item for item in cwd_items if item["scope"] == "project")

            self.assertNotIn("profile", all_bundle)
            self.assertEqual(bundle["version"], 1)
            self.assertEqual(bundle["project"], "demo")
            self.assertEqual(len(bundle["memories"]), 2)
            self.assertTrue(all(item["origin_key"] for item in bundle["memories"]))
            self.assertIn("profile", bundle)
            self.assertEqual(imported["seen"], 2)
            self.assertEqual(imported["imported"], 2)
            self.assertEqual(imported["updated"], 0)
            self.assertEqual(reimported["imported"], 0)
            self.assertEqual(reimported["updated"], 2)
            self.assertEqual(edited_import["imported"], 0)
            self.assertEqual(edited_import["updated"], 2)
            self.assertEqual(len(imported_items), 2)
            self.assertIn("copy", {item["project"] for item in imported_items})
            self.assertIn(None, {item["project"] for item in imported_items})
            self.assertIsNone(user_item["project"])
            self.assertEqual(project_item["project"], "copy")
            self.assertEqual(cwd_imported["imported"], 2)
            self.assertEqual(cwd_project_item["project"], "other")
            source_db.close()
            target_db.close()
            cwd_target_db.close()


if __name__ == "__main__":
    unittest.main()
