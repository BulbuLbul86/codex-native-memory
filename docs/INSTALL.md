# Install Codex Native Memory

This guide installs Codex Native Memory as a local Python package and exposes it
to Codex as an MCP server.

## Requirements

- Python 3.11 or newer.
- Codex Desktop or Codex CLI with a working local Codex login.
- Git.

No Claude, Gemini, OpenRouter, or vendor API key is required.

## 1. Clone the repository

```powershell
git clone https://github.com/BulbuLbul86/codex-native-memory.git
cd codex-native-memory
```

## 2. Install the package

For normal use:

```powershell
python -m pip install -e .
```

For development:

```powershell
python -m pip install -e ".[dev]"
```

## 3. Check local health

```powershell
python -m codex_native_memory doctor
python -m codex_native_memory doctor --json
```

The report shows:

- the memory database path;
- Codex CLI discovery;
- transcript globs;
- MCP wrapper status;
- whether the setup is Codex-only.

## 4. Install the MCP entry for Codex

Windows PowerShell:

```powershell
.\scripts\install-for-codex.ps1
```

macOS/Linux:

```bash
./scripts/install-for-codex.sh
```

Restart Codex after running the installer.

## 5. Use it inside Codex

In a Codex thread, ask naturally:

```text
подними память проекта
```

or:

```text
what did we decide about the memory plugin architecture?
```

The skill should call `memory_bootstrap` first, import recent transcripts, and
return a compact project context.

## 6. Optional external sources

External AI tools are optional. Codex remains the primary coding AI.

Windows helper:

```powershell
.\scripts\configure-sources.ps1
```

Manual examples:

```powershell
python -m codex_native_memory sources add claude --type claude --path "$HOME\.claude\**\*.jsonl" --review-enabled
python -m codex_native_memory sources add gemini --type gemini --path "$HOME\.gemini\**\*.jsonl" --review-enabled
python -m codex_native_memory backfill --all-sources
```

If you only use Codex, skip this section.

## 7. Useful fallback commands

```powershell
python -m codex_native_memory bootstrap "current task" --cwd "$PWD" --json
python -m codex_native_memory context "current task" --cwd "$PWD" --json
python -m codex_native_memory search "project decision" --limit 10
python -m codex_native_memory memories --cwd "$PWD"
python -m codex_native_memory remember "Use Russian answers for this project." --cwd "$PWD"
```

These commands are maintenance tools. Day to day, Codex should use the MCP tools
for you.
