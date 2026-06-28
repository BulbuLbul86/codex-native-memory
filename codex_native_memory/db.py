from __future__ import annotations

import json
import os
import re
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from .paths import db_path, ensure_runtime_dirs
from .transcripts import ParsedSession


def utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class MemoryDB:
    def __init__(self, path: str | Path | None = None):
        if path is None:
            ensure_runtime_dirs()
            path = db_path()
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.fts_available = False
        self.initialize()

    def close(self) -> None:
        self.conn.close()

    def initialize(self) -> None:
        self.conn.executescript(
            """
            PRAGMA journal_mode=WAL;
            PRAGMA foreign_keys=ON;

            CREATE TABLE IF NOT EXISTS sessions (
              id TEXT PRIMARY KEY,
              source_path TEXT UNIQUE NOT NULL,
              source_app TEXT NOT NULL DEFAULT 'codex',
              source_kind TEXT NOT NULL DEFAULT 'codex-jsonl',
              title TEXT,
              cwd TEXT,
              project TEXT,
              started_at TEXT,
              updated_at TEXT,
              last_imported_mtime REAL,
              internal INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS messages (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
              ordinal INTEGER NOT NULL,
              role TEXT NOT NULL,
              kind TEXT NOT NULL,
              text TEXT NOT NULL,
              created_at TEXT,
              UNIQUE(session_id, ordinal)
            );

            CREATE TABLE IF NOT EXISTS tool_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
              ordinal INTEGER NOT NULL,
              kind TEXT NOT NULL,
              name TEXT,
              call_id TEXT,
              input_text TEXT,
              output_text TEXT,
              created_at TEXT,
              UNIQUE(session_id, ordinal)
            );

            CREATE TABLE IF NOT EXISTS queue (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
              kind TEXT NOT NULL,
              status TEXT NOT NULL DEFAULT 'pending',
              attempts INTEGER NOT NULL DEFAULT 0,
              error TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL,
              UNIQUE(session_id, kind)
            );

            CREATE TABLE IF NOT EXISTS session_summaries (
              session_id TEXT PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
              summary TEXT NOT NULL,
              decisions_json TEXT NOT NULL DEFAULT '[]',
              open_questions_json TEXT NOT NULL DEFAULT '[]',
              updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS observations (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
              scope TEXT NOT NULL,
              subject TEXT NOT NULL,
              text TEXT NOT NULL,
              confidence REAL NOT NULL DEFAULT 0.5,
              created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS memory_items (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              scope TEXT NOT NULL,
              subject TEXT NOT NULL,
              text TEXT NOT NULL,
              project TEXT,
              cwd TEXT,
              source TEXT NOT NULL DEFAULT 'manual',
              origin_key TEXT,
              confidence REAL NOT NULL DEFAULT 1.0,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            """
        )
        self._ensure_columns(
            "sessions",
            {
                "source_app": "TEXT NOT NULL DEFAULT 'codex'",
                "source_kind": "TEXT NOT NULL DEFAULT 'codex-jsonl'",
            },
        )
        self._ensure_columns("memory_items", {"origin_key": "TEXT"})
        self.conn.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_memory_items_origin
            ON memory_items(origin_key, project, scope)
            """
        )
        self.fts_available = self._ensure_fts()

    def _ensure_columns(self, table: str, columns: dict[str, str]) -> None:
        existing = {
            row["name"] for row in self.conn.execute(f"PRAGMA table_info({table})").fetchall()
        }
        for name, definition in columns.items():
            if name not in existing:
                self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")

    def _ensure_fts(self) -> bool:
        try:
            self.conn.execute(
                """
                CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts
                USING fts5(
                  session_id UNINDEXED,
                  ordinal UNINDEXED,
                  role UNINDEXED,
                  kind UNINDEXED,
                  text
                )
                """
            )
        except sqlite3.OperationalError:
            return False
        return True

    def replace_session(self, parsed: ParsedSession, *, source_mtime: float | None = None) -> None:
        now = utc_now()
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO sessions (
                  id, source_path, source_app, source_kind, title, cwd,
                  project, started_at, updated_at,
                  last_imported_mtime, internal
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                  source_path = excluded.source_path,
                  source_app = excluded.source_app,
                  source_kind = excluded.source_kind,
                  title = excluded.title,
                  cwd = excluded.cwd,
                  project = excluded.project,
                  started_at = excluded.started_at,
                  updated_at = excluded.updated_at,
                  last_imported_mtime = excluded.last_imported_mtime,
                  internal = excluded.internal
                """,
                (
                    parsed.session_id,
                    parsed.source_path,
                    parsed.source_app,
                    parsed.source_kind,
                    parsed.title,
                    parsed.cwd,
                    parsed.project,
                    parsed.started_at,
                    parsed.updated_at,
                    source_mtime,
                    int(parsed.internal),
                ),
            )
            self.conn.execute("DELETE FROM messages WHERE session_id = ?", (parsed.session_id,))
            self.conn.execute("DELETE FROM tool_events WHERE session_id = ?", (parsed.session_id,))
            if self.fts_available:
                self.conn.execute(
                    "DELETE FROM messages_fts WHERE session_id = ?", (parsed.session_id,)
                )

            self.conn.executemany(
                """
                INSERT INTO messages(session_id, ordinal, role, kind, text, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        msg.session_id,
                        msg.ordinal,
                        msg.role,
                        msg.kind,
                        msg.text,
                        msg.created_at,
                    )
                    for msg in parsed.messages
                ],
            )
            self.conn.executemany(
                """
                INSERT INTO tool_events(
                  session_id, ordinal, kind, name, call_id, input_text, output_text, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        event.session_id,
                        event.ordinal,
                        event.kind,
                        event.name,
                        event.call_id,
                        event.input_text,
                        event.output_text,
                        event.created_at,
                    )
                    for event in parsed.tool_events
                ],
            )
            if self.fts_available:
                self.conn.executemany(
                    """
                    INSERT INTO messages_fts(session_id, ordinal, role, kind, text)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    [
                        (msg.session_id, msg.ordinal, msg.role, msg.kind, msg.text)
                        for msg in parsed.messages
                    ],
                )
            if parsed.messages and not parsed.internal:
                self.conn.execute(
                    """
                    INSERT INTO queue(
                      session_id, kind, status, attempts, error, created_at, updated_at
                    )
                    VALUES (?, 'summary', 'pending', 0, NULL, ?, ?)
                    ON CONFLICT(session_id, kind) DO UPDATE SET
                      status = CASE
                        WHEN queue.status = 'processing' THEN queue.status
                        ELSE 'pending'
                      END,
                      error = NULL,
                      updated_at = excluded.updated_at
                    """,
                    (parsed.session_id, now, now),
                )

    def source_mtime(self, source_path: str | Path) -> float | None:
        row = self.conn.execute(
            "SELECT last_imported_mtime FROM sessions WHERE source_path = ?",
            (str(Path(source_path).expanduser().resolve()),),
        ).fetchone()
        if not row:
            return None
        return row["last_imported_mtime"]

    def fetch_messages(self, session_id: str) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT session_id, ordinal, role, kind, text, created_at
            FROM messages
            WHERE session_id = ?
            ORDER BY ordinal
            """,
            (session_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def pending(self, *, limit: int = 10, max_attempts: int = 3) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT id, session_id, kind, status, attempts, error, created_at, updated_at
            FROM queue
            WHERE status IN ('pending', 'error') AND attempts < ?
            ORDER BY updated_at ASC
            LIMIT ?
            """,
            (max_attempts, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def mark_queue(self, queue_id: int, status: str, error: str | None = None) -> None:
        with self.conn:
            self.conn.execute(
                """
                UPDATE queue
                SET status = ?, attempts = attempts + 1, error = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, error, utc_now(), queue_id),
            )

    def store_summary(self, session_id: str, result: dict[str, Any]) -> None:
        now = utc_now()
        decisions = _string_list(result.get("decisions"))
        open_questions = _string_list(result.get("open_questions"))
        summary = str(result.get("summary") or "").strip() or "Imported conversation."
        observations = result.get("observations") or []
        if not isinstance(observations, list):
            observations = []
        with self.conn:
            self.conn.execute(
                """
                INSERT INTO session_summaries(
                  session_id, summary, decisions_json, open_questions_json, updated_at
                )
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(session_id) DO UPDATE SET
                  summary = excluded.summary,
                  decisions_json = excluded.decisions_json,
                  open_questions_json = excluded.open_questions_json,
                  updated_at = excluded.updated_at
                """,
                (
                    session_id,
                    summary,
                    json.dumps(decisions, ensure_ascii=False),
                    json.dumps(open_questions, ensure_ascii=False),
                    now,
                ),
            )
            self.conn.execute("DELETE FROM observations WHERE session_id = ?", (session_id,))
            self.conn.executemany(
                """
                INSERT INTO observations(session_id, scope, subject, text, confidence, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        session_id,
                        str(obs.get("scope") or "project"),
                        str(obs.get("subject") or "general"),
                        str(obs.get("text") or "").strip(),
                        float(obs.get("confidence") or 0.5),
                        now,
                    )
                    for obs in observations
                    if isinstance(obs, dict) and str(obs.get("text") or "").strip()
                ],
            )

    def remember(
        self,
        text: str,
        *,
        scope: str = "project",
        subject: str = "general",
        project: str | None = None,
        cwd: str | Path | None = None,
        source: str = "manual",
        confidence: float = 1.0,
        origin_key: str | None = None,
    ) -> dict[str, Any]:
        clean_text = _clean_memory_text(text)
        if not clean_text:
            raise ValueError("Memory text cannot be empty.")
        clean_scope = _normalize_scope(scope)
        clean_subject = _clean_memory_label(subject, default="general")
        clean_source = _clean_memory_label(source, default="manual")
        clean_origin_key = _clean_origin_key(origin_key)
        project_name = self._memory_target_project(scope=clean_scope, project=project, cwd=cwd)
        cwd_text = _memory_cwd(cwd)
        now = utc_now()
        existing_origin_id = (
            self._matching_memory_origin_id(
                origin_key=clean_origin_key,
                scope=clean_scope,
                project=project_name,
            )
            if clean_origin_key
            else None
        )
        if existing_origin_id is not None:
            return self.update_memory(
                existing_origin_id,
                text=clean_text,
                scope=clean_scope,
                subject=clean_subject,
                project=project_name,
                cwd=cwd,
                source=clean_source,
                confidence=confidence,
                origin_key=clean_origin_key,
            )
        existing_id = self._matching_memory_id(
            scope=clean_scope,
            subject=clean_subject,
            text=clean_text,
            project=project_name,
        )
        if existing_id is not None:
            return self.update_memory(
                existing_id,
                cwd=cwd_text,
                source=clean_source,
                confidence=confidence,
                origin_key=clean_origin_key,
            )
        with self.conn:
            cursor = self.conn.execute(
                """
                INSERT INTO memory_items(
                  scope, subject, text, project, cwd, source,
                  origin_key, confidence, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    clean_scope,
                    clean_subject,
                    clean_text,
                    project_name,
                    cwd_text,
                    clean_source,
                    clean_origin_key,
                    min(max(float(confidence), 0.0), 1.0),
                    now,
                    now,
                ),
            )
        memory_id = cursor.lastrowid
        if memory_id is None:
            raise RuntimeError("SQLite did not return a memory item id.")
        return self.memory_item(memory_id)

    def memory_item(self, memory_id: int) -> dict[str, Any]:
        row = self.conn.execute(
            """
            SELECT
              id, scope, subject, text, project, cwd, source,
              origin_key, confidence, created_at, updated_at
            FROM memory_items
            WHERE id = ?
            """,
            (memory_id,),
        ).fetchone()
        if row is None:
            raise ValueError(f"Memory item not found: {memory_id}")
        return _memory_item_dict(row)

    def update_memory(
        self,
        memory_id: int,
        *,
        text: str | None = None,
        scope: str | None = None,
        subject: str | None = None,
        project: str | None = None,
        cwd: str | Path | None = None,
        source: str | None = None,
        confidence: float | None = None,
        origin_key: str | None = None,
    ) -> dict[str, Any]:
        current = self.memory_item(memory_id)
        clean_scope = _normalize_scope(scope) if scope else str(current["scope"])
        clean_text = _clean_memory_text(text) if text is not None else str(current["text"])
        if not clean_text:
            raise ValueError("Memory text cannot be empty.")
        clean_subject = (
            _clean_memory_label(subject, default="general")
            if subject is not None
            else str(current["subject"])
        )
        clean_source = (
            _clean_memory_label(source, default="manual")
            if source is not None
            else str(current["source"])
        )
        clean_origin_key = (
            _clean_origin_key(origin_key) if origin_key is not None else current.get("origin_key")
        )
        if clean_scope == "user" and project is None:
            project_name = None
        elif project is not None or cwd is not None or scope is not None:
            project_name = self._memory_target_project(
                scope=clean_scope,
                project=project if project is not None else current.get("project"),
                cwd=cwd if cwd is not None else current.get("cwd"),
            )
        else:
            project_name = current.get("project")
        cwd_text = _memory_cwd(cwd) if cwd is not None else current.get("cwd")
        confidence_value = (
            min(max(float(confidence), 0.0), 1.0)
            if confidence is not None
            else float(current["confidence"])
        )
        with self.conn:
            self.conn.execute(
                """
                UPDATE memory_items
                SET
                  scope = ?,
                  subject = ?,
                  text = ?,
                  project = ?,
                  cwd = ?,
                  source = ?,
                  origin_key = ?,
                  confidence = ?,
                  updated_at = ?
                WHERE id = ?
                """,
                (
                    clean_scope,
                    clean_subject,
                    clean_text,
                    project_name,
                    cwd_text,
                    clean_source,
                    clean_origin_key,
                    confidence_value,
                    utc_now(),
                    memory_id,
                ),
            )
        return self.memory_item(memory_id)

    def memory_items(
        self,
        *,
        project: str | None = None,
        cwd: str | Path | None = None,
        scope: str | None = None,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        clean_scope = _normalize_scope(scope) if scope else None
        restrict_project = project is not None or cwd is not None
        project_name = (
            self._memory_target_project(scope="project", project=project, cwd=cwd)
            if restrict_project
            else None
        )
        return self._project_memory_items(
            project_name,
            scope=clean_scope,
            limit=max(limit, 1),
            include_all=not restrict_project,
        )

    def forget_memory(self, memory_id: int) -> bool:
        with self.conn:
            cursor = self.conn.execute("DELETE FROM memory_items WHERE id = ?", (memory_id,))
        return cursor.rowcount > 0

    def export_bundle(
        self,
        *,
        project: str | None = None,
        cwd: str | Path | None = None,
        scope: str | None = None,
        limit: int = 100,
        include_profile: bool = True,
    ) -> dict[str, Any]:
        project_name = self._resolve_project(project=project, cwd=cwd) if (project or cwd) else None
        memories = [
            {**item, "origin_key": _memory_export_origin_key(item)}
            for item in self.memory_items(project=project, cwd=cwd, scope=scope, limit=limit)
        ]
        bundle: dict[str, Any] = {
            "version": 1,
            "exported_at": utc_now(),
            "project": project_name,
            "scope": scope,
            "memories": memories,
        }
        if include_profile and (project is not None or cwd is not None):
            bundle["profile"] = self.project_profile(
                project=project,
                cwd=cwd,
                limit=min(max(limit, 1), 50),
            )
        return bundle

    def import_bundle(
        self,
        payload: Any,
        *,
        project: str | None = None,
        cwd: str | Path | None = None,
        source: str = "import",
    ) -> dict[str, Any]:
        if isinstance(payload, list):
            raw_items = payload
        elif isinstance(payload, dict):
            raw_items = payload.get("memories", [])
        else:
            raise ValueError("Memory import payload must be a JSON object or list.")
        if not isinstance(raw_items, list):
            raise ValueError("Memory import payload must contain a 'memories' list.")

        stats: dict[str, Any] = {
            "seen": 0,
            "imported": 0,
            "updated": 0,
            "skipped": 0,
            "errors": 0,
            "items": [],
        }
        for raw_item in raw_items:
            stats["seen"] += 1
            if not isinstance(raw_item, dict):
                stats["skipped"] += 1
                continue
            try:
                text = _clean_memory_text(str(raw_item.get("text") or ""))
                if not text:
                    stats["skipped"] += 1
                    continue
                scope = str(raw_item.get("scope") or "project")
                subject = str(raw_item.get("subject") or "general")
                clean_scope = _normalize_scope(scope)
                clean_subject = _clean_memory_label(subject, default="general")
                if project is not None:
                    target_project = project
                elif cwd is not None:
                    target_project = None
                else:
                    target_project = raw_item.get("project")
                target_cwd = cwd if cwd is not None else raw_item.get("cwd")
                project_arg = None if clean_scope == "user" else target_project
                project_name = self._memory_target_project(
                    scope=clean_scope,
                    project=str(project_arg) if project_arg is not None else None,
                    cwd=target_cwd,
                )
                origin_key = _memory_export_origin_key(raw_item)
                existing_id = self._matching_memory_id(
                    scope=clean_scope,
                    subject=clean_subject,
                    text=text,
                    project=project_name,
                )
                if origin_key:
                    existing_id = (
                        self._matching_memory_origin_id(
                            origin_key=origin_key,
                            scope=clean_scope,
                            project=project_name,
                        )
                        or existing_id
                    )
                if existing_id is None:
                    item = self.remember(
                        text,
                        scope=clean_scope,
                        subject=clean_subject,
                        project=project_name,
                        cwd=target_cwd,
                        source=source or str(raw_item.get("source") or "import"),
                        confidence=float(raw_item.get("confidence", 1.0)),
                        origin_key=origin_key,
                    )
                else:
                    item = self.update_memory(
                        existing_id,
                        text=text,
                        scope=clean_scope,
                        subject=clean_subject,
                        project=project_name,
                        cwd=target_cwd,
                        source=source or str(raw_item.get("source") or "import"),
                        confidence=float(raw_item.get("confidence", 1.0)),
                        origin_key=origin_key,
                    )
                if existing_id is None:
                    stats["imported"] += 1
                else:
                    stats["updated"] += 1
                stats["items"].append(item)
            except Exception as exc:
                stats["errors"] += 1
                stats["items"].append({"error": str(exc), "raw": raw_item})
        return stats

    def search(self, query: str, *, limit: int = 10, kind: str = "all") -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        if kind in {"all", "messages", "prompts", "answers"}:
            role = {"prompts": "user", "answers": "assistant"}.get(kind)
            results.extend(self._search_messages(query, limit=limit, role=role))
        if kind in {"all", "summaries"}:
            results.extend(self._search_summaries(query, limit=limit))
        if kind in {"all", "observations"}:
            results.extend(self._search_observations(query, limit=limit))
        if kind in {"all", "memories"}:
            results.extend(self._search_memory_items(query, limit=limit))
        return results[:limit]

    def project_context(
        self,
        *,
        project: str | None = None,
        cwd: str | Path | None = None,
        query: str | None = None,
        limit: int = 5,
    ) -> dict[str, Any]:
        project_name = self._resolve_project(project=project, cwd=cwd)
        session_count = self._project_session_count(project_name)
        recent = self.recent_sessions(limit=limit, project=project_name)
        summaries = self._project_summaries(project_name, limit=limit)
        memories = self._project_memory_items(project_name, limit=max(limit * 2, 10))
        observations = self._project_observations(project_name, limit=max(limit * 2, 10))
        matches = self._project_matches(project_name, query=query, limit=limit)
        decisions = _context_strings(
            (decision for summary in summaries for decision in summary["decisions"]),
            limit=max(limit * 2, 6),
        )
        open_questions = _context_strings(
            (question for summary in summaries for question in summary["open_questions"]),
            limit=max(limit * 2, 6),
        )
        return {
            "project": project_name,
            "session_count": session_count,
            "brief": _context_brief(
                project=project_name,
                session_count=session_count,
                summaries=summaries,
                decisions=decisions,
                open_questions=open_questions,
                memories=memories,
                observations=observations,
                matches=matches,
            ),
            "recent_sessions": recent,
            "summaries": summaries,
            "memories": memories,
            "decisions": decisions,
            "open_questions": open_questions,
            "observations": observations,
            "relevant_matches": matches,
        }

    def project_profile(
        self,
        *,
        project: str | None = None,
        cwd: str | Path | None = None,
        limit: int = 10,
    ) -> dict[str, Any]:
        project_name = self._resolve_project(project=project, cwd=cwd)
        session_count = self._project_session_count(project_name)
        recent = self.recent_sessions(limit=min(max(limit, 1), 10), project=project_name)
        summaries = self._project_summaries(project_name, limit=limit)
        memories = self._project_memory_items(project_name, limit=max(limit * 2, 10))
        observations = self._project_observations(project_name, limit=max(limit * 3, 15))
        profile_signals = memories + observations
        decisions = _context_strings(
            (decision for summary in summaries for decision in summary["decisions"]),
            limit=max(limit, 6),
        )
        open_questions = _context_strings(
            (question for summary in summaries for question in summary["open_questions"]),
            limit=max(limit, 6),
        )
        preferences = _context_strings(
            (
                str(item["text"])
                for item in profile_signals
                if _profile_observation_bucket(item) == "preference"
            ),
            limit=limit,
        )
        constraints = _context_strings(
            (
                str(item["text"])
                for item in profile_signals
                if _profile_observation_bucket(item) == "constraint"
            ),
            limit=limit,
        )
        warnings = _context_strings(
            (
                str(item["text"])
                for item in profile_signals
                if _profile_observation_bucket(item) == "warning"
            ),
            limit=limit,
        )
        observation_texts = _context_strings(
            (str(item["text"]) for item in observations),
            limit=limit,
        )
        return {
            "project": project_name,
            "session_count": session_count,
            "profile_kind": "dynamic",
            "updated_at": _latest_timestamp(recent, summaries, memories, observations),
            "brief": _profile_brief(
                project=project_name,
                session_count=session_count,
                summaries=summaries,
                decisions=decisions,
                open_questions=open_questions,
                preferences=preferences,
                constraints=constraints,
                warnings=warnings,
            ),
            "recent_activity": recent[:3],
            "memories": memories,
            "decisions": decisions,
            "open_questions": open_questions,
            "preferences": preferences,
            "constraints": constraints,
            "warnings": warnings,
            "observations": observation_texts,
        }

    def _search_messages(
        self, query: str, *, limit: int, role: str | None = None
    ) -> list[dict[str, Any]]:
        if self.fts_available:
            fts_query = _fts_query(query)
            if fts_query:
                sql = (
                    "SELECT session_id, ordinal, role, kind, text, bm25(messages_fts) AS score "
                    "FROM messages_fts WHERE messages_fts MATCH ?"
                )
                params: list[Any] = [fts_query]
                if role:
                    sql += " AND role = ?"
                    params.append(role)
                sql += " ORDER BY score LIMIT ?"
                params.append(limit)
                try:
                    rows = self.conn.execute(sql, params).fetchall()
                    return [_message_result(row) for row in rows]
                except sqlite3.OperationalError:
                    pass

        like = f"%{query}%"
        sql = (
            "SELECT session_id, ordinal, role, kind, text, 0.0 AS score "
            "FROM messages WHERE text LIKE ?"
        )
        params = [like]
        if role:
            sql += " AND role = ?"
            params.append(role)
        sql += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)
        rows = self.conn.execute(sql, params).fetchall()
        return [_message_result(row) for row in rows]

    def _search_summaries(self, query: str, *, limit: int) -> list[dict[str, Any]]:
        like = f"%{query}%"
        rows = self.conn.execute(
            """
            SELECT s.session_id, s.summary, s.decisions_json, s.open_questions_json, sess.title
            FROM session_summaries s
            JOIN sessions sess ON sess.id = s.session_id
            WHERE s.summary LIKE ? OR s.decisions_json LIKE ? OR s.open_questions_json LIKE ?
            ORDER BY s.updated_at DESC
            LIMIT ?
            """,
            (like, like, like, limit),
        ).fetchall()
        return [
            {
                "type": "summary",
                "session_id": row["session_id"],
                "title": row["title"],
                "text": _snippet(row["summary"]),
                "score": 0.0,
            }
            for row in rows
        ]

    def _search_observations(self, query: str, *, limit: int) -> list[dict[str, Any]]:
        like = f"%{query}%"
        rows = self.conn.execute(
            """
            SELECT session_id, scope, subject, text, confidence
            FROM observations
            WHERE text LIKE ? OR subject LIKE ? OR scope LIKE ?
            ORDER BY confidence DESC, created_at DESC
            LIMIT ?
            """,
            (like, like, like, limit),
        ).fetchall()
        return [
            {
                "type": "observation",
                "session_id": row["session_id"],
                "scope": row["scope"],
                "subject": row["subject"],
                "text": _snippet(row["text"]),
                "confidence": row["confidence"],
                "score": 0.0,
            }
            for row in rows
        ]

    def _search_memory_items(self, query: str, *, limit: int) -> list[dict[str, Any]]:
        like = f"%{query}%"
        rows = self.conn.execute(
            """
            SELECT
              id, scope, subject, text, project, cwd, source,
              confidence, created_at, updated_at
            FROM memory_items
            WHERE text LIKE ? OR subject LIKE ? OR scope LIKE ? OR project LIKE ?
            ORDER BY confidence DESC, updated_at DESC
            LIMIT ?
            """,
            (like, like, like, like, limit),
        ).fetchall()
        return [
            {
                "type": "memory",
                "memory_id": row["id"],
                "scope": row["scope"],
                "subject": row["subject"],
                "project": row["project"],
                "source": row["source"],
                "text": _snippet(row["text"]),
                "confidence": row["confidence"],
                "score": 0.0,
            }
            for row in rows
        ]

    def _matching_memory_id(
        self,
        *,
        scope: str,
        subject: str,
        text: str,
        project: str | None,
    ) -> int | None:
        row = self.conn.execute(
            """
            SELECT id
            FROM memory_items
            WHERE scope = ?
              AND subject = ?
              AND text = ?
              AND (
                (project IS NULL AND ? IS NULL)
                OR project = ?
              )
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (scope, subject, text, project, project),
        ).fetchone()
        return int(row["id"]) if row else None

    def _matching_memory_origin_id(
        self,
        *,
        origin_key: str,
        scope: str,
        project: str | None,
    ) -> int | None:
        row = self.conn.execute(
            """
            SELECT id
            FROM memory_items
            WHERE origin_key = ?
              AND scope = ?
              AND (
                (project IS NULL AND ? IS NULL)
                OR project = ?
              )
            ORDER BY updated_at DESC
            LIMIT 1
            """,
            (origin_key, scope, project, project),
        ).fetchone()
        return int(row["id"]) if row else None

    def recent_sessions(
        self,
        *,
        limit: int = 10,
        project: str | None = None,
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT
              id, source_app, source_kind, title, cwd, project,
              started_at, updated_at, internal
            FROM sessions
            WHERE (? IS NULL OR project = ?)
            ORDER BY COALESCE(updated_at, started_at) DESC
            LIMIT ?
            """,
            (project, project, limit),
        ).fetchall()
        return [dict(row) for row in rows]

    def _project_summaries(self, project: str | None, *, limit: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT
              s.session_id, s.summary, s.decisions_json, s.open_questions_json,
              s.updated_at, sess.title, sess.project, sess.cwd
            FROM session_summaries s
            JOIN sessions sess ON sess.id = s.session_id
            WHERE (? IS NULL OR sess.project = ?)
            ORDER BY s.updated_at DESC
            LIMIT ?
            """,
            (project, project, limit),
        ).fetchall()
        return [
            {
                "session_id": row["session_id"],
                "title": row["title"],
                "project": row["project"],
                "cwd": row["cwd"],
                "summary": row["summary"],
                "decisions": _context_strings(_json_string_list(row["decisions_json"]), limit=8),
                "open_questions": _context_strings(
                    _json_string_list(row["open_questions_json"]),
                    limit=8,
                ),
                "updated_at": row["updated_at"],
            }
            for row in rows
        ]

    def _project_observations(self, project: str | None, *, limit: int) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT
              o.session_id, o.scope, o.subject, o.text, o.confidence,
              o.created_at, sess.project
            FROM observations o
            JOIN sessions sess ON sess.id = o.session_id
            WHERE (? IS NULL OR sess.project = ?)
            ORDER BY o.confidence DESC, o.created_at DESC
            LIMIT ?
            """,
            (project, project, limit * 3),
        ).fetchall()
        deduped: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str]] = set()
        for row in rows:
            key = (row["scope"], row["subject"], row["text"])
            if key in seen:
                continue
            seen.add(key)
            deduped.append(
                {
                    "session_id": row["session_id"],
                    "project": row["project"],
                    "scope": row["scope"],
                    "subject": row["subject"],
                    "text": row["text"],
                    "confidence": row["confidence"],
                    "created_at": row["created_at"],
                }
            )
            if len(deduped) >= limit:
                break
        return deduped

    def _project_memory_items(
        self,
        project: str | None,
        *,
        scope: str | None = None,
        limit: int,
        include_all: bool = False,
    ) -> list[dict[str, Any]]:
        rows = self.conn.execute(
            """
            SELECT
              id, scope, subject, text, project, cwd, source,
              origin_key, confidence, created_at, updated_at
            FROM memory_items
            WHERE
              (
                ? = 1
                OR (? IS NOT NULL AND (project = ? OR (project IS NULL AND scope = 'user')))
                OR (? IS NULL AND project IS NULL)
              )
              AND (? IS NULL OR scope = ?)
            ORDER BY
              CASE WHEN source = 'manual' THEN 0 ELSE 1 END,
              confidence DESC,
              updated_at DESC
            LIMIT ?
            """,
            (
                int(include_all),
                project,
                project,
                project,
                scope,
                scope,
                limit * 3,
            ),
        ).fetchall()
        deduped: list[dict[str, Any]] = []
        seen: set[tuple[str, str, str, str | None]] = set()
        for row in rows:
            key = (row["scope"], row["subject"], row["text"], row["project"])
            if key in seen:
                continue
            seen.add(key)
            deduped.append(_memory_item_dict(row))
            if len(deduped) >= limit:
                break
        return deduped

    def _project_matches(
        self,
        project: str | None,
        *,
        query: str | None,
        limit: int,
    ) -> list[dict[str, Any]]:
        if not query:
            return []
        matches = self.search(query, limit=max(limit * 3, 10), kind="all")
        if not project:
            return matches[:limit]
        session_ids = {
            row["id"]
            for row in self.conn.execute(
                "SELECT id FROM sessions WHERE project = ?",
                (project,),
            ).fetchall()
        }
        return [match for match in matches if match.get("session_id") in session_ids][:limit]

    def _latest_project(self) -> str | None:
        row = self.conn.execute(
            """
            SELECT project
            FROM sessions
            WHERE project IS NOT NULL AND project != ''
            ORDER BY COALESCE(updated_at, started_at) DESC
            LIMIT 1
            """
        ).fetchone()
        return str(row["project"]) if row else None

    def _resolve_project(self, *, project: str | None, cwd: str | Path | None) -> str | None:
        clean_project = str(project).strip() if project else ""
        if clean_project:
            return clean_project
        if cwd is not None:
            matched = self._project_for_cwd(cwd) or self._memory_project_for_cwd(cwd)
            if matched:
                return matched
            cwd_project = _project_from_cwd(cwd)
            if cwd_project:
                return cwd_project
        return self._latest_project()

    def _memory_target_project(
        self,
        *,
        scope: str,
        project: str | None,
        cwd: str | Path | None,
    ) -> str | None:
        clean_project = str(project).strip() if project else ""
        if clean_project:
            return clean_project
        if scope == "user":
            return None
        if cwd is not None:
            matched = self._project_for_cwd(cwd) or self._memory_project_for_cwd(cwd)
            if matched:
                return matched
            return _project_from_cwd(cwd)
        return self._latest_project()

    def _memory_project_for_cwd(self, cwd: str | Path) -> str | None:
        target = _normalized_path(cwd)
        rows = self.conn.execute(
            """
            SELECT project, cwd
            FROM memory_items
            WHERE project IS NOT NULL AND project != '' AND cwd IS NOT NULL AND cwd != ''
            """
        ).fetchall()
        best_project: str | None = None
        best_length = -1
        for row in rows:
            memory_cwd = _normalized_path(row["cwd"])
            if _path_is_under(target, memory_cwd) and len(memory_cwd) > best_length:
                best_project = str(row["project"])
                best_length = len(memory_cwd)
        return best_project

    def _project_for_cwd(self, cwd: str | Path) -> str | None:
        target = _normalized_path(cwd)
        rows = self.conn.execute(
            """
            SELECT project, cwd
            FROM sessions
            WHERE project IS NOT NULL AND project != '' AND cwd IS NOT NULL AND cwd != ''
            """
        ).fetchall()
        best_project: str | None = None
        best_length = -1
        for row in rows:
            session_cwd = _normalized_path(row["cwd"])
            if _path_is_under(target, session_cwd) and len(session_cwd) > best_length:
                best_project = str(row["project"])
                best_length = len(session_cwd)
        return best_project

    def _project_session_count(self, project: str | None) -> int:
        if not project:
            row = self.conn.execute("SELECT COUNT(*) AS count FROM sessions").fetchone()
        else:
            row = self.conn.execute(
                "SELECT COUNT(*) AS count FROM sessions WHERE project = ?",
                (project,),
            ).fetchone()
        return int(row["count"])

    def stats(self) -> dict[str, Any]:
        def count(query: str) -> int:
            row = self.conn.execute(query).fetchone()
            return int(row["count"])

        queue_rows = self.conn.execute(
            "SELECT status, COUNT(*) AS count FROM queue GROUP BY status"
        ).fetchall()
        source_rows = self.conn.execute(
            "SELECT source_app, COUNT(*) AS count FROM sessions GROUP BY source_app"
        ).fetchall()
        return {
            "path": str(self.path),
            "fts_available": self.fts_available,
            "sessions": count("SELECT COUNT(*) AS count FROM sessions"),
            "messages": count("SELECT COUNT(*) AS count FROM messages"),
            "summaries": count("SELECT COUNT(*) AS count FROM session_summaries"),
            "observations": count("SELECT COUNT(*) AS count FROM observations"),
            "memory_items": count("SELECT COUNT(*) AS count FROM memory_items"),
            "queue": {row["status"]: row["count"] for row in queue_rows},
            "sources": {row["source_app"]: row["count"] for row in source_rows},
        }


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


