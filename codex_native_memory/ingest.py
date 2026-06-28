from __future__ import annotations

import glob
from pathlib import Path
from typing import Iterable

from .db import MemoryDB
from .paths import data_dir as default_data_dir
from .paths import default_transcript_globs, internal_workdir
from .transcripts import parse_jsonl_file


def iter_transcript_files(patterns: Iterable[str] | None = None) -> list[Path]:
    seen: set[Path] = set()
    files: list[Path] = []
    for pattern in patterns or default_transcript_globs():
        for match in glob.iglob(pattern, recursive=True):
            path = Path(match)
            if not path.is_file() or path.suffix.lower() != ".jsonl":
                continue
            resolved = path.resolve()
            if resolved in seen:
                continue
            seen.add(resolved)
            files.append(resolved)
    files.sort(key=lambda item: item.stat().st_mtime, reverse=True)
    return files


def backfill(
    db: MemoryDB,
    *,
    patterns: Iterable[str] | None = None,
    limit: int | None = None,
    force: bool = False,
    data_root: str | Path | None = None,
) -> dict[str, int]:
    root = default_data_dir(data_root)
    files = iter_transcript_files(patterns)
    if limit is not None:
        files = files[:limit]

    stats = {"seen": 0, "imported": 0, "skipped": 0, "empty": 0, "errors": 0}
    internal_roots = [internal_workdir(root)]
    for path in files:
        stats["seen"] += 1
        try:
            mtime = path.stat().st_mtime
            known_mtime = db.source_mtime(path)
            if not force and known_mtime is not None and known_mtime >= mtime:
                stats["skipped"] += 1
                continue
            parsed = parse_jsonl_file(path, internal_roots=internal_roots)
            if not parsed.messages:
                stats["empty"] += 1
                continue
            db.replace_session(parsed, source_mtime=mtime)
            stats["imported"] += 1
        except OSError:
            stats["errors"] += 1
        except Exception:
            stats["errors"] += 1
    return stats
