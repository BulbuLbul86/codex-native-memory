# Troubleshooting

## Codex does not show memory tools

Run:

```powershell
python -m codex_native_memory doctor --json
```

Check that:

- `mcp.wrapper_exists` is `true`;
- `mcp.transport` is `json-lines`;
- `db.path` points to the expected local database;
- `codex_provider_available` is `true` if you want Codex-generated summaries.

Then reinstall the MCP entry and restart Codex:

```powershell
.\scripts\install-for-codex.ps1
```

On macOS/Linux:

```bash
./scripts/install-for-codex.sh
```

## A thread reports a closed MCP transport

If this happens immediately after a plugin reinstall or process cleanup, the
thread may still hold a stale MCP connection. Use the CLI fallback once:

```powershell
python -m codex_native_memory bootstrap "current task" --cwd "$PWD" --summary-mode extractive --json
```

Then retry in a fresh Codex thread.

## The current Codex folder is `new-chat*`

Temporary Codex workspaces can look empty. `memory_bootstrap` includes project
candidate discovery and may return:

- `project_resolution`;
- `project_candidates`;
- `recommended_profile`;
- `recommended_context`.

When confidence is high, use the recommended real project context. When it is
low, mention the uncertainty before relying on it.

## No previous sessions were found

Check the transcript glob:

```powershell
python -m codex_native_memory doctor --json
```

By default, Codex transcripts are read from:

```text
~/.codex/sessions/**/*.jsonl
```

Override the glob with:

```powershell
$env:CODEX_NATIVE_MEMORY_TRANSCRIPTS = "C:\path\to\sessions\**\*.jsonl"
python -m codex_native_memory backfill --force
```

## Codex summaries are unavailable

The plugin still works with extractive summaries. Run:

```powershell
python -m codex_native_memory process-queue --mode extractive --limit 25
```

`--mode codex` needs a local Codex CLI discovered by `doctor`.

## Reset local memory

The runtime directory defaults to:

```text
~/.codex-native-memory
```

Back it up before deleting it. The database is local SQLite and is not uploaded
by the plugin.
