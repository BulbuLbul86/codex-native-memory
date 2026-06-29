# Codex Native Memory v0.1.0

Codex Native Memory is a local, Codex-first memory layer for Codex Desktop and
Codex CLI. It imports local Codex transcripts, stores them in SQLite, and
exposes project memory through MCP tools.

## Highlights

- Local cross-session memory for Codex conversations.
- Codex-only mode by default. Claude, Gemini, and other tools are optional
  attached sources, not required dependencies.
- SQLite storage with FTS search when available.
- MCP tools for search, import, context, bootstrap, health, and pinned memory.
- Project bootstrap that imports recent sessions, processes summaries, and
  returns a compact project profile.
- Temporary `new-chat*` workspace detection with project recommendations.
- Pinned memory for durable user, project, and workflow rules.
- Export/import for project handoff and backups.
- Windows and macOS/Linux Codex MCP installer scripts.
- CI on Python 3.11 and 3.12.

## Install

```powershell
git clone https://github.com/BulbuLbul86/codex-native-memory.git
cd codex-native-memory
python -m pip install -e .
python -m codex_native_memory doctor
.\scripts\install-for-codex.ps1
```

On macOS/Linux:

```bash
git clone https://github.com/BulbuLbul86/codex-native-memory.git
cd codex-native-memory
python -m pip install -e .
python -m codex_native_memory doctor
./scripts/install-for-codex.sh
```

Restart Codex after installing the MCP entry.

## First prompt in Codex

Ask naturally:

```text
подними память проекта
```

The skill should call `memory_bootstrap`, import recent Codex sessions, and
return relevant project context.

## Useful links

- [Install guide](https://github.com/BulbuLbul86/codex-native-memory/blob/main/docs/INSTALL.md)
- [Troubleshooting](https://github.com/BulbuLbul86/codex-native-memory/blob/main/docs/TROUBLESHOOTING.md)
- [Changelog](https://github.com/BulbuLbul86/codex-native-memory/blob/main/CHANGELOG.md)
- [Security policy](https://github.com/BulbuLbul86/codex-native-memory/blob/main/SECURITY.md)

## Notes

This is an MVP release. Treat retrieved memory as context, not as unquestioned
truth. Verify stale or high-impact facts against the current workspace.
