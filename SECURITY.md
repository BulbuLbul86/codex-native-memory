# Security Policy

Codex Native Memory stores imported conversation metadata and summaries in a
local SQLite database under `~/.codex-native-memory` by default. It does not
require Claude, Gemini, OpenRouter, or other vendor API keys.

## Supported Versions

Security fixes target the current `main` branch until formal releases begin.

## Reporting a Vulnerability

For now, report security issues by opening a private advisory or contacting the
repository maintainers directly. Do not include secrets, tokens, private
transcripts, or full database dumps in public issues.

## Local Data

- Runtime data defaults to `~/.codex-native-memory`.
- Codex transcript imports default to `~/.codex/sessions/**/*.jsonl`.
- Optional external sources must be configured explicitly.
- Summaries should avoid secrets, credentials, tokens, and long verbatim source
  text.

If you share logs or diagnostics, prefer `python -m codex_native_memory doctor
--json` and review the output before posting it.
