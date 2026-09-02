from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .storage import LocalDatabase
from .types import AgentEvent


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class MemoryRecord:
    summary: str = ""
    facts: list[str] = field(default_factory=list)
    preferences: list[str] = field(default_factory=list)
    decisions: list[str] = field(default_factory=list)
    open_tasks: list[str] = field(default_factory=list)
    recent_tasks: list[str] = field(default_factory=list)
    touched_files: list[str] = field(default_factory=list)
    updated_at: str = ""


class MemoryStore:
    def __init__(self, workspace_root: Path, namespace: str | None = None) -> None:
        self.workspace_root = workspace_root
        self.namespace = namespace
        if namespace:
            self.path = workspace_root / ".chasm" / "sessions" / namespace / "memory.json"
        else:
            self.path = workspace_root / ".chasm" / "memory.json"

    def load(self) -> MemoryRecord:
        if not self.path.exists():
            return MemoryRecord()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return MemoryRecord(
            summary=data.get("summary", ""),
            facts=list(data.get("facts", [])),
            preferences=list(data.get("preferences", [])),
            decisions=list(data.get("decisions", [])),
            open_tasks=list(data.get("open_tasks", [])),
            recent_tasks=list(data.get("recent_tasks", [])),
            touched_files=list(data.get("touched_files", [])),
            updated_at=data.get("updated_at", ""),
        )

    def save(self, record: MemoryRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "summary": record.summary,
            "facts": record.facts[-20:],
            "preferences": record.preferences[-20:],
            "decisions": record.decisions[-20:],
            "open_tasks": record.open_tasks[-20:],
            "recent_tasks": record.recent_tasks[-10:],
            "touched_files": record.touched_files[-50:],
            "updated_at": record.updated_at or _utc_now(),
        }
        self.path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def append_fact(self, fact: str) -> None:
        record = self.load()
        if fact not in record.facts:
            record.facts.append(fact)
        record.updated_at = _utc_now()
        self.save(record)

    def update_from_run(
        self,
        task: str,
        final_message: str,
        events: list[AgentEvent],
        reflection: dict[str, Any] | None = None,
    ) -> None:
        record = self.load()
        record.recent_tasks.append(task)
        if reflection:
            summary = str(reflection.get("summary") or "").strip() or final_message.strip()
            if summary:
                record.summary = summary[:800]
            for item in reflection.get("lessons", []) or []:
                text = str(item).strip()
                if text and text not in record.facts:
                    record.facts.append(text)
            for item in reflection.get("next_steps", []) or []:
                text = str(item).strip()
                if text and text not in record.open_tasks:
                    record.open_tasks.append(text)
            for item in reflection.get("files", []) or []:
                text = str(item).strip()
                if text and text not in record.touched_files:
                    record.touched_files.append(text)
            for item in reflection.get("decisions", []) or []:
                text = str(item).strip()
                if text and text not in record.decisions:
                    record.decisions.append(text)
            for item in reflection.get("preferences", []) or []:
                text = str(item).strip()
                if text and text not in record.preferences:
                    record.preferences.append(text)
        elif final_message.strip():
            record.summary = final_message.strip()[:800]

        if final_message.strip() and any(key in final_message.lower() for key in ["terminated", "error", "limit"]):
            fallback = f"Follow up on: {task[:200]}"
            if fallback not in record.open_tasks:
                record.open_tasks.append(fallback)

        touched = set(record.touched_files)
        for event in events:
            if event.kind != "tool_call":
                continue
            name = event.payload.get("name")
            args = event.payload.get("args") or {}
            path = args.get("path")
            if name in {"read_file", "write_file", "replace_text", "search_text", "list_files", "delete_path"} and path:
                touched.add(str(path))
        record.touched_files = sorted(touched)
        record.updated_at = _utc_now()
        self.save(record)

    def render(self) -> str:
        record = self.load()
        parts: list[str] = []
        if record.summary:
            parts.append(f"Current project memory: {record.summary}")
        if record.facts:
            parts.append("Facts:")
            parts.extend(f"- {fact}" for fact in record.facts[-8:])
        if record.decisions:
            parts.append("Decisions:")
            parts.extend(f"- {item}" for item in record.decisions[-8:])
        if record.preferences:
            parts.append("Preferences:")
            parts.extend(f"- {item}" for item in record.preferences[-8:])
        if record.open_tasks:
            parts.append("Open tasks:")
            parts.extend(f"- {item}" for item in record.open_tasks[-8:])
        if record.touched_files:
            parts.append("Touched files:")
            parts.extend(f"- {item}" for item in record.touched_files[-12:])
        if record.recent_tasks:
            parts.append("Recent tasks:")
            parts.extend(f"- {item}" for item in record.recent_tasks[-5:])
        return "\n".join(parts).strip()


def _tokens(text: str) -> set[str]:
    return {
        token
        for token in "".join(ch.lower() if ch.isalnum() else " " for ch in text).split()
        if len(token) > 2
    }


class MemoryArchive:
    def __init__(self, db: LocalDatabase) -> None:
        self.db = db

    def render(
        self,
        query: str,
        user_id: int,
        project_root: str,
        limit: int = 4,
        exclude_session_id: str | None = None,
    ) -> str:
        query_tokens = _tokens(query)
        candidates = []
        for item in self.db.list_sessions(user_id=user_id, limit=40):
            if exclude_session_id and item.get("id") == exclude_session_id:
                continue
            if item.get("project_root") != project_root:
                continue
            blob = " ".join(
                [
                    str(item.get("task", "")),
                    str(item.get("result", "")),
                    str(item.get("status", "")),
                ]
            )
            score = len(query_tokens & _tokens(blob))
            if score > 0:
                candidates.append((score, item))
        candidates.sort(key=lambda pair: (pair[0], pair[1].get("updated_at", "")), reverse=True)
        lines: list[str] = []
        for _, item in candidates[:limit]:
            lines.append(
                f"- {item.get('task', '')[:80]} | {item.get('status', '')} | {str(item.get('result', ''))[:160]}"
            )
        return "\n".join(lines).strip()
