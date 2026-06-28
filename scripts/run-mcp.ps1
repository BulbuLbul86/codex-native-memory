$ErrorActionPreference = "Stop"

$PluginRoot = Split-Path -Parent $PSScriptRoot
$separator = [System.IO.Path]::PathSeparator
if ($env:PYTHONPATH) {
  $env:PYTHONPATH = "$PluginRoot$separator$env:PYTHONPATH"
} else {
  $env:PYTHONPATH = $PluginRoot
}

python -m codex_native_memory mcp
exit $LASTEXITCODE
