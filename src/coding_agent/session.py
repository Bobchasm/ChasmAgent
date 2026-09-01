from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .storage import LocalDatabase
from .types import AgentEvent


@dataclass(slots=True)
class SessionRecord:
    id: str
    task: str
    project_root: str
    user_id: int = 1
    mode: str = "auto"
    status: str = "queued"
    created_at: str = ""
    updated_at: str = ""
    events: list[dict[str, Any]] = field(default_factory=list)
    messages: list[dict[str, Any]] = field(default_factory=list)
    result: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "user_id": self.user_id,
            "task": self.task,
            "project_root": self.project_root,
            "mode": self.mode,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "events": self.events,
            "messages": self.messages,
            "result": self.result,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SessionRecord":
        return cls(
            id=payload["id"],
            user_id=int(payload.get("user_id", 1)),
            task=payload.get("task", ""),
            project_root=payload.get("project_root", ""),
            mode=payload.get("mode", "auto"),
            status=payload.get("status", "queued"),
            created_at=payload.get("created_at", ""),
            updated_at=payload.get("updated_at", ""),
            events=list(payload.get("events", [])),
            messages=list(payload.get("messages", [])),
            result=payload.get("result", ""),
        )


class SessionStore:
    def __init__(self, data_dir: Path, legacy_workspace_root: Path | None = None) -> None:
        self.data_dir = data_dir.expanduser().resolve()
        self.db = LocalDatabase(self.data_dir)
        self.system_user = self.db.ensure_system_user()
        if legacy_workspace_root is not None:
            self.db.import_legacy_sessions(legacy_workspace_root)

    def create(self, task: str, project_root: str, mode: str = "auto", user_id: int = 1) -> SessionRecord:
        if user_id == 1 and self.system_user is not None:
            user_id = self.system_user.id
        record = self.db.create_session(user_id=user_id, task=task, project_root=project_root, mode=mode)
        return SessionRecord.from_dict(record)

    def get(self, session_id: str) -> SessionRecord | None:
        record = self.db.get_session(session_id)
        if record is None:
            return None
        return SessionRecord.from_dict(record)

    def list_recent(self, limit: int = 20, user_id: int = 1) -> list[SessionRecord]:
        if user_id == 1 and self.system_user is not None:
            user_id = self.system_user.id
        return [SessionRecord.from_dict(item) for item in self.db.list_sessions(user_id=user_id, limit=limit)]

    def update(self, session_id: str, **fields: Any) -> SessionRecord:
        record = self.db.update_session(session_id, **fields)
        return SessionRecord.from_dict(record)

    def append_event(self, session_id: str, event: AgentEvent) -> None:
        self.db.append_event(session_id, event)

    def append_message(self, session_id: str, role: str, content: str) -> None:
        self.db.append_message(session_id, role, content)

    def get_events_since(self, session_id: str, index: int) -> list[dict[str, Any]]:
        return self.db.get_events_since(session_id, index)

    def get_events(self, session_id: str) -> list[dict[str, Any]]:
        return self.db.get_events(session_id)

    def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        return self.db.get_messages(session_id)

    def delete(self, session_id: str, user_id: int) -> None:
        self.db.delete_session(session_id, user_id)

    def wait_for_events(self, session_id: str, index: int, timeout: float | None = None) -> None:
        # SQLite is polled by the SSE loop; this shim keeps the old API surface.
        import time

        deadline = None if timeout is None else time.monotonic() + timeout
        while True:
            if len(self.get_events_since(session_id, index)) > 0:
                return
            if deadline is not None and time.monotonic() >= deadline:
                return
            time.sleep(0.25)
