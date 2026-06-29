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
   when available. Use its pinned memory and dynamic profile to gather
   preferences, constraints, warnings, recent activity, decisions, open
   questions, and relevant matches.
   If the bootstrap result includes `project_resolution.strategy =
   "recommended_candidate"`, treat `recommended_profile` and
   `recommended_context` as the likely real project context. When its confidence
   is `high`, use it directly; when confidence is lower, mention the suggested
   project briefly and avoid presenting it as certain.
2. If `memory_bootstrap` is unavailable or too heavy for the task, call
   `memory_context` with the current project/cwd and a focused query.
3. For narrow lookups, or when `memory_context` returns too little, call
   `memory_search` with a focused query.
4. When the user explicitly asks Codex to remember a durable preference, rule,
   or project fact, call `memory_remember`. Use `scope=user` for global user
   preferences, `scope=project` for project facts, and `scope=workflow` for
   process guardrails. Use `memory_notes` to inspect stored items and
   `memory_update` to fix an item by id. Use `memory_forget` to delete a bad
   item by id. Re-remembering the same scoped subject/text updates the existing
   item instead of creating a duplicate.
5. For backups, migration between machines, or project handoff, use
   `memory_export`. Restore pinned memory with `memory_import_bundle`; the
   imported project can be overridden with `project`/`cwd` for project and
   workflow scoped items, while user scoped items remain global. Repeated
   imports use stable origin keys, so edited source memories update instead of
   multiplying.
6. If MCP is not available but this repository is accessible, run:

   ```powershell
   python -m codex_native_memory bootstrap "<query>" --cwd "<current cwd>" --summary-mode extractive --json
   ```

7. Use retrieved memory as context, not as unquestioned truth. If the result is stale or uncertain,
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
