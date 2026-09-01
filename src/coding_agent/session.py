from __future__ import annotations

import threading
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .types import AgentEvent


@dataclass(slots=True)
class SessionRecord:
    id: str
    task: str
    mode: str = "auto"
    status: str = "queued"
    events: list[dict[str, Any]] = field(default_factory=list)
    result: str = ""


class SessionStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._sessions: dict[str, SessionRecord] = {}

    def create(self, task: str, mode: str = "auto") -> SessionRecord:
        record = SessionRecord(id=uuid.uuid4().hex[:12], task=task, mode=mode)
        with self._lock:
            self._sessions[record.id] = record
        return record

    def get(self, session_id: str) -> SessionRecord | None:
        with self._lock:
            return self._sessions.get(session_id)

    def append_event(self, session_id: str, event: AgentEvent) -> None:
        with self._lock:
            session = self._sessions[session_id]
            session.events.append({"kind": event.kind, "payload": event.payload})
