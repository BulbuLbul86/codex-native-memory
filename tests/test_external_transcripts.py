from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from codex_native_memory.external_transcripts import parse_external_file
from codex_native_memory.sources import SourceDefinition


class ExternalTranscriptTests(unittest.TestCase):
    def test_parses_generic_jsonl_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "claude.jsonl"
            path.write_text(
                "\n".join(
                    [
                        json.dumps({"role": "user", "text": "Check this code"}),
                        json.dumps({"role": "assistant", "text": "Looks safe"}),
                    ]
                ),
                encoding="utf-8",
            )
            source = SourceDefinition(
                id="claude",
                type="claude",
                name="Claude",
                paths=[str(path)],
                project="demo",
            )

            parsed = parse_external_file(path, source)

            self.assertEqual(parsed.source_app, "claude")
            self.assertEqual(parsed.source_kind, "claude")
            self.assertEqual(parsed.project, "demo")
            self.assertEqual([message.role for message in parsed.messages], ["user", "assistant"])


if __name__ == "__main__":
    unittest.main()
