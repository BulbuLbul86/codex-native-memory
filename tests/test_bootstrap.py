from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from codex_native_memory.bootstrap import bootstrap_memory
from codex_native_memory.db import MemoryDB
from codex_native_memory.transcripts import ParsedMessage, ParsedSession


class BootstrapTests(unittest.TestCase):
    def test_bootstrap_recommends_real_project_for_temporary_codex_workspace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            db = MemoryDB(root / "memory.sqlite3")
            real_cwd = root / "codex-native-memory"
            scratch_cwd = root / "2026-06-29" / "new-chat-3"
            db.replace_session(
                ParsedSession(
                    session_id="real",
                    source_path=str(root / "real.jsonl"),
                    title="Memory plugin work",
                    cwd=str(real_cwd),
                    project="codex-native-memory",
                    updated_at="2026-06-29T00:00:00Z",
                    messages=[
                        ParsedMessage(
                            "real",
                            0,
                            "user",
                            "user_message",
                            "Improve memory plugin project continuity.",
                            None,
                        )
                    ],
                ),
                source_mtime=1.0,
            )
            db.store_summary(
                "real",
                {
                    "summary": "Implemented smarter memory plugin project continuity.",
                    "decisions": ["Use recommended project context for temporary Codex folders."],
                    "open_questions": [],
                    "observations": [],
                },
            )
            db.replace_session(
                ParsedSession(
                    session_id="scratch",
                    source_path=str(root / "scratch.jsonl"),
                    title="Подними память проекта",
                    cwd=str(scratch_cwd),
                    project="new-chat-3",
                    updated_at="2026-06-29T00:01:00Z",
                    messages=[
                        ParsedMessage(
                            "scratch",
                            0,
                            "user",
                            "user_message",
                            "подними память проекта",
                            None,
                        )
                    ],
                ),
                source_mtime=1.0,
            )

            payload = bootstrap_memory(
                db,
                data_root=root,
                cwd=scratch_cwd,
                query="memory plugin project continuity",
                context_limit=5,
                import_limit=0,
                summary_limit=0,
            )

            self.assertEqual(payload["context"]["project"], "new-chat-3")
            self.assertEqual(
                payload["project_resolution"]["effective_project"],
                "codex-native-memory",
            )
            self.assertEqual(payload["project_resolution"]["strategy"], "recommended_candidate")
            self.assertEqual(payload["project_candidates"][0]["project"], "codex-native-memory")
            self.assertEqual(payload["recommended_context"]["project"], "codex-native-memory")
            self.assertIn(
                "Use recommended project context",
                payload["recommended_context"]["decisions"][0],
            )
            db.close()


if __name__ == "__main__":
    unittest.main()
