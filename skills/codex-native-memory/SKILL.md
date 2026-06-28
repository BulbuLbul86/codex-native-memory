---
name: codex-native-memory
description: Search local Codex cross-session memory when the user asks what happened in other chats, wants project continuity, or asks to recall prior Codex work.
---

# Codex Native Memory

Use this skill when the task needs context from earlier Codex chats.

Codex is the primary coding AI. Claude, Gemini, Cursor, Aider, and other tools
are optional attached sources or review targets. Never describe an external AI
as the default coding AI.

Preferred flow:

1. If the MCP server is available, call `memory_search` with a focused query.
2. If MCP is not available but this repository is accessible, run:

   ```powershell
   python -m codex_native_memory search "<query>" --limit 10
   ```

3. Use retrieved memory as context, not as unquestioned truth. If the result is stale or uncertain,
   verify against the current workspace.

For broad project catch-up, search for the project name, the active task, and the user's exact
phrasing. For implementation work, prefer concrete facts: decisions, constraints, paths, commands,
and unresolved tasks.

When the user writes new code and asks to verify it, check configured review
targets with `memory_sources` action `review-options` when available. Ask
whether to keep review inside Codex only or also prepare/send an external
Claude/Gemini/generic review.
