# Contributing

Codex Native Memory is intentionally local-first and Codex-first. Contributions
should preserve those defaults:

- Codex remains the primary coding AI.
- Claude, Gemini, and other tools are optional attached sources or review
  targets.
- The plugin must work in Codex-only mode without vendor API keys.
- Memory output should be useful context, not unquestioned truth.
- Do not store secrets, credentials, tokens, or long verbatim source text.

## Development Setup

```powershell
python -m pip install -e ".[dev]"
python -m codex_native_memory doctor
python -m codex_native_memory init
```

On macOS/Linux, use the same commands in your shell.

## Checks

Run these before opening a pull request:

```powershell
python -m ruff check .
python -m compileall -q codex_native_memory
python -m unittest discover -s tests -v
python -m codex_native_memory doctor --json
```

When changing plugin metadata or skills, also validate the plugin with the
current Codex plugin validation tool if it is available locally.

## Release Checklist

1. Update `CHANGELOG.md`.
2. Run the checks above.
3. Verify `scripts/install-for-codex.ps1` on Windows or
   `scripts/install-for-codex.sh` on macOS/Linux.
4. Run a direct MCP smoke test against `memory_health` and `memory_bootstrap`.
5. Bump the Codex plugin cachebuster when testing through the Codex app.
