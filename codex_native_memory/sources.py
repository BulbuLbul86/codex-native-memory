from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any

from .paths import data_dir, default_transcript_globs, ensure_runtime_dirs

SOURCE_TYPES = {"codex", "claude", "gemini", "generic-jsonl", "generic-text"}


@dataclass(slots=True)
class SourceDefinition:
    id: str
    type: str
    name: str
    paths: list[str] = field(default_factory=list)
    project: str | None = None
    enabled: bool = True
    default_for_coding: bool = False
    review_enabled: bool = False
    review_command: str | None = None
    notes: str | None = None

    @property
    def source_app(self) -> str:
        return self.type.split("-", 1)[0]

    @property
    def source_kind(self) -> str:
        return self.type


@dataclass(slots=True)
class SourcesConfig:
    version: int = 1
    sources: list[SourceDefinition] = field(default_factory=list)

    def default_coding_source(self) -> SourceDefinition | None:
        for source in self.sources:
            if source.enabled and source.default_for_coding:
                return source
        return None

    def review_sources(self) -> list[SourceDefinition]:
        return [
            source
            for source in self.sources
            if source.id != "codex" and source.enabled and source.review_enabled
        ]


def sources_path(root: str | Path | None = None) -> Path:
    return data_dir(root) / "sources.json"


def load_sources(root: str | Path | None = None) -> SourcesConfig:
    ensure_runtime_dirs(root)
    path = sources_path(root)
    if not path.exists():
        return SourcesConfig(sources=[default_codex_source()])

    raw_payload = json.loads(path.read_text(encoding="utf-8"))
    payload = raw_payload if isinstance(raw_payload, dict) else {}
    raw_sources = payload.get("sources")
    if not isinstance(raw_sources, list):
        raw_sources = []
    sources = [_source_from_dict(item) for item in raw_sources if isinstance(item, dict)]
    version = int(payload.get("version", 1))
    config = SourcesConfig(version=version, sources=sources)
    enforce_codex_primary(config)
    return config


def save_sources(config: SourcesConfig, root: str | Path | None = None) -> Path:
    ensure_runtime_dirs(root)
    enforce_codex_primary(config)
    path = sources_path(root)
    payload = {
        "version": config.version,
        "sources": [asdict(source) for source in config.sources],
    }
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def default_codex_source() -> SourceDefinition:
    return SourceDefinition(
        id="codex",
        type="codex",
        name="Codex",
        paths=default_transcript_globs(),
        enabled=True,
        default_for_coding=True,
        review_enabled=False,
        notes="Codex is the primary coding shell. External AI sources attach to it.",
    )


def add_or_update_source(config: SourcesConfig, source: SourceDefinition) -> None:
    validate_source(source)
    source.default_for_coding = source.id == "codex"
    for index, existing in enumerate(config.sources):
        if existing.id == source.id:
            config.sources[index] = source
            enforce_codex_primary(config)
            return
    config.sources.append(source)
    enforce_codex_primary(config)


def remove_source(config: SourcesConfig, source_id: str) -> bool:
    if source_id == "codex":
        enforce_codex_primary(config)
        return False
    before = len(config.sources)
    config.sources = [source for source in config.sources if source.id != source_id]
    enforce_codex_primary(config)
    return len(config.sources) != before


def set_default_coding_source(config: SourcesConfig, source_id: str) -> bool:
    enforce_codex_primary(config)
    return source_id == "codex"


def get_source(config: SourcesConfig, source_id: str) -> SourceDefinition | None:
    for source in config.sources:
        if source.id == source_id:
            return source
    return None


def review_options(config: SourcesConfig) -> dict[str, Any]:
    default_source = config.default_coding_source()
    targets = config.review_sources()
    question = "Проверяем новый код только в Codex или подключаем внешнее AI-ревью?"
    if targets:
        names = ", ".join(source.name for source in targets)
        question = f"{question} Настроенные цели: {names}."
    return {
        "primary_coding_ai": asdict(default_source) if default_source else None,
        "review_targets": [asdict(source) for source in targets],
        "question": question,
        "suggested_prompt": build_review_prompt_template(targets),
    }


def build_review_prompt_template(targets: list[SourceDefinition]) -> str:
    target_names = ", ".join(source.name for source in targets) or "external AI reviewer"
    return (
        f"Ask {target_names} to review the current code changes. "
        "Focus on correctness, security, regressions, missing tests, and maintainability. "
        "Return concrete findings with file/line references when possible."
    )


def validate_source(source: SourceDefinition) -> None:
    normalized = source.id.replace("-", "").replace("_", "")
    if not source.id or not normalized.isalnum():
        raise ValueError("Source id must contain only letters, digits, '-' and '_'.")
    if source.type not in SOURCE_TYPES:
        allowed = ", ".join(sorted(SOURCE_TYPES))
        raise ValueError(f"Unsupported source type '{source.type}'. Allowed: {allowed}.")
    if source.id == "codex" and source.type != "codex":
        raise ValueError("The built-in Codex source must use type 'codex'.")
    if source.id != "codex" and source.type == "codex":
        raise ValueError("Only the built-in source id 'codex' can use type 'codex'.")
    if not source.paths and source.type != "codex":
        raise ValueError("Non-Codex sources require at least one path/glob.")


def enforce_codex_primary(config: SourcesConfig) -> None:
    codex = get_codex_source(config.sources)
    codex.type = "codex"
    codex.name = codex.name or "Codex"
    codex.enabled = True
    codex.default_for_coding = True
    if not codex.paths:
        codex.paths = default_transcript_globs()
    config.sources = [codex] + [source for source in config.sources if source is not codex]
    for source in config.sources:
        source.default_for_coding = source.id == "codex"


def get_codex_source(sources: list[SourceDefinition]) -> SourceDefinition:
    for source in sources:
        if source.id == "codex":
            return source
    source = default_codex_source()
    sources.insert(0, source)
    return source


def _source_from_dict(payload: dict[str, Any]) -> SourceDefinition:
    return SourceDefinition(
        id=str(payload.get("id") or ""),
        type=str(payload.get("type") or "generic-jsonl"),
        name=str(payload.get("name") or payload.get("id") or "Unnamed source"),
        paths=[str(item) for item in payload.get("paths") or []],
        project=payload.get("project"),
        enabled=bool(payload.get("enabled", True)),
        default_for_coding=bool(payload.get("default_for_coding", False)),
        review_enabled=bool(payload.get("review_enabled", False)),
        review_command=payload.get("review_command"),
        notes=payload.get("notes"),
    )
