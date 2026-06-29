from __future__ import annotations

import os
import sys
from dataclasses import asdict
from pathlib import Path
from typing import Any

from . import __version__
from .codex_provider import CodexProvider
from .db import MemoryDB
from .paths import ENV_CODEX, ENV_HOME, ENV_TRANSCRIPTS, data_dir, default_transcript_globs
from .sources import load_sources, review_options


def build_health_report(db: MemoryDB) -> dict[str, Any]:
    root = db.path.parent
    provider = CodexProvider(root=root)
    config = load_sources(root)
    default_source = config.default_coding_source()
    review = review_options(config)
    wrapper_path = default_mcp_wrapper_path()

    return {
        "package": {
            "name": "codex-native-memory",
            "version": __version__,
            "root": str(Path(__file__).resolve().parents[1]),
            "python": sys.executable,
        },
        "data_dir": str(root),
        "environment": {
            ENV_HOME: os.environ.get(ENV_HOME),
            ENV_TRANSCRIPTS: os.environ.get(ENV_TRANSCRIPTS),
            ENV_CODEX: os.environ.get(ENV_CODEX),
        },
        "transcript_globs": default_transcript_globs(),
        "codex_cli": str(provider.codex_path) if provider.codex_path else None,
        "codex_provider_available": provider.available(),
        "db": db.stats(),
        "sources": {
            "primary_coding_ai": asdict(default_source) if default_source else None,
            "count": len(config.sources),
            "codex_only": all(source.id == "codex" for source in config.sources),
            "external_review_configured": review["external_review_configured"],
            "review_targets": review["review_targets"],
        },
        "mcp": {
            "transport": "json-lines",
            "accepts_content_length": True,
            "wrapper_path": str(wrapper_path),
            "wrapper_exists": wrapper_path.exists(),
            "stale_connection_hint": (
                "If a long-lived Codex thread reports a closed MCP transport immediately "
                "after plugin reinstall or process cleanup, start a fresh thread or retry "
                "after Codex reconnects the MCP server."
            ),
        },
    }


def default_mcp_wrapper_path() -> Path:
    suffix = "codex-native-memory-mcp.ps1" if os.name == "nt" else "codex-native-memory-mcp"
    return data_dir(None).parent / ".codex" / "tools" / suffix