def _json_string_list(value: str | None) -> list[str]:
    if not value:
        return []
    try:
        parsed = json.loads(value)
    except json.JSONDecodeError:
        return []
    return _string_list(parsed)


def _context_strings(values: Any, *, limit: int) -> list[str]:
    filtered: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = _clean_context_string(str(value))
        if not text or text in seen:
            continue
        seen.add(text)
        filtered.append(text)
        if len(filtered) >= limit:
            break
    return filtered


def _clean_context_string(value: str) -> str:
    text = re.sub(r"\s+", " ", value).strip()
    text = re.sub(r"^[-*]\s+", "", text).strip()
    if len(text) < 12:
        return ""
    lowered = text.lower()
    prompt_starts = (
        "дай ",
        "скажи",
        "что там",
        "what ",
        "tell ",
        "show ",
        "list ",
    )
    if lowered.startswith(prompt_starts):
        return ""
    if len(text) > 180:
        return _snippet(text, limit=180)
    return text


def _context_brief(
    *,
    project: str | None,
    session_count: int,
    summaries: list[dict[str, Any]],
    decisions: list[str],
    open_questions: list[str],
    memories: list[dict[str, Any]],
    observations: list[dict[str, Any]],
    matches: list[dict[str, Any]],
) -> str:
    parts = [f"Project: {project or 'all'} ({session_count} sessions)."]
    if summaries:
        parts.append(f"Latest: {_snippet(str(summaries[0]['summary']), limit=220)}")
    if memories:
        top_memories = [str(item["text"]) for item in memories[:3]]
        parts.append("Pinned memory: " + "; ".join(top_memories))
    if decisions:
        parts.append("Decisions: " + "; ".join(decisions[:3]))
    if open_questions:
        parts.append("Open questions: " + "; ".join(open_questions[:3]))
    if observations:
        top_observations = [str(item["text"]) for item in observations[:3]]
        parts.append("Observations: " + "; ".join(top_observations))
    if matches:
        parts.append(f"Relevant matches: {len(matches)}.")
    return "\n".join(parts)


