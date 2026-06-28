# Codex Native Memory

Local cross-session memory for Codex Desktop and Codex CLI.

The goal is deliberately narrow: import Codex transcript JSONL files, index them
locally in SQLite, expose search through MCP, and optionally ask the local Codex
CLI to summarize conversations. No Claude, Gemini, OpenRouter, or vendor API key
is required. The summarizer uses the user's existing Codex/ChatGPT auth through
`codex exec`.

The architecture is project-centric rather than vendor-centric. Codex is the
main development shell, but sessions are stored with `source_app` and
`source_kind` metadata so future adapters can import Claude, Gemini, Cursor,
Aider, or other AI transcripts into the same local memory without changing the
MCP surface.

## Status

This is an MVP. It already supports:

- importing `~/.codex/sessions/**/*.jsonl`;
- SQLite storage with FTS5 search when available;
- a stdio MCP server with search, import, recent sessions, and health tools;
- queue processing with extractive summaries;
- optional AI summaries through `codex exec --ephemeral`;
- a Codex plugin manifest and helper scripts.

Planned adapter direction:

- `codex`: current `~/.codex/sessions/**/*.jsonl` importer;
- `claude`: local Claude transcript/history importer;
- `gemini`: local Gemini CLI/project history importer;
- `generic-jsonl`: user-supplied transcript folders mapped into the canonical schema.

## Quick start

From this directory:

```powershell
python -m codex_native_memory doctor
python -m codex_native_memory init
python -m codex_native_memory backfill --limit 50
python -m codex_native_memory search "VPN" --limit 5
python -m codex_native_memory process-queue --limit 5 --mode extractive
```

To expose it to Codex as MCP:

```powershell
.\scripts\install-for-codex.ps1
```

Restart Codex after installing the MCP entry.

## Commands

```text
doctor                       Show paths, Codex CLI discovery, and DB stats.
init                         Create the local SQLite database.
backfill                     Import changed transcript JSONL files.
watch                        Poll transcript files and import changes.
search <query>               Search messages, summaries, and observations.
process-queue                Summarize imported sessions.
mcp                          Run the MCP stdio server.
```

Data defaults to `%USERPROFILE%\.codex-native-memory`. Override it with
`CODEX_NATIVE_MEMORY_HOME`.

## MCP tools

- `memory_search`: search imported conversations.
- `memory_recent`: list recent imported sessions.
- `memory_import`: import changed Codex transcript files.
- `memory_health`: show DB and provider health.

Search results are intentionally normalized around sessions, messages,
summaries, and observations. External adapters should write into the same shape
and keep their original source path/source app metadata for traceability.

## Provider behavior

`process-queue --mode codex` calls the local Codex CLI like this:

```text
codex exec --ephemeral --ignore-user-config --ignore-rules --sandbox read-only
```

The run is ephemeral, so it should not create recursive transcript files. The
working directory is under the memory data directory and the command uses the
existing Codex auth stored in `CODEX_HOME`.

Use `--mode extractive` for a fully local, no-model pass. Use `--mode auto` to
try Codex and fall back to extractive summaries on failure.
