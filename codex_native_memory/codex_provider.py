from __future__ import annotations

import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any

from .paths import ENV_CODEX, ensure_runtime_dirs, internal_workdir


SUMMARY_SCHEMA: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "properties": {
        "summary": {"type": "string"},
        "decisions": {"type": "array", "items": {"type": "string"}},
        "open_questions": {"type": "array", "items": {"type": "string"}},
        "observations": {
            "type": "array",
            "items": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "scope": {"type": "string"},
                    "subject": {"type": "string"},
                    "text": {"type": "string"},
                    "confidence": {"type": "number"},
                },
                "required": ["scope", "subject", "text", "confidence"],
            },
        },
    },
    "required": ["summary", "decisions", "open_questions", "observations"],
}


class CodexProvider:
    def __init__(self, *, root: str | Path | None = None, timeout_seconds: int = 180):
        self.root = ensure_runtime_dirs(root)
        self.timeout_seconds = timeout_seconds
        self.codex_path = find_codex_cli()

    def available(self) -> bool:
        return self.codex_path is not None and self.codex_path.exists()

    def summarize(self, session_id: str, messages: list[dict[str, Any]]) -> dict[str, Any]:
        if not self.available():
            raise RuntimeError("Codex CLI was not found")

        prompt = build_summary_prompt(session_id, messages)
        workdir = internal_workdir(self.root)
        workdir.mkdir(parents=True, exist_ok=True)

        with tempfile.TemporaryDirectory(prefix="codex-native-memory-", dir=self.root / "tmp") as tmp:
            tmp_path = Path(tmp)
            schema_path = tmp_path / "schema.json"
            output_path = tmp_path / "summary.json"
            schema_path.write_text(json.dumps(SUMMARY_SCHEMA), encoding="utf-8")
            command = [
                str(self.codex_path),
                "exec",
                "--ephemeral",
                "--ignore-user-config",
                "--ignore-rules",
                "--skip-git-repo-check",
                "--sandbox",
                "read-only",
                "--cd",
                str(workdir),
                "--output-schema",
                str(schema_path),
                "--output-last-message",
                str(output_path),
            ]
            model = os.environ.get("CODEX_NATIVE_MEMORY_MODEL")
            if model:
                command.extend(["--model", model])
            command.append(prompt)

            completed = subprocess.run(
                command,
                cwd=workdir,
                text=True,
                capture_output=True,
                timeout=self.timeout_seconds,
                check=False,
            )
            if completed.returncode != 0:
                detail = (completed.stderr or completed.stdout or "").strip()
                raise RuntimeError(f"codex exec failed with exit code {completed.returncode}: {detail}")
            raw = output_path.read_text(encoding="utf-8", errors="replace")
            return parse_json_response(raw)


def find_codex_cli() -> Path | None:
    candidates: list[Path] = []
    for raw in (os.environ.get(ENV_CODEX), os.environ.get("CODEX_CLI_PATH")):
        if raw:
            candidates.append(Path(raw).expanduser())

    candidates.append(Path.home() / ".codex" / "plugins" / ".plugin-appserver" / "codex.exe")
    bin_root = Path.home() / "AppData" / "Local" / "OpenAI" / "Codex" / "bin"
    if bin_root.exists():
        candidates.extend(sorted(bin_root.glob("*/codex.exe"), key=_mtime, reverse=True))

    for candidate in candidates:
        if candidate.exists():
            return candidate.resolve()
    return None


def build_summary_prompt(session_id: str, messages: list[dict[str, Any]]) -> str:
    transcript = render_transcript(messages, limit_chars=45_000)
    return (
        "You are Codex Native Memory internal summarizer. "
        "Summarize the imported Codex conversation for later retrieval. "
        "Return strict JSON matching the provided schema. "
        "Write concise English facts even if the conversation is in another language. "
        "Only store durable project/user preferences, decisions, constraints, and unresolved tasks. "
        "Do not include secrets, credentials, tokens, or long verbatim source text.\n\n"
        f"Session id: {session_id}\n\n"
        f"Transcript:\n{transcript}"
    )


def render_transcript(messages: list[dict[str, Any]], *, limit_chars: int) -> str:
    parts: list[str] = []
    used = 0
    for message in messages:
        text = str(message.get("text") or "").strip()
        if not text:
            continue
        block = f"{message.get('role', 'unknown').upper()}: {text}\n"
        if used + len(block) > limit_chars:
            remaining = max(limit_chars - used, 0)
            if remaining > 200:
                parts.append(block[:remaining])
            parts.append("\n[Transcript truncated]\n")
            break
        parts.append(block)
        used += len(block)
    return "\n".join(parts)


def parse_json_response(raw: str) -> dict[str, Any]:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*", "", cleaned)
        cleaned = re.sub(r"\s*```$", "", cleaned)
    try:
        value = json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            raise
        value = json.loads(match.group(0))
    if not isinstance(value, dict):
        raise ValueError("Codex summary response was not a JSON object")
    return value


def _mtime(path: Path) -> float:
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0
