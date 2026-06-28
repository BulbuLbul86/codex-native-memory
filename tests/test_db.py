from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from codex_native_memory.db import MemoryDB
from codex_native_memory.transcripts import ParsedMessage, ParsedSession


class MemoryDBTests(unittest.TestCase):
    def test_replace_session_indexes_messages_and_searches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            db = MemoryDB(Path(tmp) / "memory.sqlite3")
            parsed = ParsedSession(
                session_id="s1",
                source_path=str(Path(tmp) / "s1.jsonl"),
                title="VPN setup",
                cwd=str(Path(tmp)),
                project="tmp",
                messages=[
                    ParsedMessage("s1", 0, "user", "user_message", "Need VPN setup", None),
                    ParsedMessage("s1", 1, "assistant", "agent_message", "Configured WireGuard", None),
                ],
            )
            db.replace_session(parsed, source_mtime=1.0)

            results = db.search("VPN", limit=5, kind="all")
            stats = db.stats()

            self.assertGreaterEqual(len(results), 1)
            self.assertEqual(stats["sessions"], 1)
            self.assertEqual(stats["messages"], 2)
            self.assertEqual(stats["queue"]["pending"], 1)
            db.close()


if __name__ == "__main__":
    unittest.main()
