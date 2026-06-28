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


if __name__ == "__main__":
    unittest.main()
