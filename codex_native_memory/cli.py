from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import asdict
from typing import Any

from .codex_provider import CodexProvider
from .db import MemoryDB
from .ingest import backfill, backfill_configured_sources
from .mcp_server import serve
from .paths import default_transcript_globs, ensure_runtime_dirs
from .processor import Processor
from .sources import (
    SOURCE_TYPES,
    SourceDefinition,
    add_or_update_source,
    load_sources,
    remove_source,
    review_options,
    save_sources,
    set_default_coding_source,
)


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
    backfill_cmd.add_argument("--source", help="Import one configured source by id.")
    backfill_cmd.add_argument(
        "--all-sources",
        action="store_true",
        help="Import all configured sources. Codex stays the primary coding AI.",
    )
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

    context = subcommands.add_parser("context", help="Build project-oriented memory context.")
    context.add_argument("query", nargs="?", default=None)
    context.add_argument("--project")
    context.add_argument("--cwd")
    context.add_argument("--limit", type=int, default=5)
    context.add_argument("--json", action="store_true")
    context.set_defaults(handler=cmd_context)

    process = subcommands.add_parser("process-queue", help="Summarize pending sessions.")
    process.add_argument("--limit", type=int, default=10)
    process.add_argument("--mode", choices=["auto", "codex", "extractive"], default="auto")
    process.set_defaults(handler=cmd_process_queue)

    sources = subcommands.add_parser("sources", help="Manage attached AI sources.")
    source_commands = sources.add_subparsers(dest="sources_command")

    sources_list = source_commands.add_parser("list", help="List configured sources.")
    sources_list.add_argument("--json", action="store_true")
    sources_list.set_defaults(handler=cmd_sources_list)

    sources_add = source_commands.add_parser("add", help="Add or update an external source.")
    sources_add.add_argument("id")
    sources_add.add_argument("--type", choices=sorted(SOURCE_TYPES), required=True)
    sources_add.add_argument("--name")
    sources_add.add_argument("--path", action="append", dest="paths")
    sources_add.add_argument("--project")
    sources_add.add_argument("--disabled", action="store_true")
    sources_add.add_argument("--review-enabled", action="store_true")
    sources_add.add_argument("--review-command")
    sources_add.add_argument("--notes")
    sources_add.set_defaults(handler=cmd_sources_add)

    sources_remove = source_commands.add_parser("remove", help="Remove a configured source.")
    sources_remove.add_argument("id")
    sources_remove.set_defaults(handler=cmd_sources_remove)

    sources_default = source_commands.add_parser(
        "set-default",
        help="Confirm/reset Codex as the primary coding AI.",
    )
    sources_default.add_argument("id", nargs="?", default="codex")
    sources_default.set_defaults(handler=cmd_sources_set_default)

    sources_review = source_commands.add_parser(
        "review-options",
        help="Show external AI review targets and the question to ask the user.",
    )
    sources_review.add_argument("--json", action="store_true")
    sources_review.set_defaults(handler=cmd_sources_review_options)

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
    stats: dict[str, Any]
    if args.source or args.all_sources:
        stats = backfill_configured_sources(
            db,
            source_id=args.source,
            limit=args.limit,
            force=args.force,
            data_root=root,
        )
    else:
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


def cmd_context(args: argparse.Namespace) -> int:
    root = ensure_runtime_dirs(args.data_dir)
    db = MemoryDB(root / "memory.sqlite3")
    payload = db.project_context(
        project=args.project,
        cwd=args.cwd,
        query=args.query,
        limit=args.limit,
    )
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"Project: {payload.get('project') or 'all'}")
        print(f"Sessions: {payload['session_count']}")
        print("\nBrief:")
        print(payload["brief"])
        _print_context_section("Decisions", payload["decisions"])
        _print_context_section("Open questions", payload["open_questions"])
        _print_observations(payload["observations"])
        _print_summaries(payload["summaries"])
        _print_matches(payload["relevant_matches"])
    db.close()
    return 0


