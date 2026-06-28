from __future__ import annotations

import unittest

from codex_native_memory.processor import extractive_summary


class ProcessorTests(unittest.TestCase):
    def test_extracts_known_preferences(self) -> None:
        result = extractive_summary(
            [
                {
                    "role": "user",
                    "text": "На русском пиши. Мы работаем только в Кодексе, без Claude и Gemini.",
                }
            ]
        )

        observations = {item["subject"]: item["text"] for item in result["observations"]}
        self.assertIn("language_preference", observations)
        self.assertIn("provider_preference", observations)


if __name__ == "__main__":
    unittest.main()
