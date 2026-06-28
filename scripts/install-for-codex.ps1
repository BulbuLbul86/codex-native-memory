$ErrorActionPreference = "Stop"

$PluginRoot = Split-Path -Parent $PSScriptRoot
$ToolsDir = Join-Path $HOME ".codex\tools"
$ConfigPath = Join-Path $HOME ".codex\config.toml"
$WrapperPath = Join-Path $ToolsDir "codex-native-memory-mcp.ps1"

New-Item -ItemType Directory -Force -Path $ToolsDir | Out-Null

$wrapper = @"
`$ErrorActionPreference = "Stop"
`$PluginRoot = "$PluginRoot"
`$separator = [System.IO.Path]::PathSeparator
if (`$env:PYTHONPATH) {
  `$env:PYTHONPATH = "`$PluginRoot`$separator`$env:PYTHONPATH"
} else {
  `$env:PYTHONPATH = `$PluginRoot
}
python -m codex_native_memory mcp
exit `$LASTEXITCODE
"@
Set-Content -LiteralPath $WrapperPath -Value $wrapper -Encoding UTF8

if (Test-Path -LiteralPath $ConfigPath) {
  $config = Get-Content -Raw -LiteralPath $ConfigPath
} else {
  New-Item -ItemType Directory -Force -Path (Split-Path -Parent $ConfigPath) | Out-Null
  $config = ""
}

$config = [regex]::Replace(
  $config,
  '(?ms)^\[mcp_servers\.codex_native_memory\].*?(?=^\[|\z)',
  ""
)
$config = [regex]::Replace(
  $config,
  '(?ms)^\[mcp_servers\.codex_native_memory\.env\].*?(?=^\[|\z)',
  ""
)

$tomlWrapperPath = $WrapperPath -replace "'", "''"
$block = @"

[mcp_servers.codex_native_memory]
command = 'powershell.exe'
args = ['-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', '$tomlWrapperPath']
startup_timeout_sec = 60

"@

Set-Content -LiteralPath $ConfigPath -Value ($config.TrimEnd() + $block) -Encoding UTF8

Write-Host "Codex Native Memory MCP entry installed."
Write-Host "Codex remains the primary coding AI."
Write-Host "To attach Claude/Gemini sources, run: .\scripts\configure-sources.ps1"
Write-Host "Restart Codex to pick up the new MCP server."
