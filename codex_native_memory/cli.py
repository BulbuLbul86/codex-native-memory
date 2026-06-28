from __future__ import annotations

import argparse
import json
import sys
import time
from typing import Any

from .codex_provider import CodexProvider
from .db import MemoryDB
from .ingest import backfill
from .mcp_server import serve
from .paths import default_transcript_globs, ensure_runtime_dirs
from .processor import Processor


def main(argv: list[str] | None = None) -> int:
    _configure_stdio()
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "handler"):
        parser.print_help()
        return 2
    return int(args.handler(args) or 0)


def _configure_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if reconfigure is not None:
            reconfigure(encoding="utf-8", errors="replace")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="codex-native-memory")
    parser.add_argument("--data-dir", default=None, help="Override CODEX_NATIVE_MEMORY_HOME.")
    subcommands = parser.add_subparsers(dest="command")

    doctor = subcommands.add_parser("doctor", help="Show paths and health.")
    doctor.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    doctor.set_defaults(handler=cmd_doctor)

    init = subcommands.add_parser("init", help="Create the local database.")
    init.set_defaults(handler=cmd_init)

    backfill_cmd = subcommands.add_parser("backfill", help="Import Codex transcript JSONL files.")
    backfill_cmd.add_argument("--limit", type=int, default=None)
    backfill_cmd.add_argument("--force", action="store_true")
    backfill_cmd.add_argument("--glob", action="append", dest="patterns")
    backfill_cmd.set_defaults(handler=cmd_backfill)

    watch = subcommands.add_parser("watch", help="Poll transcript files and import changes.")
    watch.add_argument("--interval", type=float, default=5.0)
    watch.add_argument("--limit", type=int, default=None)
    watch.add_argument("--glob", action="append", dest="patterns")
    watch.set_defaults(handler=cmd_watch)

    search = subcommands.add_parser("search", help="Search imported memory.")
    search.add_argument("query")
    search.add_argument("--limit", type=int, default=10)
    search.add_argument(
        "--kind",
        default="all",
        choices=["all", "messages", "prompts", "answers", "summaries", "observations"],
    )
    search.add_argument("--json", action="store_true")
    search.set_defaults(handler=cmd_search)

    process = subcommands.add_parser("process-queue", help="Summarize pending sessions.")
    process.add_argument("--limit", type=int, default=10)
    process.add_argument("--mode", choices=["auto", "codex", "extractive"], default="auto")
    process.set_defaults(handler=cmd_process_queue)

    mcp = subcommands.add_parser("mcp", help="Run the MCP stdio server.")
    mcp.set_defaults(handler=cmd_mcp)

    return parser


def cmd_doctor(args: argparse.Namespace) -> int:
    root = ensure_runtime_dirs(args.data_dir)
    db = MemoryDB(root / "memory.sqlite3")
    provider = CodexProvider(root=root)
    payload: dict[str, Any] = {
        "data_dir": str(root),
        "transcript_globs": default_transcript_globs(),
        "codex_cli": str(provider.codex_path) if provider.codex_path else None,
        "codex_provider_available": provider.available(),
        "db": db.stats(),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"Data dir: {payload['data_dir']}")
        print(f"Codex CLI: {payload['codex_cli'] or 'not found'}")
        provider_status = "available" if payload["codex_provider_available"] else "unavailable"
        print(f"Codex provider: {provider_status}")
        print(f"Database: {payload['db']['path']}")
        print(f"Sessions: {payload['db']['sessions']}")
        print(f"Messages: {payload['db']['messages']}")
        print(f"Summaries: {payload['db']['summaries']}")
        print(f"Observations: {payload['db']['observations']}")
        print(f"Queue: {payload['db']['queue']}")
    db.close()
    return 0


def cmd_init(args: argparse.Namespace) -> int:
    root = ensure_runtime_dirs(args.data_dir)
    db = MemoryDB(root / "memory.sqlite3")
    print(json.dumps(db.stats(), ensure_ascii=False, indent=2))
    db.close()
    return 0


def cmd_backfill(args: argparse.Namespace) -> int:
    root = ensure_runtime_dirs(args.data_dir)
    db = MemoryDB(root / "memory.sqlite3")
    stats = backfill(
        db,
        patterns=args.patterns,
        limit=args.limit,
        force=args.force,
        data_root=root,
    )
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    db.close()
    return 0


def cmd_watch(args: argparse.Namespace) -> int:
    root = ensure_runtime_dirs(args.data_dir)
    db = MemoryDB(root / "memory.sqlite3")
    try:
        while True:
            stats = backfill(db, patterns=args.patterns, limit=args.limit, data_root=root)
            print(json.dumps(stats, ensure_ascii=False), flush=True)
            time.sleep(args.interval)
    except KeyboardInterrupt:
        return 0
    finally:
        db.close()


def cmd_search(args: argparse.Namespace) -> int:
    root = ensure_runtime_dirs(args.data_dir)
    db = MemoryDB(root / "memory.sqlite3")
    results = db.search(args.query, limit=args.limit, kind=args.kind)
    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for index, result in enumerate(results, start=1):
            label = result.get("type")
            session_id = result.get("session_id")
            text = result.get("text")
            print(f"{index}. [{label}] {session_id}: {text}")
    db.close()
    return 0


def cmd_process_queue(args: argparse.Namespace) -> int:
    root = ensure_runtime_dirs(args.data_dir)
    db = MemoryDB(root / "memory.sqlite3")
    stats = Processor(db).process(limit=args.limit, mode=args.mode)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    db.close()
    return 0


def cmd_mcp(args: argparse.Namespace) -> int:
    root = ensure_runtime_dirs(args.data_dir)
    db = MemoryDB(root / "memory.sqlite3")
    serve(db)
    return 0
