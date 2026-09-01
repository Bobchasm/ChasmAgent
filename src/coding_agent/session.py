from __future__ import annotations

import json
import threading
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .types import AgentEvent


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(slots=True)
class SessionRecord:
    id: str
    task: str
    project_root: str
    mode: str = "auto"
    status: str = "queued"
    created_at: str = field(default_factory=_utc_now)
    updated_at: str = field(default_factory=_utc_now)
    events: list[dict[str, Any]] = field(default_factory=list)
    result: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "task": self.task,
            "project_root": self.project_root,
            "mode": self.mode,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "events": self.events,
            "result": self.result,
        }

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SessionRecord":
        return cls(
            id=payload["id"],
            task=payload.get("task", ""),
            project_root=payload.get("project_root", ""),
            mode=payload.get("mode", "auto"),
            status=payload.get("status", "queued"),
            created_at=payload.get("created_at", _utc_now()),
            updated_at=payload.get("updated_at", _utc_now()),
            events=list(payload.get("events", [])),
            result=payload.get("result", ""),
        )


class SessionStore:
    def __init__(self, workspace_root: Path) -> None:
        self.workspace_root = workspace_root
        self.session_dir = workspace_root / ".chasm" / "sessions"
        self._lock = threading.Lock()
        self._cond = threading.Condition(self._lock)
        self._sessions: dict[str, SessionRecord] = {}
        self._load_existing()

    def _path(self, session_id: str) -> Path:
        return self.session_dir / f"{session_id}.json"

    def _load_existing(self) -> None:
        if not self.session_dir.exists():
            return
        for path in sorted(self.session_dir.glob("*.json")):
            try:
                record = SessionRecord.from_dict(json.loads(path.read_text(encoding="utf-8")))
            except Exception:  # noqa: BLE001
                continue
            self._sessions[record.id] = record

    def _save(self, record: SessionRecord) -> None:
        self.session_dir.mkdir(parents=True, exist_ok=True)
        record.updated_at = _utc_now()
        self._path(record.id).write_text(json.dumps(record.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")

    def create(self, task: str, project_root: str, mode: str = "auto") -> SessionRecord:
        record = SessionRecord(id=uuid.uuid4().hex[:12], task=task, project_root=project_root, mode=mode)
        with self._cond:
            self._sessions[record.id] = record
            self._save(record)
            self._cond.notify_all()
        return record

    def get(self, session_id: str) -> SessionRecord | None:
        with self._lock:
            return self._sessions.get(session_id)

    def list_recent(self, limit: int = 20) -> list[SessionRecord]:
        with self._lock:
            items = sorted(self._sessions.values(), key=lambda item: item.updated_at, reverse=True)
            return items[:limit]

    def update(self, session_id: str, **fields: Any) -> SessionRecord:
        with self._cond:
            session = self._sessions[session_id]
            for key, value in fields.items():
                setattr(session, key, value)
            self._save(session)
            self._cond.notify_all()
            return session

    def append_event(self, session_id: str, event: AgentEvent) -> None:
        with self._cond:
            session = self._sessions[session_id]
            session.events.append({"kind": event.kind, "payload": event.payload})
            self._save(session)
            self._cond.notify_all()

    def get_events_since(self, session_id: str, index: int) -> list[dict[str, Any]]:
        with self._lock:
            session = self._sessions.get(session_id)
            if session is None:
                return []
            return session.events[index:]

    def wait_for_events(self, session_id: str, index: int, timeout: float | None = None) -> None:
        with self._cond:
            def _has_new() -> bool:
                session = self._sessions.get(session_id)
                if session is None:
                    return True
                return len(session.events) > index

            self._cond.wait_for(_has_new, timeout=timeout)
