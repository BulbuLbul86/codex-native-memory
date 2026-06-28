from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from codex_native_memory.codex_provider import (
    find_codex_cli,
    parse_json_response,
    render_transcript,
)
from codex_native_memory.paths import ENV_CODEX


class CodexProviderTests(unittest.TestCase):
    def test_parse_json_response_accepts_fences_and_embedded_json(self) -> None:
        fenced = '```json\n{"summary": "ok"}\n```'
        embedded = 'prefix {"summary": "ok", "decisions": []} suffix'

        self.assertEqual(parse_json_response(fenced)["summary"], "ok")
        self.assertEqual(parse_json_response(embedded)["summary"], "ok")

    def test_parse_json_response_rejects_non_object(self) -> None:
        with self.assertRaises(ValueError):
            parse_json_response('["not", "an", "object"]')

    def test_render_transcript_truncates_without_empty_messages(self) -> None:
        rendered = render_transcript(
            [
                {"role": "user", "text": ""},
                {"role": "user", "text": "a" * 50},
                {"role": "assistant", "text": "b" * 50},
            ],
            limit_chars=80,
        )

        self.assertIn("USER:", rendered)
        self.assertIn("[Transcript truncated]", rendered)
        self.assertNotIn("UNKNOWN", rendered)

    def test_find_codex_cli_prefers_explicit_env_path(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            codex = Path(tmp) / "codex.exe"
            codex.write_text("", encoding="utf-8")

            with patch.dict(os.environ, {ENV_CODEX: str(codex)}, clear=False):
                self.assertEqual(find_codex_cli(), codex.resolve())


if __name__ == "__main__":
    unittest.main()
