from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from codex_native_memory.db import MemoryDB
from codex_native_memory.ingest import backfill_configured_sources, backfill_source
from codex_native_memory.sources import SourceDefinition, SourcesConfig, save_sources


class IngestTests(unittest.TestCase):
    def test_backfill_configured_external_source_imports_and_skips_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            transcript = root / "claude.jsonl"
            transcript.write_text(
                "\n".join(
                    [
                        json.dumps({"role": "user", "text": "alpha import"}),
                        json.dumps({"role": "assistant", "text": "beta response"}),
                    ]
                ),
                encoding="utf-8",
            )
            save_sources(
                SourcesConfig(
                    sources=[
                        SourceDefinition(
                            id="claude",
                            type="claude",
                            name="Claude",
                            paths=[str(root / "*.jsonl")],
                        )
                    ]
                ),
                root,
            )
            db = MemoryDB(root / "memory.sqlite3")

            first = backfill_configured_sources(db, source_id="claude", data_root=root)
            second = backfill_configured_sources(db, source_id="claude", data_root=root)
            results = db.search("alpha", limit=5)
            stats = db.stats()

            self.assertEqual(first["claude"]["imported"], 1)
            self.assertEqual(second["claude"]["skipped"], 1)
            self.assertEqual(results[0]["kind"], "claude")
            self.assertEqual(stats["sources"]["claude"], 1)
            db.close()

    def test_backfill_source_counts_empty_and_parse_errors(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            empty = root / "empty.jsonl"
            bad_json = root / "bad.json"
            empty.write_text("not json\n", encoding="utf-8")
            bad_json.write_text("{not json", encoding="utf-8")
            db = MemoryDB(root / "memory.sqlite3")

            empty_stats = backfill_source(
                db,
                SourceDefinition(
                    id="generic",
                    type="generic-jsonl",
                    name="Generic",
                    paths=[str(empty)],
                ),
                data_root=root,
            )
            error_stats = backfill_source(
                db,
                SourceDefinition(
                    id="generic",
                    type="generic-jsonl",
                    name="Generic",
                    paths=[str(bad_json)],
                ),
                data_root=root,
            )

            self.assertEqual(empty_stats["empty"], 1)
            self.assertEqual(error_stats["errors"], 1)
            db.close()

    def test_unknown_configured_source_raises(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            save_sources(SourcesConfig(), root)
            db = MemoryDB(root / "memory.sqlite3")

            with self.assertRaises(ValueError):
                backfill_configured_sources(db, source_id="missing", data_root=root)

            db.close()


if __name__ == "__main__":
    unittest.main()