def _profile_observation_bucket(item: dict[str, Any]) -> str | None:
    scope = str(item.get("scope") or "").lower()
    subject = str(item.get("subject") or "").lower()
    text = str(item.get("text") or "").lower()
    if "multi_agent" in subject or any(word in text for word in ("dashboard", "window", "окн")):
        return "warning"
    constraint_subjects = (
        "provider",
        "cross_chat",
        "memory",
        "review",
        "coding",
        "source",
    )
    if scope in {"project", "workflow"} or any(word in subject for word in constraint_subjects):
        return "constraint"
    if scope == "user" or "preference" in subject or "prefers" in text:
        return "preference"
    return None


def _profile_brief(
    *,
    project: str | None,
    session_count: int,
    summaries: list[dict[str, Any]],
    decisions: list[str],
    open_questions: list[str],
    preferences: list[str],
    constraints: list[str],
    warnings: list[str],
) -> str:
    parts = [f"Dynamic project profile: {project or 'all'} ({session_count} sessions)."]
    if summaries:
        parts.append(f"Latest: {_snippet(str(summaries[0]['summary']), limit=220)}")
    if preferences:
        parts.append("Preferences: " + "; ".join(preferences[:3]))
    if constraints:
        parts.append("Constraints: " + "; ".join(constraints[:3]))
    if warnings:
        parts.append("Warnings: " + "; ".join(warnings[:3]))
    if decisions:
        parts.append("Decisions: " + "; ".join(decisions[:3]))
    if open_questions:
        parts.append("Open questions: " + "; ".join(open_questions[:3]))
    return "\n".join(parts)


