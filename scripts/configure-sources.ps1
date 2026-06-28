$ErrorActionPreference = "Stop"

$PluginRoot = Split-Path -Parent $PSScriptRoot
$separator = [System.IO.Path]::PathSeparator
if ($env:PYTHONPATH) {
  $env:PYTHONPATH = "$PluginRoot$separator$env:PYTHONPATH"
} else {
  $env:PYTHONPATH = $PluginRoot
}

Write-Host "Codex is the primary coding AI."
Write-Host "If you only use Codex, press Enter to skip every optional external source."
Write-Host "Claude, Gemini, and other tools can be attached later as memory sources or review targets."
Write-Host ""

$configured = $false

$claudePath = Read-Host "Claude transcript glob (leave empty to skip)"
if ($claudePath) {
  $configured = $true
  $claudeReview = Read-Host "Claude review command (leave empty for prompt-only)"
  $args = @(
    "-m", "codex_native_memory", "sources", "add", "claude",
    "--type", "claude",
    "--name", "Claude",
    "--path", $claudePath,
    "--review-enabled"
  )
  if ($claudeReview) {
    $args += @("--review-command", $claudeReview)
  }
  python @args
}

$geminiPath = Read-Host "Gemini transcript glob (leave empty to skip)"
if ($geminiPath) {
  $configured = $true
  $geminiReview = Read-Host "Gemini review command (leave empty for prompt-only)"
  $args = @(
    "-m", "codex_native_memory", "sources", "add", "gemini",
    "--type", "gemini",
    "--name", "Gemini",
    "--path", $geminiPath,
    "--review-enabled"
  )
  if ($geminiReview) {
    $args += @("--review-command", $geminiReview)
  }
  python @args
}

Write-Host ""
python -m codex_native_memory sources list
Write-Host ""
if ($configured) {
  Write-Host "To import all configured sources later:"
  Write-Host "python -m codex_native_memory backfill --all-sources"
} else {
  Write-Host "No external sources configured. Codex-only mode is ready."
  Write-Host "Later, rerun this script or use: python -m codex_native_memory sources add <id> --type <type> --path <glob>"
}
