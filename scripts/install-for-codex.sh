#!/usr/bin/env bash
set -euo pipefail

plugin_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
codex_home="${CODEX_HOME:-${HOME}/.codex}"
tools_dir="${codex_home}/tools"
config_path="${codex_home}/config.toml"
wrapper_path="${tools_dir}/codex-native-memory-mcp"

mkdir -p "${tools_dir}" "$(dirname "${config_path}")"

cat > "${wrapper_path}" <<EOF
#!/usr/bin/env bash
set -euo pipefail
plugin_root='${plugin_root}'
if [[ -n "\${PYTHONPATH:-}" ]]; then
  export PYTHONPATH="\${plugin_root}:\${PYTHONPATH}"
else
  export PYTHONPATH="\${plugin_root}"
fi
exec python -m codex_native_memory mcp
EOF
chmod +x "${wrapper_path}"

python - "${config_path}" "${wrapper_path}" <<'PY'
from __future__ import annotations

import re
import sys
from pathlib import Path

config_path = Path(sys.argv[1])
wrapper_path = Path(sys.argv[2])
config = config_path.read_text(encoding="utf-8") if config_path.exists() else ""
config = re.sub(r"(?ms)^\[mcp_servers\.codex_native_memory\].*?(?=^\[|\Z)", "", config)
config = re.sub(r"(?ms)^\[mcp_servers\.codex_native_memory\.env\].*?(?=^\[|\Z)", "", config)
escaped = str(wrapper_path).replace("'", "''")
block = f"""

[mcp_servers.codex_native_memory]
command = '{escaped}'
startup_timeout_sec = 60

"""
config_path.write_text(config.rstrip() + block, encoding="utf-8")
PY

echo "Codex Native Memory MCP entry installed."
echo "Codex remains the primary coding AI."
echo "No external AI sources are required."
echo "Restart Codex to pick up the new MCP server."