def _latest_timestamp(*collections: list[dict[str, Any]]) -> str | None:
    values: list[str] = []
    for collection in collections:
        for item in collection:
            for key in ("updated_at", "created_at", "started_at"):
                value = item.get(key)
                if value:
                    values.append(str(value))
                    break
    return max(values) if values else None


def _project_from_cwd(cwd: str | Path) -> str | None:
    name = Path(cwd).expanduser().name
    return name or str(cwd)


def _normalized_path(value: str | Path) -> str:
    try:
        path = Path(value).expanduser().resolve()
    except OSError:
        path = Path(value).expanduser().absolute()
    return os.path.normcase(str(path)).rstrip("\\/")


def _path_is_under(candidate: str, parent: str) -> bool:
    if not candidate or not parent:
        return False
    return candidate == parent or candidate.startswith(parent + os.sep)


def _fts_query(query: str) -> str:
    tokens = re.findall(r"\w+", query, flags=re.UNICODE)
    return " OR ".join(f'"{token}"' for token in tokens[:12])


def _message_result(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "type": "message",
        "session_id": row["session_id"],
        "ordinal": row["ordinal"],
        "role": row["role"],
        "kind": row["kind"],
        "text": _snippet(row["text"]),
        "score": row["score"],
    }


def _memory_item_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {
        "id": row["id"],
        "scope": row["scope"],
        "subject": row["subject"],
        "text": row["text"],
        "project": row["project"],
        "cwd": row["cwd"],
        "source": row["source"],
        "origin_key": row["origin_key"],
        "confidence": row["confidence"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"],
    }


def _normalize_scope(value: str | None) -> str:
    scope = str(value or "").strip().lower()
    if scope in {"user", "project", "workflow"}:
        return scope
    raise ValueError("Memory scope must be one of: user, project, workflow.")


def _clean_memory_text(value: str) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _clean_memory_label(value: str | None, *, default: str) -> str:
    clean = re.sub(r"[^\w.:-]+", "_", str(value or "").strip().lower()).strip("_")
    return clean or default


def _clean_origin_key(value: str | None) -> str | None:
    clean = str(value or "").strip()
    if not clean:
        return None
    return re.sub(r"\s+", "_", clean)[:300]


def _memory_export_origin_key(item: dict[str, Any]) -> str | None:
    existing = _clean_origin_key(str(item.get("origin_key") or ""))
    if existing:
        return existing
    raw_id = item.get("id")
    if raw_id is None:
        return None
    try:
        memory_id = int(raw_id)
    except (TypeError, ValueError):
        return None
    scope = _normalize_scope(str(item.get("scope") or "project"))
    project = (
        "global"
        if scope == "user"
        else _clean_memory_label(
            str(item.get("project") or "unscoped"),
            default="unscoped",
        )
    )
    return f"codex-native-memory:v1:{scope}:{project}:{memory_id}"


def _memory_cwd(value: str | Path | None) -> str | None:
    if value is None:
        return None
    return str(Path(value).expanduser())


def _snippet(text: str, *, limit: int = 500) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip() + "..."
