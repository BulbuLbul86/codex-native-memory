from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from codex_native_memory.sources import (
    SourceDefinition,
    add_or_update_source,
    load_sources,
    review_options,
    save_sources,
    set_default_coding_source,
)


class SourcesTests(unittest.TestCase):
    def test_codex_is_default_primary_source(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = load_sources(tmp)

            primary = config.default_coding_source()
            options = review_options(config)

            self.assertIsNotNone(primary)
            self.assertEqual(primary.id, "codex")
            self.assertEqual(primary.name, "Codex")
            self.assertFalse(options["external_review_configured"])
            self.assertEqual(options["review_targets"], [])
            self.assertIn("остаётся внутри Codex", options["question"])
            self.assertNotIn("external AI reviewer", options["suggested_prompt"])

    def test_external_review_target_attaches_to_codex(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = load_sources(tmp)
            add_or_update_source(
                config,
                SourceDefinition(
                    id="claude",
                    type="claude",
                    name="Claude",
                    paths=[str(Path(tmp) / "*.jsonl")],
                    review_enabled=True,
                    review_command="claude review",
                ),
            )
            save_sources(config, tmp)

            loaded = load_sources(tmp)
            options = review_options(loaded)

            self.assertEqual(options["primary_coding_ai"]["id"], "codex")
            self.assertEqual(options["review_targets"][0]["id"], "claude")

    def test_external_source_cannot_become_primary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            config = load_sources(tmp)
            add_or_update_source(
                config,
                SourceDefinition(
                    id="gemini",
                    type="gemini",
                    name="Gemini",
                    paths=[str(Path(tmp) / "*.jsonl")],
                    default_for_coding=True,
                ),
            )

            self.assertFalse(set_default_coding_source(config, "gemini"))

            save_sources(config, tmp)
            loaded = load_sources(tmp)

            self.assertEqual(loaded.default_coding_source().id, "codex")
            gemini = next(source for source in loaded.sources if source.id == "gemini")
            self.assertFalse(gemini.default_for_coding)


if __name__ == "__main__":
    unittest.main()
