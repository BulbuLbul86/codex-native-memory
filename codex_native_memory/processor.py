from __future__ import annotations

import re
from typing import Any

from .codex_provider import CodexProvider
from .db import MemoryDB


class Processor:
    def __init__(self, db: MemoryDB, provider: CodexProvider | None = None):
        self.db = db
        self.provider = provider

    def process(self, *, limit: int = 10, mode: str = "auto") -> dict[str, int]:
        stats = {"seen": 0, "done": 0, "fallback": 0, "errors": 0}
        provider = self.provider
        if mode in {"auto", "codex"} and provider is None:
            provider = CodexProvider(root=self.db.path.parent)

        for item in self.db.pending(limit=limit):
            stats["seen"] += 1
            session_id = item["session_id"]
            messages = self.db.fetch_messages(session_id)
            try:
                result: dict[str, Any]
                if mode in {"auto", "codex"} and provider and provider.available():
                    try:
                        result = provider.summarize(session_id, messages)
                    except Exception:
                        if mode == "codex":
                            raise
                        result = extractive_summary(messages)
                        stats["fallback"] += 1
                elif mode == "codex":
                    raise RuntimeError("Codex CLI provider is not available")
                else:
                    result = extractive_summary(messages)
                    if mode == "auto":
                        stats["fallback"] += 1

                self.db.store_summary(session_id, result)
                self.db.mark_queue(item["id"], "done")
                stats["done"] += 1
            except Exception as exc:
                self.db.mark_queue(item["id"], "error", str(exc))
                stats["errors"] += 1
        return stats


def extractive_summary(messages: list[dict[str, Any]]) -> dict[str, Any]:
    user_messages = [msg for msg in messages if msg.get("role") == "user"]
    assistant_messages = [msg for msg in messages if msg.get("role") == "assistant"]
    first_user = _first_text(user_messages)
    last_user = _last_text(user_messages)
    last_assistant = _last_text(assistant_messages)

    summary_parts = [f"Imported {len(messages)} messages."]
    if first_user:
        summary_parts.append(f"First user request: {_short(first_user, 220)}")
    if last_user and last_user != first_user:
        summary_parts.append(f"Latest user request: {_short(last_user, 220)}")
    if last_assistant:
        summary_parts.append(f"Latest assistant note: {_short(last_assistant, 220)}")

    combined_user_text = "\n".join(str(msg.get("text") or "") for msg in user_messages)
    observations = infer_observations(combined_user_text)
    decisions = infer_decisions(messages)

    return {
        "summary": " ".join(summary_parts),
        "decisions": decisions,
        "open_questions": [],
        "observations": observations,
    }


def infer_observations(text: str) -> list[dict[str, Any]]:
    observations: list[dict[str, Any]] = []
    lowered = text.lower()
    if "на русском" in lowered or "по-русски" in lowered:
        observations.append(
            {
                "scope": "user",
                "subject": "language_preference",
                "text": "User prefers Russian responses.",
                "confidence": 0.95,
            }
        )
    if "кодекс" in lowered and ("claude" in lowered or "gemini" in lowered or "openrouter" in lowered):
        observations.append(
            {
                "scope": "project",
                "subject": "provider_preference",
                "text": "User wants Codex-native tooling without Claude, Gemini, or OpenRouter dependencies.",
                "confidence": 0.9,
            }
        )
    if "агент" in lowered and ("дашборд" in lowered or "окн" in lowered):
        observations.append(
            {
                "scope": "workflow",
                "subject": "multi_agent_usage",
                "text": "Avoid spawning multi-agent dashboards unless the user explicitly accepts that UI noise.",
                "confidence": 0.85,
            }
        )
    if "чат" in lowered and ("памят" in lowered or "memory" in lowered):
        observations.append(
            {
                "scope": "project",
                "subject": "cross_chat_memory",
                "text": "Cross-chat project continuity is important because work is spread across multiple Codex threads.",
                "confidence": 0.85,
            }
        )
    return observations


def infer_decisions(messages: list[dict[str, Any]]) -> list[str]:
    decisions: list[str] = []
    patterns = (
        r"\binstalled\b",
        r"\bconfigured\b",
        r"\bdecided\b",
        r"\bcreated\b",
        r"установ",
        r"настро",
        r"реш",
    )
    combined = "\n".join(str(msg.get("text") or "") for msg in messages)
    for line in combined.splitlines():
        stripped = line.strip()
        if len(stripped) < 12 or len(stripped) > 220:
            continue
        if any(re.search(pattern, stripped, flags=re.IGNORECASE) for pattern in patterns):
            decisions.append(stripped)
        if len(decisions) >= 8:
            break
    return decisions


def _first_text(messages: list[dict[str, Any]]) -> str:
    return str(messages[0].get("text") or "").strip() if messages else ""


def _last_text(messages: list[dict[str, Any]]) -> str:
    return str(messages[-1].get("text") or "").strip() if messages else ""


def _short(text: str, limit: int) -> str:
    clean = re.sub(r"\s+", " ", text).strip()
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip() + "..."
