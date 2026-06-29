#!/usr/bin/env bash
set -euo pipefail

plugin_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -n "${PYTHONPATH:-}" ]]; then
  export PYTHONPATH="${plugin_root}:${PYTHONPATH}"
else
  export PYTHONPATH="${plugin_root}"
fi

exec python -m codex_native_memory mcp
