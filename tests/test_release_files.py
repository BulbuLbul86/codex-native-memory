from __future__ import annotations

import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


class ReleaseFilesTests(unittest.TestCase):
    def test_public_project_files_are_present(self) -> None:
        expected = [
            ".github/workflows/ci.yml",
            "CHANGELOG.md",
            "CONTRIBUTING.md",
            "LICENSE",
            "SECURITY.md",
            "scripts/install-for-codex.ps1",
            "scripts/install-for-codex.sh",
            "scripts/run-mcp.ps1",
            "scripts/run-mcp.sh",
        ]

        missing = [path for path in expected if not (ROOT / path).exists()]

        self.assertEqual(missing, [])

    def test_ci_runs_lint_compile_and_unittest(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

        self.assertIn("python -m ruff check .", workflow)
        self.assertIn("python -m compileall -q codex_native_memory", workflow)
        self.assertIn("python -m unittest discover -s tests -v", workflow)


if __name__ == "__main__":
    unittest.main()
