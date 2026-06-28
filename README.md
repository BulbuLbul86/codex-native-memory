# Codex Native Memory

Local cross-session memory for Codex Desktop and Codex CLI.

The goal is deliberately narrow: import Codex transcript JSONL files, index them
locally in SQLite, expose search through MCP, and optionally ask the local Codex
CLI to summarize conversations. No Claude, Gemini, OpenRouter, or vendor API key
is required. The summarizer uses the user's existing Codex/ChatGPT auth through
`codex exec`.

The architecture is Codex-first and project-centric. Codex is the primary
coding shell and the default coding AI. Claude, Gemini, Cursor, Aider, or other
AI systems can attach later as optional external sources or review targets.
Codex-only mode is the normal default: if you do not use Claude, Gemini, or any
other AI, there is nothing extra to configure. Imported sessions are stored with
`source_app` and `source_kind` metadata so future external transcripts can flow
into the same local project memory without taking over the main Codex workflow.

## Status

This is an MVP. It already supports:

- importing `~/.codex/sessions/**/*.jsonl`;
- SQLite storage with FTS5 search when available;
- a stdio MCP server with search, import, recent sessions, and health tools;
- project-oriented memory context with summaries, decisions, questions, and observations;
- queue processing with extractive summaries;
- optional AI summaries through `codex exec --ephemeral`;
- optional configurable external sources through `sources.json`;
- optional review targets for Claude, Gemini, or generic external AI checks;
- a Codex plugin manifest and helper scripts.

Planned adapter direction:

- `codex`: current `~/.codex/sessions/**/*.jsonl` importer;
- `claude`: local Claude transcript/history importer;
- `gemini`: local Gemini CLI/project history importer;
- `generic-jsonl`: user-supplied transcript folders mapped into the canonical schema.

Codex always remains the default coding AI. If you only use Codex, skip this
section. Later, Claude, Gemini, and other tools can attach to it as memory
sources or optional review targets by pointing the plugin at their transcript
paths:

```powershell
python -m codex_native_memory sources list
python -m codex_native_memory sources add claude --type claude --path "$HOME\.claude\**\*.jsonl" --review-enabled
python -m codex_native_memory sources add gemini --type gemini --path "$HOME\.gemini\**\*.jsonl" --review-enabled
python -m codex_native_memory backfill --all-sources
python -m codex_native_memory sources review-options
```

Before using external AI review, check whether review targets are configured.
If none are configured, keep review inside Codex and do not ask the user to
connect external AI tools.

## Quick start

From this directory:

```powershell
python -m codex_native_memory doctor
python -m codex_native_memory init
python -m codex_native_memory backfill --limit 50
python -m codex_native_memory context "current task" --cwd "$PWD" --limit 5
python -m codex_native_memory search "VPN" --limit 5
python -m codex_native_memory process-queue --limit 5 --mode extractive
```

To expose it to Codex as MCP:

```powershell
.\scripts\install-for-codex.ps1
```

Restart Codex after installing the MCP entry.

To attach Claude/Gemini sources interactively later:

```powershell
.\scripts\configure-sources.ps1
```

## Commands

```text
doctor                       Show paths, Codex CLI discovery, and DB stats.
init                         Create the local SQLite database.
backfill                     Import changed transcript JSONL files.
watch                        Poll transcript files and import changes.
search <query>               Search messages, summaries, and observations.
context [query]              Build project-oriented memory context.
process-queue                Summarize imported sessions.
mcp                          Run the MCP stdio server.
```

Data defaults to `%USERPROFILE%\.codex-native-memory`. Override it with
`CODEX_NATIVE_MEMORY_HOME`.

## MCP tools

- `memory_search`: search imported conversations.
- `memory_context`: build project-oriented context from recent sessions, summaries,
  decisions, open questions, observations, and optional query matches.
- `memory_recent`: list recent imported sessions.
- `memory_import`: import changed Codex transcript files.
- `memory_sources`: list attached sources and external review options.
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
