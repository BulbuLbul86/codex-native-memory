# Changelog

All notable changes to Codex Native Memory are documented here.

## Unreleased

- Added public project hygiene: CI workflow, contributing guide, security policy,
  release checklist, and cross-platform install notes.
- Added MCP diagnostics through `doctor --json` and `memory_health`.
- Made the MCP command open SQLite lazily on the first tool call.

## 0.1.0

- Added local Codex transcript import from `~/.codex/sessions/**/*.jsonl`.
- Added SQLite storage, FTS search, recent-session lookup, and project context.
- Added stdio MCP tools for search, import, context, bootstrap, health, and
  pinned memory management.
- Added project bootstrap/profile flow with optional local Codex summaries.
- Added Codex-only default mode plus optional external source/review target
  configuration for Claude, Gemini, and generic JSONL sources.
- Added temporary `new-chat*` project candidate discovery.
- Added memory export/import for pinned project handoff.
