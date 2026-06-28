---
name: codex-native-memory
description: Search local Codex cross-session memory when the user asks what happened in other chats, wants project continuity, or asks to recall prior Codex work.
---

# Codex Native Memory

Use this skill when the task needs context from earlier Codex chats.

Codex is the primary coding AI. Claude, Gemini, Cursor, Aider, and other tools
are optional attached sources or review targets. Never describe an external AI
as the default coding AI. Codex-only mode is complete and expected when no
external sources are configured.

Preferred flow:

1. If the MCP server is available and the user needs project continuity, call
   `memory_bootstrap` first with the current project/cwd and a focused query
   when available. Use its dynamic profile to gather preferences, constraints,
   warnings, recent activity, decisions, open questions, and relevant matches.
2. If `memory_bootstrap` is unavailable or too heavy for the task, call
   `memory_context` with the current project/cwd and a focused query.
3. For narrow lookups, or when `memory_context` returns too little, call
   `memory_search` with a focused query.
4. If MCP is not available but this repository is accessible, run:

   ```powershell
   python -m codex_native_memory bootstrap "<query>" --cwd "<current cwd>" --summary-mode extractive --json
   ```

5. Use retrieved memory as context, not as unquestioned truth. If the result is stale or uncertain,
   verify against the current workspace.

For broad project catch-up, search for the project name, the active task, and the user's exact
phrasing. For implementation work, prefer concrete facts: decisions, constraints, paths, commands,
and unresolved tasks.

When the user writes new code and asks to verify it, check configured review
targets with `memory_sources` action `review-options` when available. If no
review targets are configured, keep the review inside Codex and do not ask
about Claude/Gemini/generic review. If review targets exist, ask whether to
keep review inside Codex only or also prepare/send the configured external
review.