def cmd_process_queue(args: argparse.Namespace) -> int:
    root = ensure_runtime_dirs(args.data_dir)
    db = MemoryDB(root / "memory.sqlite3")
    stats = Processor(db).process(limit=args.limit, mode=args.mode)
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    db.close()
    return 0


def cmd_sources_list(args: argparse.Namespace) -> int:
    config = load_sources(args.data_dir)
    payload = [asdict(source) for source in config.sources]
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        default = config.default_coding_source()
        print(f"Primary coding AI: {default.name if default else 'Codex'}")
        for source in config.sources:
            flags: list[str] = []
            if source.default_for_coding:
                flags.append("primary")
            if source.review_enabled:
                flags.append("review")
            if not source.enabled:
                flags.append("disabled")
            suffix = f" ({', '.join(flags)})" if flags else ""
            print(f"- {source.id}: {source.name} [{source.type}]{suffix}")
    return 0


def cmd_sources_add(args: argparse.Namespace) -> int:
    config = load_sources(args.data_dir)
    source = SourceDefinition(
        id=args.id,
        type=args.type,
        name=args.name or args.id,
        paths=args.paths or [],
        project=args.project,
        enabled=not args.disabled,
        default_for_coding=args.id == "codex",
        review_enabled=args.review_enabled and args.id != "codex",
        review_command=args.review_command,
        notes=args.notes,
    )
    add_or_update_source(config, source)
    path = save_sources(config, args.data_dir)
    print(f"Saved source '{source.id}' to {path}")
    if source.id == "codex":
        print("Codex is the primary coding AI.")
    else:
        print("Codex remains the primary coding AI. This source is attached to Codex.")
    return 0


def cmd_sources_remove(args: argparse.Namespace) -> int:
    config = load_sources(args.data_dir)
    if args.id == "codex":
        path = save_sources(config, args.data_dir)
        print("Codex is the primary coding AI and cannot be removed.")
        print(f"Saved sources to {path}")
        return 0
    removed = remove_source(config, args.id)
    path = save_sources(config, args.data_dir)
    print(f"Removed source '{args.id}'." if removed else f"Source '{args.id}' was not found.")
    print(f"Saved sources to {path}")
    return 0


def cmd_sources_set_default(args: argparse.Namespace) -> int:
    config = load_sources(args.data_dir)
    if not set_default_coding_source(config, args.id):
        raise SystemExit(
            "Codex is always the primary coding AI. External sources can only attach to it."
        )
    path = save_sources(config, args.data_dir)
    default = config.default_coding_source()
    print(f"Primary coding AI: {default.name if default else args.id}")
    print(f"Saved sources to {path}")
    return 0


def cmd_sources_review_options(args: argparse.Namespace) -> int:
    payload = review_options(load_sources(args.data_dir))
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        primary = payload.get("primary_coding_ai") or {}
        print(f"Primary coding AI: {primary.get('name') or 'Codex'}")
        print(payload["question"])
        for target in payload["review_targets"]:
            command = target.get("review_command") or "prompt-only"
            print(f"- {target['id']}: {target['name']} ({command})")
    return 0


def cmd_mcp(args: argparse.Namespace) -> int:
    root = ensure_runtime_dirs(args.data_dir)
    db = MemoryDB(root / "memory.sqlite3")
    serve(db)
    return 0


def _print_context_section(title: str, items: list[str]) -> None:
    if not items:
        return
    print(f"\n{title}:")
    for item in items:
        print(f"- {item}")


def _print_observations(items: list[dict[str, Any]]) -> None:
    if not items:
        return
    print("\nObservations:")
    for item in items:
        print(f"- [{item['scope']}/{item['subject']}] {item['text']}")


def _print_summaries(items: list[dict[str, Any]]) -> None:
    if not items:
        return
    print("\nRecent summaries:")
    for item in items:
        title = item.get("title") or item["session_id"]
        print(f"- {title}: {item['summary']}")


def _print_matches(items: list[dict[str, Any]]) -> None:
    if not items:
        return
    print("\nRelevant matches:")
    for item in items:
        print(f"- [{item['type']}] {item['session_id']}: {item['text']}")
