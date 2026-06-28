from __future__ import annotations

from pathlib import Path
from typing import Any

from .db import MemoryDB
from .ingest import backfill, backfill_configured_sources
from .processor import Processor
from .sources import load_sources, review_options


def bootstrap_memory(
    db: MemoryDB,
    *,
    data_root: str | Path | None = None,
    project: str | None = None,
    cwd: str | Path | None = None,
    query: str | None = None,
    context_limit: int = 5,
    import_limit: int | None = 100,
    summary_limit: int = 5,
    summary_mode: str = "extractive",
    force: bool = False,
    all_sources: bool = False,
    source_id: str | None = None,
) -> dict[str, Any]:
    root = Path(data_root).expanduser().resolve() if data_root is not None else db.path.parent
    context_limit = max(1, context_limit)
    import_limit = max(0, import_limit) if import_limit is not None else None
    summary_limit = max(0, summary_limit)
    if summary_mode not in {"auto", "codex", "extractive"}:
        summary_mode = "extractive"

    if source_id or all_sources:
        import_stats: dict[str, Any] = backfill_configured_sources(
            db,
            source_id=source_id,
            limit=import_limit,
            force=force,
            data_root=root,
        )
    else:
        import_stats = backfill(
            db,
            limit=import_limit,
            force=force,
            data_root=root,
        )

    summary_stats = {"seen": 0, "done": 0, "fallback": 0, "errors": 0}
    if summary_limit > 0:
        summary_stats = Processor(db).process(limit=summary_limit, mode=summary_mode)

    config = load_sources(root)
    review = review_options(config)
    enabled_sources = [source for source in config.sources if source.enabled]
    profile = db.project_profile(project=project, cwd=cwd, limit=max(context_limit * 2, 10))
    context = db.project_context(
        project=project,
        cwd=cwd,
        query=query,
        limit=context_limit,
    )
    return {
        "import": import_stats,
        "summaries": summary_stats,
        "profile": profile,
        "context": context,
        "codex_only": all(source.id == "codex" for source in enabled_sources),
        "primary_coding_ai": review["primary_coding_ai"],
        "external_review_configured": review["external_review_configured"],
        "review_targets": review["review_targets"],
        "review_question": review["question"],
    }
