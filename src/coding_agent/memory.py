from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .types import AgentEvent


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class MemoryRecord:
    summary: str = ""
    facts: list[str] = field(default_factory=list)
    recent_tasks: list[str] = field(default_factory=list)
    touched_files: list[str] = field(default_factory=list)
    updated_at: str = ""


class MemoryStore:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root
        self.path = workspace_root / ".chasm" / "memory.json"

    def load(self) -> MemoryRecord:
        if not self.path.exists():
            return MemoryRecord()
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return MemoryRecord(
            summary=data.get("summary", ""),
            facts=list(data.get("facts", [])),
            recent_tasks=list(data.get("recent_tasks", [])),
            touched_files=list(data.get("touched_files", [])),
            updated_at=data.get("updated_at", ""),
        )

    def save(self, record: MemoryRecord) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "summary": record.summary,
            "facts": record.facts[-20:],
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

    def update_from_run(self, task: str, final_message: str, events: list[AgentEvent]) -> None:
        record = self.load()
        record.recent_tasks.append(task)
        if final_message.strip():
            record.summary = final_message.strip()[:800]

        touched = set(record.touched_files)
        for event in events:
            if event.kind != "tool_call":
                continue
            name = event.payload.get("name")
            args = event.payload.get("args") or {}
            path = args.get("path")
            if name in {"read_file", "write_file", "replace_text", "search_text", "list_files"} and path:
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
        if record.touched_files:
            parts.append("Touched files:")
            parts.extend(f"- {item}" for item in record.touched_files[-12:])
        if record.recent_tasks:
            parts.append("Recent tasks:")
            parts.extend(f"- {item}" for item in record.recent_tasks[-5:])
        return "\n".join(parts).strip()

