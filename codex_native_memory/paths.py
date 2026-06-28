from __future__ import annotations

import os
from pathlib import Path

APP_DIR_NAME = ".codex-native-memory"
ENV_HOME = "CODEX_NATIVE_MEMORY_HOME"
ENV_TRANSCRIPTS = "CODEX_NATIVE_MEMORY_TRANSCRIPTS"
ENV_CODEX = "CODEX_NATIVE_MEMORY_CODEX"


def data_dir(value: str | os.PathLike[str] | None = None) -> Path:
    raw = value or os.environ.get(ENV_HOME)
    if raw:
        return Path(raw).expanduser().resolve()
    return (Path.home() / APP_DIR_NAME).resolve()


def db_path(root: str | os.PathLike[str] | None = None) -> Path:
    return data_dir(root) / "memory.sqlite3"


def internal_workdir(root: str | os.PathLike[str] | None = None) -> Path:
    return data_dir(root) / "internal-codex-runs"


def default_transcript_globs() -> list[str]:
    configured = os.environ.get(ENV_TRANSCRIPTS)
    if configured:
        return [part for part in configured.split(os.pathsep) if part]
    return [str(Path.home() / ".codex" / "sessions" / "**" / "*.jsonl")]


def ensure_runtime_dirs(root: str | os.PathLike[str] | None = None) -> Path:
    base = data_dir(root)
    base.mkdir(parents=True, exist_ok=True)
    internal_workdir(base).mkdir(parents=True, exist_ok=True)
    (base / "tmp").mkdir(parents=True, exist_ok=True)
    return base
